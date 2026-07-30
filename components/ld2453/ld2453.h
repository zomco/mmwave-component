#pragma once

#include "esphome/core/component.h"
#include "esphome/core/log.h"
#include "esphome/components/uart/uart.h"
#include "esphome/components/sensor/sensor.h"
#include "esphome/components/binary_sensor/binary_sensor.h"
#include "ld2453_transform.h"

#include <vector>
#include <cstdint>

namespace esphome {
namespace ld2453 {

struct TargetSensors {
  sensor::Sensor              *x             = nullptr;
  sensor::Sensor              *y             = nullptr;
  sensor::Sensor              *speed         = nullptr;
  sensor::Sensor              *resolution    = nullptr;
  sensor::Sensor              *room_x        = nullptr;
  sensor::Sensor              *room_y        = nullptr;
  sensor::Sensor              *room_z        = nullptr;
  binary_sensor::BinarySensor *in_boundary   = nullptr;
};

class LD2453Component : public Component, public uart::UARTDevice {
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

  void set_target_x_sensor(uint8_t idx, sensor::Sensor *s)            { if (idx < 3) targets_[idx].x = s; }
  void set_target_y_sensor(uint8_t idx, sensor::Sensor *s)            { if (idx < 3) targets_[idx].y = s; }
  void set_target_speed_sensor(uint8_t idx, sensor::Sensor *s)        { if (idx < 3) targets_[idx].speed = s; }
  void set_target_resolution_sensor(uint8_t idx, sensor::Sensor *s)   { if (idx < 3) targets_[idx].resolution = s; }
  void set_target_room_x_sensor(uint8_t idx, sensor::Sensor *s)       { if (idx < 3) targets_[idx].room_x = s; }
  void set_target_room_y_sensor(uint8_t idx, sensor::Sensor *s)       { if (idx < 3) targets_[idx].room_y = s; }
  void set_target_room_z_sensor(uint8_t idx, sensor::Sensor *s)       { if (idx < 3) targets_[idx].room_z = s; }
  void set_target_in_boundary_sensor(uint8_t idx, binary_sensor::BinarySensor *s) { if (idx < 3) targets_[idx].in_boundary = s; }

  void inject_mock_data(const std::string &data);

 protected:
  void process_byte_(uint8_t byte);
  void process_packet_();
  int16_t decode_value_(uint8_t low, uint8_t high);

  uint32_t mock_active_until_{0};
  std::vector<uint8_t> rx_buffer_;
  uint32_t last_rx_ms_{0};

  CalibrationParams cal_;
  
  binary_sensor::BinarySensor *presence_sensor_ = nullptr;
  TargetSensors targets_[3];
};

} // namespace ld2453
} // namespace esphome
