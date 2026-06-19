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
| `presence` | `binary_sensor` | `bool` | `true`/`false` | 只要有检测到目标即为 True |
| `target_count` | `sensor` | `int` | `0` ~ `max` | 雷达当前检测到的总目标数量 |
| `alarm` | `binary_sensor` | `bool` | `true`/`false` | 映射雷达内置的“有靠近目标报警”标志位 |

### 目标实体配置块

支持 `target_1`, `target_2`, `target_3`，每个块均包含：

| YAML Key | Entity 类型 | 数据类型 | 单位 | 说明 |
|---|---|---|---|---|
| `distance` | `sensor` | `float` | m | 目标距离 |
| `angle` | `sensor` | `float` | ° | 目标角度（-120°~120°） |
| `speed` | `sensor` | `float` | km/h | 径向速度（正数=靠近，负数=远离） |
| `snr` | `sensor` | `float` | — | 信噪比 (0~255) |
| `x` / `y` | `sensor` | `float` | cm | 由极坐标换算得到的局部坐标 |
| `room_x` / `room_y` / `room_z` | `sensor` | `float` | cm | 经过姿态修正后的房间绝对 3D 坐标 |
| `in_boundary` | `binary_sensor`| `bool` | — | 该目标是否位于 `distance_min` 与 `distance_max` 的有效范围内 |

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
