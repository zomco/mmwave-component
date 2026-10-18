#pragma once

#include "esphome/core/component.h"

namespace esphome {
namespace r60abd1 {
class R60ABD1Component;
}

namespace g0_meter {

class G0MeterComponent : public Component {
 public:
  void loop() override;
  void set_radar(r60abd1::R60ABD1Component *radar) { radar_ = radar; }
  float get_setup_priority() const override { return setup_priority::LATE; }

 private:
  r60abd1::R60ABD1Component *radar_{nullptr};
  uint32_t last_log_ms_{0};
  int64_t max_loop_us_{0};
};

}  // namespace g0_meter
}  // namespace esphome
