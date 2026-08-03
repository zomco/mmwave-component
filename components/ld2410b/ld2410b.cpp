#include "ld2410b.h"

namespace esphome {
namespace ld2410b {

static const char *const TAG = "ld2410b";

// Commands
static constexpr uint8_t CMD_ENABLE_CONF = 0xFF;
static constexpr uint8_t CMD_DISABLE_CONF = 0xFE;
static constexpr uint8_t CMD_ENABLE_ENG = 0x62;

// Header & Footer size
static constexpr uint8_t HEADER_FOOTER_SIZE = 4;
static constexpr uint8_t CMD_FRAME_HEADER[HEADER_FOOTER_SIZE] = {0xFD, 0xFC, 0xFB, 0xFA};
static constexpr uint8_t CMD_FRAME_FOOTER[HEADER_FOOTER_SIZE] = {0x04, 0x03, 0x02, 0x01};
static constexpr uint8_t DATA_FRAME_HEADER[HEADER_FOOTER_SIZE] = {0xF4, 0xF3, 0xF2, 0xF1};
static constexpr uint8_t DATA_FRAME_FOOTER[HEADER_FOOTER_SIZE] = {0xF8, 0xF7, 0xF6, 0xF5};

static inline bool validate_header_footer(const uint8_t *header_footer, const uint8_t *buffer) {
  return std::memcmp(header_footer, buffer, HEADER_FOOTER_SIZE) == 0;
}

void LD2410BComponent::setup() {
  ESP_LOGCONFIG(TAG, "Setting up LD2410B Component...");
  
  const uint8_t enable_cmd_value[2] = {0x01, 0x00};
  this->send_command_(CMD_ENABLE_CONF, enable_cmd_value, sizeof(enable_cmd_value));
  this->send_command_(CMD_ENABLE_ENG, nullptr, 0);
  const uint8_t disable_cmd_value[2] = {0x01, 0x00};
  this->send_command_(CMD_DISABLE_CONF, disable_cmd_value, sizeof(disable_cmd_value));
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

  for (size_t i = 0; i < TOTAL_GATES; i++) {
    if (this->gate_move_sensors_[i] != nullptr) {
      LOG_SENSOR("  ", "Gate Move Energy", this->gate_move_sensors_[i]);
    }
    if (this->gate_still_sensors_[i] != nullptr) {
      LOG_SENSOR("  ", "Gate Still Energy", this->gate_still_sensors_[i]);
    }
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

void LD2410BComponent::loop() {
  const uint32_t now = millis();

  if (this->mock_active_until_ > 0 && now < this->mock_active_until_) {
    while (this->available()) this->read();
    return;
  }

  size_t avail = this->available();
  uint8_t buf[MAX_LINE_LENGTH];
  while (avail > 0) {
    size_t to_read = std::min(avail, sizeof(buf));
    if (!this->read_array(buf, to_read)) {
      break;
    }
    avail -= to_read;
    for (size_t i = 0; i < to_read; i++) {
      this->readline_(buf[i]);
    }
  }
}

void LD2410BComponent::readline_(int readch) {
  if (readch < 0) return;
  if (this->buffer_pos_ < MAX_LINE_LENGTH - 1) {
    this->buffer_data_[this->buffer_pos_++] = readch;
    this->buffer_data_[this->buffer_pos_] = 0;
  } else {
    this->buffer_pos_ = 0;
    return;
  }

  if (this->buffer_pos_ < HEADER_FOOTER_SIZE) return;
  
  if (validate_header_footer(DATA_FRAME_FOOTER, &this->buffer_data_[this->buffer_pos_ - 4])) {
    this->handle_periodic_data_();
    this->buffer_pos_ = 0;
  } else if (validate_header_footer(CMD_FRAME_FOOTER, &this->buffer_data_[this->buffer_pos_ - 4])) {
    this->handle_ack_data_();
    this->buffer_pos_ = 0;
  }
}

void LD2410BComponent::send_command_(uint8_t command_str, const uint8_t *command_value, uint8_t command_value_len) {
  this->write_array(CMD_FRAME_HEADER, sizeof(CMD_FRAME_HEADER));
  uint8_t len = 2;
  if (command_value != nullptr) {
    len += command_value_len;
  }
  uint8_t len_cmd[] = {len, 0x00, command_str, 0x00};
  this->write_array(len_cmd, sizeof(len_cmd));
  if (command_value != nullptr) {
    this->write_array(command_value, command_value_len);
  }
  this->write_array(CMD_FRAME_FOOTER, sizeof(CMD_FRAME_FOOTER));
  
  if (command_str != CMD_ENABLE_CONF && command_str != CMD_DISABLE_CONF) {
    delay(50);
  }
}

bool LD2410BComponent::handle_ack_data_() {
  if (this->buffer_pos_ < 10) return false;
  if (!validate_header_footer(CMD_FRAME_HEADER, this->buffer_data_)) return false;
  if (this->buffer_data_[7] != 0x01) return false;
  if (this->buffer_data_[8] || this->buffer_data_[9]) return false;
  return true;
}

void LD2410BComponent::handle_periodic_data_() {
  if (this->buffer_pos_ < 12 || !validate_header_footer(DATA_FRAME_HEADER, this->buffer_data_) ||
      this->buffer_data_[7] != 0xAA || this->buffer_data_[this->buffer_pos_ - 6] != 0x55 ||
      this->buffer_data_[this->buffer_pos_ - 5] != 0x00) {
    return;
  }
  
  bool engineering_mode = (this->buffer_data_[6] == 0x01);
  uint8_t target_state = this->buffer_data_[8];
  
  if (this->target_state_sensor_ != nullptr && (!this->target_state_sensor_->has_state() || this->target_state_sensor_->state != target_state)) {
    this->target_state_sensor_->publish_state(target_state);
  }
  
  bool presence = (target_state != 0x00);
  if (this->presence_sensor_ != nullptr && (!this->presence_sensor_->has_state() || this->presence_sensor_->state != presence)) {
    this->presence_sensor_->publish_state(presence);
  }

  uint16_t moving_distance = (uint16_t(this->buffer_data_[10]) << 8) | this->buffer_data_[9];
  uint8_t moving_energy = this->buffer_data_[11];
  uint16_t stationary_distance = (uint16_t(this->buffer_data_[13]) << 8) | this->buffer_data_[12];
  uint8_t stationary_energy = this->buffer_data_[14];
  uint16_t detection_distance = (uint16_t(this->buffer_data_[16]) << 8) | this->buffer_data_[15];

  if (this->moving_distance_sensor_ != nullptr) this->moving_distance_sensor_->publish_state(moving_distance);
  if (this->moving_energy_sensor_ != nullptr) this->moving_energy_sensor_->publish_state(moving_energy);
  if (this->stationary_distance_sensor_ != nullptr) this->stationary_distance_sensor_->publish_state(stationary_distance);
  if (this->stationary_energy_sensor_ != nullptr) this->stationary_energy_sensor_->publish_state(stationary_energy);
  if (this->detection_distance_sensor_ != nullptr) this->detection_distance_sensor_->publish_state(detection_distance);

  if (engineering_mode) {
    uint8_t max_moving_gate = this->buffer_data_[17];
    uint8_t max_stationary_gate = this->buffer_data_[18];
    uint8_t max_gate = std::max(max_moving_gate, max_stationary_gate);
    float max_dist_cm = max_gate * this->distance_resolution_ * 100.0f;
    
    if (this->max_distance_sensor_ != nullptr) {
      if (!this->max_distance_sensor_->has_state() || std::abs(this->max_distance_sensor_->state - max_dist_cm) > 1.0f) {
        this->max_distance_sensor_->publish_state(max_dist_cm);
      }
    }

    for (uint8_t i = 0; i < TOTAL_GATES; i++) {
      if (this->gate_move_sensors_[i] != nullptr) {
        this->gate_move_sensors_[i]->publish_state(this->buffer_data_[19 + i]);
      }
      if (this->gate_still_sensors_[i] != nullptr) {
        this->gate_still_sensors_[i]->publish_state(this->buffer_data_[28 + i]);
      }
    }
  }

  // Coordinate Transformation
  if (presence) {
    auto pos = Transform3D::transform(0.0f, (float)detection_distance, 0.0f, this->cal_);
    if (this->room_x_sensor_ != nullptr) this->room_x_sensor_->publish_state(pos.room_x);
    if (this->room_y_sensor_ != nullptr) this->room_y_sensor_->publish_state(pos.room_y);
    if (this->room_z_sensor_ != nullptr) this->room_z_sensor_->publish_state(pos.room_z);
    if (this->in_boundary_sensor_ != nullptr && (!this->in_boundary_sensor_->has_state() || this->in_boundary_sensor_->state != pos.in_boundary)) {
      this->in_boundary_sensor_->publish_state(pos.in_boundary);
    }
  } else {
    if (this->room_x_sensor_ != nullptr) this->room_x_sensor_->publish_state(0);
    if (this->room_y_sensor_ != nullptr) this->room_y_sensor_->publish_state(0);
    if (this->room_z_sensor_ != nullptr) this->room_z_sensor_->publish_state(0);
    if (this->in_boundary_sensor_ != nullptr && (!this->in_boundary_sensor_->has_state() || this->in_boundary_sensor_->state != false)) {
      this->in_boundary_sensor_->publish_state(false);
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
    this->readline_(byte);
  }
}

} // namespace ld2410b
} // namespace esphome
