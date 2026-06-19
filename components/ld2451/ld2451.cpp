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
    this->process_byte_(this->read());
  }
}

void LD2451Component::process_byte_(uint8_t byte) {
  this->rx_buffer_.push_back(byte);

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
    } else {
      // Invalid header, drop byte
      this->rx_buffer_.erase(this->rx_buffer_.begin());
    }
  }
}

void LD2451Component::process_packet_() {
  uint16_t data_len = (uint16_t(this->rx_buffer_[5]) << 8) | this->rx_buffer_[4];
  
  if (data_len < 2) return; // Need at least target_count and alarm_info

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

      if (this->targets_[i].distance != nullptr) this->targets_[i].distance->publish_state(distance_m);
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

} // namespace ld2451
} // namespace esphome
