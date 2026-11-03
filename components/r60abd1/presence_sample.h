#pragma once

#include <stdint.h>

// Presence reports on the R60ABD1 are change-only (manual V3.4, control 0x80
// command 0x01). A host that reboots without resetting the module will not
// see another 0x01 until the next transition. The documented query is
// control 0x80 command 0x81, data 0x0F; the reply uses the same 0x00 / 0x01
// payload as the active report. Anything else is not a presence sample.

namespace esphome {
namespace r60abd1 {

enum PresenceClass : uint8_t {
  kPresenceIgnore = 0,
  kPresenceAbsent = 1,
  kPresencePresent = 2,
};

inline PresenceClass classify_presence_report(uint8_t cmd, const uint8_t *data, uint16_t len) {
  if (data == 0 || len == 0)
    return kPresenceIgnore;
  // 0x01 active report, 0x81 query reply. 0x80 is the enable-switch query
  // and must not be read as somebody/nobody.
  if (cmd != 0x01 && cmd != 0x81)
    return kPresenceIgnore;
  if (data[0] == 0x00)
    return kPresenceAbsent;
  if (data[0] == 0x01)
    return kPresencePresent;
  return kPresenceIgnore;
}

static const uint8_t kPresenceCtrl = 0x80;
static const uint8_t kPresenceEnableCmd = 0x00;
static const uint8_t kPresenceEnableData = 0x01;
static const uint8_t kPresenceQueryCmd = 0x81;
static const uint8_t kPresenceQueryData = 0x0F;

// Enable first. The query is one-shot after the other enables, not a periodic
// NVS write and not a module reset.
static const uint32_t kEnablePresenceDelayMs = 100;
static const uint32_t kEnableBreathDelayMs = 150;
static const uint32_t kEnableHeartDelayMs = 200;
static const uint32_t kEnableSleepDelayMs = 250;
static const uint32_t kQueryPresenceDelayMs = 400;

inline bool startup_queries_presence_after_enable() {
  return kQueryPresenceDelayMs > kEnablePresenceDelayMs && kQueryPresenceDelayMs > kEnableBreathDelayMs &&
         kQueryPresenceDelayMs > kEnableHeartDelayMs && kQueryPresenceDelayMs > kEnableSleepDelayMs &&
         kPresenceCtrl == 0x80 && kPresenceQueryCmd == 0x81 && kPresenceQueryData == 0x0F;
}

}  // namespace r60abd1
}  // namespace esphome
