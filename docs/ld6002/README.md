# LD6002

Hi-Link HLK-LD6002 60 GHz Respiration and Heart Rate radar — ESPHome component.

[中文文档 (Chinese)](./README_CN.md)

## Sensor Reference

> [!NOTE]
> The LD6002 is an advanced 60GHz bio-radar. It outputs complex frames (`0x01` `ID` `LEN` `TYPE` `CKSUM` `DATA`) to provide detailed biological telemetry including respiration rate and heart rate, as well as native 3D tracked coordinates. Our component maps this data through the 3D coordinate transformation engine.

### Entity Types

| ESPHome Type | Home Assistant Type | Description |
|---|---|---|
| `binary_sensor` | `binary_sensor` | Boolean state (ON/OFF) |
| `sensor` | `sensor` | Numeric sensor |

### Bio-Sensing & Presence

| YAML Key | Entity Type | Data Type | Value Range | Unit | Update Frequency | Description |
|---|---|---|---|---|---|---|
| `presence` | `binary_sensor` | `bool` | `true` / `false` | — | On state change | Human presence detection (`device_class: presence`) |
| `distance` | `sensor` | `float` | `0` ~ `max_range` | cm | Continuous | Line-of-sight distance from radar to target (`device_class: distance`) |
| `respiration_rate` | `sensor` | `float` | `0` ~ `100` | bpm | Continuous | Detected respiration rate (breaths per minute) |
| `heart_rate` | `sensor` | `float` | `0` ~ `200` | bpm | Continuous | Detected heart rate (beats per minute) |

### Body Position — Room Coordinates (Post-Transform)

| YAML Key | Entity Type | Data Type | Value Range | Unit | Update Frequency | Description |
|---|---|---|---|---|---|---|
| `room_x` | `sensor` | `float` (1 decimal place) | Depends on calibration and room dimensions | cm | Continuous | Target X coordinate in room frame |
| `room_y` | `sensor` | `float` (1 decimal place) | Depends on calibration and room dimensions | cm | Continuous | Target Y coordinate in room frame |
| `room_z` | `sensor` | `float` (1 decimal place) | `0` ~ `radar_z` | cm | Continuous | Target height above floor (`radar_z − wz`) |
| `in_boundary` | `binary_sensor` | `bool` | `true` / `false` | — | Continuous | Whether the target's distance falls within `distance_min` to `distance_max` |

---

## Quick Start: Custom ESPHome Config Firmware

### Step 1: Add the External Component

```yaml
external_components:
  - source: github://zomco/mmwave-component
    components: [ld6002]
```

### Step 2: Configure UART

The LD6002 uses a default baud rate of **115200**, 8N1.

```yaml
uart:
  id: uart_ld6002
  tx_pin: GPIO21   # ESP32-C3 → LD6002 RX (cross-wired)
  rx_pin: GPIO20   # ESP32-C3 ← LD6002 TX
  baud_rate: 115200
  data_bits: 8
  parity: NONE
  stop_bits: 1
```

> [!IMPORTANT]
> GPIO pins vary by hardware design. TX/RX must be **cross-connected**: ESP TX → Radar RX, ESP RX → Radar TX.

### Step 3: Configure the LD6002 Component

#### Minimal Config (Bio-Sensing)

```yaml
ld6002:
  uart_id: uart_ld6002
  presence:
    name: "presence"
  distance:
    name: "distance"
  respiration_rate:
    name: "respiration_rate"
  heart_rate:
    name: "heart_rate"
```

#### Full Config (All Sensors + Calibration)

```yaml
ld6002:
  id: radar
  uart_id: uart_ld6002

  # ── Calibration Parameters ────────────────────────────────
  # Mounting position: origin at room's bottom-left corner, X right, Y forward (cm)
  radar_x: 0.0          # Radar X position
  radar_y: 0.0          # Radar Y position
  radar_z: 240.0        # Mounting height 240cm above floor

  # Mounting orientation (degrees)
  yaw:   0.0            # Horizontal heading offset, clockwise positive
  pitch: 0.0            # Pitch angle, forward tilt positive
  roll:  0.0            # Roll angle, right tilt positive

  # Distance range filter (cm, 0 = disabled)
  distance_min: 30.0
  distance_max: 600.0

  # ── Bio-Sensing ───────────────────────────────────────────
  presence:
    name: "presence"
  distance:
    name: "distance"
  respiration_rate:
    name: "respiration_rate"
  heart_rate:
    name: "heart_rate"

  # ── Room Coordinates ──────────────────────────────────────
  room_x:
    name: "room_x"
  room_y:
    name: "room_y"
  room_z:
    name: "room_z"
  in_boundary:
    name: "in_boundary"
```

### Step 4 (Optional): Runtime Calibration Adjustment

Add `number` entities to adjust calibration parameters live in Home Assistant without recompiling:

```yaml
number:
  - platform: template
    name: "yaw"
    min_value: -180
    max_value:  180
    step: 0.1
    set_action:
      lambda: "id(radar).set_yaw(x);"

  - platform: template
    name: "pitch"
    min_value: -90
    max_value:  90
    step: 0.5
    set_action:
      lambda: "id(radar).set_pitch(x);"

  - platform: template
    name: "roll"
    min_value: -90
    max_value:  90
    step: 0.5
    set_action:
      lambda: "id(radar).set_roll(x);"

  - platform: template
    name: "radar_x"
    min_value: -2000
    max_value:  2000
    step: 1
    set_action:
      lambda: "id(radar).set_radar_x(x);"

  - platform: template
    name: "radar_y"
    min_value: -2000
    max_value:  2000
    step: 1
    set_action:
      lambda: "id(radar).set_radar_y(x);"
```
