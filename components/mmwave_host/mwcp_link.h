#pragma once

#include "mwcp_codec.h"
#include "mwcp_service.h"
#include "tx_pump.h"

#include <string.h>

struct MwcpHostLink {
  MwcpTxPump tx;
  uint8_t control[4143]{};
  size_t control_len = 0;
  bool control_ready = false;
  bool pumping_control = false;
  uint32_t control_completed = 0;
  // A control response must never be silently dropped: if the pump abandons
  // it mid-send (host not draining), it is re-queued and retried until it is
  // fully written or the attempt window expires. Dropping it is what made a
  // stalled host stretch every RPC to the client's retry timeout (G2
  // hardware finding: device-side delay matched the client timeout exactly).
  uint32_t control_queued_ms = 0;
  uint32_t retry_not_before_ms = 0;
  static const uint32_t kControlRetryMs = 25;      // backoff between attempts
  static const uint32_t kControlGiveUpMs = 15000;  // session-TTL scale; the response is moot after that
  uint8_t event_frame[4143]{};
  size_t event_len = 0;
  bool event_ready = false;
  uint32_t seq = 1;
  uint8_t scratch[4143]{};
  uint8_t decoded[4124]{};
  // Response scratch for mwcp_dispatch_request. A member, not a stack local:
  // the ESP32-C3 main task stack is 3.5 KiB by default and this buffer alone
  // is 4 KiB, which overflowed and reset the device on every dispatched
  // request (G2 hardware finding). Single-threaded: only the main loop
  // dispatches, and Service::handle fully rewrites the buffer before
  // queue_json reads it.
  char dispatch_json[4096]{};

  bool can_queue_control() const { return !control_ready; }
  bool may_queue_event() const { return !tx.active && !control_ready; }

  bool queue_json(uint8_t kind, uint32_t session, uint32_t request, uint16_t code, const char *json, bool control) {
    if (!json)
      return false;
    if (control && control_ready)
      return false;
    if (!control && event_ready)
      return false;
    size_t wire_len = 0;
    size_t decoded_len = 0;
    const mwcp::EncodeInput input = {kind,         session, request, code, seq, reinterpret_cast<const uint8_t *>(json),
                                     strlen(json), true};
    if (mwcp::encode_frame(input, scratch, sizeof(scratch), &wire_len, decoded, sizeof(decoded), &decoded_len) !=
        mwcp::kOk)
      return false;
    uint8_t *dst = control ? this->control : event_frame;
    const size_t cap = control ? sizeof(this->control) : sizeof(event_frame);
    if (wire_len == 0 || wire_len > cap)
      return false;
    memcpy(dst, scratch, wire_len);
    if (control) {
      control_len = wire_len;
      control_ready = true;
    } else {
      event_len = wire_len;
      event_ready = true;
    }
    seq = seq == 0xfffffffe ? 1 : seq + 1;
    return true;
  }

  template<typename Write> void pump(Write write, uint32_t now_ms) {
    if (!tx.active) {
      // An abandoned control attempt (pumping_control with no completion)
      // falls back to control_ready and is retried until fully sent.
      if (pumping_control && !control_ready) {
        if (control_queued_ms != 0 && now_ms - control_queued_ms >= kControlGiveUpMs) {
          pumping_control = false;  // session is long gone; drop the response
          control_queued_ms = 0;
        } else {
          control_ready = true;  // re-queue the same bytes
          pumping_control = false;
        }
      }
      if (control_ready) {
        if (now_ms < retry_not_before_ms)
          return;  // back off after an abandon instead of hammering the driver
        if (!tx.begin(control, control_len))
          return;
        control_ready = false;
        if (control_queued_ms == 0)
          control_queued_ms = now_ms;
        pumping_control = true;
      } else if (event_ready) {
        if (now_ms < retry_not_before_ms)
          return;
        if (!tx.begin(event_frame, event_len))
          return;
        event_ready = false;
        pumping_control = false;
      }
    }
    const uint32_t before = tx.completed;
    const uint32_t timeouts_before = tx.timeouts;
    const uint32_t failures_before = tx.failures;
    tx.pump(write, now_ms);
    if (tx.completed != before && pumping_control) {
      control_completed++;
      pumping_control = false;
      control_queued_ms = 0;
    }
    if ((tx.timeouts != timeouts_before || tx.failures != failures_before) && now_ms >= retry_not_before_ms) {
      // An attempt just ended without finishing: pause briefly before the
      // next begin so a non-draining host cannot turn the pump into a
      // busy retry loop against the USB driver.
      retry_not_before_ms = now_ms + kControlRetryMs;
    }
  }

  bool control_accepted_by_driver() const {
    return control_completed > 0 && !control_ready && !tx.active && !pumping_control;
  }
};

inline int mwcp_forward_events(mwcp_host::Service &svc, MwcpHostLink &link) {
  if (!link.may_queue_event() || link.event_ready)
    return 0;
  static char json[mwcp_host::kMaxEventJson];
  uint16_t code = 0;
  if (!svc.next_event(json, sizeof(json), &code))
    return 0;
  if (!link.queue_json(3, svc.session_id(), 0, code, json, false)) {
    svc.note_unsent_event();
    return -1;
  }
  return 1;
}

inline bool mwcp_dispatch_request(mwcp_host::Service &svc, MwcpHostLink &link, uint32_t now, uint32_t session,
                                  uint32_t request, uint16_t code, const uint8_t *payload, size_t len) {
  if (!link.can_queue_control())
    return false;
  char *json = link.dispatch_json;
  uint32_t sid = 0;
  if (!svc.handle(now, session, request, code, payload, len, json, sizeof(link.dispatch_json), &sid))
    return false;
  return link.queue_json(2, sid, request, code, json, true);
}
