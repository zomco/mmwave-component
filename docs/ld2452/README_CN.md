# ld2452

海凌�?HLK-ld2452 24 GHz 毫米波多目标轨迹跟踪雷达 �?ESPHome 组件�?

[English Documentation](./README.md)

## 传感器参�?

> [!NOTE]
> 本表格数据已与产品说明书、ESPHome 组件源码�?YAML 配置进行交叉验证�?
> 生成 Home Assistant 卡片�?AI 工具请参考本表以获取实体类型、数值范围及更新频率�?

### 实体类型

| ESPHome 类型 | Home Assistant 类型 | 说明 |
|---|---|---|
| `binary_sensor` | `binary_sensor` | 布尔状态（开/关） |
| `sensor` | `sensor` | 数值型传感�?|

### 全局存在检�?

| YAML 键名 | 实体类型 | 数据类型 | 数�?/ 状�?| 单位 | 更新频率 | 说明 |
|---|---|---|---|---|---|---|
| `presence` | `binary_sensor` | `bool` | `true` / `false` | �?| 状态变化时 | 有人存在检测（`device_class: presence`）。任一目标活动时即�?true |

### 多目标追踪（目标 1�?�?�?

针对每个目标 `n`�?�? �?3），可配置以下实体：

| YAML 键名 | 实体类型 | 数据类型 | 数值范�?| 单位 | 更新频率 | 说明 |
|---|---|---|---|---|---|---|
| `target_n_x` | `sensor` | `int16` | 视房间大小而定 | mm | �?100ms (10Hz) | 雷达局部坐标系 X 轴（左负右正�?|
| `target_n_y` | `sensor` | `int16` | 视房间大小而定 | mm | �?100ms (10Hz) | 雷达局部坐标系 Y 轴（前方为正�?|
| `target_n_speed` | `sensor` | `int16` | | cm/s | �?100ms (10Hz) | 目标移动速度（正向远离，负向靠近�?|
| `target_n_resolution` | `sensor` | `uint16` | | mm | �?100ms (10Hz) | 距离分辨�?|
| `target_n_distance` | `sensor` | `float` | 视房间大小而定 | cm | �?100ms (10Hz) | 计算所得的目标直线距离 |
| `target_n_angle` | `sensor` | `float` | `-180` ~ `+180` | ° | �?100ms (10Hz) | 计算所得的目标角度 |
| `target_n_room_x` | `sensor` | `float` | 视房间大小而定 | cm | �?100ms (10Hz) | 目标在房间坐标系中的 X 坐标 |
| `target_n_room_y` | `sensor` | `float` | 视房间大小而定 | cm | �?100ms (10Hz) | 目标在房间坐标系中的 Y 坐标 |
| `target_n_active` | `binary_sensor` | `bool` | `true` / `false` | �?| 状态变化时 | 当前目标是否被追�?|
| `target_n_in_boundary` | `binary_sensor` | `bool` | `true` / `false` | �?| �?100ms (10Hz) | 目标是否在配置的多边形边界内 |

> [!IMPORTANT]
> `target_n_room_x/y` �?`target_n_in_boundary` 是在 ESP 端计算生成的派生数据�?
> 它们的数值取决于 YAML 中配置的校准参数（`radar_x/y/z`，`yaw/pitch/roll`）及多边形边界（`polygon`）�?

### 更新频率汇�?

| 更新模式 | 传感�?|
|---|---|
| **状态变化时** | `presence`, `target_n_active` |
| **�?100ms (10Hz)** | 所有位置、速度、距离、角度及边界传感�?|

---

## 快速上手：自定�?ESPHome 固件

### 固件配置文件结构

代码库提供了两个示例配置文件，关系如下：

```
tests/
├── ld2452-esp32c3.yaml            �?基础配置（硬件参�?+ 所有传感器�?
└── ld2452-esp32c3.factory.yaml    �?工厂配置（通过 !include 引入基础配置 + OTA/配网功能�?
```

- **基础配置** (`ld2452-esp32c3.yaml`)：包含所有硬件参数和传感器定义�?*请将其作为自定义的模板�?*
- **工厂配置** (`ld2452-esp32c3.factory.yaml`)：通过 `!include` 引入基础配置，并添加蓝牙配网、HTTP OTA 更新等功能。由 CI 自动构建 �?**用户通常无需修改此文件�?*

### 第一步：添加外部组件

```yaml
external_components:
  - source: github://zomco/mmwave-component
    components: [ld2452]
```

### 第二步：配置 UART

ld2452 采用固定�?**256000** 波特率（8N1）。此设置不可更改�?

```yaml
uart:
  id: uart_ld2452
  tx_pin: GPIO21   # ESP32-C3 �?ld2452 RX (交叉接线)
  rx_pin: GPIO20   # ESP32-C3 �?ld2452 TX
  baud_rate: 256000
  data_bits: 8
  parity: NONE
  stop_bits: 1
```

> [!IMPORTANT]
> GPIO 引脚定义因硬件设计而异。ESP32-C3 的默认配置为 GPIO20 (RX) / GPIO21 (TX) �?请根据实际的 PCB 接线进行调整�?
> TX/RX 必须**交叉连接**：ESP TX �?雷达 RX，ESP RX �?雷达 TX�?

### 第三步：配置 ld2452 组件

#### 最简配置（仅人体存在�?

```yaml
ld2452:
  uart_id: uart_ld2452
  presence:
    name: "presence"
```

仅声明所需的传感器 �?未声明的传感器不会被注册，也不占用系统资源�?

#### 完整配置（所有传感器 + 校准参数�?

```yaml
ld2452:
  id: radar
  uart_id: uart_ld2452

  # ── 全局存在检�?───────────────────────────────────────
  presence:
    name: "presence"

  # ── 目标 1 ──────────────────────────────────────────────
  target_1_x:
    name: "target_1_x"
  target_1_y:
    name: "target_1_y"
  target_1_speed:
    name: "target_1_speed"
  target_1_distance:
    name: "target_1_distance"
  target_1_angle:
    name: "target_1_angle"
  target_1_room_x:
    name: "target_1_room_x"
  target_1_room_y:
    name: "target_1_room_y"
  target_1_active:
    name: "target_1_active"
  target_1_in_boundary:
    name: "target_1_in_boundary"

  # 如有需要，可按相同模式添加 target_2_x, target_3_x �?
```

### 第四�?(可�?：运行时校准调整与控制命�?

通过添加 `number` 实体，可以在 Home Assistant 中实时调整校准参数，无需重新编译；添�?`button` 实体可向雷达发送控制命令：

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

button:
  - platform: template
    name: "set_multi_target"
    on_press:
      lambda: "id(radar).set_multi_target_mode();"

  - platform: template
    name: "set_single_target"
    on_press:
      lambda: "id(radar).set_single_target_mode();"

  - platform: template
    name: "restart_radar"
    on_press:
      lambda: "id(radar).restart_module();"

text:
  - platform: template
    name: "Polygon Config"
    id: text_polygon
    min_length: 0
    max_length: 255
    optimistic: true
    mode: text
    icon: mdi:vector-polygon
    set_action:
      - lambda: "id(g_polygon) = x;"
      - script.execute: apply_polygon
```

> [!NOTE]
> 通过 `number` �?`text` 实体调整的参数将在运行时即刻生效。同时，这些参数会自动保存至设备�?Flash 闪存中，设备重启后也会自动恢复�?

### 校准参数说明

| 参数�?| 类型 | 单位 | 默认�?| 说明 |
|---|---|---|---|---|
| `radar_x` | `float` | cm | `0.0` | 雷达在房间中�?X 坐标（以左下角为原点，向右为正） |
| `radar_y` | `float` | cm | `0.0` | 雷达在房间中�?Y 坐标（向前为正） |
| `radar_z` | `float` | cm | `150.0` | 雷达距地面的安装高度（推�?100-150cm�?|
| `yaw` | `float` | �?| `0.0` | 偏航�?�?雷达正前方相对房�?Y 轴的水平偏差，顺时针为正 (�?80 ~ 180) |
| `pitch` | `float` | �?| `0.0` | 俯仰�?�?向前倾斜为正 (�?0 ~ 90) |
| `roll` | `float` | �?| `0.0` | 横滚�?�?向右倾斜为正 (�?0 ~ 90) |
| `polygon` | `list` | cm | `[]` (�? | 房间边界多边形顶点，格式�?`{ x, y }`。顶点数少于 3 个时关闭边界过滤 |
