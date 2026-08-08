#include "ld2451.h"

namespace esphome {
namespace ld2451 {

static const char *const TAG = "ld2451";

void LD2451Component::setup() {
  ESP_LOGCONFIG(TAG, "Setting up LD2451...");
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
  static uint32_t diag_bytes_ = 0;
  static uint32_t diag_frames_ = 0;
  static uint32_t last_diag_ms_ = 0;
  const uint32_t now = millis();

  // Removed boot_phase_ configuration override to allow the radar to use its internal EEPROM settings.

  // Diagnostic: every 5 seconds, report byte count
  if (now - last_diag_ms_ >= 5000) {
    ESP_LOGI(TAG, "DIAG: %u bytes received in last 5s, %u data frames parsed, available()=%d", 
             diag_bytes_, diag_frames_, this->available());
    diag_bytes_ = 0;
    diag_frames_ = 0;
    last_diag_ms_ = now;
  }

  if (now - this->last_rx_ms_ > 100 && !this->rx_buffer_.empty()) {
    this->rx_buffer_.clear();
  }

  while (this->available()) {
    this->last_rx_ms_ = now;
    uint8_t b = this->read();
    diag_bytes_++;
    
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
      if (this->target_count_sensor_->state != 0 || !this->target_count_sensor_->has_state()) {
        this->target_count_sensor_->publish_state(0);
      }
    }
  }
}

void LD2451Component::send_command_(uint16_t command, const uint8_t *command_value, uint8_t command_value_len) {
  // Enable config
  uint8_t enable_cmd[] = {0xFD, 0xFC, 0xFB, 0xFA, 0x04, 0x00, 0xFF, 0x00, 0x01, 0x00, 0x04, 0x03, 0x02, 0x01};
  this->write_array(enable_cmd, sizeof(enable_cmd));
  delay(100);

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
  delay(250); // Important: Give radar enough time to write to flash!

  // Disable config
  uint8_t disable_cmd[] = {0xFD, 0xFC, 0xFB, 0xFA, 0x02, 0x00, 0xFE, 0x00, 0x04, 0x03, 0x02, 0x01};
  this->write_array(disable_cmd, sizeof(disable_cmd));
  delay(100);
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
  ESP_LOGI(TAG, "Received ACK for command 0x%04X, status: 0x%04X", command, status);
  if (status != 0) {
    ESP_LOGW(TAG, "Command 0x%04X failed!", command);
    return;
  }
  
  if (command == 0x01A0 && data_len >= 8) {
    uint16_t type = (uint16_t(data[1]) << 8) | data[0];
    uint16_t major = (uint16_t(data[3]) << 8) | data[2];
    uint32_t minor = (uint32_t(data[7]) << 24) | (uint32_t(data[6]) << 16) | (uint32_t(data[5]) << 8) | data[4];
    ESP_LOGI(TAG, "Radar Firmware Version: V%d.%02d.%08X (Type: %04X)", major, minor >> 24, minor & 0xFFFFFF, type);
  }
  
  // Detection params ACK: 4 bytes (MaxDist, Direction, MinSpeed, Delay)
  if (command == 0x0112 && data_len >= 4) {
    ESP_LOGI(TAG, "Detection Params: MaxDist=%dm, Dir=%d (0=away,1=approach,2=both), MinSpeed=%dkm/h, Delay=%ds",
             data[0], data[1], data[2], data[3]);
  }
  
  // Sensitivity params ACK: 4 bytes (TriggerCount, SNRThreshold, ext, ext)
  if (command == 0x0113 && data_len >= 4) {
    ESP_LOGI(TAG, "Sensitivity Params: TriggerCount=%d, SNRThreshold=%d, ext=%d, ext=%d",
             data[0], data[1], data[2], data[3]);
  }
}

void LD2451Component::process_byte_(uint8_t byte) {
  // ESP_LOGD(TAG, "RX: %02X", byte); // Disabled to prevent flooding, we'll collect them in a static buffer and print
  static std::vector<uint8_t> dump_buf;
  dump_buf.push_back(byte);
  if (dump_buf.size() >= 16) {
    ESP_LOGI(TAG, "RAW RX DUMP: %02X %02X %02X %02X %02X %02X %02X %02X %02X %02X %02X %02X %02X %02X %02X %02X",
             dump_buf[0], dump_buf[1], dump_buf[2], dump_buf[3], dump_buf[4], dump_buf[5], dump_buf[6], dump_buf[7],
             dump_buf[8], dump_buf[9], dump_buf[10], dump_buf[11], dump_buf[12], dump_buf[13], dump_buf[14], dump_buf[15]);
    dump_buf.clear();
  }

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

  // Minimum frame is 10 bytes (Header 4 + Len 2 + Data 0 + Footer 4)
  if (this->rx_buffer_.size() >= 10) {
    // Check Header
    if (this->rx_buffer_[0] == 0xF4 && this->rx_buffer_[1] == 0xF3 &&
        this->rx_buffer_[2] == 0xF2 && this->rx_buffer_[3] == 0xF1) {
      
      ESP_LOGI(TAG, "Data packet header found");
      uint16_t data_len = (uint16_t(this->rx_buffer_[5]) << 8) | this->rx_buffer_[4];
      if (data_len > 30) { this->rx_buffer_.erase(this->rx_buffer_.begin()); return; }
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
    } else {
      // Invalid header, drop byte
      this->rx_buffer_.erase(this->rx_buffer_.begin());
    }
  }
}

void LD2451Component::process_packet_() {
  uint16_t data_len = (uint16_t(this->rx_buffer_[5]) << 8) | this->rx_buffer_[4];
  
  uint8_t target_count = 0;
  uint8_t alarm_info = 0;
  
  if (data_len >= 2) {
    target_count = this->rx_buffer_[6];
    alarm_info = this->rx_buffer_[7]; // 01: approaching, 00: no approaching
  }

  ESP_LOGI(TAG, "RAW DATA: %02X %02X %02X %02X | %02X %02X | %02X %02X | %02X %02X %02X %02X",
           this->rx_buffer_[0], this->rx_buffer_[1], this->rx_buffer_[2], this->rx_buffer_[3],
           this->rx_buffer_[4], this->rx_buffer_[5],
           (this->rx_buffer_.size() > 6) ? this->rx_buffer_[6] : 0, 
           (this->rx_buffer_.size() > 7) ? this->rx_buffer_[7] : 0,
           (this->rx_buffer_.size() > 8) ? this->rx_buffer_[8] : 0, 
           (this->rx_buffer_.size() > 9) ? this->rx_buffer_[9] : 0,
           (this->rx_buffer_.size() > 10) ? this->rx_buffer_[10] : 0,
           (this->rx_buffer_.size() > 11) ? this->rx_buffer_[11] : 0);

  // Calculate maximum targets we can parse from payload.
  uint8_t parseable_targets = (data_len - 2) / 5;
  uint8_t targets_to_process = std::min({target_count, parseable_targets, (uint8_t) 3});

  uint32_t now_ms = millis();
  if (now_ms - this->last_frame_publish_ms_ >= 100) {
    this->last_frame_publish_ms_ = now_ms;
    this->publish_target_frame_(targets_to_process);
  }

  // Retain the legacy entity rate while the atomic frame supplies fusion at 10 Hz.
  if (now_ms - this->last_publish_ms_ < 1000) return;
  this->last_publish_ms_ = now_ms;

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

void LD2451Component::publish_target_frame_(uint8_t target_count) {
  if (this->target_frame_sensor_ == nullptr) return;

  char payload[176];
  size_t offset = snprintf(payload, sizeof(payload),
                           "{\"v\":1,\"f\":%lu,\"ts\":%lu,\"t\":[",
                           static_cast<unsigned long>(++this->frame_id_),
                           static_cast<unsigned long>(millis()));
  for (uint8_t i = 0; i < target_count && offset < sizeof(payload); i++) {
    const uint16_t target_offset = 8 + (i * 5);
    const int16_t angle_deg = static_cast<int16_t>(this->rx_buffer_[target_offset]) - 0x80;
    const float distance_cm = static_cast<float>(this->rx_buffer_[target_offset + 1]) * 100.0f;
    const float angle_rad = angle_deg * (M_PI / 180.0f);
    const float x_cm = distance_cm * std::sin(angle_rad);
    const float y_cm = distance_cm * std::cos(angle_rad);
    const float direction = this->rx_buffer_[target_offset + 2] == 0x01 ? 1.0f : -1.0f;
    const float speed_cm_s = direction * this->rx_buffer_[target_offset + 3] * (100000.0f / 3600.0f);
    const int written = snprintf(payload + offset, sizeof(payload) - offset,
                                 "%s[%.1f,%.1f,%.1f]", i == 0 ? "" : ",",
                                 x_cm, y_cm, speed_cm_s);
    if (written < 0 || static_cast<size_t>(written) >= sizeof(payload) - offset) {
      ESP_LOGW(TAG, "Atomic target frame exceeded payload buffer");
      return;
    }
    offset += static_cast<size_t>(written);
  }
  if (offset + 3 >= sizeof(payload)) return;
  payload[offset++] = ']';
  payload[offset++] = '}';
  payload[offset] = '\0';
  this->target_frame_sensor_->publish_state(payload);
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
