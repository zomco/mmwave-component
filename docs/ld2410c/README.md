# LD2410C ESPHome Component

This component integrates the **LD2410C** human presence radar into ESPHome.

[中文文档 (Chinese)](./README_CN.md)

The LD2410C is a 1D presence and motion tracking radar: eight range gates of
0.75 m (or 0.20 m), 6 m maximum, ±60° horizontal coverage, 256000 baud. By
applying a 3D coordinate transformation pipeline, it projects its linear
detection distance into a standard 3D room coordinate space, making it
compatible with other unified radar components.

## Sensor Reference

### Detection entities

| YAML Key | Entity Type | Unit | Description |
|---|---|---|---|
| `presence` | `binary_sensor` | — | A target is detected **and** inside the range gate (see `boundary_gates_presence`) |
| `target_state` | `sensor` | — | Raw state byte: 0 none, 1 moving, 2 stationary, 3 both, 4–6 noise-floor calibration in progress/succeeded/failed |
| `moving_distance` | `sensor` | cm | Distance of the moving target |
| `moving_energy` | `sensor` | — | Energy of the moving target, 0–100 |
| `stationary_distance` | `sensor` | cm | Distance of the stationary target |
| `stationary_energy` | `sensor` | — | Energy of the stationary target, 0–100 |
| `detection_distance` | `sensor` | cm | Distance the radar reports for the detection as a whole; this is what feeds the coordinate transform |
| `max_distance` | `sensor` | cm | Configured gate count times the gate size, so it follows the radar's own setting rather than a datasheet constant. Engineering mode only |

### Engineering-mode entities

The component enables engineering mode at boot (the setting is not retained
across a power cycle), which appends per-gate energies, the on-board
photodiode reading and the OUT pin state to every frame.

| YAML Key | Entity Type | Unit | Description |
|---|---|---|---|
| `g0` … `g8` → `gate_move_energy` | `sensor` | — | Moving energy for that range gate, 0–100 |
| `g0` … `g8` → `gate_still_energy` | `sensor` | — | Stationary energy for that range gate, 0–100 |
| `light` | `sensor` | — | Photodiode reading, 0–255. Not lux — the datasheet gives no conversion |
| `out_pin` | `binary_sensor` | — | What the module drives on its OUT pin. Differs from `presence` once light-assisted control is on |

### Spatial projection entities

| YAML Key | Entity Type | Unit | Description |
|---|---|---|---|
| `room_x` / `room_y` / `room_z` | `sensor` | cm | Detection distance projected into the room frame using the calibration below |
| `in_boundary` | `binary_sensor` | — | Whether the target falls between `distance_min` and `distance_max` |

### Configuration read-back entities

These publish what the radar **answered** to a query, not what was written to
it, so a rejected setting is visible rather than assumed. The component reads
all of them once at boot and again after every write.

| YAML Key | Entity Type | Unit | Protocol | Description |
|---|---|---|---|---|
| `firmware_version` | `text_sensor` | — | 2.2.8 | e.g. `V2.68.25070917` |
| `max_moving_gate` | `sensor` | — | 2.2.4 | Furthest gate used for moving targets, 2–8 |
| `max_still_gate` | `sensor` | — | 2.2.4 | Furthest gate used for stationary targets, 2–8 |
| `unmanned_duration` | `sensor` | s | 2.2.4 | How long the radar holds a detection after the last target |
| `distance_resolution` | `sensor` | m | 2.2.17 | Metres per gate: 0.75 or 0.20 |
| `gate_sensitivity` | `text_sensor` | — | 2.2.4 | `move a,b,…|still a,b,…` for all nine gates |
| `noise_floor_status` | `text_sensor` | — | 2.2.21 | `idle` / `running` / `finished` / `failed` |

## Configuration Variables

```yaml
ld2410c:
  id: my_radar
  uart_id: uart_bus

  # Calibration parameters
  radar_x: 0.0          # Radar X position in room (cm)
  radar_y: 0.0          # Radar Y position in room (cm)
  radar_z: 240.0        # Radar height from floor (cm)
  yaw: 0.0              # Pan angle (degrees, left/right)
  pitch: 0.0            # Tilt angle (degrees, up/down)
  roll: 0.0             # Roll angle (degrees)
  distance_min: 0.0     # Minimum valid distance boundary (cm)
  distance_max: 600.0   # Maximum valid distance boundary (cm)

  # Whether a target outside the range gate still counts as presence.
  # Defaults to true, matching every other model: out-of-boundary targets stay
  # visible on the distance sensors but do not turn presence on.
  boundary_gates_presence: true

  # Radar Output Entities
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
  detection_distance:
    name: "Detection Distance"
  max_distance:
    name: "Max Distance"

  # Engineering-mode extras
  light:
    name: "Light"
  out_pin:
    name: "OUT Pin"
  g0:
    gate_move_energy:
      name: "G0 Move Energy"
    gate_still_energy:
      name: "G0 Still Energy"
  # … g1 through g8

  # Spatial Projection Entities
  room_x:
    name: "Room X"
  room_y:
    name: "Room Y"
  room_z:
    name: "Room Z"
  in_boundary:
    name: "In Boundary"

  # Configuration read-back
  firmware_version:
    name: "Firmware Version"
  max_moving_gate:
    name: "Max Moving Gate"
  max_still_gate:
    name: "Max Still Gate"
  unmanned_duration:
    name: "Unmanned Duration"
  distance_resolution:
    name: "Distance Resolution"
  gate_sensitivity:
    name: "Gate Sensitivity"
  noise_floor_status:
    name: "Noise Floor Status"
```

## Writing to the radar

The radar's own settings survive a power cycle and are stored by the radar, so
the component reads them back rather than keeping a second copy that could
disagree. Every write is followed by a re-read.

Commands are exposed as C++ methods; wire them to `number`, `select` and
`button` templates in YAML. See
[`tests/common/ld2410c.yaml`](../../tests/common/ld2410c.yaml) for the full set
the shipped firmware uses.

| Method | Protocol | Notes |
|---|---|---|
| `set_max_moving_gate(gate)` | 2.2.3 | 2–8. Sent together with the still gate and the unmanned duration |
| `set_max_still_gate(gate)` | 2.2.3 | 2–8 |
| `set_unmanned_duration(seconds)` | 2.2.3 | 0–65535 |
| `set_gate_sensitivity(gate, move, still)` | 2.2.7 | 0–100 each; pass `ALL_GATES` (0xFFFF) to set every gate at once |
| `request_distance_resolution(index)` | 2.2.16 | 0 = 0.75 m, 1 = 0.20 m. **Takes effect only after the module restarts**, so the reported resolution stays on the old value until then |
| `set_light_control_mode(mode)` | 2.2.18 | 0 off, 1 condition met below the threshold, 2 above it |
| `set_light_threshold(value)` | 2.2.18 | 0–255 |
| `set_out_pin_level(level)` | 2.2.18 | 0 = OUT idles low, 1 = idles high |
| `start_noise_floor_calibration(seconds)` | 2.2.20 | Everyone must leave the detection area; the radar waits 10 s, then measures and sets every gate's sensitivity itself |
| `query_parameters()` / `query_firmware_version()` / `query_distance_resolution()` / `query_light_control()` / `query_noise_floor_status()` | 2.2.4 / 2.2.8 / 2.2.17 / 2.2.19 / 2.2.21 | Refresh the read-back entities |
| `factory_reset()` | 2.2.10 | Applies after the module restarts |
| `restart_module()` | 2.2.11 | Restarts the radar, not the ESP |

Commands are queued and issued between one enable-config / end-config pair
(protocol 2.4.1) without blocking `loop()`, so a batch of queries costs one
configuration session rather than one each. The data stream stops for the
duration, which the UART watchdog is told to expect.

## Not implemented

The protocol also defines serial baud rate (2.2.9), Bluetooth on/off, MAC
address and Bluetooth password (2.2.12–2.2.15). Changing the baud rate or
turning off Bluetooth would strand the module relative to the firmware's own
UART configuration, so neither is exposed.
