// Background scan A -> component scan B lifecycle regression.
//
// The defect this test pins down: a background scan whose completion event is
// still queued when ESPHome's state machine times out (public state COOLDOWN)
// could be mistaken for a later component request, because the completion
// carried no identity and the component request had armed the only pending
// slot. B then published A's access points.
//
// The "legacy" half models the removed behaviour (background starts do not
// reserve, any pending component request absorbs the next event) and asserts
// that it reproduces the misattribution. The rest runs the production
// ScanCoordinator and ScanOwner, so a regression in the patch fails here.
#include "mwcp_wifi_adapter.h"
#include "wifi_scan_ownership.h"

#include <cstdio>
#include <cstring>

static int g_failed = 0;
static void expect(bool ok, const char *name) {
  if (!ok) {
    std::fprintf(stderr, "FAIL %s\n", name);
    g_failed++;
  }
}

struct Radio {
  int starts{0};
  int in_flight{0};
  int queued{0};
  mwcp_host::WifiAp ap[2]{};
  int n{0};
};

static void set_ap(Radio &radio, const char *ssid) {
  radio.n = 1;
  std::snprintf(radio.ap[0].ssid, sizeof(radio.ap[0].ssid), "%s", ssid);
  radio.ap[0].rssi = -40;
  std::snprintf(radio.ap[0].auth, sizeof(radio.ap[0].auth), "%s", "unknown");
  radio.ap[0].hidden = false;
}

/// Driver accepts at most one scan at a time. driver_complete() makes the
/// radio free again while leaving the SCAN_DONE event queued, which is the
/// state the bug depends on.
static bool radio_start(Radio &radio) {
  radio.starts++;
  if (radio.in_flight != 0)
    return false;
  radio.in_flight = 1;
  return true;
}

static void driver_complete(Radio &radio) {
  radio.in_flight = 0;
  radio.queued++;
}

static int radio_copy(void *user, mwcp_host::WifiAp *out, int cap, bool *truncated) {
  auto *radio = static_cast<Radio *>(user);
  if (truncated != nullptr)
    *truncated = false;
  int n = radio->n < cap ? radio->n : cap;
  for (int i = 0; i < n; i++)
    out[i] = radio->ap[i];
  return n;
}

// ── Legacy model: the removed behaviour, kept to prove the test can fail ────

struct Legacy {
  esphome::wifi::ScanOwnership gate;
  Radio radio;
};

static mwcp_host::ScanStart legacy_platform_start(void *user, uint32_t *generation) {
  auto *legacy = static_cast<Legacy *>(user);
  uint32_t gen = 0;
  if (!legacy->gate.begin(&gen))
    return mwcp_host::ScanStart::kBusy;
  if (!radio_start(legacy->radio)) {
    legacy->gate.cancel(gen);
    return mwcp_host::ScanStart::kBusy;
  }
  *generation = gen;
  return mwcp_host::ScanStart::kStarted;
}

// ── Current implementation ─────────────────────────────────────────────────

struct Current {
  esphome::wifi::ScanCoordinator coordinator;
  Radio radio;
  bool allowed{true};
};

static bool current_allowed(void *user) { return static_cast<Current *>(user)->allowed; }

static bool current_driver_start(void *user, bool) { return radio_start(static_cast<Current *>(user)->radio); }

static esphome::wifi::ScanHost current_host(Current &current) {
  return esphome::wifi::ScanHost{&current_allowed, &current_driver_start, &current};
}

static mwcp_host::ScanStart current_platform_start(void *user, uint32_t *generation) {
  auto *current = static_cast<Current *>(user);
  const esphome::wifi::ScanStartResult result =
      current->coordinator.start_component(current_host(*current), false, generation);
  return result == esphome::wifi::ScanStartResult::kStarted ? mwcp_host::ScanStart::kStarted
                                                            : mwcp_host::ScanStart::kBusy;
}

int main() {
  // 1. Legacy: A is started without an ownership reservation, its event is
  // queued, the state machine is in cooldown, and B is admitted. A's event is
  // then attributed to B.
  Legacy legacy;
  mwcp_host::ScanOwner legacy_owner;
  legacy_owner.configure(mwcp_host::ScanPlatform{legacy_platform_start, [](void *) {}, &legacy});
  expect(radio_start(legacy.radio), "legacy background A starts without a reservation");
  driver_complete(legacy.radio);
  set_ap(legacy.radio, "OLD_BACKGROUND_AP");
  expect(legacy_owner.start(1000) == mwcp_host::ScanStart::kStarted, "legacy component B starts");
  uint32_t taken = 0;
  expect(legacy.gate.take(&taken) == esphome::wifi::ScanOwner::kComponent,
         "legacy gate attributes the queued background event to B");
  legacy_owner.on_completion(taken, 0, 1, radio_copy, &legacy.radio);
  mwcp_host::WifiAp out[2]{};
  bool truncated = false;
  const int legacy_count = legacy_owner.poll(1010, out, 2, &truncated);
  expect(legacy_count == 1 && std::strcmp(out[0].ssid, "OLD_BACKGROUND_AP") == 0,
         "legacy bug reproduced: B publishes background A's access point");

  // 2. Current: the same ordering is refused. A still owns the radio in
  // cooldown, B cannot start, A's event is classified as background, and only
  // then can B start and return its own records.
  Current current;
  mwcp_host::ScanOwner owner;
  owner.configure(mwcp_host::ScanPlatform{current_platform_start, [](void *) {}, &current});
  expect(current.coordinator.start_background(current_host(current), false) == esphome::wifi::ScanStartResult::kStarted,
         "background A starts through the production coordinator");
  driver_complete(current.radio);
  // ESPHome's scan timeout moved the public state machine to COOLDOWN. No
  // state-machine transition touches the coordinator.
  expect(current.coordinator.in_flight(), "A still owns the radio after the scan timeout");
  expect(owner.start(1000) == mwcp_host::ScanStart::kBusy, "component B is refused while A is outstanding");
  expect(!current.coordinator.component_pending(), "the refused request left no component reservation");
  expect(owner.poll(1001, out, 2, &truncated) == -2, "no result is available for the refused request");

  set_ap(current.radio, "OLD_BACKGROUND_AP");
  uint32_t generation = 0;
  expect(current.coordinator.take_completion(&generation) == esphome::wifi::ScanOwner::kBackground,
         "A's queued completion is classified as background");
  const int waiting = owner.poll(1002, out, 2, &truncated);
  expect(waiting == -2 && !current.coordinator.in_flight(),
         "the background completion reaches no request and reopens the radio");

  set_ap(current.radio, "COMPONENT_B_AP");
  expect(owner.start(1003) == mwcp_host::ScanStart::kStarted, "component B starts after A is consumed");
  driver_complete(current.radio);
  expect(current.coordinator.take_completion(&generation) == esphome::wifi::ScanOwner::kComponent,
         "B's completion is classified as component");
  owner.on_completion(generation, 0, 1, radio_copy, &current.radio);
  const int current_count = owner.poll(1004, out, 2, &truncated);
  expect(current_count == 1 && std::strcmp(out[0].ssid, "COMPONENT_B_AP") == 0, "B returns only its own access point");

  // 3. Recovery paths must not permanently block scanning: a late background
  // completion after a scan timeout, a connect-failure retry, disable/enable,
  // and a failed roam all end with a usable radio.
  Current recovery;
  expect(
      recovery.coordinator.start_background(current_host(recovery), false) == esphome::wifi::ScanStartResult::kStarted,
      "connection scan A starts");
  driver_complete(recovery.radio);
  expect(recovery.coordinator.start_background(current_host(recovery), false) == esphome::wifi::ScanStartResult::kBusy,
         "a connect-failure retry waits for A's completion");
  expect(recovery.coordinator.take_completion(&generation) == esphome::wifi::ScanOwner::kBackground,
         "A's late completion is consumed as background");
  expect(
      recovery.coordinator.start_background(current_host(recovery), false) == esphome::wifi::ScanStartResult::kStarted,
      "the retry starts after A's completion");

  // Disable/enable during an outstanding scan: the gate is untouched by the
  // state change; the completion is background and the next request works.
  driver_complete(recovery.radio);
  expect(recovery.coordinator.start_component(current_host(recovery), false, &generation) ==
             esphome::wifi::ScanStartResult::kBusy,
         "component request during the outstanding retry is refused");
  expect(recovery.coordinator.take_completion(&generation) == esphome::wifi::ScanOwner::kBackground,
         "the retry's completion is background even after disable/enable");
  expect(recovery.coordinator.start_component(current_host(recovery), false, &generation) ==
             esphome::wifi::ScanStartResult::kStarted,
         "a component scan starts after disable/enable and the completion");

  // A failed roam refuses the component start before the driver, then recovers.
  Current roaming;
  roaming.allowed = false;
  expect(roaming.coordinator.start_component(current_host(roaming), false, &generation) ==
             esphome::wifi::ScanStartResult::kRefused,
         "component scan during a failed roam is refused");
  expect(roaming.radio.starts == 0, "the refusal happens before the driver call");
  roaming.allowed = true;
  expect(roaming.coordinator.start_component(current_host(roaming), false, &generation) ==
             esphome::wifi::ScanStartResult::kStarted,
         "component scan recovers after the roam");
  driver_complete(roaming.radio);
  expect(roaming.coordinator.take_completion(&generation) == esphome::wifi::ScanOwner::kComponent,
         "the recovered scan reports as component");

  if (g_failed) {
    std::fprintf(stderr, "mwcp scan lifecycle test failed %d\n", g_failed);
    return 1;
  }
  std::printf("mwcp scan lifecycle test passed\n");
  return 0;
}
