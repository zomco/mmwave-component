#include "ld2411s.h"
#include "esphome/core/log.h"

namespace esphome {
namespace ld2411s {

static const char *const TAG = "ld2411s";

void LD2411SComponent::setup() {
  ESP_LOGCONFIG(TAG, "Setting up LD2411S...");
}

void LD2411SComponent::dump_config() {
  ESP_LOGCONFIG(TAG, "LD2411S:");
  LOG_SENSOR("  ", "Distance", this->distance_sensor_);
  LOG_BINARY_SENSOR("  ", "Presence", this->presence_sensor_);
  LOG_BINARY_SENSOR("  ", "Moving Target", this->moving_target_sensor_);
  LOG_BINARY_SENSOR("  ", "Micro Target", this->micro_target_sensor_);
  LOG_SENSOR("  ", "Room X", this->room_x_);
  LOG_SENSOR("  ", "Room Y", this->room_y_);
  LOG_SENSOR("  ", "Room Z", this->room_z_);
  LOG_BINARY_SENSOR("  ", "In Boundary", this->in_boundary_sensor_);

  ESP_LOGCONFIG(TAG, "  Calibration:");
  ESP_LOGCONFIG(TAG, "    Radar pos:   X=%.1f cm  Y=%.1f cm  H=%.1f cm", cal_.radar_x, cal_.radar_y, cal_.radar_z);
  ESP_LOGCONFIG(TAG, "    Orientation: Yaw=%.1f°  Pitch=%.1f°  Roll=%.1f°", cal_.yaw, cal_.pitch, cal_.roll);
  ESP_LOGCONFIG(TAG, "    Distance gate: %.1f - %.1f cm (0 = off)", cal_.distance_min, cal_.distance_max);
}

void LD2411SComponent::loop() {
  uint32_t now = millis();
  
  // Presence watchdog - clear presence if no data for 1000ms
  if (now - this->last_rx_ms_ > 1000) {
    if (this->presence_sensor_ != nullptr && this->presence_sensor_->state) {
      this->presence_sensor_->publish_state(false);
    }
    if (this->moving_target_sensor_ != nullptr && this->moving_target_sensor_->state) {
      this->moving_target_sensor_->publish_state(false);
    }
    if (this->micro_target_sensor_ != nullptr && this->micro_target_sensor_->state) {
      this->micro_target_sensor_->publish_state(false);
    }
  }

  while (this->available()) {
    uint8_t byte;
    this->read_byte(&byte);
    
    if (now < this->mock_active_until_) continue;
    
    this->rx_buffer_.push_back(byte);
    
    if (this->data_state_ == DataState::IDLE) {
      if (this->rx_buffer_.size() == 2) {
        if (this->rx_buffer_[0] == 0xAA && this->rx_buffer_[1] == 0xAA) {
          this->data_state_ = DataState::READ_DATA;
        } else {
          this->rx_buffer_.erase(this->rx_buffer_.begin());
        }
      }
    } else if (this->data_state_ == DataState::READ_DATA) {
      if (this->rx_buffer_.size() == 7) {
        if (this->rx_buffer_[5] == 0x55 && this->rx_buffer_[6] == 0x55) {
          this->process_packet_();
        } else {
          ESP_LOGW(TAG, "Invalid packet tail");
        }
        this->rx_buffer_.clear();
        this->data_state_ = DataState::IDLE;
      }
    }
  }
}

void LD2411SComponent::process_packet_() {
  this->last_rx_ms_ = millis();

  uint8_t type = this->rx_buffer_[2];
  uint16_t dist_cm = this->rx_buffer_[3] | (this->rx_buffer_[4] << 8);

  uint32_t now_ms = millis();
  if (now_ms - this->last_publish_ms_ < 1000) {
    return;
  }
  this->last_publish_ms_ = now_ms;

  bool is_present = (type != 0x00);
  bool is_moving = (type == 0x01);
  bool is_micro = (type == 0x02);

  // 坐标变换（1-D：沿雷达正前方投射）+ 距离门边界过滤
  const auto pos = Transform1D::transform(static_cast<float>(dist_cm), this->cal_);

  if (this->room_x_ != nullptr) this->room_x_->publish_state(is_present ? pos.room_x : NAN);
  if (this->room_y_ != nullptr) this->room_y_->publish_state(is_present ? pos.room_y : NAN);
  if (this->room_z_ != nullptr) this->room_z_->publish_state(is_present ? pos.room_z : NAN);

  const bool in_boundary = is_present && pos.in_boundary;
  if (this->in_boundary_sensor_ != nullptr &&
      (!this->in_boundary_sensor_->has_state() || this->in_boundary_sensor_->state != in_boundary)) {
    this->in_boundary_sensor_->publish_state(in_boundary);
  }

  // 边界门控：距离门之外的目标默认不计入 presence
  if (this->boundary_gates_presence_ && !pos.in_boundary) {
    is_present = false;
    is_moving = false;
    is_micro = false;
  }

  if (this->presence_sensor_ != nullptr && (!this->presence_sensor_->has_state() || this->presence_sensor_->state != is_present)) {
    this->presence_sensor_->publish_state(is_present);
  }
  if (this->moving_target_sensor_ != nullptr && (!this->moving_target_sensor_->has_state() || this->moving_target_sensor_->state != is_moving)) {
    this->moving_target_sensor_->publish_state(is_moving);
  }
  if (this->micro_target_sensor_ != nullptr && (!this->micro_target_sensor_->has_state() || this->micro_target_sensor_->state != is_micro)) {
    this->micro_target_sensor_->publish_state(is_micro);
  }

  if (this->distance_sensor_ != nullptr) {
    this->distance_sensor_->publish_state(dist_cm);
  }
}

}  // namespace ld2411s
}  // namespace esphome

void esphome::ld2411s::LD2411SComponent::inject_mock_data(std::string data) {
  if (data == "0" || data == "reset") {
    this->mock_active_until_ = 0;
    this->rx_buffer_.clear();
    this->data_state_ = DataState::IDLE;
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
  
  for (uint8_t byte : mock_bytes) {
    this->rx_buffer_.push_back(byte);
    
    if (this->data_state_ == DataState::IDLE) {
      if (this->rx_buffer_.size() == 2) {
        if (this->rx_buffer_[0] == 0xAA && this->rx_buffer_[1] == 0xAA) {
          this->data_state_ = DataState::READ_DATA;
        } else {
          this->rx_buffer_.erase(this->rx_buffer_.begin());
        }
      }
    } else if (this->data_state_ == DataState::READ_DATA) {
      if (this->rx_buffer_.size() == 7) {
        if (this->rx_buffer_[5] == 0x55 && this->rx_buffer_[6] == 0x55) {
          this->process_packet_();
        } else {
          ESP_LOGW(TAG, "Invalid packet tail");
        }
        this->rx_buffer_.clear();
        this->data_state_ = DataState::IDLE;
      }
    }
  }
}
