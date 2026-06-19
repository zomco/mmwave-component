#pragma once

#include <cmath>
#include <cstdint>

namespace esphome {
namespace ld2411 {

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

struct Position1D {
  float room_x;
  float room_y;
  float room_z;
  bool in_boundary;
};

class Transform1D {
 public:
  static Position1D transform(float range_cm, const CalibrationParams &cal) {
    Position1D pos{};
    
    // LD2411 is a 1-D radar, target is projected along local +X axis
    float local_x = range_cm;

    // Convert angles to radians
    float yaw_rad   = cal.yaw   * (M_PI / 180.0f);
    float pitch_rad = cal.pitch * (M_PI / 180.0f);
    float roll_rad  = cal.roll  * (M_PI / 180.0f);

    float cy = std::cos(yaw_rad);
    float sy = std::sin(yaw_rad);
    float cp = std::cos(pitch_rad);
    float sp = std::sin(pitch_rad);

    // Rotation matrix elements for local +X projection
    float R11 = cy * cp;
    float R21 = sy * cp;
    float R31 = -sp;

    // Global world offsets
    float wx = R11 * local_x;
    float wy = R21 * local_x;
    float wz = R31 * local_x;

    pos.room_x = cal.radar_x + wx;
    pos.room_y = cal.radar_y + wy;
    pos.room_z = cal.radar_z - wz;

    // 1-D boundary filtering: simple distance gate
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

} // namespace ld2411
} // namespace esphome
