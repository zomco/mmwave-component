# WP-3 网页控制台核心交付

日期：2026-11-04。这是当前这一份结论，不改写 WP-2/G2 归档，也不把短测写成发布通过。

## 结论

网页控制台的基本软件功能已经在未提交工作区实现。指定测试设备是本机 COM9。同机的 COM3 也是 ESP32 USB 串口，没有打开、没有烧录、也没有在串口框里点选。

2026-11-04 独立复核之后，保存单次流程、读回确认和页面新鲜度（WP3-R1～R3）已在同一未提交树上修复。随后的配置状态 R2-A/B 也已修复：干净重连采用新配置，普通重读中断不算保存确认。两份自检分别见 docs/reviews/web-console/wp3-remediation-20261104/report.md 和 docs/reviews/web-console/wp3-remediation-20261104-r2/report.md。它们都不是独立复核通过。下面的 123/2 是整改前的命令记录。软件通过和 COM9 短测是两件事。本轮没有新的真机。

D-01、D-02、D-03 在 COM9 上做了短测。这不是发布通过，也不是两小时耐久、拔插、断电或全浏览器矩阵。

## English conclusion

The basic web-console software path is implemented in the uncommitted tree. The designated device is COM9 on this machine. COM3 is another ESP32 USB serial device on the same machine; it was not opened, flashed, or selected.

After the 2026-11-04 review, the single-flight save, read-back confirmation, and page freshness fixes (WP3-R1 through R3) are in the same uncommitted tree. The later configuration-state fixes (R2-A and R2-B) are there too. The implementer self-checks are docs/reviews/web-console/wp3-remediation-20261104/report.md and wp3-remediation-20261104-r2/report.md. Neither is an independent review. The 123/2 counts below predate those fixes. Software pass and the COM9 short run are separate. This round opened no serial port.

D-01, D-02, and D-03 had a short run on COM9. This is not release approval, and it is not the two-hour soak, unplug cycles, power cuts, or the full browser matrix.

## 版本

| 项 | 值 |
| --- | --- |
| 工作区 HEAD | `d37aaf3f4aaf67cbdcf5a924daef54228080eda8` |
| 组件 HEAD | `f5371156397e5c5605700c8a9d50f773278a81c5` |
| 提示词中的产品基线 | `mmwave-component@194524d` |
| `194524d..HEAD` 的 `static` 已提交差异 | 无 |
| 本次控制台改动 | 未提交的工作区改动 |

工作区里原有的 `cases/` 和 `ha-config/` 脏文件没有纳入这次交付。组件里原有的 `docs/rd03*`、`.esphome-stress/`、`tmp/` 也没有改。

## 改了什么

- `static/src/console/`：`session.js`、`pending-save.js`、`serial-coordinator.js`、`web-serial-transport.js`、`observe.js`、`copy.js`、`ConsoleView.jsx`
- `static/src/App.jsx`：`#console` 挂到现有页面；连接只从按钮进入；调试占用串口时烧录按钮不可用
- `static/src/content.js`：导航「USB 调试 / USB debug」，烧录后提示先做 USB 验证
- `static/test/console-core.test.js`：用真实 `ProtocolClient`、编解码器和内存传输驱动会话，不另写一套假状态
- 本报告和 `docs/reviews/web-console/wp3-core-evidence/`

协议字段、TTL、错误码和坐标旋转约定没有改。R60 能力页超过模拟器每秒 10 次的限制时，页面在两次请求之间等待并重试读取；提交这种不能重放的请求不自动重发。

## C1–C8

| 项 | 软件 | 硬件 |
| --- | --- | --- |
| C1 连接、身份、能力、取消和不支持 | 通过。安全上下文和 `navigator.serial` 分开判断；取消是 `chooser_cancelled`；无应答最多两次 HELLO，不复位循环 | COM9 上完成连接和身份。取消和不支持环境没有在这只设备上重测 |
| C2 串口独占、拔插、会话过期 | 通过。控制台与安装器互斥；一个 reader；过期后重新握手；`closed` 事件不等于端口已关闭 | COM9 断开后重连通过。没有做拔插。D-03 只是 CLI 上传退出后另一次 Web Serial 连接，不是网页安装器交接 |
| C3 未知、空目标、零坐标、过期 | 通过。有效存在样本显示「报告有人」或「报告无人」；未知仍是未知。坐标 0 或空目标不是无人 | COM9 上见到有效样本。烧录后的协议观测是有人；浏览器这一次是「报告无人」。都不是未知 |
| C4 1D 距离 | 通过，模拟器，页面会标出模拟来源。界外目标变淡但仍显示 | `not_run` |
| C5 校验、一次提交、读回、冲突 | 通过。校验失败不写；成功只写一次并读回；冲突保留草稿 | COM9 上 `install.x_cm` 从 30 改为 31，保存并读回，再恢复为 30。冲突路径没有在设备上重测 |
| C6 结果不明、`found:false`、坏帧、另一台设备 | 通过。丢失应答保持 unknown 且不自动重发；`found:false` 不能当成没执行；坏帧不确认；另一台设备不能清掉未完成保存 | `not_run` |
| C7 诊断与秘密 | 通过。导出打码；诊断页不把口令放进 DOM；没有 Wi-Fi 能力时不提供配网 | `not_run` |
| C8 外观 | 代表性通过，不是全矩阵。中英文、深浅色、约 390px、焦点落在「连接设备」、200% 缩放后 `#console` 仍在 | 不适用 |

真实页面没有模拟横幅，也没有假装系统已经弹出授权框或烧录成功。层状态仍显示 `closed`、`offline` 这类内部词，留作后续文案，不挡住使用。

## 命令

都在 `submodules/mmwave-component/static`。单元测试当次把 `D:\msys64\ucrt64\bin` 加进 PATH，并设置 `MWCP_GPP`，没有写进产品。

| 命令 | 退出码 | 结果 |
| --- | --- | --- |
| `node --test --test-timeout=20000 test/console-core.test.js` | 0 | 16 通过 |
| `npm run test:unit` | 0 | 123 通过，0 失败 |
| `npm run test:browser` | 0 | 2 通过 |
| `npm run build` | 0 | 成功。lucide 的 `use client` 警告是既有第三方提示，不是失败 |

浏览器证据用本机 Chrome 打开构建后的 `static/dist`，地址是 `http://127.0.0.1/` 上的 `#console`。截图和 DOM 记录在 `wp3-core-evidence/`。DOM 记录见 `dom-check.json`：安全上下文为真，`navigator.serial` 存在，连接按钮可用，页面文本不含模拟标记。

## 边界和未做的事

交付当时没有再列出挡住 C1–C8 的软件缺陷。随后的复核证明保存和新鲜度仍有 R1–R3；这两项的修复和自检另见整改报告，不要把本节原命令表当成那三项已经通过。

D-01、D-02、D-03 已在 COM9 上做完短测，见下面的硬件记录。没有做的是耐久、拔插、断电和全浏览器矩阵。

明确不做或推迟：两小时耐久、50 次拔插、20 次断电、全浏览器矩阵、BLE、3D、多雷达、通用终端、任意 UART 命令。没有改外壳、融合、桌面端，也没有新增雷达型号或改 Completed 状态。

## 硬件短测（只使用 COM9）

COM9 是 `USB 串行设备`，实例 `USB\\VID_303A&PID_1001&MI_00\\7&25E8ECF4&2&0000`。烧录用的是 `tests/r60abd1-esp32c3-host.yaml`，命令是 `esphome upload --device COM9`，不是 `esphome run`。工具退出后端口已放开。这是命令行上传，不是网页安装器交接；网页安装器交接没有验证。

烧录后的协议身份：`device_id` `dcda0cf8f274`，`git_sha` `f5371156397e5c5605700c8a9d50f773278a81c5`，型号 `r60abd1`，维度 `2D`，固件名 `mwcp-host`。12 帧遥测的存在样本都是 `quality: valid`、`value: true`。这是设备报告的值，不是人员标定。记录在 `hardware/d01-d02-20261103-233124.json`。

浏览器使用已构建的 `static/dist`。Chrome 从「连接设备」打开系统串口框，框里同时列出 COM3 和 COM9，只点击了 COM9。页面显示串口 open、协议 online、雷达 healthy、数据 valid，身份 `r60abd1 · 2D · mwcp-host`。断开后再次只选 COM9，结果相同。存在项这一次是「报告无人」（`absent · valid`），按设备当时的样本显示。`install.x_cm` 原值 30，试写 31 并读回，然后恢复为 30。记录在 `hardware/d02-webserial.json`、`d02-browser.png`、`d02-reconnected.png`。串口框截图 `d02-chooser.png` 是同机同一次枚举的画面，用来说明两只口都出现过；真正的点选记录在 JSON 的 `CLICK_COM9`。

页面身份卡不显示 `device_id` 和 `git_sha`。这两个值来自同一只 COM9 的协议身份，不把它们说成页面上的文字。

## 结束

当时的页面主路径和 COM9 短测已经做完，但不能称为可以发布。R1–R3 的修复自检是后来补上的，仍不是独立复核通过。D-03 不是网页安装器交接。

---

# WP-3 web console core delivery

Date: 2026-11-04. This is the one current conclusion. It does not rewrite the WP-2/G2 archives and it does not turn this short hardware run into release approval.

## Version

| Item | Value |
| --- | --- |
| Workspace HEAD | `d37aaf3f4aaf67cbdcf5a924daef54228080eda8` |
| Component HEAD | `f5371156397e5c5605700c8a9d50f773278a81c5` |
| Cited product baseline | `mmwave-component@194524d` |
| Committed `static` diff from `194524d` to HEAD | none |
| This console work | uncommitted working tree |

Pre-existing dirty `cases/` and `ha-config/` files in the workspace are not part of this delivery. Pre-existing component dirt under `docs/rd03*`, `.esphome-stress/`, and `tmp/` was not changed.

## What changed

- `static/src/console/`: session, pending save, serial coordinator, Web Serial transport, observation helpers, copy, and `ConsoleView.jsx`
- `static/src/App.jsx`: `#console` on the existing page; connect starts only from the button; flash stays disabled while debug holds the port
- `static/src/content.js`: “USB 调试 / USB debug”, and the after-flash hint to verify over USB first
- `static/test/console-core.test.js`: the real `ProtocolClient`, codec, and an in-memory byte transport drive the session
- this report and `docs/reviews/web-console/wp3-core-evidence/`

Protocol fields, TTL, error codes, and the coordinate rotation convention were not changed. When R60 capability paging exceeds the simulator’s 10 requests per second, the page waits between reads and retries them. A commit is not retried, because that request must not be replayed.

## C1–C8

| Item | Software | Hardware |
| --- | --- | --- |
| C1 connect, identity, cancel, unsupported | Pass. Secure context and `navigator.serial` are separate. Cancel is `chooser_cancelled`. No response stops after at most two HELLO frames | Connect and identity passed on COM9. Cancel and unsupported were not retested on the device |
| C2 exclusive port, unplug, session expiry | Pass. Console and installer are exclusive. One reader. Expiry starts a new handshake. A `closed` event is not a finished `port.close()` | Disconnect and reconnect passed on COM9. No unplug cycles. D-03 is only a later Web Serial connect after the CLI upload exited, not a web-installer handoff |
| C3 unknown, empty, zero, stale | Pass. A valid presence sample shows present or absent. Unknown stays unknown. Coordinate 0 or an empty list is not absence | COM9 reported valid samples. The post-flash protocol observation was present. The browser session showed absent. Neither was unknown |
| C4 1D range | Pass on the simulator, and the simulation origin stays marked. Out-of-boundary targets stay visible | `not_run` |
| C5 validate, one commit, readback, conflict | Pass. A failed validate does not write. Success writes once and reads back. A conflict keeps the draft | On COM9, `install.x_cm` went 30 → 31, was read back, then restored to 30. Conflict was not retested on the device |
| C6 unknown result, `found:false`, bad frames, other device | Pass. A lost reply stays unknown and is not resent. `found:false` is not “not executed”. A bad frame does not confirm. Another device cannot clear the pending save | `not_run` |
| C7 diagnostics and secrets | Pass. Export redacts secrets. The diagnostic view does not put a password in the DOM. Wi-Fi provisioning appears only when a capability id starts with `wifi` | `not_run` |
| C8 appearance | Representative pass, not a full matrix. Chinese and English, light and dark, about 390px, focus on Connect, and `#console` still present at 200% zoom | n/a |

The real page shows no simulation banner and does not imitate an operating-system permission dialog or a successful flash. Layer chips still show internal words such as `closed` and `offline`. That is deferred copy, not a blocked path.

## Commands

All commands ran in `submodules/mmwave-component/static`. The unit run prefixed PATH with `D:\msys64\ucrt64\bin` and set `MWCP_GPP` for that process only.

| Command | Exit | Result |
| --- | --- | --- |
| `node --test --test-timeout=20000 test/console-core.test.js` | 0 | 16 passed |
| `npm run test:unit` | 0 | 123 passed, 0 failed |
| `npm run test:browser` | 0 | 2 passed |
| `npm run build` | 0 | Success. The existing lucide `use client` warning is not a failure |

Chrome opened the built `static/dist` at `#console` on `http://127.0.0.1`. Screenshots and `dom-check.json` are in `wp3-core-evidence/`. That DOM record shows a secure context, `navigator.serial` present, an enabled connect button, and no simulation marker in the page text.

## Limits

No known software defect still blocks the C1–C8 path.

D-01, D-02, and D-03 had a short run on COM9. See the hardware record below. The soak, unplug cycles, power cuts, and full browser matrix were not run.

Deferred on purpose: the two-hour soak, 50 unplug cycles, 20 power cuts, the full browser matrix, BLE, 3D, multi-radar fusion, a generic terminal, and arbitrary UART commands. Cases, fusion, and the desktop app were not changed. No model was added and Completed status was not changed.

## Hardware short run (COM9 only)

COM9 is `USB 串行设备`, instance `USB\\VID_303A&PID_1001&MI_00\\7&25E8ECF4&2&0000`. The image came from `tests/r60abd1-esp32c3-host.yaml` via `esphome upload --device COM9`, not `esphome run`. The uploader exited and released the port. That was the command-line upload, not a web-installer handoff; the web installer handoff was not verified.

Protocol identity after the flash: `device_id` `dcda0cf8f274`, `git_sha` `f5371156397e5c5605700c8a9d50f773278a81c5`, model `r60abd1`, dimension `2D`, firmware name `mwcp-host`. All 12 telemetry frames reported presence `quality: valid`, `value: true`. That is the device's reported value, not a person calibration. Record: `hardware/d01-d02-20261103-233124.json`.

The browser served the built `static/dist`. Chrome opened the system serial chooser from the page button. The chooser listed both COM3 and COM9; only COM9 was clicked. The page showed port open, protocol online, radar healthy, data valid, and identity `r60abd1 · 2D · mwcp-host`. After disconnect, COM9 was selected again and the same result appeared. Presence on that visit was 「报告无人」 (`absent · valid`), shown as the device's sample at that time. `install.x_cm` started at 30, was saved as 31 and read back, then restored to 30. Records: `hardware/d02-webserial.json`, `d02-browser.png`, `d02-reconnected.png`. `d02-chooser.png` shows the same machine listing both ports; the click record for the successful session is `CLICK_COM9` in the JSON.

The page identity card does not show `device_id` or `git_sha`. Those values come from the protocol identity of the same COM9, not from text on the card.

## End

The page path and the COM9 short run were done, and this is not release-ready. The R1-R3 fix was self-checked later and is still not an independent review. D-03 is not a web-installer handoff.
