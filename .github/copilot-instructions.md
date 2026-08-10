# Copilot Instructions — Millimeter-Wave Radar ESPHome Components

## Project Overview

This repository contains custom ESPHome external components for multiple millimeter-wave radar models. Each component is developed independently under `components/{radar_model}/` and follows the [ESPHome starter-components](https://github.com/esphome/starter-components) template structure.

In addition to standard radar integration, every component implements two signature features:

- **Coordinate Transformation** — translates raw radar-frame target coordinates into room-frame coordinates based on the radar's physical installation parameters (position + full 3-D orientation).
- **Boundary Filtering** — discards targets outside a user-defined polygonal boundary, operating in room-frame coordinates (post-transform).

The **canonical reference implementation** is `components/r60abd1/`. All new components must structurally and stylistically follow it.

The **authoritative radar model status table** lives in `README.md`. The AI must update `README.md` whenever a model's status changes.

---

## Repository Layout

```
.
├── .github/
│   ├── copilot-instructions.md
│   └── workflows/
│       ├── ci.yml                     # PR: compiles all tests/*.yaml
│       ├── publish.yml                # Builds firmware, uploads artifacts
│       └── publish-pages.yml          # Deploys GitHub Pages (separate concern)
├── components/
│   ├── r60abd1/                        # ✅ Reference implementation
│   │   ├── __init__.py                 # CONFIG_SCHEMA, to_code, DEPENDENCIES,
│   │   │                               # and ALL entity declarations
│   │   ├── r60abd1.h
│   │   └── r60abd1.cpp
│   └── {radar_model}/
│       ├── __init__.py
│       ├── {radar_model}.h
│       └── {radar_model}.cpp
├── docs/
│   └── {radar_model}/
│       ├── <datasheet>.pdf            # Product documentation
│       ├── <protocol>.pdf             # Communication protocol
│       └── {radar_model}-*.{png|jpg}  # Wiring diagram images → published to Pages
├── static/
│   ├── _config.yml                    # Jekyll site config
│   └── index.html                     # GitHub Pages install site (ESP Web Tools)
├── tests/
│   ├── common/{radar_model}.yaml              # ← Shared radar core: uart, component,
│   │                                          #   globals, scripts, entity wiring.
│   │                                          #   Included by BOTH the base config here
│   │                                          #   and the workspace's esphome-config/.
│   ├── {radar_model}-{platform}.yaml          # Base config (CI validation + user adoption)
│   └── {radar_model}-{platform}.factory.yaml  # Factory firmware (CI + Publish + Pages flash)
├── GETTING-STARTED.md / GETTING-STARTED_CN.md # First-time setup for DIY users
├── DIY.md / DIY_CN.md                         # Advanced config, principles, limitations
└── README.md                                  # ← Radar model status table lives here
```

> **Note on `tests/common/`:** the radar definition is declared **once** per
> model there and included as a package. The per-platform file carries only
> board, networking and `external_components`. Never duplicate a radar
> definition into a platform file — the workspace includes the same core, and
> two copies drift apart silently.

> **Note on platform files:** All entities are declared in `__init__.py`. Do not create `sensor.py`, `binary_sensor.py`, or `number.py`.

---

## Status Table (maintained in `README.md`)

```
Planned → Developing → Testing → Completed
             ↕               ↕
           Paused          Paused
```

| Status       | Meaning |
|--------------|---------|
| `Planned`    | Documentation exists (or is awaited); component not yet generated. |
| `Developing` | Component generated; awaiting or undergoing on-hardware firmware tests. |
| `Testing`    | Firmware validated on hardware; undergoing Home Assistant integration tests. |
| `Completed`  | HA integration validated. No further changes unless explicitly requested. |
| `Paused`     | Blocked by an external condition (no hardware, no HA environment). AI makes no changes until maintainer explicitly resumes. |

**AI rule:** After any status change, update the table in `README.md` in the same response.

---

## Development Workflow

### Status: `Planned`

**Trigger:** Product documentation added to `docs/{radar_model}/`.

**AI responsibilities:**

1. Read **all** files in `docs/{radar_model}/` before writing any code — frame format, byte order, checksum, coordinate system, dimensionality.
2. Use `components/r60abd1/` as the canonical reference.
3. Determine output dimensionality:
   - **1-D** (range only): transform projects range along radar +X axis; boundary → `distance_min/distance_max`.
   - **2-D** (X, Y): full 2-D transform; polygon filter applies.
   - **3-D** (X, Y, Z): full 3-D transform; polygon filter on XY projection.
4. Generate `components/{radar_model}/__init__.py`, `.h`, `.cpp`, `tests/{radar_model}-{platform}.yaml`, and `tests/{radar_model}-{platform}.factory.yaml`.
5. If docs are **missing or incomplete**, report specifically what is missing and leave status as `Planned`.
6. On success, update `README.md` status to `Developing`.

**Failure conditions (stay `Planned`):** Missing protocol doc; ambiguous frame format; undocumented coordinate axes.

---

### Status: `Developing`

Diagnose and fix firmware errors by tracing the parser against `docs/{radar_model}/`. Update status to `Testing` on maintainer confirmation.

### Status: `Testing`

Fix HA integration issues. Update status to `Completed` on maintainer confirmation.

### Status: `Paused`

Make no changes. Wait for maintainer to explicitly resume.

### Status: `Completed`

No AI-initiated changes unless explicitly requested.

---

## CI/CD Pipeline

The three workflow files have distinct, non-overlapping responsibilities.

### `ci.yml` — PR Validation

- **Trigger:** Push to non-main branches; pull requests.
- **What it does:** Compiles **all** `tests/*.yaml` files (both base and factory configs) in parallel using `esphome/build-action@v6`. Fails if any config does not compile.
- **Does not** build artifacts or deploy anything.

### `publish.yml` — Firmware Build

- **Trigger:** Push to `main`; new GitHub release; `workflow_dispatch`.
- **What it does:**
  1. Auto-discovers only `tests/*.factory.yaml` files.
  2. Stamps the release tag (or `"dev"`) into each factory yaml's `version` field.
  3. Builds each with `esphome/build-action@v6` (`complete-manifest: true`).
  4. Uploads one artifact per model: `firmware-{name}` (e.g. `firmware-r60abd1-ESP32-C3`).
- **Does not** touch GitHub Pages. Base `*.yaml` files are not built here — they are for user adoption via `dashboard_import`, compiled only by CI.

### `publish-pages.yml` — GitHub Pages Deployment

- **Trigger:** Completion of `publish.yml` on `main`; push to `static/**` or `docs/**`; `workflow_dispatch`.
- **What it does:**
  1. Resolves which `publish.yml` run to pull firmware artifacts from.
  2. Downloads all `firmware-*` artifacts.
  3. Builds the Jekyll site from `static/` → `_site/`.
  4. Copies firmware files and wiring images into `_site/`.
  5. Generates `_site/models.json` (name, version, chip family, manifest path, wiring image paths).
  6. Deploys `_site/` to GitHub Pages.
- **Triggered independently** from `publish.yml`: static content (wiring images, install page) can be redeployed without rebuilding firmware.

**Wiring images** are discovered automatically: any file matching `docs/{radar_model}/{radar_model}-*.{png|jpg|jpeg}` is copied to `_site/images/{radar_model}/` and listed in `models.json.wiring_images`. The install page displays them when a user opens the Wiring Guide for a model.

### Enabling GitHub Pages

1. **Settings → Pages → Source → GitHub Actions.**
2. Push to `main` or run `publish.yml` → `publish-pages.yml` triggers automatically.

---

## Firmware Configuration: `tests/` File Pair

Each radar model + platform combination is represented by **two files** in `tests/`, following the ESPHome project template convention:

| File | Purpose | Built by |
|------|---------|----------|
| `{radar_model}-{platform}.yaml` | Base config (hardware, UART, component, WiFi). No `esphome.project`. Used for OTA adoption via `dashboard_import`. | `ci.yml` only |
| `{radar_model}-{platform}.factory.yaml` | Factory firmware: `!include` base + `esphome.project` + `dashboard_import` + provisioning. Distributed via ESP Web Tools. | `ci.yml` + `publish.yml` |

`{platform}` is lowercase, matching the ESPHome board family: `esp32c3`, `esp32s3`, `esp32`, etc.

Adding a new file pair is the only step needed to include a new model/platform in CI and firmware builds — no workflow edits required.

### Base config: `tests/{radar_model}-{platform}.yaml`

```yaml
substitutions:
  name: "{radar_model}"              # must be lowercase, no spaces
  friendly_name: "{Radar Model}"

esphome:
  name: "${name}"
  friendly_name: "${friendly_name}"
  name_add_mac_suffix: true          # prevents hostname collision on shared networks
  min_version: "2024.6.0"

# Adapt board and framework for each platform
esp32:
  board: esp32-c3-devkitm-1         # esp32-c3-devkitm-1 | esp32s3box | etc.
  framework:
    type: esp-idf                    # always esp-idf, never arduino

external_components:
  - source:
      type: local
      path: ../components            # relative to tests/
    components: ["{radar_model}"]

logger:
api:
  encryption:
    key: !secret api_encryption_key
ota:
  - platform: esphome
    password: !secret ota_password

wifi:
  ssid: !secret wifi_ssid
  password: !secret wifi_password
  ap:
    ssid: "${friendly_name} Fallback"

captive_portal:

# The radar itself — uart, component config, globals, scripts and entity
# wiring — lives in the shared core, not here.
packages:
  radar: !include common/{radar_model}.yaml
```

**Rules for base config:**
- `esphome.name` must equal the radar model identifier (e.g. `r60abd1`). The build-action uses this as the firmware name prefix.
- No `esphome.project` block — that belongs in the factory file only.
- `esp32.framework.type` must be `esp-idf`.
- `external_components.source.path` must be `../components`.
- The radar is pulled in via `packages: radar: !include common/{radar_model}.yaml`. Do not inline `uart:` or the `{radar_model}:` block here.

### Shared radar core: `tests/common/{radar_model}.yaml`

```yaml
uart:
  tx_pin: GPIO21                     # ESP32-C3 → radar RX (crossed)
  rx_pin: GPIO20                     # ESP32-C3 ← radar TX
  baud_rate: 115200                  # must match the radar protocol document exactly

{radar_model}:
  id: radar
  radar_x: 0.0
  radar_y: 0.0
  radar_z: 2.4
  radar_yaw: 0.0
  radar_pitch: 0.0
  radar_roll: 0.0
```

**Rules for the shared core:**
- Carries **no** `esp32:`, `wifi:`, `api:` or `external_components:` block. Each consumer supplies its own, and two declarations of the same key collide with no way to drop just one.
- `uart.baud_rate` must match the radar's protocol document exactly. Current values range from 9600 (LD2452) to 1382400 (LD6002) — never assume 115200.
- GPIO defaults: `GPIO20` (RX), `GPIO21` (TX). LD2410 is the sole exception at `GPIO5`/`GPIO4`. Add `# TODO` if hardware is not yet confirmed.
- Calibration restored from `globals` in `esphome.on_boot` so it survives a reboot.
- Any polygon parsing must use `strtof` with endptr validation, never `std::stof`. The esp-idf build disables C++ exceptions, so `std::stof` on malformed input calls `std::terminate()` — one typo in the HA text box reboots the radar.

### Factory config: `tests/{radar_model}-{platform}.factory.yaml`

```yaml
# Factory firmware — built by publish.yml, distributed via ESP Web Tools.

core: !include {radar_model}-{platform}.yaml   # all hardware config lives here

esphome:
  project:
    name: "mmwave-radar.{radar_model}"
    version: "dev"   # replaced by release tag in publish.yml; do not change manually

# Required by both http_request OTA and the update platform below.
http_request:

# HTTP-based OTA: allows the device to pull firmware from GitHub Pages
# autonomously. Works alongside the ESPHome OTA in the base config.
ota:
  - platform: http_request

# "Firmware" update entity in Home Assistant.
# Polls the GitHub Pages manifest; shows an update card when a new release
# is available. Users can update with one click — no ESPHome dashboard needed.
# URL pattern: https://{owner}.github.io/{repo}/{esphome.name}-{chipFamily}/manifest.json
update:
  - platform: http_request
    name: Firmware
    source: "https://{owner}.github.io/{repo}/{radar_model}-{chipFamily}/manifest.json"

# Allows importing the device into the ESPHome/HA dashboard after first flash.
# Points to the base yaml (without factory extras).
dashboard_import:
  package_import_url: "github://{owner}/{repo}/tests/{radar_model}-{platform}.yaml@main"
  import_full_config: true

# Wi-Fi provisioning over USB serial
improv_serial:

# Wi-Fi provisioning over Bluetooth LE (ESP32 family only)
esp32_improv:
  authorizer: none
```

**Rules for factory config:**
- `core: !include {radar_model}-{platform}.yaml` is the only hardware content. Never duplicate hardware config here.
- `esphome.project.name` follows the pattern `"mmwave-radar.{radar_model}"`.
- `esphome.project.version` must be the literal string `"dev"` — `publish.yml` replaces it with the release tag at build time.
- `http_request:` must appear before `ota` and `update` blocks that depend on it.
- `update.source` URL must match the path where `publish-pages.yml` places the manifest: `https://{owner}.github.io/{repo}/{esphome.name}-{chipFamily}/manifest.json`. Replace `{owner}`, `{repo}`, and use the exact chip-family string produced by `build-action` (e.g. `ESP32-C3`, `ESP32-S3`).
- `dashboard_import.package_import_url` must point to the base yaml in the repository.
- `improv_serial` and `esp32_improv` are always included for ESP32-family targets.

### Firmware artifact naming

`esphome/build-action@v6` names the build output `{esphome.name}-{chipFamily}` where `chipFamily` comes from the compiled board spec (e.g., `ESP32-C3`, `ESP32-S3`). For example:

| Factory YAML | `esphome.name` | Build artifact name |
|---|---|---|
| `r60abd1-esp32c3.factory.yaml` | `r60abd1` | `r60abd1-ESP32-C3` |
| `r60abd1-esp32s3.factory.yaml` | `r60abd1` | `r60abd1-ESP32-S3` |

This name is used for the uploaded artifact (`firmware-r60abd1-ESP32-C3`), the `_site/` subdirectory, and the `id` field in `models.json`. `publish-pages.yml` derives the radar model name for wiring image lookup by stripping the chip-family suffix: `r60abd1-ESP32-C3` → `r60abd1`.

---

## Mandatory Feature Specifications

### 1. Coordinate Transformation

**Room-frame convention (normative).** `R = Rz(yaw) · Rx(pitch) · Ry(roll)`.

- `yaw = 0` aims the radar boresight along room **+Y**. Positive yaw turns **clockwise** seen from above (toward +X).
- `pitch` tilts about the intermediate X-axis (nose up/down).
- `roll` turns about the radar's **own boresight** (local +Y).
- Room Z is measured **up from the floor**, so the translation is `room_z = radar_z − world_z`.

**This convention is implemented three times, in three separate repositories, and
changing one alone silently mirrors or rotates everyone's coordinates without
any test failing in that repo.** The three implementations are:

| Repository | File |
| --- | --- |
| mmwave-component (here) | `components/{model}/{model}_transform.h` — one per model, 16 of them |
| [mmwave-card](https://github.com/zomco/mmwave-card) | `src/utils/transform.ts` |
| [mmwave-fusion](https://github.com/zomco/mmwave-fusion) | `custom_components/mmwave_fusion/fusion.py` — `transform_point()` |

`components/r60abd1/` is the reference implementation. Any change to the
convention requires updating all three **in the same change set**.

The cross-check that catches a divergence lives in the development workspace
([mmwave-workspace](https://github.com/zomco/mmwave-workspace)), which carries
all three as submodules:

```bash
python -m unittest tests.unit.test_rotation_convention -v
```

It extracts the TypeScript expressions from the card's source and evaluates
them against `fusion.py`, so it fails if any of the three drift apart. A change
made in this repository alone will pass this repository's CI and fail there.

All six parameters exposed in CONFIG_SCHEMA for every model. **Lengths are centimetres**, matching the YAML configs and the published `room_*` sensors.

| Parameter     | Type    | Unit    | Default | Description                                                |
|---------------|---------|---------|---------|------------------------------------------------------------|
| `radar_x`     | `float` | cm      | `0.0`   | Radar origin along the room X-axis.                        |
| `radar_y`     | `float` | cm      | `0.0`   | Radar origin along the room Y-axis.                        |
| `radar_z`     | `float` | cm      | `0.0`   | Radar mounting height above the floor.                     |
| `radar_yaw`   | `float` | degrees | `0.0`   | Rotation about room Z. 0 = boresight along +Y, CW positive.|
| `radar_pitch` | `float` | degrees | `0.0`   | Rotation about the intermediate X-axis (elevation tilt).   |
| `radar_roll`  | `float` | degrees | `0.0`   | Rotation about the radar's own boresight (local +Y).       |

#### C++ rotation matrix (pre-computed in `setup()`)

```cpp
void precompute_rotation_matrix() {
  const float cy = cosf(yaw_rad_),   sy = sinf(yaw_rad_);
  const float cp = cosf(pitch_rad_), sp = sinf(pitch_rad_);
  const float cr = cosf(roll_rad_),  sr = sinf(roll_rad_);
  // R = Rz(yaw) * Rx(pitch) * Ry(roll)
  r_[0][0]= cy*cr + sy*sp*sr;  r_[0][1]= sy*cp;  r_[0][2]= -cy*sr + sy*sp*cr;
  r_[1][0]=-sy*cr + cy*sp*sr;  r_[1][1]= cy*cp;  r_[1][2]=  sy*sr + cy*sp*cr;
  r_[2][0]= cp*sr;             r_[2][1]=-sp;     r_[2][2]=  cp*cr;
}

void transform_point(float lx, float ly, float lz,
                     float &rx, float &ry, float &rz) const {
  rx = r_[0][0]*lx + r_[0][1]*ly + r_[0][2]*lz + radar_x_;
  ry = r_[1][0]*lx + r_[1][1]*ly + r_[1][2]*lz + radar_y_;
  rz = radar_z_ - (r_[2][0]*lx + r_[2][1]*ly + r_[2][2]*lz);
}
```

Never call `sinf`/`cosf` inside `loop()`.

#### Dimensionality mapping

The radar boresight is local **+Y**, so a range-only radar projects along +Y — not +X.

| Radar output     | Input to transform     | Published entities          |
|------------------|------------------------|-----------------------------|
| 1-D (range only) | `(0, range, 0)`        | `room_x`, `room_y`, `room_z`|
| 2-D (X, Y)       | `(lx, ly, 0)`          | `room_x`, `room_y`          |
| 3-D (X, Y, Z)    | `(lx, ly, lz)`         | `room_x`, `room_y`, `room_z`|

For a 1-D radar only column 1 of `R` is needed (`sy*cp`, `cy*cp`, `−sp`); roll cancels out because it turns about the boresight.

---

### 2. Boundary Filtering

Operates **exclusively in room-frame coordinates** (after transform).

- Minimum 3 vertices; validate in `__init__.py`. Empty → filter disabled (pass-through).
- For 2-D/3-D: Ray Casting on the XY projection. For 1-D: `distance_min`/`distance_max` range gate.

**Required processing order:** parse → transform → filter → publish.

#### What "filter" means

Out-of-boundary targets are **not** dropped from the per-target entities — the raw
coordinates stay visible so the Lovelace card can show a ghost and the user can
tell a mis-calibration from a real detection. Filtering is expressed two ways:

| Entity | Behaviour |
|---|---|
| `target_n_in_boundary` | Per-target verdict, published every frame. |
| `presence` | Counts **only in-boundary targets** when `boundary_gates_presence: true` (the default). |

`boundary_gates_presence` is what makes the through-wall ghost rejection in
`README.md` actually true; without it a target outside the polygon still drives
`presence`. Every component with a boundary must expose this option and default
it to `true`.

#### Native (radar-side) zone filtering

Some radars filter in firmware, which is strictly better than filtering on the
ESP because the ghost never reaches the UART. Where the protocol documents it,
expose it **in addition to** the polygon filter — they are complementary, not
alternatives:

- **LD2450** — protocol 2.2.12/2.2.13, commands `0x00C1` (query) / `0x00C2` (set).
  3 rectangles, `signed int16` mm, 26-byte payload, type `0`/`1`/`2`
  (off / detect-only-inside / ignore-inside). Config key `zone_filter`, coordinates
  in **cm** for consistency with the rest of the schema, converted to mm on the wire.
  The setting survives power-off, so only push it when the YAML actually specifies one.

Do not copy a native zone implementation to a model whose protocol document does
not define those commands — verify against `docs/{radar_model}/` first.

---

## Platform Exposure Convention

All entities declared in `__init__.py`. No `sensor.py`, `binary_sensor.py`, `number.py`.

Entity sub-schemas: `sensor.SENSOR_SCHEMA`, `binary_sensor.BINARY_SENSOR_SCHEMA`, `number.NUMBER_SCHEMA`. Entities registered in `to_code` via `sensor.new_sensor`, etc.

---

## Code Standards

- **C++14**, `#pragma once`, namespace `esphome::{radar_model}`.
- Members: trailing underscore. Constants: `static constexpr ALL_CAPS`.
- No dynamic allocation in hot paths.
- Parser: **state-machine based**, non-blocking.
- Validate values before `publish_state()` (reject NaN, ±Inf, out-of-range).
- Logging: `ESP_LOGD/I/W/E` with `TAG`. No `Serial.print`.
- All public methods: `///` Doxygen comment.
- Python: `CONF_*` constants, `snake_case` keys, `DEPENDENCIES = ["uart"]`.

---

## Pre-`Developing` Checklist

- [ ] `__init__.py`, `.h`, `.cpp` present (no separate platform files).
- [ ] `DEPENDENCIES = ["uart"]` in `__init__.py`.
- [ ] CONFIG_SCHEMA: `radar_x/y/z`, `radar_yaw/pitch/roll`, `boundary` (≥3-vertex validation).
- [ ] All entities in `__init__.py` using canonical ESPHome helpers.
- [ ] Radar-local axis convention in header comment.
- [ ] Rotation matrix: ZYX Tait-Bryan, pre-computed in `setup()`.
- [ ] Boundary filter: room-frame coords, post-transform.
- [ ] Processing order: parse → transform → filter → publish.
- [ ] Non-blocking state-machine parser.
- [ ] All values range-checked before `publish_state()`.
- [ ] `tests/{radar_model}-{platform}.yaml` present with `esp-idf` framework, correct `uart.baud_rate`, no `esphome.project`.
- [ ] `tests/{radar_model}-{platform}.factory.yaml` present with:
  - [ ] `core: !include` pointing to the base yaml.
  - [ ] `esphome.project.version: "dev"`.
  - [ ] `http_request:` declared before `ota` and `update`.
  - [ ] `ota: platform: http_request`.
  - [ ] `update: platform: http_request` with correct GitHub Pages `source` URL.
  - [ ] `dashboard_import`, `improv_serial`, `esp32_improv`.
- [ ] Both files compile cleanly in CI.
- [ ] `README.md` status updated to `Developing`.

---

## Adding a New Radar Model

1. Add `docs/{radar_model}/` with the product datasheet and communication protocol.
2. Optionally add wiring diagram images named `{radar_model}-*.png` (or `.jpg`) to the same folder — they will be automatically published to the install page.
3. Add a `Planned` row to the Radar Model Status table in `README.md`.
4. Ask the AI to generate the component. It reads the docs, generates `components/{radar_model}/` and `tests/{radar_model}-{platform}.yaml` + `tests/{radar_model}-{platform}.factory.yaml`, and updates the status to `Developing`.
5. Flash and test on hardware; report errors to the AI.
6. Once hardware tests pass → `Testing`. Once HA integration passes → `Completed`.

The CI and publish pipelines **auto-discover** `tests/*.yaml` — no workflow edits needed.

---

## CI/CD Summary

| Workflow | Trigger | Responsibility |
|---|---|---|
| **CI** (`ci.yml`) | PR / non-main push | Compiles all `tests/*.yaml` — validation only |
| **Publish** (`publish.yml`) | Push to `main` / release | Builds firmware, uploads `firmware-*` artifacts |
| **Publish Pages** (`publish-pages.yml`) | After Publish / `static/**` or `docs/**` push | Assembles site, deploys to GitHub Pages |

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
- Each radar model's user-facing documentation (sensor tables, quick-start guide, calibration) lives in `docs/{radar_model}/README.md`.