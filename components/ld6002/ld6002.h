#pragma once

#include "esphome/core/component.h"
#include "esphome/core/log.h"
#include "esphome/components/uart/uart.h"
#include "esphome/components/sensor/sensor.h"
#include "esphome/components/binary_sensor/binary_sensor.h"
#include "ld6002_transform.h"

#include <vector>
#include <cstdint>

namespace esphome {
namespace ld6002 {

enum class DataState : uint8_t {
  IDLE,
  ID_H,
  ID_L,
  LEN_H,
  LEN_L,
  TYPE_H,
  TYPE_L,
  HEAD_CKSUM,
  DATA,
  DATA_CKSUM
};

static constexpr uint8_t DATA_SOF = 0x01;

class LD6002Component : public Component, public uart::UARTDevice {
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
  void set_presence_sensor(binary_sensor::BinarySensor *s)         { presence_sensor_ = s; }
  void set_distance_sensor(sensor::Sensor *s)                      { distance_ = s; }
  void set_respiration_rate_sensor(sensor::Sensor *s)              { respiration_rate_ = s; }
  void set_heart_rate_sensor(sensor::Sensor *s)                    { heart_rate_ = s; }
  void set_room_x_sensor(sensor::Sensor *s)                        { room_x_ = s; }
  void set_room_y_sensor(sensor::Sensor *s)                        { room_y_ = s; }
  void set_room_z_sensor(sensor::Sensor *s)                        { room_z_ = s; }
  void set_in_boundary_sensor(binary_sensor::BinarySensor *s)      { in_boundary_sensor_ = s; }

 protected:
  void process_byte_(uint8_t byte);
  void process_packet_();
  void publish_position_(float x_m, float y_m, float z_m);

  DataState data_state_{DataState::IDLE};
  
  uint16_t frame_id_{0};
  uint16_t frame_len_{0};
  uint16_t frame_type_{0};
  uint8_t  frame_head_cksum_{0};
  
  std::vector<uint8_t> payload_;
  uint16_t payload_idx_{0};

  uint32_t last_rx_ms_{0};

  CalibrationParams cal_;

  float last_distance_cm_{0};

  // ── Frame type statistics (debug) ──
  uint32_t frame_count_0F09_{0};   // Presence
  uint32_t frame_count_0A04_{0};   // Personnel Position (3D)
  uint32_t frame_count_0A13_{0};   // Phase
  uint32_t frame_count_0A14_{0};   // Respiration Rate
  uint32_t frame_count_0A15_{0};   // Heart Rate
  uint32_t frame_count_0A16_{0};   // Distance
  uint32_t frame_count_0A17_{0};   // Tracked Position (3D)
  uint32_t frame_count_other_{0};  // Unknown types
  uint32_t last_stats_ms_{0};      // Last stats dump time

  // Sensors
  binary_sensor::BinarySensor *presence_sensor_    = nullptr;
  sensor::Sensor              *distance_           = nullptr;
  sensor::Sensor              *respiration_rate_   = nullptr;
  sensor::Sensor              *heart_rate_         = nullptr;
  sensor::Sensor              *room_x_             = nullptr;
  sensor::Sensor              *room_y_             = nullptr;
  sensor::Sensor              *room_z_             = nullptr;
  binary_sensor::BinarySensor *in_boundary_sensor_ = nullptr;
};

} // namespace ld6002
} // namespace esphome
