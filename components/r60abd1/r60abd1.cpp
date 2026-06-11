#include "r60abd1.h"
#include "esphome/core/log.h"

namespace esphome {
namespace r60abd1 {

static const char *const TAG = "r60abd1";

// ═══════════════════════════════════════════════════════════════════════════
// 生命周期
// ═══════════════════════════════════════════════════════════════════════════

void R60ABD1Component::setup() {
  ESP_LOGCONFIG(TAG, "R60ABD1 setup...");
  // 查询初始化状态；收到 0x05/0x01 后再发启用命令，避免模组未就绪时丢命令
  query_init_state();
}

void R60ABD1Component::loop() {
  while (available()) {
    const uint8_t byte = read();
    last_rx_ms_ = millis();
    process_byte_(byte);
  }
}

void R60ABD1Component::dump_config() {
  ESP_LOGCONFIG(TAG, "R60ABD1:");
  ESP_LOGCONFIG(TAG, "  Radar pos:   X=%.1f cm  Y=%.1f cm  H=%.1f cm",
                cal_.radar_x, cal_.radar_y, cal_.radar_z);
  ESP_LOGCONFIG(TAG, "  Orientation: Yaw=%.1f°  Pitch=%.1f°  Roll=%.1f°",
                cal_.yaw, cal_.pitch, cal_.roll);
  ESP_LOGCONFIG(TAG, "  Polygon pts: %u", (unsigned)cal_.polygon.size());
  LOG_BINARY_SENSOR("  ", "Presence",            presence_sensor_);
  LOG_SENSOR       ("  ", "Motion State",         motion_sensor_);
  LOG_SENSOR       ("  ", "Body Movement",        body_movement_);
  LOG_SENSOR       ("  ", "Body Distance",        body_distance_);
  LOG_SENSOR       ("  ", "Raw X",                raw_x_);
  LOG_SENSOR       ("  ", "Raw Y",                raw_y_);
  LOG_SENSOR       ("  ", "Raw Z",                raw_z_);
  LOG_SENSOR       ("  ", "Room X",               room_x_);
  LOG_SENSOR       ("  ", "Room Y",               room_y_);
  LOG_SENSOR       ("  ", "Height Floor",         room_z_);
  LOG_BINARY_SENSOR("  ", "In Boundary",          in_boundary_sensor_);
  LOG_SENSOR       ("  ", "Breath Value",         breath_value_);
  LOG_TEXT_SENSOR  ("  ", "Breath State",         breath_state_);
  LOG_SENSOR       ("  ", "Heart Rate",           heart_rate_);
  LOG_BINARY_SENSOR("  ", "In Bed",               in_bed_sensor_);
  LOG_TEXT_SENSOR  ("  ", "Sleep State",          sleep_state_);
  LOG_SENSOR       ("  ", "Awake Duration",       awake_duration_);
  LOG_SENSOR       ("  ", "Light Sleep Duration", light_sleep_dur_);
  LOG_SENSOR       ("  ", "Deep Sleep Duration",  deep_sleep_dur_);
  LOG_SENSOR       ("  ", "Sleep Score",          sleep_score_);
  LOG_TEXT_SENSOR  ("  ", "Sleep Quality",        sleep_quality_);
}

// ═══════════════════════════════════════════════════════════════════════════
// 命令发送
// ═══════════════════════════════════════════════════════════════════════════

/**
 * 帧格式: [0x53][0x59][ctrl][cmd][len_H][len_L][data...][sum][0x54][0x43]
 * 校验码: (0x53+0x59+ctrl+cmd+len_H+len_L+data[0..n-1]) & 0xFF
 */
void R60ABD1Component::send_cmd(uint8_t ctrl, uint8_t cmd,
                                const uint8_t *data, uint16_t len) {
  uint8_t sum = FRAME_HDR1 + FRAME_HDR2 + ctrl + cmd
              + static_cast<uint8_t>(len >> 8)
              + static_cast<uint8_t>(len & 0xFF);
  for (uint16_t i = 0; i < len; i++) sum += data[i];

  write_byte(FRAME_HDR1);
  write_byte(FRAME_HDR2);
  write_byte(ctrl);
  write_byte(cmd);
  write_byte(static_cast<uint8_t>(len >> 8));
  write_byte(static_cast<uint8_t>(len & 0xFF));
  write_array(data, len);
  write_byte(sum);
  write_byte(FRAME_TAIL1);
  write_byte(FRAME_TAIL2);

  ESP_LOGV(TAG, "TX: ctrl=0x%02X cmd=0x%02X len=%u", ctrl, cmd, len);
}

// ═══════════════════════════════════════════════════════════════════════════
// 帧解析状态机
// ═══════════════════════════════════════════════════════════════════════════

void R60ABD1Component::process_byte_(uint8_t byte) {
  switch (parse_state_) {

    case ParseState::IDLE:
      if (byte == FRAME_HDR1) {
        checksum_accum_ = FRAME_HDR1;
        parse_state_    = ParseState::HDR2;
      }
      break;

    case ParseState::HDR2:
      if (byte == FRAME_HDR2) {
        checksum_accum_ += FRAME_HDR2;
        parse_state_ = ParseState::CTRL;
      } else {
        parse_state_ = ParseState::IDLE;
      }
      break;

    case ParseState::CTRL:
      ctrl_            = byte;
      checksum_accum_ += byte;
      parse_state_     = ParseState::CMD;
      break;

    case ParseState::CMD:
      cmd_             = byte;
      checksum_accum_ += byte;
      parse_state_     = ParseState::LEN_H;
      break;

    case ParseState::LEN_H:
      data_len_        = static_cast<uint16_t>(byte) << 8;
      checksum_accum_ += byte;
      parse_state_     = ParseState::LEN_L;
      break;

    case ParseState::LEN_L:
      data_len_       |= byte;
      checksum_accum_ += byte;
      data_idx_        = 0;
      if (data_len_ > MAX_DATA_LEN) {
        ESP_LOGW(TAG, "Frame data too long (%u bytes), discarding", data_len_);
        parse_state_ = ParseState::IDLE;
      } else {
        parse_state_ = (data_len_ == 0) ? ParseState::CHECKSUM
                                        : ParseState::DATA;
      }
      break;

    case ParseState::DATA:
      rx_buf_[data_idx_++] = byte;
      checksum_accum_     += byte;
      if (data_idx_ >= data_len_) parse_state_ = ParseState::CHECKSUM;
      break;

    case ParseState::CHECKSUM:
      if (byte == checksum_accum_) {
        parse_state_ = ParseState::TAIL1;
      } else {
        ESP_LOGW(TAG, "Checksum error: got 0x%02X expected 0x%02X", byte, checksum_accum_);
        parse_state_ = ParseState::IDLE;
      }
      break;

    case ParseState::TAIL1:
      parse_state_ = (byte == FRAME_TAIL1) ? ParseState::TAIL2
                                           : ParseState::IDLE;
      break;

    case ParseState::TAIL2:
      if (byte == FRAME_TAIL2) dispatch_frame_();
      else ESP_LOGW(TAG, "Bad tail2: 0x%02X", byte);
      parse_state_ = ParseState::IDLE;
      break;
  }
}

// ═══════════════════════════════════════════════════════════════════════════
// 帧分发
// ═══════════════════════════════════════════════════════════════════════════

void R60ABD1Component::dispatch_frame_() {
  ESP_LOGV(TAG, "RX: ctrl=0x%02X cmd=0x%02X len=%u", ctrl_, cmd_, data_len_);

  switch (ctrl_) {
    case CTRL_HEARTBEAT:
      ESP_LOGV(TAG, "Heartbeat/reset ack, cmd=0x%02X", cmd_);
      break;
    case CTRL_WORK_STATE:
      handle_work_state_frame_();
      break;
    case CTRL_PRESENCE:
      handle_presence_frame_();
      break;
    case CTRL_BREATH:
      handle_breath_frame_();
      break;
    case CTRL_HEART:
      handle_heart_frame_();
      break;
    case CTRL_SLEEP:
      handle_sleep_frame_();
      break;
    case CTRL_PRODUCT:
      if (data_len_ > 0 && data_len_ < MAX_DATA_LEN) {
        rx_buf_[data_len_] = '\0';
        ESP_LOGI(TAG, "Product info (cmd=0x%02X): %s", cmd_,
                 reinterpret_cast<const char *>(rx_buf_));
      }
      break;
    default:
      ESP_LOGV(TAG, "Unhandled ctrl=0x%02X cmd=0x%02X", ctrl_, cmd_);
      break;
  }
}

// ═══════════════════════════════════════════════════════════════════════════
// 各控制字处理
// ═══════════════════════════════════════════════════════════════════════════

// ── 0x05 工作状态 ──────────────────────────────────────────────────────────

void R60ABD1Component::handle_work_state_frame_() {
  if (cmd_ != 0x01 && cmd_ != 0x81) return;

  // 0x05 0x01 上报：初始化完成（无数据字节，data_len_=1, data=0x0F 是占位符）
  // 0x05 0x81 回复：data[0]=0x01 已完成, 0x00 未完成
  const bool done = (cmd_ == 0x01) ||
                    (cmd_ == 0x81 && data_len_ >= 1 && rx_buf_[0] == 0x01);

  if (done && !initialized_) {
    initialized_ = true;
    ESP_LOGI(TAG, "R60ABD1 initialized, enabling all monitoring");
    // 延迟 100ms 确保模组完全就绪
    delay(100);
    enable_presence();
    enable_breath();
    enable_heart_rate();
    enable_sleep();
  }
}

// ── 0x80 人体存在 ──────────────────────────────────────────────────────────

void R60ABD1Component::handle_presence_frame_() {
  if (data_len_ == 0) return;

  switch (cmd_) {

    case 0x01: // 存在信息: 00=无人, 01=有人
      if (presence_sensor_) {
        const bool present = (rx_buf_[0] == 0x01);
        presence_sensor_->publish_state(present);
        ESP_LOGD(TAG, "Presence: %s", present ? "YES" : "NO");
      }
      break;

    case 0x02: // 运动状态: 00=无, 01=静止, 02=活跃
      if (motion_sensor_)
        motion_sensor_->publish_state(static_cast<float>(rx_buf_[0]));
      break;

    case 0x03: // 体动幅度: 0-100，1B
      if (body_movement_ && data_len_ >= 1)
        body_movement_->publish_state(static_cast<float>(rx_buf_[0]));
      break;

    case 0x04: { // 人体距离: 2B，单位 cm
      if (body_distance_ && data_len_ >= 2) {
        const uint16_t dist = (static_cast<uint16_t>(rx_buf_[0]) << 8) | rx_buf_[1];
        body_distance_->publish_state(static_cast<float>(dist));
        ESP_LOGD(TAG, "Distance: %u cm", dist);
      }
      break;
    }

    case 0x05: { // 人体方位: 6B (2B x, 2B y, 2B z)，15位符号幅值
      if (data_len_ < 6) break;
      const int16_t rx = decode_coord(rx_buf_[0], rx_buf_[1]);
      const int16_t ry = decode_coord(rx_buf_[2], rx_buf_[3]);
      const int16_t rz = decode_coord(rx_buf_[4], rx_buf_[5]);
      ESP_LOGD(TAG, "Raw pos: x=%d y=%d z=%d cm", rx, ry, rz);

      if (raw_x_) raw_x_->publish_state(static_cast<float>(rx));
      if (raw_y_) raw_y_->publish_state(static_cast<float>(ry));
      if (raw_z_) raw_z_->publish_state(static_cast<float>(rz));

      publish_position_(rx, ry, rz);
      break;
    }

    default:
      break;
  }
}

// ── 0x81 呼吸检测 ──────────────────────────────────────────────────────────

void R60ABD1Component::handle_breath_frame_() {
  if (data_len_ == 0) return;

  switch (cmd_) {

    case 0x01: { // 呼吸状态: 01=正常 02=过高 03=过低 04=无
      if (breath_state_) {
        const char *state;
        switch (rx_buf_[0]) {
          case 0x01: state = "normal";  break;
          case 0x02: state = "high";    break;
          case 0x03: state = "low";     break;
          default:   state = "none";    break;
        }
        breath_state_->publish_state(state);
        ESP_LOGD(TAG, "Breath state: %s", state);
      }
      break;
    }

    case 0x02: // 呼吸数值: 0-35 次/min，3s 一次
      if (breath_value_ && data_len_ >= 1) {
        breath_value_->publish_state(static_cast<float>(rx_buf_[0]));
        ESP_LOGD(TAG, "Breath rate: %u /min", rx_buf_[0]);
      }
      break;

    case 0x05: // 呼吸波形: 5B（真实值+128），1s 一次
      ESP_LOGV(TAG, "Breath waveform: %d %d %d %d %d",
               rx_buf_[0]-128, rx_buf_[1]-128, rx_buf_[2]-128,
               rx_buf_[3]-128, rx_buf_[4]-128);
      break;

    default:
      break;
  }
}

// ── 0x85 心率监测 ──────────────────────────────────────────────────────────

void R60ABD1Component::handle_heart_frame_() {
  if (data_len_ == 0) return;

  switch (cmd_) {

    case 0x02: // 心率数值: 60-120 bpm，3s 一次
      if (heart_rate_ && data_len_ >= 1) {
        heart_rate_->publish_state(static_cast<float>(rx_buf_[0]));
        ESP_LOGD(TAG, "Heart rate: %u bpm", rx_buf_[0]);
      }
      break;

    case 0x05: // 心率波形: 5B（中轴线 128），1s 一次
      ESP_LOGV(TAG, "Heart waveform: %d %d %d %d %d",
               rx_buf_[0]-128, rx_buf_[1]-128, rx_buf_[2]-128,
               rx_buf_[3]-128, rx_buf_[4]-128);
      break;

    default:
      break;
  }
}

// ── 0x84 睡眠监测 ──────────────────────────────────────────────────────────

void R60ABD1Component::handle_sleep_frame_() {
  if (data_len_ == 0) return;

  switch (cmd_) {

    case 0x01: { // 入床/离床: 0x00=离床, 0x01=入床, 0x02=无
      if (in_bed_sensor_) {
        const bool in_bed = (rx_buf_[0] == 0x01);
        in_bed_sensor_->publish_state(in_bed);
        ESP_LOGD(TAG, "In bed: %s", in_bed ? "YES" : "NO");
      }
      break;
    }

    case 0x02: { // 睡眠状态: 0x00=深睡, 0x01=浅睡, 0x02=清醒, 0x03=无
      // 每 10min 上报一次
      if (sleep_state_) {
        const char *s;
        switch (rx_buf_[0]) {
          case 0x00: s = "deep";   break;
          case 0x01: s = "light";  break;
          case 0x02: s = "awake";  break;
          default:   s = "none";   break;
        }
        sleep_state_->publish_state(s);
        ESP_LOGD(TAG, "Sleep state: %s", s);
      }
      break;
    }

    case 0x03: // 清醒时长: 2B，单位分钟
      if (awake_duration_ && data_len_ >= 2) {
        const uint16_t min = (static_cast<uint16_t>(rx_buf_[0]) << 8) | rx_buf_[1];
        awake_duration_->publish_state(static_cast<float>(min));
      }
      break;

    case 0x04: // 浅睡时长: 2B
      if (light_sleep_dur_ && data_len_ >= 2) {
        const uint16_t min = (static_cast<uint16_t>(rx_buf_[0]) << 8) | rx_buf_[1];
        light_sleep_dur_->publish_state(static_cast<float>(min));
      }
      break;

    case 0x05: // 深睡时长: 2B
      if (deep_sleep_dur_ && data_len_ >= 2) {
        const uint16_t min = (static_cast<uint16_t>(rx_buf_[0]) << 8) | rx_buf_[1];
        deep_sleep_dur_->publish_state(static_cast<float>(min));
      }
      break;

    case 0x06: // 睡眠质量评分: 0-100，睡眠结束时上报
      if (sleep_score_ && data_len_ >= 1) {
        sleep_score_->publish_state(static_cast<float>(rx_buf_[0]));
        ESP_LOGD(TAG, "Sleep score: %u", rx_buf_[0]);
      }
      break;

    case 0x0C: { // 睡眠综合状态: 8B，每 10min 上报一次
      // byte0: 存在(1=有人,0=无人)
      // byte1: 睡眠状态(3=离床,2=清醒,1=浅睡,0=深睡)
      // byte2: 10min 平均呼吸  byte3: 10min 平均心跳
      // byte4: 翻身次数       byte5: 大幅体动占比
      // byte6: 小幅体动占比   byte7: 呼吸暂停(暂无)
      if (data_len_ < 8) break;
      ESP_LOGD(TAG, "Sleep summary: present=%u state=%u "
               "avg_br=%u avg_hr=%u turns=%u",
               rx_buf_[0], rx_buf_[1], rx_buf_[2], rx_buf_[3], rx_buf_[4]);
      // 注意：不更新 breath_value_ / heart_rate_，避免用 10min 平均值覆盖实时值。
      //       如需单独实体记录睡眠平均值，在 YAML 中添加对应 sensor 并扩展此处。
      break;
    }

    case 0x0D: { // 睡眠质量分析: 12B，睡眠过程结束时上报
      if (data_len_ < 12) break;
      // byte0: 评分  byte1-2: 总时长(min)
      // byte3: 清醒%  byte4: 浅睡%  byte5: 深睡%
      // byte6: 离床时长  byte7: 离床次数  byte8: 翻身次数
      // byte9: 平均呼吸  byte10: 平均心率  byte11: 呼吸暂停(暂无)
      if (sleep_score_) sleep_score_->publish_state(static_cast<float>(rx_buf_[0]));
      const uint16_t total_min =
          (static_cast<uint16_t>(rx_buf_[1]) << 8) | rx_buf_[2];
      ESP_LOGI(TAG, "Sleep analysis: score=%u total=%u min "
               "awake=%u%% light=%u%% deep=%u%%",
               rx_buf_[0], total_min, rx_buf_[3], rx_buf_[4], rx_buf_[5]);
      break;
    }

    case 0x0E: { // 睡眠异常
      const char *abnormal;
      switch (rx_buf_[0]) {
        case 0x00: abnormal = "sleep_too_short";    break;
        case 0x01: abnormal = "sleep_too_long";     break;
        case 0x02: abnormal = "absent_during_sleep";break;
        default:   abnormal = "none";               break;
      }
      ESP_LOGW(TAG, "Sleep anomaly: %s", abnormal);
      break;
    }

    case 0x10: { // 睡眠质量评级: 00=无, 01=良好, 02=一般, 03=较差
      if (sleep_quality_) {
        const char *q;
        switch (rx_buf_[0]) {
          case 0x01: q = "good";  break;
          case 0x02: q = "fair";  break;
          case 0x03: q = "poor";  break;
          default:   q = "none";  break;
        }
        sleep_quality_->publish_state(q);
        ESP_LOGD(TAG, "Sleep quality: %s", q);
      }
      break;
    }

    case 0x11: // 异常挣扎: 00=无, 01=正常, 02=异常
      ESP_LOGD(TAG, "Struggle state: 0x%02X", rx_buf_[0]);
      break;

    case 0x12: // 无人计时: 00=无, 01=正常, 02=异常
      ESP_LOGD(TAG, "Absence timer: 0x%02X", rx_buf_[0]);
      break;

    default:
      break;
  }
}

// ═══════════════════════════════════════════════════════════════════════════
// 坐标变换 & 发布
// ═══════════════════════════════════════════════════════════════════════════

void R60ABD1Component::publish_position_(int16_t rx, int16_t ry, int16_t rz) {
  const auto res = apply(
      static_cast<float>(rx),
      static_cast<float>(ry),
      static_cast<float>(rz),
      cal_);

  if (room_x_)       room_x_->publish_state(res.room.x);
  if (room_y_)       room_y_->publish_state(res.room.y);
  if (room_z_)       room_z_->publish_state(res.room_z);
  if (in_boundary_sensor_) in_boundary_sensor_->publish_state(res.in_boundary);

  ESP_LOGD(TAG, "Room: x=%.1f y=%.1f h=%.1f cm  [%s]",
           res.room.x, res.room.y, res.room_z,
           res.in_boundary ? "inside" : "OUTSIDE");
}

} // namespace r60abd1
} // namespace esphome