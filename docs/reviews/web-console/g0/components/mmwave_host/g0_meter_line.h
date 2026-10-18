#pragma once

#include <stddef.h>
#include <stdint.h>
#include <cstdio>

struct G0Meter {
  uint32_t uptime_ms = 0;
  uint32_t free_heap = 0;
  uint32_t min_free_heap = 0;
  uint32_t largest_free_block = 0;
  uint32_t stack_high_water_bytes = 0;
  uint32_t max_loop_us = 0;
  uint32_t radar_frames = 0;
  uint32_t radar_errors = 0;
  uint32_t radar_targets = 0;
  uint32_t last_radar_frame_ms = 0;
  bool radar_known = false;
  bool radar_frame_known = false;
  const char *radar_link = "unknown";
  const char *reset_reason = "unknown";
  bool usb_exclusive = false;
  int usb_install_err = -1;
};

inline bool g0_format_meter_line(char *out, size_t cap, const G0Meter &meter) {
  char last_ms[16] = "null";
  if (meter.radar_frame_known) std::snprintf(last_ms, sizeof(last_ms), "%lu", static_cast<unsigned long>(meter.last_radar_frame_ms));
  const int n = std::snprintf(
      out, cap,
      "G0METER v=1 uptime_ms=%lu free_heap=%lu min_free_heap=%lu largest_free_block=%lu "
      "stack_high_water_bytes=%lu stack_high_water_unit=bytes stack_type_bytes=1 max_loop_us=%lu "
      "radar_frames=%lu radar_errors=%lu radar_targets=%lu last_radar_frame_ms=%s radar_link=%s",
      static_cast<unsigned long>(meter.uptime_ms), static_cast<unsigned long>(meter.free_heap),
      static_cast<unsigned long>(meter.min_free_heap), static_cast<unsigned long>(meter.largest_free_block),
      static_cast<unsigned long>(meter.stack_high_water_bytes), static_cast<unsigned long>(meter.max_loop_us),
      static_cast<unsigned long>(meter.radar_frames), static_cast<unsigned long>(meter.radar_errors),
      static_cast<unsigned long>(meter.radar_targets), last_ms, meter.radar_link ? meter.radar_link : "unknown");
  return n > 0 && static_cast<size_t>(n) < cap;
}
