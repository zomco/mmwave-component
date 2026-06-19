# LD2453

海凌科 HLK-LD2453 2D 多目标轨迹雷达 ESPHome 组件。

[English Documentation](./README.md)

## Sensor 参考表

> [!NOTE]
> LD2453 是一款支持最多 3 个目标并发追踪的 2D 轨迹雷达。
> 本组件为每个目标分配了独立的配置块，并利用内置的 3D 矩阵变换引擎，将二维局部坐标（X/Y）结合安装姿态（偏航角、俯仰角、横滚角）直接投射为绝对的三维房间坐标。
> 该雷达使用的默认波特率极高，为 **256000**。

### 目标实体配置块

| YAML Key | Entity 类型 | 数据类型 | 数值范围 | 单位 | 更新频率 | 说明 |
|---|---|---|---|---|---|---|
| `x` | `sensor` | `float` | `-max` ~ `max` | cm | 持续上报 | 目标相对于雷达平面的局部 X 坐标 |
| `y` | `sensor` | `float` | `0` ~ `max` | cm | 持续上报 | 目标相对于雷达平面的局部 Y 坐标 |
| `speed` | `sensor` | `float` | `-max` ~ `max` | cm/s | 持续上报 | 目标的径向移动速度，正数代表远离 |
| `resolution` | `sensor` | `float` | `>= 0` | mm | 持续上报 | 雷达 DSP 锁定的距离门分辨率大小 |
| `room_x` | `sensor` | `float` | — | cm | 持续上报 | 经过姿态修正后的房间绝对 X 坐标 |
| `room_y` | `sensor` | `float` | — | cm | 持续上报 | 经过姿态修正后的房间绝对 Y 坐标 |
| `room_z` | `sensor` | `float` | — | cm | 持续上报 | 经过姿态修正后的房间绝对高度（Z 坐标） |
| `in_boundary` | `binary_sensor`| `bool` | `true`/`false` | — | 持续上报 | 该目标是否位于 `distance_min` 与 `distance_max` 的有效范围内 |

*此外提供一个全局的 `presence` binary_sensor，只要三个目标槽位中有任意一个活跃，即输出 `true`。*

---

## 快速上手：自定义 ESPHome Config 固件

### 第 1 步：引入外部组件

```yaml
external_components:
  - source: github://zomco/mmwave-component
    components: [ld2453]
```

### 第 2 步：配置 UART

注意，LD2453 的波特率为 **256000**。

```yaml
uart:
  id: uart_ld2453
  tx_pin: GPIO21
  rx_pin: GPIO20
  baud_rate: 256000
```

### 第 3 步：配置 LD2453 组件

你可以按需为 Target 1、Target 2、Target 3 分别开启所需的 Sensor。

```yaml
ld2453:
  id: radar
  uart_id: uart_ld2453

  # ── 校准参数 ──────────────────────────────────────────────
  # 安装位置：以房间左下角为原点
  radar_x: 0.0          # 雷达在房间中的 X 坐标
  radar_y: 0.0          # 雷达在房间中的 Y 坐标
  radar_z: 240.0        # 安装高度

  # 安装姿态（度）
  yaw:   0.0            
  pitch: 0.0            # 向前倾斜角度
  roll:  0.0            

  # ── 全局 Sensor ──────────────────────────────────────────
  presence:
    name: "Presence"

  # ── 目标 1 ───────────────────────────────────────────────
  target_1:
    x:
      name: "Target 1 X"
    y:
      name: "Target 1 Y"
    room_x:
      name: "Target 1 Room X"
    room_y:
      name: "Target 1 Room Y"
    room_z:
      name: "Target 1 Room Z"

  # ── 目标 2 ───────────────────────────────────────────────
  target_2:
    x:
      name: "Target 2 X"
    # ... 其他需要的 Sensor
```
