#pragma once

#include "esphome/core/component.h"
#include "esphome/core/log.h"
#include "esphome/components/uart/uart.h"
#include "esphome/components/sensor/sensor.h"
#include "esphome/components/binary_sensor/binary_sensor.h"
#include "rd03e_transform.h"

#include <cstdint>

namespace esphome {
namespace rd03e {

// ─── 数据帧解析状态机 ─────────────────────────────────────────────────────────
// 数据帧格式: AA AA [status:1B] [dist_L:1B] [dist_H:1B] 55 55

enum class DataState : uint8_t {
  IDLE,
  HDR2,       // 已收到 0xAA，等待第二个 0xAA
  STATUS,     // 目标状态
  DIST_L,     // 距离低字节
  DIST_H,     // 距离高字节
  TAIL1,      // 等待 0x55
  TAIL2,      // 等待 0x55
};

// ─── 命令帧解析状态机 ─────────────────────────────────────────────────────────
// 命令帧格式: FD FC FB FA [len_L:1B] [len_H:1B] [data...] 04 03 02 01

enum class CmdState : uint8_t {
  IDLE,
  HDR2,       // 已收到 0xFD，等待 0xFC
  HDR3,       // 等待 0xFB
  HDR4,       // 等待 0xFA
  LEN_L,      // 帧内数据长度低字节
  LEN_H,      // 帧内数据长度高字节
  DATA,       // 帧内数据
  TAIL1,      // 等待 0x04
  TAIL2,      // 等待 0x03
  TAIL3,      // 等待 0x02
  TAIL4,      // 等待 0x01
};

// ─── 帧常量 ──────────────────────────────────────────────────────────────────

// 数据帧
static constexpr uint8_t DATA_HDR    = 0xAA;
static constexpr uint8_t DATA_TAIL   = 0x55;

// 命令帧
static constexpr uint8_t CMD_HDR1    = 0xFD;
static constexpr uint8_t CMD_HDR2    = 0xFC;
static constexpr uint8_t CMD_HDR3    = 0xFB;
static constexpr uint8_t CMD_HDR4    = 0xFA;
static constexpr uint8_t CMD_TAIL1   = 0x04;
static constexpr uint8_t CMD_TAIL2   = 0x03;
static constexpr uint8_t CMD_TAIL3   = 0x02;
static constexpr uint8_t CMD_TAIL4   = 0x01;
static constexpr size_t  MAX_CMD_DATA_LEN = 64;

// ─── 命令字 ──────────────────────────────────────────────────────────────────

static constexpr uint16_t CMD_FW_VERSION   = 0x0000;
static constexpr uint16_t CMD_ENABLE_CFG   = 0x00FF;
static constexpr uint16_t CMD_END_CFG      = 0x00FE;
static constexpr uint16_t CMD_DIST_CFG     = 0x0067;
static constexpr uint16_t CMD_NOISE_CFG    = 0x0068;
static constexpr uint16_t CMD_CLUTTER_CFG  = 0x0069;
static constexpr uint16_t CMD_FRAME_CFG    = 0x0070;
static constexpr uint16_t CMD_FILTER_CFG   = 0x0071;
static constexpr uint16_t CMD_CALIB_CFG    = 0x0072;
static constexpr uint16_t CMD_READ_PARAMS  = 0x0073;

// ─── 组件类 ──────────────────────────────────────────────────────────────────

class RD03EComponent : public Component, public uart::UARTDevice {
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
  void set_distance_min(float v) { cal_.distance_min = v; }
  void set_distance_max(float v) { cal_.distance_max = v; }

  // ── 传感器 setters（由 __init__.py 注册传感器对象）────────────────────
  void set_presence_sensor(binary_sensor::BinarySensor *s)    { presence_sensor_    = s; }
  void set_motion_state_sensor(sensor::Sensor *s)             { motion_state_       = s; }
  void set_distance_sensor(sensor::Sensor *s)                 { distance_           = s; }
  void set_room_x_sensor(sensor::Sensor *s)                   { room_x_             = s; }
  void set_room_y_sensor(sensor::Sensor *s)                   { room_y_             = s; }
  void set_room_z_sensor(sensor::Sensor *s)                   { room_z_             = s; }
  void set_in_boundary_sensor(binary_sensor::BinarySensor *s) { in_boundary_sensor_ = s; }

  // ── 命令发送（公开，供 button/lambda 直接调用）────────────────────────
  /// 发送命令帧（FD FC FB FA [len] [data] 04 03 02 01）
  void send_cmd(uint16_t cmd_word, const uint8_t *data, uint16_t len);

  /// 发送使能配置命令
  void send_enable_config();

  /// 发送结束配置命令
  void send_end_config();

  /// 设置距离参数（max_motion, min_motion, max_micro, min_micro, vacancy_duration）
  void send_distance_config(uint32_t max_motion, uint32_t min_motion,
                            uint32_t max_micro, uint32_t min_micro,
                            uint32_t vacancy_duration);

  /// 读取固件版本
  void send_read_firmware_version();

  /// 读取所有算法参数
  void send_read_params();

 protected:
  void process_byte_(uint8_t byte);
  void handle_data_frame_();
  void handle_cmd_frame_();
  void publish_position_(float range_cm);

  // 数据帧解析状态
  DataState data_state_{DataState::IDLE};
  uint8_t   data_status_{0};
  uint8_t   data_dist_l_{0};
  uint8_t   data_dist_h_{0};

  // 命令帧解析状态
  CmdState  cmd_state_{CmdState::IDLE};
  uint16_t  cmd_data_len_{0};
  uint16_t  cmd_data_idx_{0};
  uint8_t   cmd_buf_[MAX_CMD_DATA_LEN]{};

  uint32_t  last_rx_ms_{0};

  CalibrationParams cal_;

  // 传感器指针（全部可为 nullptr，组件自动跳过未注册的传感器）
  binary_sensor::BinarySensor *presence_sensor_    = nullptr;
  sensor::Sensor              *motion_state_       = nullptr;
  sensor::Sensor              *distance_           = nullptr;
  sensor::Sensor              *room_x_             = nullptr;
  sensor::Sensor              *room_y_             = nullptr;
  sensor::Sensor              *room_z_             = nullptr;
  binary_sensor::BinarySensor *in_boundary_sensor_ = nullptr;
};

} // namespace rd03e
} // namespace esphome
