#pragma once

#include "esphome/core/component.h"
#include "esphome/core/log.h"
#include "esphome/components/uart/uart.h"
#include "esphome/components/sensor/sensor.h"
#include "esphome/components/binary_sensor/binary_sensor.h"
#include "esphome/components/text_sensor/text_sensor.h"
#include "ld2450a_transform.h"

#include <vector>
#include <cstdint>

namespace esphome {
namespace ld2450a {

class LD2450AComponent : public Component, public uart::UARTDevice {
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

  // ── Command methods ──
  void set_gesture_distance_threshold(uint16_t val_cm);
  void set_gesture_speed_threshold(uint16_t val_cms);
  void set_gesture_angle_threshold(uint16_t val_deg);
  void reboot();
  void factory_reset();
  void inject_mock_data(std::string data);

  // ── Sensor setters ──
  void set_presence_sensor(binary_sensor::BinarySensor *s)    { presence_sensor_ = s; }
  void set_distance_sensor(sensor::Sensor *s)                 { distance_sensor_ = s; }
  void set_gesture_text_sensor(text_sensor::TextSensor *s)    { gesture_text_sensor_ = s; }
  void set_gesture_type_sensor(sensor::Sensor *s)             { gesture_type_sensor_ = s; }
  void set_gesture_distance_sensor(sensor::Sensor *s)         { gesture_distance_sensor_ = s; }
  void set_gesture_speed_sensor(sensor::Sensor *s)            { gesture_speed_sensor_ = s; }
  void set_gesture_angle_sensor(sensor::Sensor *s)            { gesture_angle_sensor_ = s; }
  void set_room_x_sensor(sensor::Sensor *s)                   { room_x_ = s; }
  void set_room_y_sensor(sensor::Sensor *s)                   { room_y_ = s; }
  void set_room_z_sensor(sensor::Sensor *s)                   { room_z_ = s; }
  void set_in_boundary_sensor(binary_sensor::BinarySensor *s) { in_boundary_sensor_ = s; }

 protected:
  void process_byte_(uint8_t byte);
  void process_packet_();
  void send_command_(uint8_t cmd, uint16_t val);
  void publish_position_(float range_cm);

  std::vector<uint8_t> rx_buffer_;
  uint32_t last_rx_ms_{0};
  uint32_t last_publish_ms_{0};
  uint32_t mock_active_until_{0};

  CalibrationParams cal_;

  // Sensors
  binary_sensor::BinarySensor *presence_sensor_         = nullptr;
  sensor::Sensor              *distance_sensor_         = nullptr;
  text_sensor::TextSensor     *gesture_text_sensor_     = nullptr;
  sensor::Sensor              *gesture_type_sensor_     = nullptr;
  sensor::Sensor              *gesture_distance_sensor_ = nullptr;
  sensor::Sensor              *gesture_speed_sensor_    = nullptr;
  sensor::Sensor              *gesture_angle_sensor_    = nullptr;
  sensor::Sensor              *room_x_                  = nullptr;
  sensor::Sensor              *room_y_                  = nullptr;
  sensor::Sensor              *room_z_                  = nullptr;
  binary_sensor::BinarySensor *in_boundary_sensor_      = nullptr;
};

} // namespace ld2450a
} // namespace esphome
