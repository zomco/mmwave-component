#pragma once

#include <stdint.h>

struct R60ProbeStats {
  uint32_t uart_bytes = 0;
  uint32_t valid_frames = 0;
  uint32_t target_observations = 0;
  uint32_t parse_errors = 0;
  uint32_t last_valid_frame_ms = 0;

  void note_uart_byte() { uart_bytes++; }

  void note_valid_frame(uint32_t now_ms) {
    valid_frames++;
    last_valid_frame_ms = now_ms;
  }

  void note_parse_error() { parse_errors++; }

  void note_target() { target_observations++; }

  bool link_waiting() const { return valid_frames == 0; }

  bool link_stale(uint32_t now_ms, uint32_t stale_after_ms) const {
    return valid_frames > 0 && now_ms - last_valid_frame_ms >= stale_after_ms;
  }
};
