# WP-3 基本功能整改自检（R1–R3）

日期：2026-11-04。这是实现方的整改和自检，不是独立复核通过，也不是发布通过。没有提交，没有推送，没有烧录，没有打开 COM3 或 COM9。

## 结论

WP3-R1、WP3-R2、WP3-R3 已在组件 f537115 的未提交工作区里改完，并用真实 ProtocolClient、编解码器和内存字节传输做了回归。自检没有发现还会挡住「一次保存、读回确认、过期数据不再报当前有效」这三项的软件问题。

这不能代替独立复核。上一轮 COM9 短测仍然有效，但那次短测没有覆盖这三个缺陷，本轮也没有再跑真机。软件用例通过不等于硬件覆盖扩大。

## English

This is the implementer's remediation self-check, not an independent review and not release approval. R1-R3 are fixed in the uncommitted tree and covered by regressions on a simulated byte transport. No port was opened and nothing was flashed. The earlier COM9 short run is unchanged and does not by itself prove these three fixes.

## 版本

| 项 | 值 |
| --- | --- |
| 工作区 HEAD | d37aaf3f4aaf67cbdcf5a924daef54228080eda8 |
| 组件 HEAD | f5371156397e5c5605700c8a9d50f773278a81c5 |
| 提示词里的产品基线 | mmwave-component@194524d |
| 工作区引用提交 | 7717179 仍是历史引用，没有改写 |
| 本次改动 | 未提交 |

git diff --stat 只看得到已跟踪文件：static/src/App.jsx、static/src/content.js、static/src/protocol/client.js（53 行新增，6 行删除）。static/src/console/ 整目录仍是未跟踪文件，所以保存锁、读回和新鲜度的改动不会出现在这份 diff stat 里。

没有改 cases/、ha-config/、协议字段、TTL、错误码、坐标约定，也没有改雷达型号状态。原有 probes.log 和复核脚本没有改。组件里原有的 .esphome-stress/、docs/rd03*、tmp/ 没有动。

## 三项分别怎么改的

R1：配置校验、提交和读回共用一个同步流程锁。未决保存还在时，放弃、重读、再校验或再保存都不会清掉原来的 op_id 和改动，也不会发第二次写。断开之后迟到的确认帧不能把新会话写成已保存。

R2：客户端在同一次等待里忽略 op_id 对不上的 CONFIG_COMMIT 成功帧，所以后面的合法帧还能确认。只有错误帧时保持 unknown，而且设备没有被那个假确认写到。读回失败或分页修订不一致时不显示「已保存并读回」，也不自动再写。真正读到另一份值时，草稿改成这次读到的设备值，并标成读回不一致。

R3：页面和检查项共用会话时钟。连接还在但样本超过 8000ms，存在和目标都是过期，雷达层不再保持 healthy。断开或会话过期后，旧样本不能显示成当前有人。新样本到来后可以恢复。过期目标不再标成 valid。重新握手复用已经打开的传输，不调用 requestPort()。

## 自检命令

目录：submodules/mmwave-component/static。当次进程把 D:\msys64\ucrt64\bin 放在 PATH 前面，并设置 MWCP_GPP。这条路径没有写进产品。

| 命令 | 退出码 | 结果 |
| --- | --- | --- |
| node --test --test-timeout=60000 --test-name-pattern C/R test/console-core.test.js | 0 | 22 通过，0 失败。其中 R1 三例、R2 两例、R3 一例，原有 C1–C7 仍在 |
| npm run test:browser | 0 | 3 通过，0 失败 |
| npm run build | 0 | 成功，约 2.33s。lucide 的 use client 警告是既有第三方提示，不是失败 |
| npm run test:unit | 0 | 129 通过，0 失败 |

129 = 整改前记录的 123，加上本轮 6 个 R 回归。浏览器 3 = 原有 2 个协议用例，加上本轮会点击配置按钮的页面用例。更早的 123 和 2 没有覆盖 R1–R3，不能再当成这三项的证据。

## 模拟和真机

浏览器用例构建的是测试页，挂的是 ConsoleView、ConsoleSession 和 SimulatedDevice。node:crypto 只在这个测试构建里换成同步 SHA-256，产品构建没有这个替换。页面会显示「模拟模式」。用例点击「配置」「在设备上验证」「保存到设备」，看到「已保存并读回」；再喂一个坐标 0 的模拟样本，快速验证和实时数据都看到「报告有人」；时钟前进 9001ms 后两处都变成「已过期」，而且过期行不再出现 valid；新样本又回到「报告有人」。

这个用例没有打开系统串口框，没有声称烧录成功，也没有访问 COM3 或 COM9。上一轮 COM9 的 30 到 31 再回到 30 的短测没有重做。D-03 仍然只证明 CLI esphome upload 退出、端口放开，然后另一次 Web Serial 连上。网页安装器交接没有验证。

## 仍延期

| ID | 状态 |
| --- | --- |
| WP3-D1 | 安装器与控制台的所有者还没有完整串起来。本轮没有改安装器，也没有新的双读证据 |
| WP3-D2 | 文档已写明 D-03 不是网页安装器交接。没有再烧录 |
| WP3-D3 | 停止记录会清缓冲。未改 |
| WP3-D4 | 固定正负 400cm 视图。未改 |
| WP3-D5 | 新鲜目标行仍可能显示英文 valid。完整视觉、键盘、可选 Wi-Fi 和任务未做 |
| WP3-D6 | 两小时耐久、50 次拔插、20 次断电、BLE、完整 HA 并发。未做 |

WP-2/G2 保持关闭，没有重开。

## 交给维护者

R1–R3 的软件基本功能已经有对应回归，自检命令都是退出码 0。本轮没有留下新的、会挡住错误保存、丢失未决写入或把过期样本报成当前数据的问题。可以交给另一次独立复核；下一阶段可以继续。不要把这份自检写成复核通过或发布通过。
