<div align="center">
  <img src="./assets/mmwave_logo.svg" alt="MMWave Logo" width="200"/>
  <h1>毫米波雷达 ESPHome 组件</h1>
</div>

[![CI](https://github.com/zomco/mmwave-component/actions/workflows/ci.yml/badge.svg)](https://github.com/zomco/mmwave-component/actions/workflows/ci.yml)
[![Publish](https://github.com/zomco/mmwave-component/actions/workflows/publish.yml/badge.svg)](https://github.com/zomco/mmwave-component/actions/workflows/publish.yml)

[English](./README.md)

16 款毫米波雷达的 ESPHome 固件，目标平台 **ESP32-C3**。数据到达 Home Assistant 之前，设备把雷达读数换成房间坐标，并丢掉你所画房间之外的目标。这样位置才能直接拿去写自动化，穿墙目标也不会把灯打开。

## 快速使用

第一次安装走 [新手上手指南](./GETTING-STARTED_CN.md)（约 45 分钟，不用写 YAML）。简版：

1. 雷达接到 ESP32-C3：四根线，TX 与 RX 交叉。
2. 浏览器烧录。只能用 Chrome 或 Edge：

   [**打开在线烧录页 →**](https://zomco.github.io/mmwave-component/)

3. 安装卡片。它是唯一的界面，校准也在里面做：

   [![Open your Home Assistant instance and open a repository inside HACS.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=zomco&repository=mmwave-card&category=plugin)

4. 在卡片里校准。跳过这一步，坐标没有意义。

改过实体所在分组后，刷完固件还要重新加载该设备的配置项。Home Assistant 会保留第一次注册时的分类。见 [DIY 指南](./DIY_CN.md)。

## 文档地图

| 想了解 | 看 |
| --- | --- |
| 第一次安装、接线、烧录、校准 | [新手上手指南](./GETTING-STARTED_CN.md) |
| 自己写 YAML、改引脚、加传感器 | [DIY 指南](./DIY_CN.md) |
| 某个型号的实体和选项 | `docs/<型号>/README_CN.md`（LD2410、LD2450A 只有说明书 PDF，在 `docs/<型号>/`） |
| 新增型号，或你是 AI 助手 | [AGENTS.md](./AGENTS.md) |
| 面板和校准界面 | [mmwave-card](https://github.com/zomco/mmwave-card) |
| 轨迹存储、区域事件、录像 | [mmwave-fusion](https://github.com/zomco/mmwave-fusion) — 仅 2D 雷达 |
| 不依赖 Home Assistant 的融合算法 | [mmwave-engine](https://github.com/zomco/mmwave-engine) |

<a id="雷达型号状态"></a>

## 雷达型号

分两类。**1D 雷达只上报距离。** 不能使用 [mmwave-fusion](https://github.com/zomco/mmwave-fusion)：没有方向，就没有轨迹、区域穿越和录像。固件和卡片仍然可用（存在检测、距离、最近/最远距离门限）。

**2D 雷达上报地面上的位置。** 可以使用全部功能，包括融合。R60ABD1 同时上报高度，列在这里是因为它可以参与融合。

数字来自 `docs/<型号>/` 里的说明书。`—` 表示说明书没有给出。标了「精度」的不是距离门宽度。LD2410 在 0.20 m 分辨率下最远 1.6 m。LD2451 按整米上报。LD2450、LD2454 的距离分辨率在每帧目标里，说明书没有固定值。LD2454 性能表写 8 m，安装章节写跟踪 6 m。

本文件的进度是权威来源。先改这里，再把同一状态抄到其他仓库。

| 状态 | 含义 |
| --- | --- |
| 开发中 | 组件已有；正在做硬件固件测试。 |
| 测试中 | 固件已在硬件上验证；正在做 Home Assistant 集成测试。 |
| 已完成 | Home Assistant 集成已验证，运行稳定。 |

### 1D 雷达

| 型号 | 检测距离 | 距离分辨率 | 开发进度 |
| --- | --- | --- | --- |
| LD2410 | 6 m | 0.75 m / 0.20 m | 开发中 |
| LD2410B | 6 m | 0.75 m（协议亦可设 0.20 m） | 测试中 |
| LD2410C | 6 m | 0.75 m（协议亦可设 0.20 m） | 测试中 |
| LD2411 | 2 m（手势 1 m） | — | 开发中 |
| LD2411S | 6 m（微动 3.5 m） | ±5 cm / ±5%（精度） | 开发中 |
| LD2412 | 9 m | 0.75 m | 开发中 |
| LD2420 | 8 m（微动 6 m） | 0.70 m | 开发中 |
| LD2450A | 2 m | 0.2 m（感知精度） | 开发中 |
| LD6002 | 1.5 m（呼吸心率） | — | 开发中 |
| RD-03E | 6 m（微动 3.5 m） | ±5 cm / ±5%（精度） | 开发中 |

### 2D 雷达

| 型号 | 检测距离 | 角度范围 | 距离分辨率 | 开发进度 |
| --- | --- | --- | --- | --- |
| LD2450 | 6 m | 方位 ±60°，俯仰 ±35° | 随帧上报 | 开发中 |
| LD2451 | 100 m | 水平 ±15°，垂直 ±7° | 1 m | 测试中 |
| LD2452 | 6 m | 方位 ±60°，俯仰 ±30° | 0.72 m | 测试中 |
| LD2453 | 6 m | 方位 ±40°，俯仰 ±30° | 0.72 m | 开发中 |
| LD2454 | 8 m | 方位 ±60°，俯仰 ±30° | 随帧上报 | 测试中 |
| R60ABD1 | 2.5 m（呼吸心率 1.5 m） | ±20° | — | 已完成 |

## 许可证

MIT
