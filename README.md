# MMWave Radar ESPHome Component

[![CI](https://github.com/zomco/mmwave-component/actions/workflows/ci.yml/badge.svg)](https://github.com/zomco/mmwave-component/actions/workflows/ci.yml)
[![Publish](https://github.com/zomco/mmwave-component/actions/workflows/publish.yml/badge.svg)](https://github.com/zomco/mmwave-component/actions/workflows/publish.yml)

Custom [ESPHome](https://esphome.io/) external components for multiple millimeter-wave radar models, targeting **ESP32-C3** (with planned ESP32-S3 and other MCU support). Includes built-in **coordinate transformation** and **boundary filtering**.

> **🔌 Install firmware directly in your browser →** [**Open Installer**](https://zomco.github.io/mmwave-component/)
>
> No software required. Requires Chrome or Edge with Web Serial support.

---

## Features

### Coordinate Transformation

Converts raw radar-frame target positions into room-frame coordinates. Supports arbitrary mounting orientation via a full ZYX Tait-Bryan rotation (yaw, pitch, roll).

```yaml
r60abd1:
  radar_x: 2.5        # metres — room X
  radar_y: 3.0        # metres — room Y
  radar_z: 2.4        # metres — mounting height
  radar_yaw: 180.0    # degrees — horizontal pan
  radar_pitch: 0.0    # degrees — elevation tilt
  radar_roll: 0.0     # degrees — bank/roll
```

### Boundary Filtering

Discards targets outside a user-defined polygon (room-frame coordinates, post-transform).

```yaml
r60abd1:
  boundary:
    - { x: 0.0, y: 0.0 }
    - { x: 5.0, y: 0.0 }
    - { x: 5.0, y: 4.0 }
    - { x: 0.0, y: 4.0 }
```

---

## Radar Model Status

| Radar Model | Status       | Docs                             | Component                                | Notes                    |
|-------------|--------------|----------------------------------|------------------------------------------|--------------------------|
| R60ABD1     | ✅ Completed  | [`docs/r60abd1/`](docs/r60abd1/) | [`components/r60abd1/`](components/r60abd1/) | Reference implementation |

| Status       | Description |
|--------------|-------------|
| `Planned`    | Documentation staged; component not yet generated. |
| `Developing` | Component generated; undergoing on-hardware firmware tests. |
| `Testing`    | Firmware validated; undergoing Home Assistant integration tests. |
| `Completed`  | HA integration validated and stable. |
| `Paused`     | Blocked by an external condition (no hardware, no test environment, etc.). |

> This table is the authoritative source of truth, updated by the AI on every status change.

---

## Repository Structure

```
.
├── .github/workflows/
│   ├── ci.yml                 # PR check: compiles all tests/*.yaml
│   ├── publish.yml            # Builds firmware, uploads artifacts
│   └── publish-pages.yml      # Deploys GitHub Pages (separate from firmware build)
├── components/{radar_model}/  # ESPHome external component
├── docs/{radar_model}/        # Product docs + wiring images ({model}-*.png/jpg)
├── static/                    # GitHub Pages source (Jekyll)
│   ├── _config.yml
│   └── index.html             # ESP Web Tools install page
├── tests/{radar_model}.yaml   # Firmware config — one per radar model
└── README.md
```

---

## Usage

### 1. Add the external component

```yaml
external_components:
  - source: github://zomco/mmwave-component
    components: [r60abd1]
```

### 2. Configure UART and radar

```yaml
uart:
  tx_pin: GPIO21
  rx_pin: GPIO20
  baud_rate: 115200

r60abd1:
  radar_x: 2.5
  radar_y: 3.0
  radar_z: 2.4
  radar_yaw: 180.0
  radar_pitch: 0.0
  radar_roll: 0.0
  boundary:
    - { x: 0.0, y: 0.0 }
    - { x: 5.0, y: 0.0 }
    - { x: 5.0, y: 4.0 }
    - { x: 0.0, y: 4.0 }
  target_count:
    name: "Target Count"
  presence:
    name: "Presence"
```

---

## Adding a New Radar Model

1. Add `docs/{radar_model}/` with the product datasheet and communication protocol.
2. Optionally add wiring diagram images named `{radar_model}-*.png` (or `.jpg`) to the same folder — they will be automatically published to the install page.
3. Add a `Planned` row to the status table above.
4. Ask the AI to generate the component. It reads the docs, generates `components/{radar_model}/` and `tests/{radar_model}.yaml`, and updates the status to `Developing`.
5. Flash and test on hardware; report errors to the AI.
6. Once hardware tests pass → `Testing`. Once HA integration passes → `Completed`.

The CI and publish pipelines **auto-discover** `tests/*.yaml` — no workflow edits needed.

---

## CI/CD

| Workflow | Trigger | Responsibility |
|----------|---------|----------------|
| **CI** | PR / non-main push | Compiles all `tests/*.yaml` — validation only |
| **Publish** | Push to `main` / release | Builds firmware, uploads `firmware-*` artifacts |
| **Publish Pages** | After Publish / `static/**` or `docs/**` push | Assembles site, deploys to GitHub Pages |

Firmware build and Pages deployment are **intentionally separate**: a firmware build failure never breaks the live install site, and wiring diagram updates or install page changes deploy instantly without a full firmware rebuild.

### Enabling GitHub Pages

1. Go to **Settings → Pages → Source → GitHub Actions**.
2. Push to `main` to trigger the first deploy.

---

## Development Notes

- All components target **ESP32-C3** by default (`esp-idf` framework). ESP32-S3 and other MCUs are planned.
- The reference implementation is `components/r60abd1/`.
- All entities are declared in `__init__.py`; no separate `sensor.py` files.
- Coordinate transform uses a pre-computed ZYX rotation matrix (cached in `setup()`).
- Boundary filtering uses Ray Casting; supports convex and concave polygons.
- Protocol parsers are state-machine based and non-blocking.

---

## License

MIT