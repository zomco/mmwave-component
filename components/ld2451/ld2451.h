#pragma once

#include "esphome/core/component.h"
#include "esphome/core/log.h"
#include "esphome/components/uart/uart.h"
#include "esphome/components/sensor/sensor.h"
#include "esphome/components/binary_sensor/binary_sensor.h"
#include "esphome/components/text_sensor/text_sensor.h"
#include "ld2451_transform.h"

#include <vector>
#include <cstdint>
#include <cmath>

namespace esphome {
namespace ld2451 {

struct TargetSensors {
  sensor::Sensor *distance = nullptr;
  sensor::Sensor *angle = nullptr;
  sensor::Sensor *speed = nullptr;
  sensor::Sensor *snr = nullptr;
  sensor::Sensor *x = nullptr;
  sensor::Sensor *y = nullptr;
  sensor::Sensor *room_x = nullptr;
  sensor::Sensor *room_y = nullptr;
  sensor::Sensor *room_z = nullptr;
  binary_sensor::BinarySensor *in_boundary = nullptr;
};

class LD2451Component : public Component, public uart::UARTDevice {
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

  // ── Sensor setters ──
  void set_presence_sensor(binary_sensor::BinarySensor *s) { presence_sensor_ = s; }
  void set_alarm_sensor(binary_sensor::BinarySensor *s) { alarm_sensor_ = s; }
  void set_target_count_sensor(sensor::Sensor *s) { target_count_sensor_ = s; }
  /// Set the optional 10 Hz atomic target-frame text sensor.
  void set_target_frame_sensor(text_sensor::TextSensor *s) { target_frame_sensor_ = s; }

  // ── Configuration read-back entities ──
  // These publish what the radar answered to a query, not what was written to
  // it, so a rejected command is visible instead of silently assumed.
  /// Firmware version reported by protocol 1.2.7.
  void set_firmware_version_sensor(text_sensor::TextSensor *s) { firmware_version_sensor_ = s; }
  /// Direction filter as a word ("away" / "approaching" / "both").
  void set_direction_filter_sensor(text_sensor::TextSensor *s) { direction_filter_sensor_ = s; }
  /// Furthest range the radar itself reports targets from, in metres.
  void set_max_detection_distance_sensor(sensor::Sensor *s) { max_detection_distance_sensor_ = s; }
  /// Slowest radial speed the radar will report, in km/h.
  void set_min_speed_sensor(sensor::Sensor *s) { min_speed_sensor_ = s; }
  /// How long the radar keeps reporting after the last target, in seconds.
  void set_no_target_delay_sensor(sensor::Sensor *s) { no_target_delay_sensor_ = s; }
  /// Consecutive detections required before the radar raises an alarm.
  void set_trigger_count_sensor(sensor::Sensor *s) { trigger_count_sensor_ = s; }
  /// Signal-to-noise threshold level; higher means less sensitive.
  void set_snr_threshold_sensor(sensor::Sensor *s) { snr_threshold_sensor_ = s; }

  void set_target_distance_sensor(uint8_t idx, sensor::Sensor *s) {
    if (idx < 3)
      targets_[idx].distance = s;
  }
  void set_target_angle_sensor(uint8_t idx, sensor::Sensor *s) {
    if (idx < 3)
      targets_[idx].angle = s;
  }
  void set_target_speed_sensor(uint8_t idx, sensor::Sensor *s) {
    if (idx < 3)
      targets_[idx].speed = s;
  }
  void set_target_snr_sensor(uint8_t idx, sensor::Sensor *s) {
    if (idx < 3)
      targets_[idx].snr = s;
  }
  void set_target_x_sensor(uint8_t idx, sensor::Sensor *s) {
    if (idx < 3)
      targets_[idx].x = s;
  }
  void set_target_y_sensor(uint8_t idx, sensor::Sensor *s) {
    if (idx < 3)
      targets_[idx].y = s;
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

  // ── Configuration Commands ──
  /// Protocol 1.2.9. Values apply after the module restarts.
  void factory_reset();
  /// Protocol 1.2.10.
  void restart_module();
  /// Protocol 1.2.7. The answer lands on the firmware_version text sensor.
  void query_firmware_version();

  /// Protocol 1.2.4 — max distance, direction, min speed and no-target delay.
  void query_detection_params();
  /// Protocol 1.2.3. All four travel in one command, so each setter re-sends
  /// the other three from the values the last query returned.
  void set_max_detection_distance(uint8_t metres);
  /// 0 = away only, 1 = approaching only, 2 = both.
  void set_direction_filter(uint8_t direction);
  void set_min_speed(uint8_t kmh);
  void set_no_target_delay(uint8_t seconds);
  uint8_t get_max_detection_distance() const { return max_detection_distance_; }
  uint8_t get_direction_filter() const { return direction_filter_; }
  uint8_t get_min_speed() const { return min_speed_; }
  uint8_t get_no_target_delay() const { return no_target_delay_; }

  /// Protocol 1.2.6 — accumulated trigger count and SNR threshold level.
  void query_sensitivity_params();
  /// Protocol 1.2.5, same paired-write rule as the detection parameters.
  void set_trigger_count(uint8_t count);
  /// 0 keeps the radar's own default (4); 3–8 otherwise, higher being less
  /// sensitive.
  void set_snr_threshold(uint8_t level);
  uint8_t get_trigger_count() const { return trigger_count_; }
  uint8_t get_snr_threshold() const { return snr_threshold_; }

  void inject_mock_data(std::string data);

 protected:
  void process_byte_(uint8_t byte);
  void process_packet_();
  void publish_target_frame_(uint8_t target_count);
  /// 仅在数值变化时发布（ESPHome 不会对数值 sensor 去重）
  void publish_if_changed_(sensor::Sensor *s, float value);
  void process_ack_();
  void write_command_frame_(uint16_t command, const uint8_t *command_value, uint8_t command_value_len);
  void enqueue_command_(uint16_t command, const uint8_t *command_value, uint8_t command_value_len);
  void service_command_queue_(uint32_t now);
  void send_detection_params_();
  void send_sensitivity_params_();
  void handle_ack_data_(uint16_t command, uint16_t status, const uint8_t *data, uint8_t data_len);

  std::vector<uint8_t> rx_buffer_;
  uint32_t last_rx_ms_{0};

  // 诊断计数器。曾经是 loop() 里的函数内 static，导致同一块 ESP 上的多个
  // LD2451 实例共用同一份计数，日志互相污染。
  uint32_t diag_bytes_{0};
  uint32_t diag_frames_{0};
  uint32_t last_diag_ms_{0};
  uint32_t last_publish_ms_{0};
  uint32_t last_frame_publish_ms_{0};
  uint32_t frame_id_{0};
  uint32_t mock_active_until_{0};
  bool boundary_gates_presence_{true};
  bool config_mode_{false};

  CalibrationParams cal_;

  binary_sensor::BinarySensor *presence_sensor_ = nullptr;
  binary_sensor::BinarySensor *alarm_sensor_ = nullptr;
  sensor::Sensor *target_count_sensor_ = nullptr;
  text_sensor::TextSensor *target_frame_sensor_ = nullptr;

  text_sensor::TextSensor *firmware_version_sensor_ = nullptr;
  text_sensor::TextSensor *direction_filter_sensor_ = nullptr;
  sensor::Sensor *max_detection_distance_sensor_ = nullptr;
  sensor::Sensor *min_speed_sensor_ = nullptr;
  sensor::Sensor *no_target_delay_sensor_ = nullptr;
  sensor::Sensor *trigger_count_sensor_ = nullptr;
  sensor::Sensor *snr_threshold_sensor_ = nullptr;

  // Cached radar-side configuration, seeded by the queries setup() issues and
  // refreshed by every later read. A setter that carries only one of four
  // fields needs the others from somewhere, and a guessed factory default
  // would quietly undo whatever the user had configured.
  uint8_t max_detection_distance_{100};
  uint8_t direction_filter_{2};
  uint8_t min_speed_{5};
  uint8_t no_target_delay_{1};
  uint8_t trigger_count_{1};
  uint8_t snr_threshold_{0};

  // Protocol 1.4.1 wraps every command in an enable-config / end-config pair.
  // Queueing them lets one session carry a batch — the three reads setup()
  // issues, say — and keeps loop() free of blocking waits. The previous nested
  // set_timeout pair shared one timer name, so a second command issued while
  // the first was in flight cancelled it.
  struct PendingCommand {
    uint16_t command;
    std::vector<uint8_t> value;
  };
  enum class CommandPhase : uint8_t { IDLE, CONFIG_OPEN, COMMAND_SENT };

  std::vector<PendingCommand> command_queue_;
  CommandPhase command_phase_{CommandPhase::IDLE};
  uint32_t command_next_ms_{0};
  uint32_t config_session_until_{0};

  TargetSensors targets_[3];
};

}  // namespace ld2451
}  // namespace esphome
