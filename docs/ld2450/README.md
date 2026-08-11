# LD2450

HLK-LD2450 24 GHz mmWave multi-target tracking radar — ESPHome component.

[中文文档 (Chinese)](./README_CN.md)

## Sensor Reference

> [!NOTE]
> This table is cross-validated against the product datasheet, ESPHome component source code, and YAML configuration.
> AI tools generating Home Assistant Cards should refer to this table for entity types, value ranges, and update frequencies.

### Entity Types

| ESPHome Type | Home Assistant Type | Description |
|---|---|---|
| `binary_sensor` | `binary_sensor` | Boolean state (ON/OFF) |
| `sensor` | `sensor` | Numeric sensor |

### Global Presence

| YAML Key | Entity Type | Data Type | Values / States | Unit | Update Frequency | Description |
|---|---|---|---|---|---|---|
| `presence` | `binary_sensor` | `bool` | `true` / `false` | — | On state change | Human presence detection (`device_class: presence`). True if any of the 3 targets is active. |

### Per-Target Tracking (Targets 1, 2, 3)

For each target `n` (1, 2, or 3), the following entities are available:

| YAML Key | Entity Type | Data Type | Value Range | Unit | Update Frequency | Description |
|---|---|---|---|---|---|---|
| `target_n_x` | `sensor` | `int16` | Depends on room | mm | Every 100ms (10Hz) | Radar-local X axis |
| `target_n_y` | `sensor` | `int16` | Depends on room | mm | Every 100ms (10Hz) | Radar-local Y axis (forward positive) |
| `target_n_speed` | `sensor` | `int16` | | cm/s | Every 100ms (10Hz) | Target moving speed |
| `target_n_resolution` | `sensor` | `uint16` | | mm | Every 100ms (10Hz) | Distance resolution |
| `target_n_distance` | `sensor` | `float` | Depends on room | cm | Every 100ms (10Hz) | Computed line-of-sight distance |
| `target_n_angle` | `sensor` | `float` | `-180` ~ `+180` | ° | Every 100ms (10Hz) | Computed angle |
| `target_n_room_x` | `sensor` | `float` | Depends on room | cm | Every 100ms (10Hz) | Target X coordinate in room frame |
| `target_n_room_y` | `sensor` | `float` | Depends on room | cm | Every 100ms (10Hz) | Target Y coordinate in room frame |
| `target_n_active` | `binary_sensor` | `bool` | `true` / `false` | — | On state change | Whether target `n` is currently being tracked |
| `target_n_in_boundary` | `binary_sensor` | `bool` | `true` / `false` | — | Every 100ms (10Hz) | Whether the target is inside the configured polygon boundary |

> [!IMPORTANT]
> `target_n_room_x/y` and `target_n_in_boundary` are derived values computed on the ESP side.
> Their values depend on the calibration parameters (`radar_x/y/z`, `yaw/pitch/roll`) and polygon boundary configured in YAML.

### Update Frequency Summary

| Update Mode | Sensors |
|---|---|
| **On state change** | `presence`, `target_n_active` |
| **Every 100ms (10Hz)** | All positional, speed, distance, angle, and boundary sensors |

---

## Quick Start: Custom ESPHome Config Firmware

### Firmware Config File Structure

The repository provides two example configs with the following relationship:

```
tests/
├── ld2450-esp32c3.yaml            ← Base config (hardware + all sensors)
└── ld2450-esp32c3.factory.yaml    ← Factory config (!include base + OTA/provisioning)
```

- **Base config** (`ld2450-esp32c3.yaml`): Contains all hardware parameters and sensor definitions. **Use this as a template for customization.**
- **Factory config** (`ld2450-esp32c3.factory.yaml`): Includes the base config via `!include` and adds BLE provisioning, HTTP OTA updates, etc. Built automatically by CI — **users typically do not need to modify this.**

### Step 1: Add the External Component

```yaml
external_components:
  - source: github://zomco/mmwave-component
    components: [ld2450]
```

### Step 2: Configure UART

The LD2450 uses a fixed baud rate of **256000**, 8N1. This cannot be changed.

```yaml
uart:
  id: uart_ld2450
  tx_pin: GPIO21   # ESP32-C3 → LD2450 RX (cross-wired)
  rx_pin: GPIO20   # ESP32-C3 ← LD2450 TX
  baud_rate: 256000
  data_bits: 8
  parity: NONE
  stop_bits: 1
```

> [!IMPORTANT]
> GPIO pins vary by hardware design. The ESP32-C3 defaults are GPIO20 (RX) / GPIO21 (TX) — adjust according to your actual PCB wiring.
> TX/RX must be **cross-connected**: ESP TX → Radar RX, ESP RX → Radar TX.

### Step 3: Configure the LD2450 Component

#### Minimal Config (Presence Only)

```yaml
ld2450:
  uart_id: uart_ld2450
  presence:
    name: "presence"
```

Only declare the sensors you need — undeclared sensors are not registered and consume no resources.

#### Full Config (All Sensors + Calibration)

```yaml
ld2450:
  id: radar
  uart_id: uart_ld2450

  # ── Global Presence ───────────────────────────────────────
  presence:
    name: "presence"

  # ── Target 1 ──────────────────────────────────────────────
  target_1_x:
    name: "target_1_x"
  target_1_y:
    name: "target_1_y"
  target_1_speed:
    name: "target_1_speed"
  target_1_distance:
    name: "target_1_distance"
  target_1_angle:
    name: "target_1_angle"
  target_1_room_x:
    name: "target_1_room_x"
  target_1_room_y:
    name: "target_1_room_y"
  target_1_active:
    name: "target_1_active"
  target_1_in_boundary:
    name: "target_1_in_boundary"

  # Add target_2_x, target_3_x, etc. as needed following the same pattern
```

### Step 4 (Optional): Runtime Calibration Adjustment & Commands

Add `number` entities to adjust calibration parameters live in Home Assistant without recompiling, and `button` entities to send commands to the radar:

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

button:
  - platform: template
    name: "set_multi_target"
    on_press:
      lambda: "id(radar).set_multi_target_mode();"

  - platform: template
    name: "set_single_target"
    on_press:
      lambda: "id(radar).set_single_target_mode();"

  - platform: template
    name: "restart_radar"
    on_press:
      lambda: "id(radar).restart_module();"

text:
  - platform: template
    name: "Polygon Config"
    id: text_polygon
    min_length: 0
    max_length: 255
    optimistic: true
    mode: text
    icon: mdi:vector-polygon
    set_action:
      - lambda: "id(g_polygon) = x;"
      - script.execute: apply_polygon
```

> [!NOTE]
> Parameters adjusted via `number` or `text` entities take effect immediately at runtime. They are also saved into the device's flash memory and will be automatically restored across reboots.

### Calibration Parameters

| Parameter | Type | Unit | Default | Description |
|---|---|---|---|---|
| `radar_x` | `float` | cm | `0.0` | Radar X position in the room (origin at bottom-left corner, rightward positive) |
| `radar_y` | `float` | cm | `0.0` | Radar Y position in the room (forward positive) |
| `radar_z` | `float` | cm | `150.0` | Radar mounting height above floor (recommended: 100-150cm) |
| `yaw` | `float` | degrees | `0.0` | Yaw angle — horizontal offset of radar forward direction relative to room Y axis, clockwise positive (−180 ~ 180) |
| `pitch` | `float` | degrees | `0.0` | Pitch angle — forward tilt positive (−90 ~ 90) |
| `roll` | `float` | degrees | `0.0` | Roll angle — right tilt positive (−90 ~ 90) |
| `polygon` | `list` | cm | `[]` (empty) | Room boundary polygon vertices, each as `{ x, y }`. Boundary filtering is disabled with fewer than 3 vertices |
| `boundary_gates_presence` | `bool` | — | `true` | When true, only targets **inside** the polygon count towards `presence`. This is what suppresses through-wall ghost targets. Set to `false` to have `presence` follow any tracked target. |
| `presence_timeout` | `time` | — | `5s` | How long `presence` stays on after the last in-boundary target disappears. |
| `zone_filter` | `map` | cm | unset | Radar-side zone filtering (protocol 2.2.12/2.2.13). See below. |

> [!NOTE]
> `yaw = 0` means the radar boresight points along room **+Y**; positive yaw rotates
> clockwise seen from above. This matches `mmwave-card` and the `mmwave_fusion`
> Home Assistant integration, so a radar calibrated here lines up in the fused view.

### Radar-side Zone Filtering (optional)

The LD2450 can discard targets in firmware, before they ever reach the UART. This is
complementary to `polygon`: use `zone_filter` to kill a known reflection source at the
radar, and `polygon` for the room outline.

```yaml
ld2450:
  zone_filter:
    type: exclude # disabled | include (detect only inside) | exclude (ignore inside)
    zones: # up to 3 rectangles, diagonal corners, in cm
      - { x1: -100.0, y1: 100.0, x2: 100.0, y2: 500.0 }
```

| Field | Meaning |
|---|---|
| `type: disabled` | Zone filtering off (factory default). |
| `type: include` | Only targets **inside** a configured rectangle are reported. |
| `type: exclude` | Targets inside a configured rectangle are **not** reported. |
| `zones` | Up to 3 rectangles given as two diagonal corners, in cm (sent to the radar as mm). |

> [!IMPORTANT]
> The zone configuration is stored in the radar and survives power-off. The component
> only writes it when `zone_filter` is present in the YAML, so it will not rewrite the
> radar's flash on every boot. It is read back and logged at startup either way.
