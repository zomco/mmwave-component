# R60ABD1

MicRadar R60ABD1 60 GHz mmWave breathing & sleep radar — ESPHome component.

[中文文档 (Chinese)](./README_CN.md)

![R60ABD1 Bottom](./r60abd1-底面.jpg)
![R60ABD1 Front](./r60abd1-正面.jpg)

## Sensor Reference

> [!NOTE]
> This table is cross-validated against the product datasheet V3.4, ESPHome component source code, and YAML configuration.
> AI tools generating Home Assistant Cards should refer to this table for entity types, value ranges, and update frequencies.

### Entity Types

| ESPHome Type    | Home Assistant Type | Description            |
| --------------- | ------------------- | ---------------------- |
| `binary_sensor` | `binary_sensor`     | Boolean state (ON/OFF) |
| `sensor`        | `sensor`            | Numeric sensor         |
| `text_sensor`   | `sensor` (string)   | Enumerated text state  |

### Presence & Motion

| YAML Key        | Entity Type     | Data Type | Values / States                        | Unit | Update Frequency                                           | Description                                                            |
| --------------- | --------------- | --------- | -------------------------------------- | ---- | ---------------------------------------------------------- | ---------------------------------------------------------------------- |
| `presence`      | `binary_sensor` | `bool`    | `true` / `false`                       | —    | On state change; absent→present ≤0.5s, present→absent ~40s | Human presence detection (`device_class: presence`)                    |
| `motion_state`  | `sensor`        | `int`     | `0`=absent, `1`=stationary, `2`=active | —    | On state change; stationary↔active switch ≤0.5s            | Motion state (protocol cmd `0x80/0x02`)                                |
| `body_movement` | `sensor`        | `int`     | `0` ~ `100`                            | —    | Every 1s                                                   | Body movement intensity                                                |
| `body_distance` | `sensor`        | `uint16`  | `0` ~ `65535`                          | cm   | Every 2s                                                   | Line-of-sight distance from radar to target (`device_class: distance`) |

### Body Position — Radar Local Coordinates

| YAML Key | Entity Type | Data Type                | Value Range         | Unit | Update Frequency | Description                                             |
| -------- | ----------- | ------------------------ | ------------------- | ---- | ---------------- | ------------------------------------------------------- |
| `raw_x`  | `sensor`    | `int16` (sign-magnitude) | `-32767` ~ `+32767` | cm   | Every 2s         | Radar-local X axis (right positive, left negative)      |
| `raw_y`  | `sensor`    | `int16` (sign-magnitude) | `-32767` ~ `+32767` | cm   | Every 2s         | Radar-local Y axis (forward positive)                   |
| `raw_z`  | `sensor`    | `int16` (sign-magnitude) | `-32767` ~ `+32767` | cm   | Every 2s         | Radar-local Z axis (outward from antenna face positive) |

> [!TIP]
> `raw_x/y/z` coordinate encoding: 2 bytes, bit15 = sign (0=positive, 1=negative), bit14–bit0 = 15-bit magnitude.
> Decoded internally by `decode_coord()`. These sensors are typically set to `internal: true` and used only for debugging.

### Body Position — Room Coordinates (Post-Transform)

| YAML Key      | Entity Type     | Data Type                 | Value Range                                | Unit | Update Frequency                       | Description                                                                                        |
| ------------- | --------------- | ------------------------- | ------------------------------------------ | ---- | -------------------------------------- | -------------------------------------------------------------------------------------------------- |
| `room_x`      | `sensor`        | `float` (1 decimal place) | Depends on calibration and room dimensions | cm   | Every 2s (synced with raw coordinates) | Target X coordinate in room frame                                                                  |
| `room_y`      | `sensor`        | `float` (1 decimal place) | Depends on calibration and room dimensions | cm   | Every 2s (synced with raw coordinates) | Target Y coordinate in room frame                                                                  |
| `room_z`      | `sensor`        | `float` (1 decimal place) | `0` ~ `radar_z` (typical 0–300)            | cm   | Every 2s (synced with raw coordinates) | Target height above floor (`radar_z − wz`)                                                         |
| `in_boundary` | `binary_sensor` | `bool`                    | `true` / `false`                           | —    | Every 2s (synced with raw coordinates) | Whether the target is inside the configured polygon boundary (always `true` when polygon is empty) |

> [!IMPORTANT]
> `room_x/y/z` and `in_boundary` are derived values computed on the ESP side, not direct radar outputs.
> Their values depend on the calibration parameters (`radar_x/y/z`, `yaw/pitch/roll`) and polygon boundary configured in YAML.

### Breathing

| YAML Key       | Entity Type   | Data Type | Values / States                            | Unit        | Update Frequency | Description                                                                                |
| -------------- | ------------- | --------- | ------------------------------------------ | ----------- | ---------------- | ------------------------------------------------------------------------------------------ |
| `breath_value` | `sensor`      | `uint8`   | `0` ~ `35`                                 | breaths/min | Every 3s         | Real-time breathing rate                                                                   |
| `breath_state` | `text_sensor` | `string`  | `"normal"` / `"high"` / `"low"` / `"none"` | —           | On state change  | Breathing status: `normal`=10–25/min, `high`=>25/min, `low`=<10/min, `none`=no one present |

### Heart Rate

| YAML Key     | Entity Type | Data Type | Value Range  | Unit | Update Frequency | Description          |
| ------------ | ----------- | --------- | ------------ | ---- | ---------------- | -------------------- |
| `heart_rate` | `sensor`    | `uint8`   | `60` ~ `120` | bpm  | Every 3s         | Real-time heart rate |

### Sleep Monitoring

| YAML Key               | Entity Type     | Data Type | Values / States                             | Unit | Update Frequency                   | Description                                                                           |
| ---------------------- | --------------- | --------- | ------------------------------------------- | ---- | ---------------------------------- | ------------------------------------------------------------------------------------- |
| `in_bed`               | `binary_sensor` | `bool`    | `true`=in bed / `false`=out of bed          | —    | On state change; in→out ~30s delay | Bed presence detection                                                                |
| `sleep_state`          | `text_sensor`   | `string`  | `"deep"` / `"light"` / `"awake"` / `"none"` | —    | Every 10min while in bed           | Sleep stage                                                                           |
| `awake_duration`       | `sensor`        | `uint16`  | `0` ~ `65535`                               | min  | Every 10min (with `sleep_state`)   | Cumulative awake duration                                                             |
| `light_sleep_duration` | `sensor`        | `uint16`  | `0` ~ `65535`                               | min  | Every 10min (with `sleep_state`)   | Cumulative light sleep duration                                                       |
| `deep_sleep_duration`  | `sensor`        | `uint16`  | `0` ~ `65535`                               | min  | Every 10min (with `sleep_state`)   | Cumulative deep sleep duration                                                        |
| `sleep_score`          | `sensor`        | `uint8`   | `0` ~ `100`                                 | —    | Once at end of sleep session       | Overall sleep quality score. Requires 4h ≤ sleep duration ≤ 12h; otherwise score is 0 |
| `sleep_quality`        | `text_sensor`   | `string`  | `"good"` / `"fair"` / `"poor"` / `"none"`   | —    | Once at end of sleep session       | Sleep quality rating: `good`=76–100, `fair`=61–75, `poor`=1–60, `none`=score is 0     |

### Update Frequency Summary

| Update Mode         | Sensors                                                                        |
| ------------------- | ------------------------------------------------------------------------------ |
| **On state change** | `presence`, `motion_state`, `breath_state`, `in_bed`, `sleep_quality`          |
| **Every 1s**        | `body_movement`                                                                |
| **Every 2s**        | `body_distance`, `raw_x/y/z`, `room_x/y/z`, `in_boundary`                      |
| **Every 3s**        | `breath_value`, `heart_rate`                                                   |
| **Every 10min**     | `sleep_state`, `awake_duration`, `light_sleep_duration`, `deep_sleep_duration` |
| **End of sleep**    | `sleep_score`, `sleep_quality`                                                 |

> [!WARNING]
> The `heart_rate` range is a hardware limitation of the radar module (60–120 bpm) and is not suitable for clinical-grade monitoring of patients with abnormal heart rates.
> `sleep_score` and `sleep_quality` only output valid values when the sleep duration condition is met (4h ≤ h ≤ 12h).

---

## Quick Start: Custom ESPHome Config Firmware

### Two Ways to Get Started

| Method                               | Best For                                                     | Description                                                                                                                            |
| ------------------------------------ | ------------------------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------- |
| **Browser flash (factory firmware)** | Quick setup, no customization needed                         | Visit the [Online Installer](https://zomco.github.io/mmwave-component/), flash via USB using Chrome/Edge — ready to use out of the box |
| **Custom YAML compilation**          | Adjusting calibration, selecting sensors, adding automations | Create a new config in ESPHome Dashboard, write YAML following the guide below, then compile and flash                                 |

### Firmware Config File Structure

The repository provides two example configs with the following relationship:

```
tests/
├── r60abd1-esp32c3.yaml            ← Base config (hardware + all sensors)
└── r60abd1-esp32c3.factory.yaml    ← Factory config (!include base + OTA/provisioning)
```

- **Base config** (`r60abd1-esp32c3.yaml`): Contains all hardware parameters and sensor definitions. **Use this as a template for customization.**
- **Factory config** (`r60abd1-esp32c3.factory.yaml`): Includes the base config via `!include` and adds BLE provisioning, HTTP OTA updates, etc. Built automatically by CI — **users typically do not need to modify this.**

### Step 1: Add the External Component

```yaml
external_components:
  - source: github://zomco/mmwave-component
    components: [r60abd1]
```

> [!TIP]
> For local development, use `source: { type: local, path: ../components }` to point to a local path.

### Step 2: Configure UART

The R60ABD1 uses a fixed baud rate of **115200**, 8N1. This cannot be changed.

```yaml
uart:
  id: uart_r60abd1
  tx_pin: GPIO21 # ESP32-C3 → R60ABD1 RXD (cross-wired)
  rx_pin: GPIO20 # ESP32-C3 ← R60ABD1 TXD
  baud_rate: 115200
  data_bits: 8
  parity: NONE
  stop_bits: 1
```

> [!IMPORTANT]
> GPIO pins vary by hardware design. The ESP32-C3 defaults are GPIO20 (RX) / GPIO21 (TX) — adjust according to your actual PCB wiring.
> TX/RX must be **cross-connected**: ESP TX → Radar RX, ESP RX → Radar TX.

### Step 3: Configure the R60ABD1 Component

#### Minimal Config (Presence Only)

```yaml
r60abd1:
  uart_id: uart_r60abd1
  presence:
    name: "presence"
```

Only declare the sensors you need — undeclared sensors are not registered and consume no resources.

#### Full Config (All Sensors + Calibration)

```yaml
r60abd1:
  id: radar
  uart_id: uart_r60abd1

  # ── Calibration Parameters ────────────────────────────────
  # Mounting position: origin at room's bottom-left corner, X right, Y forward (cm)
  radar_x: 200.0 # 200cm from left wall
  radar_y: 175.0 # 175cm from back wall
  radar_z: 220.0 # Mounting height 220cm above floor

  # Mounting orientation (degrees)
  yaw: 0.0 # Horizontal heading offset, clockwise positive
  pitch: 0.0 # Pitch angle, forward tilt positive
  roll: 0.0 # Roll angle, right tilt positive

  # Room boundary polygon (room-frame cm, < 3 vertices disables filtering)
  polygon:
    - { x: 0, y: 0 }
    - { x: 400, y: 0 }
    - { x: 400, y: 350 }
    - { x: 0, y: 350 }

  # ── Presence & Motion ─────────────────────────────────────
  presence:
    name: "presence"
  motion_state:
    name: "motion_state"
  body_movement:
    name: "body_movement"
  body_distance:
    name: "body_distance"

  # ── Raw Coordinates (debug only, remove or set internal: true for production) ─
  raw_x:
    name: "raw_x"
    internal: true
  raw_y:
    name: "raw_y"
    internal: true
  raw_z:
    name: "raw_z"
    internal: true

  # ── Room Coordinates ──────────────────────────────────────
  room_x:
    name: "room_x"
  room_y:
    name: "room_y"
  room_z:
    name: "room_z"
  in_boundary:
    name: "in_boundary"

  # ── Breathing ─────────────────────────────────────────────
  breath_value:
    name: "breath_value"
  breath_state:
    name: "breath_state"

  # ── Heart Rate ────────────────────────────────────────────
  heart_rate:
    name: "heart_rate"

  # ── Sleep ─────────────────────────────────────────────────
  in_bed:
    name: "in_bed"
  sleep_state:
    name: "sleep_state"
  awake_duration:
    name: "awake_duration"
  light_sleep_duration:
    name: "light_sleep_duration"
  deep_sleep_duration:
    name: "deep_sleep_duration"
  sleep_score:
    name: "sleep_score"
  sleep_quality:
    name: "sleep_quality"
```

### Step 4 (Optional): Runtime Calibration Adjustment

Add `number` entities to adjust calibration parameters live in Home Assistant without recompiling:

```yaml
number:
  - platform: template
    name: "yaw"
    min_value: -180
    max_value: 180
    step: 0.1
    set_action:
      lambda: "id(radar).set_yaw(x);"

  - platform: template
    name: "pitch"
    min_value: -90
    max_value: 90
    step: 0.5
    set_action:
      lambda: "id(radar).set_pitch(x);"

  - platform: template
    name: "roll"
    min_value: -90
    max_value: 90
    step: 0.5
    set_action:
      lambda: "id(radar).set_roll(x);"

  - platform: template
    name: "radar_x"
    min_value: -2000
    max_value: 2000
    step: 1
    set_action:
      lambda: "id(radar).set_radar_x(x);"

  - platform: template
    name: "radar_y"
    min_value: -2000
    max_value: 2000
    step: 1
    set_action:
      lambda: "id(radar).set_radar_y(x);"

  - platform: template
    name: "radar_z"
    min_value: 0
    max_value: 300
    step: 1
    set_action:
      lambda: "id(radar).set_radar_z(x);"
```

> [!NOTE]
> Parameters adjusted via `number` entities only take effect at runtime. They revert to the compile-time defaults in YAML after a device restart.
> Once you have finalized calibration values, write them back into the YAML config and recompile to persist them.

### Step 5: Compile & Flash

Click **Install** in the ESPHome Dashboard to compile and flash. The first flash requires a USB connection; subsequent updates can be done over-the-air (OTA).

```bash
# Command-line compilation (optional)
esphome compile your-config.yaml
esphome upload your-config.yaml
```

### Calibration Parameters

| Parameter | Type    | Unit    | Default      | Description                                                                                                       |
| --------- | ------- | ------- | ------------ | ----------------------------------------------------------------------------------------------------------------- |
| `radar_x` | `float` | cm      | `0.0`        | Radar X position in the room (origin at bottom-left corner, rightward positive)                                   |
| `radar_y` | `float` | cm      | `0.0`        | Radar Y position in the room (forward positive)                                                                   |
| `radar_z` | `float` | cm      | `220.0`      | Radar mounting height above floor                                                                                 |
| `yaw`     | `float` | degrees | `0.0`        | Yaw angle — horizontal offset of radar forward direction relative to room Y axis, clockwise positive (−180 ~ 180) |
| `pitch`   | `float` | degrees | `0.0`        | Pitch angle — forward tilt positive (−90 ~ 90)                                                                    |
| `roll`    | `float` | degrees | `0.0`        | Roll angle — right tilt positive (−90 ~ 90)                                                                       |
| `polygon` | `list`  | cm      | `[]` (empty) | Room boundary polygon vertices, each as `{ x, y }`. Boundary filtering is disabled with fewer than 3 vertices     |
