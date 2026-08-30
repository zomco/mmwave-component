#pragma once

#include "esphome/core/component.h"
#include "esphome/core/log.h"
#include "esphome/components/uart/uart.h"
#include "esphome/components/sensor/sensor.h"
#include "esphome/components/binary_sensor/binary_sensor.h"
#include "ld2411_transform.h"

#include <cstdint>
#include <string>

namespace esphome {
namespace ld2411 {

// Data frame: AA AA [status:1B] [dist_L:1B] [dist_H:1B] 55 55
enum class DataState : uint8_t {
  IDLE,
  HDR2,    // Received 0xAA, wait for second 0xAA
  STATUS,  // Target status
  DIST_L,  // Distance low byte
  DIST_H,  // Distance high byte
  TAIL1,   // Wait for 0x55
  TAIL2,   // Wait for 0x55
};

static constexpr uint8_t DATA_HDR = 0xAA;
static constexpr uint8_t DATA_TAIL = 0x55;

class LD2411Component : public Component, public uart::UARTDevice {
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
  /// 边界过滤是否门控 presence：true 时界外目标不计入存在检测（默认 true）
  void set_boundary_gates_presence(bool v) { boundary_gates_presence_ = v; }
  void set_distance_min(float v) { cal_.distance_min = v; }
  void set_distance_max(float v) { cal_.distance_max = v; }

  // ── Sensor setters ──
  void set_presence_sensor(binary_sensor::BinarySensor *s) { presence_sensor_ = s; }
  void set_motion_state_sensor(sensor::Sensor *s) { motion_state_ = s; }
  void set_distance_sensor(sensor::Sensor *s) { distance_ = s; }
  void set_room_x_sensor(sensor::Sensor *s) { room_x_ = s; }
  void set_room_y_sensor(sensor::Sensor *s) { room_y_ = s; }
  void set_room_z_sensor(sensor::Sensor *s) { room_z_ = s; }
  void set_in_boundary_sensor(binary_sensor::BinarySensor *s) { in_boundary_sensor_ = s; }

  /// 注入一帧十六进制测试数据，绕过真实串口。
  ///
  /// "0" 或 "reset" 立即结束注入窗口。其余输入按两个字符一字节解析，逐字节喂给
  /// 与真实串口相同的解析路径，因此测试覆盖的是产线代码而不是旁路。
  void inject_mock_data(const std::string &data);

 protected:
  void process_byte_(uint8_t byte);
  void handle_data_frame_();
  bool publish_position_(float range_cm);

  DataState data_state_{DataState::IDLE};
  uint8_t data_status_{0};
  uint8_t data_dist_l_{0};
  uint8_t data_dist_h_{0};

  uint32_t last_rx_ms_{0};
  /// 非零且未到期时，loop() 丢弃真实串口字节（见 inject_mock_data）。
  uint32_t mock_active_until_{0};
  bool boundary_gates_presence_{true};

  CalibrationParams cal_;

  // Sensors
  binary_sensor::BinarySensor *presence_sensor_ = nullptr;
  sensor::Sensor *motion_state_ = nullptr;
  sensor::Sensor *distance_ = nullptr;
  sensor::Sensor *room_x_ = nullptr;
  sensor::Sensor *room_y_ = nullptr;
  sensor::Sensor *room_z_ = nullptr;
  binary_sensor::BinarySensor *in_boundary_sensor_ = nullptr;
};

}  // namespace ld2411
}  // namespace esphome
