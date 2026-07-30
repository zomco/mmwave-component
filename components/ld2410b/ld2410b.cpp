#include "ld2410b.h"

namespace esphome {
namespace ld2410b {

static const char *const TAG = "ld2410b";

void LD2410BComponent::setup() {
  ESP_LOGCONFIG(TAG, "Setting up LD2410B Component...");
  this->rx_buffer_.reserve(64);

  // Enable Engineering Mode to receive max gate data
  uint8_t enable_config[] = {0xFD, 0xFC, 0xFB, 0xFA, 0x04, 0x00, 0xFF, 0x00, 0x01, 0x00, 0x04, 0x03, 0x02, 0x01};
  this->write_array(enable_config, sizeof(enable_config));
  
  uint8_t enable_eng[] = {0xFD, 0xFC, 0xFB, 0xFA, 0x02, 0x00, 0x62, 0x00, 0x04, 0x03, 0x02, 0x01};
  this->write_array(enable_eng, sizeof(enable_eng));
  
  uint8_t end_config[] = {0xFD, 0xFC, 0xFB, 0xFA, 0x02, 0x00, 0xFE, 0x00, 0x04, 0x03, 0x02, 0x01};
  this->write_array(end_config, sizeof(end_config));
}

void LD2410BComponent::dump_config() {
  ESP_LOGCONFIG(TAG, "LD2410B:");
  LOG_BINARY_SENSOR("  ", "Presence", this->presence_sensor_);
  LOG_SENSOR("  ", "Target State", this->target_state_sensor_);
  LOG_SENSOR("  ", "Moving Distance", this->moving_distance_sensor_);
  LOG_SENSOR("  ", "Moving Energy", this->moving_energy_sensor_);
  LOG_SENSOR("  ", "Stationary Distance", this->stationary_distance_sensor_);
  LOG_SENSOR("  ", "Stationary Energy", this->stationary_energy_sensor_);
  LOG_SENSOR("  ", "Detection Distance", this->detection_distance_sensor_);
  LOG_SENSOR("  ", "Max Distance", this->max_distance_sensor_);
  
  LOG_SENSOR("  ", "Room X", this->room_x_sensor_);
  LOG_SENSOR("  ", "Room Y", this->room_y_sensor_);
  LOG_SENSOR("  ", "Room Z", this->room_z_sensor_);
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

void LD2410BComponent::loop() {
  const uint32_t now = millis();

  if (this->mock_active_until_ > 0 && now < this->mock_active_until_) {
    while (this->available()) this->read();
    return;
  }

  if (now - this->last_rx_ms_ > 100 && !this->rx_buffer_.empty()) {
    this->rx_buffer_.clear();
  }

  while (this->available()) {
    this->last_rx_ms_ = now;
    this->process_byte_(this->read());
  }
}

void LD2410BComponent::process_byte_(uint8_t byte) {
  this->rx_buffer_.push_back(byte);

  // Buffer overflow protection: prevent unbounded growth from corrupted data
  if (this->rx_buffer_.size() > 256) {
    this->rx_buffer_.clear();
    return;
  }

  if (this->rx_buffer_.size() >= 10) {
    if (this->rx_buffer_[0] == 0xF4 && this->rx_buffer_[1] == 0xF3 &&
        this->rx_buffer_[2] == 0xF2 && this->rx_buffer_[3] == 0xF1) {
      
      uint16_t data_len = (uint16_t(this->rx_buffer_[5]) << 8) | this->rx_buffer_[4];
      uint16_t full_frame_len = 4 + 2 + data_len + 4;
      
      if (this->rx_buffer_.size() >= full_frame_len) {
        if (this->rx_buffer_[full_frame_len - 4] == 0xF8 && 
            this->rx_buffer_[full_frame_len - 3] == 0xF7 &&
            this->rx_buffer_[full_frame_len - 2] == 0xF6 && 
            this->rx_buffer_[full_frame_len - 1] == 0xF5) {
          
          this->process_packet_();
          this->rx_buffer_.erase(this->rx_buffer_.begin(), this->rx_buffer_.begin() + full_frame_len);
        } else {
          this->rx_buffer_.erase(this->rx_buffer_.begin());
        }
      }
    } else {
      this->rx_buffer_.erase(this->rx_buffer_.begin());
    }
  }
}

void LD2410BComponent::process_packet_() {
  uint16_t data_len = (uint16_t(this->rx_buffer_[5]) << 8) | this->rx_buffer_[4];
  if (data_len < 10) return; // Basic Target Info is at least 10 bytes (Type + Head + 8 bytes data)

  uint8_t data_type = this->rx_buffer_[6];
  if (data_type != 0x02 && data_type != 0x01) return; // 0x02 is Basic, 0x01 is Engineering
  
  if (this->rx_buffer_[7] != 0xAA) return; // Inner data head

  // Validate inner data tail (0x55) and checksum (0x00)
  uint16_t full_frame_len = 4 + 2 + data_len + 4;
  uint16_t inner_tail_idx = full_frame_len - 4 - 2; // 2 bytes before outer tail: 0x55 + 0x00
  if (inner_tail_idx < 6 || inner_tail_idx + 1 >= this->rx_buffer_.size()) return;
  if (this->rx_buffer_[inner_tail_idx] != 0x55 || this->rx_buffer_[inner_tail_idx + 1] != 0x00) return;
  
  uint8_t target_state = this->rx_buffer_[8];
  uint16_t moving_distance = (uint16_t(this->rx_buffer_[10]) << 8) | this->rx_buffer_[9];
  uint8_t moving_energy = this->rx_buffer_[11];
  uint16_t stationary_distance = (uint16_t(this->rx_buffer_[13]) << 8) | this->rx_buffer_[12];
  uint8_t stationary_energy = this->rx_buffer_[14];
  uint16_t detection_distance = (uint16_t(this->rx_buffer_[16]) << 8) | this->rx_buffer_[15];
  
  bool presence = (target_state != 0x00);

  if (this->presence_sensor_ != nullptr) {
    if (this->presence_sensor_->state != presence || !this->presence_sensor_->has_state()) {
      this->presence_sensor_->publish_state(presence);
    }
  }
  if (this->target_state_sensor_ != nullptr) {
    if (this->target_state_sensor_->state != target_state || !this->target_state_sensor_->has_state()) {
      this->target_state_sensor_->publish_state(target_state);
    }
  }
  if (this->moving_distance_sensor_ != nullptr) {
    this->moving_distance_sensor_->publish_state(moving_distance);
  }
  if (this->moving_energy_sensor_ != nullptr) {
    this->moving_energy_sensor_->publish_state(moving_energy);
  }
  if (this->stationary_distance_sensor_ != nullptr) {
    this->stationary_distance_sensor_->publish_state(stationary_distance);
  }
  if (this->stationary_energy_sensor_ != nullptr) {
    this->stationary_energy_sensor_->publish_state(stationary_energy);
  }
  if (this->detection_distance_sensor_ != nullptr) {
    this->detection_distance_sensor_->publish_state(detection_distance);
  }

  // Parse engineering mode data
  if (data_type == 0x01 && full_frame_len > 24) {
    uint8_t max_moving_gate = this->rx_buffer_[17];
    uint8_t max_stationary_gate = this->rx_buffer_[18];
    uint8_t max_gate = std::max(max_moving_gate, max_stationary_gate);
    
    // Convert to cm
    float max_dist_cm = max_gate * this->distance_resolution_ * 100.0f;
    
    if (this->max_distance_sensor_ != nullptr) {
      if (!this->max_distance_sensor_->has_state() || 
          std::abs(this->max_distance_sensor_->state - max_dist_cm) > 1.0f) {
        this->max_distance_sensor_->publish_state(max_dist_cm);
      }
    }
  }

  // Coordinate Transformation
  if (presence) {
    // 1D radar: assume local_x = 0, local_y = detection_distance, local_z = 0
    auto pos = Transform3D::transform(0.0f, (float)detection_distance, 0.0f, this->cal_);

    if (this->room_x_sensor_ != nullptr) this->room_x_sensor_->publish_state(pos.room_x);
    if (this->room_y_sensor_ != nullptr) this->room_y_sensor_->publish_state(pos.room_y);
    if (this->room_z_sensor_ != nullptr) this->room_z_sensor_->publish_state(pos.room_z);
    
    if (this->in_boundary_sensor_ != nullptr) {
      if (this->in_boundary_sensor_->state != pos.in_boundary || !this->in_boundary_sensor_->has_state()) {
        this->in_boundary_sensor_->publish_state(pos.in_boundary);
      }
    }
  } else {
    // No target: clear coordinates to prevent stale target points on UI
    if (this->room_x_sensor_ != nullptr) this->room_x_sensor_->publish_state(0);
    if (this->room_y_sensor_ != nullptr) this->room_y_sensor_->publish_state(0);
    if (this->room_z_sensor_ != nullptr) this->room_z_sensor_->publish_state(0);
    
    if (this->in_boundary_sensor_ != nullptr) {
      if (this->in_boundary_sensor_->state != false || !this->in_boundary_sensor_->has_state()) {
        this->in_boundary_sensor_->publish_state(false);
      }
    }
  }
}

void LD2410BComponent::inject_mock_data(const std::string &data) {
  if (data == "0" || data == "reset") {
    this->mock_active_until_ = 0;
    return;
  }
  this->mock_active_until_ = millis() + 10000;
  for (size_t i = 0; i < data.length(); i += 2) {
    while (i < data.length() && data[i] == ' ') i++;
    if (i + 1 >= data.length()) break;
    std::string byteString = data.substr(i, 2);
    uint8_t byte = (uint8_t) strtol(byteString.c_str(), nullptr, 16);
    this->process_byte_(byte);
  }
}

} // namespace ld2410b
} // namespace esphome
