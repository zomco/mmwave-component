# LD2412 ESPHome 组件

本组件将 HLK-LD2412 毫米波雷达传感器接入 ESPHome。LD2412 提供强大的人体存在检测与距离追踪功能（支持远达 9 米的运动与静止目标），具备 14 个距离门的高精度能量输出，并板载光敏传感器。

## 配置示例

在 ESPHome 配置文件中引入该组件并通过 UART 通信。

```yaml
external_components:
  - source:
      type: local
      path: components
    components: [ld2412]

uart:
  id: uart_ld2412
  tx_pin: GPIO21
  rx_pin: GPIO20
  baud_rate: 115200
  parity: NONE
  stop_bits: 1

ld2412:
  id: radar
  uart_id: uart_ld2412
  presence:
    name: "Presence"
  target_state:
    name: "Target State"
  moving_distance:
    name: "Moving Distance"
  moving_energy:
    name: "Moving Energy"
  stationary_distance:
    name: "Stationary Distance"
  stationary_energy:
    name: "Stationary Energy"
  light:
    name: "Light Sensor"
  
  # 配置 14 个距离门能量 (0 到 13)
  g0:
    gate_move_energy:
      name: "Gate 0 Move Energy"
    gate_still_energy:
      name: "Gate 0 Still Energy"
  g13:
    gate_move_energy:
      name: "Gate 13 Move Energy"
    gate_still_energy:
      name: "Gate 13 Still Energy"
```

## 支持的功能

- **存在检测**：区分运动与静止微动目标。
- **测距与能量**：可获取追踪目标的最远距离及能量信息。
- **14级距离门**：工程模式下支持14个不同距离区间的精细化能量值输出。
- **光感传感**：输出环境亮度相对值。
