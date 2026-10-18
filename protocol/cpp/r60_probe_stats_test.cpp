#include "r60_probe_stats.h"
#include "tx_pump.h"

#include <cstdio>

static int g_failed = 0;

static void expect(bool ok, const char *name) {
  if (!ok) {
    std::fprintf(stderr, "FAIL %s\n", name);
    g_failed++;
  }
}

static void test_radar_stats() {
  R60ProbeStats stats;
  stats.note_uart_byte();
  stats.note_parse_error();
  expect(stats.last_valid_frame_ms == 0, "noise does not refresh valid time");
  expect(stats.parse_errors == 1, "parse error");
  stats.note_valid_frame(1000);
  expect(stats.valid_frames == 1, "valid frame without text entity");
  expect(stats.last_valid_frame_ms == 1000, "valid time");
  stats.note_target();
  expect(stats.target_observations == 1, "target without text entity");
  stats.note_valid_frame(2000);
  expect(stats.target_observations == 1, "presence frame is not a target");
  expect(!stats.link_waiting(), "link up");
  expect(stats.link_stale(5000, 2000), "stale is not no-target");
}

static void test_tx_pump() {
  MwcpTxPump tx;
  const uint8_t frame[] = {1, 2, 3, 4, 5};
  expect(tx.begin(frame, sizeof(frame)), "queue");
  expect(!tx.begin(frame, sizeof(frame)), "busy");
  expect(tx.overflow == 1, "overflow");
  tx.pump([](const uint8_t *, size_t) { return 0; });
  expect(tx.zero_writes == 1 && tx.active, "backpressure keeps frame");
  tx.pump([](const uint8_t *, size_t want) { return static_cast<int>(want - 1); });
  expect(tx.short_writes == 1 && tx.active, "short write");
  tx.pump([](const uint8_t *, size_t) { return -1; });
  expect(tx.failures == 1 && !tx.active, "disconnect");
  expect(tx.begin(frame, sizeof(frame)), "after disconnect");
  tx.pump([](const uint8_t *, size_t want) { return static_cast<int>(want); });
  expect(tx.completed == 1 && !tx.active, "complete");
}

int main() {
  test_radar_stats();
  test_tx_pump();
  if (g_failed) return 1;
  std::printf("g0 probe host test passed\n");
  return 0;
}
