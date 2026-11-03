#pragma once

#include "mwcp_service.h"

namespace mwcp_host {

// Kind 1 is the only presence sample. Kind 5 is a position and must not
// create presence knowledge (P-G2-01). Distance, breath, and heart stay
// independent metrics.
inline void apply_observation(RadarView &view, uint8_t kind, bool presence, uint16_t distance_cm, int16_t local_x,
                              int16_t local_y, int16_t local_z, float room_x, float room_y, bool in_boundary,
                              float rate, uint32_t sample_ms) {
  view.seen_frame = true;
  view.last_frame_ms = sample_ms;
  view.frames++;
  if (kind == 1) {
    view.has_presence = true;
    view.presence = presence;
    view.presence_ms = sample_ms;
  }
  if (kind == 4) {
    view.has_distance = true;
    view.distance_cm = distance_cm;
    view.distance_ms = sample_ms;
  }
  if (kind == 6) {
    view.has_breath = true;
    view.breath = rate;
    view.breath_ms = sample_ms;
  }
  if (kind == 7) {
    view.has_heart = true;
    view.heart = rate;
    view.heart_ms = sample_ms;
  }
  if (kind == 5) {
    view.has_xy = true;
    view.local_x = local_x;
    view.local_y = local_y;
    view.local_z = local_z;
    view.room_x = room_x;
    view.room_y = room_y;
    view.in_boundary = in_boundary;
    view.position_ms = sample_ms;
  }
}

struct TelemetryShape {
  const char *presence_value;
  const char *presence_quality;
  const char *targets_quality;
  const char *position_quality;
  bool known_presence;
  bool present;
};

inline TelemetryShape telemetry_shape(const RadarView &radar, uint32_t now_ms) {
  TelemetryShape shape;
  shape.known_presence = radar.has_presence;
  shape.present = shape.known_presence && radar.presence;
  const bool pos_stale = radar.has_xy && now_ms - radar.position_ms >= 6000;
  shape.position_quality = !radar.has_xy ? "unknown" : (pos_stale ? "stale" : "valid");
  shape.presence_value = !shape.known_presence ? "null" : (radar.presence ? "true" : "false");
  shape.presence_quality = shape.known_presence ? "valid" : "unknown";
  shape.targets_quality =
      !shape.known_presence
          ? "unknown"
          : (shape.present && radar.has_xy ? shape.position_quality : (shape.present ? "unknown" : "valid"));
  return shape;
}

}  // namespace mwcp_host
