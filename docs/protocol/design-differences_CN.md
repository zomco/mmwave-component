# MWCP/1 待评审设计差异

状态：**待评审。** 这些都不是某一端私改线格式。协议未冻结。

| ID | 条款 | 证据 | 影响 | 最小建议 |
| --- | --- | --- | --- | --- |
| DD-01 | 安装器 `closed` 等于释放 | esp-web-tools 10.4.0 的 `connect.ts` 在 `closed` 回调里调用 `port.close()` 且没有 `await`。`install-dialog.ts` 在安装结束后重开端口并调用 `_initialize(true)`，除非 manifest 的 `new_install_improv_wait_time` 为 0。没有公共方法返回 close Promise。 | 控制台和安装器可能同时认为自己持有端口。 | WP-3 由应用调用 `navigator.serial.requestPort()` / `port.open()` / `await port.close()`。用户先关闭安装窗口，再点击连接。只有自己的 `await port.open()` 成功才算释放完成。manifest 设 `new_install_improv_wait_time: 0`，避免新固件卡在 Improv。不补丁 `navigator.serial`、shadow DOM 或 `node_modules`。 |
| DD-02 | ESPHome/ESP-IDF 未锁定 | CI 使用 `esphome/build-action@v7`，默认 `version: latest`。发布只在手动触发时要求精确版本，仓库里没有保存该版本。 | 不能把 G0 的驱动和日志结论钉死。 | 第一次获授权的构建记录精确 ESPHome 与 IDF 版本。现在不声称已锁定。 |
| DD-03 | 单一 USB 所有者 | 生产 `esphome-config/common/base.yaml` 把 logger 钉在 `USB_SERIAL_JTAG`。`tests/common/_device.yaml` 又在同一端口启用 `improv_serial`。多数测试 YAML 只有裸 `logger:`。未设置 `reboot_timeout`。 | 源码预示第二个 USB 消费者，以及离线后可能重启。未实测。 | host profile 移除 stock Improv Serial，停止纯文本日志，并把 Wi-Fi/API `reboot_timeout` 设为 `0s`。旧 profile 不得标成支持 MWCP。 |
| DD-04 | 多边形容量 | `g_polygon.max_restore_data_length` 为 254。实测 `-2000,-2000` 形式 21 个点为 251 字节，第 22 个放不下。同样 64 点的 JSON 提交为 1001 字节，低于 4096。 | 现有 globals 存不下草案上限。截断会违反协议。 | schema 在评审前保持最多 64 点。WP-2 必须用新的快照存储，不能沿用 254 字节 global。 |
| DD-05 | 多边形校验 | 固件会跳过坏点，也不检查自交。草案要求整笔拒绝。 | 如果 WP-2 只包一层现有解析器，HA 文本框和 MWCP 会不一致。 | 模拟器和 schema 按草案拒绝。本阶段不改固件。 |
| DD-06 | 速度占位 | `publish_target_frame_` 因为模组不上报速度而写 `0`。 | 把 0 导出就会编造测量。 | `speed.cm_s.supported` 为 false。遥测用 null。 |
| DD-07 | 间隔 | README 写位置/距离约每 2 秒。固件把位置发布节流到 1000 ms，并且 1000 ms 没有 UART 字节就清除 presence。草案的 2000/6000 没有实测。 | 用草案做过期判断可能把活数据标过期，或相反。 | fixture 在真机前使用 `expected_interval_ms: null`。 |
| DD-08 | 安装范围 | number 实体：x/y -2000..2000 步长 1，z 50..400 步长 1，yaw -180..180 步长 0.1，pitch/roll -90..90 步长 0.5。CONFIG_SCHEMA 允许任意正的 `radar_z`。 | 网页和 HA 可能接受不同高度。 | descriptor 采用 number 实体范围。放宽前需评审。 |
| DD-09 | CRC 合法但 JSON 非法 | 草案解析顺序在命令体错误之前到达 JSON，同时又说只有合法包络加错误命令体才返回错误。 | 一端可能回 `INVALID_ARGUMENT`，另一端只计 codec 错误。 | 两端都拒绝该帧且不执行。不产生应用响应。是否必须回响应，待评审。 |
| DD-10 | 字符串限制 | JSON Schema 的 `maxLength` 计字符。草案限制的是 UTF-8 字节。 | 中文 SSID 可能通过字符限制后超出字节限制。 | schema 注解 `x-maxUtf8Bytes`。不是线格式变更。 |
| DD-11 | 边缘点 | 现有射线法把正方形上的 `(50,0)` 和 `(0,0)` 判为内部，`(150,10)` 判为外部。 | 改谓词会移动 HA 和网页边界。 | 冻结当前结果。这里不“修正”。 |
| DD-12 | 控制台打开缓冲 | 草案写 16384。esp-web-tools 10.4.0 用 8192 打开。 | 两者可以不同，但必须写明。 | 不改安装器。将来控制台打开端口时按草案 16384，除非评审另定。 |
| DD-13 | 等价 JSON 键 | C++ 用原始键字节查重复。JS 用解码后的字符串。字面重复键两边一致。`\u0061` 与 `a` 可能不一致。 | 恶意重复键可能只被一端拒绝。 | 评审是否必须规范化转义。不得放宽任一侧。 |

| DD-13 | 等价 JSON 键 | 本轮已按解码后的键拒绝 `{"a":1,"\u0061":2}`。两端一致。 | 先前是真实分歧。 | 保持解码后比较。不是可选项。 |
| DD-14 | 带指数的整数值 | `9007199254740993e0` 和 `9007199254740993.0` 是超出 `±(2^53-1)` 的整数。`1.5` 这类非整数有限值仍允许。 | 用 `Number()` 会掩盖溢出。 | 这是现有安全整数规则的澄清，两端已实现。仅确认阅读方式，待评审。 |
| DD-15 | 未知响应字段 | 草案要求未知响应字段可忽略，未知请求字段必须拒绝。响应/事件 schema 现标记 `x-open-object`。请求仍关闭。 | 将来的 minor 字段不能弄坏客户端。 | 请确认这一阅读。请求仍然拒绝。 |

`AUTH_REQUIRED` 不是 v1 错误码。R60 的局部 Z 只作为 `diagnostics.local_z`，不是 3D 产品。`inject_mock_data` 不是 MWCP 动作。

## G0 准备阶段处置建议

这些不是已解决项。G0 硬件仍是 not_run。

| ID | 建议 | 本轮状态 |
| --- | --- | --- |
| DD-01 | 诊断页由用户点击连接，并以自己的 `port.open()` 成功作为交接证据。manifest 将来设 `new_install_improv_wait_time: 0`。不改 `node_modules`。 | 未在真机执行 |
| DD-02 | 第一次获授权的 `esphome compile` 记录精确 ESPHome/IDF。现在不声称已锁定。 | 本机没有 ESPHome，编译 not_run |
| DD-03 | host YAML 去掉 Improv，logger `baud_rate: 0`，Wi-Fi/API `reboot_timeout: 0s`。旧 profile 不标成 MWCP。 | 配置已写，未烧写、未测驱动 |
| DD-07 | 报告频率仍用 `expected_interval_ms: null`，直到真机计数。 | 未测 |
