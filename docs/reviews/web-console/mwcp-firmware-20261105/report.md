# R60ABD1 MWCP 固件离线集成报告

日期：2026-11-05。这是实现方自检，不是独立验收，也不是发布批准。没有打开串口，没有烧录，没有擦除，没有访问或修改 Home Assistant，没有提交、推送、创建 PR，也没有部署 Pages 或上传 GitHub Release。

## 结论

基本离线交付已经完成：标准 R60 日常配置和工厂配置现在启用 MWCP，并用未打补丁的 ESPHome 2026.9.1 编出了可追溯的本机候选。公开安装页的发布列表仍是空的。真机行为全部 not_run。

本机候选不是 Alpha、Beta 或已发布版本。页面只有在明确选择 local 并确认后才会使用它，而且不会把它当成默认项。

## 用户能看到什么

- R60ABD1 的日常源和工厂源启用 USB 调试控制台，不再同时占用串口 Improv。没连上家庭 Wi-Fi 时，配置里仍有备用热点和强制门户；蓝牙 Improv、HTTP OTA 和原有实体还在。
- 其他型号仍通过 tests/common/_standard_device.yaml 保留串口 Improv。
- 公开索引 static/public/releases.json 仍是 {"schemaVersion":1,"releases":[]}。打开现有安装页时，R60 仍显示没有已发布固件。
- 本机预览页会显示“本地候选、未发布”。它只存在于本机证据目录，不会被现有发布脚本接受。
- 未打补丁的这份固件不能扫描 Wi-Fi。页面和文档都按不可用说明，没有把扫描补丁编进去。

## 八项基本行为

| # | 行为 | 结果 | 证据 |
| --- | --- | --- | --- |
| 1 | 标准 R60 base/factory 启用 MWCP；原生 USB 不被 logger、IDF console 或串口 Improv 抢占；雷达 UART 不被日志占用 | pass | 见下方构建证据。这是配置和编译结果，不是示波器或串口观察 |
| 2 | 没有 HA 或尚未配网时，不因常规连接超时反复重启；配网、OTA 和原有 HA 实体保持可用 | not_run | 镜像里已经写入 api 与 wifi 的 reboot_timeout: 0s、备用热点、强制门户、BLE Improv 和 HTTP OTA。设备是否真的不重启，没有上电观察 |
| 3 | 固定依赖的目标构建成功；版本、源码差异、profile、manifest、factory/OTA 哈希对应；不用旧 host 镜像冒充 | pass | artifact-summary.json。编译目标是本机盖章后的工厂配置，不是三份 host profile |
| 4 | 真实网页安装器完成本机候选的一次烧录，关闭窗口并等待后，控制台手动连接成功 | not_run | 只在本机打开了预览页，没有连接硬件 |
| 5 | 不依赖 HA 收到少量新鲜、真实观测；unknown 仍是 unknown | not_run | 没有设备数据 |
| 6 | 读取配置，修改一个可逆字段，保存后读回；重启后再读，证明已保存 | not_run | 没有设备 |
| 7 | 恢复原字段；断开后页面显示历史或离线，并能再次手动连接 | not_run | 没有设备 |
| 8 | 材料明确区分 pass、fail、not_run、deferred；软件通过不写成真机通过 | pass | 本报告 |

wifi.scan 在未打补丁的 ESPHome 上是 UNSUPPORTED。这是已知非阻断项，不是失败。

## 构建身份

- 组件 HEAD：f5470c95d1a2792f64412262af3b430ff47dbb5f。工作树是脏的，这个 SHA 不覆盖未提交差异。
- 已跟踪差异 SHA-256：b49716b5b37d0e3e6b055677d5313ae7fc5f19aff424d0fea63a42d0f86a0411，41 个文件，+136/−81。这个哈希不含下面的新文件。
- 工作区 HEAD：de663e462118f7953ede9019b7738870f3ebb77d。
- ESPHome：2026.9.1，来自 submodules/mmwave-component/.esphome/candidate-venv。没有应用 patches/esphome-2026.9.1-wifi-scan-ownership.patch。
- 设备侧通道：development。页面侧通道：local。构建 profile：r60-daily。组件回退版本：dev。ESPHome 项目版本：v0.0.0-local.20261105。
- 运行时优先使用 ESPHOME_PROJECT_VERSION。MWCP_GIT_SHA 只记录 HEAD。
- 工厂源文件仍是 version: dev。盖章版本只写在 .esphome/candidate/r60abd1.factory.yaml 和本证据目录，不在 tests/ 里，因此现有 CI 不会把它当成一个新的发布版本。

新源文件 SHA-256：

| 文件 | SHA-256 |
| --- | --- |
| scripts/check_r60_usb_profile.py | 02a5a6bc0e3d301678492769b1ebded6c76b4c199018b8614106abd53afef311 |
| scripts/build_r60_candidate.py | b68c08c22c49eba5307c08b02d92045406f32edd9103871ab09e014a0a97e6a4 |
| scripts/assemble_local_preview.py | df06167073068d3ae864565120eb4a57771c963a5b93bf88bbf76a06ac5fa039 |
| tests/common/_improv_serial.yaml | eb05ecb3ef029cb6bc22ff9e318a118b118d59fffd59bcdd3a43d28fb99296e8 |
| tests/common/_standard_device.yaml | f413a599dbed4e1c98bf05373d0759b5ab726c548878fb9959c57ba855c6758f |

## 镜像证据

展开后的 R60 配置包含 mmwave_host，项目版本是 v0.0.0-local.20261105，firmware_version: dev，release_channel: development，build_profile: r60-daily。雷达 UART 是 GPIO21 TX / GPIO20 RX，115200 8N1。logger 是 baud_rate: 0、hardware_uart: UART0。api.reboot_timeout 和 wifi.reboot_timeout 都是 0s。配置里有备用热点、captive_portal、esp32_improv 和 HTTP OTA，没有 improv_serial。

sdkconfig.r60abd1 含有 CONFIG_ESP_CONSOLE_NONE=y 和 CONFIG_ESP_MAIN_TASK_STACK_SIZE=8192，并且 CONFIG_ESP_CONSOLE_USB_SERIAL_JTAG 未启用。

身份宏在 ESP-IDF 的 C++ 编译选项里，不在 defines.h：

- -DMWCP_BUILD_PROFILE="r60-daily"
- -DMWCP_RELEASE_CHANNEL="development"
- -DMWCP_FIRMWARE_VERSION="dev"
- -DMWCP_GIT_SHA="f5470c95d1a2792f64412262af3b430ff47dbb5f"

defines.h 含有 ESPHOME_PROJECT_VERSION "v0.0.0-local.20261105"。defines.h 和 CMake 选项都没有 MWCP_WIFI_SCAN_OWNERSHIP。源码里的扫描实现同时要求这个宏和补丁提供的监听器，所以这次未打补丁的构建不会获得扫描所有权。

分区占用：82.5%（1514210/1835008 bytes）。

| 产物 | 大小 | SHA-256 |
| --- | --- | --- |
| factory | 1580112 | f5a03d59a5472d25561a4c30c3f034cd726fa229b43d3eee2834fd2eb155c8ec |
| OTA | 1514576 | a0d872319437bc18cee65b78212d22ba6438691dc534784f1d663d59d9fbf708 |
| manifest | — | 916028cbf8114d8b0235f7dc9179229ba5a687a87469e7d3c876eb9837487f80 |

LD2450 工厂配置仍展开出 improv_serial，并且没有 mmwave_host。release_channel: nightly 被 ESPHome 拒绝，退出码 2。三份 host profile 只删去了重复的 web_server，没有改动其中的网络凭据，本报告也不抄录那些凭据。

## 命令和退出码

工作目录是 submodules/mmwave-component，除非另行注明。

| 命令 | 退出码 | 说明 |
| --- | --- | --- |
| python scripts/check_r60_usb_profile.py | 0 | self-test ok，r60 usb profile ok；构建脚本也会先跑它 |
| esphome config 非法通道样本 | 2 | 拒绝 nightly，日志 config-bad.log |
| esphome config 盖章后的 R60 工厂配置 | 0 | 日志 config-r60.log |
| esphome config tests/ld2450-esp32c3.factory.yaml | 0 | 日志 config-ld2450.log |
| esphome compile 盖章后的 R60 工厂配置 | 0 | 日志 compile.log。第一次收集脚本在编译完成后因去 defines.h 找 C++ 宏而退出 1；镜像当时已经生成。修正检查位置后的收集退出 0 |
| npm run test:unit，未设置 MWCP_GPP | 1 | 编译同时进行时为 136/138。已看到的失败是生产链路测试只查找 g++ |
| 设置 MWCP_GPP 为 clang++ 后 npm run test:unit | 0 | 138/138，约 25.4 秒。编译器是 D:\msys64\clang64\bin\clang++.exe |
| npm run build（static/） | 0 | 既有第三方 use client 警告，不是构建失败 |
| python scripts/assemble_local_preview.py | 0 | 预览目录已生成，公开索引仍为空 |
| 本机解析预览 releases.json | 0 | local 不被默认选中 |
| 本机请求预览页、releases.json 和 manifest | 200 | 页面含“本地候选、未发布” |

## 本机预览

预览目录：docs/reviews/web-console/mwcp-firmware-20261105/preview。2026-11-05 验证时由下面的命令提供：

python -m http.server 8766 --bind 127.0.0.1 --directory docs/reviews/web-console/mwcp-firmware-20261105/preview

打开 http://127.0.0.1:8766/ 。这是生产构建加上本机索引和横幅，不是 GitHub Pages。索引里的 sourceCommit 只是组件 HEAD；publishedAt 只是本机索引时间，不是发布日期。

## 模拟和真机

单元测试、配置展开、编译、哈希和本机页面检查都是软件证据。没有任何一项来自 ESP32 或雷达。预览页没有进入烧录，也没有出现系统串口授权框。

## 阻断和非阻断

阻断发布和真机承诺的事项：

- 行为 2 的“不会重启”以及行为 4 到 7 都是 not_run。没有指定并授权本次测试设备和允许的烧录、改配置、重启动作，因此没有提出新的硬件请求。
- 公开索引为空。现有 scripts/releases.py 只接受 alpha/beta，不能发布 local。这一点没有改。

不阻断离线交付的事项：

- Wi-Fi 扫描仍不可用，并已在页面和文档中说明。
- Git SHA 不代表脏工作树。差异哈希和新文件哈希写在本报告。
- 工厂源一旦被提交，以后的发布构建就会带上 MWCP 和 USB 独占。现在还没有提交，所以不会发生。

## 仍需维护者决定

1. 是否在真机授权后做 15 到 30 分钟短闭环。通过前不能把行为 2 和 4 到 7 改成 pass。
2. 是否提交这批源码。提交前应再核对无关脏文件，尤其是 docs/rd03/rd03-3D.step 和 docs/rd03d/rd03d-3D.step，它们不属于这次改动。
3. 是否将来把这个 USB 独占镜像发布为 alpha 或 beta。那是另一次发布，不是这次 local 候选。
4. 生产 HA 配置 esphome-config/r60abd1-esp32c3.yaml 仍走原来的标准设备包，没有被同步，也没有启用这份 MWCP 候选。

## 这次改过的源码

已跟踪：.github/copilot-instructions.md、.github/workflows/ci.yml、两份 GETTING-STARTED、components/mmwave_host/__init__.py、components/mmwave_host/mmwave_host.cpp、两份 FLASHER、两份 WEB_CONSOLE、两份协议 README、两份 R60 README、static/src/App.jsx、catalog.js、content.js、static/test/catalog.test.js、tests/common/_device.yaml、16 个型号核心、tests/common/r60abd1_mwcp.yaml、三份 host profile、两份 R60 YAML。

新增：两个共享设备包，以及检查、构建和本机预览三个脚本。

没有修改 static/public/releases.json、scripts/releases.py、生产 HA 配置、外壳、CAD、压力目录或临时目录。
