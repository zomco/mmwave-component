#pragma once

#include "esphome/core/component.h"
#include "esphome/core/log.h"
#include "esphome/components/uart/uart.h"
#include "esphome/components/sensor/sensor.h"
#include "esphome/components/binary_sensor/binary_sensor.h"
#include "ld2420_transform.h"

#include <cstdint>
#include <vector>

namespace esphome {
namespace ld2420 {

static constexpr uint32_t ENERGY_FRAME_FOOTER = 0xF5F6F7F8;
static constexpr uint32_t ENERGY_FRAME_HEADER = 0xF1F2F3F4;
static constexpr uint8_t MAX_FRAME_LENGTH = 64;

class LD2420Component : public Component, public uart::UARTDevice {
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
  void set_presence_sensor(binary_sensor::BinarySensor *s)    { presence_sensor_ = s; }
  void set_distance_sensor(sensor::Sensor *s)                 { distance_ = s; }
  void set_room_x_sensor(sensor::Sensor *s)                   { room_x_ = s; }
  void set_room_y_sensor(sensor::Sensor *s)                   { room_y_ = s; }
  void set_room_z_sensor(sensor::Sensor *s)                   { room_z_ = s; }
  void set_in_boundary_sensor(binary_sensor::BinarySensor *s) { in_boundary_sensor_ = s; }

 protected:
  void readline_(int rx_data);
  void handle_energy_mode_();
  void publish_position_(float range_cm);

  uint8_t buffer_[MAX_FRAME_LENGTH];
  uint8_t buffer_pos_{0};
  uint32_t last_rx_ms_{0};

  CalibrationParams cal_;

  // Sensors
  binary_sensor::BinarySensor *presence_sensor_    = nullptr;
  sensor::Sensor              *distance_           = nullptr;
  sensor::Sensor              *room_x_             = nullptr;
  sensor::Sensor              *room_y_             = nullptr;
  sensor::Sensor              *room_z_             = nullptr;
  binary_sensor::BinarySensor *in_boundary_sensor_ = nullptr;
};

} // namespace ld2420
} // namespace esphome
