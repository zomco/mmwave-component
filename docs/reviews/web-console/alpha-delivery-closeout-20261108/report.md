# Alpha 交付收口：D3 源码追溯与构建运行目录（实现方交付，待复核）

日期：2026-11-08。组件 HEAD `2c0c0e9d753841b51dcc6b70d1a58df5fb21d62d`（基线即此提交；本轮工具修改为未提交工作树改动，如实记录）。工作区验收提交 `a6cc7366a04e5241d6a4ba4caba39ef5ccce788d`。

## 结论

- **软件基本功能（工具+测试+文档）**：pass。source-state 机制、运行目录隔离、失败落盘与文档收口全部实现并通过 22/22 候选工具测试、23/23 发布工具回归与 USB 检查。
- **新候选目标编译**：**not completed（环境阻断）**。真实构建 `v0.1.0-alpha.2`（run `closeout-alpha-20261108`）在 ESPHome 生成 IDF 组件清单阶段失败：`api.registry.platformio.org` HTTP 超时（DNS 可解析、HTTP 不通；github 同样超时）。2026-11-06 演练成功时网络可用；本环境当前无出口。按包指示保留失败日志、候选标记未完成、不盲目重试。
- **新候选真机**：not_run（无授权，前置编译也未完成）。
- **发布批准**：未批准；是否安排首次 Alpha 短真机/发布由维护者决定，本包不自动执行。

---

## T1：自动保存本次构建的源码身份（C1/C2）

`scripts/build_r60_candidate.py` 新增（由真实构建入口 `main()` 在任何盖章/编译动作之前调用，非独立脚本）：

- `record_source_state()` 在构建开始时写 `source-state.json`：运行 ID、记录时间、version/channel/profile（`r60-daily`）、固定 ESPHome 版本（2026.9.1）、HEAD、clean/dirty 状态、构建实际消费输入的相对路径与 SHA-256。
- 收集范围明确：`EXPLICIT_SOURCE_FILES`（工厂/基础配置、共享 MWCP/设备/区域配置、三个工具脚本）+ `EXPLICIT_SOURCE_DIRS`（`components/mmwave_host`、`components/r60abd1`、`protocol/cpp`）递归，共 48 个文件（真实运行实测）。固定 ESPHome 版本记录在 venv/锁文件层面，不追溯全部 ESPHome 依赖源码（按包边界登记）。
- 脏树时 `capture_git_state()` 保存范围内文件的 `git diff HEAD --` 到 `source-dirty.patch`，并列出命中的 porcelain 行（dirtyScopeFiles）。Git 读取失败 → `head/status = unknown` 并记录错误，不默认 clean；摘要直接带 `gitStatus` 字段。
- 盖章后的配置单独保存为 `compiled.factory.yaml` 并在摘要中哈希（`stampedConfigSha256`）；干净源码状态（source-state）与预期盖章变更（compiled.factory.yaml）分开记录。
- 构建结束前 `verify_source_inputs()` 重哈希全部已记录输入：一致 → `status: success`；变化 → `status: uncertain` + `modifiedInputsDuringBuild`，不冒充同一确定源码候选。
- 真实失败运行验证（run `closeout-alpha-20261108`，环境阻断前）：source-state 记录 HEAD `2c0c0e9d…`、dirty、48 输入哈希（抽查 `components/mmwave_host/mmwave_host.cpp` 与实际文件一致）、`source-dirty.patch` 30KB。见 `evidence/real-run-source-state.json`、`real-run-source-dirty.patch`。
- 期间发现并修复一个真实缺陷：`capture_git_state` 对 porcelain 输出使用 `.strip()`，吞掉第一行状态列前导空格，导致首个脏文件路径错位漏记。由新增反例测试 `test_dirty_tree_captures_patch_and_scope` 抓出后改为 `.rstrip("\r\n")` 并支持 rename 行。

## T2：运行独立与历史输出保护（C3）

- `check_output_clean()` 在创建目录/写配置/子进程之前运行：输出根已包含任一既有运行产物（`artifact-summary.json`、`compiled.factory.yaml`、`source-state.json`、`compile.log`、`config-*.log`、`source-dirty.patch`）或候选固件目标已存在 → 拒绝启动，提示换新 `--output`；哨兵文件字节不变，删除调用次数 0（无 rmtree，沿用 R1）。
- `--run-id` 显式指定或默认 `run-YYYYMMDD-HHMMSS`，进入 source-state 与摘要，同版本多次构建用不同运行目录区分。
- 失败也落盘：新增 `BuildStageError(stage, exit_code)` 贯穿 `run/expect_failure/assert_text/assert_build/flash_fit`；失败时写 `artifact-summary.json`（`status: failed`、stage、exitCode、runId、version/channel），此前已产生的日志保留，不清理、不输出成功摘要。单测 `test_failed_compile_keeps_logs_and_writes_failed_summary` 覆盖。
- 盖章 include 改为按目标目录动态计算相对路径（跨盘回退为 `as_posix()` 绝对路径），bad-copy 同样处理；嵌套运行目录（`tmp/x/y/z`、`runs/2026-11-08/alpha/data`）经真实 `esphome config` 验证（非 mock）。
- 不做并发调度；一个运行一个目录。

## T3：可追溯新候选（C4/C5）——环境部分阻断

- 真实运行 `closeout-alpha-20261108`：`--version v0.1.0-alpha.2`、独立目录 `tmp/closeout/{data,out}-v010a2`（未触碰 `tmp/rehearsal-*`）。
- 完成部分：USB 检查通过、source-state/脏树 patch 落盘、盖章配置生成并通过真实 `esphome config`（退出 0；`version: "v0.1.0-alpha.2"`、`release_channel: alpha`、include `../../../tests/r60abd1-esp32c3.yaml` 从深目录正确解析）、三条配置检查日志落盘。
- 未完成部分：`esphome compile` 在 `write_cpp` 阶段失败——ESPHome 将 PIO 库解析为 IDF 组件时需查询 `api.registry.platformio.org`，HTTP 超时（DNS 正常；github 亦超时；2026-11-06 同一 venv/同一固定版本成功，说明是本次环境出口问题）。失败日志、失败摘要（stage=compile_command, exitCode=1）全部保留；未重试、未改 venv/依赖、未伪造。
- `source-state.json` 在编译失败时同样有效：C1/C2 的真实性由这次真实失败运行直接证明（见 `evidence/real-run-*.json`）。
- C5 打包/校验：新候选无产物 → **not_run**；`validate_bundle` 正/负例由发布工具 23/23 回归覆盖，另将 2026-11-06 存档 bundle 用当前工具重校验通过（`evidence/archive-bundle-revalidate.log`，`bundleSha256 fe3e7e77…aff5`），证明打包校验路径自上轮复核以来未变。旧 `rehearsal-*` 全部原样。

## T4：维护者交接（C6）

- `docs/FLASHER.md` / `FLASHER_CN.md` 新增「本地候选构建：运行目录与源码身份」一节：可复制命令（独立 data/output、--version、--run-id）、每次运行的产物清单及含义、失败/uncertain 的解读、脏树以 patch 文件为准、正式 Alpha 必须由维护者选定提交经 Publish 工作流构建、编译后提交不会改变固件内嵌 SHA。
- 运行索引见本目录 `evidence/index.md`；构建通过/真机通过/已发布三项始终分开表述。

## 冻结六项验收（C1～C6）

| ID | 验收行为 | 结果 | 证据/说明 |
| --- | --- | --- | --- |
| C1 | source-state 由真实入口构建前生成，身份不伪造 | **pass** | 真实失败运行产生完整 source-state（HEAD/状态/48 输入哈希/patch）；`.strip()` 漏记首行脏文件的真实缺陷由反例抓出并修复；Git 失败→unknown 有单测；输入中途变化→uncertain 有单测 |
| C2 | 输入与产物可关联 | **pass**（以真实运行+单测为准；完整链路待编译成功） | 摘要带 `sourceStateSha256`/`stampedConfigSha256`/`gitStatus`/runId；真实失败运行的三件套（source-state、patch、盖章配置）互相一致 |
| C3 | 不覆盖旧运行、不越界 | **pass** | 根级 8 类产物哨兵逐一拒绝且字节不变；既有候选目标拒绝（沿用 R1）；非法版本零副作用；`tmp/rehearsal-*` 原样 |
| C4 | 运行目录变化仍能配置/构建 | **部分 pass** | 深目录盖章配置经真实 `esphome config` 退出 0（合并配置、Alpha 身份、USB 独占、TX21/RX20 检查全过）；目标编译因注册表网络出口被阻断 **not completed**（非代码缺陷） |
| C5 | 新候选可被正式打包工具校验 | **not_run**（环境） | 无新产物可打包；打包/校验路径未变（23/23 回归 + 存档 bundle 当前工具重校验通过） |
| C6 | 交接材料清楚 | **pass** | 中英文档可复制命令；运行索引、限制、授权边界明确；无秘密/无关目录混入 |

## 命令与退出码

```text
python -m unittest discover -s tests -p test_build_r60_candidate.py -v   # 22 tests, OK, exit 0
python -m unittest discover -s tests -p test_releases.py -v              # 23 tests, OK, exit 0
python scripts/check_r60_usb_profile.py                                  # self-test ok / profile ok, exit 0
.esphome/candidate-venv/Scripts/python.exe -m esphome config tests/r60abd1-esp32c3.factory.yaml   # exit 0
.esphome/candidate-venv/Scripts/python.exe -m esphome config tests/r60abd1-esp32c3.yaml           # exit 0
.esphome/candidate-venv/Scripts/python.exe -m esphome config tests/ld2450-esp32c3.factory.yaml    # exit 0
python scripts/build_r60_candidate.py --python .esphome/candidate-venv/Scripts/python.exe \
  --data-dir tmp/closeout/data-v010a2 --output tmp/closeout/out-v010a2 \
  --version v0.1.0-alpha.2 --run-id closeout-alpha-20261108
  # -> 失败保留：artifact-summary.json status=failed stage=compile_command exitCode=1（网络）
```

前端/固件运行时未改：143 单元、6 浏览器及既有目标构建结论沿用，不重复。

## 限制与移交

- 目标编译的注册表访问在本环境被阻断；网络可用后在**新的**运行目录重跑同一条命令即可，工具无需再改。重试条件明确：具体环境恢复（出口可达），不是盲试。
- 正式 Alpha 发布构建必须来自维护者选定提交的干净树（Publish 工作流）；演练构建（脏树+patch）不是发布候选，文档已写明。
- 更丰富快照格式、并发矩阵、全部 ESPHome 依赖源码追溯：按包边界登记延期，不设新门禁。
- 本包未 commit/push/merge/tag/Release、未部署、未触碰串口/设备/生产 HA/cases。
