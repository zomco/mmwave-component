#pragma once

#include <cstring>

#include "mwcp_codec.h"

// Lives in esphome::mmwave_host like the rest of the component, so
// MwcpHost's unqualified references resolve.
namespace esphome {
namespace mmwave_host {

// G2-R3-01: a deferred request must OWN its payload. The parser's decoded
// buffer is reused by every subsequent frame (COBS decode writes it before
// the CRC check), so a shallow Frame copy can be rewritten by a later bad
// frame before loop() dispatches. This struct holds a bounded, owned copy.
//
// Policy (no silent overwrite, no latest-wins):
// - empty slot: any request is stashed (payload copied byte-exact);
// - while full, a frame with the SAME identity (session+request+code) AND
//   a byte-identical payload is a true idempotent transport resend: it is
//   merged (counted, payload unchanged - identical anyway);
// - while full, a frame with the SAME identity but a DIFFERENT payload,
//   length or code is an ID_REUSE conflict (protocol 3.2): the incoming
//   frame is NOT silently dropped - its identity and payload are kept in
//   the bounded conflict slot below, and loop() forwards it to the Service
//   AFTER the stashed request. The Service's replay cache holds the
//   original request and answers ID_REUSE without executing the conflict
//   body. The RX callback only copies bytes; the conflict answer happens
//   on the main loop, bounded (one slot, static memory).
// - anything else while full (a DIFFERENT request id) cannot be answered
//   with ID_REUSE (it is not a reuse); with rpc_inflight=1 it is a
//   protocol violation or noise, so it is dropped loudly and counted.
//
// Memory: two static payload slots (kPayloadCap 4096 each) + metadata,
// static in MwcpHost. Loop cost: one memcmp plus one memcpy per stashed
// frame; no allocation, no dynamic queue.
struct DeferredRequest {
  static const size_t kPayloadCap = 4096;

  uint8_t payload_[kPayloadCap];
  uint16_t payload_length_ = 0;
  uint8_t kind_ = 0;
  uint32_t session_id_ = 0;
  uint32_t request_id_ = 0;
  uint16_t code_ = 0;
  bool full_ = false;

  // Conflict slot (r3d): the same-id/different-body frame kept for the
  // delayed ID_REUSE answer. One slot, static; a further conflict while
  // the slot is full overwrites it (bounded) and is counted.
  uint8_t conflict_payload_[kPayloadCap];
  uint16_t conflict_length_ = 0;
  uint8_t conflict_kind_ = 0;
  uint32_t conflict_session_ = 0;
  uint32_t conflict_request_ = 0;
  uint16_t conflict_code_ = 0;
  bool conflict_full_ = false;

  uint32_t resend_merges = 0;
  uint32_t dropped_conflicts = 0;    // different-request frames while full
  uint32_t conflict_forwards = 0;    // same-id conflicts kept for ID_REUSE
  uint32_t conflict_overwrites = 0;  // conflicts that replaced an unforwarded one

  bool has() const { return full_; }
  bool has_conflict() const { return conflict_full_; }

  /// Stash per the policy above. Returns true when the primary slot holds
  /// a request afterwards (fresh stash or byte-identical resend merged).
  bool stash(const mwcp::Frame &frame) {
    if (!full_)
      return copy_(frame);
    const bool same_id = frame.session_id == session_id_ && frame.request_id == request_id_;
    if (same_id && frame.code == code_ && frame.payload != nullptr && frame.payload_length == payload_length_ &&
        (payload_length_ == 0 || memcmp(payload_, frame.payload, payload_length_) == 0)) {
      resend_merges++;
      return true;  // byte-identical transport resend; keep the original
    }
    if (same_id) {
      // ID_REUSE conflict: keep it (bounded) for the Service to answer;
      // the original stashed request stays untouched.
      stash_conflict_(frame);
      return true;
    }
    dropped_conflicts++;
    return false;
  }

  /// True when the stashed request matches the given identity.
  bool matches(uint32_t session, uint32_t request, uint16_t code) const {
    return full_ && session_id_ == session && request_id_ == request && code_ == code;
  }

  void clear() {
    full_ = false;
    payload_length_ = 0;
    memset(payload_, 0, sizeof(payload_));
  }

  void clear_conflict() {
    conflict_full_ = false;
    conflict_length_ = 0;
    memset(conflict_payload_, 0, sizeof(conflict_payload_));
  }

 private:
  bool copy_(const mwcp::Frame &frame) {
    if (frame.payload == nullptr || frame.payload_length == 0 || frame.payload_length > kPayloadCap)
      return false;
    memcpy(payload_, frame.payload, frame.payload_length);
    payload_length_ = frame.payload_length;
    kind_ = frame.kind;
    session_id_ = frame.session_id;
    request_id_ = frame.request_id;
    code_ = frame.code;
    full_ = true;
    return true;
  }

  void stash_conflict_(const mwcp::Frame &frame) {
    if (frame.payload == nullptr || frame.payload_length == 0 || frame.payload_length > kPayloadCap) {
      dropped_conflicts++;
      return;
    }
    if (conflict_full_)
      conflict_overwrites++;
    memcpy(conflict_payload_, frame.payload, frame.payload_length);
    conflict_length_ = frame.payload_length;
    conflict_kind_ = frame.kind;
    conflict_session_ = frame.session_id;
    conflict_request_ = frame.request_id;
    conflict_code_ = frame.code;
    conflict_full_ = true;
    conflict_forwards++;
  }
};

}  // namespace mmwave_host
}  // namespace esphome
