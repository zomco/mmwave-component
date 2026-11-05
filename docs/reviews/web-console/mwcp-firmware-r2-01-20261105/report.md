# R2-01 空响应假成功：离线修复

日期：2026-11-05。组件提交点 `f5470c95d1a2792f64412262af3b430ff47dbb5f`，工作树仍是脏的，本次未提交、未推送、未发布。

结论分开记录：

- 软件通过。安装器真正读入的每个固件 part，遇到 HTTP 失败、正文读失败或 0 字节时，在擦除和写入之前失败，并断开烧录传输。非空候选仍进入原来的 `writeFlash`，完成时的字节数等于文件长度。
- 短真机通过。本轮获得了对 COM9 的一次新授权：第一次烧录被空响应守卫拦下（未擦除、未写入），清掉 IDM 拦截后按授权做了一次明确重试，真机写入成功，身份行是 `r60abd1 · 2D · v0.0.0-local.20261105`，`install.x_cm` 试写 30→31 经一次真实重启后仍在，随后恢复为 30。
- 发布未批准。

11:51 的完成页不能说明候选已经写入。本轮也不把 IDM 断定为现场原因。固件源码没有改，没有重编。

## 修复位置

页面入口仍是 `esp-web-tools/dist/web/install-button.js`。真正下载固件的是它打包进去的 `install-dialog`，不是一份只给测试用的源码。

受控补丁在 `static/script/installer-download-guard-patches.json`，由 `static/script/apply-installer-download-guard.mjs` 应用到三处，并在擦除调用之前检查：

- `node_modules/esp-web-tools/src/flash.ts`
- `node_modules/esp-web-tools/dist/flash.js`
- `node_modules/esp-web-tools/dist/web/install-dialog-*.js`

每个 part 改为读取 `arrayBuffer()`。HTTP 非 2xx、读取抛错、或长度为 0，都抛出带路径的错误。已有的下载失败分支负责发出 error、复位并 `transport.disconnect()`，然后返回。part 列表为空导致总字节为 0 时，同样在 `eraseFlash` / `writeFlash` 之前返回。错误文案写明正文是空的或没有收到固件，并提示检查下载拦截后重试；它不说已经写入。

安装对话框原有的错误页把这条 message 显示出来，Back 回到仪表再安装就是一次明确重试。失败时烧录传输会断开；对话框原有逻辑在约 100 毫秒后重新打开同一个 Web Serial 端口，供这次重试使用。关闭对话框仍会关闭端口。本轮没有增加第二个 reader，也没有自动交接控制台。

`npm ci` 会把 `esp-web-tools` 恢复成锁文件里的未修补 10.4.0。补丁不在 `node_modules` 里。`npm run test:unit`、`npm run test:browser` 和 `npm run build` 都会先运行上述脚本；`vite.config.js` 和 `vite.app.config.js` 在 Vite 加载时也会再应用一次。生产构建若产物里没有这句空响应拒绝，会直接失败。锚点对不上时脚本抛错，不会静默沿用旧的假成功路径。

## 行为

串口传输和网络是离线替身。`writeFlash` 使用已安装的 esptool-js 0.6.1 方法，成功或失败由安装器自己的状态决定。候选是现有 factory 镜像，1580112 字节，只读，没有重编。

| 行为 | 结果 | 观察 |
| --- | --- | --- |
| HTTP 200 且正文 0 字节，不要求擦除 | pass | error，1 次下载，0 次擦除，0 次写入，传输断开 1 次，没有 finished |
| HTTP 200 且正文 0 字节，要求擦除 | pass | 同上，擦除发生在检查之前的路径没有被调用 |
| 构建没有任何 part，且要求擦除 | pass | 0 次下载，0 次擦除，0 次写入，提示没有收到固件 |
| HTTP 404，且要求擦除 | pass | error，0 次擦除，0 次写入 |
| 正文读取抛错 | pass | error，0 次擦除，0 次写入，文案含 body aborted |
| 上述失败之后一次明确重试，送入真实候选 | pass | finished，写入块数大于 0，完成字节数 1580112 |
| 直接送入真实候选 | pass | 只下载 1 次，0 次擦除，完成字节数 1580112，随后断开 |
| 生产对话框里的下载表达式 | pass | 空正文、404、读取失败被拒绝；4 字节正文被原样返回 |
| 生产构建产物 | pass | 空响应拒绝位于该产物中随后的 eraseFlash 和 writeFlash 之前 |
| COM9 短闭环 | pass | 第一次空响应被拒，未擦除未写入；重试真机写入成功，身份与配置试写全部符合预期，详见下文 |
| 发布 | 未批准 | 不由这次离线修复自动批准 |

## 命令

工作目录：`submodules/mmwave-component/static`。

| 命令 | 退出码 | 结果 |
| --- | --- | --- |
| `node --experimental-vm-modules --test --test-timeout=90000 test/installer-download-guard.test.js` | 0 | 5/5。这是修复后的直接反例和正常对照 |
| `node --experimental-vm-modules --test --test-timeout=60000 test/*.test.js` | 1 | 143 项中 141 通过、2 失败。失败是既有编译环境，不是这条烧录路径 |
| 仅重跑 `test/g0-hello.test.js` 与 `test/mwcp-production.test.js`，`MWCP_GPP=D:\msys64\clang64\bin\c++.exe` | 0 | 3/3。没有为此重跑其余 141 项 |
| `node --test --test-timeout=90000 test/browser/*.test.js` | 0 | 6/6。浏览器应用构建同样要求产物含空响应拒绝 |
| `node node_modules/vite/bin/vite.js build` | 0 | 生产构建完成。use-client 警告不是失败 |

第一次单元运行里，`g0-hello` 找到 `D:\msys64\clang64\bin\c++.exe`，但测试自己的 20 秒编译时限返回 ETIMEDOUT。`mwcp-production` 只自动查找 `g++`，当前 PATH 没有 `g++`。这两项与空固件补丁没有共同代码。设置 `MWCP_GPP` 后立即通过。

## 哈希

固件未重编。两份 factory 都是 1580112 字节，SHA-256 `f5a03d59a5472d25561a4c30c3f034cd726fa229b43d3eee2834fd2eb155c8ec`。OTA `a0d872319437bc18cee65b78212d22ba6438691dc534784f1d663d59d9fbf708`，1514576 字节。manifest `916028cbf8114d8b0235f7dc9179229ba5a687a87469e7d3c876eb9837487f80`，394 字节。

生产构建里的安装对话框：`static/dist/assets/install-dialog-im156JnI-BlHzWoG3.js`，309189 字节，SHA-256 `0e913cf8995c676e3398492e13ce1c8f63be2ba44de25ccc23a82e8c35f486d6`。空响应句子在偏移 302990，其后的 eraseFlash 在 303809，writeFlash 在 304009。

已安装依赖是 esp-web-tools 10.4.0。应用声明为 `^10.1.1`。

## 本轮修改

- `static/script/apply-installer-download-guard.mjs`
- `static/script/installer-download-guard-patches.json`
- `static/test/installer-download-guard.test.js`
- `static/package.json`
- `static/vite.config.js`
- `static/vite.app.config.js`

`node_modules` 里的三份文件由脚本改写，不作为版本真源。`static/src/App.jsx`、`catalog.js`、`content.js` 原本就是脏文件，本轮没有改它们。旧候选目录和 `attempt-1125` 原始证据没有覆盖。

## COM9 短闭环（2026-11-05 下午，授权一次）

固定站点是 `127.0.0.1:8767`（本目录 `serve.mjs`，生产构建产物），浏览器是独立用户目录的 Chrome，带 `--disable-extensions` 和 `--force-renderer-accessibility`。全程只碰 COM9，没碰 COM3，没连生产 HA。

1. 第一次安装（16:32），Erase 未勾选。守卫按预期拦截：对话框显示 `Downloading firmware r60abd1.factory.bin failed: the response was empty. Check a download blocker, then retry. Nothing was written.`，进度日志（`hw/progress.txt` 16:32:20）只有这一条 error，没有擦除、没有写入。同一时刻屏幕上出现 IDM 的「下载文件信息」抓取窗口（`hw/16-empty.png` 左下角），URL 就是本机 factory.bin 地址——IDM 把 fetch 的正文截走，浏览器侧只剩空响应。服务器本身没问题：PowerShell 直连同一 URL 返回 200、1580112 字节。第一次尝试不是一次写入，守卫阻止了假成功。
2. 按授权清理下载路径后重试一次：暂停 IDM 进程，同一干净用户目录重启 Chrome，页面内 `fetch` 实测拿到 200 和 1580112 字节。Erase 保持未勾选。
3. 重试安装（16:39:31–16:40:36）：进度出现百分比，约 65 秒后 `Installation complete!`（`hw/progress.txt`）。完成页照旧不作为写入证明。
4. 控制台验证：USB 调试连接 COM9，新握手身份行 `r60abd1 · 2D · v0.0.0-local.20261105`，芯片 串口 open / 协议 online / 雷达 healthy / 数据 valid / 配置 idle（`hw/33-identity.png`）。11:51 那种「完成页但身份还是 mwcp-host」的假成功没有复现——这次写入的是候选固件。
5. `install.x_cm` 试写：设备实读原值 30（revision 155）。用控制台会话里与「保存到设备」按钮相同的真实路径（`editDraft` + `commitDraft`，内部 validate → commit → 设备读回）写入 31，结果 `persisted_and_read_back`，revision 156（`hw/trial-write.json`）。
6. 一次正常重启，不写 flash：走固件自带协议动作 `ACTION_START device.restart`（op `4947bb52-e666-474b-aeea-f15a43062fdb`，job-1）。C3 软重启不断开 USB 枚举，协议会话按预期失效。用页面自己的「连接设备」重连 COM9，新握手 `boot_id` 从 `…a6632f914218d02a5d64` 变为 `…9144c2e839d05c2c203f`，身份行仍是 `v0.0.0-local.20261105`，`install.x_cm` 仍是 31（revision 156）——写入经受住了真实重启（`hw/reboot-verify.json`、`hw/37-after-reboot.png`）。
7. 恢复原值：31 → 30，`persisted_and_read_back`，revision 157（`hw/restore.json`）。断开连接，串口 closed。

| 步骤 | 结果 | 证据 |
| --- | --- | --- |
| 空响应守卫（真机） | pass | `hw/progress.txt`、`hw/16-empty.png`，0 擦除 0 写入 |
| 清理后一次重试写入 | pass | `hw/progress.txt` 16:39–16:40、`hw/21-complete.png` |
| 重启后身份行 | pass | `hw/33-identity.png`、`hw/37-after-reboot.png`、boot_id 变更 |
| `install.x_cm` 30→31 过重启 | pass | `hw/trial-write.json`、`hw/reboot-verify.json`（revision 155→156） |
| 恢复 30 | pass | `hw/restore.json`（revision 157） |

两次安装 Erase 都未勾选。NVS 仍没有备份，这一点不变。

### 现场另记（不属于 R2-01 判定）

配置页有一个 UI 缺陷：点过一次「重新读取设备」之后，安装位置表单的输入框会反复卸载，而会话、芯片（healthy/valid）和会话对象里的 draft 都完好（phase idle、19 项能力、8 项 configItems 都在）。「保存到设备」按钮背后的 `editDraft` + `commitDraft` 逻辑本身工作正常。为不扩大改动面，试写和恢复走的是这同一对会话方法（与按钮同一条真实写路径），而不是点按钮；结论不受影响，但按钮路径被这个渲染缺陷挡住，需要单独修。

## 仍未做

发布仍未批准：软件通过、短真机通过是必要条件，不是发布决定。配置页表单卸载缺陷需要单独修复并补 UI 级验证。固件源码没有改，没有重编，本轮只新增了本目录下的证据文件和驱动脚本；`attempt-1125` 和旧候选目录保持原样。
