#include "g0_link.h"

#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <vector>

static int hex_nibble(char c) {
  if (c >= '0' && c <= '9') return c - '0';
  if (c >= 'a' && c <= 'f') return c - 'a' + 10;
  if (c >= 'A' && c <= 'F') return c - 'A' + 10;
  return -1;
}

static bool parse_hex(const char *text, std::vector<uint8_t> *out) {
  const size_t n = std::strlen(text);
  if (n % 2) return false;
  out->clear();
  for (size_t i = 0; i < n; i += 2) {
    const int hi = hex_nibble(text[i]);
    const int lo = hex_nibble(text[i + 1]);
    if (hi < 0 || lo < 0) return false;
    out->push_back(static_cast<uint8_t>((hi << 4) | lo));
  }
  return true;
}

static void print_hex(const uint8_t *data, size_t len) {
  for (size_t i = 0; i < len; i++) std::printf("%02x", data[i]);
  std::printf("\n");
}

static bool parse_entropy(const char *mac, const char *r0, const char *r1, const char *r2, G0BootEntropy *out) {
  std::vector<uint8_t> bytes;
  if (!parse_hex(mac, &bytes) || bytes.size() != 6) return false;
  std::memcpy(out->mac, bytes.data(), 6);
  out->r0 = static_cast<uint32_t>(std::strtoul(r0, nullptr, 0));
  out->r1 = static_cast<uint32_t>(std::strtoul(r1, nullptr, 0));
  out->r2 = static_cast<uint16_t>(std::strtoul(r2, nullptr, 0));
  return true;
}

static int cmd_boot(int argc, char **argv) {
  if (argc != 6) return 2;
  G0BootEntropy entropy{};
  if (!parse_entropy(argv[2], argv[3], argv[4], argv[5], &entropy)) return 2;
  char boot[33];
  g0_format_boot_id(boot, entropy);
  std::printf("%s\n", boot);
  return std::strlen(boot) == 32 ? 0 : 1;
}

static int cmd_respond(int argc, char **argv) {
  if (argc != 8) return 2;
  G0Link link;
  G0BootEntropy entropy{};
  if (!parse_entropy(argv[2], argv[3], argv[4], argv[5], &entropy)) return 2;
  link.set_boot(entropy);
  const uint32_t now = static_cast<uint32_t>(std::strtoul(argv[6], nullptr, 0));
  std::vector<uint8_t> request;
  if (!parse_hex(argv[7], &request)) return 2;
  link.parser.push(request.data(), request.size(), now, [](const mwcp::Frame &frame, void *user) {
    auto *self = static_cast<G0Link *>(user);
    if (frame.kind != 1) return;
    if (frame.code == 0x0001) {
      char nonce[33];
      if (!G0Link::read_nonce(frame.payload, frame.payload_length, nonce)) {
        self->invalid_requests++;
        return;
      }
      self->accept_hello(nonce, frame.request_id, 0);
      return;
    }
    if (frame.code == 0x0002) self->accept_ping(frame.request_id, frame.session_id, 0);
    if (frame.code == 0x0012) {
      G0Meter meter;
      meter.radar_link = "unknown";
      meter.reset_reason = "unknown";
      self->accept_status(frame.request_id, frame.session_id, 0, meter);
    }
  }, [](mwcp::Status status, void *user) {
    static_cast<G0Link *>(user)->note_rx(status);
  }, &link);
  std::vector<uint8_t> out;
  while (link.tx.active) {
    link.tx.pump([&](const uint8_t *data, size_t want) {
      out.insert(out.end(), data, data + want);
      return static_cast<int>(want);
    }, now);
  }
  std::printf("%s\n%lu\n", link.boot_id, static_cast<unsigned long>(link.session_id));
  print_hex(out.data(), out.size());
  return 0;
}

static int cmd_ping(int argc, char **argv) {
  if (argc != 5) return 2;
  G0Link link;
  link.session_id = static_cast<uint32_t>(std::strtoul(argv[2], nullptr, 0));
  link.session_touch_ms = 0;
  const uint32_t request = static_cast<uint32_t>(std::strtoul(argv[3], nullptr, 0));
  const uint32_t now = static_cast<uint32_t>(std::strtoul(argv[4], nullptr, 0));
  link.set_boot(G0BootEntropy{});
  if (now >= G0Link::kSessionTtlMs) return 3;
  if (!link.accept_ping(request, link.session_id, now)) return 4;
  std::vector<uint8_t> out;
  while (link.tx.active) {
    link.tx.pump([&](const uint8_t *data, size_t want) {
      out.insert(out.end(), data, data + want);
      return static_cast<int>(want);
    }, now);
  }
  print_hex(out.data(), out.size());
  return 0;
}

static int cmd_status(int argc, char **argv) {
  (void)argc;
  (void)argv;
  G0Link link;
  link.rx_crc = 1;
  link.rx_cobs = 4;
  link.rx_oversize = 2;
  link.tx.zero_writes = 3;
  link.tx.short_writes = 5;
  link.tx.failures = 6;
  link.tx.timeouts = 7;
  link.tx.overflow = 8;
  G0Meter meter;
  meter.uptime_ms = 10;
  meter.free_heap = 1000;
  meter.min_free_heap = 800;
  meter.largest_free_block = 700;
  meter.stack_high_water_bytes = 600;
  meter.max_loop_us = 40;
  meter.radar_frames = 2;
  meter.radar_errors = 1;
  meter.radar_targets = 1;
  meter.radar_frame_known = true;
  meter.last_radar_frame_ms = 9;
  meter.radar_link = "healthy";
  meter.reset_reason = "power_on";
  meter.usb_exclusive = true;
  char body[1200];
  char line[320];
  if (!g0_format_status(body, sizeof(body), link, meter)) return 1;
  if (!g0_format_meter_line(line, sizeof(line), meter)) return 1;
  std::printf("%s\n%s\n", body, line);
  return 0;
}

int main(int argc, char **argv) {
  if (argc < 2) return 2;
  if (std::strcmp(argv[1], "boot") == 0) return cmd_boot(argc, argv);
  if (std::strcmp(argv[1], "respond") == 0) return cmd_respond(argc, argv);
  if (std::strcmp(argv[1], "ping") == 0) return cmd_ping(argc, argv);
  if (std::strcmp(argv[1], "status") == 0) return cmd_status(argc, argv);
  return 2;
}
