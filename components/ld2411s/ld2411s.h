#pragma once

#include "esphome/core/component.h"
#include "esphome/components/uart/uart.h"
#include "esphome/components/sensor/sensor.h"
#include "esphome/components/binary_sensor/binary_sensor.h"

namespace esphome {
namespace ld2411s {

enum class DataState {
  IDLE,
  READ_DATA,
};

class LD2411SComponent : public Component, public uart::UARTDevice {
 public:
  void setup() override;
  void loop() override;
  void dump_config() override;

  void set_distance_sensor(sensor::Sensor *sensor) { this->distance_sensor_ = sensor; }
  void set_presence_sensor(binary_sensor::BinarySensor *sensor) { this->presence_sensor_ = sensor; }
  void set_moving_target_sensor(binary_sensor::BinarySensor *sensor) { this->moving_target_sensor_ = sensor; }
  void set_micro_target_sensor(binary_sensor::BinarySensor *sensor) { this->micro_target_sensor_ = sensor; }
  void inject_mock_data(std::string data);

 protected:
  void process_packet_();
  
  sensor::Sensor *distance_sensor_{nullptr};
  binary_sensor::BinarySensor *presence_sensor_{nullptr};
  binary_sensor::BinarySensor *moving_target_sensor_{nullptr};
  binary_sensor::BinarySensor *micro_target_sensor_{nullptr};

  std::vector<uint8_t> rx_buffer_;
  DataState data_state_{DataState::IDLE};
  uint32_t last_rx_ms_{0};
  uint32_t last_publish_ms_{0};
  uint32_t mock_active_until_{0};
};

}  // namespace ld2411s
}  // namespace esphome
