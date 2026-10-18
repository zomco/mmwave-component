#pragma once

#include "esphome/core/component.h"
#include "g0_link.h"

#include <stdint.h>

namespace esphome {
namespace r60abd1 {
class R60ABD1Component;
}

namespace mmwave_host {

class MwcpHost : public Component {
 public:
  void setup() override;
  void loop() override;
  void set_radar(r60abd1::R60ABD1Component *radar) { radar_ = radar; }
  float get_setup_priority() const override { return setup_priority::LATE; }

 private:
  void on_frame_(const mwcp::Frame &frame);
  void note_error_(mwcp::Status status);
  G0Meter meter_() const;

  bool usb_exclusive_{false};
  bool usb_shared_{false};
  int usb_install_err_{-1};
  int64_t max_loop_us_{0};
  uint32_t free_heap_{0};
  uint32_t min_heap_{0};
  uint32_t largest_block_{0};
  uint32_t stack_high_water_{0};
  const char *reset_reason_{"unknown"};
  r60abd1::R60ABD1Component *radar_{nullptr};
  G0Link link_{};
};

}  // namespace mmwave_host
}  // namespace esphome
