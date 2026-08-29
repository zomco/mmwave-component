#include "ld2453.h"

namespace esphome {
namespace ld2453 {

static const char *const TAG = "ld2453";

// 连续这么久解析不出一个数据帧，就认为链路不可信。模组固定 10 帧/秒上报，
// 所以 1 秒相当于连丢 10 帧。
static const uint32_t FRAME_STALE_TIMEOUT_MS = 1000;

void LD2453Component::setup() {
  ESP_LOGCONFIG(TAG, "Setting up LD2453 Component...");
  this->rx_buffer_.reserve(64);
}

void LD2453Component::dump_config() {
  ESP_LOGCONFIG(TAG, "LD2453:");
  LOG_BINARY_SENSOR("  ", "Presence", this->presence_sensor_);
  for (uint8_t i = 0; i < 3; i++) {
    ESP_LOGCONFIG(TAG, "  Target %d:", i + 1);
    LOG_SENSOR("    ", "X", this->targets_[i].x);
    LOG_SENSOR("    ", "Y", this->targets_[i].y);
    LOG_SENSOR("    ", "Speed", this->targets_[i].speed);
    LOG_SENSOR("    ", "Resolution", this->targets_[i].resolution);
    LOG_SENSOR("    ", "Room X", this->targets_[i].room_x);
    LOG_SENSOR("    ", "Room Y", this->targets_[i].room_y);
    LOG_SENSOR("    ", "Room Z", this->targets_[i].room_z);
    LOG_BINARY_SENSOR("    ", "In Boundary", this->targets_[i].in_boundary);
  }

  ESP_LOGCONFIG(TAG, "  Calibration:");
  ESP_LOGCONFIG(TAG, "    Radar X: %.1f cm", cal_.radar_x);
  ESP_LOGCONFIG(TAG, "    Radar Y: %.1f cm", cal_.radar_y);
  ESP_LOGCONFIG(TAG, "    Radar Z: %.1f cm", cal_.radar_z);
  ESP_LOGCONFIG(TAG, "    Yaw: %.1f°", cal_.yaw);
  ESP_LOGCONFIG(TAG, "    Pitch: %.1f°", cal_.pitch);
  ESP_LOGCONFIG(TAG, "    Roll: %.1f°", cal_.roll);
  ESP_LOGCONFIG(TAG, "    Distance Min: %.1f cm", cal_.distance_min);
  ESP_LOGCONFIG(TAG, "    Distance Max: %.1f cm", cal_.distance_max);
}

void LD2453Component::loop() {
  const uint32_t now = millis();

  if (this->mock_active_until_ > 0 && now < this->mock_active_until_) {
    while (this->available())
      this->read();
    return;
  }

  if (now - this->last_rx_ms_ > 100 && !this->rx_buffer_.empty()) {
    this->rx_buffer_.clear();
  }

  while (this->available()) {
    this->last_rx_ms_ = now;
    this->process_byte_(this->read());
  }

  this->check_stale_(now);
}

/**
 * 帧级看门狗。
 *
 * 这里刻意用 last_frame_ms_ 而不是 last_rx_ms_：模组无条件以 10 帧/秒常发，
 * 只要线还接着，last_rx_ms_ 就永远是新的。原先按 last_rx_ms_ 判断的写法因此
 * 只能发现"串口彻底断流"，发现不了"字节还在来、但帧头/帧尾对不上"的失步——
 * 而失步恰恰会让所有实体连同 presence 无限期锁死在最后一个值上，在卡片上表现
 * 为目标卡住不动。按解析成功的帧计时，两种情况就都能覆盖。
 *
 * 与 ld2450/ld2452/ld2454 的 check_uart_stale_ 不同，这里连坐标 sensor 一起
 * 置 NAN。留着旧坐标会让消费端把过期位置当成实时位置继续画。
 */
void LD2453Component::check_stale_(uint32_t now) {
  // 上电后还没收到过任何一帧：各实体仍是初始状态，不需要也不应该推送。
  if (this->last_frame_ms_ == 0 || now - this->last_frame_ms_ <= FRAME_STALE_TIMEOUT_MS)
    return;

  for (uint8_t i = 0; i < 3; i++) {
    this->publish_empty_target_(i);
    publish_if_changed_(this->targets_[i].speed, NAN);
    publish_if_changed_(this->targets_[i].resolution, NAN);
  }

  if (this->presence_sensor_ != nullptr &&
      (this->presence_sensor_->state || !this->presence_sensor_->has_state())) {
    this->presence_sensor_->publish_state(false);
  }
}

void LD2453Component::inject_mock_data(const std::string &data) {
  if (data == "0" || data == "reset") {
    this->mock_active_until_ = 0;
    this->rx_buffer_.clear();
    ESP_LOGD(TAG, "Mock data disabled, resuming normal hardware UART");
    return;
  }

  this->mock_active_until_ = millis() + 10000;
  this->rx_buffer_.clear();

  for (size_t i = 0; i < data.length(); i += 2) {
    std::string byte_str = data.substr(i, 2);
    uint8_t byte = (uint8_t) strtol(byte_str.c_str(), nullptr, 16);
    this->rx_buffer_.push_back(byte);
  }

  if (this->rx_buffer_.size() >= 30 && this->rx_buffer_[0] == 0xAA && this->rx_buffer_[1] == 0xFF &&
      this->rx_buffer_[2] == 0x03 && this->rx_buffer_[3] == 0x00 && this->rx_buffer_[28] == 0x55 &&
      this->rx_buffer_[29] == 0xCC) {
    // A requested mock frame must not be dropped just because a hardware frame
    // was published within the normal output-rate window.
    this->last_frame_publish_ms_ = millis() - 100;
    this->last_publish_ms_ = millis() - 1000;
    this->process_packet_();
  } else {
    ESP_LOGW(TAG, "Injected mock data is not a valid LD2453 frame! length=%d", this->rx_buffer_.size());
  }

  this->rx_buffer_.clear();
}

void LD2453Component::send_command_(uint16_t command, const uint8_t *command_value, uint8_t command_value_len) {
  // Enable config
  uint8_t enable_cmd[] = {0xFD, 0xFC, 0xFB, 0xFA, 0x04, 0x00, 0xFF, 0x00, 0x01, 0x00, 0x04, 0x03, 0x02, 0x01};
  this->write_array(enable_cmd, sizeof(enable_cmd));
  delay(50);

  // Send command
  uint16_t len = 2 + command_value_len;
  std::vector<uint8_t> cmd;
  cmd.push_back(0xFD);
  cmd.push_back(0xFC);
  cmd.push_back(0xFB);
  cmd.push_back(0xFA);
  cmd.push_back(len & 0xFF);
  cmd.push_back((len >> 8) & 0xFF);
  cmd.push_back(command & 0xFF);
  cmd.push_back((command >> 8) & 0xFF);
  for (uint8_t i = 0; i < command_value_len; i++) {
    cmd.push_back(command_value[i]);
  }
  cmd.push_back(0x04);
  cmd.push_back(0x03);
  cmd.push_back(0x02);
  cmd.push_back(0x01);
  this->write_array(cmd.data(), cmd.size());
  delay(50);

  // Disable config
  uint8_t disable_cmd[] = {0xFD, 0xFC, 0xFB, 0xFA, 0x02, 0x00, 0xFE, 0x00, 0x04, 0x03, 0x02, 0x01};
  this->write_array(disable_cmd, sizeof(disable_cmd));
  delay(50);
}

void LD2453Component::set_tracking_mode(uint8_t mode) {
  uint16_t cmd = (mode == 1) ? 0x0080 : 0x0090;
  this->send_command_(cmd, nullptr, 0);
  ESP_LOGI(TAG, "Set tracking mode: %d", mode);
}

void LD2453Component::query_parameters() { this->send_command_(0x0091, nullptr, 0); }

void LD2453Component::factory_reset() {
  this->send_command_(0x00A2, nullptr, 0);
  ESP_LOGI(TAG, "Factory reset sent");
}

void LD2453Component::restart_module() {
  this->send_command_(0x00A3, nullptr, 0);
  ESP_LOGI(TAG, "Restart sent");
}

void LD2453Component::process_ack_() {
  if (this->rx_buffer_.size() < 10)
    return;
  uint16_t command = (uint16_t(this->rx_buffer_[7]) << 8) | this->rx_buffer_[6];
  uint16_t status = (uint16_t(this->rx_buffer_[9]) << 8) | this->rx_buffer_[8];

  uint8_t data_len = 0;
  const uint8_t *data = nullptr;
  uint16_t total_len = (uint16_t(this->rx_buffer_[5]) << 8) | this->rx_buffer_[4];
  if (total_len > 4) {
    data_len = total_len - 4;
    data = &this->rx_buffer_[10];
  }

  this->handle_ack_data_(command, status, data, data_len);
}

void LD2453Component::handle_ack_data_(uint16_t command, uint16_t status, const uint8_t *data, uint8_t data_len) {
  ESP_LOGD(TAG, "Received ACK for command 0x%04X, status: 0x%04X", command, status);
  if (status != 0) {
    ESP_LOGW(TAG, "Command 0x%04X failed!", command);
    return;
  }
  // 协议 2.1.2 表 5：ACK 帧里的命令字是"发送命令字 | 0x0100"，
  // 所以查询追踪模式（0x0091）的回包带的是 0x0191。原先比较 0x0091 永远不成立，
  // query_parameters() 因此从来没有打印过结果。
  if (command == 0x0191 && data_len >= 2) {
    uint16_t mode = (uint16_t(data[1]) << 8) | data[0];
    ESP_LOGI(TAG, "Current Tracking Mode: %s", mode == 1 ? "Single Target" : "Multi Target");
  }
}

void LD2453Component::process_byte_(uint8_t byte) {
  this->rx_buffer_.push_back(byte);

  if (this->rx_buffer_.size() >= 30) {
    if (this->rx_buffer_[0] == 0xAA && this->rx_buffer_[1] == 0xFF && this->rx_buffer_[2] == 0x03 &&
        this->rx_buffer_[3] == 0x00 && this->rx_buffer_[28] == 0x55 && this->rx_buffer_[29] == 0xCC) {
      this->process_packet_();
      this->rx_buffer_.clear();
    } else if (this->rx_buffer_[0] == 0xFD && this->rx_buffer_[1] == 0xFC && this->rx_buffer_[2] == 0xFB &&
               this->rx_buffer_[3] == 0xFA) {
      size_t tail_idx = 0;
      for (size_t i = 4; i < this->rx_buffer_.size() - 3; i++) {
        if (this->rx_buffer_[i] == 0x04 && this->rx_buffer_[i + 1] == 0x03 && this->rx_buffer_[i + 2] == 0x02 &&
            this->rx_buffer_[i + 3] == 0x01) {
          tail_idx = i;
          break;
        }
      }
      if (tail_idx > 0) {
        this->process_ack_();
        this->rx_buffer_.erase(this->rx_buffer_.begin(), this->rx_buffer_.begin() + tail_idx + 4);
      } else if (this->rx_buffer_.size() > 64) {
        this->rx_buffer_.erase(this->rx_buffer_.begin());
      }
    } else {
      // Invalid frame, pop first byte and continue
      this->rx_buffer_.erase(this->rx_buffer_.begin());
    }
  } else if (this->rx_buffer_.size() >= 10 && this->rx_buffer_[0] == 0xFD && this->rx_buffer_[1] == 0xFC &&
             this->rx_buffer_[2] == 0xFB && this->rx_buffer_[3] == 0xFA) {
    size_t tail_idx = 0;
    for (size_t i = 4; i < this->rx_buffer_.size() - 3; i++) {
      if (this->rx_buffer_[i] == 0x04 && this->rx_buffer_[i + 1] == 0x03 && this->rx_buffer_[i + 2] == 0x02 &&
          this->rx_buffer_[i + 3] == 0x01) {
        tail_idx = i;
        break;
      }
    }
    if (tail_idx > 0) {
      this->process_ack_();
      this->rx_buffer_.erase(this->rx_buffer_.begin(), this->rx_buffer_.begin() + tail_idx + 4);
    }
  }
}

int16_t LD2453Component::decode_value_(uint8_t low, uint8_t high) {
  // LD2453 sign-magnitude format: MSB (bit 15) indicates sign
  // 1 = positive, 0 = negative (this is not two's complement).
  uint16_t val = (uint16_t(high) << 8) | low;
  bool is_positive = (val & 0x8000) != 0;
  int16_t magnitude = val & 0x7FFF;
  return is_positive ? magnitude : -magnitude;
}

/**
 * 仅在数值真正变化时发布。
 *
 * ESPHome 会对 binary_sensor 去重，但不会对数值 sensor 去重。本组件按雷达
 * 的 ~10 Hz 帧率发布 24 个实体，若不去重，空闲槽位会持续以 10 Hz 推送 NAN，
 * 白白占用 API 带宽和 HA 的 recorder。NAN → NAN 视为未变化。
 */
void LD2453Component::publish_if_changed_(sensor::Sensor *s, float value) {
  if (s == nullptr)
    return;
  if (s->has_state()) {
    const float prev = s->state;
    if (std::isnan(prev) && std::isnan(value))
      return;
    if (prev == value)
      return;
  }
  s->publish_state(value);
}

void LD2453Component::publish_empty_target_(uint8_t idx) {
  publish_if_changed_(this->targets_[idx].x, NAN);
  publish_if_changed_(this->targets_[idx].y, NAN);
  publish_if_changed_(this->targets_[idx].room_x, NAN);
  publish_if_changed_(this->targets_[idx].room_y, NAN);
  publish_if_changed_(this->targets_[idx].room_z, NAN);

  if (this->targets_[idx].in_boundary != nullptr) {
    if (this->targets_[idx].in_boundary->state || !this->targets_[idx].in_boundary->has_state()) {
      this->targets_[idx].in_boundary->publish_state(false);
    }
  }
}

void LD2453Component::process_packet_() {
  uint32_t now_ms = millis();
  this->last_frame_ms_ = now_ms;

  if (now_ms - this->last_frame_publish_ms_ >= 100) {
    this->last_frame_publish_ms_ = now_ms;
    this->publish_target_frame_();
  }

  // Entities publish at the radar's own 10 Hz frame rate. ESPHome already
  // deduplicates unchanged binary_sensor states, and the fusion integration
  // needs presence/room_* to keep pace with DEFAULT_TRACK_TTL_S (1.2 s).
  this->last_publish_ms_ = now_ms;

  bool any_present = false;

  for (uint8_t i = 0; i < 3; i++) {
    uint8_t offset = 4 + (i * 8);

    int16_t x_mm = this->decode_value_(this->rx_buffer_[offset], this->rx_buffer_[offset + 1]);
    int16_t y_mm = this->decode_value_(this->rx_buffer_[offset + 2], this->rx_buffer_[offset + 3]);
    int16_t speed_cm_s = this->decode_value_(this->rx_buffer_[offset + 4], this->rx_buffer_[offset + 5]);
    uint16_t res_mm = (uint16_t(this->rx_buffer_[offset + 7]) << 8) | this->rx_buffer_[offset + 6];

    // 空槽位判定与 ld2450/ld2452/ld2454 保持一致：只看坐标。
    //
    // 原先还接受 res_mm > 0，于是坐标归零、只剩距离分辨率的槽位会被当成
    // 一个位于 (0,0) 的活目标：presence 被拉高，而消费端普遍把 (0,0) 当作
    // "无目标"过滤掉，结果就是"有人却看不到目标"。协议里空槽位是整段 0x00，
    // 分辨率非零、坐标为零的组合并无定义。
    bool target_valid = (x_mm != 0 || y_mm != 0);

    // Speed/resolution are only meaningful for an occupied slot; publishing 0
    // for empty slots contradicts the NAN used for the positional entities.
    publish_if_changed_(this->targets_[i].speed, target_valid ? speed_cm_s : NAN);
    publish_if_changed_(this->targets_[i].resolution, target_valid ? res_mm : NAN);

    if (target_valid) {
      float x_cm = x_mm / 10.0f;
      float y_cm = y_mm / 10.0f;

      publish_if_changed_(this->targets_[i].x, x_cm);
      publish_if_changed_(this->targets_[i].y, y_cm);

      // Coordinate Transformation (2D radar so local_z is 0)
      auto pos = Transform3D::transform(x_cm, y_cm, 0.0f, this->cal_);

      publish_if_changed_(this->targets_[i].room_x, pos.room_x);
      publish_if_changed_(this->targets_[i].room_y, pos.room_y);
      publish_if_changed_(this->targets_[i].room_z, pos.room_z);

      if (this->targets_[i].in_boundary != nullptr) {
        if (this->targets_[i].in_boundary->state != pos.in_boundary || !this->targets_[i].in_boundary->has_state()) {
          this->targets_[i].in_boundary->publish_state(pos.in_boundary);
        }
      }

      // 边界门控：界外目标（隔墙鬼影）默认不计入 presence
      if (!this->boundary_gates_presence_ || pos.in_boundary)
        any_present = true;
    } else {
      this->publish_empty_target_(i);
    }
  }

  if (this->presence_sensor_ != nullptr) {
    if (this->presence_sensor_->state != any_present || !this->presence_sensor_->has_state()) {
      this->presence_sensor_->publish_state(any_present);
    }
  }
}

void LD2453Component::publish_target_frame_() {
  if (this->target_frame_sensor_ == nullptr)
    return;

  char payload[176];
  size_t offset = snprintf(payload, sizeof(payload), "{\"v\":1,\"f\":%lu,\"ts\":%lu,\"t\":[",
                           static_cast<unsigned long>(++this->frame_id_), static_cast<unsigned long>(millis()));
  bool first = true;
  for (uint8_t i = 0; i < 3 && offset < sizeof(payload); i++) {
    const uint8_t target_offset = 4 + (i * 8);
    const int16_t x_mm = this->decode_value_(this->rx_buffer_[target_offset], this->rx_buffer_[target_offset + 1]);
    const int16_t y_mm = this->decode_value_(this->rx_buffer_[target_offset + 2], this->rx_buffer_[target_offset + 3]);
    const int16_t speed_cm_s =
        this->decode_value_(this->rx_buffer_[target_offset + 4], this->rx_buffer_[target_offset + 5]);
    const uint16_t resolution_mm =
        (uint16_t(this->rx_buffer_[target_offset + 7]) << 8) | this->rx_buffer_[target_offset + 6];
    if (resolution_mm == 0 && x_mm == 0 && y_mm == 0)
      continue;
    const int written = snprintf(payload + offset, sizeof(payload) - offset, "%s[%.1f,%.1f,%d]", first ? "" : ",",
                                 static_cast<float>(x_mm) / 10.0f, static_cast<float>(y_mm) / 10.0f, speed_cm_s);
    if (written < 0 || static_cast<size_t>(written) >= sizeof(payload) - offset) {
      ESP_LOGW(TAG, "Atomic target frame exceeded payload buffer");
      return;
    }
    offset += static_cast<size_t>(written);
    first = false;
  }
  if (offset + 3 >= sizeof(payload))
    return;
  payload[offset++] = ']';
  payload[offset++] = '}';
  payload[offset] = '\0';
  this->target_frame_sensor_->publish_state(payload);
}

}  // namespace ld2453
}  // namespace esphome
