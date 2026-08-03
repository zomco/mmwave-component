#include "ld2451.h"

namespace esphome {
namespace ld2451 {

static const char *const TAG = "ld2451";

void LD2451Component::setup() {
  ESP_LOGCONFIG(TAG, "Setting up LD2451 Component...");
  this->rx_buffer_.reserve(64);
}

void LD2451Component::dump_config() {
  ESP_LOGCONFIG(TAG, "LD2451:");
  LOG_BINARY_SENSOR("  ", "Presence", this->presence_sensor_);
  LOG_BINARY_SENSOR("  ", "Alarm", this->alarm_sensor_);
  LOG_SENSOR("  ", "Target Count", this->target_count_sensor_);
  for (uint8_t i = 0; i < 3; i++) {
    ESP_LOGCONFIG(TAG, "  Target %d:", i + 1);
    LOG_SENSOR("    ", "Distance", this->targets_[i].distance);
    LOG_SENSOR("    ", "Angle", this->targets_[i].angle);
    LOG_SENSOR("    ", "Speed", this->targets_[i].speed);
    LOG_SENSOR("    ", "SNR", this->targets_[i].snr);
    LOG_SENSOR("    ", "X", this->targets_[i].x);
    LOG_SENSOR("    ", "Y", this->targets_[i].y);
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

void LD2451Component::loop() {
  const uint32_t now = millis();
  if (now - this->last_rx_ms_ > 100 && !this->rx_buffer_.empty()) {
    this->rx_buffer_.clear();
  }

  while (this->available()) {
    this->last_rx_ms_ = now;
    uint8_t b = this->read();
    if (now >= this->mock_active_until_) {
      this->process_byte_(b);
    }
  }

  // Presence watchdog
  if (now - this->last_rx_ms_ > 1000) {
    if (this->presence_sensor_ != nullptr && this->presence_sensor_->state) {
      this->presence_sensor_->publish_state(false);
    }
    if (this->alarm_sensor_ != nullptr && this->alarm_sensor_->state) {
      this->alarm_sensor_->publish_state(false);
    }
    if (this->target_count_sensor_ != nullptr) {
      this->target_count_sensor_->publish_state(0);
    }
  }
}

void LD2451Component::send_command_(uint16_t command, const uint8_t *command_value, uint8_t command_value_len) {
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

void LD2451Component::factory_reset() {
  this->send_command_(0x00A2, nullptr, 0);
  ESP_LOGI(TAG, "Factory reset sent");
}

void LD2451Component::restart_module() {
  this->send_command_(0x00A3, nullptr, 0);
  ESP_LOGI(TAG, "Restart sent");
}

void LD2451Component::process_ack_() {
  if (this->rx_buffer_.size() < 10) return;
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

void LD2451Component::handle_ack_data_(uint16_t command, uint16_t status, const uint8_t *data, uint8_t data_len) {
  ESP_LOGD(TAG, "Received ACK for command 0x%04X, status: 0x%04X", command, status);
  if (status != 0) {
    ESP_LOGW(TAG, "Command 0x%04X failed!", command);
    return;
  }
}

void LD2451Component::process_byte_(uint8_t byte) {
  this->rx_buffer_.push_back(byte);

  if (this->rx_buffer_.size() >= 10 && this->rx_buffer_[0] == 0xFD && this->rx_buffer_[1] == 0xFC &&
      this->rx_buffer_[2] == 0xFB && this->rx_buffer_[3] == 0xFA) {
    size_t tail_idx = 0;
    for (size_t i = 4; i < this->rx_buffer_.size() - 3; i++) {
      if (this->rx_buffer_[i] == 0x04 && this->rx_buffer_[i+1] == 0x03 &&
          this->rx_buffer_[i+2] == 0x02 && this->rx_buffer_[i+3] == 0x01) {
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
    return;
  }

  // Minimum frame is 12 bytes (Header 4 + Len 2 + Data 2 + Footer 4) for 0 targets
  if (this->rx_buffer_.size() >= 12) {
    // Check Header
    if (this->rx_buffer_[0] == 0xF4 && this->rx_buffer_[1] == 0xF3 &&
        this->rx_buffer_[2] == 0xF2 && this->rx_buffer_[3] == 0xF1) {
      
      uint16_t data_len = (uint16_t(this->rx_buffer_[5]) << 8) | this->rx_buffer_[4];
      uint16_t full_frame_len = 4 + 2 + data_len + 4;
      
      if (this->rx_buffer_.size() >= full_frame_len) {
        // Check Footer
        if (this->rx_buffer_[full_frame_len - 4] == 0xF8 && 
            this->rx_buffer_[full_frame_len - 3] == 0xF7 &&
            this->rx_buffer_[full_frame_len - 2] == 0xF6 && 
            this->rx_buffer_[full_frame_len - 1] == 0xF5) {
          
          this->process_packet_();
          this->rx_buffer_.erase(this->rx_buffer_.begin(), this->rx_buffer_.begin() + full_frame_len);
        } else {
          // Invalid footer, drop header
          this->rx_buffer_.erase(this->rx_buffer_.begin());
        }
      }
    } else if (this->rx_buffer_[0] != 0xFD) {
      // Invalid header, drop byte
      this->rx_buffer_.erase(this->rx_buffer_.begin());
    }
  }
}

void LD2451Component::process_packet_() {
  uint16_t data_len = (uint16_t(this->rx_buffer_[5]) << 8) | this->rx_buffer_[4];
  
  if (data_len < 2) return; // Need at least target_count and alarm_info

  uint32_t now_ms = millis();
  if (now_ms - this->last_publish_ms_ < 1000) return;
  this->last_publish_ms_ = now_ms;

  uint8_t target_count = this->rx_buffer_[6];
  uint8_t alarm_info = this->rx_buffer_[7]; // 01: approaching, 00: no approaching

  bool presence = (target_count > 0);
  bool alarm = (alarm_info == 0x01);

  if (this->presence_sensor_ != nullptr) {
    if (this->presence_sensor_->state != presence || !this->presence_sensor_->has_state()) {
      this->presence_sensor_->publish_state(presence);
    }
  }
  if (this->alarm_sensor_ != nullptr) {
    if (this->alarm_sensor_->state != alarm || !this->alarm_sensor_->has_state()) {
      this->alarm_sensor_->publish_state(alarm);
    }
  }
  if (this->target_count_sensor_ != nullptr) {
    if (this->target_count_sensor_->state != target_count || !this->target_count_sensor_->has_state()) {
      this->target_count_sensor_->publish_state(target_count);
    }
  }

  // Calculate maximum targets we can parse from payload
  uint8_t parseable_targets = (data_len - 2) / 5;
  uint8_t targets_to_process = std::min({target_count, parseable_targets, (uint8_t)3});

  for (uint8_t i = 0; i < 3; i++) {
    bool target_valid = (i < targets_to_process);
    
    if (target_valid) {
      uint16_t offset = 8 + (i * 5);
      
      int16_t raw_angle = this->rx_buffer_[offset];
      int16_t angle_deg = raw_angle - 0x80;
      
      float distance_m = this->rx_buffer_[offset + 1];
      
      uint8_t speed_dir = this->rx_buffer_[offset + 2]; // 01 approaching, 00 leaving
      uint8_t speed_val = this->rx_buffer_[offset + 3];
      float speed_kmh = (speed_dir == 0x01) ? speed_val : -(float)speed_val;
      
      float snr = this->rx_buffer_[offset + 4];

      // Convert polar to cartesian
      // distance is in meters, so distance * 100 for cm
      // Assuming 0 degrees is straight ahead (y-axis)
      float angle_rad = angle_deg * (M_PI / 180.0f);
      float x_cm = distance_m * 100.0f * std::sin(angle_rad);
      float y_cm = distance_m * 100.0f * std::cos(angle_rad);

      if (this->targets_[i].distance != nullptr) this->targets_[i].distance->publish_state(distance_m * 100.0f);
      if (this->targets_[i].angle != nullptr) this->targets_[i].angle->publish_state(angle_deg);
      if (this->targets_[i].speed != nullptr) this->targets_[i].speed->publish_state(speed_kmh);
      if (this->targets_[i].snr != nullptr) this->targets_[i].snr->publish_state(snr);
      if (this->targets_[i].x != nullptr) this->targets_[i].x->publish_state(x_cm);
      if (this->targets_[i].y != nullptr) this->targets_[i].y->publish_state(y_cm);

      // Coordinate Transformation (2D radar so local_z is 0)
      auto pos = Transform3D::transform(x_cm, y_cm, 0.0f, this->cal_);

      if (this->targets_[i].room_x != nullptr) this->targets_[i].room_x->publish_state(pos.room_x);
      if (this->targets_[i].room_y != nullptr) this->targets_[i].room_y->publish_state(pos.room_y);
      if (this->targets_[i].room_z != nullptr) this->targets_[i].room_z->publish_state(pos.room_z);
      
      if (this->targets_[i].in_boundary != nullptr) {
        if (this->targets_[i].in_boundary->state != pos.in_boundary || !this->targets_[i].in_boundary->has_state()) {
          this->targets_[i].in_boundary->publish_state(pos.in_boundary);
        }
      }
    } else {
      // Clear out unused targets
      if (this->targets_[i].in_boundary != nullptr) {
        if (this->targets_[i].in_boundary->state != false || !this->targets_[i].in_boundary->has_state()) {
          this->targets_[i].in_boundary->publish_state(false);
        }
      }
    }
  }
}

void LD2451Component::inject_mock_data(std::string data) {
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

} // namespace ld2451
} // namespace esphome
