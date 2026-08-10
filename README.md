<div align="center">
  <img src="./assets/mmwave_logo.svg" alt="MMWave Logo" width="200"/>
  <h1>MMWave Radar ESPHome Component</h1>
</div>

[![CI](https://github.com/zomco/mmwave-component/actions/workflows/ci.yml/badge.svg)](https://github.com/zomco/mmwave-component/actions/workflows/ci.yml)
[![Publish](https://github.com/zomco/mmwave-component/actions/workflows/publish.yml/badge.svg)](https://github.com/zomco/mmwave-component/actions/workflows/publish.yml)

[中文文档](./README_CN.md)

ESPHome firmware for 16 millimetre-wave radar models, targeting **ESP32-C3**
(ESP32-S3 and other MCUs planned).

## What this gives you

Most ESPHome radar components hand Home Assistant the radar's own raw numbers.
That works on a bench and falls apart in a house: the coordinates mean nothing
until you know exactly how the radar is mounted, and mmWave passes straight
through plasterboard, so the radar happily reports your neighbour.

This firmware does two things about that, on the device, before Home Assistant
ever sees a value:

- **Coordinate transformation** — converts radar-local readings into **room
  coordinates**, in centimetres from a corner you pick, using the radar's
  measured position and orientation.
- **Boundary filtering** — rejects targets outside a polygon you draw around
  the actual room, which is what stops through-wall ghosts driving presence.

The result is a position you can write an automation against directly.

<img src="https://raw.githubusercontent.com/zomco/mmwave-card/main/assets/screenshot-live.gif" alt="Live View Demo" width="600">

---

## Start here

**New to this project? → [Getting Started](./GETTING-STARTED.md)**

That guide takes you from a bare board and four jumper wires to a live room
map, in about 45 minutes, without writing any YAML. The short version:

1. **Wire** the radar to an ESP32-C3 — four wires, two of them crossed.
2. **Flash** from your browser — no software to install:

   > [**Open Web Flasher →**](https://zomco.github.io/mmwave-component/)
   >
   > _Requires Chrome or Edge (Web Serial). Firefox and Safari will not work._

3. **Install the card** so you get a picture instead of numbers:

   [![Open your Home Assistant instance and open a repository inside HACS.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=zomco&repository=mmwave-card&category=plugin)

4. **Calibrate** in the card's three tabs. Do not skip this — it is what makes
   the coordinates mean anything.

---

## Documentation map

| If you are | Read |
| --- | --- |
| Setting this up for the first time | [Getting Started](./GETTING-STARTED.md) |
| Writing your own YAML, changing pins, adding sensors | [DIY guide](./DIY.md) |
| Looking up one model's entities and options | `docs/<model>/README.md`, linked in the table below |
| Adding a new radar model, or an AI agent working here | [AGENTS.md](./AGENTS.md) |
| Setting up more than one radar | [mmwave-fusion](https://github.com/zomco/mmwave-fusion) |

## Related repositories

This firmware is one of three pieces, released separately:

| Repository | What it is | Needed? |
| --- | --- | --- |
| **mmwave-component** (this) | ESPHome firmware | Yes — this is the device side. |
| [mmwave-card](https://github.com/zomco/mmwave-card) | Lovelace card | Yes in practice — it is the only UI, and calibration happens in it. |
| [mmwave-fusion](https://github.com/zomco/mmwave-fusion) | HA integration | Only for multi-radar fusion. Experimental. |

---

## Radar Model Status

All 16 models below have a component and firmware config. The `Docs` column
links model-specific entity and configuration reference where it has been
written.

| Radar Model | Status | Dimension | Targets | Baud | Application | Docs |
| --- | --- | --- | --- | --- | --- | --- |
| R60ABD1 | ✅ Completed | 3D (X, Y, Z) | 1 | 115200 | Breathing & sleep monitoring, presence, heart rate | [Docs](docs/r60abd1/README.md) |
| LD2450 | 🔧 Developing | 2D (X, Y) | 3 | 256000 | Multi-target tracking, speed, presence | [Docs](docs/ld2450/README.md) |
| LD2452 | 🧪 Testing | 2D (X, Y) | 3 | 9600 | Multi-target tracking, fusion testing | [Docs](docs/ld2452/README.md) |
| LD2453 | 🔧 Developing | 2D (X, Y) | 3 | 256000 | Multi-target tracking, presence | [Docs](docs/ld2453/README.md) |
| LD2454 | 🧪 Testing | 2D (X, Y) | 3 | 256000 | Multi-target tracking, fusion testing | — |
| LD2451 | 🔧 Developing | 2D (polar) | 3 | 115200 | Multi-target tracking, presence | [Docs](docs/ld2451/README.md) |
| LD6002 | 🔧 Developing | 1D (range) | 1 | 1382400 | Breathing, heart rate, presence | [Docs](docs/ld6002/README.md) |
| LD2410 | 🔧 Developing | 1D (range) | 1 | 256000 | Presence/motion, per-gate energy | — |
| LD2410B | 🔧 Developing | 1D (range) | 1 | 256000 | Presence/motion detection | [Docs](docs/ld2410b/README.md) |
| LD2410C | 🔧 Developing | 1D (range) | 1 | 256000 | Presence/motion detection | [Docs](docs/ld2410c/README.md) |
| LD2411 | 🔧 Developing | 1D (range) | 1 | 115200 | Presence/motion detection | [Docs](docs/ld2411/README.md) |
| LD2411S | 🔧 Developing | 1D (range) | 1 | 256000 | Presence/motion + micro-motion | [Docs](docs/ld2411s/README.md) |
| LD2412 | 🔧 Developing | 1D (range) | 1 | 115200 | Presence/motion, 14 gates, ambient light | [Docs](docs/ld2412/README.md) |
| LD2420 | 🔧 Developing | 1D (range) | 1 | 115200 | Presence/motion, 16 gates, threshold calibration | [Docs](docs/ld2420/README.md) |
| LD2450A | 🔧 Developing | 1D (range) | 1 | 256000 | Ranging + gesture recognition | — |
| RD03E | 🔧 Developing | 1D (range) | 1 | 256000 | Precise ranging, presence/motion (0.3–6 m) | [Docs](docs/rd03e/README.md) |

Only 2-D and 3-D models can take part in multi-radar fusion — a range-only
radar reports distance without direction, so there is nothing to fuse.

### Status Definitions

| Status | Description |
| --- | --- |
| `Planned` | Documentation staged; component not yet generated. |
| `Developing` | Component generated; undergoing on-hardware firmware tests. |
| `Testing` | Firmware validated; undergoing Home Assistant integration tests. |
| `Completed` | HA integration validated and stable. |
| `Paused` | Blocked by an external condition (no hardware, no test environment). |

> This table is the authoritative source of truth, updated on every status change.

---

## License

MIT
