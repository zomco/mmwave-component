#include "presence_sample.h"
#include "radar_observe.h"

#include <cstdint>
#include <cstdio>
#include <cstring>

static int g_failed = 0;

static void expect(bool ok, const char *name) {
  if (!ok) {
    std::fprintf(stderr, "FAIL %s\n", name);
    g_failed++;
  }
}

static void test_classify() {
  using esphome::r60abd1::classify_presence_report;
  using esphome::r60abd1::kPresenceAbsent;
  using esphome::r60abd1::kPresenceIgnore;
  using esphome::r60abd1::kPresencePresent;
  const uint8_t absent = 0x00;
  const uint8_t present = 0x01;
  const uint8_t other = 0x0F;
  expect(classify_presence_report(0x01, &absent, 1) == kPresenceAbsent, "active nobody");
  expect(classify_presence_report(0x01, &present, 1) == kPresencePresent, "active somebody");
  expect(classify_presence_report(0x81, &absent, 1) == kPresenceAbsent, "query nobody");
  expect(classify_presence_report(0x81, &present, 1) == kPresencePresent, "query somebody");
  expect(classify_presence_report(0x81, &other, 1) == kPresenceIgnore, "query junk ignored");
  expect(classify_presence_report(0x01, &other, 1) == kPresenceIgnore, "active junk ignored");
  expect(classify_presence_report(0x80, &present, 1) == kPresenceIgnore, "enable switch is not presence");
  expect(classify_presence_report(0x05, &present, 1) == kPresenceIgnore, "position cmd is not presence");
  expect(classify_presence_report(0x81, &present, 0) == kPresenceIgnore, "empty reply ignored");
  expect(classify_presence_report(0x81, 0, 1) == kPresenceIgnore, "null data ignored");
  expect(esphome::r60abd1::startup_queries_presence_after_enable(), "query is after enable");
}

static void observe(mwcp_host::RadarView &view, uint8_t kind, bool presence, uint32_t sample_ms, int16_t x = 0,
                    int16_t z = 0) {
  mwcp_host::apply_observation(view, kind, presence, 120, x, 0, z, 30, 0, true, 16.5f, sample_ms);
}

static void test_observer() {
  mwcp_host::RadarView view{};
  mwcp_host::TelemetryShape cold = mwcp_host::telemetry_shape(view, 1000);
  expect(!view.has_presence && std::strcmp(cold.presence_value, "null") == 0 &&
             std::strcmp(cold.presence_quality, "unknown") == 0 && std::strcmp(cold.targets_quality, "unknown") == 0 &&
             !cold.present,
         "unsampled stays unknown");

  observe(view, 5, false, 1100, 12, 40);
  mwcp_host::TelemetryShape pos = mwcp_host::telemetry_shape(view, 1100);
  expect(view.has_xy && view.local_z == 40 && view.position_ms == 1100 && !view.has_presence &&
             std::strcmp(pos.presence_value, "null") == 0 && !pos.present,
         "coordinates do not invent presence");

  observe(view, 4, false, 1200);
  observe(view, 6, false, 1300);
  observe(view, 7, false, 1400);
  expect(!view.has_presence && view.has_distance && view.distance_ms == 1200 && view.has_breath &&
             view.breath_ms == 1300 && view.has_heart && view.heart_ms == 1400,
         "other metrics do not invent presence");

  observe(view, 1, true, 2000);
  mwcp_host::TelemetryShape yes = mwcp_host::telemetry_shape(view, 2500);
  expect(view.has_presence && view.presence && view.presence_ms == 2000 &&
             std::strcmp(yes.presence_value, "true") == 0 && std::strcmp(yes.presence_quality, "valid") == 0 &&
             yes.present && std::strcmp(yes.targets_quality, "valid") == 0,
         "real present keeps its timestamp");

  observe(view, 5, false, 2600, 15, 41);
  mwcp_host::TelemetryShape still = mwcp_host::telemetry_shape(view, 2600);
  expect(view.presence && view.presence_ms == 2000 && view.position_ms == 2600 && still.present &&
             std::strcmp(still.targets_quality, "valid") == 0,
         "later coordinates do not clear presence");

  observe(view, 1, false, 3000);
  mwcp_host::TelemetryShape no = mwcp_host::telemetry_shape(view, 3000);
  expect(view.has_presence && !view.presence && view.presence_ms == 3000 &&
             std::strcmp(no.presence_value, "false") == 0 && std::strcmp(no.targets_quality, "valid") == 0 &&
             !no.present,
         "real absent has no target");

  mwcp_host::RadarView again{};
  observe(again, 1, true, 4000);
  mwcp_host::TelemetryShape resumed = mwcp_host::telemetry_shape(again, 4000);
  expect(again.presence_ms == 4000 && std::strcmp(resumed.presence_quality, "valid") == 0,
         "a new boot view learns presence from a fresh sample");
}

static void test_refresh() {
  using esphome::r60abd1::kPresenceRefreshIntervalMs;
  using esphome::r60abd1::kPresenceRefreshSend;
  using esphome::r60abd1::kPresenceRefreshWait;
  using esphome::r60abd1::PresenceRefresh;
  using esphome::r60abd1::presence_refresh_note_sample;
  using esphome::r60abd1::presence_refresh_note_startup;
  using esphome::r60abd1::presence_refresh_poll;
  using esphome::r60abd1::write_presence_query;
  uint8_t frame[10];
  write_presence_query(frame);
  const uint8_t expected[10] = {0x53, 0x59, 0x80, 0x81, 0x00, 0x01, 0x0F, 0xBD, 0x54, 0x43};
  expect(std::memcmp(frame, expected, 10) == 0, "query frame matches manual V3.4 page 12");
  PresenceRefresh state;
  expect(presence_refresh_poll(state, 0) == kPresenceRefreshWait, "no query before init");
  state.initialized = true;
  state.wanted = true;
  expect(presence_refresh_poll(state, 500) == kPresenceRefreshWait, "startup query owns the first send");
  presence_refresh_note_startup(state, 400);
  expect(state.sent_count == 1, "startup query counted once");
  expect(presence_refresh_poll(state, 400 + kPresenceRefreshIntervalMs - 1) == kPresenceRefreshWait, "interval holds");
  expect(presence_refresh_poll(state, 400 + kPresenceRefreshIntervalMs) == kPresenceRefreshSend,
         "next query at the interval");
  expect(state.sent_count == 2, "second query counted");
  expect(presence_refresh_poll(state, 400 + kPresenceRefreshIntervalMs + 100) == kPresenceRefreshWait,
         "no burst while waiting");
  state.applying = true;
  expect(presence_refresh_poll(state, 400 + 2 * kPresenceRefreshIntervalMs) == kPresenceRefreshWait,
         "config write suppresses query");
  state.applying = false;
  state.wanted = false;
  expect(presence_refresh_poll(state, 400 + 2 * kPresenceRefreshIntervalMs) == kPresenceRefreshWait,
         "pure HA does not poll");
  state.wanted = true;
  const uint32_t wrapped = 0xFFFFFFF0u;
  presence_refresh_note_startup(state, wrapped);
  expect(presence_refresh_poll(state, 20) == kPresenceRefreshWait, "wraparound does not send early");
  expect(presence_refresh_poll(state, wrapped + kPresenceRefreshIntervalMs) == kPresenceRefreshSend,
         "wraparound sends on time");
}

static void test_same_value_advances() {
  using esphome::r60abd1::classify_presence_report;
  using esphome::r60abd1::kPresencePresent;
  mwcp_host::RadarView view{};
  const uint8_t present = 0x01;
  expect(classify_presence_report(0x81, &present, 1) == kPresencePresent, "unchanged somebody reply is legal");
  observe(view, 1, true, 1000, 10, 20);
  observe(view, 5, true, 9000, 11, 21);
  expect(view.presence_ms == 1000 && view.position_ms == 9000, "a new position does not refresh presence");
  expect(classify_presence_report(0x81, &present, 1) == kPresencePresent, "repeat reply still legal");
  observe(view, 1, true, 9500, 11, 21);
  expect(view.presence && view.presence_ms == 9500, "same presence value moves the sample time");
  const uint8_t junk = 0x0F;
  expect(classify_presence_report(0x81, &junk, 1) == esphome::r60abd1::kPresenceIgnore,
         "unknown payload is not a sample");
  expect(view.presence_ms == 9500, "ignored reply leaves the old sample");
  const uint8_t absent = 0x00;
  expect(classify_presence_report(0x81, &absent, 1) == esphome::r60abd1::kPresenceAbsent, "legal nobody reply");
  observe(view, 1, false, 9600);
  expect(!view.presence && view.presence_ms == 9600, "legal nobody is explicit");
}
int main() {
  test_classify();
  test_observer();
  test_refresh();
  test_same_value_advances();
  if (g_failed) {
    std::fprintf(stderr, "%d failed\n", g_failed);
    return 1;
  }
  std::printf("r60 presence query test passed\n");
  return 0;
}
