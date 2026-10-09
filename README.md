<div align="center">
  <img src="./assets/mmwave_logo.svg" alt="MMWave Logo" width="200"/>
  <h1>MMWave Radar ESPHome Component</h1>
</div>

[![CI](https://github.com/zomco/mmwave-component/actions/workflows/ci.yml/badge.svg)](https://github.com/zomco/mmwave-component/actions/workflows/ci.yml)
[![Publish](https://github.com/zomco/mmwave-component/actions/workflows/publish.yml/badge.svg)](https://github.com/zomco/mmwave-component/actions/workflows/publish.yml)

[中文文档](./README_CN.md)

ESPHome firmware for 16 millimetre-wave radars on **ESP32-C3**. Before Home Assistant sees a value, the device converts the radar reading into room coordinates and drops targets outside the room you draw. That is what makes a position usable in an automation, and what stops a through-wall ghost from turning on a light.

## Quick start

New here? Follow [Getting Started](./GETTING-STARTED.md) (about 45 minutes, no YAML). Short version:

1. Wire the radar to an ESP32-C3 — four wires, TX and RX crossed.
2. Flash in the browser. Chrome or Edge only:

   [**Open Web Flasher →**](https://zomco.github.io/mmwave-component/)

3. Install the card. It is the only UI, and calibration happens there:

   [![Open your Home Assistant instance and open a repository inside HACS.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=zomco&repository=mmwave-card&category=plugin)

4. Calibrate in the card. Skip this and the coordinates do not mean anything.

Changing which block an entity appears in needs a config-entry reload after the flash. Home Assistant keeps the old category until then. See [DIY.md](./DIY.md).

## Documentation map

| If you want | Read |
| --- | --- |
| First install, wiring, flash, calibration | [Getting Started](./GETTING-STARTED.md) |
| Your own YAML, pins, extra sensors | [DIY guide](./DIY.md) |
| One model's entities and options | `docs/<model>/README.md` (LD2410 and LD2450A: PDF only, under `docs/<model>/`) |
| Add a model, or you are an AI agent | [AGENTS.md](./AGENTS.md) |
| The dashboard and calibration UI | [mmwave-card](https://github.com/zomco/mmwave-card) |
| Stored tracks, zone events, clips | [mmwave-fusion](https://github.com/zomco/mmwave-fusion) — 2D radars only |
| The fusion algorithm, without Home Assistant | [mmwave-engine](https://github.com/zomco/mmwave-engine) |

<a id="radar-model-status"></a>

## Radars

Two classes. **1D radars report distance only.** They cannot use [mmwave-fusion](https://github.com/zomco/mmwave-fusion): there is no direction to turn into a track, a zone crossing, or a clip. Firmware and the card still work (presence, distance, a min/max distance gate).

**2D radars report a position on the floor.** They can use every feature, including fusion. R60ABD1 also reports height; it is listed here because it can be fused.

Figures are from the manuals in `docs/<model>/`. `—` means the manual does not state it. A cell marked *accuracy* is not a range-gate width. LD2410 at 0.20 m resolution reaches 1.6 m. LD2451 reports whole metres. LD2450 and LD2454 publish resolution in each target frame; the manual has no fixed value. LD2454's performance table says 8 m; the install section says 6 m tracking.

Progress in this file is the source of truth. Update it here, then copy the same status into the other repositories.

| Status | Meaning |
| --- | --- |
| Developing | Component exists; on-hardware firmware tests are in progress. |
| Testing | Firmware checked on hardware; Home Assistant integration tests are in progress. |
| Completed | Home Assistant integration checked and stable. |

### 1D radars

| Model | Detection distance | Distance resolution | Progress |
| --- | --- | --- | --- |
| LD2410 | 6 m | 0.75 m / 0.20 m | Developing |
| LD2410B | 6 m | 0.75 m (protocol can also select 0.20 m) | Testing |
| LD2410C | 6 m | 0.75 m (protocol can also select 0.20 m) | Testing |
| LD2411 | 2 m (gesture 1 m) | — | Developing |
| LD2411S | 6 m (micro-motion 3.5 m) | ±5 cm / ±5% (accuracy) | Developing |
| LD2412 | 9 m | 0.75 m | Developing |
| LD2420 | 8 m (micro-motion 6 m) | 0.70 m | Developing |
| LD2450A | 2 m | 0.2 m (sensing accuracy) | Developing |
| LD6002 | 1.5 m (breath / heart) | — | Developing |
| RD-03E | 6 m (micro-motion 3.5 m) | ±5 cm / ±5% (accuracy) | Developing |

### 2D radars

| Model | Detection distance | Angle | Distance resolution | Progress |
| --- | --- | --- | --- | --- |
| LD2450 | 6 m | azimuth ±60°, elevation ±35° | per frame | Developing |
| LD2451 | 100 m | horizontal ±15°, vertical ±7° | 1 m | Testing |
| LD2452 | 6 m | azimuth ±60°, elevation ±30° | 0.72 m | Testing |
| LD2453 | 6 m | azimuth ±40°, elevation ±30° | 0.72 m | Developing |
| LD2454 | 8 m | azimuth ±60°, elevation ±30° | per frame | Testing |
| R60ABD1 | 2.5 m (breath / heart 1.5 m) | ±20° | — | Completed |

## License

MIT
