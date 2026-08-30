# LD2453

Hi-Link HLK-LD2453 2D Multi-Target Tracking Radar — ESPHome component.

[中文文档 (Chinese)](./README_CN.md)

## Sensor Reference

> [!NOTE]
> The LD2453 is a 2D millimeter-wave radar capable of tracking up to 3 simultaneous targets.
> This ESPHome component maps each target into a separate configuration block, and uses a built-in 3D transformation matrix to convert the local 2D X/Y coordinates into an absolute 3D room frame (pitch, yaw, and roll compensated).
> The radar operates at a high baud rate of **256000**.

> [!IMPORTANT]
> **The LD2453 has no radar-side detection limits.** Its protocol
> (`docs/ld2453/ld2453-通信协议.txt` §2.2) defines nine commands in total —
> enable/end config, single/multi-target tracking, query tracking mode, read
> firmware version, set baud rate, factory reset and restart. There is no
> distance, zone or region command, and the factory-default table lists only
> baud rate and tracking mode.
>
> So `distance_min` / `distance_max` / `polygon` here are **filters on the ESP**,
> not module settings. The radar keeps reporting targets outside them; what the
> filters change is `target_n_in_boundary`, and — while `boundary_gates_presence`
> is true — whether those targets count toward `presence`.

> [!WARNING]
> **Known hardware issue: the detection fan is rotated about 20° from the
> coordinates the module reports.** Observed on a bench unit, 2026-08-30.
>
> The datasheet (§6) specifies ±40° centred on the antenna plane normal. This
> unit detects roughly −60°…+20° in its own reported frame instead: a fan of
> the right width, rotated. It shows up as a "blind zone" on one side and
> detection ~20° beyond spec on the other — one rotation seen from both ends,
> not two faults.
>
> **This cannot be corrected with `yaw`.** Room bearing is `yaw + atan2(x, y)`,
> so `atan2(x, y)` — the bearing the module reports — is independent of `yaw`
> entirely. Changing `yaw` moves where the fan is *drawn*, never where the
> radar can *see*. A bench unit was tried at 135° and 180°; the offset was
> identical at both.
>
> What is not yet established is whether the reported bearings are accurate for
> targets the radar does see. If they are, the fault is the antenna pattern
> alone and coordinates stay trustworthy; if they carry the same ~20° bias,
> `yaw` would absorb it. The card's two-point yaw calibration distinguishes
> them: a solved yaw matching the mounting means the bearings are fine.
>
> Suspected to be vendor firmware in a recently released module rather than
> anything in this component — the transform is shared with ld2450/ld2452/
> ld2454 and is exercised by the same tests. Worth re-testing when Hi-Link
> publishes a firmware update.
>
> **Everything else about the model works.** Only the angular extent of the fan
> is affected: parsing, coordinates, boundary filtering, presence and the
> control entities are all unaffected, and a live LD2453 is still a valid
> target for feature work and automated tests. The one thing not to trust it
> for is judging where a radar can and cannot see.

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
