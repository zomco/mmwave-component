#pragma once

#include "esphome/core/component.h"
#include "esphome/core/log.h"
#include "esphome/components/uart/uart.h"
#include "esphome/components/sensor/sensor.h"
#include "esphome/components/binary_sensor/binary_sensor.h"
#include "ld2410b_transform.h"

#include <vector>
#include <cstdint>

namespace esphome {
namespace ld2410b {

class LD2410BComponent : public Component, public uart::UARTDevice {
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
  void set_target_state_sensor(sensor::Sensor *s) { target_state_sensor_ = s; }
  
  void set_moving_distance_sensor(sensor::Sensor *s) { moving_distance_sensor_ = s; }
  void set_moving_energy_sensor(sensor::Sensor *s) { moving_energy_sensor_ = s; }
  void set_stationary_distance_sensor(sensor::Sensor *s) { stationary_distance_sensor_ = s; }
  void set_stationary_energy_sensor(sensor::Sensor *s) { stationary_energy_sensor_ = s; }
  void set_detection_distance_sensor(sensor::Sensor *s) { detection_distance_sensor_ = s; }
  
  void set_room_x_sensor(sensor::Sensor *s) { room_x_sensor_ = s; }
  void set_room_y_sensor(sensor::Sensor *s) { room_y_sensor_ = s; }
  void set_room_z_sensor(sensor::Sensor *s) { room_z_sensor_ = s; }
  void set_in_boundary_sensor(binary_sensor::BinarySensor *s) { in_boundary_sensor_ = s; }

 protected:
  void process_byte_(uint8_t byte);
  void process_packet_();

  std::vector<uint8_t> rx_buffer_;
  uint32_t last_rx_ms_{0};

  CalibrationParams cal_;
  
  binary_sensor::BinarySensor *presence_sensor_ = nullptr;
  sensor::Sensor *target_state_sensor_ = nullptr;
  
  sensor::Sensor *moving_distance_sensor_ = nullptr;
  sensor::Sensor *moving_energy_sensor_ = nullptr;
  sensor::Sensor *stationary_distance_sensor_ = nullptr;
  sensor::Sensor *stationary_energy_sensor_ = nullptr;
  sensor::Sensor *detection_distance_sensor_ = nullptr;
  
  sensor::Sensor *room_x_sensor_ = nullptr;
  sensor::Sensor *room_y_sensor_ = nullptr;
  sensor::Sensor *room_z_sensor_ = nullptr;
  binary_sensor::BinarySensor *in_boundary_sensor_ = nullptr;
};

} // namespace ld2410b
} // namespace esphome
