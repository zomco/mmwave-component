#include "ld6002.h"
#include <cmath>
#include <cstring>

namespace esphome {
namespace ld6002 {

static const char *const TAG = "ld6002";

void LD6002Component::setup() {
  ESP_LOGCONFIG(TAG, "Setting up LD6002 Component...");
  this->payload_.reserve(128);
}

void LD6002Component::dump_config() {
  ESP_LOGCONFIG(TAG, "LD6002:");
  LOG_BINARY_SENSOR("  ", "Presence", this->presence_sensor_);
  LOG_SENSOR("  ", "Distance", this->distance_);
  LOG_SENSOR("  ", "Respiration Rate", this->respiration_rate_);
  LOG_SENSOR("  ", "Heart Rate", this->heart_rate_);
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

void LD6002Component::loop() {
  const uint32_t now = millis();
  if (now - this->last_rx_ms_ > 1000 && this->data_state_ != DataState::IDLE) {
    ESP_LOGV(TAG, "UART Timeout, resetting state");
    this->data_state_ = DataState::IDLE;
  }
  // Add presence watchdog
  if (now - this->last_rx_ms_ > 1000) {
    if (this->presence_sensor_ != nullptr && this->presence_sensor_->state) {
      this->presence_sensor_->publish_state(false);
    }
  }

  while (this->available()) {
    this->last_rx_ms_ = now;
    this->process_byte_(this->read());
  }

  // Periodic frame statistics dump every 10 seconds
  if (now - this->last_stats_ms_ >= 10000) {
    this->last_stats_ms_ = now;
    uint32_t total = this->frame_count_0F09_ + this->frame_count_0A04_ + this->frame_count_0A13_ +
                     this->frame_count_0A14_ + this->frame_count_0A15_ + this->frame_count_0A16_ +
                     this->frame_count_0A17_ + this->frame_count_other_;
    ESP_LOGI(TAG,
             "=== Frame Stats (10s) === total=%u | 0x0F09(Presence)=%u | 0x0A04(3D-Pos)=%u | "
             "0x0A13(Phase)=%u | 0x0A14(Breath)=%u | 0x0A15(Heart)=%u | 0x0A16(Dist)=%u | "
             "0x0A17(Track-Pos)=%u | other=%u",
             total, this->frame_count_0F09_, this->frame_count_0A04_, this->frame_count_0A13_, this->frame_count_0A14_,
             this->frame_count_0A15_, this->frame_count_0A16_, this->frame_count_0A17_, this->frame_count_other_);
    // Reset counters
    this->frame_count_0F09_ = 0;
    this->frame_count_0A04_ = 0;
    this->frame_count_0A13_ = 0;
    this->frame_count_0A14_ = 0;
    this->frame_count_0A15_ = 0;
    this->frame_count_0A16_ = 0;
    this->frame_count_0A17_ = 0;
    this->frame_count_other_ = 0;
  }
}

void LD6002Component::process_byte_(uint8_t byte) {
  switch (this->data_state_) {
    case DataState::IDLE:
      if (byte == DATA_SOF) {
        this->data_state_ = DataState::ID_H;
      }
      break;

    case DataState::ID_H:
      this->frame_id_ = (uint16_t(byte) << 8);
      this->data_state_ = DataState::ID_L;
      break;

    case DataState::ID_L:
      this->frame_id_ |= byte;
      this->data_state_ = DataState::LEN_H;
      break;

    case DataState::LEN_H:
      this->frame_len_ = (uint16_t(byte) << 8);
      this->data_state_ = DataState::LEN_L;
      break;

    case DataState::LEN_L:
      this->frame_len_ |= byte;
      if (this->frame_len_ > 1024) {
        ESP_LOGW(TAG, "Invalid Length: %d (0x%04X), ID=0x%04X", this->frame_len_, this->frame_len_, this->frame_id_);
        this->data_state_ = DataState::IDLE;
      } else {
        this->data_state_ = DataState::TYPE_H;
      }
      break;

    case DataState::TYPE_H:
      this->frame_type_ = (uint16_t(byte) << 8);
      this->data_state_ = DataState::TYPE_L;
      break;

    case DataState::TYPE_L:
      this->frame_type_ |= byte;
      this->data_state_ = DataState::HEAD_CKSUM;
      break;

    case DataState::HEAD_CKSUM: {
      uint8_t calc_cksum = DATA_SOF ^ (this->frame_id_ >> 8) ^ (this->frame_id_ & 0xFF) ^ (this->frame_len_ >> 8) ^
                           (this->frame_len_ & 0xFF) ^ (this->frame_type_ >> 8) ^ (this->frame_type_ & 0xFF);
      calc_cksum = ~calc_cksum;
      if (byte != calc_cksum) {
        ESP_LOGW(TAG, "Header Checksum error! Expected 0x%02X, got 0x%02X (Type 0x%04X, Len %d)", calc_cksum, byte,
                 this->frame_type_, this->frame_len_);
        this->data_state_ = DataState::IDLE;
      } else {
        if (this->frame_len_ == 0) {
          this->process_packet_();
          this->data_state_ = DataState::IDLE;
        } else {
          this->payload_.clear();
          this->payload_idx_ = 0;
          this->data_state_ = DataState::DATA;
        }
      }
      break;
    }

    case DataState::DATA:
      this->payload_.push_back(byte);
      this->payload_idx_++;
      if (this->payload_idx_ >= this->frame_len_) {
        this->data_state_ = DataState::DATA_CKSUM;
      }
      break;

    case DataState::DATA_CKSUM: {
      uint8_t calc_cksum = 0;
      for (uint8_t b : this->payload_) {
        calc_cksum ^= b;
      }
      calc_cksum = ~calc_cksum;
      if (byte != calc_cksum) {
        ESP_LOGW(TAG, "Data Checksum error! Expected 0x%02X, got 0x%02X for Type 0x%04X", calc_cksum, byte,
                 this->frame_type_);
      } else {
        this->process_packet_();
      }
      this->data_state_ = DataState::IDLE;
      break;
    }
  }
}

void LD6002Component::process_packet_() {
  switch (this->frame_type_) {
    case 0x0F09: {  // Presence
      this->frame_count_0F09_++;
      if (this->payload_.size() >= 2) {
        uint16_t is_human = (uint16_t(this->payload_[1]) << 8) | this->payload_[0];
        bool present = (is_human != 0);
        if (this->presence_sensor_ != nullptr) {
          if (this->presence_sensor_->state != present || !this->presence_sensor_->has_state()) {
            this->presence_sensor_->publish_state(present);
          }
        }
      }
      break;
    }

    case 0x0A04: {  // Personnel Position / 3D target
      this->frame_count_0A04_++;
      if (this->payload_.size() >= 16) {
        int32_t target_num = 0;
        std::memcpy(&target_num, &this->payload_[0], 4);
        ESP_LOGI(TAG, "0x0A04 received! target_num=%d, payload_size=%zu", target_num, this->payload_.size());
        if (target_num > 0) {
          float x_m = 0, y_m = 0, z_m = 0;
          std::memcpy(&x_m, &this->payload_[4], 4);
          std::memcpy(&y_m, &this->payload_[8], 4);
          std::memcpy(&z_m, &this->payload_[12], 4);
          ESP_LOGI(TAG, "0x0A04 position: x=%.3f y=%.3f z=%.3f", x_m, y_m, z_m);
          this->publish_position_(x_m, y_m, z_m);
        } else if (target_num == 0) {
          this->publish_position_(0, 0, 0);
        }
      }
      break;
    }

    case 0x0A16: {  // Distance
      this->frame_count_0A16_++;
      if (this->payload_.size() >= 8) {
        uint32_t flag = 0;
        std::memcpy(&flag, &this->payload_[0], 4);
        if (flag == 1) {
          float distance_cm = 0;
          std::memcpy(&distance_cm, &this->payload_[4], 4);
          this->last_distance_cm_ = distance_cm;
          if (this->distance_ != nullptr) {
            this->distance_->publish_state(distance_cm);
          }

          // LD6002 is a 1D radar. Synthesize target coordinates based on distance.
          this->publish_position_(0, distance_cm / 100.0f, 0);
        } else {
          this->publish_position_(0, 0, 0);
        }
      }
      break;
    }

    case 0x0A14: {  // Respiration Rate
      this->frame_count_0A14_++;
      if (this->payload_.size() >= 4) {
        float rate = 0;
        std::memcpy(&rate, &this->payload_[0], 4);
        if (this->respiration_rate_ != nullptr) {
          this->respiration_rate_->publish_state(rate);
        }
      }
      break;
    }

    case 0x0A15: {  // Heart Rate
      this->frame_count_0A15_++;
      if (this->payload_.size() >= 4) {
        float rate = 0;
        std::memcpy(&rate, &this->payload_[0], 4);
        if (this->heart_rate_ != nullptr) {
          this->heart_rate_->publish_state(rate);
        }
      }
      break;
    }

    case 0x0A17: {  // Tracked Position
      this->frame_count_0A17_++;
      ESP_LOGI(TAG, "0x0A17 received! payload_size=%zu", this->payload_.size());
      if (this->payload_.size() >= 12) {
        float x_m = 0, y_m = 0, z_m = 0;
        std::memcpy(&x_m, &this->payload_[0], 4);
        std::memcpy(&y_m, &this->payload_[4], 4);
        std::memcpy(&z_m, &this->payload_[8], 4);
        ESP_LOGI(TAG, "0x0A17 position: x=%.3f y=%.3f z=%.3f", x_m, y_m, z_m);
        this->publish_position_(x_m, y_m, z_m);
      }
      break;
    }

    case 0x0A13: {  // Phase data
      this->frame_count_0A13_++;
      break;
    }

    default:
      this->frame_count_other_++;
      ESP_LOGW(TAG, "Unknown frame type: 0x%04X, len: %zu", this->frame_type_, this->payload_.size());
      break;
  }
}

void LD6002Component::publish_position_(float x_m, float y_m, float z_m) {
  uint32_t now_ms = millis();
  if (now_ms - this->last_publish_ms_ < 1000)
    return;
  this->last_publish_ms_ = now_ms;

  // Convert meters to cm for internal transformation
  float x_cm = x_m * 100.0f;
  float y_cm = y_m * 100.0f;
  float z_cm = z_m * 100.0f;

  float radial_dist = sqrtf(x_cm * x_cm + y_cm * y_cm + z_cm * z_cm);
  auto pos = Transform3D::transform(x_cm, y_cm, z_cm, radial_dist, this->cal_);

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

}  // namespace ld6002
}  // namespace esphome
