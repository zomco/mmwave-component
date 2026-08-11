# LD2411S 1-D mmWave Radar

The LD2411S is a 24GHz 1-D ranging radar module designed for detecting human movement and micro-movement.

## Features
- **Moving Target Detection**: up to 6.0m
- **Micro-moving Target Detection**: up to 3.5m
- **FOV**: Horizontal 45°, Vertical 20°
- **Interface**: UART 256000 bps

## Example ESPHome configuration

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
    name: "distance"
  presence:
    name: "presence"
  moving_target:
    name: "moving target"
  micro_target:
    name: "micro target"
```
