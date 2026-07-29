# RD03E

Ai-Thinker RD03E 24 GHz FMCW precise ranging radar — ESPHome component.

[中文文档 (Chinese)](./README_CN.md)

## Sensor Reference

> [!NOTE]
> This table is cross-validated against the protocol documentation and ESPHome component source code.
> AI tools generating Home Assistant Cards should refer to this table for entity types, value ranges, and update frequencies.

> [!IMPORTANT]
> **Detection Coverage**: According to official specifications (§5.4 / §6), RD03E horizontal azimuth detection range is **±20°** (total **40° FOV**), and vertical elevation detection range is **±45°**. When configuring card visualizers or layout geometries, use `fovDegrees: 40`.

### Entity Types

| ESPHome Type | Home Assistant Type | Description |
|---|---|---|
| `binary_sensor` | `binary_sensor` | Boolean state (ON/OFF) |
| `sensor` | `sensor` | Numeric sensor |

### Presence & Motion

| YAML Key | Entity Type | Data Type | Values / States | Unit | Update Frequency | Description |
|---|---|---|---|---|---|---|
| `presence` | `binary_sensor` | `bool` | `true` / `false` | — | On state change | Human presence detection (`device_class: presence`) |
| `motion_state` | `sensor` | `int` | `0`=absent, `1`=motion, `2`=micro-motion | — | On state change | Motion state from radar |
| `distance` | `sensor` | `float` | `0` ~ `600` | cm | Continuous | Line-of-sight distance from radar to target (`device_class: distance`) |

### Body Position — Room Coordinates (Post-Transform)

| YAML Key | Entity Type | Data Type | Value Range | Unit | Update Frequency | Description |
|---|---|---|---|---|---|---|
| `room_x` | `sensor` | `float` (1 decimal place) | Depends on calibration and room dimensions | cm | Continuous (synced with distance) | Target X coordinate in room frame |
| `room_y` | `sensor` | `float` (1 decimal place) | Depends on calibration and room dimensions | cm | Continuous (synced with distance) | Target Y coordinate in room frame |
| `room_z` | `sensor` | `float` (1 decimal place) | `0` ~ `radar_z` | cm | Continuous (synced with distance) | Target height above floor (`radar_z − wz`) |
| `in_boundary` | `binary_sensor` | `bool` | `true` / `false` | — | Continuous (synced with distance) | Whether the target is inside the configured distance range (`distance_min` to `distance_max`) |

> [!IMPORTANT]
> The RD03E is a 1-D ranging radar. The `room_x/y/z` coordinates are derived by projecting the measured distance along the radar's local +X axis, and applying the calibration parameters (`radar_x/y/z`, `yaw/pitch/roll`).
> Boundary filtering uses a distance range gate (`distance_min`/`distance_max`) instead of a 2D polygon.

---

## Quick Start: Custom ESPHome Config Firmware

### Step 1: Add the External Component

```yaml
external_components:
  - source: github://zomco/mmwave-component
    components: [rd03e]
```

### Step 2: Configure UART

The RD03E uses a default baud rate of **256000**, 8N1.

```yaml
uart:
  id: uart_rd03e
  tx_pin: GPIO21   # ESP32-C3 → RD03E RX (cross-wired)
  rx_pin: GPIO20   # ESP32-C3 ← RD03E TX
  baud_rate: 256000
  data_bits: 8
  parity: NONE
  stop_bits: 1
```

> [!IMPORTANT]
> GPIO pins vary by hardware design. The ESP32-C3 defaults are GPIO20 (RX) / GPIO21 (TX) — adjust according to your actual PCB wiring.
> TX/RX must be **cross-connected**: ESP TX → Radar RX, ESP RX → Radar TX.

### Step 3: Configure the RD03E Component

#### Minimal Config (Presence & Distance)

```yaml
rd03e:
  uart_id: uart_rd03e
  presence:
    name: "presence"
  distance:
    name: "distance"
```

Only declare the sensors you need — undeclared sensors are not registered and consume no resources.

#### Full Config (All Sensors + Calibration)

```yaml
rd03e:
  id: radar
  uart_id: uart_rd03e

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

  # ── Presence & Motion ─────────────────────────────────────
  presence:
    name: "presence"
  motion_state:
    name: "motion_state"
  distance:
    name: "distance"

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

> [!NOTE]
> Parameters adjusted via `number` entities only take effect at runtime. They revert to the compile-time defaults in YAML after a device restart.
> Once you have finalized calibration values, write them back into the YAML config and recompile to persist them.

### Step 5: Compile & Flash

Click **Install** in the ESPHome Dashboard to compile and flash. The first flash requires a USB connection; subsequent updates can be done over-the-air (OTA).

### Calibration Parameters

| Parameter | Type | Unit | Default | Description |
|---|---|---|---|---|
| `radar_x` | `float` | cm | `0.0` | Radar X position in the room (origin at bottom-left corner, rightward positive) |
| `radar_y` | `float` | cm | `0.0` | Radar Y position in the room (forward positive) |
| `radar_z` | `float` | cm | `240.0` | Radar mounting height above floor |
| `yaw` | `float` | degrees | `0.0` | Yaw angle — horizontal offset of radar forward direction relative to room Y axis, clockwise positive (−180 ~ 180) |
| `pitch` | `float` | degrees | `0.0` | Pitch angle — forward tilt positive (−90 ~ 90) |
| `roll` | `float` | degrees | `0.0` | Roll angle — right tilt positive (−90 ~ 90) |
| `distance_min` | `float` | cm | `0.0` | Minimum target distance for boundary filter (0 = disabled) |
| `distance_max` | `float` | cm | `0.0` | Maximum target distance for boundary filter (0 = disabled) |
