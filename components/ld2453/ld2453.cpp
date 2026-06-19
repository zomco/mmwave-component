#include "ld2453.h"

namespace esphome {
namespace ld2453 {

static const char *const TAG = "ld2453";

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
  if (now - this->last_rx_ms_ > 100 && !this->rx_buffer_.empty()) {
    this->rx_buffer_.clear();
  }

  while (this->available()) {
    this->last_rx_ms_ = now;
    this->process_byte_(this->read());
  }
}

void LD2453Component::process_byte_(uint8_t byte) {
  this->rx_buffer_.push_back(byte);

  if (this->rx_buffer_.size() >= 30) {
    if (this->rx_buffer_[0] == 0xAA && this->rx_buffer_[1] == 0xFF &&
        this->rx_buffer_[2] == 0x03 && this->rx_buffer_[3] == 0x00 &&
        this->rx_buffer_[28] == 0x55 && this->rx_buffer_[29] == 0xCC) {
      
      this->process_packet_();
      this->rx_buffer_.clear();
    } else {
      // Invalid frame, pop first byte and continue
      this->rx_buffer_.erase(this->rx_buffer_.begin());
    }
  }
}

int16_t LD2453Component::decode_value_(uint8_t low, uint8_t high) {
  // LD2453 sign-magnitude format: MSB (bit 15) indicates sign
  // 1 = positive, 0 = negative
  uint16_t val = (uint16_t(high) << 8) | low;
  bool is_positive = (val & 0x8000) != 0;
  int16_t magnitude = val & 0x7FFF;
  return is_positive ? magnitude : -magnitude;
}

void LD2453Component::process_packet_() {
  bool any_present = false;

  for (uint8_t i = 0; i < 3; i++) {
    uint8_t offset = 4 + (i * 8);
    
    int16_t x_mm = this->decode_value_(this->rx_buffer_[offset], this->rx_buffer_[offset+1]);
    int16_t y_mm = this->decode_value_(this->rx_buffer_[offset+2], this->rx_buffer_[offset+3]);
    int16_t speed_cm_s = this->decode_value_(this->rx_buffer_[offset+4], this->rx_buffer_[offset+5]);
    uint16_t res_mm = (uint16_t(this->rx_buffer_[offset+7]) << 8) | this->rx_buffer_[offset+6];

    // If resolution is 0 and x/y are 0, this target slot is empty
    bool target_valid = (res_mm > 0 || x_mm != 0 || y_mm != 0);
    
    if (target_valid) {
      any_present = true;
    }

    float x_cm = x_mm / 10.0f;
    float y_cm = y_mm / 10.0f;
    
    if (this->targets_[i].x != nullptr) this->targets_[i].x->publish_state(x_cm);
    if (this->targets_[i].y != nullptr) this->targets_[i].y->publish_state(y_cm);
    if (this->targets_[i].speed != nullptr) this->targets_[i].speed->publish_state(speed_cm_s);
    if (this->targets_[i].resolution != nullptr) this->targets_[i].resolution->publish_state(res_mm);

    // Coordinate Transformation (2D radar so local_z is 0)
    auto pos = Transform3D::transform(x_cm, y_cm, 0.0f, this->cal_);

    // Only set boundary if target is valid, otherwise it's technically not in boundary
    bool in_boundary = target_valid ? pos.in_boundary : false;

    if (this->targets_[i].room_x != nullptr) this->targets_[i].room_x->publish_state(pos.room_x);
    if (this->targets_[i].room_y != nullptr) this->targets_[i].room_y->publish_state(pos.room_y);
    if (this->targets_[i].room_z != nullptr) this->targets_[i].room_z->publish_state(pos.room_z);
    
    if (this->targets_[i].in_boundary != nullptr) {
      if (this->targets_[i].in_boundary->state != in_boundary || !this->targets_[i].in_boundary->has_state()) {
        this->targets_[i].in_boundary->publish_state(in_boundary);
      }
    }
  }

  if (this->presence_sensor_ != nullptr) {
    if (this->presence_sensor_->state != any_present || !this->presence_sensor_->has_state()) {
      this->presence_sensor_->publish_state(any_present);
    }
  }
}

} // namespace ld2453
} // namespace esphome
