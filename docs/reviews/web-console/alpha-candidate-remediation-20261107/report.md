# Alpha 候选交付 R1 小范围整改报告（实现方整改，待复核）

日期：2026-11-07。组件基线 `a020ff1c420a4d11a413c7791daa5c608804dca8` + 上一轮未提交的 Alpha 交付修改。本轮只关闭复核报告中的唯一阻断 R1，并顺手处理 D1/D2/D3 中可小改的部分。不发布、不刷机、不提交。

## 1. R1：触发与修复

### 触发（来自独立复核 input-probe.py，本轮未执行任何危险删除）

- `scripts/build_r60_candidate.py --version` 无格式校验：`v0.1.0-beta.1`、`v0.1.0-alpha.bad`、`../outside` 均被接受。
- `stamp` 用 `"-alpha." in version` 子串判断通道：Beta 被标成 development，畸形 Alpha 被标成 alpha。
- main 把 version 直接拼进产物路径并对已存在目录 `shutil.rmtree`：`../outside` 可越出 `output/firmware`，且会静默删除既有候选。

### 修复（全部真实代码路径，未另写一套判断）

1. **共享校验**：`scripts/releases.py` 新增 `candidate_channel(version)`——复用正式发布入口的 `channel()` 严格 Alpha 正则，另定义本地受限格式 `LOCAL_CANDIDATE_VERSION = v0.0.0-local.\d{8}`（既有 `v0.0.0-local.20261105` 原样保留）。非字符串、Beta、畸形、斜杠/反斜杠、绝对路径、父目录引用、换行等一律 `ValueError`。候选构建永不产生 Beta；Beta 只能由 `promote()` 晋升已测 Alpha 字节。
2. **builder 复用同一规则**：`build_r60_candidate.py` 通过 `importlib` 加载同一份 `releases.py`（无第二套身份规则）。`stamp()` 先调 `candidate_channel` 再读写；`main()` 在 `parse_args` 之后、USB 检查子进程/mkdir/写配置之前先校验 `--version`，非法值直接 `SystemExit`。
3. **stamp 通道替换改为计数断言**：`re.subn(..., count=1)` 且 `channel_count != 1` 即报错，不再可能静默漏替换。
4. **产物路径解析后包含关系检查**：新增 `resolve_candidate_target(output, version)`——`target.resolve()` 后用 `Path.is_relative_to(firmware_root)` 判定（非字符串 startswith），已存在目录或符号链接一律拒绝；`shutil.rmtree` 从 builder 中完全移除。既有候选输出不被覆盖、不被删除，要求换新 `--output` 目录。检查位置在 mkdir 数据/输出目录之后、盖章与任何编译子进程之前（fail-fast，不浪费编译；`mkdir` 无 `exist_ok` 作为 TOCTOU 兜底）。
5. **语义保持**：正常 Alpha 的 version/channel/profile 与本地 development 的 `v0.0.0-local.YYYYMMDD`、`release_channel: development`、`build_profile: r60-daily` 全部不变；base 配置未改成 alpha；`bad_copy`/`expect_failure` 的 esphome 负例路径保留。

### 合法/非法对照（真实代码运行，I/O 以观测替身替换构建与删除）

| 输入 | 之前 | 现在 | 证据 |
| --- | --- | --- | --- |
| `v0.1.0-alpha.1` | 接受（alpha） | 接受（alpha），产物在 firmware 根内 | `evidence/input-probe-after.log` 第 1 行 `ACCEPTED alpha inside firmware: True`；单测 full-build 用例产物全部落在 `output/firmware/` 内 |
| `v0.0.0-local.20261105`（默认） | 接受（development） | 接受（development），语义不变 | 单测 `test_default_version_is_the_local_candidate` |
| `v0.1.0-beta.1` | 接受且误标 development | **拒绝**，未创建目录/文件、未启动任何子进程 | 单测 `test_invalid_version_runs_nothing_and_creates_nothing`；probe 第 2 行 |
| `v0.1.0-alpha.bad` | 接受且误标 alpha | **拒绝** | 同上；probe 第 4 行 |
| `../outside` / `..\outside` / `/absolute` / `C:\abs` / 换行 / 分号 | 接受，可越出产物根 | **拒绝**，`stamp` 不写任何字节 | 单测 `test_invalid_version_writes_nothing_and_keeps_existing_bytes`（ORIGINAL 字节不变）、`SharedCandidateChannelTests` |
| 目标目录已存在 | **rmtree 后重建** | **拒绝**：退出码 1，提示换新 `--output`；哨兵文件字节不变；删除调用次数 0 | 单测 `test_existing_target_is_refused_and_not_overwritten` |
| `firmware/<version>` 为指向根外的符号链接 | 跟随链接可越出 | **拒绝**：`resolve()` + `is_relative_to` 包含关系判定 | 单测 `test_symlink_escape_is_refused`（真实 symlink） |
| builder 删除调用 | `shutil.rmtree(target)` | 从源码移除；测试中以观测替身断言 **删除调用次数恒为 0** | 各 MainTests 用例 `self.assertEqual(self.deletions, [])` |

## 2. D1～D3 处理

- **D1（已修）**：`releases.py stamp` 备用分支删除 `f'\1...'`（U+0001）写法。既有 host 缺少或携带非 dev/development 通道（如 beta）→ 明确 `ValueError` 拒绝，文件保持原字节；无 mmwave_host 的 factory 只盖项目版本，不再无条件发明 host 块。R60 dev 占位符正常路径不变。对照：`test_stamp_rejects_host_without_a_dev_channel_placeholder`（3 种拒绝、字节不变）、`test_stamp_leaves_factories_without_mmwave_host_alone`，以及复核 probe 的 `no-host`（只盖版本）、`host-no-channel`/`wrong-channel`（拒绝且 unchanged: True）。
- **D2（已修）**：`alpha-candidate-20261106/report.md` 的 manifest 字节数 468 更正为 604（重新核对原始产物：604 字节，SHA-256 `b2725a54…568` 本来就正确），并在该报告末尾追加勘误说明；`current-status.md` 中两处交付报告链接 `../../submodules/...` 更正为 `../../../submodules/...`（已验证链接可达）。
- **D3（部分已修 + 如实缺口）**：本轮四个工具源文件的 diff（`evidence/source-diff-r1.patch`，23465 字节）与 SHA-256 索引（`evidence/source-files-r1.sha256`）、HEAD/脏树状态（`evidence/worktree-state.txt`）已保存。**如实缺口**：2026-11-06 演练构建时 `dirtyWorktree=true` 但当时未保存时点 diff/哈希索引，事后无法从当前已变化的工作树重建该历史身份，不做伪造；该缺口登记延期——触发条件为维护者执行正式 Alpha 发布或下一次目标重编之前，由发布/构建流程自动生成并归档 `source-state`（HEAD + 脏文件清单/哈希）。身份规则漂移本身已由 R1 关闭：builder 与正式发布入口共用同一 `candidate_channel`/`channel` 校验。

## 3. 验证命令与退出码（均在组件根目录执行）

```text
python -m unittest discover -s tests -p test_build_r60_candidate.py -v   # 新增定向反例 + 正常对照
  -> Ran 11 tests, OK, exit 0                                            # evidence/test-build-r60-candidate.log
python -m unittest discover -s tests -p test_releases.py -v              # 发布工具回归（含 D1 新对照）
  -> Ran 23 tests, OK, exit 0                                            # evidence/test-releases.log
python scripts/check_r60_usb_profile.py
  -> self-test ok / r60 usb profile ok, exit 0                           # evidence/check-r60-usb-profile.log
python docs/plans/mmwave-web-console/alpha-review-20261107/input-probe.py
  -> 合法 Alpha/local 接受，Beta/畸形/路径值 REJECTED ValueError；
     no-host 只盖版本；host-no-channel/wrong-channel 拒绝且 unchanged: True, exit 0
                                                                         # evidence/input-probe-after.log
.esphome/candidate-venv/Scripts/python.exe -m esphome config tests/r60abd1-esp32c3.factory.yaml
  -> Configuration is valid!, exit 0（合并后 release_channel: dev 占位符原样）
.esphome/candidate-venv/Scripts/python.exe -m esphome config tests/r60abd1-esp32c3.yaml
  -> Configuration is valid!, exit 0（base 仍为 development，未被污染）
```

按复核边界，本轮未改动前端/运行时与最终合法配置内容（仅工具层校验与文档），143 项单元、6 项浏览器与既有目标构建结论继续沿用；未重编目标、未 npm ci、未触碰硬件。

## 4. 行为变化说明（一处，有意）

`--skip-compile` 现在同样要求产物目标目录不存在（目标检查统一前移到 mkdir 之后）。此前 skip-compile 不检查目标；新语义与「候选输出只追加、不覆盖」一致，用于纯配置复检时应使用新的 `--output` 目录。

## 5. 边界

- 未执行 git commit/push/merge/tag/Release，未触发任何工作流，未部署 Pages。
- 未操作串口、未刷机、未重启设备、未写设备配置；未改 cases/CAD/生产 HA。
- 新日志全部在本报告同级 `evidence/`；未覆盖复核方的任何原始记录（其 `input-probe.log` 原样保留，本方重跑另存为 `input-probe-after.log`）。

## 6. 可复制复核命令（在 `submodules/mmwave-component` 下）

```bash
# R1 反例与正常对照（构建/删除 I/O 为观测替身，无编译无删除）
python -m unittest discover -s tests -p test_build_r60_candidate.py -v
# 发布工具回归（含 D1 对照）
python -m unittest discover -s tests -p test_releases.py -v
# USB 配置检查
python scripts/check_r60_usb_profile.py
# 复核方探针重跑（只写临时目录，不编译不删除）
python ../..-relative-path 到工作区的 docs/plans/mmwave-web-console/alpha-review-20261107/input-probe.py
# 合并配置对照（合法内容未变）
.esphome/candidate-venv/Scripts/python.exe -m esphome config tests/r60abd1-esp32c3.factory.yaml
```
