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
