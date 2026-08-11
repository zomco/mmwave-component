# 进阶配置与 DIY 指南

[English](./DIY.md)

本指南面向希望自定义 ESPHome 配置（例如添加传感器、修改接线引脚）、手动编译固件，或希望了解本组件背后技术原理的高级用户。

> **第一次安装？** 请先看[新手上手指南](./GETTING-STARTED_CN.md) —— 它覆盖接线、浏览器
> 烧录和校准，全程不用写 YAML。等你要改它没覆盖的东西时，再回到本文。

## 配置项说明

所有型号都提供同样的六个校准参数和一个边界多边形；型号专属选项（距离门、阈值、区域
过滤等）各不相同。在[雷达型号状态表](./README_CN.md#雷达型号状态)里找到你的型号，
`文档` 一列指向它的实体与配置说明。

参考实现、也是文档最完整的型号是 [R60ABD1](docs/r60abd1/README_CN.md)。

### 雷达定义实际写在哪

每个型号的雷达定义只写**一份**，位于 `tests/common/{型号}.yaml`，以 package 方式引入：

```yaml
packages:
  radar: !include common/r60abd1.yaml
```

这份共享核心包含 `uart:` 块、组件配置、校准用的 `globals`，以及多边形解析脚本。
按平台区分的文件（`tests/r60abd1-esp32c3.yaml`）只负责开发板、网络和
`external_components`。

开发工作区引入的是**同一份**核心文件，所以改一次就同时作用于出厂固件和联调环境。
如果图省事把雷达配置块复制进平台文件，两边就会悄悄地不一致。

### 接线

所有型号都是 `GPIO21` → 雷达 `RX`、`GPIO20` ← 雷达 `TX`（交叉），只有一个例外：
**LD2410** 用 `GPIO4`/`GPIO5`。

各型号波特率差异很大，必须和协议文档完全一致 —— 从 9600（LD2452）到
1382400（LD6002）都有。改 UART 配置前先查主 README 里的表。

## 功能特性

### 问题：为什么需要这些功能？

现有的大多数 ESPHome 毫米波雷达组件仅暴露原始传感器数据（距离、存在状态、雷达局部坐标系下的目标坐标）。这在单传感器、单房间的简单场景下可以使用，但在实际部署中会遇到以下问题：

```mermaid
flowchart LR
    subgraph "没有本组件"
        R1["雷达模组"] -->|"原始局部坐标<br>(x=50, y=120)"| HA1["Home Assistant"]
        HA1 -->|"❌ 无房间上下文<br>❌ 无法跨雷达比较<br>❌ 邻室幽灵目标"| U1["用户"]
    end
```

| 问题 | 描述 | 示例 |
|---|---|---|
| **坐标歧义** | 原始雷达坐标相对于雷达天线自身。同一物理位置会因雷达的安装方式（旋转、倾斜、偏心）产生不同的 (x, y) 值。 | 安装在天花板朝下的雷达报告 `y = 120 cm`，实际目标在门口——对应房间坐标为 `room_x = 350, room_y = 80`。没有坐标变换，自动化必须为每个安装位置硬编码偏移量。 |
| **无法多雷达融合** | 同一房间的两个雷达各自报告独立的局部坐标，没有共享参考系。无法关联目标或去重。 | 雷达 A 报告目标在 (50, 120)，雷达 B 报告在 (80, 90)。这是同一个人还是两个人？没有统一坐标系无法判断。 |
| **跨房间误报** | 毫米波信号可以穿透薄墙、玻璃和门。雷达可能检测到相邻房间、走廊甚至室外的人。没有机制丢弃越界目标。 | 卧室睡眠雷达检测到走廊中走动的人，在凌晨 3 点触发了错误的"在床"状态。 |

---

### 方案一：坐标变换

基于雷达的物理安装参数，将原始雷达局部坐标转换为**房间坐标系**。

```mermaid
flowchart LR
    subgraph "雷达局部坐标系"
        T["目标<br>(rx, ry, rz)"]
    end

    subgraph "变换"
        direction TB
        R["旋转矩阵<br>R = Rz(yaw)·Rx(pitch)·Ry(roll)"]
        TR["平移<br>+ (radar_x, radar_y, radar_z)"]
        R --> TR
    end

    subgraph "房间坐标系"
        RT["目标<br>(room_x, room_y, room_z)"]
    end

    T --> R
    TR --> RT
```

**工作原理：**

1. 用户测量雷达在房间中的位置（以房间角落为原点，X 向右，Y 向前）和姿态（偏航角、俯仰角、横滚角）。
2. 这 6 个参数在 YAML 中编译时声明，也可在运行时通过 Home Assistant `number` 实体调整。
3. 每次收到目标上报时，组件执行：
   - 使用 ZYX Tait-Bryan 约定构建 3×3 旋转矩阵：**R = Rz(yaw) · Rx(pitch) · Ry(roll)**
   - 计算：`world = R × [rx, ry, rz]ᵀ`
   - 平移：`room = world + [radar_x, radar_y, radar_z]ᵀ`
4. 变换后的 `room_x`、`room_y`、`room_z` 作为 ESPHome sensor 实体发布。

```yaml
r60abd1:
  radar_x: 200.0      # cm — 距左墙距离
  radar_y: 175.0      # cm — 距后墙距离
  radar_z: 220.0      # cm — 安装高度
  yaw:   0.0           # 度 — 水平朝向偏差
  pitch: 0.0           # 度 — 俯仰角
  roll:  0.0           # 度 — 横滚角
```

**解决了什么：**
- ✅ 所有目标都在统一的房间坐标系中，与雷达的安装方式无关。
- ✅ 同一房间的多个雷达可以共享同一参考系，实现目标关联。
- ✅ 自动化引用真实房间位置（如"目标在床附近"），而不是不透明的雷达局部坐标值。

**局限性：**
- ❌ 用户必须手动测量并输入 6 个校准参数。精度取决于测量精度（手动测量典型误差 ±5 cm）。
- ❌ 无法补偿雷达硬件失真（非线性距离误差、多径反射等）。
- ❌ 不执行多雷达目标融合——每个雷达仍独立发布。共享坐标系仅使融合在 HA 自动化层面*成为可能*。

**维度映射：**

不同雷达型号输出不同层级的位置信息。变换相应适配：

| 雷达输出 | 变换输入 | 发布的实体 |
|---|---|---|
| 1D（仅距离） | `(range, 0, 0)` | `room_x`, `room_y`, `room_z` |
| 2D（X, Y） | `(lx, ly, 0)` | `room_x`, `room_y` |
| 3D（X, Y, Z） | `(lx, ly, lz)` | `room_x`, `room_y`, `room_z` |

---

### 方案二：边界过滤

丢弃落在用户定义多边形外的目标，**完全在房间坐标系中运作**（变换之后）。

```mermaid
flowchart TB
    subgraph "处理流水线"
        direction LR
        P["解析<br>UART 帧"] --> X["变换<br>局部 → 房间"]
        X --> F{"在边界内?"}
        F -->|"是 ✅"| PUB["发布到 HA"]
        F -->|"否 ❌"| DROP["丢弃"]
    end

    subgraph "房间俯视图"
        direction TB
        POLY["多边形边界<br>┌─────────┐<br>│  ✅ T1  │<br>│         │<br>└─────────┘<br>      ❌ T2 (走廊)"]
    end
```

**工作原理：**

1. 用户用房间坐标（cm）定义一个多边形，表示监测区域。
2. 坐标变换后，组件使用**射线法（Ray Casting）**（每点 O(n)，支持凸多边形和凹多边形）检测每个目标的 `(room_x, room_y)` 是否在多边形内。
3. 多边形外的目标被静默丢弃——不会发布到 Home Assistant。

```yaml
r60abd1:
  polygon:
    - { x:   0, y:   0 }     # 左下角
    - { x: 400, y:   0 }     # 右下角
    - { x: 400, y: 350 }     # 右上角
    - { x:   0, y: 350 }     # 左上角
```

**解决了什么：**
- ✅ 消除跨房间误报（走廊、相邻房间、室外）。
- ✅ 支持房间内分区（如仅监测床区域，不包含卫生间）。
- ✅ 支持任意房间形状——不限于矩形。

**局限性：**
- ❌ 过滤仅基于 2D（XY 投影）。无法按高度（Z 轴）过滤。不同楼层正上方/正下方的目标如果 XY 投影落在多边形内，仍会通过。
- ❌ 至少需要 3 个多边形顶点才能激活。少于 3 个顶点时过滤功能禁用（直通）。
- ❌ 无法过滤由多径反射引起的"软"误报，即看起来来源于多边形内部的虚假目标。

---

### 端到端处理流水线

每个雷达帧的完整数据流：

```mermaid
flowchart LR
    UART["UART 字节流"]
    SM["状态机<br>帧解析"]
    DEC["解码字段<br>(存在, 坐标,<br>呼吸, 心率, 睡眠)"]
    XFM["坐标<br>变换"]
    BND["边界<br>过滤"]
    PUB["发布到<br>Home Assistant"]

    UART --> SM --> DEC --> XFM --> BND --> PUB

    style SM fill:#2d3436,stroke:#00cec9,color:#dfe6e9
    style XFM fill:#2d3436,stroke:#fdcb6e,color:#dfe6e9
    style BND fill:#2d3436,stroke:#e17055,color:#dfe6e9
```

> **处理顺序是强制的：** 解析 → 变换 → 过滤 → 发布。变换必须在过滤之前，因为多边形是在房间坐标系中定义的。

---

## 仓库结构

```
.
├── .github/
│   ├── copilot-instructions.md   # AI 开发指南 & CI/CD 文档
│   └── workflows/
│       ├── ci.yml                # PR 检查：编译所有 tests/*.yaml
│       ├── publish.yml           # 构建固件，上传产物
│       └── publish-pages.yml     # 部署 GitHub Pages（与固件构建分离）
├── components/{radar_model}/     # ESPHome 外部组件（__init__.py、.h、.cpp）
├── docs/{radar_model}/           # 规格书、协议 PDF、接线图、README.md
├── static/                       # GitHub Pages 源文件 (Jekyll)
│   ├── _config.yml
│   └── index.html                # ESP Web Tools 安装页
├── tests/
│   ├── common/{radar_model}.yaml              # 共享雷达核心 —— uart、组件、
│   │                                          # globals、脚本，只在这里改一次
│   ├── {radar_model}-{platform}.yaml          # 基础固件配置
│   └── {radar_model}-{platform}.factory.yaml  # 出厂固件配置
├── GETTING-STARTED_CN.md         # 新手上手指南，不用写 YAML
├── DIY_CN.md                     # 本文件
├── AGENTS.md                     # → .github/copilot-instructions.md
└── README_CN.md                  # 雷达型号状态表（权威来源）
```

文档全程双语：每个 `X.md` 都有对应的 `X_CN.md`，每个 `docs/{型号}/README.md` 都有
对应的 `README_CN.md`。

---

