#include "ld2412.h"

namespace esphome {
namespace ld2412 {

static const char *const TAG = "ld2412";

// UART 静默超时（ms）。超过该时长没有收到任何字节，则认为雷达已离线，
// 主动把 presence 等状态推回 false，避免永久锁定在 on。
static const uint32_t UART_STALE_TIMEOUT_MS = 1000;

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

void ld2412Component::setup() {
  ESP_LOGCONFIG(TAG, "Setting up ld2412 Component...");

  const uint8_t enable_cmd_value[2] = {0x01, 0x00};
  this->send_command_(CMD_ENABLE_CONF, enable_cmd_value, sizeof(enable_cmd_value));
  this->send_command_(CMD_ENABLE_ENG, nullptr, 0);
  const uint8_t disable_cmd_value[2] = {0x01, 0x00};
  this->send_command_(CMD_DISABLE_CONF, disable_cmd_value, sizeof(disable_cmd_value));
}

void ld2412Component::dump_config() {
  ESP_LOGCONFIG(TAG, "ld2412:");
  LOG_BINARY_SENSOR("  ", "Presence", this->presence_sensor_);
  LOG_SENSOR("  ", "Target State", this->target_state_sensor_);
  LOG_SENSOR("  ", "Moving Distance", this->moving_distance_sensor_);
  LOG_SENSOR("  ", "Moving Energy", this->moving_energy_sensor_);
  LOG_SENSOR("  ", "Stationary Distance", this->stationary_distance_sensor_);
  LOG_SENSOR("  ", "Stationary Energy", this->stationary_energy_sensor_);
  LOG_SENSOR("  ", "Light Sensor", this->light_sensor_);

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

void ld2412Component::loop() {
  const uint32_t now = millis();

  if (this->mock_active_until_ > 0 && now < this->mock_active_until_) {
    while (this->available())
      this->read();
    return;
  }

  size_t avail = this->available();
  if (avail > 0)
    this->last_rx_ms_ = now;
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

  this->check_uart_stale_(now);
}

void ld2412Component::check_uart_stale_(uint32_t now) {
  // last_rx_ms_ == 0 表示上电后还从未收到过数据，此时各传感器仍是初始 false，
  // 不需要（也不应该）推送状态。
  if (this->last_rx_ms_ == 0 || (now - this->last_rx_ms_) <= UART_STALE_TIMEOUT_MS)
    return;

  if (this->presence_sensor_ != nullptr && this->presence_sensor_->state)
    this->presence_sensor_->publish_state(false);
  if (this->in_boundary_sensor_ != nullptr && this->in_boundary_sensor_->state)
    this->in_boundary_sensor_->publish_state(false);
}

void ld2412Component::readline_(int readch) {
  if (readch < 0)
    return;
  if (this->buffer_pos_ < MAX_LINE_LENGTH - 1) {
    this->buffer_data_[this->buffer_pos_++] = readch;
    this->buffer_data_[this->buffer_pos_] = 0;
  } else {
    this->buffer_pos_ = 0;
    return;
  }

  if (this->buffer_pos_ < HEADER_FOOTER_SIZE)
    return;

  if (validate_header_footer(DATA_FRAME_FOOTER, &this->buffer_data_[this->buffer_pos_ - 4])) {
    this->handle_periodic_data_();
    this->buffer_pos_ = 0;
  } else if (validate_header_footer(CMD_FRAME_FOOTER, &this->buffer_data_[this->buffer_pos_ - 4])) {
    this->handle_ack_data_();
    this->buffer_pos_ = 0;
  }
}

void ld2412Component::send_command_(uint8_t command_str, const uint8_t *command_value, uint8_t command_value_len) {
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

bool ld2412Component::handle_ack_data_() {
  if (this->buffer_pos_ < 10)
    return false;
  if (!validate_header_footer(CMD_FRAME_HEADER, this->buffer_data_))
    return false;
  if (this->buffer_data_[7] != 0x01)
    return false;
  if (this->buffer_data_[8] || this->buffer_data_[9])
    return false;
  return true;
}

void ld2412Component::handle_periodic_data_() {
  if (this->buffer_pos_ < 12 || !validate_header_footer(DATA_FRAME_HEADER, this->buffer_data_) ||
      this->buffer_data_[7] != 0xAA || this->buffer_data_[this->buffer_pos_ - 6] != 0x55 ||
      this->buffer_data_[this->buffer_pos_ - 5] != 0x00) {
    return;
  }

  bool engineering_mode = (this->buffer_data_[6] == 0x01);
  uint8_t target_state = this->buffer_data_[8];

  if (this->target_state_sensor_ != nullptr &&
      (!this->target_state_sensor_->has_state() || this->target_state_sensor_->state != target_state)) {
    this->target_state_sensor_->publish_state(target_state);
  }

  // 雷达报的原始存在状态。最终发布要等边界判断出来 —— 见本函数末尾。
  const bool presence = (target_state != 0x00);

  uint16_t moving_distance = (uint16_t(this->buffer_data_[10]) << 8) | this->buffer_data_[9];
  uint8_t moving_energy = this->buffer_data_[11];
  uint16_t stationary_distance = (uint16_t(this->buffer_data_[13]) << 8) | this->buffer_data_[12];
  uint8_t stationary_energy = this->buffer_data_[14];

  if (this->moving_distance_sensor_ != nullptr)
    this->moving_distance_sensor_->publish_state(moving_distance);
  if (this->moving_energy_sensor_ != nullptr)
    this->moving_energy_sensor_->publish_state(moving_energy);
  if (this->stationary_distance_sensor_ != nullptr)
    this->stationary_distance_sensor_->publish_state(stationary_distance);
  if (this->stationary_energy_sensor_ != nullptr)
    this->stationary_energy_sensor_->publish_state(stationary_energy);

  uint16_t detection_distance = moving_distance > 0 ? moving_distance : stationary_distance;
  if (this->detection_distance_sensor_ != nullptr)
    this->detection_distance_sensor_->publish_state(detection_distance);

  if (engineering_mode) {
    uint8_t max_moving_gate = this->buffer_data_[15];
    uint8_t max_stationary_gate = this->buffer_data_[16];

    for (uint8_t i = 0; i < TOTAL_GATES; i++) {
      if (this->gate_move_sensors_[i] != nullptr) {
        this->gate_move_sensors_[i]->publish_state(this->buffer_data_[17 + i]);
      }
      if (this->gate_still_sensors_[i] != nullptr) {
        this->gate_still_sensors_[i]->publish_state(this->buffer_data_[31 + i]);
      }
    }

    if (this->light_sensor_ != nullptr) {
      this->light_sensor_->publish_state(this->buffer_data_[45]);
    }
  }

  // Coordinate Transformation
  bool in_boundary = false;
  bool have_position = false;
  if (presence) {
    auto pos = Transform3D::transform(0.0f, (float) detection_distance, 0.0f, this->cal_);
    in_boundary = pos.in_boundary;
    have_position = detection_distance > 0;
    if (this->room_x_sensor_ != nullptr)
      this->room_x_sensor_->publish_state(pos.room_x);
    if (this->room_y_sensor_ != nullptr)
      this->room_y_sensor_->publish_state(pos.room_y);
    if (this->room_z_sensor_ != nullptr)
      this->room_z_sensor_->publish_state(pos.room_z);
    if (this->in_boundary_sensor_ != nullptr &&
        (!this->in_boundary_sensor_->has_state() || this->in_boundary_sensor_->state != pos.in_boundary)) {
      this->in_boundary_sensor_->publish_state(pos.in_boundary);
    }
  } else {
    if (this->room_x_sensor_ != nullptr)
      this->room_x_sensor_->publish_state(0);
    if (this->room_y_sensor_ != nullptr)
      this->room_y_sensor_->publish_state(0);
    if (this->room_z_sensor_ != nullptr)
      this->room_z_sensor_->publish_state(0);
    if (this->in_boundary_sensor_ != nullptr &&
        (!this->in_boundary_sensor_->has_state() || this->in_boundary_sensor_->state != false)) {
      this->in_boundary_sensor_->publish_state(false);
    }
  }

  // 边界门控：开启时，界外目标不算存在。发布放在最后，因为它要等
  // 上面的坐标变换算出 in_boundary 才能决定。
  // 只有真的算出了位置，边界才有资格否决存在状态。拿缺失的位置去
  // 否定存在，正是让雷达看起来坏掉的那类 bug。
  const bool gated = (this->boundary_gates_presence_ && have_position) ? (presence && in_boundary) : presence;
  if (this->presence_sensor_ != nullptr &&
      (!this->presence_sensor_->has_state() || this->presence_sensor_->state != gated)) {
    this->presence_sensor_->publish_state(gated);
  }
}

void ld2412Component::inject_mock_data(const std::string &data) {
  if (data == "0" || data == "reset") {
    this->mock_active_until_ = 0;
    return;
  }
  this->mock_active_until_ = millis() + 10000;
  for (size_t i = 0; i < data.length(); i += 2) {
    while (i < data.length() && data[i] == ' ')
      i++;
    if (i + 1 >= data.length())
      break;
    std::string byteString = data.substr(i, 2);
    uint8_t byte = (uint8_t) strtol(byteString.c_str(), nullptr, 16);
    this->readline_(byte);
  }
}

}  // namespace ld2412
}  // namespace esphome
