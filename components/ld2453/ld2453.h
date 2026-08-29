#pragma once

#include "esphome/core/component.h"
#include "esphome/core/log.h"
#include "esphome/components/uart/uart.h"
#include "esphome/components/sensor/sensor.h"
#include "esphome/components/binary_sensor/binary_sensor.h"
#include "esphome/components/text_sensor/text_sensor.h"
#include "ld2453_transform.h"

#include <vector>
#include <cstdint>
#include <cmath>

namespace esphome {
namespace ld2453 {

struct TargetSensors {
  sensor::Sensor *x = nullptr;
  sensor::Sensor *y = nullptr;
  sensor::Sensor *speed = nullptr;
  sensor::Sensor *resolution = nullptr;
  sensor::Sensor *room_x = nullptr;
  sensor::Sensor *room_y = nullptr;
  sensor::Sensor *room_z = nullptr;
  binary_sensor::BinarySensor *in_boundary = nullptr;
};

class LD2453Component : public Component, public uart::UARTDevice {
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

  /// 追加一个多边形顶点（房间坐标系，cm）
  void add_polygon_point(float x, float y) { cal_.polygon.push_back(Vec2{x, y}); }
  /// 清空多边形（运行时可通过 text/button 实体调用以禁用边界过滤）
  void clear_polygon() { cal_.polygon.clear(); }
  /// 边界过滤是否门控 presence：true 时界外目标不计入存在检测（默认 true）
  void set_boundary_gates_presence(bool v) { boundary_gates_presence_ = v; }
  /// 目标消失后 presence 保持多久才置 false（迟滞窗口，ms）
  void set_presence_timeout(uint32_t ms) { presence_timeout_ = ms; }

  // ── Sensor setters ──
  void set_presence_sensor(binary_sensor::BinarySensor *s) { presence_sensor_ = s; }
  /// Set the optional 10 Hz atomic target-frame text sensor.
  void set_target_frame_sensor(text_sensor::TextSensor *s) { target_frame_sensor_ = s; }

  void set_target_x_sensor(uint8_t idx, sensor::Sensor *s) {
    if (idx < 3)
      targets_[idx].x = s;
  }
  void set_target_y_sensor(uint8_t idx, sensor::Sensor *s) {
    if (idx < 3)
      targets_[idx].y = s;
  }
  void set_target_speed_sensor(uint8_t idx, sensor::Sensor *s) {
    if (idx < 3)
      targets_[idx].speed = s;
  }
  void set_target_resolution_sensor(uint8_t idx, sensor::Sensor *s) {
    if (idx < 3)
      targets_[idx].resolution = s;
  }
  void set_target_room_x_sensor(uint8_t idx, sensor::Sensor *s) {
    if (idx < 3)
      targets_[idx].room_x = s;
  }
  void set_target_room_y_sensor(uint8_t idx, sensor::Sensor *s) {
    if (idx < 3)
      targets_[idx].room_y = s;
  }
  void set_target_room_z_sensor(uint8_t idx, sensor::Sensor *s) {
    if (idx < 3)
      targets_[idx].room_z = s;
  }
  void set_target_in_boundary_sensor(uint8_t idx, binary_sensor::BinarySensor *s) {
    if (idx < 3)
      targets_[idx].in_boundary = s;
  }

  void inject_mock_data(const std::string &data);

  // ── Configuration Commands ──
  void set_tracking_mode(uint8_t mode);  // 1 = Single, 2 = Multi
  void query_parameters();
  void factory_reset();
  void restart_module();

 protected:
  void process_byte_(uint8_t byte);
  void process_packet_();
  void publish_target_frame_();
  /// 仅在数值变化时发布（ESPHome 不会对数值 sensor 去重）
  void publish_if_changed_(sensor::Sensor *s, float value);
  /// 把一个目标槽位置空：坐标发布 NAN，in_boundary 置 false。
  void publish_empty_target_(uint8_t idx);
  /// 帧级看门狗：长时间解析不出数据帧时清空所有目标。
  void check_stale_();
  /// presence 的唯一发布点，带迟滞（见 .cpp 中的说明）。
  void update_presence_();
  void process_ack_();
  void send_command_(uint16_t command, const uint8_t *command_value, uint8_t command_value_len);
  void handle_ack_data_(uint16_t command, uint16_t status, const uint8_t *data, uint8_t data_len);
  int16_t decode_value_(uint8_t low, uint8_t high);

  uint32_t mock_active_until_{0};
  std::vector<uint8_t> rx_buffer_;
  uint32_t last_rx_ms_{0};
  /// 最后一次**成功解析出数据帧**的时刻。与 last_rx_ms_ 不同，它不会被
  /// 那些没能通过帧头/帧尾校验的字节刷新，所以失步时它会停住。
  uint32_t last_frame_ms_{0};
  uint32_t last_publish_ms_{0};
  uint32_t last_frame_publish_ms_{0};
  uint32_t frame_id_{0};
  bool config_mode_{false};
  bool boundary_gates_presence_{true};
  /// 见 update_presence_：模组会在相邻帧之间丢掉边缘目标，没有迟滞的话
  /// presence 会以数赫兹的频率抖动。
  uint32_t presence_timeout_{1500};
  uint32_t last_presence_ms_{0};

  CalibrationParams cal_;

  binary_sensor::BinarySensor *presence_sensor_ = nullptr;
  text_sensor::TextSensor *target_frame_sensor_ = nullptr;
  TargetSensors targets_[3];
};

}  // namespace ld2453
}  // namespace esphome
