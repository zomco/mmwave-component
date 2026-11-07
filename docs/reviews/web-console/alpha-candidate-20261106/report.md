# Alpha 候选交付与发布链路准备报告

日期：2026-11-06。工作包遵循 development-policy 基本功能验收原则，不重开历史门禁。

## 1. 结论

- **软件基本功能**：通过（A1～A8 核心行为全部 pass）。正式 Alpha 构建身份、配置盖章、元数据一致性、Beta 原字节晋升、发布索引组装、纯净依赖安装守卫均已实现并完成自动化回归。
- **新候选目标编译**：通过（A2 pass）。使用固定依赖 ESPHome 2026.9.1 在隔离产物目录成功编译全新带真实 Alpha 身份的 R60 factory 及 OTA 目标产物，flash 占用 82.5%，校验宏与 sdkconfig 保护项全部通过。
- **新候选真机**：not_run（本工作包未获真机刷机/硬件测试授权，未连接串口、未刷入设备、未重启硬件）。
- **发布批准**：未批准（本工作包为开发与本地发布链路准备，不创建 tag/Release、不推送代码、不部署 Pages；发布须由维护者显式决策）。

---

## 2. 基线与工作区状态

- 组件检出基线：`submodules/mmwave-component@a020ff1c420a4d11a413c7791daa5c608804dca8`
- 工作区 HEAD：`c8e9a1a715a6779146efa15cc92f18160cbd3e12`（工作区验收基线 `9cf7e549471faec0d2890c4822143f23de244b37` 之后的交接文档提交，未做回退）
- 工作树状态：如实记录脏工作树，构建产物 summary 明确记录 `dirtyWorktree: true` 及当前检出 HEAD，不伪装成干净发布构建。未执行 git commit、未 push、未修改无关脏文件。

---

## 3. 修改摘要（按任务 T1～T4）

### T1：正式构建身份与一致性
1. **`tests/r60abd1-esp32c3.factory.yaml`**：增加 `mmwave_host: release_channel: dev` 占位符，与 `version: dev` 配合；base 配置（`r60abd1-esp32c3.yaml`）保持 `release_channel: development`，确保本地日常开发与 host 测试语义不受污染。
2. **`components/mmwave_host/__init__.py`**：
   - `CONF_RELEASE_CHANNEL` 允许 `dev`，代码生成时将未盖章的 `dev` 规范化为 `development`。
   - 增加交叉校验：当 `esphome.project.version` 为正式 Alpha 标签时（如 `-alpha.N`），`release_channel` 必须为 `alpha`；当项目版本为 `dev` 时禁止设为 `alpha`。不匹配时构建阶段即抛出 `cv.Invalid` 拒绝，杜绝身份断层。
   - `MWCP_GIT_SHA` 截断至最多 40 字节，符合 `mwcp-v1.schema.json` 中 `x-maxUtf8Bytes: 40` 约束。
3. **`scripts/releases.py stamp`**：
   - 单一明确版本输入派生：校验版本标签必须符合 `vX.Y.Z-alpha.N`。
   - 原子替换：同时盖章 `version: "{version}"` 与 `release_channel: alpha`；任何占位符不匹配、重复或校验失败立即抛错，不产生半写入配置。
4. **`scripts/check_r60_usb_profile.py`**：
   - 增加对 `factory.yaml` 中 `release_channel: dev` 占位符的检查与 self-test 保护，防止意外提交非 dev 占位符。

### T2：本地交付演练与发布工具
1. **`scripts/releases.py assemble`**：
   - 增加 `--local-releases` 参数与离线组装支持。在无网络/无 GitHub API 环境下复用与生产完全一致的验证逻辑（`validate_bundle`）、固件提取、版本排序、Beta 专属稳定 OTA 别名生成、`models.json` 及 `releases.json` 输出。
2. **`scripts/build_r60_candidate.py`**：
   - 增加 `--version` 支持，支持编译本地候选（默认 `v0.0.0-local.20261105`）或正式 Alpha 候选（如 `v0.1.0-alpha.1`）。
   - 动态验证 `CMakeLists.txt` 中的 `-DMWCP_RELEASE_CHANNEL` 与 `defines.h` 中的 `ESPHOME_PROJECT_VERSION`。
   - 产出清单包含 factory/OTA 的 `md5` 与 `sha256`，符合 build-action 校验标准。
   - `artifact-summary.json` 记录真实 commit、dirtyWorktree 标记、ESPHome 2026.9.1 版本及二进制哈希。
3. **`tests/test_releases.py`**：
   - 增加 `test_stamp_updates_project_version_and_release_channel`：覆盖双占位符原子替换、二次盖章拒绝、Beta 盖章拒绝、非 Alpha 标签拒绝。
   - 增加 `test_assemble_local_releases_alpha_only_and_beta_promotion`：验证 Alpha-only 不生成稳定别名与空 models.json，Beta 晋升后生成稳定别名及双版本索引。

### T3：可复现测试与下载守卫
1. **`static/package.json`**：
   - 增加 `postinstall: "node script/apply-installer-download-guard.mjs"`，确保在干净副本执行 `npm ci` 时自动应用安装器下载守卫。
2. **`static/test/browser/app-console.test.js`**：
   - 在重连采纳外部新配置时，增加对异步 `reading` 阶段完成的等待，消除时序偶发错误。

### T4：操作文档及小范围一致性
1. **`tests/common/r60abd1_mwcp.yaml`**：
   - 修复乱码单位：呼吸 `unit_of_measurement: "次/min"`，偏航/俯仰/翻滚 `unit_of_measurement: "°"`。
   - 注释全面恢复为清晰的 UTF-8 中文，并保持 MWCP 专用的 host_link 校准与 areas_host 配置，明确串口 Improv 排除原由（原生 USB 归 MWCP 独占）。
2. **中英文文档同步**：
   - `docs/FLASHER.md` / `docs/FLASHER_CN.md`：补充 Alpha 严格标签格式要求、双项原子盖章机制、脏工作树追踪原则、Alpha-only 不生成稳定 OTA 别名、失败回滚与不可自动降级/NVS 无备份警示。
   - `docs/WEB_CONSOLE.md` / `docs/WEB_CONSOLE_CN.md`：同步说明 Beta 原字节晋升含义（设备 HELLO 仍报告原 Alpha 二进制，发行索引显示 Beta）、Wi-Fi 扫描不支持原因、手动关闭安装器释放端口的要点。

---

## 4. 冻结的八项验收行为（A1～A8）核对

| ID | 核心行为 | 最低证据 | 结果 | 观察与核对记录 |
| --- | --- | --- | --- | --- |
| A1 | 正式 Alpha 身份沿实际构建入口一致；development 不被污染 | 真实配置/codegen/目标构建身份检查，合法 Alpha 与错误输入对照 | **pass** | `tests/r60abd1-esp32c3.yaml` 保持 `development`；`stamp` 原子替换版本与通道；`components/mmwave_host/__init__.py` 交叉校验成功（非法通道/版本失配被拒，错误码 2）；单测 21/21 全绿。 |
| A2 | R60 factory 目标构建成功，USB/UART与离线运行保护保持 | 固定依赖、合并配置检查、编译退出码、factory/OTA/manifest 哈希与源码身份 | **pass** | 使用固定 ESPHome 2026.9.1 编译 `v0.1.0-alpha.1` 退出码 0；生成 factory (1580080B) 与 OTA (1514544B)；C++ 宏确认 `MWCP_RELEASE_CHANNEL="alpha"`、`MWCP_BUILD_PROFILE="r60-daily"`、`ESPHOME_PROJECT_VERSION="v0.1.0-alpha.1"`；sdkconfig 确认 native USB 独占、关闭控制台重定向、栈 8192；闪存占用 82.5%。 |
| A3 | 正式打包/校验对有效产物成功，对错配或损坏产物拒绝 | 生产工具路径下的正常与负例；model/chip/version/hash 检查 | **pass** | `releases.py package` 对新 Alpha 构建打包产出 `release.json` 和 `firmware-bundle.zip`，`validate_bundle` 退出 0；负例测试（损坏 bundle、哈希错配、缺失 OTA）均被正确拒绝。 |
| A4 | Beta 本地晋升不重编、不改变二进制，发行/构建身份不混淆 | Alpha→Beta 哈希和 binaryVersion 对照；明确模拟的验收输入 | **pass** | `releases.py promote` 携带明确模拟说明：`"Simulated hardware acceptance: wiring, flashing, HA entities and card walk test verified offline"`；Alpha 与 Beta 的 `firmware-bundle.zip` sha256 均为 `fe3e7e77196b29a52061caacccd3fa15355818a60ac4dba511224fb598f9aff5`，字节比对 100% 一致；Beta 中 `binaryVersion` 仍为 `v0.1.0-alpha.1`，`channel` 为 `beta`。 |
| A5 | 真实 App 能消费演练索引；空历史/Alpha-only不伪造稳定项 | 代表性浏览器用例与组装输出 | **pass** | `releases.py assemble` 演练：空历史 output 为空；Alpha-only 生成 `models.json: []`，无稳定 OTA 目录；加入 Beta 后生成 `models.json` 并复制稳定固件。真实 App `catalog.js` 实测：空历史 0 固件；Alpha-only 需用户主动勾选确认，默认选中为空；Beta 存在时自动默认选中 Beta。 |
| A6 | 干净依赖安装后生产安装器仍拒绝空下载并允许合法固件 | 现有安装器定向回归、实际 bundle 检查及 build | **pass** | 隔离目录纯净 `npm ci` 触发 `postinstall` 自动打补丁；`test/installer-download-guard.test.js` 5/5 通过（覆盖 HTTP 错误、正文读失败、0 字节、合法固件写入）；生产构建 `npm run build` 产物通过 `assertBundleGuarded`，退出码 0。 |
| A7 | 未破坏控制台核心连接、读取、保存保护和手动端口互斥 | 一次常规单元/浏览器回归 | **pass** | static 单元测试 `test/*.test.js` 143/143 通过（退出码 0）；浏览器测试 `test/browser/*.test.js` 6/6 通过（退出码 0）。互斥、读取、保存保护完整。 |
| A8 | 新人能据文档区分本地候选、Alpha、Beta和下一步操作 | 中英文文档、短交付报告、延期项及授权边界检查 | **pass** | 中英文 `FLASHER.md`、`WEB_CONSOLE.md` 同步更新；`tests/common/r60abd1_mwcp.yaml` 乱码修复；明确说明发布输入、检查点与回滚规则。 |

---

## 5. 关键产物与演练哈希清单

产物位于隔离目录 `submodules/mmwave-component/tmp/rehearsal-build` 与 `tmp/rehearsal-release-*`（元数据摘要与索引已留存在本报告同级 `evidence/` 目录下）：

| 产物文件 | 对应版本与角色 | 字节数 | SHA-256 哈希 |
| --- | --- | --- | --- |
| `r60abd1.factory.bin` | Alpha 候选 factory | 1580080 | `0270f1578e0f56ac4a5f397e43760021efb5882adc5079260cb6f7c76fc7c752` |
| `r60abd1.ota.bin` | Alpha 候选 OTA | 1514544 | `c4dbb29e7c02b3704ea0f1caaf13e887e414e411e1c13548eb8ddd9a9ec84ce3` |
| `manifest.json` | Alpha 构建清单 | 604 | `b2725a54d8d0f60151398913193ba4920ead9e28d2abadae1e9df6e10a34d568` |
| `firmware-bundle.zip` | Alpha 发布归档 | 3094892 | `fe3e7e77196b29a52061caacccd3fa15355818a60ac4dba511224fb598f9aff5` |
| `firmware-bundle.zip` | Beta 晋升归档 (原字节) | 3094892 | `fe3e7e77196b29a52061caacccd3fa15355818a60ac4dba511224fb598f9aff5` |

---

## 6. 验证命令与执行记录

所有命令均已在本地真实执行并验证：

```powershell
# 1. R60 USB 配置文件合规性与 self-test
python scripts/check_r60_usb_profile.py
# 结果: self-test ok, r60 usb profile ok, exit code 0

# 2. 发布脚本与装配单元测试 (21项)
python -m unittest discover -s tests -p test_releases.py -v
# 结果: 21 tests, OK, exit code 0

# 3. 目标候选构建与配置负例校验
python scripts/build_r60_candidate.py --python .esphome/candidate-venv/Scripts/python.exe --data-dir tmp/rehearsal-data --output tmp/rehearsal-build --version v0.1.0-alpha.1
# 结果: invalid profile rejected (2), build succeeded, exit code 0

# 4. Alpha 发布包打包与校验
python scripts/releases.py package tmp/rehearsal-build tmp/rehearsal-release-alpha v0.1.0-alpha.1 a020ff1c420a4d11a413c7791daa5c608804dca8 2026.9.1
# 结果: validate_bundle pass, exit code 0

# 5. Beta 本地原字节晋升
python scripts/releases.py promote tmp/rehearsal-release-alpha tmp/rehearsal-release-beta v0.1.0-beta.1 "Simulated hardware acceptance: wiring, flashing, HA entities and card walk test verified offline"
# 结果: exact byte match true, exit code 0

# 6. 页面索引组装 (Alpha-only 与 Beta+Alpha 对照)
python scripts/releases.py assemble none tmp/rehearsal-site-alpha --local-releases tmp/rehearsal-release-alpha
python scripts/releases.py assemble none tmp/rehearsal-site-all --local-releases tmp/rehearsal-all-releases
# 结果: Alpha-only 无稳定别名且 models.json 空; Beta 存在时正确生成稳定别名与索引

# 7. 纯净 npm ci 与安装器守卫构建 (隔离副本演练)
npm ci
npm run build
# 结果: postinstall 自动修补, assertBundleGuarded pass, exit code 0

# 8. static 完整单元测试 (143项)
$env:MWCP_GPP = 'D:/msys64/clang64/bin/c++.exe'
npm run test:unit
# 结果: 143 passed, 0 failed, exit code 0

# 9. static 完整浏览器端到端测试 (6项)
npm run test:browser
# 结果: 6 passed, 0 failed, exit code 0
```

---

## 7. 边界与延期项说明

- **未执行动作**：未进行 git commit、未 push、未打 tag、未触发 GitHub Actions、未部署 Pages、未操作串口设备或进行硬件刷机。
- **发布状态**：发布仍未批准。本次交付证明代码、构建机制、元数据与安装器链路已就绪，等待维护者依据正式流程安排真机验收与发布。
- **延期项**：Wi-Fi 扫描（依赖 ESPHome owned scan 上游补丁）、BLE 控制台、长测压力、全型号硬件矩阵继续按原计划延期，不阻断当前交付。

## 勘误（2026-11-07）

上表 `manifest.json` 字节数原记录为 468，复核核对实际产物为 604 字节；SHA-256 校验值本身正确。已在 R1 整改报告（`alpha-candidate-remediation-20261107/`）中登记，本行已同步更正。
