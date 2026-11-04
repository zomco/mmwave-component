# WP-5 候选说明

这是给维护者看的草稿，不是发布说明，也没有版本号。

## 用户能用什么

已刷入兼容 MWCP 固件的 ESP32-C3，可以用桌面 Chrome 或 Edge，经主控 USB 查看观测、验证并保存一项配置、再断开。不需要 Home Assistant 或 Wi-Fi。第一次写明的组合是 R60ABD1 和原生 USB 的 ESP32-C3。其他目录项只是声明，不是都已验收。

## 明确没支持或没验证的

- 本仓库 static/public/releases.json 是空列表。这里没有 MWCP 固件下载。
- tests/r60abd1-esp32c3.factory.yaml 包含 tests/r60abd1-esp32c3.yaml，后者不启用 mmwave_host。
- 没有新的真机记录。COM3、COM9 都没打开。没有烧录，所以没有刷入镜像的哈希。
- 真实网页安装器交接、操作系统对串口的独占，都没验证。
- 全浏览器、全尺寸、完整无障碍、自动缩放、可选 Wi-Fi 任务扩展、HA 并发、BLE、耐久和压力，都不在这次。

## 源码和工作树

- 组件 HEAD：7456131ff0c2bca0295a942a3851533fc9173385。WP-4 已提交的内容在这里。
- 工作区 HEAD：d1c6debf528f09ccf08b9bc9829c42e4f93180a1。这是 WP-5 计划提交，不是本轮文档提交。
- 本轮差异是未提交的文档、帮助链接、记录文案、测试入口和 app-flash-ready.test.js。文件列表见 report.md。
- 本地 npm.cmd run build 生成了被忽略的 static/dist。那是构建产物，不是刷进板子的镜像。

## 依据的既有记录

- WP-4 独立复核：工作区 docs/plans/mmwave-web-console/wp4-core-review-2026-11-04.md，组件证据 docs/reviews/web-console/wp4-core-20261104/。
- WP-3 第三次独立复核：工作区 docs/plans/mmwave-web-console/wp3-core-review-2026-11-04-r3.md。
- 这些记录里的通过项本轮没有重做硬件长测。

## 软件、真机、发布

- 软件：文档和模拟回归通过。见 commands.md。
- 真机：not_run。
- 发布：未批准，也未执行。

## 回退草案

只写步骤，本轮没有部署，也没有回退。

页面和文档：把这次未提交的文档和前端文案从候选提交里拿掉，或在已经发布页面后改回上一份静态构建。不要覆盖不可变 tag，不要删除 docs/reviews/web-console/ 里的证据。文档回退不改变板子上的配置。

设备固件：与页面回退分开。本轮没有刷过镜像，没有可以回退的哈希，不要编一个。将来如果刷了 MWCP 镜像再要撤回，应重刷当时有记录的那一份镜像，并按那次记录恢复被改过的配置项。不要为了撤销一份说明去清空设备，也不要抹掉烧录日志。
