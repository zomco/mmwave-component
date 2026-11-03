#include "wifi_scan_ownership.h"

#include <cstdio>

static int g_failed = 0;
static void expect(bool ok, const char *name) {
  if (!ok) {
    std::fprintf(stderr, "FAIL %s\n", name);
    g_failed++;
  }
}

struct Driver {
  int calls{0};
  bool accept{true};
};

struct Host {
  bool allowed{true};
  Driver driver;
};

static bool driver_start(void *user, bool) {
  auto *host = static_cast<Host *>(user);
  host->driver.calls++;
  return host->driver.accept;
}

static bool host_allowed(void *user) { return static_cast<Host *>(user)->allowed; }

static esphome::wifi::ScanHost host_of(Host &host) {
  return esphome::wifi::ScanHost{&host_allowed, &driver_start, &host};
}

int main() {
  using esphome::wifi::ScanCoordinator;
  using esphome::wifi::ScanDriver;
  using esphome::wifi::ScanDriverResult;
  using esphome::wifi::ScanOrigin;
  using esphome::wifi::ScanOwner;
  using esphome::wifi::ScanOwnership;
  using esphome::wifi::ScanStartResult;
  using esphome::wifi::ScanTicket;
  using esphome::wifi::start_owned_scan;

  ScanOwnership gate;
  uint32_t gen = 0;
  uint32_t taken = 0;
  expect(!gate.pending() && !gate.in_flight() && gate.take(&taken) == ScanOwner::kNone,
         "idle gate has nothing to take");
  expect(gate.begin(&gen) && gen != 0 && gate.pending() && gate.in_flight(),
         "begin reserves exclusive ownership and marks a scan in flight");
  expect(gate.owns(gen) && !gate.owns(gen + 1), "only the reserved generation owns the radio");
  expect(gate.take(&taken) == ScanOwner::kComponent && taken == gen && !gate.pending() && !gate.in_flight(),
         "take returns the begin generation and releases the radio");
  expect(gate.take(&taken) == ScanOwner::kNone, "a completion is consumed exactly once");

  uint32_t a = 0;
  uint32_t b = 0;
  expect(gate.begin(&a), "request A owns the gate");
  expect(!gate.begin(&b), "request B is refused while A is pending");
  expect(gate.take(&taken) == ScanOwner::kComponent && taken == a, "the pending request keeps its own generation");
  expect(gate.begin(&b) && b != a, "generations advance across requests");
  expect(!gate.cancel(a) && gate.pending(), "a stale cancel cannot release a newer request");
  expect(gate.cancel(b) && !gate.pending() && !gate.in_flight() && gate.take(&taken) == ScanOwner::kNone,
         "cancel releases a refused request");

  expect(!gate.begin(nullptr), "a null generation is refused");
  expect(gate.take(nullptr) == ScanOwner::kNone && !gate.cancel(0), "null and zero arguments are refused");

  // Every scan entry shares the gate. A background scan whose state machine
  // timed out still blocks a component request until its completion is
  // processed, and that completion is consumed as background, not delivered.
  ScanOwnership coordinated;
  uint32_t component_gen = 0;
  expect(coordinated.begin_background(), "background scan reserves the radio");
  expect(coordinated.in_flight() && !coordinated.pending() && coordinated.owner() == ScanOwner::kBackground,
         "background scan has no component generation");
  expect(!coordinated.begin(&component_gen), "component request is refused while background scan is in flight");
  expect(coordinated.take(&taken) == ScanOwner::kBackground && !coordinated.in_flight() && !coordinated.pending(),
         "background completion consumes the reservation without a generation");
  expect(coordinated.begin(&component_gen) && component_gen != 0,
         "component request starts after background completion");
  expect(!coordinated.begin_background(), "background scan is refused while component request is in flight");
  expect(coordinated.take(&taken) == ScanOwner::kComponent && taken == component_gen,
         "component completion keeps its generation");
  expect(coordinated.begin_background(), "background scan starts after component completion");
  coordinated.cancel_background();
  expect(!coordinated.in_flight(), "refused background start releases the reservation");
  expect(coordinated.begin(&component_gen), "component request starts after refused background start");
  coordinated.cancel(component_gen);

  ScanOwnership cancel_background;
  expect(cancel_background.begin_background(), "background reservation for cancel test");
  cancel_background.cancel_background();
  expect(!cancel_background.in_flight() && !cancel_background.pending(), "background cancel clears ownership");

  // The driver choke point reserves before the driver is called, so a start
  // that reaches the driver always has an owner for its completion.
  Host host;
  const ScanDriver driver{driver_start, &host};
  ScanOwnership choke;
  expect(start_owned_scan(choke, driver, ScanTicket{ScanOrigin::kBackground, 0}, false) == ScanDriverResult::kStarted &&
             choke.in_flight() && host.driver.calls == 1,
         "background ticket reserves before the driver start");
  expect(start_owned_scan(choke, driver, ScanTicket{ScanOrigin::kBackground, 0}, false) == ScanDriverResult::kBusy &&
             host.driver.calls == 1,
         "a second start is refused before the driver is touched");
  expect(start_owned_scan(choke, driver, ScanTicket{ScanOrigin::kComponent, 0}, false) == ScanDriverResult::kBusy &&
             host.driver.calls == 1,
         "a component ticket without the reservation cannot start");
  choke.take(&taken);

  uint32_t choke_gen = 0;
  expect(choke.begin(&choke_gen), "reserve a component scan at the choke point");
  expect(start_owned_scan(choke, driver, ScanTicket{ScanOrigin::kComponent, choke_gen + 1}, false) ==
             ScanDriverResult::kBusy,
         "a stale component ticket is refused");
  expect(start_owned_scan(choke, driver, ScanTicket{ScanOrigin::kComponent, choke_gen}, false) ==
             ScanDriverResult::kStarted,
         "the reserved component ticket starts");
  choke.cancel(choke_gen);

  host.driver.accept = false;
  expect(start_owned_scan(choke, driver, ScanTicket{ScanOrigin::kBackground, 0}, false) == ScanDriverResult::kRefused &&
             !choke.in_flight(),
         "driver refusal after a background reservation releases it");

  // The coordinator is the lifecycle every WiFi scan entry uses.
  Host coord_host;
  ScanCoordinator coordinator;
  uint32_t coordinator_gen = 0;
  expect(coordinator.start_background(host_of(coord_host), false) == ScanStartResult::kStarted,
         "connection and roaming scans start through the coordinator");
  expect(coordinator.in_flight() && !coordinator.component_pending() && coordinator.starts() == 1,
         "a background start is recorded as in flight");
  expect(coordinator.start_component(host_of(coord_host), false, &coordinator_gen) == ScanStartResult::kBusy,
         "a component request is refused while a background scan is in flight");
  expect(coordinator.start_background(host_of(coord_host), false) == ScanStartResult::kBusy,
         "a second background scan is refused while one is in flight");
  expect(coordinator.take_completion(&gen) == ScanOwner::kBackground && coordinator.completions() == 1,
         "the background completion is classified as background");
  expect(coordinator.stray_completions() == 0, "a matched background completion is not stray");

  expect(coordinator.start_component(host_of(coord_host), false, &coordinator_gen) == ScanStartResult::kStarted &&
             coordinator_gen != 0 && coordinator.component_pending(),
         "a component scan starts after the background completion");
  expect(coordinator.take_completion(&gen) == ScanOwner::kComponent && gen == coordinator_gen,
         "the component completion carries its own generation");
  expect(coordinator.take_completion(&gen) == ScanOwner::kNone && coordinator.stray_completions() == 1,
         "a duplicate completion is classified as unmatched, never component");

  coord_host.allowed = false;
  const uint32_t calls_before = static_cast<uint32_t>(coord_host.driver.calls);
  expect(coordinator.start_component(host_of(coord_host), false, &coordinator_gen) == ScanStartResult::kRefused &&
             static_cast<uint32_t>(coord_host.driver.calls) == calls_before,
         "an unauthorized component request never reaches the driver");
  coord_host.allowed = true;

  coord_host.driver.accept = false;
  expect(coordinator.start_component(host_of(coord_host), false, &coordinator_gen) == ScanStartResult::kDriverRefused &&
             !coordinator.in_flight() && !coordinator.component_pending(),
         "a driver refusal cancels the component reservation");
  expect(coordinator.start_background(host_of(coord_host), false) == ScanStartResult::kDriverRefused &&
             !coordinator.in_flight(),
         "a driver refusal during a background start leaves nothing in flight");
  coord_host.driver.accept = true;
  expect(coordinator.start_component(host_of(coord_host), false, &coordinator_gen) == ScanStartResult::kStarted,
         "a refused driver does not strand later scans");

  ScanOwnership wrap(0xffffffffu);
  uint32_t g = 0;
  expect(wrap.begin(&g) && g == 1 && wrap.take(&g) == ScanOwner::kComponent && g == 1, "generation wrap skips zero");

  ScanOwnership edge(0xfffffffeu);
  expect(edge.begin(&g) && g == 0xffffffffu, "last representable generation");
  edge.take(&g);
  expect(edge.begin(&g) && g == 1, "the next generation wraps to one");
  expect(edge.take(&g) == ScanOwner::kComponent && g == 1, "the wrapped generation is taken exactly");

  if (g_failed) {
    std::fprintf(stderr, "mwcp scan gate test failed %d\n", g_failed);
    return 1;
  }
  std::printf("mwcp scan gate test passed\n");
  return 0;
}
