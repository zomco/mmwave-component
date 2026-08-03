#pragma once

#include "esphome/core/component.h"
#include "esphome/components/uart/uart.h"
#include "esphome/core/automation.h"
#include "esphome/core/helpers.h"
#include <span>
#ifdef USE_TEXT_SENSOR
#include "esphome/components/text_sensor/text_sensor.h"
#endif
#ifdef USE_SELECT
#include "esphome/components/select/select.h"
#endif
#ifdef USE_NUMBER
#include "esphome/components/number/number.h"
#endif
#ifdef USE_BUTTON
#include "esphome/components/button/button.h"
#endif

#include "esphome/components/sensor/sensor.h"
#include "esphome/components/binary_sensor/binary_sensor.h"
#include <cmath>

namespace esphome::ld2420 {

static constexpr uint8_t CALIBRATE_SAMPLES = 64;
// Energy frame is 45 bytes; +1 for null terminator, +4 so that a frame footer always lands
// inside the buffer during footer-based resynchronization after losing sync.
static constexpr uint8_t MAX_LINE_LENGTH = 50;
static constexpr uint8_t TOTAL_GATES = 16;

enum OpMode : uint8_t {
  OP_NORMAL_MODE = 1,
  OP_CALIBRATE_MODE = 2,
  OP_SIMPLE_MODE = 3,
};

class LD2420Listener {
 public:
  virtual void on_presence(bool presence){};
  virtual void on_distance(uint16_t distance){};
  virtual void on_energy(uint16_t *sensor_energy, size_t size){};
  virtual void on_fw_version(std::string &fw){};
};

class LD2420Component final : public Component, public uart::UARTDevice {
 public:
  struct CmdFrameT {
    uint32_t header{0};
    uint32_t footer{0};
    uint16_t length{0};
    uint16_t command{0};
    uint16_t data_length{0};
    uint8_t data[18];
  };

  struct RegConfigT {
    uint32_t move_thresh[TOTAL_GATES];
    uint32_t still_thresh[TOTAL_GATES];
    uint16_t min_gate{0};
    uint16_t max_gate{0};
    uint16_t timeout{0};
  };

  void setup() override;
  void dump_config() override;
  void loop() override;
#ifdef USE_SELECT
  void set_operating_mode_select(select::Select *selector) { this->operating_selector_ = selector; };
#endif
#ifdef USE_NUMBER
  void set_gate_timeout_number(number::Number *number) { this->gate_timeout_number_ = number; };
  void set_gate_select_number(number::Number *number) { this->gate_select_number_ = number; };
  void set_min_gate_distance_number(number::Number *number) { this->min_gate_distance_number_ = number; };
  void set_max_gate_distance_number(number::Number *number) { this->max_gate_distance_number_ = number; };
  void set_gate_move_sensitivity_factor_number(number::Number *number) {
    this->gate_move_sensitivity_factor_number_ = number;
  };
  void set_gate_still_sensitivity_factor_number(number::Number *number) {
    this->gate_still_sensitivity_factor_number_ = number;
  };
  void set_gate_still_threshold_numbers(int gate, number::Number *n) { this->gate_still_threshold_numbers_[gate] = n; };
  void set_gate_move_threshold_numbers(int gate, number::Number *n) { this->gate_move_threshold_numbers_[gate] = n; };
  bool is_gate_select() { return gate_select_number_ != nullptr; };
  uint8_t get_gate_select_value() { return static_cast<uint8_t>(this->gate_select_number_->state); };
  float get_min_gate_distance_value() { return min_gate_distance_number_->state; };
  float get_max_gate_distance_value() { return max_gate_distance_number_->state; };
  void publish_gate_move_threshold(uint8_t gate) {
    // With gate_select we only use 1 number pointer, thus we hard code [0]
    this->gate_move_threshold_numbers_[0]->publish_state(this->new_config.move_thresh[gate]);
  };
  void publish_gate_still_threshold(uint8_t gate) {
    this->gate_still_threshold_numbers_[0]->publish_state(this->new_config.still_thresh[gate]);
  };
  void init_gate_config_numbers();
  void refresh_gate_config_numbers();
#endif
#ifdef USE_BUTTON
  void set_apply_config_button(button::Button *button) { this->apply_config_button_ = button; };
  void set_revert_config_button(button::Button *button) { this->revert_config_button_ = button; };
  void set_restart_module_button(button::Button *button) { this->restart_module_button_ = button; };
  void set_factory_reset_button(button::Button *button) { this->factory_reset_button_ = button; };
#endif
  void register_listener(LD2420Listener *listener) { this->listeners_.push_back(listener); }

  void send_module_restart();
  void restart_module_action();
  void apply_config_action();
  void factory_reset_action();
  void revert_config_action();
  float get_setup_priority() const override;
  int send_cmd_from_array(CmdFrameT cmd_frame);
  void report_gate_data();
  void handle_cmd_error(uint8_t error);
  void set_operating_mode(const char *state);
  void auto_calibrate_sensitivity();
  void update_radar_data(uint16_t const *gate_energy, uint8_t sample_number);
  uint8_t set_config_mode(bool enable);
  void set_min_max_distances_timeout(uint32_t max_gate_distance, uint32_t min_gate_distance, uint32_t timeout);
  void set_gate_threshold(uint8_t gate);
  void set_reg_value(uint16_t reg, uint16_t value);
  void set_system_mode(uint16_t mode);
  void ld2420_restart();

  float gate_move_sensitivity_factor{0.5};
  float gate_still_sensitivity_factor{0.5};
  int32_t last_periodic_millis{0};
  int32_t report_periodic_millis{0};
  int32_t monitor_periodic_millis{0};
  int32_t last_normal_periodic_millis{0};
  uint16_t radar_data[TOTAL_GATES][CALIBRATE_SAMPLES];
  uint16_t gate_avg[TOTAL_GATES];
  uint16_t gate_peak[TOTAL_GATES];
  uint16_t total_sample_number_counter{0};
  uint8_t current_operating_mode{OP_NORMAL_MODE};
  uint8_t sample_number_counter{0};
  bool output_energy_state{false};
  RegConfigT current_config;
  RegConfigT new_config;
#ifdef USE_SELECT
  select::Select *operating_selector_{nullptr};
#endif
#ifdef USE_BUTTON
  button::Button *apply_config_button_{nullptr};
  button::Button *revert_config_button_{nullptr};
  button::Button *restart_module_button_{nullptr};
  button::Button *factory_reset_button_{nullptr};
#endif

  // Custom 3D coordinates and entities
  void set_radar_x(float x) { this->radar_x_ = x; }
  void set_radar_y(float y) { this->radar_y_ = y; }
  void set_radar_z(float z) { this->radar_z_ = z; }
  void set_yaw(float yaw) { this->yaw_ = yaw; }
  void set_pitch(float pitch) { this->pitch_ = pitch; }
  void set_roll(float roll) { this->roll_ = roll; }
  void set_distance_min(float d) { this->distance_min_ = d; }
  void set_distance_max(float d) { this->distance_max_ = d; }

  void set_presence_sensor(binary_sensor::BinarySensor *s) { this->presence_sensor_ = s; }
  void set_distance_sensor(sensor::Sensor *s) { this->distance_sensor_ = s; }
  void set_room_x_sensor(sensor::Sensor *s) { this->room_x_sensor_ = s; }
  void set_room_y_sensor(sensor::Sensor *s) { this->room_y_sensor_ = s; }
  void set_room_z_sensor(sensor::Sensor *s) { this->room_z_sensor_ = s; }
  void set_in_boundary_sensor(binary_sensor::BinarySensor *s) { this->in_boundary_sensor_ = s; }

  struct Transform1D {
    float x;
    float y;
    float z;
    bool in_boundary;
  };

  Transform1D transform_1d(float distance) {
    Transform1D result = {0, 0, 0, true};
    if (distance <= 0) {
      result.in_boundary = false;
      return result;
    }

    if ((distance_min_ > 0 && distance < distance_min_) ||
        (distance_max_ > 0 && distance > distance_max_)) {
      result.in_boundary = false;
    }

    // Since LD2420 is a 1D radar, it assumes target is directly in front along its local Y axis.
    // Convert degrees to radians
    float yaw_rad = yaw_ * M_PI / 180.0f;
    float pitch_rad = pitch_ * M_PI / 180.0f;
    float roll_rad = roll_ * M_PI / 180.0f;

    // Apply pitch
    float p_y = distance * cos(pitch_rad);
    float p_z = -distance * sin(pitch_rad);

    // Apply roll (to p_x and p_z)
    float p_x = p_z * sin(roll_rad);
    p_z = p_z * cos(roll_rad);

    // Apply yaw
    float final_x = p_x * cos(yaw_rad) - p_y * sin(yaw_rad);
    float final_y = p_x * sin(yaw_rad) + p_y * cos(yaw_rad);
    float final_z = p_z;

    result.x = final_x + radar_x_;
    result.y = final_y + radar_y_;
    result.z = final_z + radar_z_;
    return result;
  }

 protected:
  struct CmdReplyT {
    uint32_t data[4];
    uint16_t error;
    uint8_t command;
    uint8_t status;
    uint8_t length;
    volatile bool ack;
  };

  void get_firmware_version_();
  int get_gate_threshold_(uint8_t gate);
  void get_reg_value_(uint16_t reg);
  int get_min_max_distances_timeout_();
  uint16_t get_mode_() { return this->system_mode_; };
  void set_mode_(uint16_t mode) { this->system_mode_ = mode; };
  bool get_presence_() { return this->presence_; };
  void set_presence_(bool presence) { this->presence_ = presence; };
  uint16_t get_distance_() { return this->distance_; };
  void set_distance_(uint16_t distance) { this->distance_ = distance; };
  void handle_simple_mode_(const uint8_t *inbuf, int len);
  void handle_energy_mode_(uint8_t *buffer, int len);
  void handle_ack_data_(uint8_t *buffer, int len);
  void readline_(int rx_data, uint8_t *buffer, int len);
  void read_batch_(std::span<uint8_t, MAX_LINE_LENGTH> buffer);
  void set_calibration_(bool state) { this->calibration_ = state; };
  bool get_calibration_() { return this->calibration_; };

#ifdef USE_NUMBER
  number::Number *gate_timeout_number_{nullptr};
  number::Number *gate_select_number_{nullptr};
  number::Number *min_gate_distance_number_{nullptr};
  number::Number *max_gate_distance_number_{nullptr};
  number::Number *gate_move_sensitivity_factor_number_{nullptr};
  number::Number *gate_still_sensitivity_factor_number_{nullptr};
  std::vector<number::Number *> gate_still_threshold_numbers_ = std::vector<number::Number *>(16);
  std::vector<number::Number *> gate_move_threshold_numbers_ = std::vector<number::Number *>(16);
#endif

  uint16_t distance_{0};
  uint16_t system_mode_;
  uint16_t gate_energy_[TOTAL_GATES];
  uint8_t buffer_pos_{0};  // where to resume processing/populating buffer
  uint8_t buffer_data_[MAX_LINE_LENGTH];
  char firmware_ver_[8]{"v0.0.0"};
  bool cmd_active_{false};
  bool presence_{false};
  bool calibration_{false};
  CmdReplyT cmd_reply_;
  std::vector<LD2420Listener *> listeners_{};

  // Custom 3D attributes
  float radar_x_{0.0};
  float radar_y_{0.0};
  float radar_z_{0.0};
  float yaw_{0.0};
  float pitch_{0.0};
  float roll_{0.0};
  float distance_min_{0.0};
  float distance_max_{0.0};

  binary_sensor::BinarySensor *presence_sensor_{nullptr};
  sensor::Sensor *distance_sensor_{nullptr};
  sensor::Sensor *room_x_sensor_{nullptr};
  sensor::Sensor *room_y_sensor_{nullptr};
  sensor::Sensor *room_z_sensor_{nullptr};
  binary_sensor::BinarySensor *in_boundary_sensor_{nullptr};
  
  uint32_t last_presence_ms_{0};
  uint32_t last_update_ms_{0};
};

}  // namespace esphome::ld2420
