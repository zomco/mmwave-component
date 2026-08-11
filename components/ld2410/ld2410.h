#pragma once

#include "esphome/core/component.h"
#include "esphome/core/log.h"
#include "esphome/components/uart/uart.h"
#include "esphome/components/sensor/sensor.h"
#include "esphome/components/binary_sensor/binary_sensor.h"
#include "ld2410_transform.h"

#include <vector>
#include <array>
#include <cstdint>

namespace esphome {
namespace ld2410 {

static constexpr uint8_t MAX_LINE_LENGTH = 50;
static constexpr uint8_t TOTAL_GATES = 9;

class LD2410Component : public Component, public uart::UARTDevice {
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
  void set_distance_resolution(float v) { distance_resolution_ = v; }

  // ── Sensor setters ──
  void set_presence_sensor(binary_sensor::BinarySensor *s) { presence_sensor_ = s; }
  void set_target_state_sensor(sensor::Sensor *s) { target_state_sensor_ = s; }

  void set_moving_distance_sensor(sensor::Sensor *s) { moving_distance_sensor_ = s; }
  void set_moving_energy_sensor(sensor::Sensor *s) { moving_energy_sensor_ = s; }
  void set_stationary_distance_sensor(sensor::Sensor *s) { stationary_distance_sensor_ = s; }
  void set_stationary_energy_sensor(sensor::Sensor *s) { stationary_energy_sensor_ = s; }
  void set_detection_distance_sensor(sensor::Sensor *s) { detection_distance_sensor_ = s; }
  void set_max_distance_sensor(sensor::Sensor *s) { max_distance_sensor_ = s; }

  void set_room_x_sensor(sensor::Sensor *s) { room_x_sensor_ = s; }
  void set_room_y_sensor(sensor::Sensor *s) { room_y_sensor_ = s; }
  void set_room_z_sensor(sensor::Sensor *s) { room_z_sensor_ = s; }
  void set_in_boundary_sensor(binary_sensor::BinarySensor *s) { in_boundary_sensor_ = s; }

  void set_gate_move_sensor(uint8_t gate, sensor::Sensor *s) { gate_move_sensors_[gate] = s; }
  void set_gate_still_sensor(uint8_t gate, sensor::Sensor *s) { gate_still_sensors_[gate] = s; }

  void inject_mock_data(const std::string &data);

 protected:
  void readline_(int readch);
  void handle_periodic_data_();
  bool handle_ack_data_();
  void send_command_(uint8_t command_str, const uint8_t *command_value, uint8_t command_value_len);

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

  float distance_resolution_{0.75f};

  sensor::Sensor *room_x_sensor_ = nullptr;
  sensor::Sensor *room_y_sensor_ = nullptr;
  sensor::Sensor *room_z_sensor_ = nullptr;
  binary_sensor::BinarySensor *in_boundary_sensor_ = nullptr;

  std::array<sensor::Sensor *, TOTAL_GATES> gate_move_sensors_{};
  std::array<sensor::Sensor *, TOTAL_GATES> gate_still_sensors_{};
};

}  // namespace ld2410
}  // namespace esphome
