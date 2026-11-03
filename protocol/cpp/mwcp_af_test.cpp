#include "mwcp_link.h"

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

struct SplitStore {
  uint8_t cache[2][4096];
  uint8_t durable[2][4096];
  bool cache_set[2];
  bool durable_set[2];
  size_t len;
  bool fail_sync;
};
static bool split_load(void *user, int slot, uint8_t *dst, size_t len) {
  SplitStore *s = static_cast<SplitStore *>(user);
  if (!s->durable_set[slot] || s->len < len)
    return false;
  std::memcpy(dst, s->durable[slot], len);
  return true;
}
static bool split_store(void *user, int slot, const uint8_t *src, size_t len) {
  SplitStore *s = static_cast<SplitStore *>(user);
  if (len > sizeof(s->cache[0]))
    return false;
  std::memcpy(s->cache[slot], src, len);
  s->cache_set[slot] = true;
  s->len = len;
  return true;
}
static bool split_sync(void *user) {
  SplitStore *s = static_cast<SplitStore *>(user);
  if (s->fail_sync) {
    s->cache_set[0] = s->cache_set[1] = false;
    return false;
  }
  for (int i = 0; i < 2; i++)
    if (s->cache_set[i]) {
      std::memcpy(s->durable[i], s->cache[i], s->len);
      s->durable_set[i] = true;
      s->cache_set[i] = false;
    }
  return true;
}
static bool split_readback(void *user, int slot, uint8_t *dst, size_t len) { return split_load(user, slot, dst, len); }

struct Mem {
  bool present[2];
  uint8_t data[2][4096];
  size_t len[2];
  bool fail_store;
};
static bool mem_load(void *user, int slot, uint8_t *dst, size_t len) {
  Mem *m = static_cast<Mem *>(user);
  if (!m->present[slot] || m->len[slot] < len)
    return false;
  std::memcpy(dst, m->data[slot], len);
  return true;
}
static bool mem_store(void *user, int slot, const uint8_t *src, size_t len) {
  Mem *m = static_cast<Mem *>(user);
  if (m->fail_store)
    return false;
  std::memcpy(m->data[slot], src, len);
  m->len[slot] = len;
  m->present[slot] = true;
  return true;
}

static int g_published = 0;
static void on_publish(void *) { g_published++; }

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

int main() {
  Mem mem{};
  mwcp_host::Service svc;
  MwcpHostLink link;
  auto id = ident();
  svc.begin(id, "0123456789abcdef0123456789abcdef");
  mwcp_host::StoragePort storage{mem_load, mem_store, &mem, nullptr, nullptr};
  svc.set_storage(storage);
  svc.set_publish_hook(on_publish, nullptr);
  const char *hello = "{\"client\":{\"name\":\"mmwave-web-console\",\"version\":\"0.1.0\"},\"nonce\":"
                      "\"0123456789abcdef0123456789abcdef\","
                      "\"protocol\":{\"major\":1,\"minor_max\":0},\"max_payload\":4096}";
  expect(mwcp_dispatch_request(svc, link, 1000, 0, 1, 0x0001, reinterpret_cast<const uint8_t *>(hello),
                               std::strlen(hello)),
         "hello");
  uint32_t sid = svc.session_id();
  mem.fail_store = true;
  int z = 0;
  svc.config_z(&z);
  uint64_t rev = svc.revision_u64();
  expect(!svc.apply_ha_number("install.z_cm", 333, 100), "ha save fails");
  int z2 = 0;
  svc.config_z(&z2);
  expect(z2 == z && svc.revision_u64() == rev && g_published == 0, "failed ha write restores state");
  mem.fail_store = false;
  expect(svc.apply_ha_number("install.z_cm", 333, 200), "ha save ok");
  svc.config_z(&z2);
  expect(z2 == 333 && g_published == 1, "ha publish after persist");

  char out[1200];
  const char *bad_area = "{\"base_revision\":\"2\",\"changes\":{\"areas.definitions\":[{\"slot\":99,\"enabled\":true,"
                         "\"name\":\"a\",\"points_cm\":[]}]}}";
  expect(call(svc, link, 1500, sid, 3, 0x0021, bad_area, out, sizeof(out)), "area validate dispatched");
  expect(std::strstr(out, "INVALID_ARGUMENT") != nullptr, "slot 99 rejected");
  const char *ok_area = "{\"base_revision\":\"2\",\"op_id\":\"11111111-2222-3333-4444-555555555555\",\"changes\":{"
                        "\"areas.definitions\":[{\"slot\":0,\"enabled\":false,\"name\":\"off\",\"points_cm\":[]}]}}";
  expect(call(svc, link, 1600, sid, 4, 0x0022, ok_area, out, sizeof(out)), "disabled area commit");
  expect(std::strstr(out, "\"persisted\":true") != nullptr, "disabled area persisted");
  expect(svc.area_count() == 1, "area stored");

  int seen[8] = {0, 0, 0, 0, 0, 0, 0, 0};
  const char *names[] = {"install.x_cm",      "install.y_cm",     "install.z_cm",         "install.yaw_deg",
                         "install.pitch_deg", "install.roll_deg", "geometry.boundary_cm", "areas.definitions"};
  const char *cursor = nullptr;
  char body[80] = "{\"cursor\":null}";
  for (int page = 0; page < 6; page++) {
    expect(call(svc, link, 1700 + page, sid, static_cast<uint32_t>(10 + page), 0x0020, body, out, sizeof(out)),
           "config page");
    int hits = 0;
    for (int i = 0; i < 8; i++)
      if (std::strstr(out, names[i])) {
        seen[i]++;
        hits++;
      }
    expect(hits > 0 && hits <= 2, "page size");
    if (std::strstr(out, "\"next_cursor\":null")) {
      cursor = nullptr;
      break;
    }
    expect(std::strstr(out, "\"next_cursor\":\"cfg:") != nullptr, "cursor advances");
    const char *p = std::strstr(out, "cfg:");
    char next[64];
    int n = 0;
    while (p && *p && *p != '"' && n < 60)
      next[n++] = *p++;
    next[n] = 0;
    std::snprintf(body, sizeof(body), "{\"cursor\":\"%s\"}", next);
    cursor = body;
  }
  int total = 0;
  for (int i = 0; i < 8; i++)
    total += seen[i] == 1;
  expect(total == 8 && cursor == nullptr, "all eight config keys once");

  expect(call(svc, link, 1800, sid, 20, 0x0030,
              "{\"streams\":[{\"id\":\"telemetry\"},{\"id\":\"logs\"}],\"event_budget_bps\":8000}", out, sizeof(out)),
         "subscribe");
  expect(std::strstr(out, "telemetry") && std::strstr(out, "logs"), "subscribe echoes streams");
  expect(call(svc, link, 1900, sid, 21, 0x0031, "{\"streams\":[\"logs\"]}", out, sizeof(out)), "unsubscribe logs");
  expect(std::strstr(out, "logs") && std::strstr(out, "telemetry") == nullptr, "only logs removed");

  struct Wifi {
    int starts;
    bool fail_start;
  } wifi{};
  auto start_scan = [](void *user) -> mwcp_host::ScanStart {
    auto *w = static_cast<Wifi *>(user);
    w->starts++;
    return w->fail_start ? mwcp_host::ScanStart::kBusy : mwcp_host::ScanStart::kStarted;
  };
  auto poll_scan = [](void *, mwcp_host::WifiAp *outp, int cap, bool *truncated) {
    if (cap < 2)
      return 0;
    std::snprintf(outp[0].ssid, 33, "slow");
    outp[0].rssi = -80;
    std::snprintf(outp[0].auth, 12, "wpa2_psk");
    outp[0].hidden = false;
    std::snprintf(outp[1].ssid, 33, "fast");
    outp[1].rssi = -40;
    std::snprintf(outp[1].auth, 12, "open");
    outp[1].hidden = false;
    *truncated = false;
    return 2;
  };
  mwcp_host::WifiPort port{};
  port.start_scan = start_scan;
  port.poll_scan = poll_scan;
  port.user = &wifi;
  svc.set_wifi(port);
  expect(
      call(svc, link, 2000, sid, 30, 0x0051, "{\"op_id\":\"22222222-3333-4444-5555-666666666666\"}", out, sizeof(out)),
      "scan start");
  svc.poll(2001);
  expect(call(svc, link, 2100, sid, 31, 0x0053, "{\"job_id\":\"job-1\",\"cursor\":null}", out, sizeof(out)),
         "scan page");
  expect(std::strstr(out, "fast") && std::strstr(out, "slow"), "both APs returned");
  expect(std::strstr(out, "fast") < std::strstr(out, "slow"), "rssi sort");
  auto poll3 = [](void *, mwcp_host::WifiAp *outp, int, bool *truncated) {
    const char *names[] = {"c", "b", "a"};
    const int rssi[] = {-70, -50, -30};
    for (int i = 0; i < 3; i++) {
      std::snprintf(outp[i].ssid, 33, "%s", names[i]);
      outp[i].rssi = static_cast<int8_t>(rssi[i]);
      std::snprintf(outp[i].auth, 12, "open");
      outp[i].hidden = false;
    }
    *truncated = false;
    return 3;
  };
  port.poll_scan = poll3;
  svc.set_wifi(port);
  expect(
      call(svc, link, 2200, sid, 32, 0x0051, "{\"op_id\":\"33333333-3333-4444-5555-666666666666\"}", out, sizeof(out)),
      "scan3");
  const char *job = std::strstr(out, "job-");
  char job_id[16] = "";
  if (job) {
    int n = 0;
    while (job[n] && job[n] != '"' && n < 15) {
      job_id[n] = job[n];
      n++;
    }
    job_id[n] = 0;
  }
  svc.poll(2201);
  char page[80];
  std::snprintf(page, sizeof(page), "{\"job_id\":\"%s\",\"cursor\":null}", job_id);
  expect(call(svc, link, 2300, sid, 33, 0x0053, page, out, sizeof(out)), "scan page1");
  expect(std::strstr(out, "\"next_cursor\":\"2\"") != nullptr, "cursor is 2");
  std::snprintf(page, sizeof(page), "{\"job_id\":\"%s\",\"cursor\":\"2\"}", job_id);
  expect(call(svc, link, 2400, sid, 34, 0x0053, page, out, sizeof(out)), "scan page2");
  expect(std::strstr(out, "\"c\"") != nullptr && std::strstr(out, "\"next_cursor\":null") != nullptr,
         "second page is the third AP");

  SplitStore split{};
  mwcp_host::Service cold;
  cold.begin(id, "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa");
  mwcp_host::StoragePort split_port{split_load, split_store, &split, split_sync, split_readback};
  cold.set_storage(split_port);
  split.fail_sync = true;
  expect(!cold.apply_ha_number("install.z_cm", 400, 1), "sync failure");
  int z3 = 0;
  cold.config_z(&z3);
  expect(z3 != 400, "sync failure does not publish");

  uint64_t rev_before = svc.revision_u64();
  expect(svc.apply_ha_changes("{\"geometry.boundary_cm\":[[1,1],[2,1],[1,2]]}", 3000), "save triangle");
  expect(svc.apply_ha_changes("{\"geometry.boundary_cm\":[[100,100],[200,100],[100,200]]}", 3100), "replace triangle");
  int16_t xy[8];
  int bn = 0;
  svc.export_boundary(xy, &bn);
  expect(bn == 3 && xy[0] == 100 && svc.revision_u64() == rev_before + 2, "different points bump revision");
  mwcp_host::Service again;
  again.begin(id, "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb");
  again.set_storage(storage);
  again.load_storage();
  int16_t coldxy[8];
  int coldn = 0;
  again.export_boundary(coldxy, &coldn);
  expect(coldn == 3 && coldxy[0] == 100, "cold start keeps new triangle");
  const char *ops[] = {"aaaaaaaa-0000-4000-8000-000000000001", "aaaaaaaa-0000-4000-8000-000000000002",
                       "aaaaaaaa-0000-4000-8000-000000000003", "aaaaaaaa-0000-4000-8000-000000000004"};
  for (int i = 0; i < 4; i++) {
    char commit[180];
    std::snprintf(commit, sizeof(commit),
                  "{\"base_revision\":\"%s\",\"op_id\":\"%s\",\"changes\":{\"install.z_cm\":%d}}", svc.revision(),
                  ops[i], 100 + i);
    expect(call(svc, link, 3400 + i, sid, static_cast<uint32_t>(50 + i), 0x0022, commit, out, sizeof(out)),
           "ring fill");
  }
  expect(svc.has_commit(ops[0]), "oldest commit kept before overflow");
  mem.fail_store = true;
  char overflow[180];
  std::snprintf(overflow, sizeof(overflow),
                "{\"base_revision\":\"%s\",\"op_id\":\"aaaaaaaa-0000-4000-8000-000000000005\",\"changes\":{\"install.z_"
                "cm\":180}}",
                svc.revision());
  expect(call(svc, link, 3500, sid, 60, 0x0022, overflow, out, sizeof(out)), "overflow dispatched");
  expect(std::strstr(out, "STORAGE_FAILED") != nullptr && svc.has_commit(ops[0]) &&
             !svc.has_commit("aaaaaaaa-0000-4000-8000-000000000005"),
         "failed overflow restores commit ring");
  mem.fail_store = false;

  char cross[320];
  std::snprintf(cross, sizeof(cross),
                "{\"base_revision\":\"%s\",\"changes\":{\"areas.definitions\":[{\"slot\":1,\"enabled\":true,\"name\":"
                "\"x\",\"points_cm\":[[0,0],[100,100],[0,100],[100,0]]}]}}",
                svc.revision());
  expect(call(svc, link, 4200, sid, 70, 0x0021, cross, out, sizeof(out)), "cross dispatched");
  expect(std::strstr(out, "INVALID_ARGUMENT") != nullptr, "self-intersection rejected");
  expect(call(svc, link, 4300, sid, 71, 0x0030, "{\"streams\":[{\"id\":\"logs\"}],\"event_budget_bps\":8000}", out,
              sizeof(out)),
         "sub logs");
  svc.push_log_at("password=MARKER_SECRET", 42, "info");
  char ev[320];
  uint16_t evc = 0;
  expect(svc.next_event(ev, sizeof(ev), &evc), "log event");
  expect(std::strstr(ev, "MARKER_SECRET") == nullptr && std::strstr(ev, "<redacted>") != nullptr,
         "secret value removed");

  if (g_failed)
    return 1;
  std::printf("mwcp af test passed\n");
  return 0;
}
