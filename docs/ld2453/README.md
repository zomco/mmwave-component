# LD2453

Hi-Link HLK-LD2453 2D Multi-Target Tracking Radar — ESPHome component.

[中文文档 (Chinese)](./README_CN.md)

## Sensor Reference

> [!NOTE]
> The LD2453 is a 2D millimeter-wave radar capable of tracking up to 3 simultaneous targets.
> This ESPHome component maps each target into a separate configuration block, and uses a built-in 3D transformation matrix to convert the local 2D X/Y coordinates into an absolute 3D room frame (pitch, yaw, and roll compensated).
> The radar operates at a high baud rate of **256000**.

### Target Entity Blocks

| YAML Key | Entity Type | Data Type | Value Range | Unit | Update Frequency | Description |
|---|---|---|---|---|---|---|
| `x` | `sensor` | `float` | `-max` ~ `max` | cm | Continuous | Target's local X coordinate relative to the radar face |
| `y` | `sensor` | `float` | `0` ~ `max` | cm | Continuous | Target's local Y coordinate relative to the radar face |
| `speed` | `sensor` | `float` | `-max` ~ `max` | cm/s | Continuous | Target's radial speed. Positive implies moving away. |
| `resolution` | `sensor` | `float` | `>= 0` | mm | Continuous | Distance resolution gate size from the radar DSP |
| `room_x` | `sensor` | `float` | — | cm | Continuous | Projected X coordinate in the global room frame |
| `room_y` | `sensor` | `float` | — | cm | Continuous | Projected Y coordinate in the global room frame |
| `room_z` | `sensor` | `float` | — | cm | Continuous | Projected Z height in the global room frame |
| `in_boundary` | `binary_sensor`| `bool` | `true`/`false` | — | Continuous | True if target's distance falls within `distance_min` & `distance_max` |

*A global `presence` binary_sensor is also provided, which reads `true` if any of the three targets are currently active.*

---

## Quick Start: Custom ESPHome Config Firmware

### Step 1: Add the External Component

```yaml
external_components:
  - source: github://zomco/mmwave-component
    components: [ld2453]
```

### Step 2: Configure UART

The LD2453 requires a baud rate of **256000**.

```yaml
uart:
  id: uart_ld2453
  tx_pin: GPIO21
  rx_pin: GPIO20
  baud_rate: 256000
```

### Step 3: Configure the LD2453 Component

```yaml
ld2453:
  id: radar
  uart_id: uart_ld2453

  # ── Calibration Parameters ────────────────────────────────
  # Mounting position: origin at room's bottom-left corner
  radar_x: 0.0          # Radar X position
  radar_y: 0.0          # Radar Y position
  radar_z: 240.0        # Mounting height 240cm above floor

  # Mounting orientation (degrees)
  yaw:   0.0            # Horizontal heading offset
  pitch: 0.0            # Pitch angle (e.g. tilted downwards)
  roll:  0.0            # Roll angle

  # ── Global Sensors ────────────────────────────────────────
  presence:
    name: "Presence"

  # ── Target 1 Config ───────────────────────────────────────
  target_1:
    x:
      name: "Target 1 X"
    y:
      name: "Target 1 Y"
    room_x:
      name: "Target 1 Room X"
    room_y:
      name: "Target 1 Room Y"
    room_z:
      name: "Target 1 Room Z"

  # ── Target 2 Config ───────────────────────────────────────
  target_2:
    x:
      name: "Target 2 X"
    # ... any other target sensors
```
