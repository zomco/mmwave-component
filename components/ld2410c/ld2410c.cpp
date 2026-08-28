#include "ld2410c.h"

#include <cstdio>

namespace esphome {
namespace ld2410c {

static const char *const TAG = "ld2410c";

// UART 静默超时（ms）。超过该时长没有收到任何字节，则认为雷达已离线，
// 主动把 presence 等状态推回 false，避免永久锁定在 on。
static const uint32_t UART_STALE_TIMEOUT_MS = 1000;

// Commands (protocol 2.2). Every LD2410C command word has a zero high byte, so
// only the low byte is carried here.
static constexpr uint8_t CMD_ENABLE_CONF = 0xFF;
static constexpr uint8_t CMD_DISABLE_CONF = 0xFE;
static constexpr uint8_t CMD_ENABLE_ENG = 0x62;
static constexpr uint8_t CMD_SET_MAX_GATES = 0x60;      // 2.2.3
static constexpr uint8_t CMD_QUERY_PARAMS = 0x61;       // 2.2.4
static constexpr uint8_t CMD_SET_SENSITIVITY = 0x64;    // 2.2.7
static constexpr uint8_t CMD_QUERY_FIRMWARE = 0xA0;     // 2.2.8
static constexpr uint8_t CMD_FACTORY_RESET = 0xA2;      // 2.2.10
static constexpr uint8_t CMD_RESTART = 0xA3;            // 2.2.11
static constexpr uint8_t CMD_SET_RESOLUTION = 0xAA;     // 2.2.16
static constexpr uint8_t CMD_QUERY_RESOLUTION = 0xAB;   // 2.2.17
static constexpr uint8_t CMD_SET_LIGHT_CTRL = 0xAD;     // 2.2.18
static constexpr uint8_t CMD_QUERY_LIGHT_CTRL = 0xAE;   // 2.2.19
static constexpr uint8_t CMD_NOISE_FLOOR = 0x0B;        // 2.2.20
static constexpr uint8_t CMD_QUERY_NOISE_FLOOR = 0x1B;  // 2.2.21

// Timings for one configuration session. The radar has to answer the
// enable-config command before it will look at anything else, and 2.2.3 /
// 2.2.7 write to flash. Staging these through loop() rather than delay()
// keeps the component inside ESPHome's 30 ms budget — the previous inline
// delay(50) chain stalled it for 150 ms on every boot.
static const uint32_t CONFIG_OPEN_MS = 100;
static const uint32_t COMMAND_SETTLE_MS = 250;
static const uint32_t CONFIG_CLOSE_MS = 100;

// Header & Footer size
static constexpr uint8_t HEADER_FOOTER_SIZE = 4;
static constexpr uint8_t CMD_FRAME_HEADER[HEADER_FOOTER_SIZE] = {0xFD, 0xFC, 0xFB, 0xFA};
static constexpr uint8_t CMD_FRAME_FOOTER[HEADER_FOOTER_SIZE] = {0x04, 0x03, 0x02, 0x01};
static constexpr uint8_t DATA_FRAME_HEADER[HEADER_FOOTER_SIZE] = {0xF4, 0xF3, 0xF2, 0xF1};
static constexpr uint8_t DATA_FRAME_FOOTER[HEADER_FOOTER_SIZE] = {0xF8, 0xF7, 0xF6, 0xF5};

static inline bool validate_header_footer(const uint8_t *header_footer, const uint8_t *buffer) {
  return std::memcmp(header_footer, buffer, HEADER_FOOTER_SIZE) == 0;
}

void LD2410CComponent::setup() {
  ESP_LOGCONFIG(TAG, "Setting up LD2410C Component...");

  this->move_sensitivity_.fill(0);
  this->still_sensitivity_.fill(0);

  // Engineering mode is off after every power cycle and the setting is not
  // retained, so it has to be re-enabled here — without it there are no gate
  // energies, no light reading and no OUT pin state.
  this->enqueue_command_(CMD_ENABLE_ENG, nullptr, 0);
  // Read back what the module is actually configured with. max_distance is
  // computed from the resolution, so a wrong assumption here scales every
  // reported range by 3.75x.
  this->enqueue_command_(CMD_QUERY_RESOLUTION, nullptr, 0);
  this->enqueue_command_(CMD_QUERY_PARAMS, nullptr, 0);
  this->enqueue_command_(CMD_QUERY_LIGHT_CTRL, nullptr, 0);
  this->enqueue_command_(CMD_QUERY_FIRMWARE, nullptr, 0);
}

void LD2410CComponent::dump_config() {
  ESP_LOGCONFIG(TAG, "LD2410C:");
  LOG_BINARY_SENSOR("  ", "Presence", this->presence_sensor_);
  LOG_SENSOR("  ", "Target State", this->target_state_sensor_);
  LOG_SENSOR("  ", "Moving Distance", this->moving_distance_sensor_);
  LOG_SENSOR("  ", "Moving Energy", this->moving_energy_sensor_);
  LOG_SENSOR("  ", "Stationary Distance", this->stationary_distance_sensor_);
  LOG_SENSOR("  ", "Stationary Energy", this->stationary_energy_sensor_);
  LOG_SENSOR("  ", "Detection Distance", this->detection_distance_sensor_);
  LOG_SENSOR("  ", "Max Distance", this->max_distance_sensor_);
  LOG_SENSOR("  ", "Light", this->light_sensor_);
  LOG_BINARY_SENSOR("  ", "OUT Pin", this->out_pin_sensor_);

  LOG_SENSOR("  ", "Room X", this->room_x_sensor_);
  LOG_SENSOR("  ", "Room Y", this->room_y_sensor_);
  LOG_SENSOR("  ", "Room Z", this->room_z_sensor_);
  LOG_BINARY_SENSOR("  ", "In Boundary", this->in_boundary_sensor_);

  LOG_TEXT_SENSOR("  ", "Firmware Version", this->firmware_version_sensor_);
  LOG_TEXT_SENSOR("  ", "Gate Sensitivity", this->gate_sensitivity_sensor_);
  LOG_TEXT_SENSOR("  ", "Noise Floor Status", this->noise_floor_status_sensor_);
  LOG_SENSOR("  ", "Max Moving Gate", this->max_moving_gate_sensor_);
  LOG_SENSOR("  ", "Max Still Gate", this->max_still_gate_sensor_);
  LOG_SENSOR("  ", "Unmanned Duration", this->unmanned_duration_sensor_);
  LOG_SENSOR("  ", "Distance Resolution", this->distance_resolution_sensor_);

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

void LD2410CComponent::loop() {
  const uint32_t now = millis();

  this->service_command_queue_(now);

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

void LD2410CComponent::check_uart_stale_(uint32_t now) {
  // last_rx_ms_ == 0 表示上电后还从未收到过数据，此时各传感器仍是初始 false，
  // 不需要（也不应该）推送状态。
  if (this->last_rx_ms_ == 0 || (now - this->last_rx_ms_) <= UART_STALE_TIMEOUT_MS)
    return;

  // A configuration session silences the data stream by design. Reporting the
  // radar as gone because a button was pressed would drop presence on every
  // parameter read.
  if (now < this->config_session_until_)
    return;

  if (this->presence_sensor_ != nullptr && this->presence_sensor_->state)
    this->presence_sensor_->publish_state(false);
  if (this->in_boundary_sensor_ != nullptr && this->in_boundary_sensor_->state)
    this->in_boundary_sensor_->publish_state(false);
}

void LD2410CComponent::readline_(int readch) {
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

// ── Command queue ────────────────────────────────────────────────────────────
//
// Every configuration command has to sit between an enable-config and an
// end-config (protocol 2.4.1). Queueing them means a batch — the five reads
// setup() issues, say — shares one session instead of opening and closing it
// five times, and it keeps loop() free of blocking waits.

void LD2410CComponent::write_command_frame_(uint8_t command_str, const uint8_t *command_value,
                                            uint8_t command_value_len) {
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
}

void LD2410CComponent::enqueue_command_(uint8_t command, const uint8_t *command_value, uint8_t command_value_len) {
  PendingCommand pending;
  pending.command = command;
  if (command_value != nullptr && command_value_len > 0) {
    pending.value.assign(command_value, command_value + command_value_len);
  }
  this->command_queue_.push_back(std::move(pending));
}

void LD2410CComponent::service_command_queue_(uint32_t now) {
  if (this->command_phase_ == CommandPhase::IDLE && this->command_queue_.empty())
    return;
  if (now < this->command_next_ms_)
    return;

  // Hold the watchdog off for the whole session, not just the current step.
  this->config_session_until_ = now + CONFIG_OPEN_MS + COMMAND_SETTLE_MS + CONFIG_CLOSE_MS + UART_STALE_TIMEOUT_MS;

  switch (this->command_phase_) {
    case CommandPhase::IDLE: {
      const uint8_t enable_value[2] = {0x01, 0x00};
      this->write_command_frame_(CMD_ENABLE_CONF, enable_value, sizeof(enable_value));
      this->command_phase_ = CommandPhase::CONFIG_OPEN;
      this->command_next_ms_ = now + CONFIG_OPEN_MS;
      break;
    }
    case CommandPhase::CONFIG_OPEN: {
      const PendingCommand &pending = this->command_queue_.front();
      this->write_command_frame_(pending.command, pending.value.empty() ? nullptr : pending.value.data(),
                                 static_cast<uint8_t>(pending.value.size()));
      this->command_phase_ = CommandPhase::COMMAND_SENT;
      this->command_next_ms_ = now + COMMAND_SETTLE_MS;
      break;
    }
    case CommandPhase::COMMAND_SENT: {
      this->command_queue_.erase(this->command_queue_.begin());
      if (this->command_queue_.empty()) {
        // 协议 2.2.2：结束配置命令的命令值为「无」，不得携带数据
        this->write_command_frame_(CMD_DISABLE_CONF, nullptr, 0);
        this->command_phase_ = CommandPhase::IDLE;
        this->command_next_ms_ = now + CONFIG_CLOSE_MS;
      } else {
        this->command_phase_ = CommandPhase::CONFIG_OPEN;
        this->command_next_ms_ = now;
      }
      break;
    }
  }
}

// ── Public commands ──────────────────────────────────────────────────────────

void LD2410CComponent::factory_reset() {
  this->enqueue_command_(CMD_FACTORY_RESET, nullptr, 0);
  ESP_LOGI(TAG, "Factory reset queued; values apply after the module restarts");
}

void LD2410CComponent::restart_module() {
  this->enqueue_command_(CMD_RESTART, nullptr, 0);
  ESP_LOGI(TAG, "Module restart queued");
}

void LD2410CComponent::query_firmware_version() { this->enqueue_command_(CMD_QUERY_FIRMWARE, nullptr, 0); }
void LD2410CComponent::query_parameters() { this->enqueue_command_(CMD_QUERY_PARAMS, nullptr, 0); }
void LD2410CComponent::query_distance_resolution() { this->enqueue_command_(CMD_QUERY_RESOLUTION, nullptr, 0); }
void LD2410CComponent::query_light_control() { this->enqueue_command_(CMD_QUERY_LIGHT_CTRL, nullptr, 0); }
void LD2410CComponent::query_noise_floor_status() { this->enqueue_command_(CMD_QUERY_NOISE_FLOOR, nullptr, 0); }

void LD2410CComponent::send_max_gate_command_() {
  // 2.2.3: three parameter words, each a 2-byte id followed by a 4-byte value.
  const uint8_t value[18] = {
      0x00,
      0x00,
      this->max_moving_gate_,
      0x00,
      0x00,
      0x00,
      0x01,
      0x00,
      this->max_still_gate_,
      0x00,
      0x00,
      0x00,
      0x02,
      0x00,
      static_cast<uint8_t>(this->unmanned_duration_ & 0xFF),
      static_cast<uint8_t>((this->unmanned_duration_ >> 8) & 0xFF),
      0x00,
      0x00,
  };
  this->enqueue_command_(CMD_SET_MAX_GATES, value, sizeof(value));
  this->enqueue_command_(CMD_QUERY_PARAMS, nullptr, 0);
}

void LD2410CComponent::set_max_moving_gate(uint8_t gate) {
  this->max_moving_gate_ = std::min<uint8_t>(gate, TOTAL_GATES - 1);
  this->send_max_gate_command_();
}

void LD2410CComponent::set_max_still_gate(uint8_t gate) {
  this->max_still_gate_ = std::min<uint8_t>(gate, TOTAL_GATES - 1);
  this->send_max_gate_command_();
}

void LD2410CComponent::set_unmanned_duration(uint16_t seconds) {
  this->unmanned_duration_ = seconds;
  this->send_max_gate_command_();
}

void LD2410CComponent::set_gate_sensitivity(uint16_t gate, uint8_t move_sensitivity, uint8_t still_sensitivity) {
  // 2.2.7: gate word, then moving and still sensitivity words.
  const uint8_t value[18] = {
      0x00,
      0x00,
      static_cast<uint8_t>(gate & 0xFF),
      static_cast<uint8_t>((gate >> 8) & 0xFF),
      0x00,
      0x00,
      0x01,
      0x00,
      move_sensitivity,
      0x00,
      0x00,
      0x00,
      0x02,
      0x00,
      still_sensitivity,
      0x00,
      0x00,
      0x00,
  };
  this->enqueue_command_(CMD_SET_SENSITIVITY, value, sizeof(value));
  this->enqueue_command_(CMD_QUERY_PARAMS, nullptr, 0);
}

float LD2410CComponent::get_uniform_move_sensitivity() const {
  if (!this->sensitivity_known_)
    return NAN;
  for (uint8_t i = 1; i < TOTAL_GATES; i++) {
    if (this->move_sensitivity_[i] != this->move_sensitivity_[0])
      return NAN;
  }
  return this->move_sensitivity_[0];
}

float LD2410CComponent::get_uniform_still_sensitivity() const {
  if (!this->sensitivity_known_)
    return NAN;
  for (uint8_t i = 1; i < TOTAL_GATES; i++) {
    if (this->still_sensitivity_[i] != this->still_sensitivity_[0])
      return NAN;
  }
  return this->still_sensitivity_[0];
}

void LD2410CComponent::request_distance_resolution(uint8_t index) {
  const uint8_t value[2] = {static_cast<uint8_t>(index & 0x01), 0x00};
  this->enqueue_command_(CMD_SET_RESOLUTION, value, sizeof(value));
  ESP_LOGI(TAG, "Distance resolution set to %s; it takes effect after the module restarts",
           index == 0 ? "0.75 m" : "0.20 m");
}

void LD2410CComponent::send_light_control_command_() {
  const uint8_t value[4] = {this->light_control_mode_, this->light_threshold_, this->out_pin_level_, 0x00};
  this->enqueue_command_(CMD_SET_LIGHT_CTRL, value, sizeof(value));
  this->enqueue_command_(CMD_QUERY_LIGHT_CTRL, nullptr, 0);
}

void LD2410CComponent::set_light_control_mode(uint8_t mode) {
  this->light_control_mode_ = std::min<uint8_t>(mode, 2);
  this->send_light_control_command_();
}

void LD2410CComponent::set_light_threshold(uint8_t threshold) {
  this->light_threshold_ = threshold;
  this->send_light_control_command_();
}

void LD2410CComponent::set_out_pin_level(uint8_t level) {
  this->out_pin_level_ = level ? 1 : 0;
  this->send_light_control_command_();
}

void LD2410CComponent::start_noise_floor_calibration(uint16_t seconds) {
  const uint8_t value[2] = {static_cast<uint8_t>(seconds & 0xFF), static_cast<uint8_t>((seconds >> 8) & 0xFF)};
  this->enqueue_command_(CMD_NOISE_FLOOR, value, sizeof(value));
  ESP_LOGI(TAG, "Noise floor calibration queued: leave the detection area, measurement starts in 10 s");
}

// ── ACK handling ─────────────────────────────────────────────────────────────

void LD2410CComponent::publish_gate_sensitivity_summary_() {
  if (this->gate_sensitivity_sensor_ == nullptr || !this->sensitivity_known_)
    return;
  // "move 20,20,…|still 25,25,…" — compact enough for a state string, and it
  // shows a per-gate configuration that the uniform controls cannot represent.
  char payload[128];
  size_t offset = snprintf(payload, sizeof(payload), "move ");
  for (uint8_t i = 0; i < TOTAL_GATES && offset < sizeof(payload); i++) {
    offset +=
        snprintf(payload + offset, sizeof(payload) - offset, "%s%u", i == 0 ? "" : ",", this->move_sensitivity_[i]);
  }
  if (offset < sizeof(payload))
    offset += snprintf(payload + offset, sizeof(payload) - offset, "|still ");
  for (uint8_t i = 0; i < TOTAL_GATES && offset < sizeof(payload); i++) {
    offset +=
        snprintf(payload + offset, sizeof(payload) - offset, "%s%u", i == 0 ? "" : ",", this->still_sensitivity_[i]);
  }
  this->gate_sensitivity_sensor_->publish_state(payload);
}

void LD2410CComponent::handle_ack_data_() {
  if (this->buffer_pos_ < 10)
    return;
  if (!validate_header_footer(CMD_FRAME_HEADER, this->buffer_data_))
    return;
  if (this->buffer_data_[7] != 0x01)
    return;

  const uint8_t command = this->buffer_data_[6];
  const uint16_t status = (uint16_t(this->buffer_data_[9]) << 8) | this->buffer_data_[8];
  if (status != 0) {
    ESP_LOGW(TAG, "Command 0x%02X failed (status 0x%04X)", command, status);
    return;
  }

  const uint16_t frame_len = (uint16_t(this->buffer_data_[5]) << 8) | this->buffer_data_[4];
  const uint8_t data_len = frame_len > 4 ? static_cast<uint8_t>(frame_len - 4) : 0;
  const uint8_t *data = &this->buffer_data_[10];

  switch (command) {
    // 2.2.8: 2B firmware type + 2B major + 4B minor, little-endian within each.
    // 00 01 | 02 01 | 16 24 06 22  ->  V1.02.22062416
    case CMD_QUERY_FIRMWARE: {
      if (data_len < 8)
        break;
      char version[32];
      snprintf(version, sizeof(version), "V%u.%02u.%02X%02X%02X%02X", data[3], data[2], data[7], data[6], data[5],
               data[4]);
      ESP_LOGI(TAG, "Radar firmware: %s (type 0x%04X)", version, (uint16_t(data[1]) << 8) | data[0]);
      if (this->firmware_version_sensor_ != nullptr)
        this->firmware_version_sensor_->publish_state(version);
      break;
    }

    // 2.2.4: 0xAA, max gate N, configured moving gate, configured still gate,
    // N+1 moving sensitivities, N+1 still sensitivities, 2B unmanned duration.
    case CMD_QUERY_PARAMS: {
      if (data_len < 3 || data[0] != 0xAA)
        break;
      const uint8_t gate_count = std::min<uint8_t>(data[1] + 1, TOTAL_GATES);
      if (data_len < static_cast<uint16_t>(4 + 2 * gate_count + 2))
        break;
      this->max_moving_gate_ = data[2];
      this->max_still_gate_ = data[3];
      for (uint8_t i = 0; i < gate_count; i++) {
        this->move_sensitivity_[i] = data[4 + i];
        this->still_sensitivity_[i] = data[4 + gate_count + i];
      }
      this->sensitivity_known_ = true;
      const uint8_t duration_offset = 4 + 2 * gate_count;
      this->unmanned_duration_ = (uint16_t(data[duration_offset + 1]) << 8) | data[duration_offset];

      ESP_LOGI(TAG, "Radar params: max gate %u, moving gate %u, still gate %u, unmanned %u s", data[1],
               this->max_moving_gate_, this->max_still_gate_, this->unmanned_duration_);

      if (this->max_moving_gate_sensor_ != nullptr)
        this->max_moving_gate_sensor_->publish_state(this->max_moving_gate_);
      if (this->max_still_gate_sensor_ != nullptr)
        this->max_still_gate_sensor_->publish_state(this->max_still_gate_);
      if (this->unmanned_duration_sensor_ != nullptr)
        this->unmanned_duration_sensor_->publish_state(this->unmanned_duration_);
      this->publish_gate_sensitivity_summary_();
      break;
    }

    // 2.2.17: 0x0000 = 0.75 m per gate, 0x0001 = 0.20 m.
    case CMD_QUERY_RESOLUTION: {
      if (data_len < 2)
        break;
      const uint16_t index = (uint16_t(data[1]) << 8) | data[0];
      this->distance_resolution_ = (index == 0x0001) ? 0.20f : 0.75f;
      ESP_LOGI(TAG, "Distance resolution: %.2f m per gate", this->distance_resolution_);
      if (this->distance_resolution_sensor_ != nullptr)
        this->distance_resolution_sensor_->publish_state(this->distance_resolution_);
      break;
    }

    // 2.2.19: mode, threshold, OUT default level.
    case CMD_QUERY_LIGHT_CTRL: {
      if (data_len < 3)
        break;
      this->light_control_mode_ = data[0];
      this->light_threshold_ = data[1];
      this->out_pin_level_ = data[2];
      ESP_LOGI(TAG, "Light control: mode %u, threshold %u, OUT idle level %s", this->light_control_mode_,
               this->light_threshold_, this->out_pin_level_ ? "high" : "low");
      break;
    }

    // 2.2.21: 0 idle, 1 running, 2 finished.
    case CMD_QUERY_NOISE_FLOOR: {
      if (data_len < 2)
        break;
      const uint16_t state = (uint16_t(data[1]) << 8) | data[0];
      const char *label = state == 0x0001 ? "running" : (state == 0x0002 ? "finished" : "idle");
      ESP_LOGI(TAG, "Noise floor calibration: %s", label);
      if (this->noise_floor_status_sensor_ != nullptr)
        this->noise_floor_status_sensor_->publish_state(label);
      break;
    }

    default:
      ESP_LOGD(TAG, "ACK for command 0x%02X accepted", command);
      break;
  }
}

void LD2410CComponent::handle_periodic_data_() {
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

  // Table 14: 0x00 no target, 0x01 moving, 0x02 still, 0x03 both. 0x04 to 0x06
  // report the progress of a noise-floor calibration and are not detections —
  // treating them as presence would park the sensor on for the whole run.
  // Provisional: the boundary gate below has the final say on presence.
  const bool detected = (target_state >= 0x01 && target_state <= 0x03);
  bool presence = detected;
  if (target_state >= 0x04 && target_state <= 0x06 && this->noise_floor_status_sensor_ != nullptr) {
    const char *label = target_state == 0x04 ? "running" : (target_state == 0x05 ? "finished" : "failed");
    if (this->noise_floor_status_sensor_->state != label)
      this->noise_floor_status_sensor_->publish_state(label);
  }

  uint16_t moving_distance = (uint16_t(this->buffer_data_[10]) << 8) | this->buffer_data_[9];
  uint8_t moving_energy = this->buffer_data_[11];
  uint16_t stationary_distance = (uint16_t(this->buffer_data_[13]) << 8) | this->buffer_data_[12];
  uint8_t stationary_energy = this->buffer_data_[14];
  uint16_t detection_distance = (uint16_t(this->buffer_data_[16]) << 8) | this->buffer_data_[15];

  if (this->moving_distance_sensor_ != nullptr)
    this->moving_distance_sensor_->publish_state(moving_distance);
  if (this->moving_energy_sensor_ != nullptr)
    this->moving_energy_sensor_->publish_state(moving_energy);
  if (this->stationary_distance_sensor_ != nullptr)
    this->stationary_distance_sensor_->publish_state(stationary_distance);
  if (this->stationary_energy_sensor_ != nullptr)
    this->stationary_energy_sensor_->publish_state(stationary_energy);
  if (this->detection_distance_sensor_ != nullptr)
    this->detection_distance_sensor_->publish_state(detection_distance);

  if (engineering_mode) {
    uint8_t max_moving_gate = this->buffer_data_[17];
    uint8_t max_stationary_gate = this->buffer_data_[18];
    uint8_t max_gate = std::max(max_moving_gate, max_stationary_gate);
    float max_dist_cm = max_gate * this->distance_resolution_ * 100.0f;

    if (this->max_distance_sensor_ != nullptr) {
      if (!this->max_distance_sensor_->has_state() ||
          std::abs(this->max_distance_sensor_->state - max_dist_cm) > 1.0f) {
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

    // Table 15 appends the photodiode reading and the OUT pin state after the
    // gate energies. The frame is 45 bytes when they are present; guard on the
    // length so a module that omits them is not read past its tail.
    if (this->buffer_pos_ >= 45) {
      const uint8_t light = this->buffer_data_[37];
      const bool out_pin = this->buffer_data_[38] != 0x00;
      if (this->light_sensor_ != nullptr &&
          (!this->light_sensor_->has_state() || this->light_sensor_->state != light)) {
        this->light_sensor_->publish_state(light);
      }
      if (this->out_pin_sensor_ != nullptr &&
          (!this->out_pin_sensor_->has_state() || this->out_pin_sensor_->state != out_pin)) {
        this->out_pin_sensor_->publish_state(out_pin);
      }
    }
  }

  // Coordinate Transformation
  if (detected) {
    auto pos = Transform3D::transform(0.0f, (float) detection_distance, 0.0f, this->cal_);
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
    // Order is parse -> transform -> filter -> publish: presence is decided
    // after the range gate, so a target beyond distance_max stays visible on
    // detection_distance while presence reports nobody in the room.
    presence = !this->boundary_gates_presence_ || pos.in_boundary;
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

  if (this->presence_sensor_ != nullptr &&
      (!this->presence_sensor_->has_state() || this->presence_sensor_->state != presence)) {
    this->presence_sensor_->publish_state(presence);
  }
}

void LD2410CComponent::inject_mock_data(const std::string &data) {
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

}  // namespace ld2410c
}  // namespace esphome
