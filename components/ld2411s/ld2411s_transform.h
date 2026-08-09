#pragma once
/**
 * ld2411s_transform.h
 *
 * 一维测距坐标变换 + 距离范围边界过滤
 *
 * 旋转顺序: R = Rz(yaw) · Rx(pitch) · Ry(roll)
 * 房间坐标约定: yaw=0 时雷达正前方指向房间 +Y，yaw 俯视顺时针为正
 * （与 mmwave-card / HA mmwave_fusion / r60abd1 保持一致）
 *
 * 雷达局部坐标系约定:
 *   Y 轴 — 雷达正前方（距离方向）
 *   X 轴 — 无（1-D 雷达无角度分辨）
 *   Z 轴 — 无
 *   单位 — cm
 *
 * LD2411S 为 1-D 雷达（仅输出距离），变换时将距离投射到
 * 雷达正前方 +Y: local = (0, range, 0)
 */

#include <cmath>
#include <cstdint>

#ifndef M_PI
#define M_PI 3.14159265358979323846f
#endif

namespace esphome {
namespace ld2411s {

struct CalibrationParams {
  float radar_x{0.0f};       // 雷达在房间中的 X 位置（cm）
  float radar_y{0.0f};       // 雷达在房间中的 Y 位置（cm）
  float radar_z{240.0f};     // 雷达安装高度（cm）
  float yaw{0.0f};           // 偏航角（°，俯视顺时针为正）
  float pitch{0.0f};         // 俯仰角（°，向前倾为正）
  float roll{0.0f};          // 横滚角（°，绕正前方轴）
  float distance_min{0.0f};  // 最小距离过滤（cm），0 = 不过滤
  float distance_max{0.0f};  // 最大距离过滤（cm），0 = 不过滤
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

    // LD2411S is a 1-D radar; the target is projected along the boresight (local +Y)
    float local_y = range_cm;

    float yaw_rad = cal.yaw * (M_PI / 180.0f);
    float pitch_rad = cal.pitch * (M_PI / 180.0f);

    float cy = std::cos(yaw_rad);
    float sy = std::sin(yaw_rad);
    float cp = std::cos(pitch_rad);
    float sp = std::sin(pitch_rad);

    // Room-frame convention: R = Rz(yaw) * Rx(pitch) * Ry(roll), boresight = local +Y.
    // Only column 1 of R is needed; roll turns about the boresight and cancels out.
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

}  // namespace ld2411s
}  // namespace esphome
