#include "mwcp_service.h"

#include <cstdio>
#include <cstring>

static int g_failed = 0;

static void expect(bool ok, const char *name) {
  if (!ok) {
    std::fprintf(stderr, "FAIL %s\n", name);
    g_failed++;
  }
}

struct MemStore {
  bool present[2];
  uint8_t data[2][4096];
  size_t len[2];
  bool fail_store;
  int corrupt;
};

static bool mem_load(void *user, int slot, uint8_t *dst, size_t len) {
  MemStore *m = static_cast<MemStore *>(user);
  if (slot < 0 || slot > 1 || !m->present[slot] || m->len[slot] < len)
    return false;
  std::memcpy(dst, m->data[slot], len);
  if (m->corrupt == slot + 1)
    dst[16] ^= 0xff;
  return true;
}

static bool mem_store(void *user, int slot, const uint8_t *src, size_t len) {
  MemStore *m = static_cast<MemStore *>(user);
  if (m->fail_store || len > sizeof(m->data[0]))
    return false;
  std::memcpy(m->data[slot], src, len);
  m->len[slot] = len;
  m->present[slot] = true;
  return true;
}

struct WifiFake {
  int scans;
  int connects;
  bool persist_ok;
  bool rolled;
  char last_ssid[33];
};

static mwcp_host::ScanStart wifi_scan(void *user) {
  static_cast<WifiFake *>(user)->scans++;
  return mwcp_host::ScanStart::kStarted;
}
static int wifi_poll_scan(void *user, mwcp_host::WifiAp *out, int cap, bool *truncated) {
  (void) user;
  if (cap < 2)
    return 0;
  std::snprintf(out[0].ssid, sizeof(out[0].ssid), "b");
  out[0].rssi = -70;
  std::snprintf(out[0].auth, sizeof(out[0].auth), "wpa2_psk");
  out[0].hidden = false;
  std::snprintf(out[1].ssid, sizeof(out[1].ssid), "a");
  out[1].rssi = -40;
  std::snprintf(out[1].auth, sizeof(out[1].auth), "open");
  out[1].hidden = false;
  *truncated = false;
  return 2;
}
static bool wifi_connect(void *user, const char *ssid, const char *, const char *) {
  WifiFake *w = static_cast<WifiFake *>(user);
  w->connects++;
  std::snprintf(w->last_ssid, sizeof(w->last_ssid), "%s", ssid);
  return true;
}
static int wifi_poll_connect(void *user, char *ip, size_t ip_cap, int *rssi) {
  (void) user;
  std::snprintf(ip, ip_cap, "10.0.0.8");
  *rssi = -48;
  return 1;
}
static bool wifi_persist(void *user, const char *, const char *) { return static_cast<WifiFake *>(user)->persist_ok; }
static bool wifi_rollback(void *user) {
  static_cast<WifiFake *>(user)->rolled = true;
  return true;
}

static mwcp_host::Identity ident() {
  mwcp_host::Identity id{};
  id.device_id = "g2-host";
  id.configured_model = "r60abd1";
  id.dimension = "2D";
  id.firmware_version = "g2";
  id.git_sha = "9a524b8";
  id.release_channel = "development";
  id.build_profile = "host-test";
  id.cap_revision = "r60-cap-1";
  id.max_targets = 1;
  return id;
}

static void call(mwcp_host::Service &svc, uint32_t now, uint32_t session, uint32_t req, uint16_t code, const char *json,
                 char *out, size_t cap, uint32_t *sid, bool *sent) {
  *sent =
      svc.handle(now, session, req, code, reinterpret_cast<const uint8_t *>(json), std::strlen(json), out, cap, sid);
}

int main() {
  MemStore mem{};
  WifiFake wifi{};
  wifi.persist_ok = true;
  mwcp_host::Service svc;
  mwcp_host::Identity id = ident();
  svc.begin(id, "0123456789abcdef0123456789abcdef");
  mwcp_host::StoragePort storage{mem_load, mem_store, &mem};
  mwcp_host::WifiPort wport{wifi_scan,    wifi_poll_scan, wifi_connect, wifi_poll_connect,
                            wifi_persist, wifi_rollback,  &wifi};
  svc.set_storage(storage);
  svc.set_wifi(wport);
  mwcp_host::RadarView radar{};
  svc.set_radar(&radar);

  char out[2048];
  uint32_t sid = 0;
  bool sent = false;
  call(svc, 1000, 0, 1, 0x0001,
       "{\"client\":{\"name\":\"mmwave-web-console\",\"version\":\"0.1.0\"},\"nonce\":"
       "\"0123456789abcdef0123456789abcdef\","
       "\"protocol\":{\"major\":1,\"minor_max\":0},\"max_payload\":4096}",
       out, sizeof(out), &sid, &sent);
  expect(sent && std::strstr(out, "\"boot_id\":\"0123456789abcdef0123456789abcdef\""), "hello boot");
  expect(std::strlen("0123456789abcdef0123456789abcdef") == 32, "boot width");

  call(svc, 1100, sid, 2, 0x0002, "{}", out, sizeof(out), &sid, &sent);
  expect(sent && std::strstr(out, "uptime_ms"), "ping");
  char first[2048];
  std::snprintf(first, sizeof(first), "%s", out);
  call(svc, 1200, sid, 2, 0x0002, "{}", out, sizeof(out), &sid, &sent);
  expect(sent && std::strcmp(first, out) == 0, "replay");
  call(svc, 1300, sid, 2, 0x0012, "{}", out, sizeof(out), &sid, &sent);
  expect(sent && std::strstr(out, "ID_REUSE"), "id reuse");

  int z = 0;
  svc.config_z(&z);
  call(svc, 1400, sid, 3, 0x0021, "{\"base_revision\":\"1\",\"changes\":{\"install.z_cm\":600}}", out, sizeof(out),
       &sid, &sent);
  int z_after = 0;
  svc.config_z(&z_after);
  expect(sent && std::strstr(out, "\"valid\":true") && z_after == z, "validate has no side effect");

  call(
      svc, 1500, sid, 4, 0x0022,
      "{\"base_revision\":\"1\",\"op_id\":\"01234567-89ab-cdef-0123-456789abcdef\",\"changes\":{\"install.z_cm\":600}}",
      out, sizeof(out), &sid, &sent);
  expect(sent && std::strstr(out, "\"persisted\":true") && std::strstr(out, "\"revision\":\"2\""), "commit");
  svc.config_z(&z);
  expect(z == 600, "commit applied");
  call(
      svc, 1600, sid, 5, 0x0022,
      "{\"base_revision\":\"1\",\"op_id\":\"01234567-89ab-cdef-0123-456789abcdef\",\"changes\":{\"install.z_cm\":600}}",
      out, sizeof(out), &sid, &sent);
  expect(sent && std::strstr(out, "\"revision\":\"2\""), "commit idempotent");
  call(
      svc, 1700, sid, 6, 0x0022,
      "{\"base_revision\":\"2\",\"op_id\":\"01234567-89ab-cdef-0123-456789abcdef\",\"changes\":{\"install.z_cm\":220}}",
      out, sizeof(out), &sid, &sent);
  expect(sent && std::strstr(out, "OP_ID_REUSE"), "op reuse");

  mem.fail_store = true;
  call(
      svc, 1800, sid, 7, 0x0022,
      "{\"base_revision\":\"2\",\"op_id\":\"aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee\",\"changes\":{\"install.z_cm\":220}}",
      out, sizeof(out), &sid, &sent);
  expect(sent && std::strstr(out, "STORAGE_FAILED"), "store failure visible");
  svc.config_z(&z);
  expect(z == 600, "failed persist rolls back");
  mem.fail_store = false;

  for (int i = 0; i < 8; i++) {
    char body[160];
    std::snprintf(body, sizeof(body),
                  "{\"action_id\":\"radar.reset_module\",\"op_id\":\"%08d-2222-3333-4444-555555555555\",\"params\":{},"
                  "\"confirm\":\"radar.reset_module\"}",
                  i + 1);
    call(svc, 2000, sid, static_cast<uint32_t>(20 + i), 0x0041, body, out, sizeof(out), &sid, &sent);
    expect(sent && std::strstr(out, "job-"), "reset admitted");
  }
  expect(svc.record_count() == 8, "eight records");
  for (uint32_t step = 1; step <= 29; step++) {
    call(svc, 2000 + step * 10000, sid, 100 + step, 0x0002, "{}", out, sizeof(out), &sid, &sent);
    expect(sent, "keepalive");
  }
  char again[180];
  std::snprintf(again, sizeof(again),
                "{\"action_id\":\"radar.reset_module\",\"op_id\":\"%08d-2222-3333-4444-555555555555\",\"params\":{},"
                "\"confirm\":\"radar.reset_module\"}",
                1);
  call(svc, 2000 + 299999, sid, 200, 0x0041, again, out, sizeof(out), &sid, &sent);
  expect(sent && std::strstr(out, "\"job_id\""), "idempotent at full capacity");
  call(svc, 2000 + 299999, sid, 201, 0x0041,
       "{\"action_id\":\"radar.reset_module\",\"op_id\":\"99999999-2222-3333-4444-555555555555\",\"params\":{},"
       "\"confirm\":\"radar.reset_module\"}",
       out, sizeof(out), &sid, &sent);
  expect(sent && std::strstr(out, "capacity") && svc.record_count() == 8, "299999 protected");
  const char *wifi_before = svc.wifi_state();
  call(svc, 2000 + 299999, sid, 202, 0x0052,
       "{\"op_id\":\"abababab-2222-3333-4444-555555555555\",\"ssid\":\"x\",\"auth\":\"wpa2_psk\",\"password\":"
       "\"secret123\"}",
       out, sizeof(out), &sid, &sent);
  expect(sent && std::strstr(out, "capacity") && std::strcmp(svc.wifi_state(), wifi_before) == 0 && wifi.connects == 0,
         "capacity has no wifi side effect");
  expect(std::strstr(out, "secret123") == nullptr, "password not in capacity error");
  call(svc, 2000 + 300000, sid, 203, 0x0041,
       "{\"action_id\":\"radar.reset_module\",\"op_id\":\"88888888-2222-3333-4444-555555555555\",\"params\":{},"
       "\"confirm\":\"radar.reset_module\"}",
       out, sizeof(out), &sid, &sent);
  expect(sent && std::strstr(out, "job-"), "300000 reclaim");
  call(svc, 2000 + 300001, sid, 204, 0x0041,
       "{\"action_id\":\"device.restart\",\"op_id\":\"77777777-2222-3333-4444-555555555555\",\"params\":{},\"confirm\":"
       "\"device.restart\"}",
       out, sizeof(out), &sid, &sent);
  expect(sent && svc.restart_pending() && std::strstr(out, "job-"), "restart accepted not finished");
  call(svc, 2000 + 300001, sid, 205, 0x0042, "{\"op_id\":\"77777777-2222-3333-4444-555555555555\"}", out, sizeof(out),
       &sid, &sent);
  expect(std::strstr(out, "\"state\":\"running\"") && std::strstr(out, "succeeded") == nullptr,
         "restart not succeeded");

  char rev_before[24];
  std::snprintf(rev_before, sizeof(rev_before), "%s", svc.revision());
  svc.begin(id, "fedcba9876543210fedcba9876543210");
  expect(std::strcmp(svc.boot_id(), "fedcba9876543210fedcba9876543210") == 0, "new boot");
  expect(svc.record_count() == 0, "reboot clears jobs");
  expect(std::strcmp(svc.revision(), rev_before) == 0, "reboot keeps config");
  call(svc, 10, 0, 1, 0x0001,
       "{\"client\":{\"name\":\"mmwave-web-console\",\"version\":\"0.1.0\"},\"nonce\":"
       "\"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\","
       "\"protocol\":{\"major\":1,\"minor_max\":0},\"max_payload\":4096}",
       out, sizeof(out), &sid, &sent);
  call(svc, 20, sid, 2, 0x0042, "{\"job_id\":\"job-1\"}", out, sizeof(out), &sid, &sent);
  expect(std::strstr(out, "\"state\":\"unknown\""), "old job unknown after reboot");

  call(svc, 30, sid, 3, 0x0050, "{}", out, sizeof(out), &sid, &sent);
  expect(std::strstr(out, "password") == nullptr, "status has no password");

  mem.corrupt = 1;
  MemStore bad{};
  bad.present[0] = bad.present[1] = true;
  bad.len[0] = bad.len[1] = sizeof(bad.data[0]);
  std::memset(bad.data[0], 1, sizeof(bad.data[0]));
  std::memset(bad.data[1], 2, sizeof(bad.data[1]));
  mwcp_host::Service broken;
  broken.begin(id, "0123456789abcdef0123456789abcdef");
  mwcp_host::StoragePort badport{mem_load, mem_store, &bad};
  broken.set_storage(badport);
  broken.load_storage();
  expect(std::strcmp(broken.storage_state(), "recovery_required") == 0, "both slots corrupt");
  mwcp_host::LegacyInstall legacy{};
  legacy.z = 220;
  expect(!broken.migrate_legacy(legacy), "no silent factory reset");

  if (g_failed)
    return 1;
  std::printf("mwcp service test passed\n");
  return 0;
}
