#pragma once

#include "esphome/core/component.h"
#include "esphome/core/log.h"
#include "esphome/components/uart/uart.h"
#include "esphome/components/sensor/sensor.h"
#include "esphome/components/binary_sensor/binary_sensor.h"
#include "esphome/components/button/button.h"
#include "esphome/components/switch/switch.h"
#include "esphome/components/text_sensor/text_sensor.h"
#include "ld2454_transform.h"

#include <vector>
#include <cstdint>
#include <cmath>

namespace esphome {
namespace ld2454 {

// ─── 常量 ─────────────────────────────────────────────────────────────────────

static constexpr uint8_t MAX_TARGETS     = 3;
static constexpr uint8_t TARGET_BYTES    = 8;    // 每个目标 8 字节
static constexpr uint8_t DATA_BODY_LEN   = 24;   // 3 目标 × 8 字节
static constexpr uint8_t MAX_CMD_DATA    = 64;   // 命令 ACK 最大数据长度

// ── 数据帧标记 ────────────────────────────────────────────────────────────────
static constexpr uint8_t DATA_HDR1  = 0xAA;
static constexpr uint8_t DATA_HDR2  = 0xFF;
static constexpr uint8_t DATA_HDR3  = 0x03;
static constexpr uint8_t DATA_HDR4  = 0x00;
static constexpr uint8_t DATA_TAIL1 = 0x55;
static constexpr uint8_t DATA_TAIL2 = 0xCC;

// ── 命令帧标记 ────────────────────────────────────────────────────────────────
static constexpr uint8_t CMD_HDR1  = 0xFD;
static constexpr uint8_t CMD_HDR2  = 0xFC;
static constexpr uint8_t CMD_HDR3  = 0xFB;
static constexpr uint8_t CMD_HDR4  = 0xFA;
static constexpr uint8_t CMD_TAIL1 = 0x04;
static constexpr uint8_t CMD_TAIL2 = 0x03;
static constexpr uint8_t CMD_TAIL3 = 0x02;
static constexpr uint8_t CMD_TAIL4 = 0x01;

// ── 命令字 ────────────────────────────────────────────────────────────────────
static constexpr uint16_t CMD_ENABLE_CONFIG   = 0x00FF;
static constexpr uint16_t CMD_END_CONFIG      = 0x00FE;
static constexpr uint16_t CMD_SINGLE_TARGET   = 0x0080;
static constexpr uint16_t CMD_MULTI_TARGET    = 0x0090;
static constexpr uint16_t CMD_FW_VERSION      = 0x00A0;
static constexpr uint16_t CMD_SET_BAUD_RATE   = 0x00A1;
static constexpr uint16_t CMD_FACTORY_RESET   = 0x00A2;
static constexpr uint16_t CMD_RESTART         = 0x00A3;

// ─── 帧解析状态机 ─────────────────────────────────────────────────────────────

enum class ParseState : uint8_t {
  IDLE,
  // 数据帧路径: AA FF 03 00 [24B] 55 CC
  D_HDR2,       // 等待 0xFF
  D_HDR3,       // 等待 0x03
  D_HDR4,       // 等待 0x00
  D_BODY,       // 收集 24 字节目标数据
  D_TAIL1,      // 等待 0x55
  D_TAIL2,      // 等待 0xCC
  // 命令 ACK 路径: FD FC FB FA [len_L][len_H][data...] 04 03 02 01
  C_HDR2,       // 等待 0xFC
  C_HDR3,       // 等待 0xFB
  C_HDR4,       // 等待 0xFA
  C_LEN_L,      // 长度低字节
  C_LEN_H,      // 长度高字节
  C_DATA,       // 收集 N 字节数据
  C_TAIL1,      // 等待 0x04
  C_TAIL2,      // 等待 0x03
  C_TAIL3,      // 等待 0x02
  C_TAIL4,      // 等待 0x01
};

// ─── 每目标传感器指针 ─────────────────────────────────────────────────────────

struct TargetSensors {
  sensor::Sensor              *x{nullptr};
  sensor::Sensor              *y{nullptr};
  sensor::Sensor              *speed{nullptr};
  sensor::Sensor              *resolution{nullptr};
  sensor::Sensor              *distance{nullptr};
  sensor::Sensor              *angle{nullptr};
  sensor::Sensor              *room_x{nullptr};
  sensor::Sensor              *room_y{nullptr};
  binary_sensor::BinarySensor *active{nullptr};
  binary_sensor::BinarySensor *in_boundary{nullptr};
};

class LD2454Component;

class LD2454Button : public button::Button {
 public:
  enum ButtonType { RESTART, FACTORY_RESET };
  void set_parent(LD2454Component *parent) { parent_ = parent; }
  void set_button_type(ButtonType type) { type_ = type; }
  void press_action() override;
 protected:
  LD2454Component *parent_;
  ButtonType type_;
};

class LD2454Switch : public switch_::Switch {
 public:
  enum SwitchType { MULTI_TARGET };
  void set_parent(LD2454Component *parent) { parent_ = parent; }
  void set_switch_type(SwitchType type) { type_ = type; }
  void write_state(bool state) override;
 protected:
  LD2454Component *parent_;
  SwitchType type_;
};

// ─── 组件类 ───────────────────────────────────────────────────────────────────

class LD2454Component : public Component, public uart::UARTDevice {
 public:
  // ── 生命周期 ────────────────────────────────────────────────────────────
  void setup()       override;
  void loop()        override;
  void dump_config() override;
  float get_setup_priority() const override { return setup_priority::DATA; }

  // ── 校准参数 setters ───────────────────────────────────────────────────
  /// 设置雷达在房间中的 X 坐标（cm）
  void set_radar_x(float v)      { cal_.radar_x = v; }
  /// 设置雷达在房间中的 Y 坐标（cm）
  void set_radar_y(float v)      { cal_.radar_y = v; }
  /// 设置雷达安装高度（cm）
  void set_radar_z(float v)      { cal_.radar_z = v; }
  /// 设置偏航角（°），触发旋转矩阵重算
  void set_yaw(float v)          { cal_.yaw   = v; recompute_rotation_(); }
  /// 设置俯仰角（°），触发旋转矩阵重算
  void set_pitch(float v)        { cal_.pitch = v; recompute_rotation_(); }
  /// 设置横滚角（°），触发旋转矩阵重算
  void set_roll(float v)         { cal_.roll  = v; recompute_rotation_(); }

  /// 追加一个多边形顶点（房间坐标系，cm）
  void add_polygon_point(float x, float y) {
    cal_.polygon.push_back(Vec2{x, y});
  }
  /// 清空多边形
  void clear_polygon() { cal_.polygon.clear(); }

  // ── 全局传感器 setters ─────────────────────────────────────────────────
  /// 设置存在检测传感器（任一目标存在即为 true）
  void set_presence_sensor(binary_sensor::BinarySensor *s) { presence_sensor_ = s; }
  /// Set the optional atomic target-frame text sensor.
  void set_target_frame_sensor(text_sensor::TextSensor *s) { target_frame_sensor_ = s; }
  void set_presence_timeout(uint32_t t) { presence_timeout_ = t * 1000; }

  // ── 目标 1 传感器 setters ──────────────────────────────────────────────
  void set_target_1_x_sensor(sensor::Sensor *s)                    { targets_[0].x = s; }
  void set_target_1_y_sensor(sensor::Sensor *s)                    { targets_[0].y = s; }
  void set_target_1_speed_sensor(sensor::Sensor *s)                { targets_[0].speed = s; }
  void set_target_1_resolution_sensor(sensor::Sensor *s)           { targets_[0].resolution = s; }
  void set_target_1_distance_sensor(sensor::Sensor *s)             { targets_[0].distance = s; }
  void set_target_1_angle_sensor(sensor::Sensor *s)                { targets_[0].angle = s; }
  void set_target_1_room_x_sensor(sensor::Sensor *s)               { targets_[0].room_x = s; }
  void set_target_1_room_y_sensor(sensor::Sensor *s)               { targets_[0].room_y = s; }
  void set_target_1_active_sensor(binary_sensor::BinarySensor *s)  { targets_[0].active = s; }
  void set_target_1_in_boundary_sensor(binary_sensor::BinarySensor *s) { targets_[0].in_boundary = s; }

  // ── 目标 2 传感器 setters ──────────────────────────────────────────────
  void set_target_2_x_sensor(sensor::Sensor *s)                    { targets_[1].x = s; }
  void set_target_2_y_sensor(sensor::Sensor *s)                    { targets_[1].y = s; }
  void set_target_2_speed_sensor(sensor::Sensor *s)                { targets_[1].speed = s; }
  void set_target_2_resolution_sensor(sensor::Sensor *s)           { targets_[1].resolution = s; }
  void set_target_2_distance_sensor(sensor::Sensor *s)             { targets_[1].distance = s; }
  void set_target_2_angle_sensor(sensor::Sensor *s)                { targets_[1].angle = s; }
  void set_target_2_room_x_sensor(sensor::Sensor *s)               { targets_[1].room_x = s; }
  void set_target_2_room_y_sensor(sensor::Sensor *s)               { targets_[1].room_y = s; }
  void set_target_2_active_sensor(binary_sensor::BinarySensor *s)  { targets_[1].active = s; }
  void set_target_2_in_boundary_sensor(binary_sensor::BinarySensor *s) { targets_[1].in_boundary = s; }

  // ── 目标 3 传感器 setters ──────────────────────────────────────────────
  void set_target_3_x_sensor(sensor::Sensor *s)                    { targets_[2].x = s; }
  void set_target_3_y_sensor(sensor::Sensor *s)                    { targets_[2].y = s; }
  void set_target_3_speed_sensor(sensor::Sensor *s)                { targets_[2].speed = s; }
  void set_target_3_resolution_sensor(sensor::Sensor *s)           { targets_[2].resolution = s; }
  void set_target_3_distance_sensor(sensor::Sensor *s)             { targets_[2].distance = s; }
  void set_target_3_angle_sensor(sensor::Sensor *s)                { targets_[2].angle = s; }
  void set_target_3_room_x_sensor(sensor::Sensor *s)               { targets_[2].room_x = s; }
  void set_target_3_room_y_sensor(sensor::Sensor *s)               { targets_[2].room_y = s; }
  void set_target_3_active_sensor(binary_sensor::BinarySensor *s)  { targets_[2].active = s; }
  void set_target_3_in_boundary_sensor(binary_sensor::BinarySensor *s) { targets_[2].in_boundary = s; }

  // ── 命令发送（公开，供 button/lambda 直接调用）────────────────────────
  /// 发送命令帧（自动包裹 enable/end config）
  void send_config_cmd(uint16_t cmd_word, const uint8_t *data, uint16_t len);
  /// 设置多目标追踪模式
  void set_multi_target_mode(bool enable) {
    if (enable) send_config_cmd(CMD_MULTI_TARGET, nullptr, 0);
    else send_config_cmd(CMD_SINGLE_TARGET, nullptr, 0);
  }
  /// 重启模块
  void restart_module()          { send_config_cmd(CMD_RESTART, nullptr, 0); }
  /// 恢复出厂设置
  void factory_reset()           { send_config_cmd(CMD_FACTORY_RESET, nullptr, 0); }
  /// 查询雷达状态（LD2454 仅支持固件版本查询）
  void query_state() {
    send_config_cmd(CMD_FW_VERSION, nullptr, 0);
  }
  /// 注入测试数据
  void inject_mock_data(const std::string &hex_str);

  // 控制实体指针
  switch_::Switch *multi_target_switch_{nullptr};

 protected:
  void process_byte_(uint8_t byte);
  void dispatch_data_frame_();
  void publish_target_frame_();
  void dispatch_cmd_frame_();
  void recompute_rotation_();
  void publish_target_(uint8_t idx, int16_t x_mm, int16_t y_mm,
                       int16_t speed_cm_s, uint16_t resolution_mm, bool active);
  void send_raw_cmd_(uint16_t cmd_word, const uint8_t *data, uint16_t len);

  // ── 帧解析状态 ─────────────────────────────────────────────────────────
  ParseState parse_state_{ParseState::IDLE};

  // 数据帧缓冲
  uint8_t  data_buf_[DATA_BODY_LEN]{};
  uint8_t  data_idx_{0};

  // 命令帧缓冲
  uint16_t cmd_len_{0};
  uint16_t cmd_idx_{0};
  uint8_t  cmd_buf_[MAX_CMD_DATA]{};

  // ── 校准 & 变换 ────────────────────────────────────────────────────────
  CalibrationParams cal_;
  Mat3 rotation_;  // 预计算的旋转矩阵

  // ── 传感器指针 ─────────────────────────────────────────────────────────
  TargetSensors targets_[MAX_TARGETS];
  binary_sensor::BinarySensor *presence_sensor_{nullptr};
  text_sensor::TextSensor *target_frame_sensor_{nullptr};
  uint32_t frame_id_{0};
  uint32_t presence_timeout_{5000};
  uint32_t last_presence_ms_{0};

  // ── 测试模拟数据状态 ───────────────────────────────────────────────────
  uint32_t mock_active_until_{0};
};

} // namespace ld2454
} // namespace esphome
