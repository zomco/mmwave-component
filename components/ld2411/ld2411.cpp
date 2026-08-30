#include "ld2411.h"

namespace esphome {
namespace ld2411 {

static const char *const TAG = "ld2411";

void LD2411Component::setup() { ESP_LOGCONFIG(TAG, "Setting up LD2411 Component..."); }

void LD2411Component::dump_config() {
  ESP_LOGCONFIG(TAG, "LD2411:");
  LOG_BINARY_SENSOR("  ", "Presence", this->presence_sensor_);
  LOG_SENSOR("  ", "Motion State", this->motion_state_);
  LOG_SENSOR("  ", "Distance", this->distance_);
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

void LD2411Component::loop() {
  const uint32_t now = millis();
  if (now - this->last_rx_ms_ > 1000 && this->data_state_ != DataState::IDLE) {
    ESP_LOGV(TAG, "UART Timeout, resetting state");
    this->data_state_ = DataState::IDLE;
  }

  if (this->mock_active_until_ > 0 && now < this->mock_active_until_) {
    while (this->available())
      this->read();
    return;
  }

  while (this->available()) {
    this->last_rx_ms_ = now;
    this->process_byte_(this->read());
  }
}

void LD2411Component::process_byte_(uint8_t byte) {
  switch (this->data_state_) {
    case DataState::IDLE:
      if (byte == DATA_HDR) {
        this->data_state_ = DataState::HDR2;
      }
      break;

    case DataState::HDR2:
      if (byte == DATA_HDR) {
        this->data_state_ = DataState::STATUS;
      } else {
        this->data_state_ = DataState::IDLE;
      }
      break;

    case DataState::STATUS:
      this->data_status_ = byte;
      this->data_state_ = DataState::DIST_L;
      break;

    case DataState::DIST_L:
      this->data_dist_l_ = byte;
      this->data_state_ = DataState::DIST_H;
      break;

    case DataState::DIST_H:
      this->data_dist_h_ = byte;
      this->data_state_ = DataState::TAIL1;
      break;

    case DataState::TAIL1:
      if (byte == DATA_TAIL) {
        this->data_state_ = DataState::TAIL2;
      } else {
        ESP_LOGW(TAG, "Invalid Tail1: 0x%02X", byte);
        this->data_state_ = DataState::IDLE;
      }
      break;

    case DataState::TAIL2:
      if (byte == DATA_TAIL) {
        this->handle_data_frame_();
      } else {
        ESP_LOGW(TAG, "Invalid Tail2: 0x%02X", byte);
      }
      this->data_state_ = DataState::IDLE;
      break;
  }
}

void LD2411Component::handle_data_frame_() {
  uint16_t dist_raw = (uint16_t(this->data_dist_h_) << 8) | this->data_dist_l_;

  bool is_present = (this->data_status_ != 0);

  if (this->presence_sensor_ != nullptr) {
    if (this->presence_sensor_->state != is_present || !this->presence_sensor_->has_state()) {
      this->presence_sensor_->publish_state(is_present);
    }
  }

  if (this->motion_state_ != nullptr) {
    if (this->motion_state_->state != this->data_status_ || !this->motion_state_->has_state()) {
      this->motion_state_->publish_state(this->data_status_);
    }
  }

  // To avoid noise, only publish distance if a target is actually present.
  if (is_present) {
    float distance_cm = dist_raw;
    if (this->distance_ != nullptr) {
      this->distance_->publish_state(distance_cm);
    }
    this->publish_position_(distance_cm);
  } else {
    // Publish a default "far" value or leave untouched?
    // Often it's cleaner to just not update distance when nobody is present
    if (this->in_boundary_sensor_ != nullptr) {
      if (this->in_boundary_sensor_->state != false || !this->in_boundary_sensor_->has_state()) {
        this->in_boundary_sensor_->publish_state(false);
      }
    }
  }
}

void LD2411Component::publish_position_(float range_cm) {
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

/**
 * 注入十六进制测试数据。
 *
 * 与 ld2412/ld2450/ld245x 的实现保持一致：注入期间 loop() 丢弃真实串口字节，
 * 10 秒后自动恢复，"0"/"reset" 可以提前结束。字节走 process_byte_，也就是真实
 * 数据的同一条解析路径。
 */
void LD2411Component::inject_mock_data(const std::string &data) {
  if (data == "0" || data == "reset") {
    this->mock_active_until_ = 0;
    ESP_LOGD(TAG, "Mock data disabled, resuming normal hardware UART");
    return;
  }

  this->mock_active_until_ = millis() + 10000;
  for (size_t i = 0; i + 1 < data.length(); i += 2) {
    while (i + 1 < data.length() && data[i] == ' ')
      i++;
    if (i + 1 >= data.length())
      break;
    const std::string byte_str = data.substr(i, 2);
    this->process_byte_((uint8_t) strtol(byte_str.c_str(), nullptr, 16));
  }
}

}  // namespace ld2411
}  // namespace esphome
