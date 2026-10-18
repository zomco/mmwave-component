#pragma once

#include "g0_hello.h"
#include "g0_meter_line.h"
#include "mwcp_codec.h"
#include "tx_pump.h"

#include <cstdio>
#include <cstring>

struct G0Link;
bool g0_format_status(char *out, size_t cap, const G0Link &link, const G0Meter &meter);

struct G0Link {
  static const uint32_t kSessionTtlMs = 15000;
  G0BootEntropy entropy{};
  char boot_id[33]{};
  uint32_t session_id = 0;
  uint32_t next_session = 1;
  uint32_t session_touch_ms = 0;
  uint32_t wire_seq = 1;
  uint32_t rx_frames = 0;
  uint32_t rx_crc = 0;
  uint32_t rx_cobs = 0;
  uint32_t rx_header = 0;
  uint32_t rx_utf8 = 0;
  uint32_t rx_json = 0;
  uint32_t rx_oversize = 0;
  uint32_t rx_timeout = 0;
  uint32_t invalid_requests = 0;
  uint32_t hello_enqueue_failures = 0;
  uint32_t logs_seen = 0;
  uint32_t logs_dropped = 0;
  bool encoding = false;
  MwcpTxPump tx{};
  mwcp::Parser parser{};
  uint8_t encode_decoded[mwcp::kMaxDecoded]{};

  void set_boot(const G0BootEntropy &value) {
    entropy = value;
    g0_format_boot_id(boot_id, entropy);
  }

  void note_rx(mwcp::Status status) {
    if (status == mwcp::kBadCrc) rx_crc++;
    else if (status == mwcp::kBadCobs) rx_cobs++;
    else if (status == mwcp::kBadUtf8) rx_utf8++;
    else if (status == mwcp::kBadJson) rx_json++;
    else if (status == mwcp::kOversize || status == mwcp::kPayloadTooLarge || status == mwcp::kBadLength) rx_oversize++;
    else if (status == mwcp::kTimeout) rx_timeout++;
    else rx_header++;
  }

  void poll_session(uint32_t now_ms) {
    if (session_id != 0 && now_ms - session_touch_ms >= kSessionTtlMs) end_session();
  }

  void end_session() {
    session_id = 0;
    tx.drop_session();
  }

  bool session_ok(uint32_t request_session, uint32_t now_ms) const {
    return session_id != 0 && request_session == session_id && now_ms - session_touch_ms < kSessionTtlMs;
  }

  bool enqueue(uint16_t code, uint32_t request_id, uint32_t response_session, const char *json) {
    if (encoding || !json) {
      tx.overflow++;
      return false;
    }
    if (!tx.claim()) return false;
    encoding = true;
    size_t wire_len = 0;
    size_t decoded_len = 0;
    const mwcp::EncodeInput input = {2, response_session, request_id, code, wire_seq, reinterpret_cast<const uint8_t *>(json), std::strlen(json), true};
    const mwcp::Status status = mwcp::encode_frame(input, tx.data, MwcpTxPump::kCap, &wire_len, encode_decoded, sizeof(encode_decoded), &decoded_len);
    encoding = false;
    if (status != mwcp::kOk || !tx.commit(wire_len)) {
      if (tx.active) tx.abandon();
      return false;
    }
    wire_seq = wire_seq == 0xfffffffe ? 1 : wire_seq + 1;
    return true;
  }

  bool accept_hello(const char *nonce, uint32_t request_id, uint32_t now_ms) {
    tx.drop_session();
    const uint32_t candidate = next_session == 0xfffffffe ? 1 : next_session + 1;
    char body[640];
    if (!g0_format_hello(body, sizeof(body), nonce, boot_id) || !enqueue(0x0001, request_id, candidate, body)) {
      hello_enqueue_failures++;
      return false;
    }
    next_session = candidate;
    session_id = candidate;
    session_touch_ms = now_ms;
    return true;
  }

  bool accept_ping(uint32_t request_id, uint32_t request_session, uint32_t now_ms) {
    if (!session_ok(request_session, now_ms)) {
      invalid_requests++;
      return false;
    }
    char body[64];
    if (!g0_format_ping(body, sizeof(body), now_ms) || !enqueue(0x0002, request_id, session_id, body)) return false;
    session_touch_ms = now_ms;
    return true;
  }

  bool accept_status(uint32_t request_id, uint32_t request_session, uint32_t now_ms, const G0Meter &meter) {
    if (!session_ok(request_session, now_ms)) {
      invalid_requests++;
      return false;
    }
    char body[1200];
    if (!g0_format_status(body, sizeof(body), *this, meter) || !enqueue(0x0012, request_id, session_id, body)) return false;
    session_touch_ms = now_ms;
    return true;
  }

  static bool read_nonce(const uint8_t *payload, size_t len, char out[33]) {
    const char key[] = "\"nonce\":\"";
    if (!payload || len < 42) return false;
    for (size_t i = 0; i + 42 <= len; i++) {
      if (std::memcmp(payload + i, key, 9) != 0) continue;
      bool hex = true;
      for (int n = 0; n < 32; n++) {
        const char c = static_cast<char>(payload[i + 9 + n]);
        if (!((c >= '0' && c <= '9') || (c >= 'a' && c <= 'f'))) hex = false;
      }
      if (!hex || payload[i + 41] != '"') continue;
      std::memcpy(out, payload + i + 9, 32);
      out[32] = 0;
      return true;
    }
    return false;
  }
};

inline bool g0_format_status(char *out, size_t cap, const G0Link &link, const G0Meter &meter) {
  char last_ms[16] = "null";
  if (meter.radar_frame_known) std::snprintf(last_ms, sizeof(last_ms), "%lu", static_cast<unsigned long>(meter.last_radar_frame_ms));
  const int n = std::snprintf(
      out, cap,
      "{\"ok\":true,\"result\":{\"uptime_ms\":%lu,\"radar_link\":\"%s\",\"last_radar_frame_ms\":%s,"
      "\"config_revision\":null,\"config_storage\":\"degraded\",\"active_jobs\":[],"
      "\"counters\":{\"rx_frames\":%lu,\"rx_crc_errors\":%lu,\"rx_oversize\":%lu,\"invalid_requests\":%lu,"
      "\"radar_frames\":%lu,\"radar_errors\":%lu,\"telemetry_coalesced\":0,\"logs_dropped\":%lu,\"tx_overflow\":%lu},"
      "\"reset_reason\":\"%s\",\"free_heap\":%lu,\"min_free_heap\":%lu,\"largest_free_block\":%lu,"
      "\"stack_high_water_bytes\":%lu,\"stack_high_water_unit\":\"bytes\",\"stack_type_bytes\":1,\"max_loop_us\":%lu,"
      "\"usb_exclusive\":%s,\"usb_install_err\":%d,"
      "\"tx\":{\"zero_writes\":%lu,\"short_writes\":%lu,\"failures\":%lu,\"timeouts\":%lu,\"overflow\":%lu,\"resyncs\":%lu,\"dropped\":%lu},"
      "\"rx_errors\":{\"crc\":%lu,\"cobs\":%lu,\"header\":%lu,\"utf8\":%lu,\"json\":%lu,\"timeout\":%lu,\"oversize\":%lu},"
      "\"radar_targets\":%lu,"
      "\"unmeasured\":[\"config_storage\",\"telemetry_coalesced\"],"
      "\"config_storage_measured\":false,\"telemetry_coalesced_measured\":false}}",
      static_cast<unsigned long>(meter.uptime_ms), meter.radar_link ? meter.radar_link : "unknown", last_ms,
      static_cast<unsigned long>(link.rx_frames), static_cast<unsigned long>(link.rx_crc),
      static_cast<unsigned long>(link.rx_oversize), static_cast<unsigned long>(link.invalid_requests),
      static_cast<unsigned long>(meter.radar_frames), static_cast<unsigned long>(meter.radar_errors),
      static_cast<unsigned long>(link.logs_dropped), static_cast<unsigned long>(link.tx.overflow),
      meter.reset_reason ? meter.reset_reason : "unknown",
      static_cast<unsigned long>(meter.free_heap), static_cast<unsigned long>(meter.min_free_heap),
      static_cast<unsigned long>(meter.largest_free_block), static_cast<unsigned long>(meter.stack_high_water_bytes),
      static_cast<unsigned long>(meter.max_loop_us), meter.usb_exclusive ? "true" : "false", meter.usb_install_err,
      static_cast<unsigned long>(link.tx.zero_writes), static_cast<unsigned long>(link.tx.short_writes),
      static_cast<unsigned long>(link.tx.failures), static_cast<unsigned long>(link.tx.timeouts),
      static_cast<unsigned long>(link.tx.overflow), static_cast<unsigned long>(link.tx.resyncs),
      static_cast<unsigned long>(link.tx.dropped),
      static_cast<unsigned long>(link.rx_crc), static_cast<unsigned long>(link.rx_cobs),
      static_cast<unsigned long>(link.rx_header), static_cast<unsigned long>(link.rx_utf8),
      static_cast<unsigned long>(link.rx_json), static_cast<unsigned long>(link.rx_timeout),
      static_cast<unsigned long>(link.rx_oversize), static_cast<unsigned long>(meter.radar_targets));
  return n > 0 && static_cast<size_t>(n) < cap;
}


