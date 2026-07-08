<div align="center">
  <img src="./assets/mmwave_logo.svg" alt="MMWave Logo" width="200"/>
  <h1>MMWave Radar ESPHome Component</h1>
</div>

[![CI](https://github.com/zomco/mmwave-component/actions/workflows/ci.yml/badge.svg)](https://github.com/zomco/mmwave-component/actions/workflows/ci.yml)
[![Publish](https://github.com/zomco/mmwave-component/actions/workflows/publish.yml/badge.svg)](https://github.com/zomco/mmwave-component/actions/workflows/publish.yml)

[中文文档](./README_CN.md)

Custom [ESPHome](https://esphome.io/) external components for multiple millimeter-wave radar models, targeting **ESP32-C3** (with planned ESP32-S3 and other MCU support).

## What is this?

This repository provides custom ESPHome firmware to integrate powerful millimeter-wave (mmWave) radars into Home Assistant seamlessly. It solves the common problems of "ghost targets" (e.g., detecting people through walls) and overlapping rooms by adding built-in **coordinate transformation** and **boundary filtering**.

Instead of dealing with raw radar data, you get precise room coordinates that are easy to use in your smart home automations!

<img src="https://raw.githubusercontent.com/zomco/mmwave-card/main/docs/screenshot-live.png" alt="Live View Demo" width="600">

## Quick Start (Out-of-the-Box)

The easiest way to use this component is to install the pre-compiled firmware directly from your browser. No coding or complex configuration required!

> **🔌 Install firmware directly in your browser →** [**Open Web Flasher**](https://zomco.github.io/mmwave-component/)
>
> _No software required. Requires Chrome or Edge with Web Serial support._

After flashing the firmware, you can visualize and configure your radar using our companion Home Assistant card. Install it with one click via HACS:

[![Open your Home Assistant instance and open a repository inside HACS.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=zomco&repository=mmwave-card&category=plugin)

## Advanced Usage (DIY)

For advanced users who prefer to write custom ESPHome YAML configurations (adding sensors, changing wiring pins), or compile the firmware manually, please refer to our DIY documentation.

The DIY guide also contains detailed explanations of the technical principles behind the coordinate transformations, filtering algorithms, and their limitations.

👉 **[Advanced Configuration & DIY Guide](./DIY.md)**

---

## Radar Model Status

| Radar Model | Status        | Dimension         | Application                                                            | Docs                                    |
| ----------- | ------------- | ----------------- | ---------------------------------------------------------------------- | --------------------------------------- |
| R60ABD1     | ✅ Completed  | 3D (X, Y, Z)      | Breathing & sleep monitoring, presence detection, heart rate           | [Documentation](docs/r60abd1/README.md) |
| LD2450      | 🔧 Developing | 2D (X, Y)         | Multi-target tracking (up to 3), speed measurement, presence detection | [Documentation](docs/ld2450/)           |
| RD03E       | 🔧 Developing | 1D (range)        | Precise ranging, presence/motion detection (0.3–6 m)                   | [Documentation](docs/rd03e/)            |
| LD2411      | 🔧 Developing | 1D (range)        | Presence/motion detection                                              | [Documentation](docs/ld2411/)           |
| LD2410B     | 🔧 Developing | 1D (range)        | Presence/motion detection                                              | [Documentation](docs/ld2410b/)          |
| LD2410C     | 🔧 Developing | 1D (range)        | Presence/motion detection                                              | [Documentation](docs/ld2410c/)          |
| LD6002      | 🔧 Developing | 3D (X, Y, Z, Bio) | Breathing, sleep, presence, positioning                                | [Documentation](docs/ld6002/)           |
| LD2453      | 🔧 Developing | 2D (X, Y)         | Multi-target tracking, presence detection                              | [Documentation](docs/ld2453/)           |
| LD2451      | 🔧 Developing | 2D (Polar)        | Multi-target tracking, presence detection                              | [Documentation](docs/ld2451/)           |

### Status Definitions

| Status       | Description                                                                |
| ------------ | -------------------------------------------------------------------------- |
| `Planned`    | Documentation staged; component not yet generated.                         |
| `Developing` | Component generated; undergoing on-hardware firmware tests.                |
| `Testing`    | Firmware validated; undergoing Home Assistant integration tests.           |
| `Completed`  | HA integration validated and stable.                                       |
| `Paused`     | Blocked by an external condition (no hardware, no test environment, etc.). |

> This table is the authoritative source of truth, updated on every status change.

---

## License

MIT
