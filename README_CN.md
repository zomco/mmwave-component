<div align="center">
  <img src="./assets/mmwave_logo.svg" alt="MMWave Logo" width="200"/>
  <h1>毫米波雷达 ESPHome 组件</h1>
</div>

[![CI](https://github.com/zomco/mmwave-component/actions/workflows/ci.yml/badge.svg)](https://github.com/zomco/mmwave-component/actions/workflows/ci.yml)
[![Publish](https://github.com/zomco/mmwave-component/actions/workflows/publish.yml/badge.svg)](https://github.com/zomco/mmwave-component/actions/workflows/publish.yml)

[English](./README.md)

支持 16 款毫米波雷达型号的 [ESPHome](https://esphome.io/) 固件，目标平台 **ESP32-C3**
（ESP32-S3 及其他 MCU 在计划中）。

## 它解决什么问题

大多数 ESPHome 雷达组件把雷达的原始读数直接丢给 Home Assistant。这在实验台上没问题，
放进真实住宅就不行了：你不知道雷达具体怎么装的，那些坐标就毫无意义；而且毫米波能直接
穿透石膏板，雷达会兴高采烈地把隔壁邻居报给你。

本固件在数据到达 Home Assistant 之前，就在设备端做了两件事：

- **坐标变换** —— 根据实测的雷达安装位置和朝向，把雷达本地读数换算成**房间坐标**：
  以你指定的墙角为原点，单位厘米。
- **边界过滤** —— 丢弃你所画房间多边形之外的目标，这正是"穿墙幽灵不再触发存在检测"
  的实现方式。

得到的位置可以直接拿去写自动化。

<img src="https://raw.githubusercontent.com/zomco/mmwave-card/main/assets/screenshot-live.gif" alt="Live View Demo" width="600">

---

## 从这里开始

**第一次接触本项目？→ [新手上手指南](./GETTING-STARTED_CN.md)**

那份指南带你从一块光板加四根杜邦线，到一张实时房间图，大约 45 分钟，全程不用写 YAML。
简版流程：

1. **接线**：雷达接到 ESP32-C3，四根线，其中两根要交叉。
2. **烧录**：浏览器直接刷，不用装软件：

   > [**打开在线烧录页 →**](https://zomco.github.io/mmwave-component/)
   >
   > _需要 Chrome 或 Edge（Web Serial）。Firefox 和 Safari 用不了。_

3. **安装卡片**：这样看到的是图，而不是一堆数字：

   [![Open your Home Assistant instance and open a repository inside HACS.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=zomco&repository=mmwave-card&category=plugin)

4. **校准**：在卡片的三个标签页里完成。别跳过 —— 坐标有没有意义全看这一步。

---

## 文档导航

| 你的身份 | 该看 |
| --- | --- |
| 第一次安装 | [新手上手指南](./GETTING-STARTED_CN.md) |
| 想自己写 YAML、改引脚、加传感器 | [DIY 指南](./DIY_CN.md) |
| 查某个型号的实体和配置项 | `docs/<型号>/README_CN.md`，见下方型号表 |
| 想新增雷达型号，或者你是 AI 助手 | [AGENTS.md](./AGENTS.md) |
| 要装多台雷达 | [mmwave-fusion](https://github.com/zomco/mmwave-fusion) |

## 相关仓库

本固件是三个独立发版的组成部分之一：

| 仓库 | 是什么 | 要装吗 |
| --- | --- | --- |
| **mmwave-component**（本仓库） | ESPHome 固件 | 要 —— 这是设备端。 |
| [mmwave-card](https://github.com/zomco/mmwave-card) | Lovelace 卡片 | 实际上要 —— 它是唯一的界面，校准也在它里面做。 |
| [mmwave-fusion](https://github.com/zomco/mmwave-fusion) | HA 集成 | 只有多雷达融合才需要，实验性。 |

---

## 雷达型号状态

下面 16 款型号都已具备组件和固件配置。`文档` 一列指向已经写好的型号专属实体与配置说明。

| 雷达型号 | 状态 | 维度 | 目标数 | 波特率 | 应用场景 | 文档 |
| --- | --- | --- | --- | --- | --- | --- |
| R60ABD1 | ✅ 已完成 | 3D (X, Y, Z) | 1 | 115200 | 呼吸与睡眠监测、存在检测、心率 | [文档](docs/r60abd1/README_CN.md) |
| LD2450 | 🔧 开发中 | 2D (X, Y) | 3 | 256000 | 多目标追踪、速度、存在检测 | [文档](docs/ld2450/README_CN.md) |
| LD2452 | 🧪 测试中 | 2D (X, Y) | 3 | 9600 | 多目标追踪、融合测试 | [文档](docs/ld2452/README_CN.md) |
| LD2453 | 🔧 开发中 | 2D (X, Y) | 3 | 256000 | 多目标追踪、存在检测 | [文档](docs/ld2453/README_CN.md) |
| LD2454 | 🧪 测试中 | 2D (X, Y) | 3 | 256000 | 多目标追踪、融合测试 | — |
| LD2451 | 🔧 开发中 | 2D（极坐标） | 3 | 115200 | 多目标追踪、存在检测 | [文档](docs/ld2451/README_CN.md) |
| LD6002 | 🔧 开发中 | 1D（距离） | 1 | 1382400 | 呼吸、心率、存在检测 | [文档](docs/ld6002/README_CN.md) |
| LD2410 | 🔧 开发中 | 1D（距离） | 1 | 256000 | 存在/运动检测、分距离门能量 | — |
| LD2410B | 🔧 开发中 | 1D（距离） | 1 | 256000 | 存在/运动检测 | [文档](docs/ld2410b/README_CN.md) |
| LD2410C | 🔧 开发中 | 1D（距离） | 1 | 256000 | 存在/运动检测 | [文档](docs/ld2410c/README_CN.md) |
| LD2411 | 🔧 开发中 | 1D（距离） | 1 | 115200 | 存在/运动检测 | [文档](docs/ld2411/README_CN.md) |
| LD2411S | 🔧 开发中 | 1D（距离） | 1 | 256000 | 存在/运动 + 微动检测 | [文档](docs/ld2411s/README_CN.md) |
| LD2412 | 🔧 开发中 | 1D（距离） | 1 | 115200 | 存在/运动检测、14 距离门、环境光 | [文档](docs/ld2412/README_CN.md) |
| LD2420 | 🔧 开发中 | 1D（距离） | 1 | 115200 | 存在/运动检测、16 距离门、阈值校准 | [文档](docs/ld2420/README_CN.md) |
| LD2450A | 🔧 开发中 | 1D（距离） | 1 | 256000 | 测距 + 手势识别 | — |
| RD03E | 🔧 开发中 | 1D（距离） | 1 | 256000 | 精确测距、存在/运动检测（0.3–6 m） | [文档](docs/rd03e/README_CN.md) |

只有 2D 和 3D 型号能参与多雷达融合 —— 只测距的雷达只有距离没有方向，没有可融合的信息。

### 状态定义

| 状态 | 描述 |
| --- | --- |
| `Planned` | 文档已准备；组件尚未生成。 |
| `Developing` | 组件已生成；正在进行硬件固件测试。 |
| `Testing` | 固件已验证；正在进行 Home Assistant 集成测试。 |
| `Completed` | HA 集成已验证，运行稳定。 |
| `Paused` | 受外部条件阻塞（无硬件、无测试环境等）。 |

> 此表为权威信息来源，每次状态变更时更新。

---

## 许可证

MIT
