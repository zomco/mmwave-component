#include "ld2450a.h"

namespace esphome {
namespace ld2450a {

static const char *const TAG = "ld2450a";

void LD2450AComponent::setup() { ESP_LOGCONFIG(TAG, "Setting up LD2450A Component..."); }

void LD2450AComponent::dump_config() {
  ESP_LOGCONFIG(TAG, "LD2450A:");
  LOG_BINARY_SENSOR("  ", "Presence", this->presence_sensor_);
  LOG_SENSOR("  ", "Distance", this->distance_sensor_);
  LOG_TEXT_SENSOR("  ", "Gesture", this->gesture_text_sensor_);
  LOG_SENSOR("  ", "Gesture Type", this->gesture_type_sensor_);
  LOG_SENSOR("  ", "Gesture Distance", this->gesture_distance_sensor_);
  LOG_SENSOR("  ", "Gesture Speed", this->gesture_speed_sensor_);
  LOG_SENSOR("  ", "Gesture Angle", this->gesture_angle_sensor_);
  LOG_SENSOR("  ", "Room X", this->room_x_);
  LOG_SENSOR("  ", "Room Y", this->room_y_);
  LOG_SENSOR("  ", "Room Z", this->room_z_);
  LOG_BINARY_SENSOR("  ", "In Boundary", this->in_boundary_sensor_);

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

void LD2450AComponent::loop() {
  const uint32_t now = millis();
  if (now - this->last_rx_ms_ > 1000) {
    this->rx_buffer_.clear();
    if (this->presence_sensor_ != nullptr && this->presence_sensor_->state) {
      this->presence_sensor_->publish_state(false);
    }
  }

  while (this->available()) {
    this->last_rx_ms_ = now;
    uint8_t b = this->read();
    if (now >= this->mock_active_until_) {
      this->process_byte_(b);
    }
  }
}

void LD2450AComponent::process_byte_(uint8_t byte) {
  this->rx_buffer_.push_back(byte);

  while (this->rx_buffer_.size() >= 4) {
    if (this->rx_buffer_[0] != 0xAA) {
      this->rx_buffer_.erase(this->rx_buffer_.begin());
      continue;
    }

    uint8_t frame_len = this->rx_buffer_[1];
    if (frame_len < 4 || frame_len > 64) {
      this->rx_buffer_.erase(this->rx_buffer_.begin());
      continue;
    }

    if (this->rx_buffer_.size() < frame_len) {
      break;  // Wait for more bytes
    }

    if (this->rx_buffer_[frame_len - 1] != 0x55) {
      this->rx_buffer_.erase(this->rx_buffer_.begin());
      continue;
    }

    // Check CRC8 (XOR sum from byte 1 to frame_len - 3)
    uint8_t crc_calc = 0;
    for (size_t i = 1; i <= frame_len - 3; i++) {
      crc_calc ^= this->rx_buffer_[i];
    }

    if (crc_calc == this->rx_buffer_[frame_len - 2]) {
      this->process_packet_();
    } else {
      ESP_LOGW(TAG, "CRC Check Failed: expected 0x%02X, calculated 0x%02X", this->rx_buffer_[frame_len - 2], crc_calc);
    }

    this->rx_buffer_.erase(this->rx_buffer_.begin(), this->rx_buffer_.begin() + frame_len);
  }
}

void LD2450AComponent::process_packet_() {
  uint8_t frame_type = this->rx_buffer_[2];

  if (frame_type == 0xB0 && this->rx_buffer_.size() >= 16) {
    uint32_t now_ms = millis();
    if (now_ms - this->last_publish_ms_ < 1000)
      return;
    this->last_publish_ms_ = now_ms;

    uint8_t presence_val = this->rx_buffer_[3];
    uint8_t dist_val = this->rx_buffer_[4];
    uint8_t gesture_val = this->rx_buffer_[5];
    uint8_t gesture_dist = this->rx_buffer_[6];
    // uint8_t gesture_dist_thresh = this->rx_buffer_[7];
    uint8_t gesture_spd = this->rx_buffer_[8];
    // uint8_t gesture_spd_thresh  = this->rx_buffer_[9];
    uint8_t gesture_ang = this->rx_buffer_[10];
    // uint8_t gesture_ang_thresh  = this->rx_buffer_[11];

    // 雷达报的原始存在状态。发布要等边界判断出来。
    const bool is_present = (presence_val != 0x00);
    bool in_boundary = false;
    bool have_position = false;

    if (is_present && dist_val != 255) {
      float dist_cm = dist_val;
      if (this->distance_sensor_ != nullptr) {
        this->distance_sensor_->publish_state(dist_cm);
      }
      in_boundary = this->publish_position_(dist_cm);
      have_position = true;
    } else {
      if (this->in_boundary_sensor_ != nullptr) {
        this->in_boundary_sensor_->publish_state(false);
      }
    }

    // 边界门控：开启时，界外目标不算存在。
    // 只有真的算出了位置，边界才有资格否决存在状态。拿缺失的位置去
    // 否定存在，正是让雷达看起来坏掉的那类 bug。
    const bool gated = (this->boundary_gates_presence_ && have_position) ? (is_present && in_boundary) : is_present;
    if (this->presence_sensor_ != nullptr) {
      this->presence_sensor_->publish_state(gated);
    }

    // Gesture reporting
    const char *gesture_str = "None";
    if (gesture_val == 0x01) {
      gesture_str = "Wave Right";
    } else if (gesture_val == 0x02) {
      gesture_str = "Wave Left";
    }

    if (this->gesture_text_sensor_ != nullptr &&
        (this->gesture_text_sensor_->state != gesture_str || !this->gesture_text_sensor_->has_state())) {
      this->gesture_text_sensor_->publish_state(gesture_str);
    }

    if (this->gesture_type_sensor_ != nullptr) {
      this->gesture_type_sensor_->publish_state(gesture_val);
    }

    if (gesture_val != 0) {
      if (this->gesture_distance_sensor_ != nullptr) {
        this->gesture_distance_sensor_->publish_state(gesture_dist);
      }
      if (this->gesture_speed_sensor_ != nullptr) {
        this->gesture_speed_sensor_->publish_state(gesture_spd);
      }
      if (this->gesture_angle_sensor_ != nullptr) {
        this->gesture_angle_sensor_->publish_state(gesture_ang);
      }
    }
  } else if (frame_type == 0xB1) {
    ESP_LOGD(TAG, "Received ACK frame for command 0x%02X", this->rx_buffer_[3]);
  }
}

void LD2450AComponent::send_command_(uint8_t cmd, uint16_t val) {
  uint8_t frame[11];
  frame[0] = 0xAA;
  frame[1] = 0x0B;
  frame[2] = 0xB1;
  frame[3] = cmd;
  frame[4] = (val >> 8) & 0xFF;
  frame[5] = val & 0xFF;
  frame[6] = 0x00;
  frame[7] = 0x00;
  frame[8] = 0x00;

  uint8_t crc = 0;
  for (int i = 1; i <= 8; i++) {
    crc ^= frame[i];
  }
  frame[9] = crc;
  frame[10] = 0x55;

  this->write_array(frame, 11);
  ESP_LOGD(TAG, "Sent command 0x%02X with value %u", cmd, val);
}

void LD2450AComponent::set_gesture_distance_threshold(uint16_t val_cm) { this->send_command_(0xC2, val_cm); }

void LD2450AComponent::set_gesture_speed_threshold(uint16_t val_cms) { this->send_command_(0xC3, val_cms); }

void LD2450AComponent::set_gesture_angle_threshold(uint16_t val_deg) { this->send_command_(0xC4, val_deg); }

void LD2450AComponent::factory_reset() { this->send_command_(0xC5, 0); }

void LD2450AComponent::reboot() { this->send_command_(0x02, 0); }

bool LD2450AComponent::publish_position_(float range_cm) {
  auto pos = Transform1D::transform(range_cm, this->cal_);

  if (this->room_x_ != nullptr) {
    this->room_x_->publish_state(pos.room_x);
  }
  if (this->room_y_ != nullptr) {
    this->room_y_->publish_state(pos.room_y);
  }
  if (this->room_z_ != nullptr) {
    this->room_z_->publish_state(pos.room_z);
  }
  if (this->in_boundary_sensor_ != nullptr) {
    if (this->in_boundary_sensor_->state != pos.in_boundary || !this->in_boundary_sensor_->has_state()) {
      this->in_boundary_sensor_->publish_state(pos.in_boundary);
    }
  }
  return pos.in_boundary;
}

void LD2450AComponent::inject_mock_data(std::string data) {
  if (data == "0" || data == "reset") {
    this->mock_active_until_ = 0;
    this->rx_buffer_.clear();
    ESP_LOGI(TAG, "Mock data mode disabled");
    return;
  }

  this->mock_active_until_ = millis() + 10000;

  std::vector<uint8_t> mock_bytes;
  for (size_t i = 0; i < data.length(); i += 2) {
    std::string byteString = data.substr(i, 2);
    uint8_t byte = (uint8_t) strtol(byteString.c_str(), NULL, 16);
    mock_bytes.push_back(byte);
  }

  for (uint8_t b : mock_bytes) {
    this->process_byte_(b);
  }
}

}  // namespace ld2450a
}  // namespace esphome
