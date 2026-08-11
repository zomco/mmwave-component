#pragma once

#include <cmath>
#include <cstdint>

namespace esphome {
namespace ld2450a {

struct CalibrationParams {
  float radar_x{0.0f};
  float radar_y{0.0f};
  float radar_z{150.0f};
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

    // LD2450A is a 1-D ranging and gesture recognition radar, target is projected along local +Y axis
    float local_y = range_cm;

    // Convert angles to radians
    float yaw_rad = cal.yaw * (M_PI / 180.0f);
    float pitch_rad = cal.pitch * (M_PI / 180.0f);

    float cy = std::cos(yaw_rad);
    float sy = std::sin(yaw_rad);
    float cp = std::cos(pitch_rad);
    float sp = std::sin(pitch_rad);

    // Room-frame convention: R = Rz(yaw) * Rx(pitch) * Ry(roll), boresight = local +Y.
    // Column 1 of R; roll turns about the boresight and cancels out.
    float R12 = sy * cp;
    float R22 = cy * cp;
    float R32 = -sp;

    // Global world offsets
    float wx = R12 * local_y;
    float wy = R22 * local_y;
    float wz = R32 * local_y;

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

}  // namespace ld2450a
}  // namespace esphome
