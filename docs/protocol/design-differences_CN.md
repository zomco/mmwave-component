# MWCP/1 设计差异与 G1 契约处置台账 (`DD-01` ～ `DD-15`)

- **文档状态**：**G1 整改候选，待独立复核**（`DD-01`～`DD-15` 已收口，含用户已批准并落地的 `DD-07` C2 与 `DD-08` C2，以及 G1-R1～G1-R5 验收整改）
- **更新日期**：2026-10-19
- **英文镜像**：[docs/protocol/design-differences.md](./design-differences.md)
- **G0 硬件实测证据索引**：[docs/reviews/web-console/g0-evidence-index.json](../reviews/web-console/g0-evidence-index.json)
- **规范正文**：[docs/protocol/README_CN.md](./README_CN.md)

---

## 1. 分类准则与本轮清理说明

本台账基于已完成的 **G0 真机验证**（LuatOS ESP32C3-CORE `USB\VID_303A&PID_1001` + R60ABD1 `GPIO21 TX / GPIO20 RX`，包含 2 小时 `7,198` 样本脱机长测）与 **WP-1 双端契约实现**，对 `DD-01`～`DD-15` 逐项完成处置分类：

- **台账清理记录**：
  1. 已移除旧版中重复的 `DD-13` 条目，合并为唯一权威 `DD-13` 记录；
  2. 已移除旧版末尾过时的“G0 硬件仍是 `not_run` / 本机没有 ESPHome”陈述，全部替换为真实 G0 硬件编译、烧写与 2 小时长测证据；
  3. 已修正全部源码/测试路径引用，与仓库真实结构保持 100% 一致。
- **三类处置定义**：
  - **A 类（规范已明确，代码/契约已一致，作为已解决项收口）**：`DD-06`、`DD-09`、`DD-10`、`DD-11`、`DD-13`、`DD-14`、`DD-15`（共 7 项）。两端代码、Schema、黄金向量与测试已完全锁定，不存在线格式或语义分歧。
  - **B 类（G0 已提供实测证据，给出明确工程契约与阶段边界）**：`DD-01`、`DD-02`、`DD-03`、`DD-04`、`DD-05`、`DD-12`（共 6 项）。G0 真机与源码审计已消除未知风险，已转化为 WP-2 / WP-3 的强制实现契约。
  - **C 类（涉及既有行为或参数范围调整，已由用户明确拍板并完成三端落地）**：`DD-07`、`DD-08`（共 2 项）。已在第 3 节记录选项对比、G0 真机证据、用户最终拍板结论及已同步修改的文件与回归断言。

---

## 2. `DD-01` ～ `DD-15` 完整处置矩阵

| ID | 原问题 | 当前证据（G0 真机 + 代码/Schema 审计） | 类别 | 处理结论或选项建议 | 影响范围 | 对应测试 | 责任阶段 | 评审状态 |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **DD-01** | `esp-web-tools` 安装器触发 `closed` 事件是否等于底层串口已释放 | 1. 源码审计：`esp-web-tools@10.4.0` 的 `connect.ts` 在 `closed` 回调中调用 `port.close()` 但未 `await`；`install-dialog.ts` 在安装后重开串口尝试 Improv（除非 `new_install_improv_wait_time: 0`）。<br>2. G0-U2 严格端口生命周期改造：`static/src/g0/diag.js` 实现了按单次打开生命周期代际（epoch）跟踪关闭 Promise、超时后迟到完成回收、同一 `port` 对象重复 `open/close` 状态重置。<br>3. G0-04 真机验证：Chrome `155` 在 `COM9` 上完成连接→握手→在线采样→断开→立即重连闭环。 | **B 类** | **明确契约**：<br>1. 严禁把安装器 `closed` 事件当作端口已释放；必须由控制台自身调用 `await port.open()` 成功作为唯一交接判据（`static/src/protocol/flash-handoff.js`）。<br>2. 发布给控制台使用的 manifest 设置 `new_install_improv_wait_time: 0`。<br>3. WP-3/G3/G4 必须在真机上补齐安装器 UI 5 分支（安装成功、失败、取消、关弹窗、中途拔线）端到端测试。 | `static/src/g0/diag.js`、`static/src/protocol/flash-handoff.js`、WP-3 串口管理器 | `static/test/g0-diag.test.js`、`static/test/flash-handoff.test.js`、`static/test/browser/protocol-browser.test.js`、真机 `G0-04` | WP-1（已完成诊断页闭环）→ WP-3 / G3 / G4（安装器 5 分支） | **B 类方案已收口（待独立复核）** |
| **DD-02** | ESPHome 与 ESP-IDF 构建版本未在仓库工作流中固定，无法钉死底层 USB 驱动结论 | 1. 工作流现状：`.github/workflows/publish.yml` 默认允许动态版本。<br>2. G0 真机实测已精确记录工具链与框架基线：`ESPHome 2026.9.1`、`ESP-IDF 5.5.5`、`riscv32-esp-elf-gcc 14.2.0`、板卡 `esp32-c3-devkitm-1`（LuatOS ESP32C3-CORE `USB\VID_303A&PID_1001&REV_0101&MI_00`）。<br>3. 编译产物 SHA-256 已固化于 `g0-evidence-index.json`（Host OTA: `DF0DA728...4026`，Host factory: `72C87C3D...6DD6`，Baseline OTA: `7E0B7077...D1B8`，Baseline factory: `EDD24371...B21D`）。 | **B 类** | **明确契约**：<br>1. 将 `ESPHome 2026.9.1 + ESP-IDF 5.5.5` 作为 G0/G1 验证参考基线写入阶段报告与证据索引。<br>2. 不在本阶段擅自修改 CI 发布工作流；后续每次硬件回归必须在报告中记录精确 `esphome` 与 `esp_idf` 版本，并在 `DEVICE_INFO (0x0010)` 中导出。 | `docs/reviews/web-console/g0-evidence-index.json`、WP-2 `DEVICE_INFO` 实现 | 真机 `G0-01`～`G0-05`、`static/test/protocol-schema.test.js` (`DEVICE_INFO`) | WP-1（证据已固化）→ WP-2 | **B 类方案已收口（待独立复核）** |
| **DD-03** | 同一 `USB_SERIAL_JTAG` 端口存在 `logger`、`improv_serial` 与 MWCP 多消费者冲突，且无 Wi-Fi/HA 时可能因 `reboot_timeout` 重启 | 1. G0 真机验证（`docs/reviews/web-console/g0/host.yaml`）：禁用 `improv_serial`、`CONFIG_ESP_CONSOLE_NONE: y`、`logger: hardware_uart: UART0, baud_rate: 0`、`wifi.reboot_timeout: 0s`、`api.reboot_timeout: 0s`。<br>2. G0-03 2 小时脱机长测（`7,198` 样本）：`boot_id` 全程保持 `dcda0cf8f2741d72537c31049c579aea`，`0` 次意外重启，`0` 次 CRC/帧错误。<br>3. G0 实测同时证实：若主机停止读取 USB CDC IN URB，阻塞式写 `USB_SERIAL_JTAG` 会填满 64B 硬件 FIFO 并阻塞 `loop()`。 | **B 类** | **明确契约**：<br>1. 启用 MWCP 的 host profile 必须独占 USB 串口（移除 stock `improv_serial`、`logger` 设 `baud_rate: 0`、`reboot_timeout: 0s`）。<br>2. WP-2 生产 `HostLink` 发送必须采用 64B 分块非阻塞写入（`timeout = 0`，连续零写 `250 ms` 放弃并标记重同步），超时丢弃低优先级事件并递增 `tx_overflow`，严禁阻塞雷达 `loop()`。 | `docs/reviews/web-console/g0/host.yaml`、WP-2 `HostLink` 与 `LogService` | 真机 `G0-01`、`G0-02`、`G0-03`、`protocol/cpp/g0_session_test.cpp` | WP-1（G0 已验证）→ WP-2（生产 `HostLink`） | **B 类方案已收口（待独立复核）** |
| **DD-04** | 现有固件 `g_polygon` 使用 `max_restore_data_length: 254` 字符串存储，最多仅能存 21 个点，装不下协议规定的 64 顶点多边形 | 1. 容量实测：`-2000,-2000` 文本格式 21 点占 `251 B`，第 22 点溢出。<br>2. G1 契约验证（`C-13`）：包含全部 8 项 R60 主机配置项及几何合法的 64 顶点凸多边形的 `CONFIG_COMMIT` 请求，UTF-8 JSON 负载远小于 `MAX_PAYLOAD = 4096 B`。 | **B 类** | **明确契约**：<br>1. MWCP/1 协议与 Schema 保持 `geometry.boundary_cm` 支持 `3..64` 个顶点（`schema_id: "polygon.xy.v1"`）。<br>2. WP-2 实现 `ConfigService` 双槽持久化快照时，必须使用独立的二进制/结构化 NVS 快照存储，不再受旧 254 字节字符串 `globals` 限制，并提供旧 `g_polygon` 一次性迁移。 | `docs/protocol/schema/mwcp-v1.schema.json`、WP-2 `ConfigService` | `static/test/protocol-schema.test.js`（64 顶点凸多边形最大 R60 配置提交与 `4096B/4097B` 边界测试） | WP-1（Schema 已锁定）→ WP-2（`ConfigService` 存储） | **B 类方案已收口（待独立复核）** |
| **DD-05** | 现有固件多边形解析器会跳过格式错误的点且不检查自交，而协议要求整笔原子拒绝 | 1. `static/src/protocol/geometry.js` (`polygonIssues`)、`contract.js` (`validateConfigChanges`) 与 `simulator.js` 已实现完整几何校验：检查顶点数（边界 `3..64`，R60 区域 `3..12`）、坐标范围 `[-2000, 2000] cm`、相邻重复点、显式重复首尾闭合点、退化零面积、共线重叠与非相邻边自交。<br>2. 任何单点或几何违规在 `CONFIG_VALIDATE` 与 `CONFIG_COMMIT` 中均整笔拒绝并返回 `INVALID_ARGUMENT`（或范围超限返回 `OUT_OF_RANGE`）。 | **B 类** | **明确契约**：<br>1. 锁定整笔原子拒绝语义，严禁静默丢弃坏点或截断多边形。<br>2. WP-2 固件端 `ConfigService` 必须移植与 `geometry.js` 完全一致的多边形校验算法，使 HA 入口与 MWCP 入口共享同一校验标准。 | `static/src/protocol/geometry.js`、`contract.js`、`simulator.js`、WP-2 `ConfigService` | `static/test/protocol-coordinates.test.js`、`static/test/protocol-schema.test.js` | WP-1（JS/Schema 已实现）→ WP-2（C++ 移植） | **B 类方案已收口（待独立复核）** |
| **DD-06** | R60ABD1 原厂协议不上报目标速度，但旧固件 `publish_target_frame_` 写入占位值 `0` | 1. R60ABD1 手册与源码确认 `0x80/0x05` 仅含 X/Y/Z 坐标，无速度字段。<br>2. `r60abd1-capabilities.json` 已声明 `{"kind": "feature", "id": "speed.cm_s", "supported": false}` 且列入 `unsupported`。<br>3. `TELEMETRY (0x8001)` 中 R60 目标的 `speed_cm_s` 固定为 `null`。 | **A 类** | **已解决并收口**：<br>R60ABD1 的 `speed.cm_s.supported` 固定为 `false`，遥测快照中 `speed_cm_s` 必须输出 `null`，严禁将占位 `0` 伪造为实测零速度。 | `docs/protocol/fixtures/r60abd1-capabilities.json`、`static/src/protocol/simulator.js`、WP-2 R60 Adapter | `static/test/protocol-schema.test.js`、`static/test/protocol-session.test.js` | WP-1（已收口） | **已解决（待独立复核）** |
| **DD-07** | R60 各观测字段的 `expected_interval_ms` 与 `stale_after_ms` 取值尚未在真机确认 | 1. **G0-03 2 小时真机长测精确计数**（`7,199.8 s`，`7,198` 样本）：<br>  - 全类别合法帧 `radar_frames`：`+34,878`（均值 **`4.84 Hz`**，每秒 `4..8` 帧，含心跳、存在 `0x80/0x01`、运动 `0x80/0x02`、体动 `0x80/0x03`、距离 `0x80/0x04`、坐标 `0x80/0x05`、呼吸、心率、睡眠）。<br>  - 2D 坐标帧 `radar_targets`（仅计 `0x80/0x05`）：`+3,599`（严格 **`0.50 Hz`**，即每 **`2,000 ms`** 1 帧）。<br>2. 固件 `R60ABD1Component::publish_position_()` 另有 `1,000 ms` 发布节流，且无串口字节 `1,000 ms` 清除存在。<br>3. 不能把总串口帧率 `~4.84 Hz` 混同于单字段更新间隔。 | **C 类（已拍板）** | **用户已批准采用选项 C2（仅设置已获真机证明的 `position.xy`）**：<br>将 `r60abd1-capabilities.json` 与 `simulator.js` 中的 `position.xy` 设为 `expected_interval_ms: 2000, stale_after_ms: 6000`；其余未单独分桶计数的事件驱动/混合字段保持 `null`（详见第 3.1 节）。 | `docs/protocol/fixtures/r60abd1-capabilities.json`、`static/src/protocol/simulator.js`、WP-3 遥测过期提示 | 真机 `G0-03`（`g0-evidence-index.json`）、`static/test/protocol-schema.test.js` | WP-1（已按用户决策落地）→ WP-2 / WP-3 | **已由用户批准并落地（选项 C2）** |
| **DD-08** | R60 安装高度 `install.z_cm` 在 HA number 实体中为 `50..400 cm`，而组件 Python `CONFIG_SCHEMA` 允许任意正数 | 1. 原 `tests/common/r60abd1.yaml` 中 HA number 实体 `num_radar_z` 为 `50..400` (step `1`)。<br>2. 用户明确拍板采用**同步放宽上限方案（选项 C2：`50..600 cm`）**。<br>3. 已同步更新 `r60abd1-capabilities.json`、`static/src/protocol/simulator.js` 与 `tests/common/r60abd1.yaml`（`num_radar_z` `max_value: 600`），保持三端范围一致。 | **C 类（已拍板）** | **用户已批准采用选项 C2（同步放宽上限为 `50..600 cm`）**：<br>三端（`r60abd1-capabilities.json`、`simulator.js`、`tests/common/r60abd1.yaml` `num_radar_z`）统一将 `install.z_cm` 设为 `min: 50, max: 600, step: 1`（详见第 3.2 节）。 | `docs/protocol/fixtures/r60abd1-capabilities.json`、`static/src/protocol/simulator.js`、`tests/common/r60abd1.yaml` | `static/test/protocol-schema.test.js`（验证 `install.z_cm = 600` 通过、`601` 报 `OUT_OF_RANGE`） | WP-1（已按用户决策完成三端同步） | **已由用户批准并落地（选项 C2：`50..600 cm`）** |
| **DD-09** | CRC32C 校验通过但 JSON 语法非法时，是静默计错丢弃还是返回应用层 `INVALID_ARGUMENT` | 1. 协议草案第 2 节解析顺序规定：分隔→COBS→长度→头部→CRC32C→UTF-8→JSON→结构/字段验证；坏帧不产生应用响应。<br>2. `static/src/protocol/codec.js` (`decodeDecoded`) 与 `protocol/cpp/mwcp_codec.cpp` (`decode_decoded`) 均在帧解码层执行 `checkJson`/`json_check`，JSON 语法错误直接返回 `bad_json` 并计入 codec 统计，不生成响应帧。 | **A 类** | **已解决并收口**：<br>CRC32C 合法但 UTF-8 或基础 JSON 语法/深度/键数/重复键/安全整数校验失败的帧，统一归类为 codec 层损坏（`bad_utf8` / `bad_json`），两端只递增诊断计数并丢弃，**不返回应用层响应帧**。只有合法 JSON 对象进入命令分发后才返回 `errorEnvelope`。 | `static/src/protocol/codec.js`、`protocol/cpp/mwcp_codec.cpp`、`protocol/cpp/mwcp_json.cpp` | `static/test/protocol-codec.test.js`、`protocol/cpp/mwcp_host_test.cpp` (`P-01`～`P-14`) | WP-1（已收口） | **已解决（待独立复核）** |
| **DD-10** | 标准 JSON Schema `maxLength` 按 Unicode 字符数计数，而协议要求按 UTF-8 字节数限制字符串长度 | 1. `docs/protocol/schema/mwcp-v1.schema.json` 已定义扩展关键字 `x-maxUtf8Bytes`（如 `ssid` 限 `32` UTF-8 字节，`revision` 限 `20` 字节，`message` 限 `256/512` 字节）。<br>2. `static/src/protocol/schema.js` 使用 `utf8Len()` 精确校验 `x-maxUtf8Bytes`。 | **A 类** | **已解决并收口**：<br>Schema 统一使用 `x-maxUtf8Bytes` 表达 UTF-8 字节上限，校验器按 UTF-8 编码后字节数严格判定。 | `docs/protocol/schema/mwcp-v1.schema.json`、`static/src/protocol/schema.js` | `static/test/protocol-schema.test.js`（11 个中文字符 = 33 UTF-8 字节 SSID 拒绝测试） | WP-1（已收口） | **已解决（待独立复核）** |
| **DD-11** | 多边形射线法（Ray-Casting）对落在边界线/顶点上的边缘点归属（`inside` vs `outside`）必须与现有固件及卡片一致 | 1. 现有固件（`components/r60abd1/r60abd1_transform.h`）与 `mmwave-card` 的射线法将正方形 `[0..100, 0..100]` 上的 `(50, 0)` 与 `(0, 0)` 判为 `inside`，`(150, 10)` 判为 `outside`。<br>2. `static/src/protocol/geometry.js`、`static/src/protocol/transform.js` 与 `docs/protocol/fixtures/coordinate-vectors.json` 已锁定该精确行为。 | **A 类** | **已解决并收口**：<br>严格锁定现有射线法谓词与共享坐标向量结果，不在协议层私自修改边界包含谓词，确保固件、HA 卡片与 Web Console 判定 100% 一致。 | `static/src/protocol/geometry.js`、`static/src/protocol/transform.js`、`docs/protocol/fixtures/coordinate-vectors.json` | `static/test/protocol-coordinates.test.js`、`protocol/cpp/mwcp_host_test.cpp` (`test_transform`)、工作区 `tests/unit/test_mwcp_sources.py` | WP-1（已收口） | **已解决（待独立复核）** |
| **DD-12** | 协议草案规定 Web Serial `port.open({ bufferSize: 16384 })`，而 `esp-web-tools 10.4.0` 内部使用 `8192` | 1. `static/src/g0/diag.js` 已使用 `bufferSize: 16384` 打开串口，并在 G0-04 真机 Chrome 155 上验证稳定。<br>2. `esp-web-tools` 安装器在独立生命周期中运行，关闭后由控制台以 `16384` 重新打开端口，互不干扰。 | **B 类** | **明确契约**：<br>不修改 `esp-web-tools` 内部代码；Web Console 打开串口统一使用规范参数 `baudRate: 115200, bufferSize: 16384`。 | `static/src/g0/diag.js`、WP-3 Web Serial 传输层 | `static/test/g0-diag.test.js`、真机 `G0-04` | WP-1（已采用）→ WP-3 | **B 类方案已收口（待独立复核）** |
| **DD-13** | JSON 对象中含有转义等价重复键（如 `{"a":1,"\u0061":2}`）时，JS 与 C++14 是否一致拒绝 | 1. `static/src/protocol/json.js` 与 `protocol/cpp/mwcp_json.cpp` (`json_check`) 均已在解码字符串转义序列后比对同一对象内的所有键名。<br>2. `protocol/fixtures/json-cases.json` 中的转义重复键用例在 JS 与 C++14 双端均精确返回 `duplicate_key` 拒绝。 | **A 类** | **已解决并收口**：<br>两端统一按反转义后的键名检测重复键，任何字面或转义等价重复键一律拒绝。 | `static/src/protocol/json.js`、`protocol/cpp/mwcp_json.cpp`、`protocol/fixtures/json-cases.json` | `static/test/protocol-codec.test.js`、`static/test/protocol-h-fixes.test.js`、`protocol/cpp/mwcp_host_test.cpp` | WP-1（已收口） | **已解决（待独立复核）** |
| **DD-14** | 带科学计数法指数或 `.0` 小数的超大整数值（如 `9007199254740993e0`、`9007199254740993.0`）是否受 `±(2^53-1)` 安全整数约束 | 1. `static/src/protocol/json.js` 与 `protocol/cpp/mwcp_json.cpp` 均对数学值为整数的 JSON number 检查 `±9007199254740991` 范围，并对照 `protocol/fixtures/double-overflow-threshold.txt` 检查 binary64 溢出边界。<br>2. `protocol/fixtures/json-cases.json` 中的指数/小数超大整数在双端均被拒绝。 | **A 类** | **已解决并收口**：<br>凡数学值为整数的 JSON number（无论书写为十进制整数、`.0` 或正指数形式）均不得超出 `±(2^53-1)`，否则按 `unsafe_integer` 拒绝。 | `static/src/protocol/json.js`、`protocol/cpp/mwcp_json.cpp`、`protocol/fixtures/json-cases.json` | `static/test/protocol-codec.test.js`、`static/test/protocol-h-fixes.test.js`、`protocol/cpp/mwcp_host_test.cpp` | WP-1（已收口） | **已解决（待独立复核）** |
| **DD-15** | 协议要求“未知响应/事件字段可忽略，未知请求字段必须拒绝”如何在 JSON Schema 中机器化表达 | 1. `docs/protocol/schema/mwcp-v1.schema.json` 对响应 `result` 与 `event` 对象设置 `"x-open-object": true`，对所有 `request` 对象保持 `"additionalProperties": false`。<br>2. `static/src/protocol/schema.js` 与 `contract.js` 严格执行：请求含未知字段返回 `UNKNOWN_FIELD`，响应/事件含未知扩展字段正常放行。 | **A 类** | **已解决并收口**：<br>保持请求闭合（拒绝未知字段并报 `UNKNOWN_FIELD`）、响应与事件开放（通过 `x-open-object: true` 忽略未知附加字段）的前向兼容规则。 | `docs/protocol/schema/mwcp-v1.schema.json`、`static/src/protocol/schema.js`、`contract.js` | `static/test/protocol-schema.test.js`（请求拒绝未知字段 vs 响应/事件忽略未知字段回归） | WP-1（已收口） | **已解决（待独立复核）** |

---

## 3. C 类决策项拍板记录与落地详情（用户已批准）

### 3.1 `DD-07`：R60ABD1 能力描述符中的 `expected_interval_ms` 与 `stale_after_ms`
- **背景与 G0 真机证据**：
  - 早期协议草案第 5 节曾以 `position.xy: { expected_interval_ms: 2000, stale_after_ms: 6000 }` 作为示例，并注明“须真机验证；若未说明可为 `null`”。
  - 在 G0-03 2 小时真机长测（`7,199.8 s`）中，获得了确凿的硬件统计证据：
    1. `R60ProbeStats::target_observations`（专门统计 R60 `0x80/0x05` 2D 坐标帧）在 `7,199.8 s` 内从 `14` 增至 `3,613`（净增 `3,599` 帧），证明 **R60ABD1 硬件上报 `position.xy` 的真实周期精确为 `2,000 ms`（`0.50 Hz`）**。
    2. `R60ProbeStats::valid_frames`（汇总心跳、存在 `0x80/0x01`、运动 `0x80/0x02`、体动 `0x80/0x03`、距离 `0x80/0x04`、坐标 `0x80/0x05`、呼吸、心率、睡眠等全部控制字）净增 `34,878` 帧（均值 **`4.84 Hz`**，`4..8 帧/秒`）。由于 G0 探针未对除 `0x80/0x05` 以外的每个子控制字单独分桶计数，因此 `presence`、`breath_rate`、`heart_rate` 等字段各自的独立硬件周期尚未在 G0 中单独分桶测量。
- **对比方案**：
  - **选项 C1**：在 `docs/protocol/fixtures/r60abd1-capabilities.json` 中，所有观测特征暂保持 `"expected_interval_ms": null, "stale_after_ms": null`。
  - **选项 C2（用户已拍板采用）**：仅设置已获 G0 真机证明的 `position.xy`，将其更新为 `"expected_interval_ms": 2000, "stale_after_ms": 6000`，其余未单独分桶计数的字段保持 `null`。
  - **选项 C3**：在 WP-2 编写 R60 生产 Adapter 时，为每个特征记录独立帧计数并在 G2 阶段统一填入。
- **最终状态**：**已由用户批准采用选项 C2 并落地**（已更新 `docs/protocol/fixtures/r60abd1-capabilities.json`、`static/src/protocol/simulator.js` 与 `static/test/protocol-schema.test.js`）。

### 3.2 `DD-08`：R60ABD1 安装高度 `install.z_cm` 的允许范围（`50..400 cm` vs 同步放宽上限 `50..600 cm`）
- **背景与证据**：
  - 原 `tests/common/r60abd1.yaml` 中 Home Assistant 的 `num_radar_z` Number 实体定义为 `min_value: 50, max_value: 400, step: 1`（单位 `cm`），而 `components/r60abd1/__init__.py` 的编译期 YAML Schema 允许任意正数。
- **对比方案**：
  - **选项 C1**：保持 `install.z_cm` 范围为 `50..400 cm`（step `1`）。
  - **选项 C2（用户已拍板采用）**：同步放宽上限为 `50..600 cm`（step `1`），同时更新 `tests/common/r60abd1.yaml`（`num_radar_z`）、`docs/protocol/fixtures/r60abd1-capabilities.json` 与 `static/src/protocol/simulator.js`，确保 Home Assistant 实体、固件与 Web Console 三端范围 100% 一致。
- **最终状态**：**已由用户批准采用选项 C2（`50..600 cm`）并完成三端同步落地**（已在 `static/test/protocol-schema.test.js` 中验证 `install.z_cm = 600` 提交成功、`601` 精确返回 `OUT_OF_RANGE`）。

---

## 4. 非 v1 范围的明确排除声明（已收口）
1. `AUTH_REQUIRED` 不属于 MWCP/1 错误码（v1 依赖物理 USB 本地可信边界）。
2. R60ABD1 的局部 Z 轴输出仅作为 `diagnostics.local_z` 诊断特征暴露，不将 R60ABD1 定义为 3D 点云产品。
3. `inject_mock_data` 与 `raw_uart_tx` 不属于 MWCP/1 生产动作，严禁在生产固件中开放。
