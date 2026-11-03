#include "presence_sample.h"
#include "radar_observe.h"

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
  expect(view.has_presence && view.presence && view.presence_ms == 2000 && std::strcmp(yes.presence_value, "true") == 0 &&
             std::strcmp(yes.presence_quality, "valid") == 0 && yes.present &&
             std::strcmp(yes.targets_quality, "valid") == 0,
         "real present keeps its timestamp");

  observe(view, 5, false, 2600, 15, 41);
  mwcp_host::TelemetryShape still = mwcp_host::telemetry_shape(view, 2600);
  expect(view.presence && view.presence_ms == 2000 && view.position_ms == 2600 && still.present &&
             std::strcmp(still.targets_quality, "valid") == 0,
         "later coordinates do not clear presence");

  observe(view, 1, false, 3000);
  mwcp_host::TelemetryShape no = mwcp_host::telemetry_shape(view, 3000);
  expect(view.has_presence && !view.presence && view.presence_ms == 3000 && std::strcmp(no.presence_value, "false") == 0 &&
             std::strcmp(no.targets_quality, "valid") == 0 && !no.present,
         "real absent has no target");

  mwcp_host::RadarView again{};
  observe(again, 1, true, 4000);
  mwcp_host::TelemetryShape resumed = mwcp_host::telemetry_shape(again, 4000);
  expect(again.presence_ms == 4000 && std::strcmp(resumed.presence_quality, "valid") == 0,
         "a new boot view learns presence from a fresh sample");
}

int main() {
  test_classify();
  test_observer();
  if (g_failed) {
    std::fprintf(stderr, "%d failed\n", g_failed);
    return 1;
  }
  std::printf("r60 presence query test passed\n");
  return 0;
}
