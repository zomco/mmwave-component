#include "mwcp_link.h"
#include "mwcp_service.h"

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

struct Captured {
  char json[4096];
  uint32_t request_id;
  uint16_t code;
  uint32_t session_id;
  bool saw;
  std::vector<uint8_t> wire;
};

static void clear(Captured *cap) {
  cap->json[0] = 0;
  cap->request_id = 0;
  cap->code = 0;
  cap->session_id = 0;
  cap->saw = false;
  cap->wire.clear();
}

static void pump_done(MwcpHostLink &link, uint32_t now) {
  for (int i = 0; i < 80 && (link.tx.active || link.control_ready); i++)
    link.pump([](const uint8_t *, size_t n) { return static_cast<int>(n); }, now);
}

static void decode_one(const std::vector<uint8_t> &wire, uint32_t now, Captured *cap) {
  cap->json[0] = 0;
  cap->saw = false;
  mwcp::Parser parser;
  parser.push(
      wire.data(), wire.size(), now,
      [](const mwcp::Frame &frame, void *user) {
        auto *slot = static_cast<Captured *>(user);
        if (slot->saw)
          return;
        slot->saw = true;
        slot->request_id = frame.request_id;
        slot->code = frame.code;
        slot->session_id = frame.session_id;
        size_t n = frame.payload_length < sizeof(slot->json) - 1 ? frame.payload_length : sizeof(slot->json) - 1;
        std::memcpy(slot->json, frame.payload, n);
        slot->json[n] = 0;
      },
      [](mwcp::Status, void *) {}, cap);
}

static bool request(mwcp_host::Service &svc, MwcpHostLink &link, uint32_t now, uint32_t sid, uint32_t req,
                    uint16_t code, const char *body, Captured *cap) {
  pump_done(link, now);
  clear(cap);
  if (!mwcp_dispatch_request(svc, link, now, sid, req, code, reinterpret_cast<const uint8_t *>(body),
                             std::strlen(body)))
    return false;
  for (int i = 0; i < 80 && (link.tx.active || link.control_ready); i++) {
    link.pump(
        [&](const uint8_t *data, size_t n) {
          cap->wire.insert(cap->wire.end(), data, data + n);
          return static_cast<int>(n);
        },
        now);
  }
  decode_one(cap->wire, now, cap);
  return cap->saw && cap->request_id == req && cap->code == code;
}

static bool has(const char *s, const char *needle) { return s != nullptr && std::strstr(s, needle) != nullptr; }

static bool capture_event(mwcp_host::Service &svc, MwcpHostLink &link, uint32_t now, const char *job, const char *state,
                          Captured *cap) {
  for (int tries = 0; tries < 12; tries++) {
    pump_done(link, now);
    if (!link.event_ready) {
      if (mwcp_forward_events(svc, link) != 1)
        return false;
    }
    clear(cap);
    for (int i = 0; i < 80 && (link.tx.active || link.event_ready); i++) {
      link.pump(
          [&](const uint8_t *data, size_t n) {
            cap->wire.insert(cap->wire.end(), data, data + n);
            return static_cast<int>(n);
          },
          now);
    }
    decode_one(cap->wire, now, cap);
    if (!cap->saw || cap->code != 0x8004)
      continue;
    if (job != nullptr) {
      char needle[64];
      std::snprintf(needle, sizeof(needle), "\"job_id\":\"%s\"", job);
      if (!has(cap->json, needle))
        continue;
    }
    if (state != nullptr) {
      char needle[48];
      std::snprintf(needle, sizeof(needle), "\"state\":\"%s\"", state);
      if (!has(cap->json, needle))
        continue;
    }
    return true;
  }
  return false;
}

static uint32_t hello(mwcp_host::Service &svc, MwcpHostLink &link, uint32_t now, uint32_t req, uint32_t n) {
  char nonce[33];
  std::snprintf(nonce, sizeof(nonce), "%032x", n);
  char body[320];
  std::snprintf(body, sizeof(body),
                "{\"client\":{\"name\":\"mwcp-job-test\",\"version\":\"0.1.0\"},\"nonce\":\"%s\","
                "\"protocol\":{\"major\":1,\"minor_max\":0},\"max_payload\":4096}",
                nonce);
  Captured cap{};
  expect(request(svc, link, now, 0, req, 0x0001, body, &cap), "hello");
  return svc.session_id();
}

static void subscribe_rate(mwcp_host::Service &svc, MwcpHostLink &link, uint32_t now, uint32_t sid, uint32_t req,
                           int hz) {
  char body[128];
  std::snprintf(body, sizeof(body), "{\"streams\":[{\"id\":\"jobs\",\"max_rate_hz\":%d}],\"event_budget_bps\":8000}",
                hz);
  Captured cap{};
  expect(request(svc, link, now, sid, req, 0x0030, body, &cap), "jobs subscription");
}

static void subscribe(mwcp_host::Service &svc, MwcpHostLink &link, uint32_t now, uint32_t sid, uint32_t req) {
  subscribe_rate(svc, link, now, sid, req, 20);
}

static bool job_get(mwcp_host::Service &svc, MwcpHostLink &link, uint32_t now, uint32_t sid, uint32_t req,
                    const char *job, Captured *cap) {
  char body[96];
  std::snprintf(body, sizeof(body), "{\"job_id\":\"%s\"}", job);
  return request(svc, link, now, sid, req, 0x0042, body, cap);
}

static bool start_scan(mwcp_host::Service &svc, MwcpHostLink &link, uint32_t now, uint32_t sid, uint32_t req,
                       const char *op, char *job, size_t cap) {
  char body[96];
  std::snprintf(body, sizeof(body), "{\"op_id\":\"%s\"}", op);
  Captured out{};
  if (!request(svc, link, now, sid, req, 0x0051, body, &out))
    return false;
  const char *p = std::strstr(out.json, "\"job_id\":\"");
  if (p == nullptr)
    return false;
  p += 10;
  size_t n = 0;
  while (p[n] && p[n] != '"' && n + 1 < cap) {
    job[n] = p[n];
    n++;
  }
  job[n] = 0;
  return n > 0;
}

static bool start_action(mwcp_host::Service &svc, MwcpHostLink &link, uint32_t now, uint32_t sid, uint32_t req,
                         const char *op, char *job, size_t cap) {
  char body[192];
  std::snprintf(
      body, sizeof(body),
      "{\"action_id\":\"radar.reset_module\",\"op_id\":\"%s\",\"params\":{},\"confirm\":\"radar.reset_module\"}", op);
  Captured out{};
  if (!request(svc, link, now, sid, req, 0x0041, body, &out))
    return false;
  const char *p = std::strstr(out.json, "\"job_id\":\"");
  if (p == nullptr)
    return false;
  p += 10;
  size_t n = 0;
  while (p[n] && p[n] != '"' && n + 1 < cap) {
    job[n] = p[n];
    n++;
  }
  job[n] = 0;
  return n > 0;
}

static bool provision(mwcp_host::Service &svc, MwcpHostLink &link, uint32_t now, uint32_t sid, uint32_t req,
                      const char *op, char *job, size_t cap) {
  char body[192];
  std::snprintf(body, sizeof(body),
                "{\"op_id\":\"%s\",\"ssid\":\"Lab\",\"auth\":\"wpa2_psk\",\"password\":\"password123\"}", op);
  Captured out{};
  if (!request(svc, link, now, sid, req, 0x0052, body, &out))
    return false;
  const char *p = std::strstr(out.json, "\"job_id\":\"");
  if (p == nullptr)
    return false;
  p += 10;
  size_t n = 0;
  while (p[n] && p[n] != '"' && n + 1 < cap) {
    job[n] = p[n];
    n++;
  }
  job[n] = 0;
  return n > 0;
}

struct Wifi {
  mwcp_host::ScanStart start_result{mwcp_host::ScanStart::kStarted};
  int poll_result{-1};
  bool persist_ok{true};
  mwcp_host::WifiAp ap{};
};

static mwcp_host::ScanStart wifi_start_scan(void *user) { return static_cast<Wifi *>(user)->start_result; }
static int wifi_poll_scan(void *user, mwcp_host::WifiAp *out, int cap, bool *truncated) {
  auto *w = static_cast<Wifi *>(user);
  if (truncated)
    *truncated = false;
  if (w->poll_result < 0 || cap < 1)
    return w->poll_result;
  out[0] = w->ap;
  return w->poll_result;
}
static bool wifi_start_connect(void *, const char *, const char *, const char *) { return true; }
static int wifi_poll_connect(void *, char *ip, size_t cap, int *rssi) {
  std::snprintf(ip, cap, "%s", "192.168.1.50");
  *rssi = -42;
  return 1;
}
static bool wifi_persist(void *user, const char *, const char *) { return static_cast<Wifi *>(user)->persist_ok; }
static bool wifi_rollback(void *) { return true; }

static int g_reset_rc = 0;
static int reset_hook(void *) { return g_reset_rc; }

static void pair(const Captured &event, const Captured &response) {
  std::printf("JOBPAIR ");
  for (uint8_t b : event.wire)
    std::printf("%02x", b);
  std::printf(" ");
  for (uint8_t b : response.wire)
    std::printf("%02x", b);
  std::printf("\n");
}

int main() {
  mwcp_host::Service svc;
  MwcpHostLink link;
  svc.begin(ident(), "0123456789abcdef0123456789abcdef");

  Wifi wifi{};
  mwcp_host::WifiPort port{wifi_start_scan, wifi_poll_scan, wifi_start_connect, wifi_poll_connect, wifi_persist,
                           wifi_rollback,   &wifi};
  svc.set_wifi(port);
  svc.set_radar_action(reset_hook, nullptr);

  uint32_t sid = hello(svc, link, 1000, 1, 1);
  subscribe(svc, link, 1100, sid, 2);

  uint32_t req = 10;
  char job[16]{};
  Captured event{};
  Captured response{};

  // Running and succeeded events for a successful scan.
  std::snprintf(wifi.ap.ssid, sizeof(wifi.ap.ssid), "%s", "LAB_AP");
  wifi.ap.rssi = -40;
  std::snprintf(wifi.ap.auth, sizeof(wifi.ap.auth), "%s", "unknown");
  wifi.poll_result = 1;
  expect(start_scan(svc, link, 2000, sid, req++, "11111111-1111-1111-1111-111111111111", job, sizeof(job)),
         "successful scan accepted");
  expect(capture_event(svc, link, 2000, job, "running", &event) && has(event.json, "\"state\":\"running\""),
         "running JOB_CHANGED is emitted");
  std::printf("WIRE event ");
  for (uint8_t b : event.wire)
    std::printf("%02x", b);
  std::printf("\n");
  expect(event.json[0] == '{' && has(event.json, "\"op_id\":\"11111111-1111-1111-1111-111111111111\"") &&
             has(event.json, "\"action_id\":\"wifi.scan\"") && has(event.json, "\"progress\":null"),
         "running event carries the complete job");
  expect(job_get(svc, link, 2010, sid, req++, job, &response) && has(response.json, "\"state\":\"running\"") &&
             has(response.json, "\"error\":null"),
         "JOB_GET matches the running event");
  pair(event, response);

  svc.poll(2100);
  expect(capture_event(svc, link, 2110, job, "succeeded", &event) && has(event.json, "\"state\":\"succeeded\""),
         "succeeded JOB_CHANGED is emitted");
  expect(
      has(event.json, "\"result\":{\"verified\":false,\"verification\":\"none\"}") && has(event.json, "\"error\":null"),
      "succeeded event has result and no error");
  expect(job_get(svc, link, 2120, sid, req++, job, &response) && has(response.json, "\"state\":\"succeeded\"") &&
             has(response.json, "\"finished_ms\":2100") && has(response.json, "\"error\":null"),
         "JOB_GET matches the succeeded event");
  pair(event, response);

  // Start refusal: the job is admitted and then failed with RADAR_UNAVAILABLE.
  wifi.start_result = mwcp_host::ScanStart::kBusy;
  expect(start_scan(svc, link, 3000, sid, req++, "22222222-2222-2222-2222-222222222222", job, sizeof(job)),
         "refused scan admitted");
  expect(job_get(svc, link, 3100, sid, req++, job, &response) && has(response.json, "\"state\":\"failed\"") &&
             has(response.json, "\"code\":\"RADAR_UNAVAILABLE\"") &&
             has(response.json, "\"message\":\"Radar is unavailable\"") && has(response.json, "\"result\":null"),
         "start refusal reports RADAR_UNAVAILABLE in JOB_GET");

  // Unsupported start: this build cannot own scans; say so instead of guessing.
  wifi.start_result = mwcp_host::ScanStart::kUnsupported;
  expect(start_scan(svc, link, 3200, sid, req++, "23232323-2323-2323-2323-232323232323", job, sizeof(job)),
         "unsupported scan admitted");
  expect(job_get(svc, link, 3300, sid, req++, job, &response) && has(response.json, "\"state\":\"failed\"") &&
             has(response.json, "\"code\":\"UNSUPPORTED\"") &&
             has(response.json, "\"message\":\"Unsupported operation\"") && has(response.json, "\"result\":null"),
         "unsupported start reports UNSUPPORTED in JOB_GET");
  wifi.start_result = mwcp_host::ScanStart::kStarted;

  // Radio failure: the bridge reports a failed completion.
  wifi.poll_result = -2;
  expect(start_scan(svc, link, 4000, sid, req++, "33333333-3333-3333-3333-333333333333", job, sizeof(job)),
         "radio-failure scan admitted");
  expect(capture_event(svc, link, 4000, job, "running", &event) && has(event.json, "\"state\":\"running\""),
         "radio-failure running event is emitted");
  svc.poll(4200);
  expect(capture_event(svc, link, 4210, job, "failed", &event) && has(event.json, "\"state\":\"failed\"") &&
             has(event.json, "\"code\":\"VERIFY_FAILED\"") && !has(event.json, "\"verified\":true"),
         "radio failure event has a structured error");
  expect(job_get(svc, link, 4220, sid, req++, job, &response) && has(response.json, "\"code\":\"VERIFY_FAILED\"") &&
             has(response.json, "\"finished_ms\":4200,"),
         "JOB_GET exposes the radio failure reason");
  pair(event, response);

  // Scan timeout: keep the session alive across the deadline, then fail.
  wifi.poll_result = -1;
  expect(start_scan(svc, link, 5000, sid, req++, "44444444-4444-4444-4444-444444444444", job, sizeof(job)),
         "timeout scan admitted");
  expect(capture_event(svc, link, 5000, job, "running", &event) && has(event.json, "\"state\":\"running\""),
         "timeout scan running event is emitted");
  sid = hello(svc, link, 20000, req++, 2);
  subscribe(svc, link, 20001, sid, req++);
  svc.poll(20002);
  expect(capture_event(svc, link, 20003, job, "failed", &event) && has(event.json, "\"state\":\"failed\"") &&
             has(event.json, "\"code\":\"RADAR_TIMEOUT\""),
         "timeout event carries RADAR_TIMEOUT");
  expect(job_get(svc, link, 20004, sid, req++, job, &response) && has(response.json, "\"code\":\"RADAR_TIMEOUT\"") &&
             has(response.json, "\"message\":\"Radar operation timed out\""),
         "JOB_GET exposes the timeout reason");
  pair(event, response);

  // Successful reset: the action runs synchronously, so the terminal event is
  // coalesced by the jobs stream rate; JOB_GET is the recovery path for the
  // final state (the running event still goes out).
  g_reset_rc = 0;
  const uint32_t reset_drops = svc.unsent_events();
  expect(start_action(svc, link, 20100, sid, req++, "55555555-5555-5555-5555-555555555555", job, sizeof(job)),
         "reset action admitted");
  expect(svc.unsent_events() == reset_drops + 1, "synchronous reset coalesces its terminal event");
  expect(job_get(svc, link, 20110, sid, req++, job, &response) && has(response.json, "\"state\":\"succeeded\"") &&
             has(response.json, "\"result\":{\"verified\":false,\"verification\":\"none\"}") &&
             has(response.json, "\"error\":null"),
         "reset success is visible through JOB_GET");

  // Failed reset: structured RADAR_UNAVAILABLE with a null result.
  g_reset_rc = -1;
  expect(start_action(svc, link, 20200, sid, req++, "66666666-6666-6666-6666-666666666666", job, sizeof(job)),
         "failed reset admitted");
  svc.poll(20201);
  expect(job_get(svc, link, 20202, sid, req++, job, &response) && has(response.json, "\"state\":\"failed\"") &&
             has(response.json, "\"code\":\"RADAR_UNAVAILABLE\"") && has(response.json, "\"result\":null"),
         "failed reset exposes the cause");

  // Storage failure during provisioning: event and JOB_GET agree.
  wifi.persist_ok = false;
  expect(provision(svc, link, 20300, sid, req++, "77777777-7777-7777-7777-777777777777", job, sizeof(job)),
         "provision admitted");
  svc.poll(20400);
  expect(capture_event(svc, link, 20410, job, "failed", &event) && has(event.json, "\"state\":\"failed\"") &&
             has(event.json, "\"code\":\"STORAGE_FAILED\""),
         "provision storage failure event");
  sid = hello(svc, link, 80400, req++, 3);
  subscribe(svc, link, 80401, sid, req++);
  expect(job_get(svc, link, 80404, sid, req++, job, &response) && has(response.json, "\"code\":\"STORAGE_FAILED\"") &&
             has(response.json, "\"message\":\"Storage operation failed\""),
         "JOB_GET exposes the storage failure");
  pair(event, response);

  // Unknown job: contract summary, no invented error.
  expect(job_get(svc, link, 80410, sid, req++, "job-999", &response) && has(response.json, "\"state\":\"unknown\"") &&
             has(response.json, "\"error\":null") && has(response.json, "\"finished_ms\":null"),
         "unknown job is a null summary");

  // A terminal event dropped by the jobs stream rate is still recoverable:
  // JOB_GET is the ground truth when the event stream coalesces. The gap also
  // lets the job table reclaim the records from the earlier sections.
  sid = hello(svc, link, 400000, req++, 4);
  subscribe_rate(svc, link, 400001, sid, req++, 1);
  const uint32_t dropped_before = svc.unsent_events();
  wifi.start_result = mwcp_host::ScanStart::kBusy;
  expect(start_scan(svc, link, 400100, sid, req++, "88888888-8888-8888-8888-888888888888", job, sizeof(job)),
         "throttled refusal scan admitted");
  expect(capture_event(svc, link, 400100, job, "running", &event) && has(event.json, "\"state\":\"running\""),
         "throttled running event is delivered");
  expect(!capture_event(svc, link, 400100, job, "failed", &event), "the throttled terminal event is not delivered");
  expect(svc.unsent_events() > dropped_before, "the throttled terminal event was dropped, not queued");
  expect(job_get(svc, link, 400110, sid, req++, job, &response) && has(response.json, "\"state\":\"failed\"") &&
             has(response.json, "\"code\":\"RADAR_UNAVAILABLE\""),
         "JOB_GET recovers the rate-limited terminal state");
  wifi.start_result = mwcp_host::ScanStart::kStarted;

  if (g_failed) {
    std::fprintf(stderr, "mwcp job test failed %d\n", g_failed);
    return 1;
  }
  std::printf("mwcp job test passed\n");
  return 0;
}
