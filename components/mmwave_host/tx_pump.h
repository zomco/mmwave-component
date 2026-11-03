#pragma once

#include <stddef.h>
#include <stdint.h>
#include <string.h>

struct MwcpTxPump {
  static const size_t kCap = 4143;
  static const size_t kChunk = 64;
  static const uint32_t kStallMs = 250;
  uint8_t data[kCap];
  size_t len = 0;
  size_t sent = 0;
  bool active = false;
  bool needs_resync = false;
  bool have_progress = false;
  uint32_t progress_ms = 0;
  uint32_t overflow = 0;
  uint32_t zero_writes = 0;
  uint32_t short_writes = 0;
  uint32_t failures = 0;
  uint32_t timeouts = 0;
  uint32_t dropped = 0;
  uint32_t resyncs = 0;
  uint32_t completed = 0;

  bool claim() {
    if (active) {
      overflow++;
      return false;
    }
    active = true;
    len = 0;
    sent = 0;
    progress_ms = 0;
    have_progress = false;
    return true;
  }

  bool commit(size_t wire_len) {
    if (!active || wire_len == 0 || wire_len > kCap) {
      abandon();
      return false;
    }
    if (needs_resync) {
      if (wire_len + 1 > kCap) {
        abandon();
        return false;
      }
      memmove(data + 1, data, wire_len);
      data[0] = 0;
      wire_len += 1;
      needs_resync = false;
      resyncs++;
    }
    len = wire_len;
    sent = 0;
    return true;
  }

  void abandon() {
    active = false;
    len = 0;
    sent = 0;
    progress_ms = 0;
    have_progress = false;
    failures++;
  }

  void drop_session() {
    if (sent > 0)
      needs_resync = true;
    if (active)
      dropped++;
    active = false;
    len = 0;
    sent = 0;
    progress_ms = 0;
    have_progress = false;
  }

  bool begin(const uint8_t *wire, size_t wire_len) {
    if (!wire || wire_len == 0 || wire_len > kCap) {
      overflow++;
      return false;
    }
    if (active) {
      overflow++;
      return false;
    }
    memcpy(data, wire, wire_len);
    if (!claim())
      return false;
    return commit(wire_len);
  }

  template<typename Write> void pump(Write write, uint32_t now_ms = 0) {
    if (!active)
      return;
    if (!have_progress) {
      progress_ms = now_ms;
      have_progress = true;
    }
    const size_t want = len - sent > kChunk ? kChunk : len - sent;
    const int n = write(data + sent, want);
    if (n < 0) {
      failures++;
      if (sent > 0)
        needs_resync = true;
      active = false;
      sent = 0;
      len = 0;
      progress_ms = 0;
      have_progress = false;
      return;
    }
    if (n == 0) {
      zero_writes++;
      if (now_ms >= progress_ms && now_ms - progress_ms >= kStallMs) {
        timeouts++;
        if (sent > 0)
          needs_resync = true;
        active = false;
        sent = 0;
        len = 0;
        progress_ms = 0;
        have_progress = false;
      }
      return;
    }
    if (static_cast<size_t>(n) < want)
      short_writes++;
    sent += static_cast<size_t>(n);
    progress_ms = now_ms;
    have_progress = true;
    if (sent >= len) {
      completed++;
      active = false;
      sent = 0;
      len = 0;
      progress_ms = 0;
      have_progress = false;
    }
  }
};
