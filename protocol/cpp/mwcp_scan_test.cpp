#include "mwcp_link.h"
#include "mwcp_wifi_adapter.h"
#include "wifi_scan_ownership.h"

#include <cstdio>
#include <cstring>
#include <utility>
#include <vector>

static int g_failed = 0;
static void expect(bool ok, const char *name) {
  if (!ok) {
    std::fprintf(stderr, "FAIL %s\n", name);
    g_failed++;
  }
}

struct Mem {
  uint8_t data[2][4096];
  size_t len[2];
  bool present[2];
};
static bool mem_load(void *user, int slot, uint8_t *dst, size_t len) {
  Mem *m = static_cast<Mem *>(user);
  if (slot < 0 || slot > 1 || !m->present[slot] || m->len[slot] < len)
    return false;
  std::memcpy(dst, m->data[slot], len);
  return true;
}
static bool mem_store(void *user, int slot, const uint8_t *src, size_t len) {
  Mem *m = static_cast<Mem *>(user);
  if (slot < 0 || slot > 1 || len > sizeof(m->data[0]))
    return false;
  std::memcpy(m->data[slot], src, len);
  m->len[slot] = len;
  m->present[slot] = true;
  return true;
}

static mwcp_host::Identity ident() {
  mwcp_host::Identity id{};
  id.device_id = "dev";
  id.configured_model = "r60abd1";
  id.dimension = "2D";
  id.firmware_version = "test";
  id.git_sha = nullptr;
  id.release_channel = "development";
  id.build_profile = "host-test";
  id.cap_revision = "r60-cap-1";
  id.max_targets = 1;
  return id;
}

static bool call(mwcp_host::Service &svc, MwcpHostLink &link, uint32_t now, uint32_t sid, uint32_t req, uint16_t code,
                 const char *body, char *out, size_t cap) {
  for (int i = 0; i < 40 && (link.tx.active || link.control_ready); i++)
    link.pump([](const uint8_t *, size_t n) { return static_cast<int>(n); }, now);
  out[0] = 0;
  if (!mwcp_dispatch_request(svc, link, now, sid, req, code, reinterpret_cast<const uint8_t *>(body),
                             std::strlen(body)))
    return false;
  std::vector<uint8_t> sent;
  for (int i = 0; i < 40 && (link.tx.active || link.control_ready); i++) {
    link.pump(
        [&](const uint8_t *data, size_t n) {
          sent.insert(sent.end(), data, data + n);
          return static_cast<int>(n);
        },
        now);
  }
  mwcp::Parser parser;
  std::pair<char *, size_t> dst{out, cap};
  parser.push(
      sent.data(), sent.size(), now,
      [](const mwcp::Frame &frame, void *user) {
        auto *slot = static_cast<std::pair<char *, size_t> *>(user);
        size_t n = frame.payload_length < slot->second - 1 ? frame.payload_length : slot->second - 1;
        std::memcpy(slot->first, frame.payload, n);
        slot->first[n] = 0;
      },
      [](mwcp::Status, void *) {}, &dst);
  return out[0] == '{';
}

static uint32_t rehello(mwcp_host::Service &svc, MwcpHostLink &link, uint32_t now, uint32_t n) {
  char nonce[33];
  std::snprintf(nonce, sizeof(nonce), "%032x", n);
  char body[320];
  std::snprintf(body, sizeof(body),
                "{\"client\":{\"name\":\"mwcp-scan-test\",\"version\":\"0.1.0\"},\"nonce\":\"%s\","
                "\"protocol\":{\"major\":1,\"minor_max\":0},\"max_payload\":4096}",
                nonce);
  char out[2048];
  call(svc, link, now, 0, 90000 + n, 0x0001, body, out, sizeof(out));
  return svc.session_id();
}

/// Dependency state mirroring the patched WiFiComponent: the shared production
/// scan coordinator decides whether a start is accepted and which queued
/// completion belongs to the component, and the driver can refuse a start
/// after the reservation is taken.
struct Fake {
  bool disabled{false};
  bool roaming{false};
  bool driver_refuses{false};
  bool scan_in_progress{false};
  /// Public WiFi state machine: true while ESPHome believes it is scanning.
  /// It may be false (cooldown) while a scan is still outstanding.
  bool state_scanning{false};
  bool state_connecting{false};
  uint32_t now{0};
  int suppression{0};
  bool suppression_negative{false};
  int start_calls{0};
  int releases{0};
  int backgrounds{0};
  mwcp_host::WifiAp ap[4]{};
  int n{0};
  bool copy_available{true};
  int copies{0};
  int connects{0};
  bool persisted{false};
  int connect_result{0};
  char last_ssid[33]{};
  esphome::wifi::ScanCoordinator coordinator;
  mwcp_host::ScanOwner owner;
};

static bool fake_disabled(void *user) { return static_cast<Fake *>(user)->disabled; }
static bool fake_roaming(void *user) { return static_cast<Fake *>(user)->roaming; }
static void fake_suppress(void *user) { static_cast<Fake *>(user)->suppression++; }
static void fake_release(void *user) {
  auto *f = static_cast<Fake *>(user);
  f->suppression--;
  f->releases++;
  if (f->suppression < 0)
    f->suppression_negative = true;
}

/// Mirrors WiFiComponent::scan_component_allowed_().
static bool fake_component_allowed(void *user) {
  auto *f = static_cast<Fake *>(user);
  return !f->disabled && !f->roaming && !f->state_scanning && !f->state_connecting;
}

/// Mirrors WiFiComponent::scan_driver_start_(): called only with a reservation.
static bool fake_driver_start(void *user, bool) {
  auto *f = static_cast<Fake *>(user);
  f->start_calls++;
  if (f->driver_refuses || f->scan_in_progress)
    return false;
  f->scan_in_progress = true;
  return true;
}

static esphome::wifi::ScanHost fake_host(Fake &f) {
  return esphome::wifi::ScanHost{&fake_component_allowed, &fake_driver_start, &f};
}

/// Mirrors WiFiComponent::start_scanning() for connection, retry and roaming
/// scans: the coordinator owns every such start.
static bool fake_background_start(Fake &f) {
  const esphome::wifi::ScanStartResult result = f.coordinator.start_background(fake_host(f), false);
  f.state_scanning = true;
  f.state_connecting = false;
  return result == esphome::wifi::ScanStartResult::kStarted;
}

/// Mirrors WiFiComponent::start_scan_for_component().
static bool fake_component_start(void *user, uint32_t *generation) {
  auto *f = static_cast<Fake *>(user);
  return f->coordinator.start_component(fake_host(*f), false, generation) == esphome::wifi::ScanStartResult::kStarted;
}

static int fake_copy(void *user, mwcp_host::WifiAp *out, int cap, bool *truncated) {
  auto *f = static_cast<Fake *>(user);
  f->copies++;
  if (truncated)
    *truncated = false;
  if (!f->copy_available)
    return 0;
  int n = f->n < cap ? f->n : cap;
  for (int i = 0; i < n; i++)
    out[i] = f->ap[i];
  if (truncated)
    *truncated = f->n > cap;
  return n;
}

/// The real adapter entry production uses; injected with a fake dependency.
static mwcp_host::ScanStart fake_platform_start(void *user, uint32_t *generation) {
  auto *f = static_cast<Fake *>(user);
  mwcp_host::OwnedWifiApi api{};
  api.disabled = fake_disabled;
  api.roaming = fake_roaming;
  api.request_suppression = fake_suppress;
  api.release_suppression = fake_release;
  api.start = fake_component_start;
  api.user = f;
  return mwcp_host::acquire_owned_scan(api, generation);
}

static void fake_platform_finish(void *user) { fake_release(user); }

static int fake_poll(void *user, mwcp_host::WifiAp *out, int cap, bool *truncated) {
  auto *f = static_cast<Fake *>(user);
  return f->owner.poll(f->now, out, cap, truncated);
}

static bool fake_connect(void *user, const char *ssid, const char *, const char *) {
  auto *f = static_cast<Fake *>(user);
  f->connects++;
  std::snprintf(f->last_ssid, sizeof(f->last_ssid), "%s", ssid);
  return true;
}
static int fake_poll_connect(void *user, char *ip, size_t ip_cap, int *rssi) {
  auto *f = static_cast<Fake *>(user);
  if (f->connect_result <= 0)
    return f->connect_result;
  std::snprintf(ip, ip_cap, "%s", "10.0.0.8");
  *rssi = -48;
  return 1;
}
static bool fake_persist(void *user, const char *, const char *) {
  static_cast<Fake *>(user)->persisted = true;
  return true;
}
static bool fake_rollback(void *) { return true; }

static void set_aps(Fake &f, const char *const *names, int n) {
  f.n = n;
  for (int i = 0; i < n; i++) {
    std::snprintf(f.ap[i].ssid, sizeof(f.ap[i].ssid), "%s", names[i]);
    f.ap[i].rssi = static_cast<int8_t>(-40 - i);
    std::snprintf(f.ap[i].auth, sizeof(f.ap[i].auth), "%s", "unknown");
    f.ap[i].hidden = false;
  }
}

static void set_one(Fake &f, const char *name) {
  const char *names[1] = {name};
  set_aps(f, names, 1);
}

/// Process one completion exactly as the patched WiFiComponent does in the
/// main loop: the shared coordinator classifies the event by ownership, and
/// only a component completion's stored generation reaches the MWCP owner. A
/// background or unmatched completion is never attributed to a request.
static void deliver(Fake &f, uint32_t status, uint16_t number) {
  uint32_t generation = 0;
  const esphome::wifi::ScanOwner owner = f.coordinator.take_completion(&generation);
  f.scan_in_progress = false;
  f.state_scanning = false;
  if (owner != esphome::wifi::ScanOwner::kComponent) {
    f.backgrounds++;
    return;
  }
  f.owner.on_completion(generation, status, number, fake_copy, &f);
}

static void poll_service(mwcp_host::Service &svc, Fake &f, uint32_t now) {
  f.now = now;
  f.owner.tick(now);
  svc.poll(now);
}

static bool extract_job(const char *out, char *job, size_t job_cap) {
  const char *p = std::strstr(out, "\"job_id\":\"");
  if (!p)
    return false;
  p += 10;
  size_t n = 0;
  while (p[n] && p[n] != '"' && n + 1 < job_cap) {
    job[n] = p[n];
    n++;
  }
  job[n] = 0;
  return n > 0;
}

static bool start_scan(mwcp_host::Service &svc, Fake &f, MwcpHostLink &link, uint32_t sid, uint32_t req, uint32_t now,
                       const char *op_id, char *job, size_t job_cap) {
  f.now = now;
  char body[96];
  std::snprintf(body, sizeof(body), "{\"op_id\":\"%s\"}", op_id);
  char out[2048];
  if (!call(svc, link, now, sid, req, 0x0051, body, out, sizeof(out)))
    return false;
  return extract_job(out, job, job_cap);
}

static bool start_provision(mwcp_host::Service &svc, Fake &f, MwcpHostLink &link, uint32_t sid, uint32_t req,
                            uint32_t now, const char *op_id, const char *ssid, char *job, size_t job_cap, char *out,
                            size_t out_cap) {
  f.now = now;
  char body[192];
  std::snprintf(body, sizeof(body),
                "{\"op_id\":\"%s\",\"ssid\":\"%s\",\"auth\":\"wpa2_psk\",\"password\":\"secret123\"}", op_id, ssid);
  if (!call(svc, link, now, sid, req, 0x0052, body, out, out_cap))
    return false;
  return extract_job(out, job, job_cap);
}

static bool job_state(mwcp_host::Service &svc, MwcpHostLink &link, uint32_t sid, uint32_t req, uint32_t now,
                      const char *job, char *out, size_t cap) {
  char body[64];
  std::snprintf(body, sizeof(body), "{\"job_id\":\"%s\"}", job);
  return call(svc, link, now, sid, req, 0x0042, body, out, cap);
}

static bool scan_page(mwcp_host::Service &svc, MwcpHostLink &link, uint32_t sid, uint32_t req, uint32_t now,
                      const char *job, char *out, size_t cap) {
  char body[96];
  std::snprintf(body, sizeof(body), "{\"job_id\":\"%s\",\"cursor\":null}", job);
  return call(svc, link, now, sid, req, 0x0053, body, out, cap);
}

static bool has(const char *s, const char *needle) { return s != nullptr && std::strstr(s, needle) != nullptr; }

int main() {
  Mem mem{};
  mwcp_host::Service svc;
  MwcpHostLink link;
  svc.begin(ident(), "0123456789abcdef0123456789abcdef");
  mwcp_host::StoragePort storage{mem_load, mem_store, &mem, nullptr, nullptr};
  svc.set_storage(storage);
  const char *hello =
      "{\"client\":{\"name\":\"mwcp-scan-test\",\"version\":\"0.1.0\"},\"nonce\":\"0123456789abcdef0123456789abcdef\","
      "\"protocol\":{\"major\":1,\"minor_max\":0},\"max_payload\":4096}";
  if (!mwcp_dispatch_request(svc, link, 1000, 0, 1, 0x0001, reinterpret_cast<const uint8_t *>(hello),
                             std::strlen(hello)))
    return 1;
  uint32_t sid = svc.session_id();

  Fake f;
  mwcp_host::ScanPlatform platform{fake_platform_start, fake_platform_finish, &f};
  f.owner.configure(platform);
  mwcp_host::WifiPort port{};
  port.start_scan = [](void *user) {
    auto *self = static_cast<Fake *>(user);
    return self->owner.start(self->now);
  };
  port.poll_scan = fake_poll;
  port.start_connect = fake_connect;
  port.poll_connect = fake_poll_connect;
  port.persist = fake_persist;
  port.rollback = fake_rollback;
  port.user = &f;
  svc.set_wifi(port);

  uint32_t req = 10;
  char job[16]{};
  char out[2048]{};

  // 1. R1-A regression: A's completion is already queued when A's job times
  // out. The hold bound releases suppression only; the ownership gate stays
  // closed, so the next request is refused. Processing A's event then can
  // neither copy nor publish its records, and a request admitted afterwards
  // returns only its own results.
  set_one(f, "BACKGROUND_AP");
  deliver(f, 0, 1);
  expect(f.copies == 0 && f.backgrounds == 1, "a completion with no request is a background scan");

  set_one(f, "OLD_AP");
  expect(start_scan(svc, f, link, sid, req++, 2000, "11111111-1111-1111-1111-111111111111", job, sizeof(job)),
         "scan A accepted");
  expect(f.suppression == 1 && f.coordinator.component_pending(), "A holds the radio and the gate");
  poll_service(svc, f, 17000);
  expect(f.coordinator.component_pending(), "the job deadline passes with A's completion still queued");
  poll_service(svc, f, 62000);
  sid = rehello(svc, link, 62001, 96);
  expect(job_state(svc, link, sid, req++, 62002, job, out, sizeof(out)) && has(out, "\"state\":\"failed\"") &&
             has(out, "RADAR_TIMEOUT"),
         "scan A times out with its completion still queued");
  expect(f.suppression == 0 && f.coordinator.component_pending(),
         "the hold bound releases suppression but not ownership");
  expect(start_scan(svc, f, link, sid, req++, 62010, "22222222-2222-2222-2222-222222222222", job, sizeof(job)),
         "retry admitted as a job");
  expect(job_state(svc, link, sid, req++, 62011, job, out, sizeof(out)) && has(out, "RADAR_UNAVAILABLE"),
         "retry is refused while A's completion is unprocessed");

  set_one(f, "NEW_AP");
  deliver(f, 0, 1);
  expect(f.copies == 0, "A's late completion after the hold bound copies nothing");
  expect(!f.coordinator.component_pending(), "processing A's completion reopens the gate");
  expect(start_scan(svc, f, link, sid, req++, 62020, "33333333-3333-3333-3333-333333333333", job, sizeof(job)),
         "scan B accepted after the gate reopens");
  deliver(f, 0, 1);
  poll_service(svc, f, 62030);
  expect(job_state(svc, link, sid, req++, 62031, job, out, sizeof(out)) && has(out, "\"state\":\"succeeded\""),
         "B's own completion finishes the job");
  expect(scan_page(svc, link, sid, req++, 62032, job, out, sizeof(out)) && has(out, "NEW_AP") && !has(out, "OLD_AP"),
         "B returns only its own results");
  expect(f.copies == 1, "B's own completion copies exactly once");
  expect(f.suppression == 0, "B's completion releases the radio");
  deliver(f, 0, 1);
  expect(f.copies == 1 && f.backgrounds == 2, "a duplicate completion is a background event");

  // 2. ESPHome's own scan (reconnect or roaming) while MWCP asks: refused
  // before the radio is touched, or by the driver, but never raced.
  const int starts_before_roam = f.start_calls;
  f.roaming = true;
  expect(start_scan(svc, f, link, sid, req++, 63000, "44444444-4444-4444-4444-444444444444", job, sizeof(job)),
         "roaming request admits a job");
  expect(job_state(svc, link, sid, req++, 63001, job, out, sizeof(out)) && has(out, "\"state\":\"failed\"") &&
             has(out, "RADAR_UNAVAILABLE"),
         "roaming scan fails the job as unavailable");
  expect(f.start_calls == starts_before_roam, "roaming refusal happens before the driver call");
  f.roaming = false;

  f.scan_in_progress = true;
  expect(start_scan(svc, f, link, sid, req++, 63100, "55555555-5555-5555-5555-555555555555", job, sizeof(job)),
         "busy-radio request admits a job");
  expect(job_state(svc, link, sid, req++, 63101, job, out, sizeof(out)) && has(out, "RADAR_UNAVAILABLE"),
         "busy radio fails the job as unavailable");
  expect(f.start_calls == starts_before_roam + 1, "busy radio was refused by the start call");
  expect(f.suppression == 0, "refused starts release the radio");
  f.scan_in_progress = false;

  // 3. Driver-level refusal and disabled WiFi map to the real error paths; a
  // later accepted scan recovers. A disconnected station is not a refusal:
  // first-time provisioning must work while offline.
  f.driver_refuses = true;
  expect(start_scan(svc, f, link, sid, req++, 64000, "66666666-6666-6666-6666-666666666666", job, sizeof(job)),
         "driver refusal admits a job");
  expect(job_state(svc, link, sid, req++, 64001, job, out, sizeof(out)) && has(out, "RADAR_UNAVAILABLE") &&
             has(out, "\"message\":\"Radar is unavailable\""),
         "driver refusal fails with the structured error");
  expect(!f.coordinator.component_pending(), "driver refusal cancels the reserved ownership");
  f.driver_refuses = false;

  f.disabled = true;
  expect(start_scan(svc, f, link, sid, req++, 64100, "77777777-7777-7777-7777-777777777777", job, sizeof(job)),
         "disabled request admits a job");
  expect(job_state(svc, link, sid, req++, 64101, job, out, sizeof(out)) && has(out, "RADAR_UNAVAILABLE"),
         "disabled WiFi fails the job");
  f.disabled = false;

  set_one(f, "RECOVER_AP");
  expect(start_scan(svc, f, link, sid, req++, 64200, "88888888-8888-8888-8888-888888888888", job, sizeof(job)),
         "scan after refusals accepted");
  deliver(f, 0, 1);
  poll_service(svc, f, 64210);
  expect(scan_page(svc, link, sid, req++, 64211, job, out, sizeof(out)) && has(out, "RECOVER_AP"),
         "scan after refusals returns its own results");

  // 5. Timeout, then the timed-out request's late completion interleaved with
  // a refused retry: the late records must never answer the retry, and the
  // next request starts clean. The gap also lets the job table reclaim the
  // records from scenarios 1-3.
  sid = rehello(svc, link, 365500, 1);
  set_one(f, "SCAN_E_AP");
  expect(start_scan(svc, f, link, sid, req++, 366000, "99999999-9999-9999-9999-999999999999", job, sizeof(job)),
         "scan E accepted");
  poll_service(svc, f, 381000);
  sid = rehello(svc, link, 381001, 2);
  expect(job_state(svc, link, sid, req++, 381002, job, out, sizeof(out)) && has(out, "\"state\":\"failed\"") &&
             has(out, "RADAR_TIMEOUT"),
         "scan E times out");
  expect(f.copies == 2, "timeout does not copy");

  expect(start_scan(svc, f, link, sid, req++, 381100, "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa", job, sizeof(job)),
         "retry E admitted");
  expect(job_state(svc, link, sid, req++, 381101, job, out, sizeof(out)) && has(out, "RADAR_UNAVAILABLE"),
         "retry while the timed-out scan owns the radio is refused");
  set_one(f, "LATE_E_AP");
  deliver(f, 0, 1);
  expect(job_state(svc, link, sid, req++, 381103, job, out, sizeof(out)) && has(out, "\"state\":\"failed\""),
         "late E completion does not complete the refused retry");

  set_one(f, "SCAN_C_AP");
  expect(start_scan(svc, f, link, sid, req++, 381200, "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb", job, sizeof(job)),
         "scan C accepted");
  deliver(f, 0, 1);
  poll_service(svc, f, 381210);
  expect(scan_page(svc, link, sid, req++, 381211, job, out, sizeof(out)) && has(out, "SCAN_C_AP") &&
             !has(out, "LATE_E_AP"),
         "scan C returns only its own results");
  expect(f.suppression == 0, "late completion released the hold");

  // 6. Timeout with no completion at all: the gate stays closed past the hold
  // bound, the ultra-late completion is consumed without copying, and only
  // then can a fresh request start and succeed with its own data.
  expect(start_scan(svc, f, link, sid, req++, 382000, "cccccccc-cccc-cccc-cccc-cccccccccccc", job, sizeof(job)),
         "scan F accepted");
  poll_service(svc, f, 397000);
  sid = rehello(svc, link, 397001, 3);
  expect(job_state(svc, link, sid, req++, 397002, job, out, sizeof(out)) && has(out, "RADAR_TIMEOUT"),
         "scan F times out without a completion");
  expect(start_scan(svc, f, link, sid, req++, 397100, "dddddddd-dddd-dddd-dddd-dddddddddddd", job, sizeof(job)),
         "immediate retry admitted");
  expect(job_state(svc, link, sid, req++, 397101, job, out, sizeof(out)) && has(out, "RADAR_UNAVAILABLE"),
         "immediate retry is refused");
  poll_service(svc, f, 442001);
  expect(f.suppression == 0 && f.coordinator.component_pending(),
         "the hold bound releases suppression but the gate stays closed");
  sid = rehello(svc, link, 442002, 4);
  expect(start_scan(svc, f, link, sid, req++, 442002, "eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee", job, sizeof(job)),
         "retry past the hold bound admitted as a job");
  expect(job_state(svc, link, sid, req++, 442003, job, out, sizeof(out)) && has(out, "RADAR_UNAVAILABLE"),
         "the gate refuses the retry until F's event is processed");
  set_one(f, "ULTRA_LATE_AP");
  deliver(f, 0, 1);
  expect(f.copies == 4, "the ultra-late completion of the abandoned scan copies nothing");
  expect(!f.coordinator.component_pending(), "the ultra-late completion reopens the gate");
  set_one(f, "SCAN_H_AP");
  expect(start_scan(svc, f, link, sid, req++, 442005, "12345678-1234-1234-1234-123456789abc", job, sizeof(job)),
         "scan after the late completion accepted");
  deliver(f, 0, 1);
  poll_service(svc, f, 442010);
  expect(scan_page(svc, link, sid, req++, 442011, job, out, sizeof(out)) && has(out, "SCAN_H_AP") &&
             !has(out, "ULTRA_LATE_AP"),
         "fresh scan returns only its own results");

  // 7. Empty, identical, same-count-different and consecutive successes.
  sid = rehello(svc, link, 750000, 5);
  expect(start_scan(svc, f, link, sid, req++, 750100, "ffffffff-ffff-ffff-ffff-ffffffffffff", job, sizeof(job)),
         "empty scan accepted");
  const int copies_before_empty = f.copies;
  deliver(f, 0, 0);
  poll_service(svc, f, 750110);
  expect(job_state(svc, link, sid, req++, 750111, job, out, sizeof(out)) && has(out, "\"state\":\"succeeded\""),
         "empty scan succeeds");
  const bool empty_page = scan_page(svc, link, sid, req++, 750112, job, out, sizeof(out)) && has(out, "\"items\":[]");
  expect(empty_page, "empty scan publishes an empty list");
  expect(f.copies == copies_before_empty, "empty scan does not copy");

  set_one(f, "SAME_AP");
  expect(start_scan(svc, f, link, sid, req++, 751000, "11111111-2222-3333-4444-555555555555", job, sizeof(job)),
         "identical scan 1 accepted");
  deliver(f, 0, 1);
  poll_service(svc, f, 751010);
  expect(scan_page(svc, link, sid, req++, 751011, job, out, sizeof(out)) && has(out, "SAME_AP"),
         "identical scan 1 publishes SAME_AP");
  expect(start_scan(svc, f, link, sid, req++, 752000, "11111111-2222-3333-4444-666666666666", job, sizeof(job)),
         "identical scan 2 accepted");
  deliver(f, 0, 1);
  poll_service(svc, f, 752010);
  expect(scan_page(svc, link, sid, req++, 752011, job, out, sizeof(out)) && has(out, "SAME_AP"),
         "identical scan 2 is not filtered as a duplicate");
  set_one(f, "OTHER_AP");
  expect(start_scan(svc, f, link, sid, req++, 753000, "11111111-2222-3333-4444-777777777777", job, sizeof(job)),
         "same-count-different scan accepted");
  deliver(f, 0, 1);
  poll_service(svc, f, 753010);
  expect(
      scan_page(svc, link, sid, req++, 753011, job, out, sizeof(out)) && has(out, "OTHER_AP") && !has(out, "SAME_AP"),
      "same-count-different scan returns only its own results");

  // 8. A failed scan never publishes the previous scan's list, and a scan whose
  // records were lost after retrieval fails instead of succeeding empty.
  sid = rehello(svc, link, 760000, 6);
  set_one(f, "KEEP_AP");
  expect(start_scan(svc, f, link, sid, req++, 760100, "11111111-2222-3333-4444-888888888888", job, sizeof(job)),
         "baseline scan accepted");
  deliver(f, 0, 1);
  poll_service(svc, f, 760110);
  expect(scan_page(svc, link, sid, req++, 760111, job, out, sizeof(out)) && has(out, "KEEP_AP"), "baseline published");

  expect(start_scan(svc, f, link, sid, req++, 761000, "11111111-2222-3333-4444-999999999999", job, sizeof(job)),
         "failing scan accepted");
  deliver(f, 1, 0);
  poll_service(svc, f, 761010);
  expect(job_state(svc, link, sid, req++, 761011, job, out, sizeof(out)) && has(out, "\"state\":\"failed\"") &&
             has(out, "VERIFY_FAILED"),
         "driver failure fails the job");
  expect(scan_page(svc, link, sid, req++, 761012, job, out, sizeof(out)) && has(out, "\"items\":[]") &&
             !has(out, "KEEP_AP"),
         "driver failure does not publish the previous list");

  f.n = 2;
  f.copy_available = false;
  expect(start_scan(svc, f, link, sid, req++, 762000, "11111111-2222-3333-4444-aaaaaaaaaaaa", job, sizeof(job)),
         "records-lost scan accepted");
  deliver(f, 0, 2);
  poll_service(svc, f, 762010);
  expect(job_state(svc, link, sid, req++, 762011, job, out, sizeof(out)) && has(out, "\"state\":\"failed\"") &&
             has(out, "VERIFY_FAILED"),
         "records lost after a successful scan fails, not succeeds empty");
  expect(f.copies > 0, "the records-lost scan attempted a copy");
  expect(scan_page(svc, link, sid, req++, 762012, job, out, sizeof(out)) && has(out, "\"items\":[]"),
         "records-lost scan publishes nothing");
  f.copy_available = true;

  // 9. Timing across the uint32 millisecond wrap.
  sid = rehello(svc, link, 0xffffe000u, 7);
  set_one(f, "WRAP_AP");
  expect(start_scan(svc, f, link, sid, req++, 0xfffff000u, "11111111-2222-3333-4444-bbbbbbbbbbbb", job, sizeof(job)),
         "pre-wrap scan accepted");
  deliver(f, 0, 1);
  poll_service(svc, f, 0xfffff010u);
  expect(job_state(svc, link, sid, req++, 0xfffff011u, job, out, sizeof(out)) && has(out, "\"state\":\"succeeded\""),
         "pre-wrap scan succeeds");

  expect(start_scan(svc, f, link, sid, req++, 0xffffff00u, "11111111-2222-3333-4444-cccccccccccc", job, sizeof(job)),
         "wrapping scan accepted");
  poll_service(svc, f, 0xffffffffu);
  sid = rehello(svc, link, 0x00000100u, 8);
  expect(job_state(svc, link, sid, req++, 0x00000101u, job, out, sizeof(out)) && has(out, "\"state\":\"running\""),
         "the deadline does not fire just after the wrap");
  poll_service(svc, f, 0x00003997u);
  expect(job_state(svc, link, sid, req++, 0x00003998u, job, out, sizeof(out)) && has(out, "\"state\":\"running\""),
         "the deadline does not fire one millisecond early");
  poll_service(svc, f, 0x00003999u);
  sid = rehello(svc, link, 0x0000399au, 9);
  expect(job_state(svc, link, sid, req++, 0x0000399bu, job, out, sizeof(out)) && has(out, "\"state\":\"failed\"") &&
             has(out, "RADAR_TIMEOUT"),
         "the deadline fires once the wrapped interval elapses");
  poll_service(svc, f, 0x0000f000u);
  expect(f.suppression == 0, "the hold bound releases the wrapping scan across the wrap");

  // 9b. The 60 s provisioning deadline is also compared across the wrap: a
  // deadline that falls just before the wrap must not survive until the next
  // 49-day cycle.
  sid = rehello(svc, link, 0xffff0000u, 10);
  expect(start_provision(svc, f, link, sid, req++, 0xffff0000u, "15151515-1515-1515-1515-151515151515", "WRAP_HOME",
                         job, sizeof(job), out, sizeof(out)),
         "pre-wrap provision accepted");
  poll_service(svc, f, 0xffffea5fu);
  poll_service(svc, f, 0x00000100u);
  sid = rehello(svc, link, 0x00000100u, 11);
  expect(job_state(svc, link, sid, req++, 0x00000101u, job, out, sizeof(out)) && has(out, "\"state\":\"failed\"") &&
             has(out, "VERIFY_FAILED"),
         "the provisioning deadline fires just after the wrap");

  // 10. Stock ESPHome (no ownership API) fails wifi.scan with UNSUPPORTED
  // instead of guessing which scan a completion belongs to.
  Fake stock;
  stock.owner.configure(mwcp_host::ScanPlatform{nullptr, fake_platform_finish, &stock});
  mwcp_host::Service svc2;
  MwcpHostLink link2;
  svc2.begin(ident(), "0123456789abcdef0123456789abcdef");
  svc2.set_storage(storage);
  mwcp_host::WifiPort port2{};
  port2.start_scan = [](void *user) {
    auto *self = static_cast<Fake *>(user);
    return self->owner.start(self->now);
  };
  port2.poll_scan = fake_poll;
  port2.start_connect = fake_connect;
  port2.poll_connect = fake_poll_connect;
  port2.persist = fake_persist;
  port2.rollback = fake_rollback;
  port2.user = &stock;
  svc2.set_wifi(port2);
  uint32_t sid2 = rehello(svc2, link2, 1100, 10);
  char job2[16]{};
  expect(start_scan(svc2, stock, link2, sid2, req++, 1200, "11111111-2222-3333-4444-dddddddddddd", job2, sizeof(job2)),
         "stock request admits a job");
  expect(job_state(svc2, link2, sid2, req++, 1201, job2, out, sizeof(out)) && has(out, "\"state\":\"failed\"") &&
             has(out, "UNSUPPORTED"),
         "stock build fails wifi.scan with UNSUPPORTED");

  // 11. First-time setup from an offline device: scan, list access points,
  // provision, and report the connected result without any prior station
  // connection. Nothing in this flow may require a preset SSID.
  Mem mem3{};
  mwcp_host::StoragePort storage3{mem_load, mem_store, &mem3, nullptr, nullptr};
  mwcp_host::Service svc3;
  MwcpHostLink link3;
  svc3.begin(ident(), "0123456789abcdef0123456789abcdef");
  svc3.set_storage(storage3);
  Fake off;
  off.owner.configure(mwcp_host::ScanPlatform{fake_platform_start, fake_platform_finish, &off});
  mwcp_host::WifiPort port3{};
  port3.start_scan = [](void *user) {
    auto *self = static_cast<Fake *>(user);
    return self->owner.start(self->now);
  };
  port3.poll_scan = fake_poll;
  port3.start_connect = fake_connect;
  port3.poll_connect = fake_poll_connect;
  port3.persist = fake_persist;
  port3.rollback = fake_rollback;
  port3.user = &off;
  svc3.set_wifi(port3);
  uint32_t sid3 = rehello(svc3, link3, 1000, 11);

  set_one(off, "SETUP_AP");
  expect(start_scan(svc3, off, link3, sid3, req++, 1100, "12121212-1212-1212-1212-121212121212", job, sizeof(job)),
         "offline scan accepted");
  expect(off.connects == 0, "the scan starts with no station connection");
  deliver(off, 0, 1);
  poll_service(svc3, off, 1110);
  expect(scan_page(svc3, link3, sid3, req++, 1111, job, out, sizeof(out)) && has(out, "SETUP_AP"),
         "offline scan lists access points");

  expect(start_provision(svc3, off, link3, sid3, req++, 1200, "13131313-1313-1313-1313-131313131313", "HOME", job,
                         sizeof(job), out, sizeof(out)),
         "provision accepted from offline");
  expect(off.connects == 1 && std::strcmp(off.last_ssid, "HOME") == 0, "provision starts the new connection");
  expect(std::strcmp(svc3.wifi_state(), "connecting") == 0, "provision reports connecting");
  expect(!has(out, "secret123"), "the provision response does not echo the password");

  off.connect_result = 1;
  poll_service(svc3, off, 1300);
  expect(job_state(svc3, link3, sid3, req++, 1301, job, out, sizeof(out)) && has(out, "\"state\":\"succeeded\""),
         "provision job succeeds after the access point accepts");
  expect(std::strcmp(svc3.wifi_state(), "connected") == 0, "provision reports connected");
  expect(off.persisted, "provision persists the credentials");

  set_one(off, "AFTER_CONNECTED_AP");
  expect(start_scan(svc3, off, link3, sid3, req++, 1400, "14141414-1414-1414-1414-141414141414", job, sizeof(job)),
         "scan from a connected station is accepted");
  deliver(off, 0, 1);
  poll_service(svc3, off, 1410);
  expect(std::strcmp(svc3.wifi_state(), "connected") == 0, "a scan does not disconnect a connected station");
  expect(scan_page(svc3, link3, sid3, req++, 1411, job, out, sizeof(out)) && has(out, "AFTER_CONNECTED_AP"),
         "connected-station scan returns its own records");

  // 12. WP-2: a background scan A is still in flight after ESPHome's state
  // machine timed out and entered cooldown. The public state no longer says
  // SCANNING, but A still owns the radio. Component B must be refused; A's
  // late completion is consumed as background, and only then can B start and
  // return its own access points.
  Mem mem4{};
  mwcp_host::StoragePort storage4{mem_load, mem_store, &mem4, nullptr, nullptr};
  mwcp_host::Service svc4;
  MwcpHostLink link4;
  svc4.begin(ident(), "0123456789abcdef0123456789abcdef");
  svc4.set_storage(storage4);
  Fake bg;
  bg.owner.configure(mwcp_host::ScanPlatform{fake_platform_start, fake_platform_finish, &bg});
  mwcp_host::WifiPort port4{};
  port4.start_scan = [](void *user) {
    auto *self = static_cast<Fake *>(user);
    return self->owner.start(self->now);
  };
  port4.poll_scan = fake_poll;
  port4.start_connect = fake_connect;
  port4.poll_connect = fake_poll_connect;
  port4.persist = fake_persist;
  port4.rollback = fake_rollback;
  port4.user = &bg;
  svc4.set_wifi(port4);
  uint32_t sid4 = rehello(svc4, link4, 1000, 12);

  set_one(bg, "OLD_BACKGROUND_AP");
  expect(fake_background_start(bg), "background A holds the radio after the connection scan timeout");
  // ESPHome's scan timeout has already moved the public state to COOLDOWN; the
  // coordinator must still attribute A's outstanding completion to A.
  bg.state_scanning = false;
  expect(bg.coordinator.in_flight(), "A still owns the radio after the state machine left SCANNING");
  expect(start_scan(svc4, bg, link4, sid4, req++, 1010, "16161616-1616-1616-1616-161616161616", job, sizeof(job)),
         "component B job admitted while A is in flight");
  expect(job_state(svc4, link4, sid4, req++, 1011, job, out, sizeof(out)) && has(out, "\"state\":\"failed\"") &&
             has(out, "RADAR_UNAVAILABLE"),
         "B is refused while the timed-out background scan still owns the radio");
  expect(bg.copies == 0 && bg.coordinator.in_flight(), "B did not acquire A's ownership");

  deliver(bg, 0, 1);
  expect(bg.copies == 0 && bg.backgrounds == 1 && !bg.coordinator.in_flight(),
         "A's late completion is consumed as background without copying");
  set_one(bg, "B_AFTER_BACKGROUND_AP");
  expect(start_scan(svc4, bg, link4, sid4, req++, 1020, "17171717-1717-1717-1717-171717171717", job, sizeof(job)),
         "B is accepted only after A's completion");
  deliver(bg, 0, 1);
  poll_service(svc4, bg, 1030);
  expect(scan_page(svc4, link4, sid4, req++, 1031, job, out, sizeof(out)) && has(out, "B_AFTER_BACKGROUND_AP") &&
             !has(out, "OLD_BACKGROUND_AP"),
         "B returns only its own results after the background completion");
  expect(bg.copies == 1 && bg.suppression == 0, "B's completion is the only component copy");

  expect(f.suppression == 0 && !f.suppression_negative, "roaming suppression is balanced");
  expect(stock.suppression == 0 && !stock.suppression_negative, "stock build never touches the radio");
  expect(off.suppression == 0 && !off.suppression_negative, "offline provisioning leaves no hold");
  expect(bg.suppression == 0 && !bg.suppression_negative, "background-refusal suppression is balanced");

  if (g_failed) {
    std::fprintf(stderr, "mwcp scan test failed %d\n", g_failed);
    return 1;
  }
  std::printf("mwcp scan test passed\n");
  return 0;
}
