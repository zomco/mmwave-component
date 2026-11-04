# WP-5 离线交付报告

日期：2026-11-04（Asia/Shanghai）。这是实现方自检，不是独立验收，也不是发布批准。

组件 HEAD 7456131ff0c2bca0295a942a3851533fc9173385。工作区 HEAD d1c6debf528f09ccf08b9bc9829c42e4f93180a1（docs(console): define WP-5 core delivery plan and AI handoff），是 WP-4 验收提交 952dc8d9f8067f749549dba438bf0c33dfb645b0 的后继，本轮没有回滚。两处改动都还没提交。

结论：中英文 USB 调试说明、帮助入口、一组模拟的合法清单正向对照和候选说明已经写好。真机没有跑。仓库里的发布列表仍是空的，factory 配置仍不启用 MWCP。

## 修改了哪些文件

组件里本轮动过的文件：

| 文件 | 作用 |
| --- | --- |
| docs/WEB_CONSOLE_CN.md | 新增中文使用说明 |
| docs/WEB_CONSOLE.md | 新增英文使用说明，范围与中文相同 |
| README.md、README_CN.md | 文档表增加指南链接 |
| GETTING-STARTED.md、GETTING-STARTED_CN.md | 说明烧录普通页面不等于打开 USB 调试 |
| docs/FLASHER.md、docs/FLASHER_CN.md | 维护者说明：源码、编译、刷入、发布是四件事 |
| static/src/console/copy.js | 帮助链接；记录上限改成与实现一致 |
| static/src/console/ConsoleView.jsx | 控制台标题下增加指南链接 |
| static/app-browser-entry.jsx | 仅测试入口：重复 open 拒绝；可挡住授权 |
| static/test/browser/app-flash-ready.test.js | 合法 Beta 清单的正向对照和错误校验反例 |

工作区另外更新了 docs/plans/mmwave-web-console/current-status.md 和 wp5-core-plan.md 的执行状态。计划正文没有改写成已验收。

没有改 static/public/releases.json。它仍是 schemaVersion 1 且 releases 为空数组。没有改 factory YAML，没有改坐标变换，没有改 Completed。static/dist 被 static/.gitignore 忽略，是本地构建结果，不是刷入的镜像。

留下没动的脏文件：工作区的 cases/、ha-config/configuration.yaml、外壳复核、esphome-config/、review-bundles/、scratch/；组件里原有的 .esphome-stress/、docs/rd03/rd03-3D.step、docs/rd03d/rd03d-3D.step、tmp/、tmp-pip/。没有全量 git add，没有提交、推送、PR 或发布。

## 用户现在能做什么

在组件仓库里可以打开中文或英文说明，从 README、新手指南和烧录维护说明也能走到。页面控制台标题下的“USB 调试使用说明”指向仓库默认分支上的中文文件；在那份文件进入默认分支之前，这个线上链接还不存在。仓库内的相对链接现在就能打开。

说明覆盖的使用步骤是：桌面 Chrome 或 Edge，HTTPS 或 localhost，选对主控 USB 口，确认协议和设备报告的型号，看有效观测，做一次验证、保存和读回，再断开。Home Assistant 仍是后一步。

用户现在还不能从本仓库的发布列表下载 MWCP 固件。普通 factory 包包含 tests/r60abd1-esp32c3.yaml，那个文件包含 tests/common/r60abd1.yaml，组件只有 r60abd1。启用协议的是 tests/r60abd1-esp32c3-host.yaml：组件含 mmwave_host，雷达配置包含 tests/common/r60abd1_mwcp.yaml。源码里有协议、某个配置编译时启用、某块板子实际刷入、某个版本已经发布，仍是四件事。本轮没有刷入，也没有发布。

## 七项基本验收行为

| # | 行为 | 结果 | 证据 |
| --- | --- | --- | --- |
| 1 | 找得到说明，并知道要 MWCP 固件、桌面 Web Serial、HTTPS 或 localhost、正确的 USB 口 | pass | 两份指南的打开页面和操作步骤；README、新手指南、烧录说明里的链接；浏览器测试断言帮助链接为 GitHub 默认分支上的 docs/WEB_CONSOLE_CN.md |
| 2 | 说明成功、未知、过期、历史和不可用；端口在线、坐标 0、空目标不等于有人或无人，也不等于整条链路通过 | pass | 两份指南的五层状态和存在说明。页面原有文案没有改写这些含义。这是文档核对，不是新的真机观测 |
| 3 | 保存说明与实现一致：验证、提交、确认、读回；冲突先重读；未知不自动重提；断开不是取消 | pass | 文案来自 static/src/console/copy.js。模拟页在 390px 下改 X、保存，看到“已保存并读回”。冲突和未知本轮没有重跑，沿用 WP-3/WP-4 已复核的页面行为 |
| 4 | 写明关闭安装器、等待、手动重连；占用和关闭失败可以重试；不声称自动接管，也不声称真烧录已验证 | pass | 两份指南的交接和故障表。真实网页安装器和操作系统独占仍是 not_run，见 WP4-D2 |
| 5 | 一个带合法版本数据的实际 App 离线用例，证明按钮会启用也会禁用，而不是只看永远禁用的空列表 | pass | static/test/browser/app-flash-ready.test.js 两条都通过。合法 Beta 清单使“连接设备并烧录”可用且 manifest 正确；连接中、占用中、延迟释放中禁用；释放后同一清单恢复。错误 hash 保持禁用并出现校验失败文案。没有点击安装按钮，服务器对 bin 返回 404 |
| 6 | 生产构建没有测试注入；现有单元和浏览器回归通过 | pass | 单元 137/137，浏览器 6/6，构建退出码 0。static/dist 中没有 SimulatedDevice、__mwcp、node:crypto、app-browser-entry、beforeGrant。帮助链接出现在生产包里，那是页面文案，不是测试入口 |
| 7 | 候选说明能追溯到精确源码和实际命令，写明没做的事；不编版本号、下载地址、镜像哈希或真机通过 | pass | 同目录 candidate.md 与 commands.md |

上面的 pass 都是软件或文档结果。没有任何一项是真机 pass，也没有一项是发布批准。

## 命令、退出码和身份

工作目录都是 submodules/mmwave-component/static。先跑新增测试，通过后再跑整组，之后没有再改代码，所以没有重跑。明细在 commands.md。

| 命令 | 退出码 | 结果 |
| --- | --- | --- |
| node --test --test-timeout=120000 test/browser/app-flash-ready.test.js | 0 | 2 通过，0 失败。约 18.7 秒和 2.0 秒，合计约 20.9 秒 |
| 仅该进程把 D:/msys64/ucrt64/bin 加到 PATH 并设置 MWCP_GPP，然后 npm.cmd run test:unit；结束后恢复 PATH | 0 | 137 通过，0 失败，约 17.1 秒 |
| npm.cmd run test:browser | 0 | 6 通过，0 失败，约 13.3 秒。含原有 4 条和新增 2 条 |
| npm.cmd run build | 0 | Vite 8.3.4，约 1.04 秒。lucide-react 的 use client 警告是既有第三方提示，不是失败 |

单元日志在工具回传里只保留了尾部。上面的 137 和 0 来自那次运行末尾的完整汇总行，没有把缺失的前半段补写成绿色日志。

模拟和真机：

- 浏览器证据用的是无头 Chrome 打开测试页 app-browser.html。页上有“模拟页面。不是系统串口授权框，也不是真机通过。”测试结束时模拟标记为真。
- 替换的是串口、时钟和 HTTP 夹具。页面、协调器、会话和协议客户端是生产代码。
- 假端口在已经打开时再次 open 会以 InvalidStateError 拒绝，且 openCalls 仍是 1。这只说明测试替身会拒绝，不能证明操作系统独占。
- 本轮没有打开 COM3 或 COM9，没有烧录，没有访问或修改 Home Assistant，没有触发 GitHub Action。历史 COM9 记录不是这次的新覆盖。本地构建产物没有刷进任何板子，也没有镜像哈希。

## 阻断问题

没有。没有复现无法连接、无法读取、错误写入、未决写丢失、假成功、秘密泄露或真实串口竞争。

## 非阻断问题和触发条件

| 事项 | 现在怎样 | 何时再做 |
| --- | --- | --- | --- |
| 记录上限文案 | 原先写到顶自动停止且不覆盖。实现是继续记录并只留最近 600 条。文案已改成实话。停止记录仍会清空内存。不是阻断 | 若用户需要到 600 条就停止，或停止后仍能导出，再改行为并加对照 |
| 页面帮助链接 | 指向默认分支。文件还没进入该分支时链接打不开。仓库内相对链接可用 | 把文档合并到默认分支时核对一次 |
| WP4-D1 | 离线正向对照已完成。真烧录没有做 | 真烧录归 WP4-D2，不把这次模拟写成烧录通过 |
| WP4-D2 | 真实网页安装器交接和操作系统独占是 not_run。自动交接继续延期，因为安装窗口关闭不等于端口释放 | 维护者授权一个 15 到 30 分钟的短窗口，并指定设备、镜像哈希、可逆字段和恢复方法之后 |
| WP4-D3 | 本轮只在 390px 看了连接、断开、保存的尺寸和可用，并用一次真实 Tab 移动了焦点。不是全浏览器、全尺寸或完整无障碍 | 要声称多浏览器或完整无障碍覆盖时 |
| 可选 Wi-Fi 任务、HA 并发、BLE、耐久和压力、图形自动缩放 | 继续延期 | 相应能力要启用或要做可靠性发布时。能力不够就保持关闭或说明，不挡住这条离线主路径 |
| factory 未启用 MWCP | 已写明。不阻塞这份文档，但阻塞“普通用户刷公开镜像就能用 USB 调试”的承诺 | 维护者决定是否把 mmwave_host 放进发布用的 factory 配置并真正发布之前 |

## 基本交付和仍要维护者决定的事

WP-5 的离线基本交付已经具备：说明、入口、有限真实 App 正向对照、候选说明和这份证据都在。可以交给独立复核。实现方自检不是独立验收。

发布前维护者还要单独决定：

1. 是否接受这次未提交工作区，以及是否提交。本轮没有提交。
2. 发布用的 factory 要不要启用 MWCP。现在不启用。
3. 要不要发布一个版本。本轮没有版本号，没有下载地址，没有镜像哈希。
4. 要不要授权 WP4-D2 的短真机窗口。不授权就保持 not_run。
5. 回退时把页面和固件分开。步骤在 candidate.md，本轮没有执行。

若以后要做真机，建议先定：设备口、要刷的镜像及其哈希、一个可逆配置字段和原值、恢复方法，以及最多 15 到 30 分钟。本轮不需要为了交付文档去等这个窗口。
