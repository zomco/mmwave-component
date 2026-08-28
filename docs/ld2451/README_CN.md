# LD2451

海凌科 HLK-LD2451 2D 多目标轨迹雷达 ESPHome 组件。

[English Documentation](./README.md)

## Sensor 参考表

> [!NOTE]
> LD2451 是一款采用**极坐标（距离和角度）**上报数据的多目标雷达。
> 本组件在代码底层集成了三角函数换算，自动将极坐标转换为局部 X/Y 笛卡尔坐标（单位 cm），然后再通过 3D 转换矩阵投射至全局房间坐标中。
> 插件最大支持解析前 **3** 个目标，串口波特率默认为 **115200**。

### 全局实体配置块

| YAML Key | Entity 类型 | 数据类型 | 数值范围 | 说明 |
|---|---|---|---|---|
| `presence` | `binary_sensor` | `bool` | `true`/`false` | 检测到目标**且**目标在距离门内（见 `boundary_gates_presence`） |
| `target_count` | `sensor` | `int` | `0` ~ `max` | 雷达当前检测到的总目标数量 |
| `alarm` | `binary_sensor` | `bool` | `true`/`false` | 映射雷达内置的“有靠近目标报警”标志位 |
| `target_frame` | `text_sensor` | `json` | — | 10 Hz 原子帧，`{"v":1,"f":…,"ts":…,"t":[[x,y,speed],…]}`，单位 cm 与 cm/s。融合集成读的就是这一条；逐目标实体会在帧边界上撕裂，这条不会 |

### 目标实体配置块

支持 `target_1`, `target_2`, `target_3`，每个块均包含：

| YAML Key | Entity 类型 | 数据类型 | 单位 | 说明 |
|---|---|---|---|---|
| `distance` | `sensor` | `float` | cm | 目标距离。雷达在协议上以整米上报，组件换算后再发布 —— 卡片与融合后端都按 cm 读取 |
| `angle` | `sensor` | `float` | ° | 目标角度（-120°~120°） |
| `speed` | `sensor` | `float` | km/h | 径向速度（正数=靠近，负数=远离） |
| `snr` | `sensor` | `float` | — | 信噪比 (0~255) |
| `x` / `y` | `sensor` | `float` | cm | 由极坐标换算得到的局部坐标 |
| `room_x` / `room_y` / `room_z` | `sensor` | `float` | cm | 经过姿态修正后的房间绝对 3D 坐标 |
| `in_boundary` | `binary_sensor`| `bool` | — | 该目标是否位于 `distance_min` 与 `distance_max` 的有效范围内 |

### 雷达配置回读实体

发布的是雷达**答复**的值，而不是写进去的值，因此写失败时看得见，而不是被默认为
已生效。组件在开机时读一次，之后每次写入后再读一次。

| YAML Key | Entity 类型 | 单位 | 协议 | 说明 |
|---|---|---|---|---|
| `firmware_version` | `text_sensor` | — | 1.2.7 | 例如 `V1.07.24072217` |
| `max_detection_distance` | `sensor` | m | 1.2.4 | 最远检测距离，10~255 |
| `direction_filter` | `text_sensor` | — | 1.2.4 | `away` / `approaching` / `both` |
| `min_speed` | `sensor` | km/h | 1.2.4 | 最小运动速度，0~120 |
| `no_target_delay` | `sensor` | s | 1.2.4 | 无目标延迟时间，0~255 |
| `trigger_count` | `sensor` | — | 1.2.6 | 累积有效触发次数，1~10 |
| `snr_threshold` | `sensor` | — | 1.2.6 | 信噪比阈值等级；0 表示沿用雷达默认值（4），否则 3~8，越大越不灵敏 |

## 写入雷达配置

雷达自身的配置掉电不丢失，由雷达保存，所以组件选择把它读回来，而不是在 ESP 侧
再存一份。四个检测参数在协议里是同一条命令，两个灵敏度参数同理，因此改其中任意
一个都会用上一次查询的结果补齐其余字段后整组重发。每次写入之后都会重新读取一次。

命令以 C++ 方法暴露，在 YAML 中用 `number` / `select` / `button` 模板接上即可。
完整示例见 [`tests/common/ld2451.yaml`](../../tests/common/ld2451.yaml)，出厂
固件用的就是这一套。

| 方法 | 协议 | 说明 |
|---|---|---|
| `set_max_detection_distance(metres)` | 1.2.3 | 10~255 |
| `set_direction_filter(direction)` | 1.2.3 | 0 只检测远离，1 只检测靠近，2 均检测 |
| `set_min_speed(kmh)` | 1.2.3 | 0~120 |
| `set_no_target_delay(seconds)` | 1.2.3 | 0~255 |
| `set_trigger_count(count)` | 1.2.5 | 1~10 |
| `set_snr_threshold(level)` | 1.2.5 | 0 沿用雷达默认值，否则 3~8 |
| `query_detection_params()` / `query_sensitivity_params()` / `query_firmware_version()` | 1.2.4 / 1.2.6 / 1.2.7 | 刷新回读实体 |
| `factory_reset()` | 1.2.9 | 重启模块后生效 |
| `restart_module()` | 1.2.10 | 重启的是雷达模块，不是 ESP |

命令会排队，在同一对「使能配置 / 结束配置」之间依次下发（协议 1.4.1），且不阻塞
`loop()`，所以一批查询只占用一次配置会话而不是每条一次。配置期间雷达停止上报数据，
存在检测看门狗已被告知这段时间属于正常静默。

串口波特率命令（1.2.8）没有暴露：改了会让模块与固件里的 UART 配置对不上。

---

## 快速上手：自定义 ESPHome Config 固件

### 第 1 步：引入外部组件

```yaml
external_components:
  - source: github://zomco/mmwave-component
    components: [ld2451]
```

### 第 2 步：配置 UART

波特率设置为 **115200**。

```yaml
uart:
  id: uart_ld2451
  tx_pin: GPIO21
  rx_pin: GPIO20
  baud_rate: 115200
```

### 第 3 步：配置 LD2451 组件

```yaml
ld2451:
  id: radar
  uart_id: uart_ld2451

  # ── 校准参数 ──────────────────────────────────────────────
  radar_x: 0.0          
  radar_y: 0.0          
  radar_z: 240.0        
  yaw:   0.0            
  pitch: 0.0            
  roll:  0.0            

  # ── 全局 Sensor ──────────────────────────────────────────
  presence:
    name: "Presence"
  alarm:
    name: "Alarm"

  # ── 目标 1 ───────────────────────────────────────────────
  target_1:
    distance:
      name: "Target 1 Distance"
    angle:
      name: "Target 1 Angle"
    room_x:
      name: "Target 1 Room X"
    room_y:
      name: "Target 1 Room Y"
    room_z:
      name: "Target 1 Room Z"
```
