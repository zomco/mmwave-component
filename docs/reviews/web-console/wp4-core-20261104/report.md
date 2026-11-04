# WP-4 核心集成自检

日期：2026-11-04。这是实现方自检，不是独立验收，也不是发布批准。软件通过、真机完成、允许发布是三件不同的事。

组件仍停在 6ee1d4359c4725b692ecf0d7e41028297b063b3e，工作区仍停在 e7fde1451fd5f2b7601fc4ed93dcfad5c61fe8e8。本轮没有提交、推送、开 PR、烧录，也没有打开 COM3 或 COM9。

## English summary

The production page stays in hardware mode. A separate test page, marked as simulation, drives a fake serial port through the real App. Port ownership, one reversible save and read-back, clean adoption, a dirty reconnect conflict, zero-coordinate presence, and stale history all passed in software. Installer auto-handoff stays deferred because the public closed event does not prove the port was released. Hardware is not_run. This is an implementer self-check, not independent acceptance or release approval.

## 结果

| 项目 | 结果 | 说明 |
| --- | --- | --- |
| 生产页连接 | pass | 测试页走真实 App，模式为 hardware。页面标明模拟，不是系统授权框，也不是真机通过 |
| 端口协调 | pass | 取消、重叠连接、延迟关闭、关闭失败后重试、安装窗口占用都不抢端口 |
| 配置保存与读回 | pass | 只提交改过的键；模拟传输，不是真机 |
| 干净重连 | pass | 没有本地修改时采用设备上的新值 |
| 未保存修改遇到外部变更 | pass | 先断开再改设备；重连后保留草稿并要求重新读取 |
| 观测恢复 | pass | 坐标 0 仍是有人；断开后是历史且过期，不是无人 |
| DIY 指引 | pass | 选了 R60ABD1 与 ESP32-C3 Super Mini，并勾选接线。页面没有“烧录成功” |
| 窄屏与键盘 | pass | 只做了 390px 和一次焦点检查，不是穷尽矩阵 |
| 安装器自动交接 | deferred | 公开 closed 事件不能证明 port.close() 已经完成 |
| COM3 / COM9 真机 | not_run | 本轮没有授权，也没有打开或烧录 |
| 发布 | N/A | 自检不能代替发布批准 |

## 行为

生产 App.jsx、src/main.jsx 和 vite.config.js 不引用 SimulatedDevice、window.__mwcp 或 node:crypto。测试入口 app-browser-entry.jsx 在渲染前放上假的 navigator.serial，并标明模拟。node:crypto 别名只存在于测试用的 vite.app.config.js。

端口阶段按这个顺序判断：关闭失败、正在关闭、正在连接、安装窗口占用、安装窗口关闭但未确认释放、控制台占用、空闲。关闭失败、正在关闭、正在连接、安装窗口占用和控制台占用时，烧录按钮禁用。正在关闭、正在连接和安装窗口占用时，连接按钮禁用。关闭失败时断开按钮还在，不能把端口当成空闲。

安装窗口只通过页面上的 ewt-install-dialog 观察。窗口还在时不连接。它的 closed 事件不代表端口已释放。窗口从页面消失只记成未确认，不自动连接，也不宣布端口已空闲。控制台正占用、正在连接或正在关闭时，安装窗口不能抢走所有权。

保存规则没有改。未知的待确认保存保持原来的操作编号、基线和改动，重连后不自动重发。错误操作编号不能确认。普通读取失败不是保存成功。已经确认但读回失败，也不是完整成功。干净重连采用设备快照。有未保存修改时，断开后设备又被别处改过，重连显示冲突，草稿保留，必须先重新读取。

坐标 0 和空目标都不是“无人”。断开后的样本保持历史，并显示过期。

## 证据

目录：docs/reviews/web-console/wp4-core-20261104/。

- test-unit.log：npm run test:unit，137 通过，0 失败，12334.1556 ms。跑之前把 D:/msys64/ucrt64/bin 加进该次进程的 PATH，没有写进产品。
- 同一命令在写日志之前先跑过一次。会话作业 pwsh-8ce787eff2a74188 退出码 0，摘要也是 137 通过、0 失败、19148.5651 ms。那次完整 TAP 没有落到磁盘，所以才把第二次输出存档。两次都通过，不是用第二次把失败改成通过。
- test-browser.log：npm run test:browser，4 通过，0 失败。包含生产页用例。单测超时是 90000 ms，不是无限等待。
- build.log：npm run build 退出码 0，1.01 秒完成。lucide 的 use client 警告与以往相同，不是构建失败。
- 构建后的 static/dist 搜索 SimulatedDevice、__mwcp、node:crypto，0 处。

生产页用例检查了这些可见结果：身份 r60abd1；零坐标显示“报告有人”；install.x_cm 保存为 31 并读回，写入次数 1；干净重连后 Y 采用 88；把 X 改成 32 后断开，设备 Y 再改为 77，重连出现冲突，草稿仍是 X 32、Y 88，保存禁用；重新读取后 Y 为 77、X 回到 31；再把 X 改为 34 并保存，设备上是 X 34、Y 77，写入次数 2。延迟关闭时看到“正在释放端口”，松开后快速验证显示“历史样本”和“已过期”。关闭失败时断开按钮仍在，并显示端口仍被占用；重试后关闭次数增加 2。安装窗口出现时不新增选口；窗口消失后提示手动连接，不自动打开。取消选口不增加打开次数。

## 没有做的事

没有打开 COM3 或 COM9，没有烧录，没有把历史 COM9 记录算成新的覆盖。D-03 仍只是过去 CLI esphome upload 退出后的另一次连接。网页安装器到控制台的自动交接没有真机证据，软件上也不自动接管。

没有改坐标变换，没有改 session.js。无关的外壳、HA、压力目录、STEP 和临时目录都没有动。没有提交。
