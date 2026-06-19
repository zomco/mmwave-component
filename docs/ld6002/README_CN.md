# LD6002

海凌科 HLK-LD6002 60 GHz 呼吸心率检测雷达 ESPHome 组件。

[English Documentation](./README.md)

## Sensor 参考表

> [!NOTE]
> LD6002 是一款先进的 60GHz 生物检测雷达。它通过复杂的数据帧格式（`0x01` `ID` `LEN` `TYPE` `CKSUM` `DATA`）输出详细的生命体征数据（包括呼吸频率、心率），并能原生输出目标的 3D 坐标。本组件解析这些数据并通过自定义的 3D 坐标系转换逻辑映射为房间坐标系坐标。

### Entity 类型说明

| ESPHome 类型 | Home Assistant 类型 | 说明 |
|---|---|---|
| `binary_sensor` | `binary_sensor` | 布尔状态（ON/OFF） |
| `sensor` | `sensor` | 数值型传感器 |

### 生物特征与存在检测

| YAML Key | Entity 类型 | 数据类型 | 数值/状态 | 单位 | 更新频率 | 说明 |
|---|---|---|---|---|---|---|
| `presence` | `binary_sensor` | `bool` | `true` / `false` | — | 状态变化时上报 | 人体存在检测（`device_class: presence`） |
| `distance` | `sensor` | `float` | `0` ~ `max_range` | cm | 持续上报 | 人体与雷达之间的直线距离（`device_class: distance`） |
| `respiration_rate` | `sensor` | `float` | `0` ~ `100` | bpm | 持续上报 | 检测到的呼吸频率（次/分钟） |
| `heart_rate` | `sensor` | `float` | `0` ~ `200` | bpm | 持续上报 | 检测到的心率（次/分钟） |

### 人体方位 — 房间坐标（坐标变换后）

| YAML Key | Entity 类型 | 数据类型 | 数值范围 | 单位 | 更新频率 | 说明 |
|---|---|---|---|---|---|---|
| `room_x` | `sensor` | `float`（精度 1 位小数） | 取决于校准参数和房间尺寸 | cm | 持续上报 | 目标在房间坐标系中的 X 坐标 |
| `room_y` | `sensor` | `float`（精度 1 位小数） | 取决于校准参数和房间尺寸 | cm | 持续上报 | 目标在房间坐标系中的 Y 坐标 |
| `room_z` | `sensor` | `float`（精度 1 位小数） | `0` ~ `radar_z` | cm | 持续上报 | 目标距地面高度（`radar_z − wz`） |
| `in_boundary` | `binary_sensor` | `bool` | `true` / `false` | — | 持续上报 | 目标距离是否在配置的范围内（`distance_min` 至 `distance_max`） |

---

## 快速上手：自定义 ESPHome Config 固件

### 第 1 步：引入外部组件

```yaml
external_components:
  - source: github://zomco/mmwave-component
    components: [ld6002]
```

### 第 2 步：配置 UART

LD6002 默认波特率为 **115200**。

```yaml
uart:
  id: uart_ld6002
  tx_pin: GPIO21   # ESP32-C3 → LD6002 RX（交叉接线）
  rx_pin: GPIO20   # ESP32-C3 ← LD6002 TX
  baud_rate: 115200
  data_bits: 8
  parity: NONE
  stop_bits: 1
```

> [!IMPORTANT]
> GPIO 引脚因硬件设计而异。注意 TX/RX 需要**交叉连接**：ESP 的 TX 接雷达的 RX，ESP 的 RX 接雷达的 TX。

### 第 3 步：配置 LD6002 组件

#### 最小配置（仅包含生命体征和存在距离）

```yaml
ld6002:
  uart_id: uart_ld6002
  presence:
    name: "presence"
  distance:
    name: "distance"
  respiration_rate:
    name: "respiration_rate"
  heart_rate:
    name: "heart_rate"
```

#### 完整配置（全部 Sensor + 校准参数）

```yaml
ld6002:
  id: radar
  uart_id: uart_ld6002

  # ── 校准参数 ──────────────────────────────────────────────
  # 安装位置：以房间左下角为原点，X 向右，Y 向前（单位 cm）
  radar_x: 0.0          # 雷达在房间中的 X 坐标
  radar_y: 0.0          # 雷达在房间中的 Y 坐标
  radar_z: 240.0        # 距地面安装高度 240cm

  # 安装姿态（单位：度）
  yaw:   0.0            # 水平朝向偏差，顺时针为正
  pitch: 0.0            # 俯仰角，向前倾为正
  roll:  0.0            # 横滚角，向右倾为正

  # 距离范围过滤（cm，0 = 不过滤）
  distance_min: 30.0
  distance_max: 600.0

  # ── 生物检测 ────────────────────────────────────────────
  presence:
    name: "presence"
  distance:
    name: "distance"
  respiration_rate:
    name: "respiration_rate"
  heart_rate:
    name: "heart_rate"

  # ── 房间坐标 ──────────────────────────────────────────────
  room_x:
    name: "room_x"
  room_y:
    name: "room_y"
  room_z:
    name: "room_z"
  in_boundary:
    name: "in_boundary"
```

### 第 4 步（可选）：运行时校准参数调整

添加 `number` 实体后，可在 Home Assistant 中实时调整校准参数，无需重新编译固件：

```yaml
number:
  - platform: template
    name: "yaw"
    min_value: -180
    max_value:  180
    step: 0.1
    set_action:
      lambda: "id(radar).set_yaw(x);"

  - platform: template
    name: "pitch"
    min_value: -90
    max_value:  90
    step: 0.5
    set_action:
      lambda: "id(radar).set_pitch(x);"

  - platform: template
    name: "roll"
    min_value: -90
    max_value:  90
    step: 0.5
    set_action:
      lambda: "id(radar).set_roll(x);"

  - platform: template
    name: "radar_x"
    min_value: -2000
    max_value:  2000
    step: 1
    set_action:
      lambda: "id(radar).set_radar_x(x);"

  - platform: template
    name: "radar_y"
    min_value: -2000
    max_value:  2000
    step: 1
    set_action:
      lambda: "id(radar).set_radar_y(x);"
```
