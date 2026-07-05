# R60ABD1

MicRadar R60ABD1 60 GHz 毫米波呼吸睡眠雷达 ESPHome 组件。

[English Documentation](./README.md)

![R60ABD1 底面](./r60abd1-底面.jpg)
![R60ABD1 正面](./r60abd1-正面.jpg)

## Sensor 参考表

> [!NOTE]
> 本表基于产品说明书 V3.4、ESPHome 组件实现代码和 YAML 配置交叉校验。
> AI 工具生成 Home Assistant Card 时应参考本表确定实体类型、数值范围和更新频率。

### Entity 类型说明

| ESPHome 类型    | Home Assistant 类型 | 说明               |
| --------------- | ------------------- | ------------------ |
| `binary_sensor` | `binary_sensor`     | 布尔状态（ON/OFF） |
| `sensor`        | `sensor`            | 数值型传感器       |
| `text_sensor`   | `sensor`（字符串）  | 枚举文本状态       |

### 存在与运动

| YAML Key        | Entity 类型     | 数据类型 | 数值/状态                       | 单位 | 更新频率                                        | 说明                                                 |
| --------------- | --------------- | -------- | ------------------------------- | ---- | ----------------------------------------------- | ---------------------------------------------------- |
| `presence`      | `binary_sensor` | `bool`   | `true` / `false`                | —    | 状态变化时上报；无人→有人 ≤0.5s，有人→无人 ~40s | 人体存在检测（`device_class: presence`）             |
| `motion_state`  | `sensor`        | `int`    | `0`＝无人，`1`＝静止，`2`＝活跃 | —    | 状态变化时上报；静止↔活跃切换 ≤0.5s             | 运动状态（协议 cmd `0x80/0x02`）                     |
| `body_movement` | `sensor`        | `int`    | `0` ~ `100`                     | —    | 每 1s 上报                                      | 体动幅度参数                                         |
| `body_distance` | `sensor`        | `uint16` | `0` ~ `65535`                   | cm   | 每 2s 上报                                      | 人体与雷达之间的直线距离（`device_class: distance`） |

### 人体方位 — 雷达局部坐标

| YAML Key | Entity 类型 | 数据类型                | 数值范围            | 单位 | 更新频率   | 说明                                 |
| -------- | ----------- | ----------------------- | ------------------- | ---- | ---------- | ------------------------------------ |
| `raw_x`  | `sensor`    | `int16`（符号幅值编码） | `-32767` ~ `+32767` | cm   | 每 2s 上报 | 雷达局部坐标 X（右正左负）           |
| `raw_y`  | `sensor`    | `int16`（符号幅值编码） | `-32767` ~ `+32767` | cm   | 每 2s 上报 | 雷达局部坐标 Y（正前方为正）         |
| `raw_z`  | `sensor`    | `int16`（符号幅值编码） | `-32767` ~ `+32767` | cm   | 每 2s 上报 | 雷达局部坐标 Z（垂直天线面向外为正） |

> [!TIP]
> `raw_x/y/z` 坐标编码方式：2 字节，bit15 为符号位（0＝正，1＝负），bit14–bit0 为 15 位幅值。
> 组件内部通过 `decode_coord()` 函数解码。通常这三个 sensor 设置 `internal: true`，仅用于调试。

### 人体方位 — 房间坐标（坐标变换后）

| YAML Key      | Entity 类型     | 数据类型                 | 数值范围                      | 单位 | 更新频率                      | 说明                                                      |
| ------------- | --------------- | ------------------------ | ----------------------------- | ---- | ----------------------------- | --------------------------------------------------------- |
| `room_x`      | `sensor`        | `float`（精度 1 位小数） | 取决于校准参数和房间尺寸      | cm   | 每 2s 上报（与 raw 坐标同步） | 目标在房间坐标系中的 X 坐标                               |
| `room_y`      | `sensor`        | `float`（精度 1 位小数） | 取决于校准参数和房间尺寸      | cm   | 每 2s 上报（与 raw 坐标同步） | 目标在房间坐标系中的 Y 坐标                               |
| `room_z`      | `sensor`        | `float`（精度 1 位小数） | `0` ~ `radar_z`（典型 0~300） | cm   | 每 2s 上报（与 raw 坐标同步） | 目标距地面高度（`radar_z − wz`）                          |
| `in_boundary` | `binary_sensor` | `bool`                   | `true` / `false`              | —    | 每 2s 上报（与 raw 坐标同步） | 目标是否在配置的多边形边界内（polygon 为空时始终 `true`） |

> [!IMPORTANT]
> `room_x/y/z` 和 `in_boundary` 是组件侧计算的派生值，不是雷达直接输出。
> 其值依赖 YAML 中配置的校准参数（`radar_x/y/z`、`yaw/pitch/roll`）和多边形边界（`polygon`）。

### 呼吸监测

| YAML Key       | Entity 类型   | 数据类型 | 数值/状态                                  | 单位   | 更新频率       | 说明                                                                                      |
| -------------- | ------------- | -------- | ------------------------------------------ | ------ | -------------- | ----------------------------------------------------------------------------------------- |
| `breath_value` | `sensor`      | `uint8`  | `0` ~ `35`                                 | 次/min | 每 3s 上报     | 实时呼吸频率                                                                              |
| `breath_state` | `text_sensor` | `string` | `"normal"` / `"high"` / `"low"` / `"none"` | —      | 状态变化时上报 | 呼吸状态判断：`normal`＝10~25 次/min，`high`＝>25 次/min，`low`＝<10 次/min，`none`＝无人 |

### 心率监测

| YAML Key     | Entity 类型 | 数据类型 | 数值范围     | 单位 | 更新频率   | 说明         |
| ------------ | ----------- | -------- | ------------ | ---- | ---------- | ------------ |
| `heart_rate` | `sensor`    | `uint8`  | `60` ~ `120` | bpm  | 每 3s 上报 | 实时心率数值 |

### 睡眠监测

| YAML Key               | Entity 类型     | 数据类型 | 数值/状态                                   | 单位 | 更新频率                            | 说明                                                                                 |
| ---------------------- | --------------- | -------- | ------------------------------------------- | ---- | ----------------------------------- | ------------------------------------------------------------------------------------ |
| `in_bed`               | `binary_sensor` | `bool`   | `true`＝入床 / `false`＝离床                | —    | 状态变化时上报；入床→离床 ~30s 延迟 | 入床/离床检测                                                                        |
| `sleep_state`          | `text_sensor`   | `string` | `"deep"` / `"light"` / `"awake"` / `"none"` | —    | 入床状态下每 10min 上报             | 睡眠阶段                                                                             |
| `awake_duration`       | `sensor`        | `uint16` | `0` ~ `65535`                               | min  | 跟随 `sleep_state` 每 10min 上报    | 累计清醒时长                                                                         |
| `light_sleep_duration` | `sensor`        | `uint16` | `0` ~ `65535`                               | min  | 跟随 `sleep_state` 每 10min 上报    | 累计浅睡时长                                                                         |
| `deep_sleep_duration`  | `sensor`        | `uint16` | `0` ~ `65535`                               | min  | 跟随 `sleep_state` 每 10min 上报    | 累计深睡时长                                                                         |
| `sleep_score`          | `sensor`        | `uint8`  | `0` ~ `100`                                 | —    | 睡眠过程结束时上报（一次性）        | 整晚睡眠质量评分。需满足 4h ≤ 睡眠时长 ≤ 12h，否则评分为 0                           |
| `sleep_quality`        | `text_sensor`   | `string` | `"good"` / `"fair"` / `"poor"` / `"none"`   | —    | 睡眠过程结束时上报（一次性）        | 睡眠质量评级：`good`＝76~100 分，`fair`＝61~75 分，`poor`＝1~60 分，`none`＝评分为 0 |

### 更新频率汇总

| 更新模式           | 涉及 Sensor                                                                    |
| ------------------ | ------------------------------------------------------------------------------ |
| **状态变化时上报** | `presence`、`motion_state`、`breath_state`、`in_bed`、`sleep_quality`          |
| **每 1s**          | `body_movement`                                                                |
| **每 2s**          | `body_distance`、`raw_x/y/z`、`room_x/y/z`、`in_boundary`                      |
| **每 3s**          | `breath_value`、`heart_rate`                                                   |
| **每 10min**       | `sleep_state`、`awake_duration`、`light_sleep_duration`、`deep_sleep_duration` |
| **睡眠结束时**     | `sleep_score`、`sleep_quality`                                                 |

> [!WARNING]
> `heart_rate` 范围是雷达模组硬件限制（60~120 bpm），不适用于心率异常患者的医疗级监测。
> `sleep_score` 和 `sleep_quality` 仅在满足睡眠时长条件（4h ≤ h ≤ 12h）时才输出有效值。

---

## 快速上手：自定义 ESPHome Config 固件

### 两种使用方式

| 方式                   | 适合场景                                  | 说明                                                                                                     |
| ---------------------- | ----------------------------------------- | -------------------------------------------------------------------------------------------------------- |
| **浏览器直刷出厂固件** | 快速体验、无需自定义                      | 访问 [在线安装页](https://zomco.github.io/mmwave-component/)，用 Chrome/Edge 通过 USB 直接刷入，开箱即用 |
| **自定义 YAML 编译**   | 需要修改校准参数、裁剪 Sensor、添加自动化 | 在 ESPHome Dashboard 中新建配置，按下方说明编写 YAML 后编译刷入                                          |

### 固件配置文件结构

仓库中提供了两个示例配置，关系如下：

```
tests/
├── r60abd1-esp32c3.yaml            ← 基础配置（硬件定义 + 全部 Sensor）
└── r60abd1-esp32c3.factory.yaml    ← 出厂配置（!include 基础配置 + OTA/配网等）
```

- **基础配置**（`r60abd1-esp32c3.yaml`）：包含所有硬件参数和 Sensor 定义，**自定义时以此为模板**。
- **出厂配置**（`r60abd1-esp32c3.factory.yaml`）：通过 `!include` 引入基础配置，额外添加 BLE 配网、HTTP OTA 更新等出厂功能，由 CI 自动构建，**用户通常不需要修改**。

### 第 1 步：引入外部组件

```yaml
external_components:
  - source: github://zomco/mmwave-component
    components: [r60abd1]
```

> [!TIP]
> 本地开发时可使用 `source: { type: local, path: ../components }` 指向本地路径。

### 第 2 步：配置 UART

R60ABD1 波特率固定 **115200**，8N1，不可更改。

```yaml
uart:
  id: uart_r60abd1
  tx_pin: GPIO21 # ESP32-C3 → R60ABD1 RXD（交叉接线）
  rx_pin: GPIO20 # ESP32-C3 ← R60ABD1 TXD
  baud_rate: 115200
  data_bits: 8
  parity: NONE
  stop_bits: 1
```

> [!IMPORTANT]
> GPIO 引脚因硬件设计而异。ESP32-C3 默认使用 GPIO20(RX) / GPIO21(TX)，请根据实际 PCB 接线调整。
> 注意 TX/RX 需要**交叉连接**：ESP 的 TX 接雷达的 RX，ESP 的 RX 接雷达的 TX。

### 第 3 步：配置 R60ABD1 组件

#### 最小配置（仅存在检测）

```yaml
r60abd1:
  uart_id: uart_r60abd1
  presence:
    name: "presence"
```

只需声明你需要的 Sensor，未声明的 Sensor 不会被注册，不消耗资源。

#### 完整配置（全部 Sensor + 校准参数）

```yaml
r60abd1:
  id: radar
  uart_id: uart_r60abd1

  # ── 校准参数 ──────────────────────────────────────────────
  # 安装位置：以房间左下角为原点，X 向右，Y 向前（单位 cm）
  radar_x: 200.0 # 雷达距左墙 200cm
  radar_y: 175.0 # 雷达距后墙 175cm
  radar_z: 220.0 # 距地面安装高度 220cm

  # 安装姿态（单位：度）
  yaw: 0.0 # 水平朝向偏差，顺时针为正
  pitch: 0.0 # 俯仰角，向前倾为正
  roll: 0.0 # 横滚角，向右倾为正

  # 房间边界多边形（房间坐标系 cm，< 3 个顶点时不过滤）
  polygon:
    - { x: 0, y: 0 }
    - { x: 400, y: 0 }
    - { x: 400, y: 350 }
    - { x: 0, y: 350 }

  # ── 存在与运动 ────────────────────────────────────────────
  presence:
    name: "presence"
  motion_state:
    name: "motion_state"
  body_movement:
    name: "body_movement"
  body_distance:
    name: "body_distance"

  # ── 原始坐标（调试用，生产环境可删除或设 internal: true）─
  raw_x:
    name: "raw_x"
    internal: true
  raw_y:
    name: "raw_y"
    internal: true
  raw_z:
    name: "raw_z"
    internal: true

  # ── 房间坐标 ──────────────────────────────────────────────
  room_x:
    name: "room_x"
  room_y:
    name: "room_y"
  room_z:
    name: "room_z"
  in_boundary:
    name: "in_boundary"

  # ── 呼吸 ──────────────────────────────────────────────────
  breath_value:
    name: "breath_value"
  breath_state:
    name: "breath_state"

  # ── 心率 ──────────────────────────────────────────────────
  heart_rate:
    name: "heart_rate"

  # ── 睡眠 ──────────────────────────────────────────────────
  in_bed:
    name: "in_bed"
  sleep_state:
    name: "sleep_state"
  awake_duration:
    name: "awake_duration"
  light_sleep_duration:
    name: "light_sleep_duration"
  deep_sleep_duration:
    name: "deep_sleep_duration"
  sleep_score:
    name: "sleep_score"
  sleep_quality:
    name: "sleep_quality"
```

### 第 4 步（可选）：运行时校准参数调整

添加 `number` 实体后，可在 Home Assistant 中实时调整校准参数，无需重新编译固件：

```yaml
number:
  - platform: template
    name: "yaw"
    min_value: -180
    max_value: 180
    step: 0.1
    set_action:
      lambda: "id(radar).set_yaw(x);"

  - platform: template
    name: "pitch"
    min_value: -90
    max_value: 90
    step: 0.5
    set_action:
      lambda: "id(radar).set_pitch(x);"

  - platform: template
    name: "roll"
    min_value: -90
    max_value: 90
    step: 0.5
    set_action:
      lambda: "id(radar).set_roll(x);"

  - platform: template
    name: "radar_x"
    min_value: -2000
    max_value: 2000
    step: 1
    set_action:
      lambda: "id(radar).set_radar_x(x);"

  - platform: template
    name: "radar_y"
    min_value: -2000
    max_value: 2000
    step: 1
    set_action:
      lambda: "id(radar).set_radar_y(x);"

  - platform: template
    name: "radar_z"
    min_value: 0
    max_value: 2000
    step: 1
    set_action:
      lambda: "id(radar).set_radar_z(x);"
```

> [!NOTE]
> 使用 `number` 实体调整的参数仅在运行时生效，设备重启后恢复为 YAML 中的编译期默认值。
> 确认最终校准值后，建议将其写回 YAML 配置并重新编译，以实现持久化。

### 第 5 步：编译与刷写

在 ESPHome Dashboard 中点击 **Install** 即可编译并刷写。首次刷写需 USB 连接，后续可通过 OTA 无线更新。

```bash
# 命令行编译（可选）
esphome compile your-config.yaml
esphome upload your-config.yaml
```

### 校准参数说明

| 参数      | 类型    | 单位 | 默认值     | 说明                                                                         |
| --------- | ------- | ---- | ---------- | ---------------------------------------------------------------------------- |
| `radar_x` | `float` | cm   | `0.0`      | 雷达在房间中的 X 坐标（以房间左下角为原点，向右为正）                        |
| `radar_y` | `float` | cm   | `0.0`      | 雷达在房间中的 Y 坐标（向前为正）                                            |
| `radar_z` | `float` | cm   | `220.0`    | 雷达距地面的安装高度                                                         |
| `yaw`     | `float` | 度   | `0.0`      | 偏航角，雷达正前方相对房间 Y 轴的水平偏差，顺时针为正（−180 ~ 180）          |
| `pitch`   | `float` | 度   | `0.0`      | 俯仰角，向前倾为正（−90 ~ 90）                                               |
| `roll`    | `float` | 度   | `0.0`      | 横滚角，向右倾为正（−90 ~ 90）                                               |
| `polygon` | `list`  | cm   | `[]`（空） | 房间边界多边形顶点列表，每个顶点为 `{ x, y }`。少于 3 个顶点时不启用边界过滤 |
