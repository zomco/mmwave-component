#include "ld2450.h"
#include "esphome/core/log.h"

namespace esphome {
namespace ld2450 {

static const char *const TAG = "ld2450";

// ═══════════════════════════════════════════════════════════════════════════
// 生命周期
// ═══════════════════════════════════════════════════════════════════════════

void LD2450Component::setup() {
  ESP_LOGCONFIG(TAG, "LD2450 setup...");
  recompute_rotation_();
  // LD2450 默认为多目标追踪模式，上电后立即输出数据帧，无需初始化命令
}

void LD2450Component::loop() {
  while (available()) {
    const uint8_t byte = read();
    process_byte_(byte);
  }
}

void LD2450Component::dump_config() {
  ESP_LOGCONFIG(TAG, "LD2450:");
  ESP_LOGCONFIG(TAG, "  Radar pos:   X=%.1f cm  Y=%.1f cm  H=%.1f cm",
                cal_.radar_x, cal_.radar_y, cal_.radar_z);
  ESP_LOGCONFIG(TAG, "  Orientation: Yaw=%.1f°  Pitch=%.1f°  Roll=%.1f°",
                cal_.yaw, cal_.pitch, cal_.roll);
  ESP_LOGCONFIG(TAG, "  Polygon pts: %u", (unsigned)cal_.polygon.size());
  LOG_BINARY_SENSOR("  ", "Presence", presence_sensor_);
  for (uint8_t i = 0; i < MAX_TARGETS; i++) {
    ESP_LOGCONFIG(TAG, "  Target %u:", i + 1);
    LOG_SENSOR     ("    ", "X",          targets_[i].x);
    LOG_SENSOR     ("    ", "Y",          targets_[i].y);
    LOG_SENSOR     ("    ", "Speed",      targets_[i].speed);
    LOG_SENSOR     ("    ", "Resolution", targets_[i].resolution);
    LOG_SENSOR     ("    ", "Distance",   targets_[i].distance);
    LOG_SENSOR     ("    ", "Angle",      targets_[i].angle);
    LOG_SENSOR     ("    ", "Room X",     targets_[i].room_x);
    LOG_SENSOR     ("    ", "Room Y",     targets_[i].room_y);
    LOG_BINARY_SENSOR("    ", "Active",      targets_[i].active);
    LOG_BINARY_SENSOR("    ", "In Boundary", targets_[i].in_boundary);
  }
}

// ═══════════════════════════════════════════════════════════════════════════
// 旋转矩阵预计算
// ═══════════════════════════════════════════════════════════════════════════

void LD2450Component::recompute_rotation_() {
  rotation_ = build_rotation(cal_.yaw, cal_.pitch, cal_.roll);
  ESP_LOGD(TAG, "Rotation matrix recomputed (yaw=%.1f° pitch=%.1f° roll=%.1f°)",
           cal_.yaw, cal_.pitch, cal_.roll);
}

// ═══════════════════════════════════════════════════════════════════════════
// 命令发送
// ═══════════════════════════════════════════════════════════════════════════

/**
 * 发送裸命令帧: [FD FC FB FA][len_L][len_H][cmd_L][cmd_H][data...][04 03 02 01]
 * len = 2（命令字）+ data_len
 */
void LD2450Component::send_raw_cmd_(uint16_t cmd_word,
                                     const uint8_t *data, uint16_t len) {
  const uint16_t frame_data_len = 2 + len;  // 命令字 2B + 数据 N B

  write_byte(CMD_HDR1);
  write_byte(CMD_HDR2);
  write_byte(CMD_HDR3);
  write_byte(CMD_HDR4);
  write_byte(static_cast<uint8_t>(frame_data_len & 0xFF));
  write_byte(static_cast<uint8_t>(frame_data_len >> 8));
  write_byte(static_cast<uint8_t>(cmd_word & 0xFF));
  write_byte(static_cast<uint8_t>(cmd_word >> 8));
  if (data != nullptr && len > 0)
    write_array(data, len);
  write_byte(CMD_TAIL1);
  write_byte(CMD_TAIL2);
  write_byte(CMD_TAIL3);
  write_byte(CMD_TAIL4);

  ESP_LOGV(TAG, "TX cmd: 0x%04X len=%u", cmd_word, len);
}

/**
 * 发送配置命令（自动包裹 enable_config / end_config）
 *
 * 流程:  enable_config → 目标命令 → end_config
 * LD2450 要求在发送任何配置命令前先发送 enable_config
 */
void LD2450Component::send_config_cmd(uint16_t cmd_word,
                                       const uint8_t *data, uint16_t len) {
  // 1. 使能配置
  const uint8_t enable_val[] = {0x01, 0x00};
  send_raw_cmd_(CMD_ENABLE_CONFIG, enable_val, 2);

  // 2. 发送目标命令
  send_raw_cmd_(cmd_word, data, len);

  // 3. 结束配置
  send_raw_cmd_(CMD_END_CONFIG, nullptr, 0);

  ESP_LOGD(TAG, "Config cmd sent: 0x%04X", cmd_word);
}

// ═══════════════════════════════════════════════════════════════════════════
// 帧解析状态机
// ═══════════════════════════════════════════════════════════════════════════

void LD2450Component::process_byte_(uint8_t byte) {
  switch (parse_state_) {

    // ── IDLE: 区分数据帧 (0xAA) 和命令帧 (0xFD) ──────────────────────────
    case ParseState::IDLE:
      if (byte == DATA_HDR1) {
        parse_state_ = ParseState::D_HDR2;
      } else if (byte == CMD_HDR1) {
        parse_state_ = ParseState::C_HDR2;
      }
      break;

    // ══════════════════════════════════════════════════════════════════════
    // 数据帧路径: AA FF 03 00 [24 bytes] 55 CC
    // ══════════════════════════════════════════════════════════════════════

    case ParseState::D_HDR2:
      parse_state_ = (byte == DATA_HDR2) ? ParseState::D_HDR3 : ParseState::IDLE;
      break;

    case ParseState::D_HDR3:
      parse_state_ = (byte == DATA_HDR3) ? ParseState::D_HDR4 : ParseState::IDLE;
      break;

    case ParseState::D_HDR4:
      if (byte == DATA_HDR4) {
        data_idx_    = 0;
        parse_state_ = ParseState::D_BODY;
      } else {
        parse_state_ = ParseState::IDLE;
      }
      break;

    case ParseState::D_BODY:
      data_buf_[data_idx_++] = byte;
      if (data_idx_ >= DATA_BODY_LEN)
        parse_state_ = ParseState::D_TAIL1;
      break;

    case ParseState::D_TAIL1:
      parse_state_ = (byte == DATA_TAIL1) ? ParseState::D_TAIL2 : ParseState::IDLE;
      break;

    case ParseState::D_TAIL2:
      if (byte == DATA_TAIL2)
        dispatch_data_frame_();
      else
        ESP_LOGW(TAG, "Data frame bad tail2: 0x%02X", byte);
      parse_state_ = ParseState::IDLE;
      break;

    // ══════════════════════════════════════════════════════════════════════
    // 命令 ACK 路径: FD FC FB FA [len_L][len_H][data...] 04 03 02 01
    // ══════════════════════════════════════════════════════════════════════

    case ParseState::C_HDR2:
      parse_state_ = (byte == CMD_HDR2) ? ParseState::C_HDR3 : ParseState::IDLE;
      break;

    case ParseState::C_HDR3:
      parse_state_ = (byte == CMD_HDR3) ? ParseState::C_HDR4 : ParseState::IDLE;
      break;

    case ParseState::C_HDR4:
      parse_state_ = (byte == CMD_HDR4) ? ParseState::C_LEN_L : ParseState::IDLE;
      break;

    case ParseState::C_LEN_L:
      cmd_len_     = byte;
      parse_state_ = ParseState::C_LEN_H;
      break;

    case ParseState::C_LEN_H:
      cmd_len_ |= static_cast<uint16_t>(byte) << 8;
      cmd_idx_  = 0;
      if (cmd_len_ > MAX_CMD_DATA) {
        ESP_LOGW(TAG, "CMD data too long (%u bytes), discarding", cmd_len_);
        parse_state_ = ParseState::IDLE;
      } else if (cmd_len_ == 0) {
        parse_state_ = ParseState::C_TAIL1;
      } else {
        parse_state_ = ParseState::C_DATA;
      }
      break;

    case ParseState::C_DATA:
      cmd_buf_[cmd_idx_++] = byte;
      if (cmd_idx_ >= cmd_len_)
        parse_state_ = ParseState::C_TAIL1;
      break;

    case ParseState::C_TAIL1:
      parse_state_ = (byte == CMD_TAIL1) ? ParseState::C_TAIL2 : ParseState::IDLE;
      break;

    case ParseState::C_TAIL2:
      parse_state_ = (byte == CMD_TAIL2) ? ParseState::C_TAIL3 : ParseState::IDLE;
      break;

    case ParseState::C_TAIL3:
      parse_state_ = (byte == CMD_TAIL3) ? ParseState::C_TAIL4 : ParseState::IDLE;
      break;

    case ParseState::C_TAIL4:
      if (byte == CMD_TAIL4)
        dispatch_cmd_frame_();
      else
        ESP_LOGW(TAG, "CMD frame bad tail4: 0x%02X", byte);
      parse_state_ = ParseState::IDLE;
      break;
  }
}

// ═══════════════════════════════════════════════════════════════════════════
// 数据帧分发
// ═══════════════════════════════════════════════════════════════════════════

/**
 * 解析 24 字节目标数据，每个目标 8 字节:
 *   [X_L][X_H][Y_L][Y_H][Speed_L][Speed_H][Res_L][Res_H]
 *
 * 全为 0 表示无目标
 */
void LD2450Component::dispatch_data_frame_() {
  bool any_active = false;

  for (uint8_t i = 0; i < MAX_TARGETS; i++) {
    const uint8_t *p = data_buf_ + i * TARGET_BYTES;

    const int16_t  x_mm      = decode_coord(p[0], p[1]);
    const int16_t  y_mm      = decode_coord(p[2], p[3]);
    const int16_t  speed     = decode_speed(p[4], p[5]);
    const uint16_t res       = decode_resolution(p[6], p[7]);

    // 目标存在判定：X 和 Y 同时为 0 视为无目标
    const bool active = (x_mm != 0 || y_mm != 0);
    if (active) any_active = true;

    publish_target_(i, x_mm, y_mm, speed, res, active);
  }

  if (presence_sensor_)
    presence_sensor_->publish_state(any_active);

  ESP_LOGV(TAG, "Data frame: %s", any_active ? "targets detected" : "no targets");
}

// ═══════════════════════════════════════════════════════════════════════════
// 命令 ACK 分发
// ═══════════════════════════════════════════════════════════════════════════

void LD2450Component::dispatch_cmd_frame_() {
  if (cmd_len_ < 2) {
    ESP_LOGV(TAG, "CMD ACK: len=%u (too short)", cmd_len_);
    return;
  }

  // 命令字 = 原始命令 | 0x0100（ACK 标记）
  const uint16_t ack_cmd = (static_cast<uint16_t>(cmd_buf_[1]) << 8) | cmd_buf_[0];
  // ACK 状态（如果有）
  const bool has_status = (cmd_len_ >= 4);
  const uint16_t status = has_status
      ? ((static_cast<uint16_t>(cmd_buf_[3]) << 8) | cmd_buf_[2])
      : 0xFFFF;

  ESP_LOGD(TAG, "CMD ACK: cmd=0x%04X status=%s",
           ack_cmd, has_status ? (status == 0 ? "OK" : "FAIL") : "N/A");

  // 特殊处理: 固件版本 (0xA001)
  if (ack_cmd == (CMD_FW_VERSION | 0x0100) && cmd_len_ >= 12 && status == 0) {
    // cmd_buf[4..5]: 固件类型, cmd_buf[6..7]: 主版本号, cmd_buf[8..11]: 次版本号
    ESP_LOGI(TAG, "Firmware: V%u.%02u.%02u%02u%02u%02u",
             cmd_buf_[7], cmd_buf_[6],
             cmd_buf_[11], cmd_buf_[10], cmd_buf_[9], cmd_buf_[8]);
  }

  // 特殊处理: 追踪模式查询 (0x9101)
  if (ack_cmd == (CMD_QUERY_MODE | 0x0100) && cmd_len_ >= 6 && status == 0) {
    const uint16_t mode = (static_cast<uint16_t>(cmd_buf_[5]) << 8) | cmd_buf_[4];
    ESP_LOGI(TAG, "Tracking mode: %s",
             mode == 0x0001 ? "single" : (mode == 0x0002 ? "multi" : "unknown"));
  }
}

// ═══════════════════════════════════════════════════════════════════════════
// 目标处理: 变换 → 过滤 → 发布
// ═══════════════════════════════════════════════════════════════════════════

void LD2450Component::publish_target_(uint8_t idx, int16_t x_mm, int16_t y_mm,
                                       int16_t speed_cm_s, uint16_t resolution_mm,
                                       bool active) {
  const auto &t = targets_[idx];

  // ── 发布目标激活状态 ────────────────────────────────────────────────────
  if (t.active) t.active->publish_state(active);

  if (!active) {
    // 目标不存在时发布 0
    if (t.x)          t.x->publish_state(0);
    if (t.y)          t.y->publish_state(0);
    if (t.speed)      t.speed->publish_state(0);
    if (t.resolution) t.resolution->publish_state(0);
    if (t.distance)   t.distance->publish_state(0);
    if (t.angle)      t.angle->publish_state(0);
    if (t.room_x)     t.room_x->publish_state(0);
    if (t.room_y)     t.room_y->publish_state(0);
    if (t.in_boundary) t.in_boundary->publish_state(false);
    return;
  }

  // ── 发布原始值 ─────────────────────────────────────────────────────────
  if (t.x)          t.x->publish_state(static_cast<float>(x_mm));
  if (t.y)          t.y->publish_state(static_cast<float>(y_mm));
  if (t.speed)      t.speed->publish_state(static_cast<float>(speed_cm_s));
  if (t.resolution) t.resolution->publish_state(static_cast<float>(resolution_mm));

  // ── 计算距离和角度 ─────────────────────────────────────────────────────
  const float x_cm = static_cast<float>(x_mm) / 10.0f;
  const float y_cm = static_cast<float>(y_mm) / 10.0f;
  const float dist_cm = sqrtf(x_cm * x_cm + y_cm * y_cm);
  const float angle_deg = atan2f(x_cm, y_cm) * 180.0f / static_cast<float>(M_PI);

  if (t.distance) t.distance->publish_state(dist_cm);
  if (t.angle)    t.angle->publish_state(angle_deg);

  // ── 坐标变换（雷达局部 → 房间坐标系） ──────────────────────────────────
  const auto res = apply(x_cm, y_cm, rotation_, cal_);

  if (t.room_x) t.room_x->publish_state(res.room.x);
  if (t.room_y) t.room_y->publish_state(res.room.y);

  // ── 边界过滤 ───────────────────────────────────────────────────────────
  if (t.in_boundary) t.in_boundary->publish_state(res.in_boundary);

  ESP_LOGD(TAG, "T%u: x=%d y=%d mm  spd=%d cm/s  dist=%.1f cm  "
           "room=(%.1f,%.1f) [%s]",
           idx + 1, x_mm, y_mm, speed_cm_s, dist_cm,
           res.room.x, res.room.y,
           res.in_boundary ? "inside" : "OUTSIDE");
}

} // namespace ld2450
} // namespace esphome
