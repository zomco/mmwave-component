# LD2410C ESPHome Component

This component integrates the **LD2410C** human presence radar into ESPHome.

The LD2410C is a 1D presence and motion tracking radar. By applying a 3D coordinate transformation pipeline, it projects its linear detection distance into a standard 3D room coordinate space, making it compatible with other unified radar components.

## Configuration Variables

```yaml
ld2410c:
  id: my_radar
  uart_id: uart_bus
  
  # Calibration parameters
  radar_x: 0.0          # Radar X position in room (cm)
  radar_y: 0.0          # Radar Y position in room (cm)
  radar_z: 240.0        # Radar height from floor (cm)
  yaw: 0.0              # Pan angle (degrees, left/right)
  pitch: 0.0            # Tilt angle (degrees, up/down)
  roll: 0.0             # Roll angle (degrees)
  distance_min: 0.0     # Minimum valid distance boundary (cm)
  distance_max: 300.0   # Maximum valid distance boundary (cm)

  # Radar Output Entities
  presence:
    name: "Presence"
  target_state:
    name: "Target State"
  moving_distance:
    name: "Moving Distance"
  moving_energy:
    name: "Moving Energy"
  stationary_distance:
    name: "Stationary Distance"
  stationary_energy:
    name: "Stationary Energy"
  detection_distance:
    name: "Detection Distance"

  # Spatial Projection Entities
  room_x:
    name: "Room X"
  room_y:
    name: "Room Y"
  room_z:
    name: "Room Z"
  in_boundary:
    name: "In Boundary"
```
