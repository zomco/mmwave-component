#include "ld2451.h"

#include <cstdio>

namespace esphome {
namespace ld2451 {

static const char *const TAG = "ld2451";

void LD2451Component::setup() {
  ESP_LOGCONFIG(TAG, "Setting up LD2451...");
  this->rx_buffer_.reserve(64);

  // Read back what the module is actually configured with. These settings
  // survive a power cycle, so the ESP has no business assuming them - and the
  // write commands carry all four fields at once, which means a setter needs
  // the other three from a real answer rather than a guessed default.
  this->enqueue_command_(0x0012, nullptr, 0);
  this->enqueue_command_(0x0013, nullptr, 0);
  this->enqueue_command_(0x00A0, nullptr, 0);
}

void LD2451Component::dump_config() {
  ESP_LOGCONFIG(TAG, "LD2451:");
  LOG_BINARY_SENSOR("  ", "Presence", this->presence_sensor_);
  LOG_BINARY_SENSOR("  ", "Alarm", this->alarm_sensor_);
  LOG_SENSOR("  ", "Target Count", this->target_count_sensor_);
  LOG_TEXT_SENSOR("  ", "Firmware Version", this->firmware_version_sensor_);
  LOG_TEXT_SENSOR("  ", "Direction Filter", this->direction_filter_sensor_);
  LOG_SENSOR("  ", "Max Detection Distance", this->max_detection_distance_sensor_);
  LOG_SENSOR("  ", "Min Speed", this->min_speed_sensor_);
  LOG_SENSOR("  ", "No Target Delay", this->no_target_delay_sensor_);
  LOG_SENSOR("  ", "Trigger Count", this->trigger_count_sensor_);
  LOG_SENSOR("  ", "SNR Threshold", this->snr_threshold_sensor_);
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

  this->service_command_queue_(now);

  // Removed boot_phase_ configuration override to allow the radar to use its internal EEPROM settings.

  // Diagnostic: every 5 seconds, report byte count
  if (now - this->last_diag_ms_ >= 5000) {
    ESP_LOGV(TAG, "DIAG: %u bytes received in last 5s, %u data frames parsed, available()=%d", this->diag_bytes_,
             this->diag_frames_, this->available());
    this->diag_bytes_ = 0;
    this->diag_frames_ = 0;
    this->last_diag_ms_ = now;
  }

  if (now - this->last_rx_ms_ > 100 && !this->rx_buffer_.empty()) {
    this->rx_buffer_.clear();
  }

  while (this->available()) {
    this->last_rx_ms_ = now;
    uint8_t b = this->read();
    this->diag_bytes_++;

    if (now >= this->mock_active_until_) {
      this->process_byte_(b);
    }
  }

  // Presence watchdog. A configuration session silences the data stream by
  // design, so a parameter read must not read as the radar having gone away.
  if (now - this->last_rx_ms_ > 1000 && now >= this->config_session_until_) {
    if (this->presence_sensor_ != nullptr && this->presence_sensor_->state) {
      this->presence_sensor_->publish_state(false);
    }
    if (this->alarm_sensor_ != nullptr && this->alarm_sensor_->state) {
      this->alarm_sensor_->publish_state(false);
    }
    if (this->target_count_sensor_ != nullptr) {
      if (this->target_count_sensor_->state != 0 || !this->target_count_sensor_->has_state()) {
        this->target_count_sensor_->publish_state(0);
      }
    }
  }
}

// Timings for one configuration session. Protocol 1.4.1 requires
// enable-config -> command -> end-config with time for the radar to answer
// (and to finish its flash write) in between. Staging the writes through
// loop() keeps the component non-blocking; the previous inline delay() chain
// stalled it for 450 ms, well over ESPHome's 30 ms budget.
static const uint32_t CONFIG_OPEN_MS = 100;
static const uint32_t COMMAND_SETTLE_MS = 250;
static const uint32_t CONFIG_CLOSE_MS = 100;

void LD2451Component::write_command_frame_(uint16_t command, const uint8_t *command_value, uint8_t command_value_len) {
  const uint16_t len = 2 + command_value_len;
  std::vector<uint8_t> cmd;
  cmd.reserve(12 + command_value_len);
  cmd.insert(cmd.end(), {0xFD, 0xFC, 0xFB, 0xFA});
  cmd.push_back(len & 0xFF);
  cmd.push_back((len >> 8) & 0xFF);
  cmd.push_back(command & 0xFF);
  cmd.push_back((command >> 8) & 0xFF);
  if (command_value != nullptr && command_value_len > 0) {
    cmd.insert(cmd.end(), command_value, command_value + command_value_len);
  }
  cmd.insert(cmd.end(), {0x04, 0x03, 0x02, 0x01});
  this->write_array(cmd.data(), cmd.size());
}

void LD2451Component::enqueue_command_(uint16_t command, const uint8_t *command_value, uint8_t command_value_len) {
  PendingCommand pending;
  pending.command = command;
  if (command_value != nullptr && command_value_len > 0) {
    pending.value.assign(command_value, command_value + command_value_len);
  }
  this->command_queue_.push_back(std::move(pending));
}

void LD2451Component::service_command_queue_(uint32_t now) {
  if (this->command_phase_ == CommandPhase::IDLE && this->command_queue_.empty())
    return;
  if (now < this->command_next_ms_)
    return;

  // Hold the watchdog off for the whole session, not just the current step.
  this->config_session_until_ = now + CONFIG_OPEN_MS + COMMAND_SETTLE_MS + CONFIG_CLOSE_MS + 1000;

  switch (this->command_phase_) {
    case CommandPhase::IDLE: {
      const uint8_t enable_value[2] = {0x01, 0x00};
      this->write_command_frame_(0x00FF, enable_value, sizeof(enable_value));
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
        this->write_command_frame_(0x00FE, nullptr, 0);
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

void LD2451Component::query_firmware_version() { this->enqueue_command_(0x00A0, nullptr, 0); }
void LD2451Component::query_detection_params() { this->enqueue_command_(0x0012, nullptr, 0); }
void LD2451Component::query_sensitivity_params() { this->enqueue_command_(0x0013, nullptr, 0); }

void LD2451Component::send_detection_params_() {
  const uint8_t value[4] = {this->max_detection_distance_, this->direction_filter_, this->min_speed_,
                            this->no_target_delay_};
  this->enqueue_command_(0x0002, value, sizeof(value));
  this->enqueue_command_(0x0012, nullptr, 0);
}

void LD2451Component::set_max_detection_distance(uint8_t metres) {
  // Protocol 1.2.3 accepts 0x0A to 0xFF metres; anything below reads as a
  // configuration error rather than a very short range.
  this->max_detection_distance_ = std::max<uint8_t>(metres, 10);
  this->send_detection_params_();
}

void LD2451Component::set_direction_filter(uint8_t direction) {
  this->direction_filter_ = std::min<uint8_t>(direction, 2);
  this->send_detection_params_();
}

void LD2451Component::set_min_speed(uint8_t kmh) {
  this->min_speed_ = std::min<uint8_t>(kmh, 120);
  this->send_detection_params_();
}

void LD2451Component::set_no_target_delay(uint8_t seconds) {
  this->no_target_delay_ = seconds;
  this->send_detection_params_();
}

void LD2451Component::send_sensitivity_params_() {
  const uint8_t value[4] = {this->trigger_count_, this->snr_threshold_, 0x00, 0x00};
  this->enqueue_command_(0x0003, value, sizeof(value));
  this->enqueue_command_(0x0013, nullptr, 0);
}

void LD2451Component::set_trigger_count(uint8_t count) {
  this->trigger_count_ = std::min<uint8_t>(std::max<uint8_t>(count, 1), 10);
  this->send_sensitivity_params_();
}

void LD2451Component::set_snr_threshold(uint8_t level) {
  // 0 means "keep the radar's own default"; the configurable band is 3 to 8.
  this->snr_threshold_ = (level == 0) ? 0 : std::min<uint8_t>(std::max<uint8_t>(level, 3), 8);
  this->send_sensitivity_params_();
}

void LD2451Component::factory_reset() {
  this->enqueue_command_(0x00A2, nullptr, 0);
  ESP_LOGI(TAG, "Factory reset sent");
}

void LD2451Component::restart_module() {
  this->enqueue_command_(0x00A3, nullptr, 0);
  ESP_LOGI(TAG, "Restart sent");
}

void LD2451Component::process_ack_() {
  if (this->rx_buffer_.size() < 10)
    return;
  uint16_t command = (uint16_t(this->rx_buffer_[7]) << 8) | this->rx_buffer_[6];
  uint16_t status = (uint16_t(this->rx_buffer_[9]) << 8) | this->rx_buffer_[8];

  uint8_t data_len = 0;
  const uint8_t *data = nullptr;
  uint16_t total_len = (uint16_t(this->rx_buffer_[5]) << 8) | this->rx_buffer_[4];
  if (total_len > 4) {
    data_len = total_len - 4;
    data = &this->rx_buffer_[10];
  }

  this->handle_ack_data_(command, status, data, data_len);
}

void LD2451Component::handle_ack_data_(uint16_t command, uint16_t status, const uint8_t *data, uint8_t data_len) {
  ESP_LOGD(TAG, "Received ACK for command 0x%04X, status: 0x%04X", command, status);
  if (status != 0) {
    ESP_LOGW(TAG, "Command 0x%04X failed!", command);
    return;
  }

  // Protocol 1.2.7: 2B firmware type (0x2451) + 2B major + 4B minor,
  // e.g. 51 24 | 01 01 | 10 15 05 24  ->  V1.01.24051510
  if (command == 0x01A0 && data_len >= 8) {
    const uint16_t type = (uint16_t(data[1]) << 8) | data[0];
    char version[32];
    snprintf(version, sizeof(version), "V%u.%02u.%02X%02X%02X%02X", data[3], data[2], data[7], data[6], data[5],
             data[4]);
    ESP_LOGI(TAG, "Radar firmware: %s (type 0x%04X)", version, type);
    if (this->firmware_version_sensor_ != nullptr)
      this->firmware_version_sensor_->publish_state(version);
  }

  // Detection params ACK: 4 bytes (MaxDist, Direction, MinSpeed, Delay)
  if (command == 0x0112 && data_len >= 4) {
    this->max_detection_distance_ = data[0];
    this->direction_filter_ = data[1];
    this->min_speed_ = data[2];
    this->no_target_delay_ = data[3];
    ESP_LOGI(TAG, "Detection Params: MaxDist=%dm, Dir=%d (0=away,1=approach,2=both), MinSpeed=%dkm/h, Delay=%ds",
             data[0], data[1], data[2], data[3]);

    this->publish_if_changed_(this->max_detection_distance_sensor_, this->max_detection_distance_);
    this->publish_if_changed_(this->min_speed_sensor_, this->min_speed_);
    this->publish_if_changed_(this->no_target_delay_sensor_, this->no_target_delay_);
    if (this->direction_filter_sensor_ != nullptr) {
      const char *label =
          this->direction_filter_ == 0 ? "away" : (this->direction_filter_ == 1 ? "approaching" : "both");
      if (this->direction_filter_sensor_->state != label)
        this->direction_filter_sensor_->publish_state(label);
    }
  }

  // Sensitivity params ACK: 4 bytes (TriggerCount, SNRThreshold, ext, ext)
  if (command == 0x0113 && data_len >= 4) {
    this->trigger_count_ = data[0];
    this->snr_threshold_ = data[1];
    ESP_LOGI(TAG, "Sensitivity Params: TriggerCount=%d, SNRThreshold=%d, ext=%d, ext=%d", data[0], data[1], data[2],
             data[3]);

    this->publish_if_changed_(this->trigger_count_sensor_, this->trigger_count_);
    this->publish_if_changed_(this->snr_threshold_sensor_, this->snr_threshold_);
  }
}

void LD2451Component::process_byte_(uint8_t byte) {
  this->rx_buffer_.push_back(byte);

  if (this->rx_buffer_.size() >= 10 && this->rx_buffer_[0] == 0xFD && this->rx_buffer_[1] == 0xFC &&
      this->rx_buffer_[2] == 0xFB && this->rx_buffer_[3] == 0xFA) {
    size_t tail_idx = 0;
    for (size_t i = 4; i < this->rx_buffer_.size() - 3; i++) {
      if (this->rx_buffer_[i] == 0x04 && this->rx_buffer_[i + 1] == 0x03 && this->rx_buffer_[i + 2] == 0x02 &&
          this->rx_buffer_[i + 3] == 0x01) {
        tail_idx = i;
        break;
      }
    }
    if (tail_idx > 0) {
      this->process_ack_();
      this->rx_buffer_.erase(this->rx_buffer_.begin(), this->rx_buffer_.begin() + tail_idx + 4);
    } else if (this->rx_buffer_.size() > 64) {
      this->rx_buffer_.erase(this->rx_buffer_.begin());
    }
    return;
  }

  // Minimum frame is 10 bytes (Header 4 + Len 2 + Data 0 + Footer 4)
  if (this->rx_buffer_.size() >= 10) {
    // Check Header
    if (this->rx_buffer_[0] == 0xF4 && this->rx_buffer_[1] == 0xF3 && this->rx_buffer_[2] == 0xF2 &&
        this->rx_buffer_[3] == 0xF1) {
      uint16_t data_len = (uint16_t(this->rx_buffer_[5]) << 8) | this->rx_buffer_[4];
      if (data_len > 30) {
        this->rx_buffer_.erase(this->rx_buffer_.begin());
        return;
      }
      uint16_t full_frame_len = 4 + 2 + data_len + 4;

      if (this->rx_buffer_.size() >= full_frame_len) {
        // Check Footer
        if (this->rx_buffer_[full_frame_len - 4] == 0xF8 && this->rx_buffer_[full_frame_len - 3] == 0xF7 &&
            this->rx_buffer_[full_frame_len - 2] == 0xF6 && this->rx_buffer_[full_frame_len - 1] == 0xF5) {
          this->process_packet_();
          this->diag_frames_++;
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

/**
 * 仅在数值真正变化时发布。
 *
 * ESPHome 会对 binary_sensor 去重，但不会对数值 sensor 去重。移除 1 Hz 节流后
 * 本组件按雷达帧率发布，若不去重，空闲槽位会持续推送 NAN。NAN → NAN 视为未变化。
 */
void LD2451Component::publish_if_changed_(sensor::Sensor *s, float value) {
  if (s == nullptr)
    return;
  if (s->has_state()) {
    const float prev = s->state;
    if (std::isnan(prev) && std::isnan(value))
      return;
    if (prev == value)
      return;
  }
  s->publish_state(value);
}

void LD2451Component::process_packet_() {
  uint16_t data_len = (uint16_t(this->rx_buffer_[5]) << 8) | this->rx_buffer_[4];

  uint8_t target_count = 0;
  uint8_t alarm_info = 0;

  if (data_len >= 2) {
    target_count = this->rx_buffer_[6];
    alarm_info = this->rx_buffer_[7];  // 01: approaching, 00: no approaching
  }

  ESP_LOGV(TAG, "Data frame: len=%u targets=%u alarm=%u", data_len, target_count, alarm_info);

  // Calculate maximum targets we can parse from payload.
  uint8_t parseable_targets = (data_len - 2) / 5;
  uint8_t targets_to_process = std::min({target_count, parseable_targets, (uint8_t) 3});

  uint32_t now_ms = millis();
  if (now_ms - this->last_frame_publish_ms_ >= 100) {
    this->last_frame_publish_ms_ = now_ms;
    this->publish_target_frame_(targets_to_process);
  }

  // Entities publish at the radar's own frame rate; ESPHome deduplicates
  // unchanged binary_sensor states, and the fusion integration needs presence
  // to keep pace with DEFAULT_TRACK_TTL_S (1.2 s).
  this->last_publish_ms_ = now_ms;

  bool alarm = (alarm_info == 0x01);

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

  // 边界门控：只有落在距离门内的目标才计入 presence
  bool presence = false;

  for (uint8_t i = 0; i < 3; i++) {
    bool target_valid = (i < targets_to_process);

    if (target_valid) {
      uint16_t offset = 8 + (i * 5);

      int16_t raw_angle = this->rx_buffer_[offset];
      int16_t angle_deg = raw_angle - 0x80;

      float distance_m = this->rx_buffer_[offset + 1];

      uint8_t speed_dir = this->rx_buffer_[offset + 2];  // 01 approaching, 00 leaving
      uint8_t speed_val = this->rx_buffer_[offset + 3];
      float speed_kmh = (speed_dir == 0x01) ? speed_val : -(float) speed_val;

      float snr = this->rx_buffer_[offset + 4];

      // Convert polar to cartesian
      // distance is in meters, so distance * 100 for cm
      // Assuming 0 degrees is straight ahead (y-axis)
      float angle_rad = angle_deg * (M_PI / 180.0f);
      float x_cm = distance_m * 100.0f * std::sin(angle_rad);
      float y_cm = distance_m * 100.0f * std::cos(angle_rad);

      publish_if_changed_(this->targets_[i].distance, distance_m * 100.0f);
      publish_if_changed_(this->targets_[i].angle, angle_deg);
      publish_if_changed_(this->targets_[i].speed, speed_kmh);
      publish_if_changed_(this->targets_[i].snr, snr);
      publish_if_changed_(this->targets_[i].x, x_cm);
      publish_if_changed_(this->targets_[i].y, y_cm);

      // Coordinate Transformation (2D radar so local_z is 0)
      auto pos = Transform3D::transform(x_cm, y_cm, 0.0f, this->cal_);

      publish_if_changed_(this->targets_[i].room_x, pos.room_x);
      publish_if_changed_(this->targets_[i].room_y, pos.room_y);
      publish_if_changed_(this->targets_[i].room_z, pos.room_z);

      if (this->targets_[i].in_boundary != nullptr) {
        if (this->targets_[i].in_boundary->state != pos.in_boundary || !this->targets_[i].in_boundary->has_state()) {
          this->targets_[i].in_boundary->publish_state(pos.in_boundary);
        }
      }

      if (!this->boundary_gates_presence_ || pos.in_boundary)
        presence = true;
    } else {
      // Clear out unused targets. Positional entities must go to NAN rather than
      // keep the last tracked value, otherwise a vanished target stays "parked"
      // at its final coordinates in Home Assistant.
      publish_if_changed_(this->targets_[i].distance, NAN);
      publish_if_changed_(this->targets_[i].angle, NAN);
      publish_if_changed_(this->targets_[i].speed, NAN);
      publish_if_changed_(this->targets_[i].snr, NAN);
      publish_if_changed_(this->targets_[i].x, NAN);
      publish_if_changed_(this->targets_[i].y, NAN);
      publish_if_changed_(this->targets_[i].room_x, NAN);
      publish_if_changed_(this->targets_[i].room_y, NAN);
      publish_if_changed_(this->targets_[i].room_z, NAN);

      if (this->targets_[i].in_boundary != nullptr) {
        if (this->targets_[i].in_boundary->state != false || !this->targets_[i].in_boundary->has_state()) {
          this->targets_[i].in_boundary->publish_state(false);
        }
      }
    }
  }

  if (this->presence_sensor_ != nullptr) {
    if (this->presence_sensor_->state != presence || !this->presence_sensor_->has_state()) {
      this->presence_sensor_->publish_state(presence);
    }
  }
}

void LD2451Component::publish_target_frame_(uint8_t target_count) {
  if (this->target_frame_sensor_ == nullptr)
    return;

  char payload[176];
  size_t offset = snprintf(payload, sizeof(payload), "{\"v\":1,\"f\":%lu,\"ts\":%lu,\"t\":[",
                           static_cast<unsigned long>(++this->frame_id_), static_cast<unsigned long>(millis()));
  for (uint8_t i = 0; i < target_count && offset < sizeof(payload); i++) {
    const uint16_t target_offset = 8 + (i * 5);
    const int16_t angle_deg = static_cast<int16_t>(this->rx_buffer_[target_offset]) - 0x80;
    const float distance_cm = static_cast<float>(this->rx_buffer_[target_offset + 1]) * 100.0f;
    const float angle_rad = angle_deg * (M_PI / 180.0f);
    const float x_cm = distance_cm * std::sin(angle_rad);
    const float y_cm = distance_cm * std::cos(angle_rad);
    const float direction = this->rx_buffer_[target_offset + 2] == 0x01 ? 1.0f : -1.0f;
    const float speed_cm_s = direction * this->rx_buffer_[target_offset + 3] * (100000.0f / 3600.0f);
    const int written = snprintf(payload + offset, sizeof(payload) - offset, "%s[%.1f,%.1f,%.1f]", i == 0 ? "" : ",",
                                 x_cm, y_cm, speed_cm_s);
    if (written < 0 || static_cast<size_t>(written) >= sizeof(payload) - offset) {
      ESP_LOGW(TAG, "Atomic target frame exceeded payload buffer");
      return;
    }
    offset += static_cast<size_t>(written);
  }
  if (offset + 3 >= sizeof(payload))
    return;
  payload[offset++] = ']';
  payload[offset++] = '}';
  payload[offset] = '\0';
  this->target_frame_sensor_->publish_state(payload);
}

void LD2451Component::inject_mock_data(std::string data) {
  if (data == "0" || data == "reset") {
    this->mock_active_until_ = 0;
    this->rx_buffer_.clear();
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

  for (uint8_t b : mock_bytes) {
    this->process_byte_(b);
  }
}

}  // namespace ld2451
}  // namespace esphome
