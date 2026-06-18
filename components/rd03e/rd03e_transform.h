#pragma once
/**
 * rd03e_transform.h
 *
 * 一维测距坐标变换 + 距离范围边界过滤
 *
 * 旋转顺序: Rz(yaw) · Rx(pitch) · Ry(roll)
 *
 * 雷达局部坐标系约定:
 *   X 轴 — 雷达正前方（距离方向）
 *   Y 轴 — 无（1-D 雷达无角度分辨）
 *   Z 轴 — 无
 *   单位 — cm
 *   编码 — 小端 uint16，直接表示距离
 *
 * RD03E 为 1-D 雷达（仅输出距离），变换时将距离投射到
 * 雷达 +X 方向: local = (range, 0, 0)
 */

#include <cmath>
#include <cstdint>

#ifndef M_PI
#define M_PI 3.14159265358979323846f
#endif

namespace esphome {
namespace rd03e {

// ─── 基础数据结构 ─────────────────────────────────────────────────────────────

struct Vec2 {
  float x = 0.f;
  float y = 0.f;
};

struct CalibrationParams {
  float radar_x      = 0.f;   // 雷达在房间中的 X 位置（cm）
  float radar_y      = 0.f;   // 雷达在房间中的 Y 位置（cm）
  float radar_z      = 240.f; // 雷达安装高度（cm）
  float yaw          = 0.f;   // 偏航角（°，顺时针为正）
  float pitch        = 0.f;   // 俯仰角（°，向前倾为正）
  float roll         = 0.f;   // 横滚角（°，向右倾为正）
  float distance_min = 0.f;   // 最小距离过滤（cm），0 = 不过滤
  float distance_max = 0.f;   // 最大距离过滤（cm），0 = 不过滤
};

struct TransformResult {
  Vec2  room;          // 变换后的房间水平坐标（cm）
  float room_z;        // 目标距地面高度（cm）= radar_z - wz
  bool  in_boundary;   // 是否在距离范围内（distance_min/max 均为 0 时始终 true）
};

// ─── 旋转矩阵 ────────────────────────────────────────────────────────────────

struct Mat3 { float m[3][3] = {}; };

/**
 * 构建旋转矩阵 R = Rz(yaw) · Rx(pitch) · Ry(roll)
 *
 *         ┌ cγcβ+sγsαsβ   sγcα   −cγsβ+sγsαcβ ┐
 * R(γαβ) = │−sγcβ+cγsαsβ   cγcα    sγsβ+cγsαcβ │
 *         └ cαsβ          −sα      cαcβ          ┘
 */
inline Mat3 build_rotation(float yaw_deg, float pitch_deg, float roll_deg) {
  const float D2R = static_cast<float>(M_PI) / 180.f;
  const float g   = yaw_deg   * D2R;
  const float a   = pitch_deg * D2R;
  const float b   = roll_deg  * D2R;

  const float sg = sinf(g), cg = cosf(g);
  const float sa = sinf(a), ca = cosf(a);
  const float sb = sinf(b), cb = cosf(b);

  Mat3 R;
  R.m[0][0] =  cg*cb + sg*sa*sb;  R.m[0][1] = sg*ca;  R.m[0][2] = -cg*sb + sg*sa*cb;
  R.m[1][0] = -sg*cb + cg*sa*sb;  R.m[1][1] = cg*ca;  R.m[1][2] =  sg*sb + cg*sa*cb;
  R.m[2][0] =  ca*sb;              R.m[2][1] = -sa;    R.m[2][2] =  ca*cb;
  return R;
}

// ─── 距离范围过滤 ─────────────────────────────────────────────────────────────

/**
 * 判断原始距离是否在 [distance_min, distance_max] 范围内
 * 若两者均为 0，则不过滤（始终返回 true）
 */
inline bool in_distance_range(float distance_cm,
                               float distance_min, float distance_max) {
  if (distance_min <= 0.f && distance_max <= 0.f) return true;
  if (distance_min > 0.f && distance_cm < distance_min) return false;
  if (distance_max > 0.f && distance_cm > distance_max) return false;
  return true;
}

// ─── 主变换函数 ──────────────────────────────────────────────────────────────

/**
 * 将 1-D 雷达距离变换到房间坐标系
 *
 * 步骤：
 *   1. 将距离投射到雷达局部 X 轴: local = (range, 0, 0)
 *   2. R = Rz(yaw) · Rx(pitch) · Ry(roll)
 *   3. world_vec = R * [range, 0, 0]ᵀ
 *   4. room.x = radar_x + world_vec.x
 *      room.y = radar_y + world_vec.y
 *      room_z = radar_z − world_vec.z
 *   5. 距离范围过滤
 */
inline TransformResult apply(float range_cm,
                              const CalibrationParams& cal) {
  const Mat3 R = build_rotation(cal.yaw, cal.pitch, cal.roll);

  // 1-D: 仅沿 X 轴投射，Y=Z=0
  const float wx = R.m[0][0] * range_cm;
  const float wy = R.m[1][0] * range_cm;
  const float wz = R.m[2][0] * range_cm;

  TransformResult res;
  res.room.x      = cal.radar_x + wx;
  res.room.y      = cal.radar_y + wy;
  res.room_z      = cal.radar_z - wz;
  res.in_boundary = in_distance_range(range_cm, cal.distance_min, cal.distance_max);
  return res;
}

} // namespace rd03e
} // namespace esphome
