#pragma once

#include "esphome/core/component.h"
#include "esphome/core/log.h"
#include "esphome/components/uart/uart.h"
#include "esphome/components/sensor/sensor.h"
#include "esphome/components/binary_sensor/binary_sensor.h"
#include "ld2451_transform.h"

#include <vector>
#include <cstdint>

namespace esphome {
namespace ld2451 {

struct TargetSensors {
  sensor::Sensor              *distance      = nullptr;
  sensor::Sensor              *angle         = nullptr;
  sensor::Sensor              *speed         = nullptr;
  sensor::Sensor              *snr           = nullptr;
  sensor::Sensor              *x             = nullptr;
  sensor::Sensor              *y             = nullptr;
  sensor::Sensor              *room_x        = nullptr;
  sensor::Sensor              *room_y        = nullptr;
  sensor::Sensor              *room_z        = nullptr;
  binary_sensor::BinarySensor *in_boundary   = nullptr;
};

class LD2451Component : public Component, public uart::UARTDevice {
 public:
  void setup() override;
  void loop() override;
  void dump_config() override;
  float get_setup_priority() const override { return setup_priority::DATA; }

  // ── Calibration setters ──
  void set_radar_x(float v)      { cal_.radar_x      = v; }
  void set_radar_y(float v)      { cal_.radar_y      = v; }
  void set_radar_z(float v)      { cal_.radar_z      = v; }
  void set_yaw(float v)          { cal_.yaw          = v; }
  void set_pitch(float v)        { cal_.pitch        = v; }
  void set_roll(float v)         { cal_.roll         = v; }
  void set_distance_min(float v) { cal_.distance_min = v; }
  void set_distance_max(float v) { cal_.distance_max = v; }

  // ── Sensor setters ──
  void set_presence_sensor(binary_sensor::BinarySensor *s) { presence_sensor_ = s; }
  void set_alarm_sensor(binary_sensor::BinarySensor *s) { alarm_sensor_ = s; }
  void set_target_count_sensor(sensor::Sensor *s) { target_count_sensor_ = s; }

  void set_target_distance_sensor(uint8_t idx, sensor::Sensor *s)     { if (idx < 3) targets_[idx].distance = s; }
  void set_target_angle_sensor(uint8_t idx, sensor::Sensor *s)        { if (idx < 3) targets_[idx].angle = s; }
  void set_target_speed_sensor(uint8_t idx, sensor::Sensor *s)        { if (idx < 3) targets_[idx].speed = s; }
  void set_target_snr_sensor(uint8_t idx, sensor::Sensor *s)          { if (idx < 3) targets_[idx].snr = s; }
  void set_target_x_sensor(uint8_t idx, sensor::Sensor *s)            { if (idx < 3) targets_[idx].x = s; }
  void set_target_y_sensor(uint8_t idx, sensor::Sensor *s)            { if (idx < 3) targets_[idx].y = s; }
  void set_target_room_x_sensor(uint8_t idx, sensor::Sensor *s)       { if (idx < 3) targets_[idx].room_x = s; }
  void set_target_room_y_sensor(uint8_t idx, sensor::Sensor *s)       { if (idx < 3) targets_[idx].room_y = s; }
  void set_target_room_z_sensor(uint8_t idx, sensor::Sensor *s)       { if (idx < 3) targets_[idx].room_z = s; }
  void set_target_in_boundary_sensor(uint8_t idx, binary_sensor::BinarySensor *s) { if (idx < 3) targets_[idx].in_boundary = s; }

  // ── Configuration Commands ──
  void factory_reset();
  void restart_module();

 protected:
  void process_byte_(uint8_t byte);
  void process_packet_();
  void process_ack_();
  void send_command_(uint16_t command, const uint8_t *command_value, uint8_t command_value_len);
  void handle_ack_data_(uint16_t command, uint16_t status, const uint8_t *data, uint8_t data_len);

  std::vector<uint8_t> rx_buffer_;
  uint32_t last_rx_ms_{0};
  bool config_mode_{false};

  CalibrationParams cal_;
  
  binary_sensor::BinarySensor *presence_sensor_ = nullptr;
  binary_sensor::BinarySensor *alarm_sensor_ = nullptr;
  sensor::Sensor *target_count_sensor_ = nullptr;
  
  TargetSensors targets_[3];
};

} // namespace ld2451
} // namespace esphome
