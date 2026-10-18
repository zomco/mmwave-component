#include "g0_link.h"

#include <cstdio>
#include <cstring>
#include <vector>

static int g_failed = 0;

static void expect(bool ok, const char *name) {
  if (!ok) {
    std::fprintf(stderr, "FAIL %s\n", name);
    g_failed++;
  }
}

static void test_boot_id() {
  G0BootEntropy zero{};
  char id[33];
  g0_format_boot_id(id, zero);
  expect(std::strlen(id) == 32, "boot id width");
  expect(std::strcmp(id, "00000000000000000000000000000000") == 0, "leading zeros kept");
  G0BootEntropy again = zero;
  expect(g0_boot_id_same(zero, again), "same boot entropy");
  again.r0 = 1;
  expect(!g0_boot_id_same(zero, again), "reboot entropy changes id");
  char hello[640];
  expect(g0_format_hello(hello, sizeof(hello), "0123456789abcdef0123456789abcdef", id), "hello uses firmware formatter");
  expect(std::strstr(hello, id) != nullptr, "hello contains boot id");
  expect(std::strlen(id) != 24, "old 24-char format is not used");
}

static void test_stall_and_resync() {
  MwcpTxPump tx;
  const uint8_t frame[] = {1, 2, 3, 4, 5};
  expect(tx.begin(frame, sizeof(frame)), "queue");
  tx.pump([](const uint8_t *, size_t) { return 0; }, 0);
  expect(tx.active && tx.timeouts == 0, "zero write waits for deadline");
  tx.pump([](const uint8_t *, size_t) { return 0; }, MwcpTxPump::kStallMs);
  expect(!tx.active && tx.timeouts == 1, "stall recovers");
  expect(tx.begin(frame, sizeof(frame)), "requeue");
  tx.pump([](const uint8_t *, size_t) { return 2; }, 0);
  tx.pump([](const uint8_t *, size_t) { return -1; }, 1);
  expect(!tx.active && tx.needs_resync && tx.failures == 1, "partial failure marks resync");
  G0Link link;
  link.tx = tx;
  link.set_boot(G0BootEntropy{});
  expect(link.accept_hello("0123456789abcdef0123456789abcdef", 1, 10), "hello after partial");
  expect(link.tx.data[0] == 0 && link.tx.resyncs == 1, "resync byte precedes new frame");
  expect(link.session_id != 0, "session assigned only with queued response");
}

static void test_session_queue() {
  G0Link link;
  link.set_boot(G0BootEntropy{});
  const uint8_t old_frame[] = {9, 9, 9, 9};
  expect(link.tx.begin(old_frame, sizeof(old_frame)), "occupied");
  expect(link.accept_hello("0123456789abcdef0123456789abcdef", 7, 20), "hello replaces queue");
  expect(link.session_id == 2, "new session");
  std::vector<uint8_t> sent;
  link.tx.pump([&](const uint8_t *data, size_t want) {
    sent.insert(sent.end(), data, data + want);
    return static_cast<int>(want);
  }, 20);
  expect(!sent.empty() && sent[0] != 9, "old session bytes are not sent");
  link.poll_session(20 + G0Link::kSessionTtlMs);
  expect(link.session_id == 0, "session expired");
  sent.clear();
  link.tx.pump([&](const uint8_t *data, size_t want) {
    sent.insert(sent.end(), data, data + want);
    return static_cast<int>(want);
  }, 20 + G0Link::kSessionTtlMs);
  expect(sent.empty(), "expired session sends nothing");
  expect(!link.accept_ping(1, 2, 20 + G0Link::kSessionTtlMs), "old session ping rejected");
  expect(link.accept_hello("fedcba9876543210fedcba9876543210", 1, 30), "hello recovers");
  expect(link.session_id != 2, "rehandshake does not reuse expired session");
}

static void test_error_class_and_status() {
  G0Link link;
  link.note_rx(mwcp::kBadCobs);
  link.note_rx(mwcp::kBadCrc);
  G0Meter meter;
  meter.radar_link = "waiting";
  meter.reset_reason = "power_on";
  meter.radar_frames = 3;
  meter.radar_errors = 1;
  meter.stack_high_water_bytes = 600;
  char body[1200];
  expect(g0_format_status(body, sizeof(body), link, meter), "status formats");
  expect(std::strstr(body, "\"rx_crc_errors\":1") != nullptr, "crc is only crc");
  expect(std::strstr(body, "\"cobs\":1") != nullptr, "cobs is separate");
  expect(std::strstr(body, "\"unmeasured\":[\"config_storage\",\"telemetry_coalesced\"]") != nullptr, "unmeasured marked");
  expect(std::strstr(body, "\"config_storage\":\"healthy\"") == nullptr, "storage is not reported healthy");
  expect(std::strstr(body, "\"stack_high_water_bytes\":600") != nullptr, "raw mark is already bytes");
  expect(std::strstr(body, "\"stack_high_water_bytes\":2400") == nullptr, "four-times overestimate");
  expect(std::strstr(body, "stack_word_bytes") == nullptr, "word size is not guessed");
  char line[320];
  expect(g0_format_meter_line(line, sizeof(line), meter), "baseline line");
  expect(std::strstr(line, "last_radar_frame_ms=null") != nullptr, "missing radar time is null");
}

static void test_parser_resync() {
  G0Link link;
  link.set_boot(G0BootEntropy{});
  expect(link.accept_hello("0123456789abcdef0123456789abcdef", 1, 1), "frame");
  std::vector<uint8_t> good;
  while (link.tx.active) {
    link.tx.pump([&](const uint8_t *data, size_t want) {
      good.insert(good.end(), data, data + want);
      return static_cast<int>(want);
    }, 1);
  }
  mwcp::Parser parser;
  int frames = 0;
  int errors = 0;
  struct Count { int *frames; int *errors; } count{&frames, &errors};
  const uint8_t partial[] = {0x01, 0x02};
  parser.push(partial, sizeof(partial), 1, nullptr, nullptr, nullptr);
  parser.push(good.data(), good.size(), 1, [](const mwcp::Frame &, void *user) {
    (*static_cast<Count *>(user)->frames)++;
  }, [](mwcp::Status, void *user) {
    (*static_cast<Count *>(user)->errors)++;
  }, &count);
  expect(errors == 1 && frames == 1, "delimiter resyncs then accepts the firmware frame");
}

int main() {
  test_boot_id();
  test_stall_and_resync();
  test_session_queue();
  test_error_class_and_status();
  test_parser_resync();
  if (g_failed) return 1;
  std::printf("g0 session test passed\n");
  return 0;
}
