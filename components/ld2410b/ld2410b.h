#pragma once

#include "esphome/core/component.h"
#include "esphome/core/log.h"
#include "esphome/components/uart/uart.h"
#include "esphome/components/sensor/sensor.h"
#include "esphome/components/binary_sensor/binary_sensor.h"
#include "esphome/components/text_sensor/text_sensor.h"
#include "ld2410b_transform.h"

#include <vector>
#include <array>
#include <cstdint>

namespace esphome {
namespace ld2410b {

// The longest frame the radar sends is the read-parameters ACK (protocol
// 2.2.4): 4 header + 2 length + 28 payload + 4 footer = 38 bytes. Engineering
// data frames are 45. 64 leaves room for both without a resize.
static constexpr uint8_t MAX_LINE_LENGTH = 64;
static constexpr uint8_t TOTAL_GATES = 9;

// Sentinel accepted by the gate-sensitivity command (protocol 2.2.7) meaning
// "every gate at once".
static constexpr uint16_t ALL_GATES = 0xFFFF;

class LD2410BComponent : public Component, public uart::UARTDevice {
 public:
  void setup() override;
  void loop() override;
  void dump_config() override;
  float get_setup_priority() const override { return setup_priority::DATA; }

  // ── Calibration setters ──
  void set_radar_x(float v) { cal_.radar_x = v; }
  void set_radar_y(float v) { cal_.radar_y = v; }
  void set_radar_z(float v) { cal_.radar_z = v; }
  void set_yaw(float v) { cal_.yaw = v; }
  void set_pitch(float v) { cal_.pitch = v; }
  void set_roll(float v) { cal_.roll = v; }
  void set_distance_min(float v) { cal_.distance_min = v; }
  void set_distance_max(float v) { cal_.distance_max = v; }
  /// 边界过滤是否门控 presence：true 时超出 distance_min/max 的目标不计入存在检测（默认 true）
  void set_boundary_gates_presence(bool v) { boundary_gates_presence_ = v; }

  // Seed value only. setup() asks the radar what its resolution actually is
  // (protocol 2.2.17) and the answer overwrites this, so a wrong seed corrects
  // itself a second after boot rather than mis-scaling max_distance forever.
  void set_distance_resolution(float v) { distance_resolution_ = v; }
  float get_distance_resolution() const { return distance_resolution_; }

  // ── Sensor setters ──
  void set_presence_sensor(binary_sensor::BinarySensor *s) { presence_sensor_ = s; }
  void set_target_state_sensor(sensor::Sensor *s) { target_state_sensor_ = s; }

  void set_moving_distance_sensor(sensor::Sensor *s) { moving_distance_sensor_ = s; }
  void set_moving_energy_sensor(sensor::Sensor *s) { moving_energy_sensor_ = s; }
  void set_stationary_distance_sensor(sensor::Sensor *s) { stationary_distance_sensor_ = s; }
  void set_stationary_energy_sensor(sensor::Sensor *s) { stationary_energy_sensor_ = s; }
  void set_detection_distance_sensor(sensor::Sensor *s) { detection_distance_sensor_ = s; }
  void set_max_distance_sensor(sensor::Sensor *s) { max_distance_sensor_ = s; }
  void set_light_sensor(sensor::Sensor *s) { light_sensor_ = s; }
  void set_out_pin_sensor(binary_sensor::BinarySensor *s) { out_pin_sensor_ = s; }

  void set_room_x_sensor(sensor::Sensor *s) { room_x_sensor_ = s; }
  void set_room_y_sensor(sensor::Sensor *s) { room_y_sensor_ = s; }
  void set_room_z_sensor(sensor::Sensor *s) { room_z_sensor_ = s; }
  void set_in_boundary_sensor(binary_sensor::BinarySensor *s) { in_boundary_sensor_ = s; }

  void set_gate_move_sensor(uint8_t gate, sensor::Sensor *s) { gate_move_sensors_[gate] = s; }
  void set_gate_still_sensor(uint8_t gate, sensor::Sensor *s) { gate_still_sensors_[gate] = s; }

  // ── Configuration read-back entities ──
  // These publish what the radar answered, not what was asked for, so a
  // rejected write is visible rather than silently assumed to have taken.
  void set_firmware_version_sensor(text_sensor::TextSensor *s) { firmware_version_sensor_ = s; }
  void set_gate_sensitivity_sensor(text_sensor::TextSensor *s) { gate_sensitivity_sensor_ = s; }
  void set_noise_floor_status_sensor(text_sensor::TextSensor *s) { noise_floor_status_sensor_ = s; }
  void set_max_moving_gate_sensor(sensor::Sensor *s) { max_moving_gate_sensor_ = s; }
  void set_max_still_gate_sensor(sensor::Sensor *s) { max_still_gate_sensor_ = s; }
  void set_unmanned_duration_sensor(sensor::Sensor *s) { unmanned_duration_sensor_ = s; }
  void set_distance_resolution_sensor(sensor::Sensor *s) { distance_resolution_sensor_ = s; }

  // ── Configuration commands (protocol 2.2) ──
  void factory_reset();
  void restart_module();
  void query_firmware_version();
  void query_parameters();
  void query_distance_resolution();
  void query_light_control();
  void query_noise_floor_status();

  /// 2.2.3 — max moving gate, max still gate and the unmanned duration travel
  /// in one command, so each setter re-sends all three from the cached values.
  void set_max_moving_gate(uint8_t gate);
  void set_max_still_gate(uint8_t gate);
  void set_unmanned_duration(uint16_t seconds);
  uint8_t get_max_moving_gate() const { return max_moving_gate_; }
  uint8_t get_max_still_gate() const { return max_still_gate_; }
  uint16_t get_unmanned_duration() const { return unmanned_duration_; }

  /// 2.2.7 — pass ALL_GATES to set every gate to the same pair.
  void set_gate_sensitivity(uint16_t gate, uint8_t move_sensitivity, uint8_t still_sensitivity);
  /// The value every gate shares, or NAN when they differ — a uniform control
  /// must not claim a single number for a radar configured per gate.
  float get_uniform_move_sensitivity() const;
  float get_uniform_still_sensitivity() const;

  /// 2.2.16 — takes effect only after the module restarts, which is why this
  /// does not touch distance_resolution_: the scale in use is still the old one.
  void request_distance_resolution(uint8_t index);

  /// 2.2.18 — mode, threshold and OUT level travel in one command, as above.
  void set_light_control_mode(uint8_t mode);
  void set_light_threshold(uint8_t threshold);
  void set_out_pin_level(uint8_t level);
  uint8_t get_light_control_mode() const { return light_control_mode_; }
  uint8_t get_light_threshold() const { return light_threshold_; }
  uint8_t get_out_pin_level() const { return out_pin_level_; }

  /// 2.2.20 — everyone must leave the detection area; the radar waits 10 s
  /// before it starts measuring the noise floor.
  void start_noise_floor_calibration(uint16_t seconds);

  void inject_mock_data(const std::string &data);

 protected:
  void readline_(int readch);
  void handle_periodic_data_();
  void handle_ack_data_();
  void write_command_frame_(uint8_t command, const uint8_t *command_value, uint8_t command_value_len);
  void enqueue_command_(uint8_t command, const uint8_t *command_value, uint8_t command_value_len);
  void service_command_queue_(uint32_t now);
  void send_max_gate_command_();
  void send_light_control_command_();
  void publish_gate_sensitivity_summary_();

  uint32_t mock_active_until_{0};
  uint8_t buffer_pos_{0};
  uint8_t buffer_data_[MAX_LINE_LENGTH];

  CalibrationParams cal_;

  binary_sensor::BinarySensor *presence_sensor_ = nullptr;

  // UART 静默看门狗：记录最后一次收到串口字节的时刻。

  uint32_t last_rx_ms_{0};

  void check_uart_stale_(uint32_t now);

  sensor::Sensor *target_state_sensor_ = nullptr;

  sensor::Sensor *moving_distance_sensor_ = nullptr;
  sensor::Sensor *moving_energy_sensor_ = nullptr;
  sensor::Sensor *stationary_distance_sensor_ = nullptr;
  sensor::Sensor *stationary_energy_sensor_ = nullptr;
  sensor::Sensor *detection_distance_sensor_ = nullptr;
  sensor::Sensor *max_distance_sensor_ = nullptr;
  sensor::Sensor *light_sensor_ = nullptr;
  binary_sensor::BinarySensor *out_pin_sensor_ = nullptr;

  float distance_resolution_{0.75f};
  bool boundary_gates_presence_{true};

  sensor::Sensor *room_x_sensor_ = nullptr;
  sensor::Sensor *room_y_sensor_ = nullptr;
  sensor::Sensor *room_z_sensor_ = nullptr;
  binary_sensor::BinarySensor *in_boundary_sensor_ = nullptr;

  std::array<sensor::Sensor *, TOTAL_GATES> gate_move_sensors_{};
  std::array<sensor::Sensor *, TOTAL_GATES> gate_still_sensors_{};

  text_sensor::TextSensor *firmware_version_sensor_ = nullptr;
  text_sensor::TextSensor *gate_sensitivity_sensor_ = nullptr;
  text_sensor::TextSensor *noise_floor_status_sensor_ = nullptr;
  sensor::Sensor *max_moving_gate_sensor_ = nullptr;
  sensor::Sensor *max_still_gate_sensor_ = nullptr;
  sensor::Sensor *unmanned_duration_sensor_ = nullptr;
  sensor::Sensor *distance_resolution_sensor_ = nullptr;

  // Cached configuration, seeded by the queries setup() issues and refreshed by
  // every later read. A setter that only carries one of several fields in a
  // command needs the others from somewhere, and guessing a factory default
  // would quietly undo whatever the user had configured.
  uint8_t max_moving_gate_{TOTAL_GATES - 1};
  uint8_t max_still_gate_{TOTAL_GATES - 1};
  uint16_t unmanned_duration_{5};
  uint8_t light_control_mode_{0};
  uint8_t light_threshold_{0x80};
  uint8_t out_pin_level_{0};
  std::array<uint8_t, TOTAL_GATES> move_sensitivity_{};
  std::array<uint8_t, TOTAL_GATES> still_sensitivity_{};
  bool sensitivity_known_{false};

  // A config session stops the data stream, so the UART watchdog has to know
  // one is running or it reports the radar as gone every time a button is
  // pressed.
  struct PendingCommand {
    uint8_t command;
    std::vector<uint8_t> value;
  };
  enum class CommandPhase : uint8_t { IDLE, CONFIG_OPEN, COMMAND_SENT };

  std::vector<PendingCommand> command_queue_;
  CommandPhase command_phase_{CommandPhase::IDLE};
  uint32_t command_next_ms_{0};
  uint32_t config_session_until_{0};
};

}  // namespace ld2410b
}  // namespace esphome
