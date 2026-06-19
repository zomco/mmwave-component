#include "ld2420.h"

#include <cstring>

namespace esphome {
namespace ld2420 {

static const char *const TAG = "ld2420";

void LD2420Component::setup() {
  ESP_LOGCONFIG(TAG, "Setting up LD2420 Component...");
}

void LD2420Component::dump_config() {
  ESP_LOGCONFIG(TAG, "LD2420:");
  LOG_SENSOR("  ", "Distance", this->distance_);
  LOG_BINARY_SENSOR("  ", "Presence", this->presence_sensor_);
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

void LD2420Component::loop() {
  const uint32_t now = millis();
  if (now - this->last_rx_ms_ > 1000 && this->buffer_pos_ > 0) {
    ESP_LOGV(TAG, "UART Timeout, resetting buffer");
    this->buffer_pos_ = 0;
  }

  while (this->available()) {
    this->last_rx_ms_ = now;
    this->readline_(this->read());
  }
}

void LD2420Component::readline_(int rx_data) {
  if (rx_data < 0) return;

  if (this->buffer_pos_ < MAX_FRAME_LENGTH) {
    this->buffer_[this->buffer_pos_++] = rx_data;
  } else {
    // Buffer full, drop first byte and shift
    memmove(this->buffer_, this->buffer_ + 1, MAX_FRAME_LENGTH - 1);
    this->buffer_[MAX_FRAME_LENGTH - 1] = rx_data;
  }

  // Check for Energy Frame Footer: F8 F7 F6 F5
  if (this->buffer_pos_ >= 4) {
    uint32_t footer;
    memcpy(&footer, &this->buffer_[this->buffer_pos_ - 4], 4);
    if (footer == ENERGY_FRAME_FOOTER) {
      // Find Header: F4 F3 F2 F1
      for (int i = 0; i <= this->buffer_pos_ - 8; i++) {
        uint32_t header;
        memcpy(&header, &this->buffer_[i], 4);
        if (header == ENERGY_FRAME_HEADER) {
          // Align buffer to start at header
          int frame_len = this->buffer_pos_ - i;
          if (i > 0) {
            memmove(this->buffer_, &this->buffer_[i], frame_len);
            this->buffer_pos_ = frame_len;
          }
          this->handle_energy_mode_();
          this->buffer_pos_ = 0;
          return;
        }
      }
      // If we found footer but no header, reset buffer
      this->buffer_pos_ = 0;
    }
  }
}

void LD2420Component::handle_energy_mode_() {
  // Energy Frame Structure:
  // 0-3: Header (F4 F3 F2 F1)
  // 4-5: Length (L L)
  // 6: Presence (1 byte)
  // 7-8: Distance (2 bytes, little-endian)
  // ... (Gate energies)
  // N-4..N: Footer (F8 F7 F6 F5)

  if (this->buffer_pos_ < 10) {
    ESP_LOGW(TAG, "Frame too short");
    return;
  }

  uint8_t presence = this->buffer_[6];
  uint16_t distance_cm = 0;
  memcpy(&distance_cm, &this->buffer_[7], 2);

  // Publish presence
  if (this->presence_sensor_ != nullptr) {
    bool is_present = (presence > 0);
    if (this->presence_sensor_->state != is_present || !this->presence_sensor_->has_state()) {
      this->presence_sensor_->publish_state(is_present);
    }
  }

  // Publish distance
  if (this->distance_ != nullptr) {
    this->distance_->publish_state(distance_cm);
  }

  // Calculate and publish coordinates
  this->publish_position_(distance_cm);
}

void LD2420Component::publish_position_(float range_cm) {
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
}

} // namespace ld2420
} // namespace esphome
