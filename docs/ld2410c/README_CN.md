# LD2410C ESPHome 组件

本组件将 **LD2410C** 人体存在雷达集成到 ESPHome 中。

[English Documentation](./README.md)

LD2410C 是一款一维（1D）存在与运动侦测雷达：8 个距离门，每门 0.75 m（或
0.20 m），最远 6 m，水平覆盖 ±60°，串口波特率 256000。通过 3D 坐标变换流水线，
它能够将其直线探测距离投影到标准的 3D 房间坐标系中，从而与其他统一的雷达组件
保持兼容。

## Sensor 参考表

### 探测实体

| YAML Key | Entity 类型 | 单位 | 说明 |
|---|---|---|---|
| `presence` | `binary_sensor` | — | 检测到目标**且**目标在距离门内（见 `boundary_gates_presence`） |
| `target_state` | `sensor` | — | 原始状态字节：0 无目标，1 运动，2 静止，3 运动&静止，4~6 底噪检测中/成功/失败 |
| `moving_distance` | `sensor` | cm | 运动目标距离 |
| `moving_energy` | `sensor` | — | 运动目标能量值，0~100 |
| `stationary_distance` | `sensor` | cm | 静止目标距离 |
| `stationary_energy` | `sensor` | — | 静止目标能量值，0~100 |
| `detection_distance` | `sensor` | cm | 雷达上报的探测距离，坐标变换用的就是这个值 |
| `max_distance` | `sensor` | cm | 已配置的最大距离门 × 距离分辨率，跟随雷达实际配置而非数据手册常数。仅工程模式 |

### 工程模式实体

组件在 setup() 时开启工程模式（该配置掉电丢失，因此每次上电都要重发），
开启后每帧会追加各距离门能量值、模块自带光敏二极管读数与 OUT 引脚状态。

| YAML Key | Entity 类型 | 单位 | 说明 |
|---|---|---|---|
| `g0` … `g8` → `gate_move_energy` | `sensor` | — | 该距离门的运动能量值，0~100 |
| `g0` … `g8` → `gate_still_energy` | `sensor` | — | 该距离门的静止能量值，0~100 |
| `light` | `sensor` | — | 光敏检测值，0~255。不是照度：数据手册未给出换算关系 |
| `out_pin` | `binary_sensor` | — | 模块 OUT 引脚的实际输出。开启光感辅助控制后会与 `presence` 不同 |

### 空间投影实体

| YAML Key | Entity 类型 | 单位 | 说明 |
|---|---|---|---|
| `room_x` / `room_y` / `room_z` | `sensor` | cm | 按下方校准参数投影到房间坐标系的探测距离 |
| `in_boundary` | `binary_sensor` | — | 目标是否落在 `distance_min` 与 `distance_max` 之间 |

### 雷达配置回读实体

发布的是雷达**答复**的值，而不是写进去的值，因此写失败时看得见，而不是被默认为
已生效。组件在开机时读一次，之后每次写入后再读一次。

| YAML Key | Entity 类型 | 单位 | 协议 | 说明 |
|---|---|---|---|---|
| `firmware_version` | `text_sensor` | — | 2.2.8 | 例如 `V2.68.25070917` |
| `max_moving_gate` | `sensor` | — | 2.2.4 | 运动探测最远距离门，2~8 |
| `max_still_gate` | `sensor` | — | 2.2.4 | 静止探测最远距离门，2~8 |
| `unmanned_duration` | `sensor` | s | 2.2.4 | 无人持续时间 |
| `distance_resolution` | `sensor` | m | 2.2.17 | 每个距离门代表的距离：0.75 或 0.20 |
| `gate_sensitivity` | `text_sensor` | — | 2.2.4 | 9 个距离门的 `move a,b,…|still a,b,…` |
| `noise_floor_status` | `text_sensor` | — | 2.2.21 | `idle` / `running` / `finished` / `failed` |

## 配置变量

```yaml
ld2410c:
  id: my_radar
  uart_id: uart_bus

  # 校准参数
  radar_x: 0.0          # 雷达在房间的 X 坐标 (厘米)
  radar_y: 0.0          # 雷达在房间的 Y 坐标 (厘米)
  radar_z: 240.0        # 雷达离地高度 Z 坐标 (厘米)
  yaw: 0.0              # 偏航角 (度，左右旋转)
  pitch: 0.0            # 俯仰角 (度，上下倾斜)
  roll: 0.0             # 横滚角 (度)
  distance_min: 0.0     # 最小有效距离边界 (厘米)
  distance_max: 600.0   # 最大有效距离边界 (厘米)

  # 距离门外的目标是否仍计入 presence。默认 true，与其他型号一致：
  # 界外目标在距离传感器上依然可见，但不会把 presence 置为 on。
  boundary_gates_presence: true

  # 雷达输出实体
  presence:
    name: "存在状态"
  target_state:
    name: "目标状态"
  moving_distance:
    name: "运动目标距离"
  moving_energy:
    name: "运动能量"
  stationary_distance:
    name: "静止目标距离"
  stationary_energy:
    name: "静止能量"
  detection_distance:
    name: "探测距离"
  max_distance:
    name: "最大探测距离"

  # 工程模式附加数据
  light:
    name: "光感值"
  out_pin:
    name: "OUT 引脚状态"
  g0:
    gate_move_energy:
      name: "距离门 0 运动能量"
    gate_still_energy:
      name: "距离门 0 静止能量"
  # … g1 至 g8

  # 空间投影实体
  room_x:
    name: "房间 X 坐标"
  room_y:
    name: "房间 Y 坐标"
  room_z:
    name: "房间 Z 坐标"
  in_boundary:
    name: "在边界内"

  # 雷达配置回读
  firmware_version:
    name: "雷达固件版本"
  max_moving_gate:
    name: "运动最远距离门"
  max_still_gate:
    name: "静止最远距离门"
  unmanned_duration:
    name: "无人持续时间"
  distance_resolution:
    name: "距离分辨率"
  gate_sensitivity:
    name: "距离门灵敏度"
  noise_floor_status:
    name: "底噪检测状态"
```

## 写入雷达配置

雷达自身的配置掉电不丢失，由雷达保存，所以组件选择把它读回来，而不是在 ESP 侧
再存一份 —— 两份配置一旦不一致，就再也说不清哪一份是真的。每次写入之后都会重新
读取一次。

命令以 C++ 方法暴露，在 YAML 中用 `number` / `select` / `button` 模板接上即可。
完整示例见 [`tests/common/ld2410c.yaml`](../../tests/common/ld2410c.yaml)，出厂
固件用的就是这一套。

| 方法 | 协议 | 说明 |
|---|---|---|
| `set_max_moving_gate(gate)` | 2.2.3 | 2~8。与静止距离门、无人持续时间打包成一条命令下发 |
| `set_max_still_gate(gate)` | 2.2.3 | 2~8 |
| `set_unmanned_duration(seconds)` | 2.2.3 | 0~65535 |
| `set_gate_sensitivity(gate, move, still)` | 2.2.7 | 各 0~100；门号传 `ALL_GATES`（0xFFFF）可统一设置全部距离门 |
| `request_distance_resolution(index)` | 2.2.16 | 0 = 0.75 m，1 = 0.20 m。**重启模块后才生效**，因此在重启前回读值仍是旧的 |
| `set_light_control_mode(mode)` | 2.2.18 | 0 关闭，1 光感值小于阈值时条件满足，2 大于阈值时满足 |
| `set_light_threshold(value)` | 2.2.18 | 0~255 |
| `set_out_pin_level(level)` | 2.2.18 | 0 = OUT 默认低电平，1 = 默认高电平 |
| `start_noise_floor_calibration(seconds)` | 2.2.20 | 所有人须离开探测范围；模块等 10 秒后开始统计底噪，完成后自动配置各距离门灵敏度 |
| `query_parameters()` / `query_firmware_version()` / `query_distance_resolution()` / `query_light_control()` / `query_noise_floor_status()` | 2.2.4 / 2.2.8 / 2.2.17 / 2.2.19 / 2.2.21 | 刷新回读实体 |
| `factory_reset()` | 2.2.10 | 重启模块后生效 |
| `restart_module()` | 2.2.11 | 重启的是雷达模块，不是 ESP |

命令会排队，在同一对「使能配置 / 结束配置」之间依次下发（协议 2.4.1），且不阻塞
`loop()`，所以一批查询只占用一次配置会话而不是每条一次。配置期间雷达停止上报数据，
UART 看门狗已被告知这段时间属于正常静默。

## 未实现的命令

协议还定义了串口波特率（2.2.9）以及蓝牙开关、MAC 地址、蓝牙密码
（2.2.12~2.2.15）。改波特率或关蓝牙都会让模块与固件里的 UART 配置对不上，
因此都没有暴露。
