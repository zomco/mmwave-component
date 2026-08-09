#pragma once
/**
 * ld2450_transform.h
 *
 * 二维坐标变换 + 房间边界过滤（射线法）
 *
 * 旋转顺序: R = Rz(yaw) · Rx(pitch) · Ry(roll)
 * 房间坐标约定: yaw=0 时雷达正前方指向房间 +Y，yaw 俯视顺时针为正
 *
 * LD2450 局部坐标系约定（手册 v1.03）:
 *   Y 轴 — 雷达正前方（始终为正）
 *   X 轴 — 左负右正
 *   无 Z 轴输出（2D 雷达）
 *   单位 — mm
 *   编码 — bit15=符号(1=正,0=负), bit14-0=15位幅值
 *
 * 注意: LD2450 的符号位约定与 R60ABD1 相反:
 *   LD2450: bit15=1 表示正，bit15=0 表示负
 *   R60ABD1: bit15=0 表示正，bit15=1 表示负
 */

#include <cmath>
#include <cstdint>
#include <vector>

#ifndef M_PI
#define M_PI 3.14159265358979323846f
#endif

namespace esphome {
namespace ld2450 {

// ─── 坐标解码 ────────────────────────────────────────────────────────────────

/**
 * 将 LD2450 输出的两字节坐标解码为有符号整数（mm）
 * 小端序: low byte 在前, high byte 在后
 * 符号位: bit15=1 为正, bit15=0 为负
 *
 * 示例: 0x86B1 → bit15=1, value=0x06B1=1713 → +1713 mm
 *       0x030E → bit15=0, value=0x030E=782  → -782 mm
 */
inline int16_t decode_coord(uint8_t low, uint8_t high) {
  const uint16_t raw   = (static_cast<uint16_t>(high) << 8) | low;
  const bool positive  = (raw >> 15) & 1u;
  const uint16_t value = raw & 0x7FFFu;
  return positive ?  static_cast<int16_t>(value)
                  : -static_cast<int16_t>(value);
}

/**
 * 将 LD2450 输出的两字节速度解码为有符号整数（cm/s）
 * 编码方式与坐标相同: bit15=1 为正向速度, bit15=0 为负向速度
 */
inline int16_t decode_speed(uint8_t low, uint8_t high) {
  return decode_coord(low, high);
}

/**
 * 将 LD2450 输出的两字节距离分辨率解码为无符号整数（mm）
 */
inline uint16_t decode_resolution(uint8_t low, uint8_t high) {
  return (static_cast<uint16_t>(high) << 8) | low;
}

// ─── 基础数据结构 ─────────────────────────────────────────────────────────────

struct Vec2 {
  float x = 0.f;
  float y = 0.f;
};

struct CalibrationParams {
  float radar_x      = 0.f;   // 雷达在房间中的 X 位置（cm）
  float radar_y      = 0.f;   // 雷达在房间中的 Y 位置（cm）
  float radar_z      = 150.f; // 雷达安装高度（cm）—— LD2450 推荐 1.0~1.5m
  float yaw          = 0.f;   // 偏航角（°，顺时针为正）
  float pitch        = 0.f;   // 俯仰角（°，向前倾为正）
  float roll         = 0.f;   // 横滚角（°，向右倾为正）
  std::vector<Vec2> polygon;  // 房间边界多边形（cm）; 空 = 不过滤
};

struct TransformResult {
  Vec2  room;          // 变换后的房间水平坐标（cm）
  bool  in_boundary;   // 是否在多边形内（polygon 为空时始终 true）
};

// ─── 旋转矩阵 ────────────────────────────────────────────────────────────────

struct Mat3 { float m[3][3] = {}; };

/**
 * 构建旋转矩阵 R = Rz(yaw) · Rx(pitch) · Ry(roll)
 *
 *         ┌ cy·cr+sy·sp·sr    sy·cp   −cy·sr+sy·sp·cr ┐
 * R(y,p,r)= │ −sy·cr+cy·sp·sr   cy·cp    sy·sr+cy·sp·cr │
 *         └ cp·sr             −sp      cp·cr           ┘
 *
 * yaw=0 时雷达正前方指向房间 +Y，yaw 俯视顺时针为正（转向 +X）；
 * roll 是绕雷达自身正前方（局部 +Y）的旋转。
 * 与 mmwave-card / HA mmwave_fusion / r60abd1 保持一致。
 */
inline Mat3 build_rotation(float yaw_deg, float pitch_deg, float roll_deg) {
  const float D2R = static_cast<float>(M_PI) / 180.f;
  const float y   = yaw_deg   * D2R;
  const float p   = pitch_deg * D2R;
  const float r   = roll_deg  * D2R;

  const float sy = sinf(y), cy = cosf(y);
  const float sp = sinf(p), cp = cosf(p);
  const float sr = sinf(r), cr = cosf(r);

  Mat3 R;
  R.m[0][0] =  cy*cr + sy*sp*sr;  R.m[0][1] =  sy*cp;  R.m[0][2] = -cy*sr + sy*sp*cr;
  R.m[1][0] = -sy*cr + cy*sp*sr;  R.m[1][1] =  cy*cp;  R.m[1][2] =  sy*sr + cy*sp*cr;
  R.m[2][0] =  cp*sr;             R.m[2][1] = -sp;     R.m[2][2] =  cp*cr;
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

// ─── 主变换函数（2D 雷达） ───────────────────────────────────────────────────

/**
 * 将雷达局部坐标 (lx, ly) 变换到房间坐标系
 *
 * 步骤：
 *   1. 使用预计算的旋转矩阵 R
 *   2. world_vec = R * [lx, ly, 0]ᵀ  （2D 雷达，Z 输入为 0）
 *   3. room.x = radar_x + world_vec.x
 *      room.y = radar_y + world_vec.y
 *   4. 射线法判断 room.(x,y) 是否在 polygon 内
 *
 * @param lx  雷达局部 X 坐标（cm，已从 mm 转换）
 * @param ly  雷达局部 Y 坐标（cm，已从 mm 转换）
 * @param R   预计算的旋转矩阵
 * @param cal 校准参数
 */
inline TransformResult apply(float lx, float ly,
                             const Mat3& R,
                             const CalibrationParams& cal) {
  // 2D 雷达: lz = 0，只需矩阵前两列
  const float wx = R.m[0][0]*lx + R.m[0][1]*ly;
  const float wy = R.m[1][0]*lx + R.m[1][1]*ly;

  TransformResult res;
  res.room.x      = cal.radar_x + wx;
  res.room.y      = cal.radar_y + wy;
  res.in_boundary = point_in_polygon(res.room.x, res.room.y, cal.polygon);
  return res;
}

} // namespace ld2450
} // namespace esphome
