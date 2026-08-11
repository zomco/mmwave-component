# LD2411S 1-D 毫米波雷达

LD2411S 是一款 24GHz 的一维测距雷达模块，专为人体运动和微动检测设计。

## 特点
- **运动目标检测**: 最远 6.0 米
- **微动目标检测**: 最远 3.5 米
- **探测角度**: 水平面 45°，垂直面 20°
- **通信接口**: 串口 256000 bps

## ESPHome 配置示例

```yaml
uart:
  id: uart_ld2411s
  tx_pin: GPIO21
  rx_pin: GPIO20
  baud_rate: 256000

ld2411s:
  id: radar
  uart_id: uart_ld2411s
  distance:
    name: "距离"
  presence:
    name: "存在状态"
  moving_target:
    name: "运动目标"
  micro_target:
    name: "微动目标"
```
