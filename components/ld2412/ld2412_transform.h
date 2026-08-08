#pragma once

#include <cmath>
#include <cstdint>

namespace esphome {
namespace ld2412 {

struct CalibrationParams {
  float radar_x{0.0f};
  float radar_y{0.0f};
  float radar_z{240.0f};
  float yaw{0.0f};
  float pitch{0.0f};
  float roll{0.0f};
  float distance_min{0.0f};
  float distance_max{0.0f};
};

struct Position3D {
  float room_x;
  float room_y;
  float room_z;
  bool in_boundary;
};

class Transform3D {
 public:
  static Position3D transform(float local_x, float local_y, float local_z, const CalibrationParams &cal) {
    Position3D pos{};
    
    // Radial distance for boundary filtering
    float range_cm = std::sqrt(local_x * local_x + local_y * local_y + local_z * local_z);

    // Convert angles to radians
    float yaw_rad   = cal.yaw   * (M_PI / 180.0f);
    float pitch_rad = cal.pitch * (M_PI / 180.0f);
    float roll_rad  = cal.roll  * (M_PI / 180.0f);

    float cy = std::cos(yaw_rad);
    float sy = std::sin(yaw_rad);
    float cp = std::cos(pitch_rad);
    float sp = std::sin(pitch_rad);
    float cr = std::cos(roll_rad);
    float sr = std::sin(roll_rad);

    // 3D Rotation Matrix elements (Tait-Bryan Z-Y-X)
    float R11 = cy * cp;
    float R12 = cy * sp * sr - sy * cr;
    float R13 = cy * sp * cr + sy * sr;

    float R21 = sy * cp;
    float R22 = sy * sp * sr + cy * cr;
    float R23 = sy * sp * cr - cy * sr;

    float R31 = -sp;
    float R32 = cp * sr;
    float R33 = cp * cr;

    // Apply rotation to local coordinate
    float wx = R11 * local_x + R12 * local_y + R13 * local_z;
    float wy = R21 * local_x + R22 * local_y + R23 * local_z;
    float wz = R31 * local_x + R32 * local_y + R33 * local_z;

    // Apply translation to room coordinate
    pos.room_x = cal.radar_x + wx;
    pos.room_y = cal.radar_y + wy;
    pos.room_z = cal.radar_z - wz; // -wz because z-axis points down from radar but room_z points up from floor

    // Boundary filtering based on radial distance
    pos.in_boundary = true;
    if (cal.distance_min > 0.01f && range_cm < cal.distance_min) {
        pos.in_boundary = false;
    }
    if (cal.distance_max > 0.01f && range_cm > cal.distance_max) {
        pos.in_boundary = false;
    }

    return pos;
  }
};

} // namespace ld2412
} // namespace esphome
