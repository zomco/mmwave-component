#pragma once
/**
 * r60abd1_transform.h
 *
 * 三维坐标变换 + 房间边界过滤（射线法）
 *
 * 旋转顺序: Rz(yaw) · Rx(pitch) · Ry(roll)
 *
 * 雷达局部坐标系约定（手册 v2.5 勘误后）:
 *   Y 轴 — 雷达正前方
 *   X 轴 — 右正左负
 *   Z 轴 — 垂直天线面向外为正
 *   单位 — cm
 *   编码 — bit15=符号(0=正,1=负), bit14-0=15位幅值
 */

#include <cmath>
#include <cstdint>
#include <vector>

#ifndef M_PI
#define M_PI 3.14159265358979323846f
#endif

namespace esphome {
namespace r60abd1 {

// ─── 坐标解码 ────────────────────────────────────────────────────────────────

/**
 * 将 R60ABD1 输出的两字节坐标解码为有符号整数（cm）
 * 手册 v2.5 修正：bit15=符号, bit14-0=15位幅值
 */
inline int16_t decode_coord(uint8_t high, uint8_t low) {
  const uint16_t raw   = (static_cast<uint16_t>(high) << 8) | low;
  const bool negative  = (raw >> 15) & 1u;
  const uint16_t value = raw & 0x7FFFu;
  return negative ? -static_cast<int16_t>(value)
                  :  static_cast<int16_t>(value);
}

// ─── 基础数据结构 ─────────────────────────────────────────────────────────────

struct Vec2 {
  float x = 0.f;
  float y = 0.f;
};

struct CalibrationParams {
  float radar_x      = 0.f;   // 雷达在房间中的 X 位置（cm）
  float radar_y      = 0.f;   // 雷达在房间中的 Y 位置（cm）
  float radar_height = 220.f; // 雷达安装高度（cm）
  float yaw          = 0.f;   // 偏航角（°，顺时针为正）
  float pitch        = 0.f;   // 俯仰角（°，向前倾为正）
  float roll         = 0.f;   // 横滚角（°，向右倾为正）
  std::vector<Vec2> polygon;  // 房间边界多边形（cm）; 空 = 不过滤
};

struct TransformResult {
  Vec2  room;             // 变换后的房间水平坐标（cm）
  float height_floor_cm; // 目标距地面高度（cm）= radar_height - wz
  bool  in_boundary;     // 是否在多边形内（polygon 为空时始终 true）
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
  const float γ   = yaw_deg   * D2R;
  const float α   = pitch_deg * D2R;
  const float β   = roll_deg  * D2R;

  const float sγ = sinf(γ), cγ = cosf(γ);
  const float sα = sinf(α), cα = cosf(α);
  const float sβ = sinf(β), cβ = cosf(β);

  Mat3 R;
  R.m[0][0] =  cγ*cβ + sγ*sα*sβ;  R.m[0][1] = sγ*cα;  R.m[0][2] = -cγ*sβ + sγ*sα*cβ;
  R.m[1][0] = -sγ*cβ + cγ*sα*sβ;  R.m[1][1] = cγ*cα;  R.m[1][2] =  sγ*sβ + cγ*sα*cβ;
  R.m[2][0] =  cα*sβ;              R.m[2][1] = -sα;    R.m[2][2] =  cα*cβ;
  return R;
}

// ─── 边界过滤（射线法）────────────────────────────────────────────────────────

/**
 * 判断点 (px, py) 是否在多边形内（Ray Casting 算法，O(n)）
 * polygon 顶点不足 3 个时始终返回 true（不过滤）
 */
inline bool point_in_polygon(float px, float py,
                              const std::vector<Vec2>& polygon) {
  const size_t n = polygon.size();
  if (n < 3) return true;

  bool inside = false;
  for (size_t i = 0, j = n - 1; i < n; j = i++) {
    const float xi = polygon[i].x, yi = polygon[i].y;
    const float xj = polygon[j].x, yj = polygon[j].y;
    const bool  cross = ((yi > py) != (yj > py)) &&
                        (px < (xj - xi) * (py - yi) / (yj - yi) + xi);
    if (cross) inside = !inside;
  }
  return inside;
}

// ─── 主变换函数 ──────────────────────────────────────────────────────────────

/**
 * 将雷达局部坐标 (rx, ry, rz) 变换到房间坐标系
 *
 * 步骤：
 *   1. R = Rz(yaw) · Rx(pitch) · Ry(roll)
 *   2. world_vec = R * [rx, ry, rz]ᵀ
 *   3. room.x = radar_x + world_vec.x
 *      room.y = radar_y + world_vec.y
 *      height_floor = radar_height − world_vec.z
 *   4. 射线法判断 room.(x,y) 是否在 polygon 内
 *
 * 无 IMU 时：pitch/roll 可设为 0（水平安装误差 <5° 可忽略）
 */
inline TransformResult apply(float rx, float ry, float rz,
                             const CalibrationParams& cal) {
  const Mat3 R = build_rotation(cal.yaw, cal.pitch, cal.roll);

  const float wx = R.m[0][0]*rx + R.m[0][1]*ry + R.m[0][2]*rz;
  const float wy = R.m[1][0]*rx + R.m[1][1]*ry + R.m[1][2]*rz;
  const float wz = R.m[2][0]*rx + R.m[2][1]*ry + R.m[2][2]*rz;

  TransformResult res;
  res.room.x          = cal.radar_x + wx;
  res.room.y          = cal.radar_y + wy;
  res.height_floor_cm = cal.radar_height - wz;
  res.in_boundary     = point_in_polygon(res.room.x, res.room.y, cal.polygon);
  return res;
}

// ─── 校准辅助（仅在校准流程中调用一次）──────────────────────────────────────

/**
 * 已知两参考点的房间坐标和雷达读数，计算偏航角修正量（度）
 */
inline float compute_yaw_from_two_points(Vec2 map_a, Vec2 map_b,
                                         Vec2 det_a, Vec2 det_b) {
  const float am = atan2f(map_b.y - map_a.y, map_b.x - map_a.x);
  const float ad = atan2f(det_b.y - det_a.y, det_b.x - det_a.x);
  float yaw = (am - ad) * 180.f / static_cast<float>(M_PI);
  while (yaw >  180.f) yaw -= 360.f;
  while (yaw < -180.f) yaw += 360.f;
  return yaw;
}

/**
 * 计算两点校准残差（cm）
 * < 5 cm：良好；< 15 cm：可接受；> 15 cm：建议重新校准
 */
inline float calibration_residual(Vec2 map_a, Vec2 map_b,
                                   Vec2 det_a, Vec2 det_b,
                                   const CalibrationParams& cal) {
  const auto ta = apply(det_a.x, det_a.y, 0.f, cal);
  const auto tb = apply(det_b.x, det_b.y, 0.f, cal);
  const float ra = hypotf(ta.room.x - map_a.x, ta.room.y - map_a.y);
  const float rb = hypotf(tb.room.x - map_b.x, tb.room.y - map_b.y);
  return (ra + rb) / 2.f;
}

} // namespace r60abd1
} // namespace esphome