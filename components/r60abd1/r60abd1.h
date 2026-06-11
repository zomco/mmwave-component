#pragma once

#include "esphome/core/component.h"
#include "esphome/core/log.h"
#include "esphome/components/uart/uart.h"
#include "esphome/components/sensor/sensor.h"
#include "esphome/components/binary_sensor/binary_sensor.h"
#include "esphome/components/text_sensor/text_sensor.h"
#include "r60abd1_transform.h"

#include <vector>
#include <cstdint>

namespace esphome {
namespace r60abd1 {

// ─── 帧解析状态机 ─────────────────────────────────────────────────────────────

enum class ParseState : uint8_t {
  IDLE,
  HDR2,       // 已收到 0x53，等待 0x59
  CTRL,
  CMD,
  LEN_H,
  LEN_L,
  DATA,
  CHECKSUM,
  TAIL1,      // 等待 0x54
  TAIL2,      // 等待 0x43
};

static constexpr uint8_t FRAME_HDR1  = 0x53;
static constexpr uint8_t FRAME_HDR2  = 0x59;
static constexpr uint8_t FRAME_TAIL1 = 0x54;
static constexpr uint8_t FRAME_TAIL2 = 0x43;
static constexpr size_t  MAX_DATA_LEN = 32;

// ─── 控制字 ──────────────────────────────────────────────────────────────────

static constexpr uint8_t CTRL_HEARTBEAT  = 0x01;
static constexpr uint8_t CTRL_PRODUCT    = 0x02;
static constexpr uint8_t CTRL_WORK_STATE = 0x05;
static constexpr uint8_t CTRL_PRESENCE   = 0x80;
static constexpr uint8_t CTRL_BREATH     = 0x81;
static constexpr uint8_t CTRL_SLEEP      = 0x84;
static constexpr uint8_t CTRL_HEART      = 0x85;

// ─── 组件类 ──────────────────────────────────────────────────────────────────

class R60ABD1Component : public Component, public uart::UARTDevice {
 public:
  // ── 生命周期 ────────────────────────────────────────────────────────────
  void setup()       override;
  void loop()        override;
  void dump_config() override;
  float get_setup_priority() const override { return setup_priority::DATA; }

  // ── 校准参数 setters（由 __init__.py 在 setup 时调用；
  //    也可在运行时通过 number 实体的 set_action 调用）─────────────────────
  void set_radar_x(float v)      { cal_.radar_x      = v; }
  void set_radar_y(float v)      { cal_.radar_y      = v; }
  void set_radar_z(float v)      { cal_.radar_z      = v; }
  void set_yaw(float v)          { cal_.yaw          = v; }
  void set_pitch(float v)        { cal_.pitch        = v; }
  void set_roll(float v)         { cal_.roll         = v; }

  /**
   * 追加一个多边形顶点（房间坐标系，cm）
   * __init__.py 为每个 polygon 条目调用一次此方法，
   * 避免在代码生成阶段传递 std::vector。
   */
  void add_polygon_point(float x, float y) {
    cal_.polygon.push_back(Vec2{x, y});
  }

  /** 清空多边形（可在运行时通过按钮实体调用以禁用边界过滤）*/
  void clear_polygon() { cal_.polygon.clear(); }

  // ── 传感器 setters（由 __init__.py 注册传感器对象）────────────────────
  void set_presence_sensor(binary_sensor::BinarySensor *s)    { presence_sensor_    = s; }
  void set_motion_sensor(sensor::Sensor *s)                   { motion_sensor_      = s; }
  void set_body_movement_sensor(sensor::Sensor *s)            { body_movement_      = s; }
  void set_body_distance_sensor(sensor::Sensor *s)            { body_distance_      = s; }
  void set_raw_x_sensor(sensor::Sensor *s)                    { raw_x_              = s; }
  void set_raw_y_sensor(sensor::Sensor *s)                    { raw_y_              = s; }
  void set_raw_z_sensor(sensor::Sensor *s)                    { raw_z_              = s; }
  void set_room_x_sensor(sensor::Sensor *s)                   { room_x_             = s; }
  void set_room_y_sensor(sensor::Sensor *s)                   { room_y_             = s; }
  void set_room_z_sensor(sensor::Sensor *s)                   { room_z_             = s; }
  void set_in_boundary_sensor(binary_sensor::BinarySensor *s) { in_boundary_sensor_ = s; }
  void set_breath_value_sensor(sensor::Sensor *s)             { breath_value_       = s; }
  void set_breath_state_sensor(text_sensor::TextSensor *s)    { breath_state_       = s; }
  void set_heart_rate_sensor(sensor::Sensor *s)               { heart_rate_         = s; }
  void set_in_bed_sensor(binary_sensor::BinarySensor *s)      { in_bed_sensor_      = s; }
  void set_sleep_state_sensor(text_sensor::TextSensor *s)     { sleep_state_        = s; }
  void set_awake_duration_sensor(sensor::Sensor *s)           { awake_duration_     = s; }
  void set_light_sleep_duration_sensor(sensor::Sensor *s)     { light_sleep_dur_    = s; }
  void set_deep_sleep_duration_sensor(sensor::Sensor *s)      { deep_sleep_dur_     = s; }
  void set_sleep_score_sensor(sensor::Sensor *s)              { sleep_score_        = s; }
  void set_sleep_quality_sensor(text_sensor::TextSensor *s)   { sleep_quality_      = s; }

  // ── 命令发送（公开，供 button/lambda 直接调用）────────────────────────
  void send_cmd(uint8_t ctrl, uint8_t cmd, const uint8_t *data, uint16_t len);
  void enable_presence()   { const uint8_t d = 0x01; send_cmd(CTRL_PRESENCE, 0x00, &d, 1); }
  void enable_breath()     { const uint8_t d = 0x01; send_cmd(CTRL_BREATH,   0x00, &d, 1); }
  void enable_heart_rate() { const uint8_t d = 0x01; send_cmd(CTRL_HEART,    0x00, &d, 1); }
  void enable_sleep()      { const uint8_t d = 0x01; send_cmd(CTRL_SLEEP,    0x00, &d, 1); }
  void reset_module()      { const uint8_t d = 0x0F; send_cmd(CTRL_HEARTBEAT, 0x02, &d, 1); }
  void query_init_state()  { const uint8_t d = 0x0F; send_cmd(CTRL_WORK_STATE, 0x81, &d, 1); }

 protected:
  void process_byte_(uint8_t byte);
  void dispatch_frame_();
  void handle_presence_frame_();
  void handle_breath_frame_();
  void handle_heart_frame_();
  void handle_sleep_frame_();
  void handle_work_state_frame_();
  void publish_position_(int16_t rx, int16_t ry, int16_t rz);

  // 帧解析状态
  ParseState parse_state_{ParseState::IDLE};
  uint8_t    ctrl_{0}, cmd_{0};
  uint16_t   data_len_{0}, data_idx_{0};
  uint8_t    rx_buf_[MAX_DATA_LEN]{};
  uint8_t    checksum_accum_{0};

  bool       initialized_{false};
  uint32_t   last_rx_ms_{0};

  CalibrationParams cal_;

  // 传感器指针（全部可为 nullptr，组件自动跳过未注册的传感器）
  binary_sensor::BinarySensor *presence_sensor_    = nullptr;
  sensor::Sensor               *motion_sensor_     = nullptr;
  sensor::Sensor               *body_movement_     = nullptr;
  sensor::Sensor               *body_distance_     = nullptr;
  sensor::Sensor               *raw_x_             = nullptr;
  sensor::Sensor               *raw_y_             = nullptr;
  sensor::Sensor               *raw_z_             = nullptr;
  sensor::Sensor               *room_x_            = nullptr;
  sensor::Sensor               *room_y_            = nullptr;
  sensor::Sensor               *room_z_      = nullptr;
  binary_sensor::BinarySensor  *in_boundary_sensor_= nullptr;
  sensor::Sensor               *breath_value_      = nullptr;
  text_sensor::TextSensor      *breath_state_      = nullptr;
  sensor::Sensor               *heart_rate_        = nullptr;
  binary_sensor::BinarySensor  *in_bed_sensor_     = nullptr;
  text_sensor::TextSensor      *sleep_state_       = nullptr;
  sensor::Sensor               *awake_duration_    = nullptr;
  sensor::Sensor               *light_sleep_dur_   = nullptr;
  sensor::Sensor               *deep_sleep_dur_    = nullptr;
  sensor::Sensor               *sleep_score_       = nullptr;
  text_sensor::TextSensor      *sleep_quality_     = nullptr;
};

} // namespace r60abd1
} // namespace esphome