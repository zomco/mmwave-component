<div align="center">
  <img src="./assets/mmwave_logo.svg" alt="MMWave Logo" width="200"/>
  <h1>毫米波雷达 ESPHome 组件</h1>
</div>

[![CI](https://github.com/zomco/mmwave-component/actions/workflows/ci.yml/badge.svg)](https://github.com/zomco/mmwave-component/actions/workflows/ci.yml)
[![Publish](https://github.com/zomco/mmwave-component/actions/workflows/publish.yml/badge.svg)](https://github.com/zomco/mmwave-component/actions/workflows/publish.yml)

[English](./README.md)

适用于多款毫米波雷达型号的自定义 [ESPHome](https://esphome.io/) 外部组件，目标平台 **ESP32-C3**（计划支持 ESP32-S3 及其他 MCU）。

## 这是什么？

本仓库提供自定义的 ESPHome 固件，可将功能强大的毫米波雷达无缝集成到 Home Assistant 中。它通过内置的**坐标变换**和**边界过滤**功能，解决了“幽灵目标”（例如穿墙检测到人）和房间重叠等常见问题。

您无需处理复杂的原始雷达数据，而是直接获取精确的房间坐标，让智能家居自动化变得无比简单！

<img src="https://raw.githubusercontent.com/zomco/mmwave-card/main/docs/screenshot-live.png" alt="Live View Demo" width="600">

## 快速开始（开箱即用）

最简单的使用方式是通过浏览器直接安装预编译的固件。无需编写代码或进行复杂的配置！

> **🔌 在浏览器中直接安装固件 →** [**打开安装页**](https://zomco.github.io/mmwave-component/)
>
> _无需安装任何软件。需要 Chrome 或 Edge 浏览器（支持 Web Serial）。_

刷入固件后，您可以使用我们配套的 Home Assistant 卡片来可视化并配置雷达。通过 HACS 一键安装：

[![Open your Home Assistant instance and open a repository inside HACS.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=zomco&repository=mmwave-card&category=plugin)

## 进阶使用（DIY）

对于喜欢自定义 ESPHome YAML 配置（例如添加传感器、修改接线引脚）或手动编译固件的高级用户，请参考我们的 DIY 文档。

DIY 指南中还详细解释了坐标变换、过滤算法背后的技术原理及其局限性。

👉 **[进阶配置与 DIY 指南](./DIY_CN.md)**

---

## 雷达型号状态

| 雷达型号 | 状态      | 维度         | 应用场景                       | 文档                               |
| -------- | --------- | ------------ | ------------------------------ | ---------------------------------- |
| R60ABD1  | ✅ 已完成 | 3D (X, Y, Z) | 呼吸与睡眠监测、存在检测、心率 | [使用文档](docs/r60abd1/README.md) |

### 状态定义

| 状态         | 描述                                           |
| ------------ | ---------------------------------------------- |
| `Planned`    | 文档已准备；组件尚未生成。                     |
| `Developing` | 组件已生成；正在进行硬件固件测试。             |
| `Testing`    | 固件已验证；正在进行 Home Assistant 集成测试。 |
| `Completed`  | HA 集成已验证，运行稳定。                      |
| `Paused`     | 受外部条件阻塞（无硬件、无测试环境等）。       |

> 此表为权威信息来源，每次状态变更时更新。

---

## 许可证

MIT
