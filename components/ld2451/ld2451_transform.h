#pragma once

#include <cmath>
#include <cstdint>
#include <vector>

namespace esphome {
namespace ld2451 {

struct Vec2 {
  float x = 0.f;
  float y = 0.f;
};

struct CalibrationParams {
  float radar_x{0.0f};
  float radar_y{0.0f};
  float radar_z{240.0f};
  float yaw{0.0f};
  float pitch{0.0f};
  float roll{0.0f};
  float distance_min{0.0f};
  float distance_max{0.0f};
  std::vector<Vec2> polygon;  // 房间边界多边形（cm）; 少于 3 个顶点 = 不过滤
};

/**
 * 判断点 (px, py) 是否在多边形内（Ray Casting 算法，O(n)）
 * 顶点不足 3 个时始终返回 true（不过滤）
 */
inline bool point_in_polygon(float px, float py, const std::vector<Vec2> &polygon) {
  const size_t n = polygon.size();
  if (n < 3)
    return true;

  bool inside = false;
  for (size_t i = 0, j = n - 1; i < n; j = i++) {
    const float xi = polygon[i].x, yi = polygon[i].y;
    const float xj = polygon[j].x, yj = polygon[j].y;
    const bool cross = ((yi > py) != (yj > py)) && (px < (xj - xi) * (py - yi) / (yj - yi) + xi);
    if (cross)
      inside = !inside;
  }
  return inside;
}

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
    float yaw_rad = cal.yaw * (M_PI / 180.0f);
    float pitch_rad = cal.pitch * (M_PI / 180.0f);
    float roll_rad = cal.roll * (M_PI / 180.0f);

    float cy = std::cos(yaw_rad);
    float sy = std::sin(yaw_rad);
    float cp = std::cos(pitch_rad);
    float sp = std::sin(pitch_rad);
    float cr = std::cos(roll_rad);
    float sr = std::sin(roll_rad);

    // Room-frame convention, shared with mmwave-card / HA mmwave_fusion / r60abd1:
    //   R = Rz(yaw) * Rx(pitch) * Ry(roll)
    // yaw = 0 aims the radar boresight along room +Y; positive yaw turns clockwise
    // seen from above (toward +X). Roll is rotation about the boresight itself.
    float R11 = cy * cr + sy * sp * sr;
    float R12 = sy * cp;
    float R13 = -cy * sr + sy * sp * cr;

    float R21 = -sy * cr + cy * sp * sr;
    float R22 = cy * cp;
    float R23 = sy * sr + cy * sp * cr;

    float R31 = cp * sr;
    float R32 = -sp;
    float R33 = cp * cr;

    // Apply rotation to local coordinate
    float wx = R11 * local_x + R12 * local_y + R13 * local_z;
    float wy = R21 * local_x + R22 * local_y + R23 * local_z;
    float wz = R31 * local_x + R32 * local_y + R33 * local_z;

    // Apply translation to room coordinate
    pos.room_x = cal.radar_x + wx;
    pos.room_y = cal.radar_y + wy;
    pos.room_z = cal.radar_z - wz;  // -wz because z-axis points down from radar but room_z points up from floor

    // Boundary filtering: radial distance gate AND room-frame polygon (ray casting).
    // The polygon is evaluated post-transform, in room coordinates.
    pos.in_boundary = true;
    if (cal.distance_min > 0.01f && range_cm < cal.distance_min) {
      pos.in_boundary = false;
    }
    if (cal.distance_max > 0.01f && range_cm > cal.distance_max) {
      pos.in_boundary = false;
    }
    if (pos.in_boundary && !point_in_polygon(pos.room_x, pos.room_y, cal.polygon)) {
      pos.in_boundary = false;
    }

    return pos;
  }
};

}  // namespace ld2451
}  // namespace esphome
