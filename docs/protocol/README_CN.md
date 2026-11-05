# MWCP/1 毫米波设备控制台协议规范（组件自包含规范基线）

- **文档状态**：**G1 整改候选，待独立复核**（`DD-01`～`DD-15` 已收口，含用户已批准并落地的 `DD-07` C2 与 `DD-08` C2，以及 G1-R1～G1-R5 验收整改）
- **协议主版本**：`major = 1`, `minor = 0`（线格式标识 `MWCP`）
- **英文镜像**：[docs/protocol/README.md](./README.md)
- **设计差异与处置台账**：[docs/protocol/design-differences_CN.md](./design-differences_CN.md)（[English](./design-differences.md)）
- **G0 硬件实测证据索引**：[docs/reviews/web-console/g0-evidence-index.json](../reviews/web-console/g0-evidence-index.json)
- **阶段验收报告**：[docs/reviews/web-console/wp0-wp1-phase-report_CN.md](../reviews/web-console/wp0-wp1-phase-report_CN.md)（[English](../reviews/web-console/wp0-wp1-phase-report.md)）
- **总体设计来源**：工作区 `docs/plans/mmwave-web-console/protocol-v1.md`

---

## 0. 规范优先级与契约资产清单

当计划文档、阶段报告与代码实现之间出现措辞差异时，MWCP/1 的**权威真源优先级（从高到低）**如下：

1. **可执行机器契约与黄金向量（最高优先级，两端逐字节互验）**：
   - 共享协议黄金向量与测试夹具：
     - [`protocol/fixtures/protocol-vectors.json`](../../protocol/fixtures/protocol-vectors.json)（与工作区 `docs/plans/mmwave-web-console/protocol-vectors.json` 保持 SHA-256 逐字节一致，由工作区 `tests/unit/test_mwcp_sources.py` 强制校验）；
     - [`protocol/fixtures/json-cases.json`](../../protocol/fixtures/json-cases.json) 与 [`protocol/fixtures/double-overflow-threshold.txt`](../../protocol/fixtures/double-overflow-threshold.txt)（JS 与 C++14 共用的 JSON 边界与 binary64 溢出阈值夹具）；
     - [`docs/protocol/fixtures/coordinate-vectors.json`](./fixtures/coordinate-vectors.json)（3D 旋转矩阵、1D `+Y` 投影与多边形射线法边缘点共享向量）。
   - 机器可校验 JSON Schema：[`docs/protocol/schema/mwcp-v1.schema.json`](./schema/mwcp-v1.schema.json)（覆盖全部 `19` 个命令的 `request`/`result`、`5` 个 `event`、统一 `errorEnvelope` 及 `x-configSchemas` 结构化配置定义 `polygon.xy.v1`、`range.window.v1`、`r60.areas.v1`）。
   - R60ABD1 能力与配置描述符唯一真源：[`docs/protocol/fixtures/r60abd1-capabilities.json`](./fixtures/r60abd1-capabilities.json)（共 `19` 项：`11` 项观测特征/指标 + `8` 项主机可写配置；另含 `2` 项支持动作与 `4` 项显式 `unsupported` 声明）。
   - 双端参考实现：
     - JavaScript：[`static/src/protocol/limits.js`](../../static/src/protocol/limits.js)、[`static/src/protocol/codec.js`](../../static/src/protocol/codec.js)、[`static/src/protocol/json.js`](../../static/src/protocol/json.js)、[`static/src/protocol/schema.js`](../../static/src/protocol/schema.js)、[`static/src/protocol/geometry.js`](../../static/src/protocol/geometry.js)、[`static/src/protocol/transform.js`](../../static/src/protocol/transform.js)、[`static/src/protocol/contract.js`](../../static/src/protocol/contract.js)、[`static/src/protocol/client.js`](../../static/src/protocol/client.js)、[`static/src/protocol/simulator.js`](../../static/src/protocol/simulator.js)、[`static/src/protocol/flash-handoff.js`](../../static/src/protocol/flash-handoff.js)。
     - C++14（无异常 `-fno-exceptions`、无 RTTI `-fno-rtti`）：[`protocol/cpp/mwcp_codec.h`](../../protocol/cpp/mwcp_codec.h)、[`protocol/cpp/mwcp_codec.cpp`](../../protocol/cpp/mwcp_codec.cpp)、[`protocol/cpp/mwcp_json.h`](../../protocol/cpp/mwcp_json.h)、[`protocol/cpp/mwcp_json.cpp`](../../protocol/cpp/mwcp_json.cpp) 以及坐标变换头 [`components/r60abd1/r60abd1_transform.h`](../../components/r60abd1/r60abd1_transform.h)。
2. **本组件自包含规范正文**：`docs/protocol/README_CN.md` 与 `docs/protocol/README.md`。
3. **设计差异与处置台账**：`docs/protocol/design-differences_CN.md`（`DD-01`～`DD-15`）。
4. **工作区早期设计档案**：`docs/plans/mmwave-web-console/protocol-v1.md`。

---

## 1. 适用范围、分层与非目标

### 1.1 分层模型
1. **字节传输层**：浏览器 Web Serial API ↔ ESP32-C3 原生 `USB Serial/JTAG`（或经验证的 USB-UART 桥接），面向主机控制台通信，不改变雷达模组内部 UART 协议（ESP32-C3 与 R60ABD1 在 `UART1` `GPIO21 TX / GPIO20 RX` 上以 `115200 8N1` 独立通信）。
2. **帧与校验层**：`0x00 | COBS(decoded_frame) | 0x00`，包含 24 字节定长包头、UTF-8 JSON 负载（`<= 4096 B`）与 4 字节尾随 `CRC32C (Castagnoli)`；支持分包、粘包、上电/崩溃噪声隔离与半帧超时自愈。
3. **会话与可靠性层**：`HELLO` 握手、`session_id` / `request_id` / `nonce` / `boot_id` 关联、最近 4 条响应缓存去重（`ID_REUSE` / `REQUEST_EXPIRED`）与超时控制。
4. **应用语义层**：设备身份、能力分页发现（`CAPABILITIES_LIST`）、实时遥测与日志订阅（`SUBSCRIBE`/`UNSUBSCRIBE`）、主机配置原子事务（`CONFIG_READ`/`VALIDATE`/`COMMIT`/`COMMIT_STATUS`）、异步任务（`ACTIONS_LIST`/`ACTION_START`/`JOB_GET`）与 USB Wi-Fi 配网（`WIFI_*`）。

### 1.2 串口打开参数与单一端口所有者约束
- **浏览器 `port.open()` 默认参数**：`baudRate: 115200`、8N1、无硬件流控、`bufferSize: 16384`（详见 `DD-12`：现有 `esp-web-tools 10.4.0` 安装器内部使用 `8192`，独立控制台打开串口时采用规范值 `16384`）。不随意切换 `DTR/RTS` 以免触发板卡复位。
- **单一运行时所有者（`DD-03`，G0 真机已验证）**：
  - 同一物理 USB 串口在同一时刻只允许一个运行时消费者。启用 MWCP 的 host profile（如 [`docs/reviews/web-console/g0/host.yaml`](../reviews/web-console/g0/host.yaml)）必须移除 stock `improv_serial`，设置 `CONFIG_ESP_CONSOLE_NONE: y`、`CONFIG_ESP_CONSOLE_USB_SERIAL_JTAG: n`，将 `logger` 设为 `hardware_uart: UART0, baud_rate: 0`（禁用串口明文日志混排），并将 `wifi.reboot_timeout` 与 `api.reboot_timeout` 设为 `0s`。R60ABD1 的日常配置和工厂配置现在遵循这条规则。其他型号仍通过 `tests/common/_standard_device.yaml` 保留串口 Improv。未打补丁的 ESPHome 上，`wifi.scan` 仍不可用。
  - **G0 硬件实测关键边界**：在 LuatOS ESP32C3-CORE（`USB\VID_303A&PID_1001`）原生 `USB Serial/JTAG` 上，若主机停止读取 IN URB，而固件端阻塞式向 `USB_SERIAL_JTAG` 写入数据，硬件 64B TX FIFO 写满后会阻塞主循环。因此 `HostLink` 发送必须采用 64B 分块非阻塞泵（连续零写 `250 ms` 放弃并标记下一帧前补 `0x00` 重同步）。

### 1.3 首版非目标
- **不定义 BLE**：不分配 GATT UUID，不实现 BLE 分片、配对或广播。
- **不替代原厂雷达 UART**：不开放通过网页发送任意裸原厂 UART 指令（`raw_uart_tx`），不开放 `inject_mock_data`。
- **不升级为 3D 点云产品**：范围仅限 1D/2D 雷达，R60ABD1 的原始 Z 轴仅作为诊断特征 `diagnostics.local_z` 暴露。

---

## 2. 帧格式、CRC32C 与 JSON 约束（规范）

### 2.1 在线封装与 COBS 规则
- **在线字节流格式**：`0x00 | COBS(decoded_frame) | 0x00`。
  - 每次发送帧均以 `0x00` 开头并以 `0x00` 结尾；连续的 `0x00`（空帧）直接忽略。
  - COBS 采用标准 `0xFF` 分段规则（非 COBS/R）。
  - 所有多字节整数均为 **Little-Endian（小端序）**。

### 2.2 解码后帧结构（`decoded_frame`）

| `decoded` 字节偏移 | 长度（字节） | 字段名 | v1 规范取值与语义 |
| :--- | :--- | :--- | :--- |
| `0..3` | 4 | `magic` | 固定 ASCII `"MWCP"`（十六进制 `4d 57 43 50`） |
| `4` | 1 | `major` | 主版本号，固定为 `1` |
| `5` | 1 | `minor` | 次版本号，固定为 `0` |
| `6` | 1 | `kind` | 帧类别：`1` = `request`，`2` = `response`，`3` = `event` |
| `7` | 1 | `flags` | 标志位，v1 固定为 `0`（其余位保留且**必须**为 `0`，非零报 `bad_flags`） |
| `8..11` | 4 (`uint32 LE`) | `session_id` | 会话 ID：`HELLO` 请求固定为 `0`；已建立会话为设备分配的非零 `uint32` |
| `12..15` | 4 (`uint32 LE`) | `request_id` | 请求/响应匹配 ID；`event` 帧固定为 `0`；请求帧为 `0` 属非法 |
| `16..17` | 2 (`uint16 LE`) | `code` | 命令或事件编号（见第 4 节注册表） |
| `18..19` | 2 (`uint16 LE`) | `payload_length` | JSON 负载的 UTF-8 字节数（`0 <= N <= 4096`，不是字符数） |
| `20..23` | 4 (`uint32 LE`) | `wire_seq` | 单方向发帧递增计数，允许按 `uint32` 模回绕；仅用于传输诊断，不参与业务去重 |
| `24 .. 24+N-1` | `N` | `payload` | UTF-8 编码的 JSON 对象字节串（`N <= 4096`） |
| `24+N .. 27+N` | 4 (`uint32 LE`) | `crc32c` | 覆盖 `decoded[0 .. 24+N-1]`（即 24B 包头 + `payload`）的 CRC32C 校验值 |

### 2.3 长度硬限制与 CRC32C 算法
- **常量定义（`static/src/protocol/limits.js` / `protocol/cpp/mwcp_codec.h`）**：
  - `HEADER_LEN = 24`，`CRC_LEN = 4`，最小合法 `decoded` 长度为 **`28` 字节**。
  - `MAX_PAYLOAD = 4096` 字节。
  - `MAX_DECODED = 24 + 4096 + 4 = 4124` 字节。
  - `MAX_COBS = 4124 + floor(4124 / 254) + 1 = 4141` 字节。
  - `MAX_WIRE = MAX_COBS + 2 = 4143` 字节（含首尾 `0x00` 分隔符）。
  - `HALF_FRAME_MS = 2000` 毫秒（半帧持续 `2000 ms` 无新字节到达则丢弃当前缓冲并等待下一个 `0x00` 分隔符，`stats.timeouts++`）。
- **CRC32C (Castagnoli) 参数**：
  - 反射多项式：`0x82F63B78`（初值 `0xFFFFFFFF`，最终异或 `0xFFFFFFFF`）。
  - 标准校验串 ASCII `"123456789"` 的 CRC32C 值为 **`0xE3069283`**，小端在线字节序为 **`83 92 06 e3`**。禁止混用 IEEE 802.3 CRC32。
- **严格解析顺序与静默丢弃边界（`DD-09` 已收口）**：
  1. `0x00` 分隔符切分与 `MAX_COBS (4141 B)` 累积上限检查（超限立即进入 `discarding` 状态直至下一个 `0x00`，计 `oversize`）；
  2. COBS 解码（失败计 `bad_cobs`）；
  3. `decoded` 长度范围（`28 .. 4124 B`）与 `magic` (`"MWCP"`)、`major (1)` / `minor (0)`、`kind (1..3)`、`flags (0)` 检查；
  4. `payload_length <= 4096` 且 `decoded.length === 24 + payload_length + 4` 精确匹配（禁止尾随字节）；
  5. `CRC32C` 校验（失败计 `bad_crc`）；
  6. 严格 UTF-8 校验（`bad_utf8`）与基础 JSON 语法/深度/键数/重复键/安全整数校验（`bad_json`）。
  - **关键规则**：步骤 1～6 中任何一项失败均属于**编解码层损坏**，接收端只递增对应诊断计数器，**不执行命令且不生成应用层响应帧**（防止噪声放大）。只有通过步骤 1～6 获得合法包络与合法 JSON 对象后，若命令号未知或业务字段校验失败，才返回应用层错误响应 `{"ok":false,"error":{...}}`。

### 2.4 JSON 语法与安全约束（`DD-10`、`DD-13`、`DD-14`、`DD-15` 已收口）
1. **结构上限**：根节点必须为 JSON Object（`{...}`），无 UTF-8 BOM；最大嵌套深度 `JSON_MAX_DEPTH = 10`（根对象深度为 1；从 8 提高到 10，使 `CONFIG_READ` 包络能装下 `areas.definitions`）；单对象最多 `JSON_MAX_KEYS = 64` 个键；单数组最多 `JSON_MAX_ITEMS = 256` 项。
2. **禁止等价重复键（`DD-13`）**：`static/src/protocol/json.js` 与 `protocol/cpp/mwcp_json.cpp` 均在反转义（`\uXXXX` 等）后比较对象键名，任何字面重复或转义等价重复键（如 `{"a":1,"\u0061":2}`）一律按 `duplicate_key` 拒绝。
3. **安全整数与 binary64 溢出阈值（`DD-14`）**：所有数学值为整数的 JSON 数值（含不带小数的十进制数，以及带指数或 `.0` 尾数但数学值为整数的数值，如 `9007199254740993e0`、`9007199254740993.0`）必须在 `±(2^53 - 1)`（`MAX_SAFE_INT = 9007199254740991`）范围内；超出按 `unsafe_integer` 拒绝。非整数按 IEEE 754 binary64 向偶舍入溢出点 `2^1024 - 2^970`（`protocol/fixtures/double-overflow-threshold.txt`）严格判定有限性。64 位持久化 `revision` 统一使用十进制数字字符串（`^[0-9]+$`，`x-maxUtf8Bytes: 20`）。
4. **UTF-8 字节长度约束（`DD-10`）**：Schema 中使用自定义扩展关键字 `x-maxUtf8Bytes` 约束字符串的 UTF-8 字节长度（例如多字节中文 SSID 按 UTF-8 字节数统计，`<= 32` 字节），而非 UTF-16 字符数。
5. **前向兼容字段策略（`DD-15`）**：请求对象严禁未知字段（违者返回 `UNKNOWN_FIELD`）；响应与事件对象在 Schema 中标记 `x-open-object: true`，允许未来次版本新增可选字段而不破坏现有客户端。

---

## 3. 会话生命周期、请求去重与超时

### 3.1 `HELLO (0x0001)` 握手
客户端打开串口后发送 `session_id = 0`、`request_id = 1`、`code = 0x0001 (HELLO)`：
```json
{
  "client": { "name": "mmwave-web-console", "version": "0.1.0" },
  "nonce": "0123456789abcdef0123456789abcdef",
  "protocol": { "major": 1, "minor_max": 0 },
  "max_payload": 4096
}
```
设备端分配非零 `session_id` 放入响应包头，返回：
```json
{
  "ok": true,
  "result": {
    "nonce": "0123456789abcdef0123456789abcdef",
    "protocol": { "major": 1, "minor": 0 },
    "boot_id": "fedcba9876543210fedcba9876543210",
    "session_ttl_ms": 15000,
    "limits": {
      "max_payload": 4096,
      "rpc_inflight": 1,
      "max_targets": 8,
      "event_budget_bps": 8000
    },
    "identity": {
      "device_id": "local-device-id",
      "configured_model": "r60abd1",
      "dimension": "2D",
      "firmware_version": "0.1.0-alpha.1"
    },
    "cap_revision": "r60-cap-1"
  }
}
```
- `nonce` 与 `boot_id` 均为 16 字节随机数的 32 位小写十六进制字符串（`^[0-9a-f]{32}$`）。客户端仅接受 `request_id` 与 `nonce` 均匹配的 `HELLO` 响应。
- 若客户端 `max_payload < 4096`，设备返回 `LIMIT_UNSUPPORTED`；若主版本不兼容，以 `session_id = 0` 返回 `VERSION_UNSUPPORTED`。
- 同一 `nonce` 的 `HELLO` 重传返回当前会话；新 `nonce` 替换旧会话、清空旧订阅与旧 `request_id` 去重窗口，但不会取消或重做已受理的持久化写任务。

### 3.2 `request_id` 严格递增与 4 槽响应去重缓存
- 会话建立后，客户端 `request_id` 从 `2` 开始严格递增（`0` 保留给 `event` 帧）。普通 RPC 同时最多 `1` 个在途（`rpc_inflight = 1`）；长耗时任务（`ACTION_START` / `WIFI_SCAN` / `WIFI_PROVISION`）返回 `job_id` 后即释放 RPC 槽位。
- **传输层去重（4 槽缓存）**：
  - 设备在当前会话内缓存最近 `4` 个已完成的 `(request_id, code, payload_sha256, response)`。
  - 收到相同 `request_id`、相同 `code` 且相同 `payload` 字节时，直接重放缓存响应，不重复执行。
  - 收到相同 `request_id` 但 `code` 或 `payload` 不同时，返回 `ID_REUSE`。
  - 收到 `request_id <= max_seen_request_id` 且已移出 4 槽缓存的旧请求时，返回 `REQUEST_EXPIRED`，绝不重新执行。
- **业务层幂等（`op_id`）**：
  - 具有副作用的命令（`CONFIG_COMMIT`、`ACTION_START`、`WIFI_SCAN`、`WIFI_PROVISION`）携带 UUID 格式 `op_id`。
  - `CONFIG_COMMIT` 在持久化快照中保留最近 `4` 次提交的 `(op_id, request_sha256, revision)`；相同 `op_id` 且摘要一致时直接返回原提交结果（先判 `op_id` 去重，再判 `base_revision`）；相同 `op_id` 但摘要不同返回 `OP_ID_REUSE`。

### 3.3 超时与保活参数
- **客户端超时**：
  - `HELLO` 握手：`3,000 ms`；
  - 普通只读/查询 RPC：`1,000 ms`（允许使用**相同 `request_id` 与相同字节**自动重试 1 次）；
  - `CONFIG_COMMIT`：`2,000 ms`（超时后标记结果未知并通过 `COMMIT_STATUS` + `CONFIG_READ` 核实，禁止自动生成新 `op_id` 重发）；
  - `ACTION_START` / `WIFI_PROVISION` 受理：`1,000 ms`（超时不以新 ID 自动重发，改为 `JOB_GET` / `WIFI_STATUS` 查询）。
- **会话 TTL 与心跳**：客户端每 `5,000 ms` 发送 `PING (0x0002)`；会话在 `15,000 ms`（`session_ttl_ms`）内无合法客户端请求则过期并清理订阅（设备主动发出的 `event` 不自续期）。

### 3.4 统一响应与错误信封格式
- **成功响应（`kind = 2`）**：`{"ok": true, "result": { ... }}`（`header.code` 与请求 `code` 相同，`header.request_id` 回显请求 `request_id`）。
- **错误响应（`kind = 2`）**：
```json
{
  "ok": false,
  "error": {
    "code": "REVISION_CONFLICT",
    "message": "Configuration changed",
    "field": "base_revision",
    "details": { "current_revision": "43" }
  }
}
```

#### 标准错误码枚举（18 个机器码，`limits.js` `ERROR`）

| 错误码 (`error.code`) | 触发条件与客户端处置语义 |
| :--- | :--- |
| `VERSION_UNSUPPORTED` | `HELLO` 协议主版本不匹配；停止操作并提示兼容版本 |
| `LIMIT_UNSUPPORTED` | `HELLO` 中 `max_payload < 4096`；拒绝连接 |
| `UNSUPPORTED` | 命令或配置项/动作不被当前型号能力支持；UI 禁用或隐藏对应项 |
| `INVALID_ARGUMENT` | 参数类型、格式、枚举、确认串（`confirm`）或多边形几何不合法 |
| `UNKNOWN_FIELD` | 请求体或配置 `changes` 含有未声明字段 |
| `OUT_OF_RANGE` | 数值超出配置描述符声明的 `[minimum, maximum]` 范围 |
| `PAYLOAD_TOO_LARGE` | 负载超出 `4096 B` 或单条配置记录超出预算；禁止静默截断或私自拆包 |
| `ID_REUSE` | 同一 `request_id` 被用于不同 `code` 或不同请求体 |
| `OP_ID_REUSE` | 同一 `op_id` 被用于不同请求内容的写操作/动作 |
| `REQUEST_EXPIRED` | 重传的 `request_id` 已滑出设备最近 4 条响应缓存窗口 |
| `REVISION_CONFLICT` | `base_revision` 与当前 `revision` 不一致，或分页读取中途 `revision` 变化 |
| `BUSY` | 同一资源锁（`wifi` / `radar` / `restart`）已有活动任务，返回 `details.resource` 与 `job_id` |
| `RADAR_UNAVAILABLE` | 雷达 UART 离线或不可用，或 Wi-Fi 扫描无法启动：射频已禁用、连接状态机正在扫描/连接、漫游扫描/roam 进行中、先前的组件扫描仍挂起，或驱动拒绝（USB 主机连接仍保持在线） |
| `RADAR_TIMEOUT` | 雷达模组超时未响应，或已受理的 Wi-Fi 扫描 15 s 内没有完成通知 |
| `VERIFY_FAILED` | 参数写入后读回校验不一致 |
| `STORAGE_FAILED` | NVS 存储槽损坏或写入失败 |
| `RATE_LIMITED` | 超出请求限流（10 RPC/s）或持久化写令牌桶限制（含 `details.retry_after_ms`） |
| `INTERNAL_ERROR` | 固件内部未预期错误；客户端将操作标为“状态未知”并重读确认 |

---

## 4. 命令与事件完整注册表（19 个命令 + 5 个事件）

请求与响应在包头中使用相同的 `code`（`kind = 1` 为请求，`kind = 2` 为响应）；事件使用 `kind = 3`、`request_id = 0`。等级 `M` 表示首版强制实现，`C` 表示按声明能力实现。

### 4.1 请求/响应命令表（`0x0001` ～ `0x0053`）

| `code` (Hex / Dec) | 命令名称 | 等级 | 请求负载 (`request`) | 成功结果 (`result`) |
| :--- | :--- | :--- | :--- | :--- |
| `0x0001` (`1`) | `HELLO` | M | `{client:{name,version}, nonce, protocol:{major,minor_max}, max_payload}` | `{nonce, protocol:{major,minor}, boot_id, session_ttl_ms, limits, identity, cap_revision}` |
| `0x0002` (`2`) | `PING` | M | `{}` | `{uptime_ms}` |
| `0x0003` (`3`) | `SESSION_CLOSE` | M | `{}` | `{closed: true}`（应答排出后结束当前会话，不重启设备） |
| `0x0010` (`16`) | `DEVICE_INFO` | M | `{}` | `{device_id, boot_id, configured_model, dimension, firmware_version, git_sha, release_channel, build_profile, host_protocol, radar_identity}` |
| `0x0011` (`17`) | `CAPABILITIES_LIST` | M | `{cursor: null \| string}` | `{revision, items: CapabilityItem[], next_cursor}` |
| `0x0012` (`18`) | `STATUS_GET` | M | `{}` | `{uptime_ms, radar_link, last_radar_frame_ms, config_revision, config_storage, active_jobs, counters}` |
| `0x0020` (`32`) | `CONFIG_READ` | M | `{cursor: null \| string}` | `{revision, items: [{key, value}, ...], next_cursor}` |
| `0x0021` (`33`) | `CONFIG_VALIDATE` | M | `{base_revision, changes}` | `{valid: true, base_revision, restart_required: false}`（纯校验无副作用） |
| `0x0022` (`34`) | `CONFIG_COMMIT` | M | `{base_revision, op_id, changes}` | `{op_id, revision, persisted: true, restart_required: false}` |
| `0x0023` (`35`) | `COMMIT_STATUS` | M | `{op_id}` | `{found: boolean, revision: string \| null, current_revision: string}` |
| `0x0030` (`48`) | `SUBSCRIBE` | M | `{streams: [{id, max_rate_hz}], event_budget_bps}` | `{streams: [{id, max_rate_hz}], event_budget_bps}` |
| `0x0031` (`49`) | `UNSUBSCRIBE` | M | `{streams: [id, ...]}` | `{removed: [id, ...]}` |
| `0x0040` (`64`) | `ACTIONS_LIST` | M | `{cursor: null \| string}` | `{revision, items: ActionDescriptor[], next_cursor}` |
| `0x0041` (`65`) | `ACTION_START` | C | `{action_id, op_id, params, confirm: string \| null}` | `{job_id}` |
| `0x0042` (`66`) | `JOB_GET` | M | `{job_id}` 或 `{op_id}`（二选一互斥） | `Job` 对象（若按未命中 `op_id` 查询则返回 `state: "unknown"` 摘要） |
| `0x0050` (`80`) | `WIFI_STATUS` | M | `{}` | `{state, ssid, ip, rssi_dbm, last_error}`（**永不返回密码**） |
| `0x0051` (`81`) | `WIFI_SCAN` | M | `{op_id}` | `{job_id}` |
| `0x0052` (`82`) | `WIFI_PROVISION` | M | `{op_id, ssid, auth, password}` | `{job_id}` |
| `0x0053` (`83`) | `WIFI_SCAN_RESULTS` | M | `{job_id, cursor: null \| string}` | `{items: [{ssid, rssi_dbm, auth, hidden}], next_cursor, truncated}` |

### 4.2 异步事件表（`0x8001` ～ `0x8005`）

| `code` (Hex / Dec) | 事件名称 | 对应订阅流 `id` | 事件负载 (`event`) |
| :--- | :--- | :--- | :--- |
| `0x8001` (`32769`) | `TELEMETRY` | `telemetry` | `{source_seq, sent_ms, origin, presence, targets_quality, targets_ms, targets, metrics}` |
| `0x8002` (`32770`) | `STATUS_CHANGED` | `status` | 与 `STATUS_GET` 的 `result` 同构 |
| `0x8003` (`32771`) | `CONFIG_CHANGED` | `config` | `{revision, changed_keys, origin: "host"\|"ha"\|"web"\|"boot", op_id: string\|null}` |
| `0x8004` (`32772`) | `JOB_CHANGED` | `jobs` | `Job` 对象：`{job_id, op_id, action_id, state, stage, progress, started_ms, finished_ms, result, error}` |
| `0x8005` (`32773`) | `LOG` | `logs` | `{sample_ms, level: "error"\|"warn"\|"info"\|"debug", source, message, dropped_before}` |

---

## 5. 核心领域契约细则

### 5.1 身份、能力发现与分页一致性
- **分页规则（适用于 `CAPABILITIES_LIST`、`CONFIG_READ`、`ACTIONS_LIST`、`WIFI_SCAN_RESULTS`）**：
  - 首页请求 `cursor: null`；响应 `next_cursor: null` 表示最后一页；每页含包络总长 `<= 4096 B`，绝不截断单条记录。
  - 若在多页读取过程中底层 `revision` 发生变化，后续页请求返回 `REVISION_CONFLICT`，客户端从首页重读，禁止拼接新旧两页。
- **R60ABD1 基线能力、配置与动作契约（唯一真源：[`docs/protocol/fixtures/r60abd1-capabilities.json`](./fixtures/r60abd1-capabilities.json)）**：
  - **观测特征与指标（11 项）**：`presence`、`distance.cm`、`position.xy`（`max_targets: 1`, `target_id_stable: false`, `expected_interval_ms: 2000`, `stale_after_ms: 6000`，见 `DD-07` C2）、`diagnostics.local_z`、`speed.cm_s`（`supported: false`，见 `DD-06`）、`motion.state`、`body.movement`、`breath_rate`（`medical: false`）、`heart_rate`（`medical: false`）、`sleep.state`、`areas.occupancy`。
  - **R60ABD1 主机可写配置项（精确 8 项，与 `r60abd1-capabilities.json` 及 `simulator.js` `r60` 模型完全一致）**：
    1. `install.x_cm`（`number`, `-2000 .. 2000`, step `1`, `cm`, `domain: "host"`, `restart_required: false`）
    2. `install.y_cm`（`number`, `-2000 .. 2000`, step `1`, `cm`, `domain: "host"`, `restart_required: false`）
    3. `install.z_cm`（`number`, `50 .. 600`, step `1`, `cm`, `domain: "host"`, `restart_required: false`；按用户批准的 `DD-08` 选项 C2，已将 `r60abd1-capabilities.json`、`simulator.js` 与 `tests/common/r60abd1.yaml` `num_radar_z` 三端统一为 `50..600 cm`）
    4. `install.yaw_deg`（`number`, `-180 .. 180`, step `0.1`, `deg`, `domain: "host"`, `restart_required: false`）
    5. `install.pitch_deg`（`number`, `-90 .. 90`, step `0.5`, `deg`, `domain: "host"`, `restart_required: false`）
    6. `install.roll_deg`（`number`, `-90 .. 90`, step `0.5`, `deg`, `domain: "host"`, `restart_required: false`）
    7. `geometry.boundary_cm`（`array | null`, `unit: "cm"`, `schema_id: "polygon.xy.v1"`, `min_items: 3`, `max_items: 64`, `domain: "host"`, `restart_required: false`；`null` 表示禁用边界，非空时为 `3..64` 个 `[-2000, 2000] cm` 范围内的 `[x, y]` 顶点 2D 多边形，严格禁止坐标越界、相邻重复点、显式重复首尾闭合点、退化零面积、共线重叠或自交边，见 `DD-04`/`DD-05`）
    8. `areas.definitions`（`array`, `unit: "cm"`, `schema_id: "r60.areas.v1"`, `min_items: 0`, `max_items: 3`, `domain: "host"`, `restart_required: false`；元素为区域槽对象 `{slot, enabled, name, points_cm}`：`slot` 为整数 `0..2` 且数组内不得重复 `slot`，`enabled` 为布尔值，`name` 为 `<= 32` UTF-8 字节字符串，禁止未知附加字段；当 `enabled: true` 时 `points_cm` 必须为 `3..12` 个 `[-2000, 2000] cm` 范围内的 `[x, y]` 顶点合法非自交、非零面积 2D 多边形；当 `enabled: false` 时 `points_cm` 仅允许为空数组 `[]` 或合法的 `3..12` 顶点多边形）
  - **1D 型号专用配置项（不属于 R60ABD1）**：
    - `range.window_cm`（`schema_id: "range.window.v1"`, `{min: 0..600, max: 0..600}` 且 `min <= max`，禁止附加字段）仅适用于 1D 距离门型号（`simulator.js` 中的 `range1d` profile）。在 `r60abd1-capabilities.json` 中，`range.window_cm` 显式列于 `unsupported`（`["range.window_cm", "inject_mock_data", "raw_uart_tx", "speed.cm_s"]`），对 R60 实例提交 `range.window_cm` 将被拒绝（`UNSUPPORTED`）。
  - **R60ABD1 支持动作（精确 2 项）**：
    - `device.restart`（`confirm: true`, `verification: "none"`, `resource: "restart"`, `deadline_ms: 8000`）
    - `radar.reset_module`（`confirm: true`, `verification: "none"`, `resource: "radar"`, `deadline_ms: 2000`）

### 5.2 遥测质量语义、坐标变换与 G0 真机频率证据
- **质量枚举（`quality`）**：`valid | unknown | stale | invalid | unsupported`。
  - 当 `quality` 为 `unknown`、`unsupported` 或 `invalid` 时，对应 `value` **必须**为 `null`（由 `contract.js` `telemetryIssue` 强制校验）。
  - 1D 目标使用 `range_cm`，2D 目标使用 `local_cm: [x, y]` 与 `room_cm: [x, y]`，同一帧 `targets` 严禁混用 1D 与 2D 表示（`mixed_representation`）。
  - R60ABD1 不上报速度，`speed_cm_s` 固定为 `null`（`DD-06`）。
- **房间坐标变换与边界判定（`DD-11` 已收口）**：
  - 沿用现有固件与 `mmwave-card` 的旋转矩阵约定：`Rz(yaw) * Rx(pitch) * Ry(roll)`，`yaw = 0` 指向 `+Y`，正 `yaw` 为顺时针，`room_z = radar_z - world_z`。
  - 多边形射线法（Ray-Casting）边缘点归属与现有固件及卡片完全一致（如正方形 `[0..100, 0..100]` 上 `(50, 0)` 与 `(0, 0)` 判为 `inside`，`(150, 10)` 判为 `outside`），由 [`static/test/protocol-coordinates.test.js`](../../static/test/protocol-coordinates.test.js)、[`protocol/cpp/mwcp_host_test.cpp`](../../protocol/cpp/mwcp_host_test.cpp) (`test_transform`) 与工作区 `tests/unit/test_mwcp_sources.py` 共同锁定。
- **G0 真机上报频率实测与 `DD-07` C2 策略**：
  - 在 2 小时脱机长测（`7,198` 样本）中，`R60ABD1` 全类别合法控制字（`radar_frames`）平均速率为 **`4.84 Hz`（`4～8 帧/秒`）**，而 `0x80/0x05` 2D 坐标帧（`radar_targets`）严格为 **`0.50 Hz`（每 `2,000 ms` 1 帧）**，且固件 `publish_position_()` 存在 `1,000 ms` 节流。按用户拍板的 `DD-07` 选项 C2，`position.xy` 已写入真机实测值 `expected_interval_ms: 2000, stale_after_ms: 6000`；其余未在 G0 单独分桶的观察/生理指标项保持 `null`，由设备侧根据控制字状态机维护 `quality`。

### 5.3 配置事务、双槽持久化与最大 R60 配置证明（`C-13`）
- **原子验证与提交**：
  - `CONFIG_VALIDATE (0x0021)` 与 `CONFIG_COMMIT (0x0022)` 在 Schema（`mwcp-v1.schema.json` `x-configSchemas`）、契约层（`contract.js` `validateConfigChanges`）与模拟器/服务端执行一致校验：验证 `base_revision`、字段白名单、数值范围/步长、`range.window.v1`（`min <= max`）、`polygon.xy.v1`（`3..64` 顶点，`[-2000, 2000] cm`，无退化/自交）与 `r60.areas.v1`（`0..3` 槽，`slot 0..2` 无重复，无未知字段，多边形 `3..12` 顶点合法性）。`CONFIG_VALIDATE` 纯校验无副作用。
  - `CONFIG_COMMIT (0x0022)` 校验 `op_id` 幂等与 `base_revision` 后，原子更新快照、递增十进制字符串 `revision` 并发出 `CONFIG_CHANGED (0x8003)`。
  - **最大有效 R60 配置容量证明（`C-13`）**：包含全部 8 项 R60 主机配置项（含 `install.z_cm = 600`、几何合法的 64 顶点凸多边形 `geometry.boundary_cm` 及 3 个启用的 12 顶点凸多边形 `areas.definitions` 槽）的 `CONFIG_COMMIT` 帧，其 UTF-8 JSON 负载远低于 `MAX_PAYLOAD = 4096 B`；`4096 B` 边界精确通过，`4097 B` 精确以 `payload_too_large` 拒绝。

### 5.4 异步任务（Job）与 USB Wi-Fi 配网安全
- **动作安全与确认（`A-01`～`A-03`，G1-R1 / G1-R2 已加固）**：
  - `mwcp-v1.schema.json` 中 `ACTION_START (0x0041)` 的 `confirm` 字段类型严格限制为 `["string", "null"]`（布尔值 `true` / `false` 在 Schema 层直接拒绝）。对于 `confirm: true` 的动作，`confirm` 必须精确等于 `action_id` 字符串（如 `"device.restart"` 或 `"radar.reset_module"`），否则返回 `INVALID_ARGUMENT`。
  - **任务准入控制、预留不变量与完成记录保护（G1-R2-A 终版）**：
    1. **任务容量预留不变量**：设备任务存储严格有界，任何时刻必须满足：
       $$\text{保护期内已完成记录数} + \text{活动任务预留数} \le 8$$
       因每个已受理的活动任务在执行结束后必然转化为一条完成记录，为杜绝“先受理执行、完成时却因历史已满而不得不破坏 5 分钟保留期或超界扩容”，设备必须在受理新任务前为每一个活动任务预留将来的完成记录槽位。
    2. **严格无副作用的准入校验顺序**：
       - **第一步：幂等性复核**：若传入的 `op_id` 已在活动或完成表中存在，若请求负载摘要一致，则直接返回已有 `job_id`（不占用新槽位、不重复执行，即便是容量已满时幂等查询也照常返回）；若内容不一致，立即在任何副作用发生前返回 `OP_ID_REUSE`。
       - **第二步：资源互斥检查**：同一资源（`wifi` / `radar` / `restart`）若存在活动任务，返回 `BUSY`（携带 `details.resource` 与活动 `job_id`）。
       - **第三步：容量准入判定**：先回收 `elapsed >= 300,000 ms` 的已完成记录；若回收后 `(completedJobs.length + activeJobs.size) >= 8`（即剩余已完成记录均满足 `elapsed < 300,000 ms`，仍在保护期内），则新任务必须在产生任何副作用前立即拒绝，返回 `ERROR.BUSY`（`details: { reason: "capacity", retry_after_ms: 1000 }`）。被拒绝时**严禁**创建任务、占有资源锁、发出事件，亦严禁修改 Wi-Fi 状态（如 `state` 保持当前状态、`ssid` 不被覆盖）。
       - **第四步：状态变更与受理**：只有在前述检查全部通过后，设备才更新 Wi-Fi 状态、创建并加入活动任务表、锁定资源并返回新 `job_id`。
    3. **完成历史严格按完成顺序与 5 分钟（300,000 ms）最小保留窗口**：
       - 任务完成时记入 `finished_ms` 并移入完成历史。
       - 记 `elapsed = now_ms - finished_ms`（同一 boot 内单调时钟）。
       - **5 分钟保护期内严禁淘汰**：`elapsed < 300,000 ms` 的记录受绝对保护，绝不允许因新任务到达而提前驱逐。
       - **仅自然过期回收**：仅当 `elapsed >= 300,000 ms`（即达到或超过 `300,000 ms`；设备重启另行清空）时，才允许在准入或查询时被自然剔除，释放出空槽供新任务准入。精确边界：`299,999 ms` 仍受保护；`300,000 ms` 与 `300,001 ms` 均可回收。
       - **活动任务永不淘汰**：活动任务（`queued`/`running`）绝不参与历史驱逐，其资源锁持续有效直到执行完毕或重启。
    4. **`unknown` 语义界定**：达到或超过 5 分钟保留期（`elapsed >= 300,000 ms`）并被自然回收或跨重启丢失的任务，`JOB_GET` 查询返回 `state: "unknown"`。**客户端必须明确：`unknown` 表示设备端已无该任务的留存记录，绝不代表该任务从未被受理或从未执行过**；对于状态变为 `unknown` 的有副作用任务，严禁盲目自动重试。
  - **设备重启生命周期与有界易失内存（G1-R2-B）**：
    1. 设备重启模拟真实硬件行为：清空 RAM 中的所有活动任务、任务历史、会话、订阅和易失性资源锁，保证设备任务内存严格有界（任何情况下活动任务与已完成记录总数不超过 8 条，与“受保护完成记录 + 活动任务预留 <= 8”一致）；连续重启每次生成全新的随机 32 位十六进制 `boot_id`。
    2. 跨重启查询旧 `job_id` 或旧 `op_id` 统一返回 `state: "unknown"`，绝不泄漏旧 boot 的结果。
    3. 重启不影响 NVS 持久化状态：配置快照、`revision` 以及 `CONFIG_COMMIT` 最近 4 次原子提交历史严格跨重启保留。
    4. 普通的连接断开或会话过期不是重启，不得取消或丢失已受理的任务。
  - **未验证动作与重启语义（G1-R2）**：`verification: "none"` 的非重启动作（如 `radar.reset_module`）完成后，`Job.result` 固定返回 `{"verified": false, "verification": "none"}`（严禁返回 `verified: true`），UI 必须显示“已发送，未验证”，不能声称硬件验证成功；`device.restart` 在重启发生前保持 `queued` / `running`（严禁在重启前标为 `succeeded`），设备重启后 `boot_id` 变化、旧 `job_id` 查询返回 `state: "unknown"`，客户端凭新 `boot_id` 确认重启完成。
- **Wi-Fi 扫描与配网零密码回显（`W-01`～`W-04`）**：
  - `WIFI_SCAN (0x0051)` 启动带归属的扫描任务；完成后通过 `WIFI_SCAN_RESULTS (0x0053)` 分页读取，结果按 `rssi_dbm` 从强到弱排序，超出 64 条上限时截断并置 `truncated: true`。
  - 固件构建固定使用一个 ESPHome 补丁：对所有扫描启动串行化。连接/重试扫描通过后台令牌占用射频；组件扫描携带代际占用。任何扫描在进行中时都不能启动下一次扫描，每次完成恰好消费一个占用。只有组件完成携带代际；后台完成绝不归属给任何请求。没有该 API 的构建会让 `WIFI_SCAN` 立即返回 `UNSUPPORTED`；设备绝不猜测是哪个扫描完成。
  - 启动结果是即时的：射频已禁用、任何连接/重试/漫游扫描仍在进行、组件扫描仍挂起，或驱动拒绝 → `RADAR_UNAVAILABLE`（`Radar is unavailable`），射频空闲后可重试。不要求站点已连接：从未配网的设备可以扫描、列出 AP 并配网。已受理的扫描若被驱动报告失败，或声明有条目但无法取回，则以 `VERIFY_FAILED` 失败。已受理的扫描 15 s 内没有完成通知 → `RADAR_TIMEOUT`；迟到完成不能完成重试，只有该完成事件被处理后才重开归属。若完成事件丢失，归属保持关闭，后续扫描返回 `RADAR_UNAVAILABLE`，直到完成到达或设备重启；没有基于时间的释放。
  - 扫描任务挂起期间，`WIFI_SCAN_RESULTS` 返回 `BUSY`。扫描失败或超时后，同一分页返回 `items: []`（绝不返回上一轮扫描结果）；启动被拒时任务并未受理，该 `job_id` 的 `WIFI_SCAN_RESULTS` 返回 `INVALID_ARGUMENT`。
  - `WIFI_PROVISION (0x0052)` 校验 `auth`（`open` 要求空密码；`wpa2_psk` 要求 `8..63` UTF-8 字节口令或 64 位 hex PSK）。
  - 扫描结果的 `auth` 为 `open`、`wpa2_psk` 或 `unknown`。`unknown` 表示无线电没有给出认证套件，不能直接抄进 `WIFI_PROVISION`。
  - **铁律**：任何响应（`WIFI_STATUS`、`JOB_GET`）、事件（`JOB_CHANGED`、`LOG`）或错误详情中**绝不回显 `password`**。

---

## 6. 验证矩阵与本地可直接执行命令

以下所有命令均与仓库真实目录结构一致，可直接复制运行：

### 6.1 前端与协议 JS 单元测试、CDP 浏览器测试及生产构建
执行目录：`submodules/mmwave-component/static`

```bash
# Linux / WSL2 / macOS (bash)
cd submodules/mmwave-component/static
MWCP_GPP=g++ npm run test:unit
npm run test:browser
npm run build
```

```powershell
# Windows (PowerShell)
cd submodules/mmwave-component/static
$env:MWCP_GPP = "D:\Build\mingw64\bin\g++.exe"
npm run test:unit
npm run test:browser
npm run build
```
- 说明：`npm run test:unit` 运行全部单元测试套件（`static/test/*.test.js`，包含 R1～R5 全套回归用例，通过率 100%）；`npm run test:browser` 使用内置零依赖 Chrome DevTools Protocol (CDP) 驱动（`static/test/browser-harness.js` + `static/test/browser/protocol-browser.test.js`）在真实无头 Chrome/Chromium 中执行 2 项浏览器包测试。

### 6.2 C++14 宿主测试（含 `P-14` 100,000 次确定性变异模糊测试与 ASan/UBSan）
执行目录：`submodules/mmwave-component`

```bash
# Linux / WSL2 (bash) — 含 AddressSanitizer + UndefinedBehaviorSanitizer
cd submodules/mmwave-component

g++ -std=c++14 -O1 -g -fsanitize=address,undefined -fno-omit-frame-pointer -Wall -Wextra -Werror \
  -I protocol/cpp -I components/r60abd1 \
  protocol/cpp/mwcp_codec.cpp protocol/cpp/mwcp_json.cpp protocol/cpp/mwcp_host_test.cpp \
  -o /tmp/mwcp_host_test_asan && /tmp/mwcp_host_test_asan protocol/fixtures/protocol-vectors.json

g++ -std=c++14 -Wall -Wextra -Werror -static \
  -I docs/reviews/web-console/g0/components/mmwave_host -I protocol/cpp -I components/r60abd1 \
  protocol/cpp/g0_session_test.cpp protocol/cpp/mwcp_codec.cpp protocol/cpp/mwcp_json.cpp \
  -o /tmp/g0_session_test && /tmp/g0_session_test

g++ -std=c++14 -Wall -Wextra -Werror -static \
  -I components/r60abd1 -I docs/reviews/web-console/g0/components/mmwave_host \
  protocol/cpp/r60_probe_stats_test.cpp \
  -o /tmp/r60_probe_stats_test && /tmp/r60_probe_stats_test
```

```powershell
# Windows (PowerShell)
cd submodules/mmwave-component

D:\Build\mingw64\bin\g++.exe -std=c++14 -fno-exceptions -fno-rtti -static -Wall -Wextra -Werror `
  -I protocol/cpp -I components/r60abd1 `
  protocol/cpp/mwcp_codec.cpp protocol/cpp/mwcp_json.cpp protocol/cpp/mwcp_host_test.cpp `
  -o "$env:TEMP\mwcp_host_test.exe"
& "$env:TEMP\mwcp_host_test.exe" protocol/fixtures/protocol-vectors.json

D:\Build\mingw64\bin\g++.exe -std=c++14 -static -Wall -Wextra -Werror `
  -I docs/reviews/web-console/g0/components/mmwave_host -I protocol/cpp -I components/r60abd1 `
  protocol/cpp/g0_session_test.cpp protocol/cpp/mwcp_codec.cpp protocol/cpp/mwcp_json.cpp `
  -o "$env:TEMP\g0_session_test.exe"
& "$env:TEMP\g0_session_test.exe"

D:\Build\mingw64\bin\g++.exe -std=c++14 -static -Wall -Wextra -Werror `
  -I components/r60abd1 -I docs/reviews/web-console/g0/components/mmwave_host `
  protocol/cpp/r60_probe_stats_test.cpp `
  -o "$env:TEMP\r60_probe_stats_test.exe"
& "$env:TEMP\r60_probe_stats_test.exe"
```

### 6.3 Python 发布校验与黄金向量/卡片变换同源测试

```bash
# 1. 组件仓库内执行（submodules/mmwave-component）：20/20 passed
cd submodules/mmwave-component
python -m unittest discover -s tests -p test_releases.py -v

# 2. 工作区根目录执行（mmwave-workspace）：2/2 passed（校验黄金向量双端一致性及与 mmwave-card 变换一致性）
cd ../..
python -m unittest tests/unit/test_mwcp_sources.py -v
```
