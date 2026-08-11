# LD2412 ESPHome Component

This component integrates the HLK-LD2412 mmWave radar sensor into ESPHome. The LD2412 provides robust presence detection and distance tracking (moving/stationary targets up to 9m), with 14 distance gates for granular energy readings, along with an onboard light sensor.

## Configuration

Include the component and configure it over UART.

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
  
  # Configure 14 distance gates (0 to 13)
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

## Supported Features

- **Presence Detection**: Moving and micro-movement (stationary) target detection.
- **Distance & Energy**: Read max distance and target energy values.
- **14 Range Gates**: Engineering mode provides 14 separate distance gate energy values.
- **Light Sensor**: Output relative brightness reading.
