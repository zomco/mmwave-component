# 本候选短测第一次人工尝试（2026-11-05 11:25）

这不是通过，也不是发布批准。没有改固件，没有重编，没有提交，没有把原 not_run 报告改成通过。

审核先读文末「11:51 烧录的闭合记录」。11:25 的三张图和 11:51 的安装完成页是两次记录，不能合成一次通过。

## 结论

维护者指定了 COM9，并说明未勾选 Erase device、安装成功、断开后显示离线、重连成功、过程中没有意外重启、结束时配置已恢复。三张截图只能证明：串口框里选中了 COM9，随后控制台连上的固件身份是 `r60abd1 · 2D · mwcp-host`。

页面第三段是设备上报的 `firmware_version`。当前候选只有在没有 `ESPHOME_PROJECT_VERSION` 时才会落到 `mwcp-host`；这份候选的构建把项目版本定为 `v0.0.0-local.20261105`。因此截图中的设备不是本候选。网页交接不能记 pass。

这三张 11:25 截图没有安装完成画面，没有通道或 profile，也没有 `install.x_cm` 的原值、试写、重启读回和恢复读回。实时数据画面把目标和存在标成“已过期”，不能当作新鲜观测。同页后来的一次真实烧录见文末：安装器出现了 `Installation complete!`，但重连后身份仍是 `mwcp-host`，因此停在身份失败，没有继续试写。

## 截图

| 文件 | SHA-256 | 可见内容 |
| --- | --- | --- |
| serial-chooser.png | `b65531775b76ee3077853e276aaf6b3361e5d7df2cf7827edba3855ffe92668e` | `127.0.0.1:8766` 请求串口。列出 COM3 和 COM9，选中 COM9 且显示已配对。这是连接框，不是安装成功页 |
| live.png | `6bbc38af8c4ce69f3493b0336b05bed884ea89ff427a48f8246ea93d41377cbc` | 串口 open，协议 online，雷达 stale，数据 stale，配置 idle。身份 `mwcp-host`。存在“已过期”。坐标 20, 45 cm，sample 172715，边界外，仍显示。生命体征多项为未知 |
| quick.png | `be08c386fd3ef2013759bbe2bef6e6666ff6b02da640db99737ad98242050db6` | 顶栏雷达 healthy、数据 valid，身份仍是 `mwcp-host`。快速项里 USB 协议和配置可读为通过，雷达通信和存在为已过期。页脚：已过期 · 有目标 · seq 360 |

截图本身没有时钟。记录时间取维护者提交消息的 2026-11-05 11:25（北京时间）。

## 维护者陈述与截图的差别

可以记录为维护者陈述、但截图没有核对到的内容：安装成功提示、断开后的离线画面、再次连接、没有意外重启、配置已恢复。陈述没有给出 `install.x_cm` 数值。这些不能补成行为 6 或 7 的 pass。

## 行为

| # | 结果 | 依据 |
| --- | --- | --- |
| 1、3 | pass | 仍是离线构建结论，本轮未重编 |
| 2 | 配置 pass / 上电 not_run | 没有本候选在无 HA 条件下的运行观察 |
| 4 | fail | 连上的是 `mwcp-host`，不是 `v0.0.0-local.20261105`。不能把旧 host 固件算作本候选网页交接 |
| 5 | not_run | 画面中的样本标明已过期，不是新鲜观测 |
| 6、7 | not_run | 没有可核对的试写、重启读回和恢复数值 |
| 8 | pass | 陈述和截图分开记录 |

COM3 出现在选择框里，没有被选中，也没有打开。没有代码整改：运行身份说明板上仍不是本候选，不是已证实的保存或协议故障。

## 随后的烧录页（准备阶段）

installer-before-connect.png，SHA-256 `efebd3c5e705022de874e50ef9496324d87c61c4e6fe442102d9f4b9352840f7`。页面已选中 `v0.0.0-local.20261105`，本地候选确认框已勾选，但当时系统串口框仍开着，主按钮是“取消”。这只说明准备烧录本候选。

## 11:51 烧录的闭合记录

这是同一次授权里、11:25 截图之后的另一次网页安装。浏览器是 Google Chrome，窗口标题为「mmWave Radar · 在线安装」；Chrome 版本号没有记。地址是 `http://127.0.0.1:8766/`，控制台是 `/#console`。设备只使用维护者指定的 COM9（USB JTAG/serial debug unit，已配对）。COM3 出现在选择框里，没有点中，也没有打开。没有重编，没有第二次烧录，没有写配置，没有正常重启测试，没有接入 HA 或 Wi-Fi，没有发布。

时间来自操作记录，不在截图像素里：11:51:37 点下确认页的 Install；约 18 秒后出现下载框；12:06 前断开，随后本机可以打开再关掉 COM9。

### 三者分开

| 身份 | 记录 |
| --- | --- |
| 源码基线 | 组件 HEAD 仍是 `f5470c95d1a2792f64412262af3b430ff47dbb5f`，工作区 HEAD 仍是 `de663e462118f7953ede9019b7738870f3ebb77d`。组件 `git status --short` 有 53 条，本轮没有提交，也没有把差异清单复制进报告 |
| 候选构建 | 未重编。证据目录和 `preview/` 里的 factory、OTA、manifest 哈希仍是 `f5a03d59a5472d25561a4c30c3f034cd726fa229b43d3eee2834fd2eb155c8ec`、`a0d872319437bc18cee65b78212d22ba6438691dc534784f1d663d59d9fbf708`、`916028cbf8114d8b0235f7dc9179229ba5a687a87469e7d3c876eb9837487f80`。factory 1580112 字节，其中字符串 `v0.0.0-local.20261105` 出现 4 次，`r60-daily` 和 `development` 各 1 次，`mwcp-host` 为 0 次 |
| 设备运行身份 | 烧录完成页之后，COM9 控制台显示 `r60abd1 · 2D · mwcp-host`。第三段是 hello 的 `firmware_version`。运行中的通道和 profile 没有出现在这个身份行里，本轮没有另记 |

页面上的候选名和安装完成页不能代替第三列。也没有读回闪存，所以不能写成“已写入的字节等于上面的 factory 哈希”。

### 实际顺序

1. 页面已选 `v0.0.0-local.20261105`，本地候选确认框已勾选。
2. 安装器里 Erase device 为空，点 Next。确认页文字是 `R60ABD1 local candidate v0.0.0-local.20261105`，点 Install。
3. 先看到 Installing / Preparing installation。随后 Internet Download Manager 盖住页面，要把 `r60abd1.factory.bin` 另存到 `D:\Download`。点了取消，又在“是否修复 Chrome 集成”上点了否，没有点开始下载。
4. 这两个框关掉后，安装器页面是 `Installation complete!`。点 Next 回到仪表，再点关闭。关闭后 COM9 能被本机打开并立刻关掉。
5. 打开 USB 调试，只选 COM9 并连接。身份行是 `r60abd1 · 2D · mwcp-host`；串口 open、协议 online，稍后雷达 healthy、数据 valid。没有记下 presence 的 quality、数值或样本时间。
6. 点断开。页面变为 closed / offline。COM9 再次能打开并关掉。

`mmwave_host.cpp` 在定义了 `ESPHOME_PROJECT_VERSION` 时把 `firmware_version` 设成它；候选构建会检查 `defines.h` 含 `#define ESPHOME_PROJECT_VERSION "v0.0.0-local.20261105"`。`mwcp-host` 只在该宏和 `MWCP_FIRMWARE_VERSION` 都没有时使用。因此这块板当时跑的不是本候选。安装完成页记失败，不记 pass。

### 这次烧录的行为

| # | 结果 | 依据 |
| --- | --- | --- |
| 1、3 | pass | 仍用原离线构建和原哈希，本轮未重编 |
| 2 | 配置 pass / 上电 not_run | 没有本候选在无 HA 条件下的运行观察 |
| 4 | fail | 安装器出现完成页，但交接后的 `firmware_version` 是 `mwcp-host` |
| 5 | not_run | healthy / valid 只是状态芯片。没有带时间的新鲜样本，也不是本候选的观测 |
| 6、7 | not_run | 身份已失败，没有读 `install.x_cm`，没有试写、重启读回或恢复读回 |
| 8 | pass | 11:25 材料、这次烧录和原 not_run 报告分开 |

软件离线复核的通过结论不变。短真机未通过。发布未批准。

### 设备最后状态

控制台已断开，最后身份仍是 `mwcp-host`。没有写过配置，所以不存在“已恢复原值”；也没有读过原值，不能声称未勾选擦除就保住了旧配置。分区覆盖风险仍以父报告为准，这次没有新的配置快照。

### 失败的影响和未证实的可能

用户按页面完成安装后，USB 控制台仍连上旧的默认固件身份。没有观察到保存错误、秘密泄漏或端口死锁；断开后端口可以再打开。不能把完成页当成身份通过。

没有证明 Internet Download Manager 截走了烧录用的下载。它只是同时出现的环境干扰：完成页可见，但没有安装器下载日志或闪存读回。后续若再授权，应先区分“字节没写上”和“写上后仍报旧身份”，再做配置试写。本包不追加第二次烧录。

低优先级仍是原复核的 MFI-D1～D3。本机下载工具拦截工厂包 URL 只记在这台电脑的这次操作里，没有证成安装器代码缺陷。

### 这次烧录的截图

同目录其余 PNG 只是过程画面或裁剪，不另作结论。

| 文件 | SHA-256 | 可见内容 |
| --- | --- | --- |
| erase-or-next.png | `6bc7f59d296d648fc917e1b88fb01647190cb8d341009e93ab6292d3db3761eb` | Erase device 未勾选，旁边是 Back 和 Next |
| after-next.png | `7ab9baf83bc9abd972c005ab0289bbe871aa1cdbee0e494df42fd2e5e7a5f7df` | Confirm Installation，版本 `v0.0.0-local.20261105` |
| flash-start.png | `a368aba5b6eec2b37f7f66cf1af14650629e08e92d72c5983d3b33dcdd2d9b29` | Installing / Preparing installation，2026-11-05 11:51:37 |
| crop-done.png | `35b04141f20647563e7a7b47558bf0daf4d9a6ab171fe06315c707870eb14150` | `Installation complete!` 和 Next |
| com9-selected.png | `2c44a3929f644e2cd868ea15d6eb8008405a3eababba458be7e2c3f16cecf912` | 串口框里 COM9 高亮，COM3 未选 |
| back-console.png | `faa4c19c09a4d406a11a5e7a8f3bf6e72f59d366106ccfb5e115968254bc6f0b` | open / online / healthy / valid，身份仍是 `r60abd1 · 2D · mwcp-host` |
| after-disconnect.png | `090b9c7ccd363de8592c4563767dfa03e518a76af74704294f9c245331f21156` | 断开后 closed / offline，身份行仍留着 `mwcp-host` |
