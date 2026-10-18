#include "g0_meter.h"

#include "g0_meter_line.h"
#include "r60abd1.h"

#include "esphome/core/log.h"

#include "esp_heap_caps.h"
#include "esp_system.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

namespace esphome {
namespace g0_meter {

static_assert(sizeof(StackType_t) == 1, "ESP-IDF RISC-V high-water mark is not bytes");
static const char *const TAG = "g0_meter";

void G0MeterComponent::loop() {
  const int64_t started = esp_timer_get_time();
  const uint32_t now = millis();
  if (now - last_log_ms_ < 5000) {
    const int64_t skipped = esp_timer_get_time() - started;
    if (skipped > max_loop_us_) max_loop_us_ = skipped;
    return;
  }
  last_log_ms_ = now;
  G0Meter meter;
  meter.uptime_ms = now;
  meter.free_heap = esp_get_free_heap_size();
  meter.min_free_heap = esp_get_minimum_free_heap_size();
  meter.largest_free_block = heap_caps_get_largest_free_block(MALLOC_CAP_8BIT);
  meter.stack_high_water_bytes = uxTaskGetStackHighWaterMark(nullptr);
  meter.max_loop_us = static_cast<uint32_t>(max_loop_us_ > 0xffffffffLL ? 0xffffffffLL : max_loop_us_);
  meter.radar_link = "unknown";
  if (radar_) {
    const R60ProbeStats stats = radar_->probe_stats();
    meter.radar_frames = stats.valid_frames;
    meter.radar_errors = stats.parse_errors;
    meter.radar_targets = stats.target_observations;
    if (stats.valid_frames > 0) {
      meter.radar_frame_known = true;
      meter.last_radar_frame_ms = stats.last_valid_frame_ms;
      meter.radar_link = stats.link_stale(now, 2000) ? "stale" : "healthy";
    } else {
      meter.radar_link = "waiting";
    }
  }
  char line[320];
  if (g0_format_meter_line(line, sizeof(line), meter)) ESP_LOGI(TAG, "%s", line);
  const int64_t elapsed = esp_timer_get_time() - started;
  if (elapsed > max_loop_us_) max_loop_us_ = elapsed;
}

}  // namespace g0_meter
}  // namespace esphome
