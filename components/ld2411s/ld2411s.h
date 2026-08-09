#pragma once

#include "esphome/core/component.h"
#include "esphome/components/uart/uart.h"
#include "esphome/components/sensor/sensor.h"
#include "esphome/components/binary_sensor/binary_sensor.h"
#include "ld2411s_transform.h"

#include <vector>

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

  // ── 安装校准参数 ────────────────────────────────────────────────────────
  /// 设置雷达在房间中的 X 坐标（cm）
  void set_radar_x(float v) { cal_.radar_x = v; }
  /// 设置雷达在房间中的 Y 坐标（cm）
  void set_radar_y(float v) { cal_.radar_y = v; }
  /// 设置雷达安装高度（cm）
  void set_radar_z(float v) { cal_.radar_z = v; }
  /// 设置偏航角（°，俯视顺时针为正）
  void set_yaw(float v) { cal_.yaw = v; }
  /// 设置俯仰角（°，向前倾为正）
  void set_pitch(float v) { cal_.pitch = v; }
  /// 设置横滚角（°，绕雷达正前方轴）
  void set_roll(float v) { cal_.roll = v; }
  /// 最小有效距离（cm），0 = 不过滤
  void set_distance_min(float v) { cal_.distance_min = v; }
  /// 最大有效距离（cm），0 = 不过滤
  void set_distance_max(float v) { cal_.distance_max = v; }
  /// 边界过滤是否门控 presence：true 时界外目标不计入存在检测（默认 true）
  void set_boundary_gates_presence(bool v) { boundary_gates_presence_ = v; }

  // ── 变换后传感器 ────────────────────────────────────────────────────────
  void set_room_x_sensor(sensor::Sensor *s) { this->room_x_ = s; }
  void set_room_y_sensor(sensor::Sensor *s) { this->room_y_ = s; }
  void set_room_z_sensor(sensor::Sensor *s) { this->room_z_ = s; }
  void set_in_boundary_sensor(binary_sensor::BinarySensor *s) { this->in_boundary_sensor_ = s; }

 protected:
  void process_packet_();
  
  sensor::Sensor *distance_sensor_{nullptr};
  binary_sensor::BinarySensor *presence_sensor_{nullptr};
  binary_sensor::BinarySensor *moving_target_sensor_{nullptr};
  binary_sensor::BinarySensor *micro_target_sensor_{nullptr};

  sensor::Sensor *room_x_{nullptr};
  sensor::Sensor *room_y_{nullptr};
  sensor::Sensor *room_z_{nullptr};
  binary_sensor::BinarySensor *in_boundary_sensor_{nullptr};

  CalibrationParams cal_;
  bool boundary_gates_presence_{true};

  std::vector<uint8_t> rx_buffer_;
  DataState data_state_{DataState::IDLE};
  uint32_t last_rx_ms_{0};
  uint32_t last_publish_ms_{0};
  uint32_t mock_active_until_{0};
};

}  // namespace ld2411s
}  // namespace esphome
