#pragma once

#include <stddef.h>
#include <stdint.h>
#include <cstdio>
#include <cstring>

struct G0BootEntropy {
  uint8_t mac[6];
  uint32_t r0;
  uint32_t r1;
  uint16_t r2;
};

inline void g0_format_boot_id(char out[33], const G0BootEntropy &entropy) {
  uint8_t raw[16];
  memcpy(raw, entropy.mac, 6);
  raw[6] = static_cast<uint8_t>(entropy.r0);
  raw[7] = static_cast<uint8_t>(entropy.r0 >> 8);
  raw[8] = static_cast<uint8_t>(entropy.r0 >> 16);
  raw[9] = static_cast<uint8_t>(entropy.r0 >> 24);
  raw[10] = static_cast<uint8_t>(entropy.r1);
  raw[11] = static_cast<uint8_t>(entropy.r1 >> 8);
  raw[12] = static_cast<uint8_t>(entropy.r1 >> 16);
  raw[13] = static_cast<uint8_t>(entropy.r1 >> 24);
  raw[14] = static_cast<uint8_t>(entropy.r2);
  raw[15] = static_cast<uint8_t>(entropy.r2 >> 8);
  for (int i = 0; i < 16; i++) std::snprintf(out + (i * 2), 3, "%02x", raw[i]);
  out[32] = 0;
}

inline bool g0_boot_id_same(const G0BootEntropy &a, const G0BootEntropy &b) {
  char left[33];
  char right[33];
  g0_format_boot_id(left, a);
  g0_format_boot_id(right, b);
  return std::strcmp(left, right) == 0;
}

inline bool g0_format_hello(char *out, size_t cap, const char *nonce, const char *boot_id) {
  if (!out || !nonce || !boot_id || std::strlen(nonce) != 32 || std::strlen(boot_id) != 32) return false;
  const int n = std::snprintf(
      out, cap,
      "{\"ok\":true,\"result\":{\"nonce\":\"%s\",\"protocol\":{\"major\":1,\"minor\":0},"
      "\"boot_id\":\"%s\",\"session_ttl_ms\":15000,"
      "\"limits\":{\"max_payload\":4096,\"rpc_inflight\":1,\"max_targets\":1,\"event_budget_bps\":8000},"
      "\"identity\":{\"device_id\":\"g0-probe\",\"configured_model\":\"r60abd1\",\"dimension\":\"2D\","
      "\"firmware_version\":\"g0-probe\"},\"cap_revision\":\"g0\"}}",
      nonce, boot_id);
  return n > 0 && static_cast<size_t>(n) < cap;
}

inline bool g0_format_ping(char *out, size_t cap, uint32_t uptime_ms) {
  const int n = std::snprintf(out, cap, "{\"ok\":true,\"result\":{\"uptime_ms\":%lu}}",
                              static_cast<unsigned long>(uptime_ms));
  return n > 0 && static_cast<size_t>(n) < cap;
}
