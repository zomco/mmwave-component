# LD2451

Hi-Link HLK-LD2451 2D Multi-Target Tracking Radar — ESPHome component.

[中文文档 (Chinese)](./README_CN.md)

## Sensor Reference

> [!NOTE]
> The LD2451 is a multi-target radar that outputs data in **polar coordinates** (distance and angle).
> This ESPHome component will dynamically convert these polar coordinates into Cartesian local coordinates (`x` and `y`) and then feed them through the built-in 3D transformation matrix to provide absolute 3D room coordinates.
> It processes up to **3** concurrent targets and uses a default baud rate of **115200**.

### Global Entities

| YAML Key | Entity Type | Data Type | Value Range | Description |
|---|---|---|---|---|
| `presence` | `binary_sensor` | `bool` | `true`/`false` | True if at least 1 target is detected |
| `target_count` | `sensor` | `int` | `0` ~ `max` | Total number of detected targets reported by the DSP |
| `alarm` | `binary_sensor` | `bool` | `true`/`false` | True if the radar's built-in "approaching alarm" is active |

### Target Entity Blocks

For each target block (`target_1`, `target_2`, `target_3`):

| YAML Key | Entity Type | Data Type | Value Range | Unit | Description |
|---|---|---|---|---|---|
| `distance` | `sensor` | `float` | `0` ~ `100` | m | Target radial distance |
| `angle` | `sensor` | `float` | `-120` ~ `120` | ° | Target angle |
| `speed` | `sensor` | `float` | `-120` ~ `120` | km/h | Radial speed (positive = approaching, negative = leaving) |
| `snr` | `sensor` | `float` | `0` ~ `255` | — | Signal-to-Noise Ratio |
| `x` | `sensor` | `float` | — | cm | Calculated local X coordinate |
| `y` | `sensor` | `float` | — | cm | Calculated local Y coordinate |
| `room_x` | `sensor` | `float` | — | cm | Projected X coordinate in the global room frame |
| `room_y` | `sensor` | `float` | — | cm | Projected Y coordinate in the global room frame |
| `room_z` | `sensor` | `float` | — | cm | Projected Z height in the global room frame |
| `in_boundary` | `binary_sensor`| `bool` | `true`/`false` | — | True if target falls within `distance_min` & `distance_max` |

---

## Quick Start: Custom ESPHome Config Firmware

### Step 1: Add the External Component

```yaml
external_components:
  - source: github://zomco/mmwave-component
    components: [ld2451]
```

### Step 2: Configure UART

The LD2451 defaults to **115200** baud.

```yaml
uart:
  id: uart_ld2451
  tx_pin: GPIO21
  rx_pin: GPIO20
  baud_rate: 115200
```

### Step 3: Configure the LD2451 Component

```yaml
ld2451:
  id: radar
  uart_id: uart_ld2451

  # ── Calibration Parameters ────────────────────────────────
  radar_x: 0.0          
  radar_y: 0.0          
  radar_z: 240.0        
  yaw:   0.0            
  pitch: 0.0            
  roll:  0.0            

  # ── Global Sensors ────────────────────────────────────────
  presence:
    name: "Presence"
  target_count:
    name: "Target Count"

  # ── Target 1 Config ───────────────────────────────────────
  target_1:
    distance:
      name: "Target 1 Distance"
    angle:
      name: "Target 1 Angle"
    room_x:
      name: "Target 1 Room X"
    room_y:
      name: "Target 1 Room Y"
    room_z:
      name: "Target 1 Room Z"
```
