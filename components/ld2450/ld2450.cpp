#include "ld2450.h"
#include "esphome/core/log.h"

#include <cstring>  // std::memcmp, used by the MAC/bluetooth ACK handling

namespace esphome {
namespace ld2450 {

static const char *const TAG = "ld2450";

// UART 静默超时（ms）。超过该时长没有收到任何字节，则认为雷达已离线，
// 主动把 presence 等状态推回 false，避免永久锁定在 on。
static const uint32_t UART_STALE_TIMEOUT_MS = 1000;

void LD2450Button::press_action() {
  if (type_ == RESTART) parent_->restart_module();
  else if (type_ == FACTORY_RESET) parent_->factory_reset();
}

void LD2450Switch::write_state(bool state) {
  if (type_ == MULTI_TARGET) parent_->set_multi_target_mode(state);
  else if (type_ == BLUETOOTH) parent_->set_bluetooth(state);
}

// ═══════════════════════════════════════════════════════════════════════════
// 生命周期
// ═══════════════════════════════════════════════════════════════════════════

void LD2450Component::setup() {
  ESP_LOGCONFIG(TAG, "LD2450 setup...");
  recompute_rotation_();
  // 延迟 1 秒后查询设备状态，确保雷达启动完毕
  this->set_timeout(1000, [this]() {
    this->query_state();
    // 区域过滤配置掉电不丢失，仅在 YAML 明确配置了非默认值时才下发，
    // 避免每次上电都写一遍雷达 flash。
    if (this->zone_config_pending_) {
      this->set_timeout("zone_cfg", 500, [this]() {
        this->apply_zone_config();
        this->set_timeout("zone_query", 500, [this]() { this->query_zone_config(); });
      });
    } else {
      this->set_timeout("zone_query", 500, [this]() { this->query_zone_config(); });
    }
  });
}

void LD2450Component::loop() {
  while (available()) {
    const uint8_t byte = read();
    this->last_rx_ms_ = millis();
    if (millis() < this->mock_active_until_) {
      continue;
    }
    process_byte_(byte);
  }

  this->check_uart_stale_(millis());
}

void LD2450Component::check_uart_stale_(uint32_t now) {
  // last_rx_ms_ == 0 表示上电后还从未收到过数据，此时各传感器仍是初始 false，
  // 不需要（也不应该）推送状态。
  if (this->last_rx_ms_ == 0 || (now - this->last_rx_ms_) <= UART_STALE_TIMEOUT_MS)
    return;

  if (this->presence_sensor_ != nullptr && this->presence_sensor_->state)
    this->presence_sensor_->publish_state(false);

  for (uint8_t i = 0; i < MAX_TARGETS; i++) {
    if (this->targets_[i].active != nullptr && this->targets_[i].active->state)
      this->targets_[i].active->publish_state(false);
    if (this->targets_[i].in_boundary != nullptr && this->targets_[i].in_boundary->state)
      this->targets_[i].in_boundary->publish_state(false);
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
  delay(50);  // NOLINT

  // 2. 发送目标命令
  send_raw_cmd_(cmd_word, data, len);
  delay(50);  // NOLINT

  // 3. 结束配置
  send_raw_cmd_(CMD_END_CONFIG, nullptr, 0);

  ESP_LOGD(TAG, "Config cmd sent: 0x%04X", cmd_word);
}

/**
 * 下发区域过滤配置（协议 2.2.13，命令字 0x00C2）
 *
 * 命令值 26 字节，全部小端：
 *   [0..1]   区域过滤类型（0 关闭 / 1 仅检测 / 2 不检测）
 *   [2..25]  3 个区域 × (x1, y1, x2, y2)，signed int16，单位 mm
 * 所有坐标为 0 表示该区域未使用。
 */
void LD2450Component::apply_zone_config() {
  uint8_t data[ZONE_CFG_LEN];
  data[0] = static_cast<uint8_t>(zone_type_ & 0xFF);
  data[1] = static_cast<uint8_t>(zone_type_ >> 8);

  uint8_t off = 2;
  for (uint8_t i = 0; i < MAX_ZONES; i++) {
    const int16_t coords[4] = {zones_[i].x1, zones_[i].y1, zones_[i].x2, zones_[i].y2};
    for (uint8_t c = 0; c < 4; c++) {
      const uint16_t raw = static_cast<uint16_t>(coords[c]);
      data[off++] = static_cast<uint8_t>(raw & 0xFF);
      data[off++] = static_cast<uint8_t>(raw >> 8);
    }
  }

  send_config_cmd(CMD_SET_ZONE, data, ZONE_CFG_LEN);
  ESP_LOGI(TAG, "Zone filter -> type=%u  z1=(%d,%d)-(%d,%d)  z2=(%d,%d)-(%d,%d)  z3=(%d,%d)-(%d,%d) mm",
           zone_type_,
           zones_[0].x1, zones_[0].y1, zones_[0].x2, zones_[0].y2,
           zones_[1].x1, zones_[1].y1, zones_[1].x2, zones_[1].y2,
           zones_[2].x1, zones_[2].y1, zones_[2].x2, zones_[2].y2);
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
  bool any_present = false;

  for (uint8_t i = 0; i < MAX_TARGETS; i++) {
    const uint8_t *p = data_buf_ + i * TARGET_BYTES;

    const int16_t  x_mm      = decode_coord(p[0], p[1]);
    const int16_t  y_mm      = decode_coord(p[2], p[3]);
    const int16_t  speed     = decode_speed(p[4], p[5]);
    const uint16_t res       = decode_resolution(p[6], p[7]);

  // 目标存在判定：X 和 Y 同时为 0 视为无目标
    const bool active = (x_mm != 0 || y_mm != 0);

    // publish_target_ 返回该目标是否计入 presence：
    // boundary_gates_presence_ 为真时，只有落在多边形内的目标才算数，
    // 这样隔墙的鬼影目标不会把 presence 拉高。
    if (publish_target_(i, x_mm, y_mm, speed, res, active)) any_present = true;
  }

  publish_target_frame_();

  if (presence_sensor_) {
    if (any_present) {
      last_presence_ms_ = millis();
      if (!presence_sensor_->state || !presence_sensor_->has_state()) {
        presence_sensor_->publish_state(true);
      }
    } else {
      if (millis() - last_presence_ms_ > presence_timeout_) {
        if (presence_sensor_->state || !presence_sensor_->has_state()) {
          presence_sensor_->publish_state(false);
        }
      }
    }
  }

  ESP_LOGV(TAG, "Data frame: %s", any_present ? "targets detected" : "no targets");
}

void LD2450Component::publish_target_frame_() {
  if (target_frame_sensor_ == nullptr) return;

  char payload[176];
  size_t offset = snprintf(payload, sizeof(payload),
                           "{\"v\":1,\"f\":%lu,\"ts\":%lu,\"t\":[",
                           static_cast<unsigned long>(++frame_id_),
                           static_cast<unsigned long>(millis()));
  bool first = true;
  for (uint8_t i = 0; i < MAX_TARGETS && offset < sizeof(payload); i++) {
    const uint8_t *p = data_buf_ + i * TARGET_BYTES;
    const int16_t x_mm = decode_coord(p[0], p[1]);
    const int16_t y_mm = decode_coord(p[2], p[3]);
    if (x_mm == 0 && y_mm == 0) continue;
    const int16_t speed_cm_s = decode_speed(p[4], p[5]);
    const int written = snprintf(payload + offset, sizeof(payload) - offset,
                                 "%s[%.1f,%.1f,%d]", first ? "" : ",",
                                 static_cast<float>(x_mm) / 10.0f,
                                 static_cast<float>(y_mm) / 10.0f,
                                 speed_cm_s);
    if (written < 0 || static_cast<size_t>(written) >= sizeof(payload) - offset) {
      ESP_LOGW(TAG, "Atomic target frame exceeded payload buffer");
      return;
    }
    offset += static_cast<size_t>(written);
    first = false;
  }
  if (offset + 3 >= sizeof(payload)) return;
  payload[offset++] = ']';
  payload[offset++] = '}';
  payload[offset] = '\0';
  target_frame_sensor_->publish_state(payload);
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

  // 特殊处理: 追踪模式查询或设置确认 (0x9101, 0x8001, 0x9001)
  if (ack_cmd == (CMD_QUERY_MODE | 0x0100) && cmd_len_ >= 6 && status == 0) {
    const uint16_t mode = (static_cast<uint16_t>(cmd_buf_[5]) << 8) | cmd_buf_[4];
    ESP_LOGI(TAG, "Tracking mode: %s",
             mode == 0x0001 ? "single" : (mode == 0x0002 ? "multi" : "unknown"));
    if (this->multi_target_switch_ != nullptr) {
      this->multi_target_switch_->publish_state(mode == 0x0002);
    }
  } else if (ack_cmd == (CMD_MULTI_TARGET | 0x0100) && status == 0) {
    if (this->multi_target_switch_ != nullptr) this->multi_target_switch_->publish_state(true);
  } else if (ack_cmd == (CMD_SINGLE_TARGET | 0x0100) && status == 0) {
    if (this->multi_target_switch_ != nullptr) this->multi_target_switch_->publish_state(false);
  }

  // 特殊处理: 区域过滤配置查询 (0xC101)
  // 帧内数据 = 2B 命令字 + 2B 状态 + 2B 区域类型 + 24B 坐标 = 30 字节
  if (ack_cmd == (CMD_QUERY_ZONE | 0x0100) && cmd_len_ >= 30 && status == 0) {
    const uint16_t type = (static_cast<uint16_t>(cmd_buf_[5]) << 8) | cmd_buf_[4];
    ESP_LOGI(TAG, "Zone filter: type=%u (%s)", type,
             type == ZONE_INCLUDE ? "detect only inside"
                                  : (type == ZONE_EXCLUDE ? "ignore inside" : "disabled"));
    for (uint8_t i = 0; i < MAX_ZONES; i++) {
      const uint8_t *z = &cmd_buf_[6 + i * 8];
      const int16_t x1 = static_cast<int16_t>((static_cast<uint16_t>(z[1]) << 8) | z[0]);
      const int16_t y1 = static_cast<int16_t>((static_cast<uint16_t>(z[3]) << 8) | z[2]);
      const int16_t x2 = static_cast<int16_t>((static_cast<uint16_t>(z[5]) << 8) | z[4]);
      const int16_t y2 = static_cast<int16_t>((static_cast<uint16_t>(z[7]) << 8) | z[6]);
      if (x1 || y1 || x2 || y2)
        ESP_LOGI(TAG, "  zone %u: (%d,%d) - (%d,%d) mm", i + 1, x1, y1, x2, y2);
    }
  } else if (ack_cmd == (CMD_SET_ZONE | 0x0100)) {
    ESP_LOGI(TAG, "Zone filter config %s", status == 0 ? "accepted" : "REJECTED");
  }

  // 特殊处理: 蓝牙查询或设置确认 (0xA501, 0xA401)
  // 帧内数据 = 2B 命令字 + 2B 状态 + 6B MAC，至少 10 字节
  if (ack_cmd == (CMD_GET_MAC | 0x0100) && cmd_len_ >= 10 && status == 0) {
    // MAC 全为 [0x08, 0x05, 0x04, 0x03, 0x02, 0x01] 时表示蓝牙已关闭
    const uint8_t NO_MAC[] = {0x08, 0x05, 0x04, 0x03, 0x02, 0x01};
    bool bt_on = std::memcmp(&cmd_buf_[4], NO_MAC, 6) != 0;
    ESP_LOGI(TAG, "Bluetooth: %s", bt_on ? "ON" : "OFF");
    if (this->bluetooth_switch_ != nullptr) {
      this->bluetooth_switch_->publish_state(bt_on);
    }
  }
}

// ═══════════════════════════════════════════════════════════════════════════
// 目标处理: 变换 → 过滤 → 发布
// ═══════════════════════════════════════════════════════════════════════════

bool LD2450Component::publish_target_(uint8_t idx, int16_t x_mm, int16_t y_mm,
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
    return false;
  }

  // ── 计算距离和角度 ─────────────────────────────────────────────────────
  const float x_cm = static_cast<float>(x_mm) / 10.0f;
  const float y_cm = static_cast<float>(y_mm) / 10.0f;
  const float dist_cm = sqrtf(x_cm * x_cm + y_cm * y_cm);
  const float angle_deg = atan2f(x_cm, y_cm) * 180.0f / static_cast<float>(M_PI);

  // ── 发布计算后的值 (转换为 cm 以统一单位) ──────────────────────────────
  if (t.x)          t.x->publish_state(x_cm);
  if (t.y)          t.y->publish_state(y_cm);
  if (t.speed)      t.speed->publish_state(static_cast<float>(speed_cm_s));
  if (t.resolution) t.resolution->publish_state(static_cast<float>(resolution_mm) / 10.0f);
  if (t.distance)   t.distance->publish_state(dist_cm);
  if (t.angle)      t.angle->publish_state(angle_deg);

  // ── 坐标变换（雷达局部 → 房间坐标系） ──────────────────────────────────
  const auto res = apply(x_cm, y_cm, rotation_, cal_);

  if (t.room_x) t.room_x->publish_state(res.room.x);
  if (t.room_y) t.room_y->publish_state(res.room.y);

  // ── 边界过滤 ───────────────────────────────────────────────────────────
  if (t.in_boundary) t.in_boundary->publish_state(res.in_boundary);

  ESP_LOGV(TAG, "T%u: x=%d y=%d mm  spd=%d cm/s  dist=%.1f cm  "
           "room=(%.1f,%.1f) [%s]",
           idx + 1, x_mm, y_mm, speed_cm_s, dist_cm,
           res.room.x, res.room.y,
           res.in_boundary ? "inside" : "OUTSIDE");

  // 计入 presence 与否：开启边界门控时，界外目标不算存在
  return boundary_gates_presence_ ? res.in_boundary : true;
}

void LD2450Component::inject_mock_data(const std::string &hex_str) {
  if (hex_str == "0" || hex_str == "reset" || hex_str == "clear" || hex_str.empty()) {
    ESP_LOGI(TAG, "Clearing mock mode, resuming live hardware UART input");
    this->mock_active_until_ = 0;
    return;
  }
  this->mock_active_until_ = millis() + 10000;
  ESP_LOGI(TAG, "Injecting mock data: %s", hex_str.c_str());
  std::string hex_chars;
  for (char c : hex_str) {
    if ((c >= '0' && c <= '9') || (c >= 'A' && c <= 'F') || (c >= 'a' && c <= 'f')) {
      hex_chars += c;
    }
  }

  if (hex_chars.length() % 2 != 0) {
    ESP_LOGE(TAG, "Mock data length must be even");
    return;
  }

  auto char_to_val = [](char c) -> uint8_t {
    if (c >= '0' && c <= '9') return c - '0';
    if (c >= 'A' && c <= 'F') return c - 'A' + 10;
    if (c >= 'a' && c <= 'f') return c - 'a' + 10;
    return 0;
  };

  for (size_t i = 0; i < hex_chars.length(); i += 2) {
    uint8_t byte = (char_to_val(hex_chars[i]) << 4) | char_to_val(hex_chars[i+1]);
    process_byte_(byte);
  }
}

} // namespace ld2450
} // namespace esphome
