#include "rd03e.h"
#include "esphome/core/log.h"

namespace esphome {
namespace rd03e {

static const char *const TAG = "rd03e";

// ═══════════════════════════════════════════════════════════════════════════
// 生命周期
// ═══════════════════════════════════════════════════════════════════════════

void RD03EComponent::setup() {
  ESP_LOGCONFIG(TAG, "RD03E setup...");
  // RD03E 上电后立即开始输出数据帧，无需初始化握手
}

void RD03EComponent::loop() {
  const uint32_t now = millis();
  while (available()) {
    const uint8_t byte = read();
    // Stamp the receive time before deciding whether to use the byte. Bytes are
    // still arriving while mock data is active — they are discarded, not
    // absent — and the watchdog below reads this to decide whether the radar
    // has gone quiet. Stamping it after the skip meant that one second into any
    // injection the watchdog concluded the link was dead and published
    // presence = false, wiping the state the injection had just set. Every
    // other component with mock support either does it in this order or leaves
    // loop() entirely while mock is active.
    last_rx_ms_ = now;
    if (now < this->mock_active_until_) {
      continue;
    }
    process_byte_(byte);
  }

  // Presence watchdog
  if (now - this->last_rx_ms_ > 1000) {
    if (this->presence_sensor_ != nullptr && this->presence_sensor_->state) {
      this->presence_sensor_->publish_state(false);
    }
  }
}

void RD03EComponent::dump_config() {
  ESP_LOGCONFIG(TAG, "RD03E:");
  ESP_LOGCONFIG(TAG, "  Radar pos:   X=%.1f cm  Y=%.1f cm  H=%.1f cm", cal_.radar_x, cal_.radar_y, cal_.radar_z);
  ESP_LOGCONFIG(TAG, "  Orientation: Yaw=%.1f°  Pitch=%.1f°  Roll=%.1f°", cal_.yaw, cal_.pitch, cal_.roll);
  ESP_LOGCONFIG(TAG, "  Distance filter: min=%.0f cm  max=%.0f cm", cal_.distance_min, cal_.distance_max);
  LOG_BINARY_SENSOR("  ", "Presence", presence_sensor_);
  LOG_SENSOR("  ", "Motion State", motion_state_);
  LOG_SENSOR("  ", "Distance", distance_);
  LOG_SENSOR("  ", "Room X", room_x_);
  LOG_SENSOR("  ", "Room Y", room_y_);
  LOG_SENSOR("  ", "Room Z", room_z_);
  LOG_BINARY_SENSOR("  ", "In Boundary", in_boundary_sensor_);
}

// ═══════════════════════════════════════════════════════════════════════════
// 命令发送
// ═══════════════════════════════════════════════════════════════════════════

/**
 * 命令帧格式: [FD FC FB FA] [len_L len_H] [data...] [04 03 02 01]
 * len 包含命令字 + 命令值的总长度
 */
void RD03EComponent::send_cmd(uint16_t cmd_word, const uint8_t *data, uint16_t len) {
  const uint16_t total_len = 2 + len;  // 2 bytes cmd_word + data

  write_byte(CMD_HDR1);
  write_byte(CMD_HDR2);
  write_byte(CMD_HDR3);
  write_byte(CMD_HDR4);
  write_byte(static_cast<uint8_t>(total_len & 0xFF));
  write_byte(static_cast<uint8_t>(total_len >> 8));
  write_byte(static_cast<uint8_t>(cmd_word & 0xFF));
  write_byte(static_cast<uint8_t>(cmd_word >> 8));
  if (data != nullptr && len > 0) {
    write_array(data, len);
  }
  write_byte(CMD_TAIL1);
  write_byte(CMD_TAIL2);
  write_byte(CMD_TAIL3);
  write_byte(CMD_TAIL4);

  ESP_LOGV(TAG, "TX: cmd=0x%04X len=%u", cmd_word, len);
}

void RD03EComponent::send_enable_config() {
  const uint8_t data[] = {0x01, 0x00};  // 命令值 0x0001
  send_cmd(CMD_ENABLE_CFG, data, sizeof(data));
}

void RD03EComponent::send_end_config() { send_cmd(CMD_END_CFG, nullptr, 0); }

void RD03EComponent::send_read_firmware_version() { send_cmd(CMD_FW_VERSION, nullptr, 0); }

void RD03EComponent::send_read_params() { send_cmd(CMD_READ_PARAMS, nullptr, 0); }

/**
 * 0x0067 距离参数配置
 *
 * 命令值: 5 组 (参数字 2B + 参数值 4B) = 30 字节
 *   0x0000: 最大运动距离 (30-717, unit cm)
 *   0x0001: 最小运动距离 (30-717, unit cm)
 *   0x0002: 最大微动距离 (30-425, unit cm)
 *   0x0003: 最小微动距离 (30-425, unit cm)
 *   0x0004: 无人持续时间 (0-65535, unit 50ms)
 */
void RD03EComponent::send_distance_config(uint32_t max_motion, uint32_t min_motion, uint32_t max_micro,
                                          uint32_t min_micro, uint32_t vacancy_duration) {
  uint8_t data[30];
  uint8_t *p = data;

  // 参数字 0x0000: 最大运动距离
  *p++ = 0x00;
  *p++ = 0x00;
  *p++ = static_cast<uint8_t>(max_motion & 0xFF);
  *p++ = static_cast<uint8_t>((max_motion >> 8) & 0xFF);
  *p++ = static_cast<uint8_t>((max_motion >> 16) & 0xFF);
  *p++ = static_cast<uint8_t>((max_motion >> 24) & 0xFF);

  // 参数字 0x0001: 最小运动距离
  *p++ = 0x01;
  *p++ = 0x00;
  *p++ = static_cast<uint8_t>(min_motion & 0xFF);
  *p++ = static_cast<uint8_t>((min_motion >> 8) & 0xFF);
  *p++ = static_cast<uint8_t>((min_motion >> 16) & 0xFF);
  *p++ = static_cast<uint8_t>((min_motion >> 24) & 0xFF);

  // 参数字 0x0002: 最大微动距离
  *p++ = 0x02;
  *p++ = 0x00;
  *p++ = static_cast<uint8_t>(max_micro & 0xFF);
  *p++ = static_cast<uint8_t>((max_micro >> 8) & 0xFF);
  *p++ = static_cast<uint8_t>((max_micro >> 16) & 0xFF);
  *p++ = static_cast<uint8_t>((max_micro >> 24) & 0xFF);

  // 参数字 0x0003: 最小微动距离
  *p++ = 0x03;
  *p++ = 0x00;
  *p++ = static_cast<uint8_t>(min_micro & 0xFF);
  *p++ = static_cast<uint8_t>((min_micro >> 8) & 0xFF);
  *p++ = static_cast<uint8_t>((min_micro >> 16) & 0xFF);
  *p++ = static_cast<uint8_t>((min_micro >> 24) & 0xFF);

  // 参数字 0x0004: 无人持续时间
  *p++ = 0x04;
  *p++ = 0x00;
  *p++ = static_cast<uint8_t>(vacancy_duration & 0xFF);
  *p++ = static_cast<uint8_t>((vacancy_duration >> 8) & 0xFF);
  *p++ = static_cast<uint8_t>((vacancy_duration >> 16) & 0xFF);
  *p++ = static_cast<uint8_t>((vacancy_duration >> 24) & 0xFF);

  send_cmd(CMD_DIST_CFG, data, sizeof(data));
}

// ═══════════════════════════════════════════════════════════════════════════
// 帧解析状态机（双路并行）
// ═══════════════════════════════════════════════════════════════════════════

void RD03EComponent::process_byte_(uint8_t byte) {
  // ── 数据帧解析: AA AA [status] [dist_L] [dist_H] 55 55 ─────────────────
  switch (data_state_) {
    case DataState::IDLE:
      if (byte == DATA_HDR) {
        data_state_ = DataState::HDR2;
      }
      break;

    case DataState::HDR2:
      if (byte == DATA_HDR) {
        data_state_ = DataState::STATUS;
      } else {
        data_state_ = DataState::IDLE;
      }
      break;

    case DataState::STATUS:
      data_status_ = byte;
      data_state_ = DataState::DIST_L;
      break;

    case DataState::DIST_L:
      data_dist_l_ = byte;
      data_state_ = DataState::DIST_H;
      break;

    case DataState::DIST_H:
      data_dist_h_ = byte;
      data_state_ = DataState::TAIL1;
      break;

    case DataState::TAIL1:
      if (byte == DATA_TAIL) {
        data_state_ = DataState::TAIL2;
      } else {
        data_state_ = DataState::IDLE;
      }
      break;

    case DataState::TAIL2:
      if (byte == DATA_TAIL) {
        handle_data_frame_();
      } else {
        ESP_LOGW(TAG, "Data frame: bad tail2: 0x%02X", byte);
      }
      data_state_ = DataState::IDLE;
      break;
  }

  // ── 命令 ACK 帧解析: FD FC FB FA [len_L len_H] [data...] 04 03 02 01 ──
  switch (cmd_state_) {
    case CmdState::IDLE:
      if (byte == CMD_HDR1) {
        cmd_state_ = CmdState::HDR2;
      }
      break;

    case CmdState::HDR2:
      cmd_state_ = (byte == CMD_HDR2) ? CmdState::HDR3 : CmdState::IDLE;
      break;

    case CmdState::HDR3:
      cmd_state_ = (byte == CMD_HDR3) ? CmdState::HDR4 : CmdState::IDLE;
      break;

    case CmdState::HDR4:
      cmd_state_ = (byte == CMD_HDR4) ? CmdState::LEN_L : CmdState::IDLE;
      break;

    case CmdState::LEN_L:
      cmd_data_len_ = byte;
      cmd_state_ = CmdState::LEN_H;
      break;

    case CmdState::LEN_H:
      cmd_data_len_ |= static_cast<uint16_t>(byte) << 8;
      cmd_data_idx_ = 0;
      if (cmd_data_len_ > MAX_CMD_DATA_LEN) {
        ESP_LOGW(TAG, "Cmd frame data too long (%u bytes), discarding", cmd_data_len_);
        cmd_state_ = CmdState::IDLE;
      } else if (cmd_data_len_ == 0) {
        cmd_state_ = CmdState::TAIL1;
      } else {
        cmd_state_ = CmdState::DATA;
      }
      break;

    case CmdState::DATA:
      cmd_buf_[cmd_data_idx_++] = byte;
      if (cmd_data_idx_ >= cmd_data_len_)
        cmd_state_ = CmdState::TAIL1;
      break;

    case CmdState::TAIL1:
      cmd_state_ = (byte == CMD_TAIL1) ? CmdState::TAIL2 : CmdState::IDLE;
      break;

    case CmdState::TAIL2:
      cmd_state_ = (byte == CMD_TAIL2) ? CmdState::TAIL3 : CmdState::IDLE;
      break;

    case CmdState::TAIL3:
      cmd_state_ = (byte == CMD_TAIL3) ? CmdState::TAIL4 : CmdState::IDLE;
      break;

    case CmdState::TAIL4:
      if (byte == CMD_TAIL4) {
        handle_cmd_frame_();
      } else {
        ESP_LOGW(TAG, "Cmd frame: bad tail4: 0x%02X", byte);
      }
      cmd_state_ = CmdState::IDLE;
      break;
  }
}

// ═══════════════════════════════════════════════════════════════════════════
// 数据帧处理
// ═══════════════════════════════════════════════════════════════════════════

void RD03EComponent::handle_data_frame_() {
  // 目标状态: 0x00=无目标, 0x01=运动目标, 0x02=微动目标
  const uint8_t status = data_status_;
  const uint16_t distance_cm = static_cast<uint16_t>(data_dist_l_) | (static_cast<uint16_t>(data_dist_h_) << 8);

  // 范围检查
  if (status > 0x02) {
    ESP_LOGW(TAG, "Unknown target status: 0x%02X", status);
    return;
  }
  if (status != 0x00 && distance_cm > 800) {
    ESP_LOGW(TAG, "Distance out of range: %u cm", distance_cm);
    return;
  }

  uint32_t now_ms = millis();
  if (now_ms - this->last_publish_ms_ < 1000)
    return;
  this->last_publish_ms_ = now_ms;

  // 雷达报的原始存在状态。最终发布要等边界判断出来 —— 见本函数末尾。
  const bool present = (status != 0x00);
  bool in_boundary = false;

  // 发布运动状态 (0=无, 1=运动, 2=微动)
  if (motion_state_) {
    motion_state_->publish_state(static_cast<float>(status));
  }

  // 发布距离
  if (distance_) {
    if (status == 0x00) {
      // 无目标时发布 0
      distance_->publish_state(0.0f);
    } else {
      distance_->publish_state(static_cast<float>(distance_cm));
    }
  }

  // 有目标时进行坐标变换
  bool have_position = false;
  if (status != 0x00 && distance_cm > 0) {
    in_boundary = publish_position_(static_cast<float>(distance_cm));
    have_position = true;
  }

  // 边界门控：开启时，界外目标不算存在。
  // 只有真的算出了位置，边界才有资格否决存在状态。拿缺失的位置去
  // 否定存在，正是让雷达看起来坏掉的那类 bug。
  const bool gated = (boundary_gates_presence_ && have_position) ? (present && in_boundary) : present;
  if (presence_sensor_)
    presence_sensor_->publish_state(gated);

  ESP_LOGD(TAG, "Status: %u  Distance: %u cm", status, distance_cm);
}

// ═══════════════════════════════════════════════════════════════════════════
// 命令 ACK 帧处理
// ═══════════════════════════════════════════════════════════════════════════

void RD03EComponent::handle_cmd_frame_() {
  if (cmd_data_len_ < 2) {
    ESP_LOGW(TAG, "Cmd ACK too short: %u bytes", cmd_data_len_);
    return;
  }

  // ACK 命令字: 低字节 = 原命令低字节, 高字节 = 原命令高字节 | 0x01
  const uint16_t ack_word = static_cast<uint16_t>(cmd_buf_[0]) | (static_cast<uint16_t>(cmd_buf_[1]) << 8);

  ESP_LOGD(TAG, "Cmd ACK: word=0x%04X len=%u", ack_word, cmd_data_len_);

  // 检查 ACK 状态（如果有数据的话）
  if (cmd_data_len_ >= 4) {
    const uint16_t ack_status = static_cast<uint16_t>(cmd_buf_[2]) | (static_cast<uint16_t>(cmd_buf_[3]) << 8);

    // 根据 ACK 命令字识别具体命令
    switch (ack_word) {
      case 0x0001: {  // 固件版本 ACK (0x0000 | 0x0100 → 但实际为 0x0001 based on docs)
        if (cmd_data_len_ >= 8) {
          // ACK 状态 + 主版本 + 次版本 + patch
          const uint16_t major = static_cast<uint16_t>(cmd_buf_[2]) | (static_cast<uint16_t>(cmd_buf_[3]) << 8);
          const uint16_t minor = static_cast<uint16_t>(cmd_buf_[4]) | (static_cast<uint16_t>(cmd_buf_[5]) << 8);
          const uint16_t patch = static_cast<uint16_t>(cmd_buf_[6]) | (static_cast<uint16_t>(cmd_buf_[7]) << 8);
          ESP_LOGI(TAG, "Firmware version: %u.%u.%u", major, minor, patch);
        }
        break;
      }

      case 0xFF01:  // 使能配置 ACK
        ESP_LOGD(TAG, "Enable config ACK: status=%u", ack_status);
        break;

      case 0xFE01:  // 结束配置 ACK
        ESP_LOGD(TAG, "End config ACK: status=%u", ack_status);
        break;

      case 0x6701:  // 距离配置 ACK
        ESP_LOGD(TAG, "Distance config ACK: status=%u", ack_status);
        break;

      case 0x7301: {  // 读取参数 ACK
        if (cmd_data_len_ >= 48) {
          // 解析并记录所有参数
          const uint16_t max_motion = static_cast<uint16_t>(cmd_buf_[2]) | (static_cast<uint16_t>(cmd_buf_[3]) << 8);
          const uint16_t min_motion = static_cast<uint16_t>(cmd_buf_[4]) | (static_cast<uint16_t>(cmd_buf_[5]) << 8);
          const uint16_t max_micro = static_cast<uint16_t>(cmd_buf_[6]) | (static_cast<uint16_t>(cmd_buf_[7]) << 8);
          const uint16_t min_micro = static_cast<uint16_t>(cmd_buf_[8]) | (static_cast<uint16_t>(cmd_buf_[9]) << 8);
          const uint16_t vacancy = static_cast<uint16_t>(cmd_buf_[10]) | (static_cast<uint16_t>(cmd_buf_[11]) << 8);
          ESP_LOGI(TAG, "Params: motion=[%u-%u] micro=[%u-%u] vacancy=%u (*50ms)", min_motion, max_motion, min_micro,
                   max_micro, vacancy);
        }
        break;
      }

      default:
        ESP_LOGD(TAG, "Unknown ACK word: 0x%04X status=%u", ack_word, ack_status);
        break;
    }
  }
}

// ═══════════════════════════════════════════════════════════════════════════
// 坐标变换 & 发布
// ═══════════════════════════════════════════════════════════════════════════

bool RD03EComponent::publish_position_(float range_cm) {
  const auto res = apply(range_cm, cal_);

  if (room_x_)
    room_x_->publish_state(res.room.x);
  if (room_y_)
    room_y_->publish_state(res.room.y);
  if (room_z_)
    room_z_->publish_state(res.room_z);
  if (in_boundary_sensor_)
    in_boundary_sensor_->publish_state(res.in_boundary);

  ESP_LOGD(TAG, "Room: x=%.1f y=%.1f h=%.1f cm  [%s]", res.room.x, res.room.y, res.room_z,
           res.in_boundary ? "inside" : "OUTSIDE");
  return res.in_boundary;
}

void RD03EComponent::inject_mock_data(const std::string &hex_str) {
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
    if (c >= '0' && c <= '9')
      return c - '0';
    if (c >= 'A' && c <= 'F')
      return c - 'A' + 10;
    if (c >= 'a' && c <= 'f')
      return c - 'a' + 10;
    return 0;
  };

  for (size_t i = 0; i < hex_chars.length(); i += 2) {
    uint8_t byte = (char_to_val(hex_chars[i]) << 4) | char_to_val(hex_chars[i + 1]);
    process_byte_(byte);
  }
}

}  // namespace rd03e
}  // namespace esphome
