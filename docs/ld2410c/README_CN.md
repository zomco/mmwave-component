# LD2410C ESPHome 组件

本组件将 **LD2410C** 人体存在雷达集成到 ESPHome 中。

LD2410C 是一款一维（1D）存在与运动侦测雷达。通过应用 3D 坐标变换流水线，它能够将其直线探测距离投影到标准的 3D 房间坐标系中，从而与其他统一的雷达组件保持兼容。

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
  distance_max: 300.0   # 最大有效距离边界 (厘米)

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

  # 空间投影实体
  room_x:
    name: "房间 X 坐标"
  room_y:
    name: "房间 Y 坐标"
  room_z:
    name: "房间 Z 坐标"
  in_boundary:
    name: "在边界内"
```
