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
| `presence` | `binary_sensor` | `bool` | `true`/`false` | True if at least one target is detected **and** inside the range gate (see `boundary_gates_presence`) |
| `target_count` | `sensor` | `int` | `0` ~ `max` | Total number of detected targets reported by the DSP |
| `alarm` | `binary_sensor` | `bool` | `true`/`false` | True if the radar's built-in "approaching alarm" is active |
| `target_frame` | `text_sensor` | `json` | — | All targets in one atomic 10 Hz frame, `{"v":1,"f":…,"ts":…,"t":[[x,y,speed],…]}` in cm and cm/s. This is what the fusion integration reads; the per-target entities can tear across a frame boundary, this cannot |

### Target Entity Blocks

For each target block (`target_1`, `target_2`, `target_3`):

| YAML Key | Entity Type | Data Type | Value Range | Unit | Description |
|---|---|---|---|---|---|
| `distance` | `sensor` | `float` | `0` ~ `10000` | cm | Target radial distance. The radar reports whole metres on the wire; the component converts before publishing, as the card and the fusion backend both expect |
| `angle` | `sensor` | `float` | `-120` ~ `120` | ° | Target angle |
| `speed` | `sensor` | `float` | `-120` ~ `120` | km/h | Radial speed (positive = approaching, negative = leaving) |
| `snr` | `sensor` | `float` | `0` ~ `255` | — | Signal-to-Noise Ratio |
| `x` | `sensor` | `float` | — | cm | Calculated local X coordinate |
| `y` | `sensor` | `float` | — | cm | Calculated local Y coordinate |
| `room_x` | `sensor` | `float` | — | cm | Projected X coordinate in the global room frame |
| `room_y` | `sensor` | `float` | — | cm | Projected Y coordinate in the global room frame |
| `room_z` | `sensor` | `float` | — | cm | Projected Z height in the global room frame |
| `in_boundary` | `binary_sensor`| `bool` | `true`/`false` | — | True if target falls within `distance_min` & `distance_max` |

### Configuration read-back entities

These publish what the radar **answered** to a query, not what was written to
it, so a rejected setting is visible rather than assumed. The component reads
all of them once at boot and again after every write.

| YAML Key | Entity Type | Unit | Protocol | Description |
|---|---|---|---|---|
| `firmware_version` | `text_sensor` | — | 1.2.7 | e.g. `V1.07.24072217` |
| `max_detection_distance` | `sensor` | m | 1.2.4 | Furthest range the radar reports targets from, 10–255 |
| `direction_filter` | `text_sensor` | — | 1.2.4 | `away` / `approaching` / `both` |
| `min_speed` | `sensor` | km/h | 1.2.4 | Slowest radial speed the radar will report, 0–120 |
| `no_target_delay` | `sensor` | s | 1.2.4 | How long the radar keeps reporting after the last target, 0–255 |
| `trigger_count` | `sensor` | — | 1.2.6 | Consecutive detections required before an alarm is raised, 1–10 |
| `snr_threshold` | `sensor` | — | 1.2.6 | SNR threshold level; 0 means the radar's own default (4), otherwise 3–8, higher being less sensitive |

## Writing to the radar

The radar's own settings survive a power cycle and are stored by the radar, so
the component reads them back rather than keeping a second copy that could
disagree. The four detection parameters travel in one command, as do the two
sensitivity parameters, so changing any one of a group re-sends the whole group
from the values the last query returned. Every write is followed by a re-read.

Commands are exposed as C++ methods; wire them to `number`, `select` and
`button` templates in YAML. See
[`tests/common/ld2451.yaml`](../../tests/common/ld2451.yaml) for the full set
the shipped firmware uses.

| Method | Protocol | Notes |
|---|---|---|
| `set_max_detection_distance(metres)` | 1.2.3 | 10–255 |
| `set_direction_filter(direction)` | 1.2.3 | 0 away only, 1 approaching only, 2 both |
| `set_min_speed(kmh)` | 1.2.3 | 0–120 |
| `set_no_target_delay(seconds)` | 1.2.3 | 0–255 |
| `set_trigger_count(count)` | 1.2.5 | 1–10 |
| `set_snr_threshold(level)` | 1.2.5 | 0 keeps the radar default, otherwise 3–8 |
| `query_detection_params()` / `query_sensitivity_params()` / `query_firmware_version()` | 1.2.4 / 1.2.6 / 1.2.7 | Refresh the read-back entities |
| `factory_reset()` | 1.2.9 | Applies after the module restarts |
| `restart_module()` | 1.2.10 | Restarts the radar, not the ESP |

Commands are queued and issued between one enable-config / end-config pair
(protocol 1.4.1) without blocking `loop()`, so a batch of queries costs one
configuration session rather than one each. The data stream stops for the
duration, which the presence watchdog is told to expect.

The serial baud rate command (1.2.8) is not exposed: changing it would strand
the module relative to the firmware's own UART configuration.

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

> [!NOTE]
> `polygon` filters in the room frame, on the ESP, and is independent of the
> radar's own `max_detection_distance`. Use the radar-side setting to limit what
> the module reports at all, and `polygon` to shape the region that counts once
> it has been transformed into room coordinates. An empty polygon disables the
> filter; fewer than three vertices is rejected at compile time.

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
