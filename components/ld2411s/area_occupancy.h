#pragma once

#include <cmath>
#include <cstdint>

namespace mmwave_area {

struct Vec2 {
  float x = 0.f;
  float y = 0.f;
};

struct Area {
  static constexpr uint8_t kMaxVertices = 12;
  Vec2 v[kMaxVertices]{};
  uint8_t n = 0;
  bool ready() const { return n >= 3; }
  Vec2 centroid() const {
    if (n == 0)
      return {};
    float sx = 0.f, sy = 0.f;
    for (uint8_t i = 0; i < n; i++) {
      sx += v[i].x;
      sy += v[i].y;
    }
    return {sx / static_cast<float>(n), sy / static_cast<float>(n)};
  }
};

struct Sample {
  bool active = false;
  bool in_boundary = false;
  float x = 0.f;
  float y = 0.f;
  float speed = 0.f;
};

inline bool point_in(float px, float py, const Area &a) {
  if (a.n < 3)
    return false;
  bool inside = false;
  for (uint8_t i = 0, j = static_cast<uint8_t>(a.n - 1); i < a.n; j = i++) {
    const float xi = a.v[i].x, yi = a.v[i].y;
    const float xj = a.v[j].x, yj = a.v[j].y;
    const float dy = yj - yi;
    if ((yi > py) == (yj > py) || dy == 0.f)
      continue;
    if (px < (xj - xi) * (py - yi) / dy + xi)
      inside = !inside;
  }
  return inside;
}

inline float dist_seg(float px, float py, float ax, float ay, float bx, float by) {
  const float vx = bx - ax, vy = by - ay;
  const float wx = px - ax, wy = py - ay;
  const float c1 = vx * wx + vy * wy;
  if (c1 <= 0.f)
    return hypotf(px - ax, py - ay);
  const float c2 = vx * vx + vy * vy;
  if (c2 <= c1)
    return hypotf(px - bx, py - by);
  const float t = c1 / c2;
  return hypotf(px - (ax + t * vx), py - (ay + t * vy));
}

inline float dist_outside(float px, float py, const Area &a) {
  if (point_in(px, py, a))
    return 0.f;
  float best = 1e9f;
  for (uint8_t i = 0; i < a.n; i++) {
    const Vec2 &p = a.v[i];
    const Vec2 &q = a.v[(i + 1) % a.n];
    const float d = dist_seg(px, py, p.x, p.y, q.x, q.y);
    if (d < best)
      best = d;
  }
  return best;
}

class Occupancy {
 public:
  static constexpr uint8_t kAreas = 3;
  static constexpr uint8_t kTargets = 4;

  void set_hysteresis(float cm) { hyst_ = cm < 0.f ? 0.f : cm; }
  void set_still_speed(float cm_s) { still_ = cm_s < 0.f ? 0.f : cm_s; }
  void set_confirm_ms(uint32_t ms) { confirm_ms_ = ms; }
  void set_clear_ms(uint32_t ms) { clear_ms_ = ms; }
  void set_pass_speed(float cm_s) { pass_ = cm_s < 0.f ? 0.f : cm_s; }
  void set_split(float cm) { split_ = cm < 0.f ? 0.f : cm; }
  void clear(uint8_t i) {
    if (i < kAreas)
      areas_[i].n = 0;
  }
  void add_point(uint8_t i, float x, float y) {
    if (i >= kAreas || areas_[i].n >= Area::kMaxVertices)
      return;
    areas_[i].v[areas_[i].n++] = {x, y};
  }
  bool occupied(uint8_t i) const { return i < kAreas && occupied_[i]; }

  void update(const Sample *samples, uint8_t n, uint32_t now_ms = 0) {
    bool next[kAreas]{};
    float spd[kAreas];
    for (uint8_t a = 0; a < kAreas; a++)
      spd[a] = 1e9f;
    if (n > kTargets)
      n = kTargets;
    for (uint8_t t = 0; t < n; t++) {
      if (!samples[t].active || !samples[t].in_boundary) {
        assign_[t] = -1;
        continue;
      }
      const int8_t cur = assign_[t];
      const bool still = still_ > 0.f && fabsf(samples[t].speed) < still_;
      if (cur >= 0 && cur < static_cast<int8_t>(kAreas) && areas_[cur].ready()) {
        if (still || dist_outside(samples[t].x, samples[t].y, areas_[cur]) <= hyst_) {
          next[cur] = true;
          const float s = fabsf(samples[t].speed);
          if (s < spd[cur])
            spd[cur] = s;
          continue;
        }
      }
      int8_t best = -1;
      float best_d = 1e9f;
      for (uint8_t a = 0; a < kAreas; a++) {
        if (!areas_[a].ready() || !point_in(samples[t].x, samples[t].y, areas_[a]))
          continue;
        const Vec2 c = areas_[a].centroid();
        const float d = hypotf(samples[t].x - c.x, samples[t].y - c.y);
        if (d < best_d) {
          best_d = d;
          best = static_cast<int8_t>(a);
        }
      }
      assign_[t] = best;
      if (best >= 0) {
        next[best] = true;
        const float s = fabsf(samples[t].speed);
        if (s < spd[best])
          spd[best] = s;
      }
    }
    for (uint8_t t = n; t < kTargets; t++)
      assign_[t] = -1;
    apply_occupied_(next, spd, now_ms);
  }

  void update_bands(bool active, bool in_boundary, float range_cm, float speed, uint32_t now_ms) {
    bool next[kAreas]{};
    float spd[kAreas];
    for (uint8_t a = 0; a < kAreas; a++)
      spd[a] = 1e9f;
    if (active && in_boundary) {
      const uint8_t a = (split_ > 0.f && range_cm > split_) ? 1 : 0;
      next[a] = true;
      spd[a] = fabsf(speed);
    }
    apply_occupied_(next, spd, now_ms);
  }

  protected:
  void apply_occupied_(const bool next[kAreas], const float spd[kAreas], uint32_t now_ms) {
    for (uint8_t a = 0; a < kAreas; a++) {
      bool want = next[a];
      if (want && !occupied_[a] && pass_ > 0.f && spd[a] >= pass_)
        want = false;
      if (want) {
        wait_off_[a] = false;
        if (occupied_[a] || confirm_ms_ == 0) {
          occupied_[a] = true;
          wait_on_[a] = false;
          continue;
        }
        if (!wait_on_[a]) {
          wait_on_[a] = true;
          on_since_[a] = now_ms;
        }
        if (now_ms - on_since_[a] >= confirm_ms_) {
          occupied_[a] = true;
          wait_on_[a] = false;
        }
      } else {
        wait_on_[a] = false;
        if (!occupied_[a] || clear_ms_ == 0) {
          occupied_[a] = false;
          wait_off_[a] = false;
          continue;
        }
        if (!wait_off_[a]) {
          wait_off_[a] = true;
          off_since_[a] = now_ms;
        }
        if (now_ms - off_since_[a] >= clear_ms_) {
          occupied_[a] = false;
          wait_off_[a] = false;
        }
      }
    }
  }

  Area areas_[kAreas]{};
  bool occupied_[kAreas]{};
  int8_t assign_[kTargets]{-1, -1, -1, -1};
  bool wait_on_[kAreas]{};
  bool wait_off_[kAreas]{};
  uint32_t on_since_[kAreas]{};
  uint32_t off_since_[kAreas]{};
  float hyst_{50.f};
  float still_{15.f};
  uint32_t confirm_ms_{400};
  uint32_t clear_ms_{2000};
  float pass_{80.f};
  float split_{150.f};
};

}  // namespace mmwave_area
