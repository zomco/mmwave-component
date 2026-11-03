#include "mwcp_json.h"
#include "mwcp_link.h"
#include "mwcp_wifi_adapter.h"

#include <math.h>
#include <cmath>
#include <string>
#include <cstdio>
#include <cstring>
#include <cstdlib>

#include <utility>
#include <vector>

static int g_failed = 0;
static void expect(bool ok, const char *name) {
  if (!ok) {
    std::fprintf(stderr, "FAIL %s\n", name);
    g_failed++;
  }
}

static void print_wire(const char *kind, const uint8_t *data, size_t n) {
  std::printf("WIRE %s ", kind);
  for (size_t i = 0; i < n; i++)
    std::printf("%02x", data[i]);
  std::printf("\n");
}

struct Mem {
  bool present[2];
  uint8_t data[2][4096];
  size_t len[2];
  bool fail_store;
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
  if (m->fail_store || slot < 0 || slot > 1 || len > sizeof(m->data[0]))
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

struct Captured {
  char json[4096];
  uint32_t request_id;
  uint16_t code;
  uint32_t session_id;
  bool saw;
  std::vector<uint8_t> wire;
};

static bool call(mwcp_host::Service &svc, MwcpHostLink &link, uint32_t now, uint32_t sid, uint32_t req, uint16_t code,
                 const char *body, Captured *cap) {
  for (int i = 0; i < 80 && (link.tx.active || link.control_ready); i++)
    link.pump([](const uint8_t *, size_t n) { return static_cast<int>(n); }, now);
  cap->json[0] = 0;
  cap->saw = false;
  cap->wire.clear();
  if (link.control_ready || link.tx.active) {
    std::fprintf(stderr, "call busy req=%lu\n", static_cast<unsigned long>(req));
    return false;
  }
  if (!mwcp_dispatch_request(svc, link, now, sid, req, code, reinterpret_cast<const uint8_t *>(body),
                             std::strlen(body))) {
    std::fprintf(stderr, "call dispatch req=%lu sid=%lu live=%u\n", static_cast<unsigned long>(req),
                 static_cast<unsigned long>(sid), svc.session_id());
    return false;
  }
  expect(!link.may_queue_event(), "control blocks events");
  for (int i = 0; i < 80 && (link.tx.active || link.control_ready); i++) {
    link.pump(
        [&](const uint8_t *data, size_t n) {
          cap->wire.insert(cap->wire.end(), data, data + n);
          return static_cast<int>(n);
        },
        now);
  }
  mwcp::Parser parser;
  parser.push(
      cap->wire.data(), cap->wire.size(), now,
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
  const bool session_ok = code == 0x0001 ? cap->session_id != 0 : cap->session_id == sid;
  if (!cap->saw || cap->request_id != req || cap->code != code || !session_ok) {
    std::fprintf(stderr, "call miss req=%lu code=%u saw=%d got_req=%lu got_code=%u got_sid=%lu json=%.80s\n",
                 static_cast<unsigned long>(req), code, cap->saw ? 1 : 0, static_cast<unsigned long>(cap->request_id),
                 cap->code, static_cast<unsigned long>(cap->session_id), cap->json);
    return false;
  }
  return true;
}

static uint32_t blob_crc(const uint8_t *p, size_t n) {
  uint32_t crc = 0xFFFFFFFFu;
  for (size_t i = 0; i < n; i++) {
    crc ^= p[i];
    for (int bit = 0; bit < 8; bit++)
      crc = (crc >> 1) ^ (0x82F63B78u & (0u - (crc & 1u)));
  }
  return crc ^ 0xFFFFFFFFu;
}

static int stored_slot(const Mem &mem) {
  if (mem.present[1] && (!mem.present[0] || mem.len[1] >= mem.len[0]))
    return 1;
  if (mem.present[0])
    return 0;
  return -1;
}

int main() {
  struct Guard {
    char out[160];
    unsigned char canary[16];
  };
  Guard guard{};
  std::memset(guard.canary, 0xA5, sizeof(guard.canary));
  char raw[160];
  std::memset(raw, 'Z', 159);
  std::memcpy(raw, "password=x ", 11);
  raw[159] = 0;
  expect(mwcp_host::redact_secrets(raw, guard.out, sizeof(guard.out)), "redact call");
  bool canary_ok = true;
  for (size_t i = 0; i < sizeof(guard.canary); i++)
    if (guard.canary[i] != 0xA5)
      canary_ok = false;
  expect(canary_ok && std::strlen(guard.out) < sizeof(guard.out) && std::strstr(guard.out, "password=x") == nullptr &&
             std::strstr(guard.out, "<redacted>") != nullptr,
         "short secret does not overflow");
  char quoted[80];
  expect(mwcp_host::redact_secrets("password=\"alpha MARKER_SECRET\" tail", quoted, sizeof(quoted)), "quoted redact");
  expect(std::strstr(quoted, "MARKER_SECRET") == nullptr && std::strstr(quoted, "<redacted>") != nullptr &&
             std::strstr(quoted, "tail") != nullptr,
         "quoted secret removed");
  char multi[120];
  expect(mwcp_host::redact_secrets("password= api_key=\"\" PASSWORD=\"a b\"", multi, sizeof(multi)), "multi redact");
  expect(std::strstr(multi, "password=<redacted>") != nullptr && std::strstr(multi, "api_key=<redacted>") != nullptr &&
             std::strstr(multi, "PASSWORD=<redacted>") != nullptr,
         "empty and multiple secrets");
  struct Tiny {
    char out[8];
    unsigned char canary;
  } tiny_guard{};
  tiny_guard.canary = 0x3C;
  expect(mwcp_host::redact_secrets("password=MARKER_SECRET", tiny_guard.out, sizeof(tiny_guard.out)), "truncate call");
  expect(tiny_guard.canary == 0x3C && std::strstr(tiny_guard.out, "MARKER") == nullptr &&
             std::strstr(tiny_guard.out, "SECRET") == nullptr,
         "truncation does not leak");
  char emoji[16];
  unsigned char face[] = {0xF0, 0x9F, 0x98, 0x80, 0};
  char emoji_in[32];
  std::snprintf(emoji_in, sizeof(emoji_in), "%spassword=secret", face);
  expect(mwcp_host::redact_secrets(emoji_in, emoji, sizeof(emoji)), "emoji redact");
  expect(std::strstr(emoji, "secret") == nullptr &&
             (emoji[0] == 0 || (static_cast<unsigned char>(emoji[0]) == 0xF0 && std::strlen(emoji) >= 4)),
         "emoji boundary kept");

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
  Captured cap{};
  expect(call(svc, link, 1000, 0, 1, 0x0001, hello, &cap), "hello matches request");
  print_wire("response", cap.wire.data(), cap.wire.size());
  uint32_t sid = svc.session_id();
  char ha[64] = "old-ha";
  char glob[64] = "old-global";
  expect(!mwcp_host::commit_area_view(ha, sizeof(ha), glob, sizeof(glob), false, "1,1;2,2;3,1"), "failed entity write");
  expect(std::strcmp(ha, "old-ha") == 0 && std::strcmp(glob, "old-global") == 0, "failed transaction does not publish");
  expect(svc.apply_area_text(1, "0,0;100,0;50,80", 1100), "empty config slot 1");
  char canonical[64];
  expect(svc.export_area_text(1, canonical, sizeof(canonical)) &&
             mwcp_host::commit_area_view(ha, sizeof(ha), glob, sizeof(glob), true, canonical),
         "success publishes canonical text");
  expect(
      std::strcmp(ha, canonical) == 0 && std::strcmp(glob, canonical) == 0 && std::strcmp(ha, "0,0;100,0;50,80") == 0,
      "ha and global match authority");
  const char *triangle_page =
      "{\"ok\":true,\"result\":{\"revision\":\"1\",\"items\":[{\"key\":\"areas.definitions\",\"value\":[{\"slot\":0,"
      "\"enabled\":true,\"name\":\"a\",\"points_cm\":[[0,0],[1,0],[0,1]]}]}],\"next_cursor\":null}}";
  expect(mwcp::json_check(reinterpret_cast<const uint8_t *>(triangle_page), std::strlen(triangle_page)),
         "depth 9 area page is legal");
  std::string too_deep = "{\"v\":1}";
  for (int i = 0; i < 9; i++)
    too_deep = std::string("{\"a\":") + too_deep + "}";
  expect(!mwcp::json_check(reinterpret_cast<const uint8_t *>(too_deep.c_str()), too_deep.size()) &&
             std::strcmp(mwcp::json_error_code(), "depth") == 0,
         "depth 11 still rejected");
  int slot = -1, points = 0;
  bool enabled = false;
  expect(svc.area_count() == 1 && svc.area_slot(0, &slot, &enabled, &points) && slot == 1 && enabled && points == 3,
         "slot 1 stored");
  expect(svc.apply_area_text(2, "0,0;80,0;40,40", 1200), "empty config slot 2");
  expect(svc.area_count() == 2, "sparse slots");
  int slot2 = -1;
  expect(svc.area_slot(1, &slot2, &enabled, &points) && slot2 == 2, "second record is slot 2");
  expect(!svc.apply_area_text(0, "1,2;3", 1300), "partial polygon rejected");
  expect(svc.area_count() == 2, "invalid area did not mutate");
  const char *named = "{\"areas.definitions\":[{\"slot\":0,\"enabled\":true,\"name\":\"门\\\"径\\\\A\",\"points_cm\":[["
                      "0,0],[30,0],[15,20],[5,8]]},"
                      "{\"slot\":1,\"enabled\":true,\"name\":\"area1\",\"points_cm\":[[0,0],[100,0],[50,80]]},"
                      "{\"slot\":2,\"enabled\":true,\"name\":\"area2\",\"points_cm\":[[0,0],[80,0],[40,40]]}]}";
  int before_pub = g_published;
  char before_rev[24];
  std::snprintf(before_rev, sizeof(before_rev), "%s", svc.revision());
  expect(svc.apply_ha_changes(named, 1400), "custom name commit");
  expect(std::strcmp(svc.area_name(0), "门\"径\\A") == 0, "custom name stored");
  int keep_x = 0, keep_y = 0;
  expect(svc.area_point(0, 3, &keep_x, &keep_y) && keep_x == 5 && keep_y == 8, "four vertices stored");
  expect(svc.apply_area_text(1, "1,1;9,1;5,6", 1500), "update one slot");
  expect(std::strcmp(svc.area_name(0), "门\"径\\A") == 0, "other name kept");
  expect(svc.area_point(0, 3, &keep_x, &keep_y) && keep_x == 5 && keep_y == 8, "other vertices kept");
  int sx = 0, sy = 0;
  expect(svc.area_slot(1, &slot, &enabled, &points) && slot == 1 && enabled && points == 3 &&
             svc.area_point(1, 0, &sx, &sy) && sx == 1,
         "updated slot replaced");
  expect(svc.apply_area_text(1, "", 1600), "clear slot 1");
  expect(svc.area_slot(1, &slot, &enabled, &points) && slot == 1 && !enabled && points == 0, "slot 1 disabled");
  expect(std::strcmp(svc.area_name(0), "门\"径\\A") == 0, "clear kept other name");
  mem.fail_store = true;
  uint64_t rev_before = svc.revision_u64();
  int pub_before = g_published;
  expect(!svc.apply_area_text(2, "2,2;12,2;6,8", 1700), "persist failure");
  expect(svc.revision_u64() == rev_before && g_published == pub_before, "failure does not publish");
  expect(svc.area_slot(2, &slot, &enabled, &points) && slot == 2 && points == 3, "failure keeps old slot 2");
  mem.fail_store = false;
  (void) before_pub;
  (void) before_rev;

  char poly[1800];
  poly[0] = 0;
  int px[64], py[64];
  for (int i = 0; i < 64; i++) {
    double a = 6.283185307179586 * i / 64.0;
    px[i] = static_cast<int>(1500.0 * std::cos(a));
    py[i] = static_cast<int>(1500.0 * std::sin(a));
    if (i && px[i] == px[i - 1] && py[i] == py[i - 1])
      px[i]++;
    char pair[24];
    std::snprintf(pair, sizeof(pair), "%s[%d,%d]", i ? "," : "", px[i], py[i]);
    std::strcat(poly, pair);
  }
  char areas[1600];
  areas[0] = 0;
  const char *names[] = {"门口", "a\\\"b", "c\\\\d"};
  for (int s = 0; s < 3; s++) {
    char pts[240];
    pts[0] = 0;
    for (int p = 0; p < 12; p++) {
      double a = 6.283185307179586 * p / 12.0;
      int x = static_cast<int>(100.0 * std::cos(a)) + s * 300;
      int y = static_cast<int>(100.0 * std::sin(a));
      char pair[24];
      std::snprintf(pair, sizeof(pair), "%s[%d,%d]", p ? "," : "", x, y);
      std::strcat(pts, pair);
    }
    char slotj[360];
    std::snprintf(slotj, sizeof(slotj), "%s{\"slot\":%d,\"enabled\":true,\"name\":\"%s\",\"points_cm\":[%s]}",
                  s ? "," : "", s, names[s], pts);
    std::strcat(areas, slotj);
  }
  char changes[3600];
  std::snprintf(changes, sizeof(changes), "{\"geometry.boundary_cm\":[%s],\"areas.definitions\":[%s]}", poly, areas);
  expect(svc.apply_ha_changes(changes, 1800), "max config commit");
  mwcp_host::Service cold;
  cold.begin(id, "0123456789abcdef0123456789abcdef");
  cold.set_storage(storage);
  cold.load_storage();
  expect(std::strcmp(cold.area_name(0), "门口") == 0 && std::strcmp(cold.area_name(1), "a\"b") == 0 &&
             std::strcmp(cold.area_name(2), "c\\d") == 0,
         "cold start names");
  int16_t xy[128];
  int bn = 0;
  cold.export_boundary(xy, &bn);
  expect(bn == 64 && xy[0] == px[0] && xy[1] == py[0] && xy[126] == px[63] && xy[127] == py[63], "cold start boundary");
  expect(cold.area_count() == 3, "cold start three areas");
  char read_body[96];
  std::snprintf(read_body, sizeof(read_body), "{\"cursor\":\"cfg:%lu:6:%s\"}", static_cast<unsigned long>(sid),
                svc.revision());
  expect(call(svc, link, 1900, sid, 20, 0x0020, read_body, &cap), "config page request id");
  print_wire("response", cap.wire.data(), cap.wire.size());
  char point[24];
  std::snprintf(point, sizeof(point), "[%d,%d]", px[0], py[0]);
  expect(std::strstr(cap.json, "\"ok\":true") != nullptr && std::strstr(cap.json, point) != nullptr &&
             std::strstr(cap.json, "next_cursor") != nullptr,
         "boundary page keeps every encoded point");
  const char *next = std::strstr(cap.json, "cfg:");
  char next_body[96];
  if (next) {
    char cursor[80];
    size_t n = 0;
    while (next[n] && next[n] != '"' && n + 1 < sizeof(cursor)) {
      cursor[n] = next[n];
      n++;
    }
    cursor[n] = 0;
    std::snprintf(next_body, sizeof(next_body), "{\"cursor\":\"%s\"}", cursor);
    expect(call(svc, link, 1950, sid, 24, 0x0020, next_body, &cap), "areas page request id");
    print_wire("response", cap.wire.data(), cap.wire.size());
    expect(std::strstr(cap.json, "\"ok\":true") != nullptr && std::strstr(cap.json, "门口") != nullptr &&
               std::strstr(cap.json, "PAYLOAD_TOO_LARGE") == nullptr,
           "legal areas page round-trips");
  } else {
    expect(std::strstr(cap.json, "门口") != nullptr && std::strstr(cap.json, "PAYLOAD_TOO_LARGE") == nullptr,
           "legal areas share the boundary page");
  }

  expect(call(svc, link, 2100, sid, 31, 0x0030,
              "{\"streams\":[{\"id\":\"logs\",\"max_rate_hz\":1},{\"id\":\"telemetry\",\"max_rate_hz\":20}],\"event_"
              "budget_bps\":1000}",
              &cap),
         "subscribe request id");
  print_wire("response", cap.wire.data(), cap.wire.size());
  expect(svc.stream_hz(4) == 1 && svc.stream_hz(0) == 20, "per-stream rate");
  expect(std::strstr(cap.json, "\"id\":\"logs\",\"max_rate_hz\":1") != nullptr &&
             std::strstr(cap.json, "\"id\":\"telemetry\",\"max_rate_hz\":20") != nullptr,
         "accepted rates match");
  svc.push_log_at("password=\"alpha MARKER_SECRET\" \xF0\x9F\x98\x80", 2000, "info");
  char event[1280];
  uint16_t event_code = 0;
  expect(svc.next_event(event, sizeof(event), &event_code) && event_code == 0x8005, "log event path");
  expect(std::strstr(event, "MARKER_SECRET") == nullptr && std::strstr(event, "<redacted>") != nullptr,
         "event redacts quoted secret");
  uint8_t ewire[4200];
  uint8_t edec[4200];
  size_t ewire_n = 0, edec_n = 0;
  mwcp::EncodeInput enc{};
  enc.kind = 3;
  enc.session_id = sid;
  enc.request_id = 0;
  enc.code = event_code;
  enc.wire_seq = 1;
  enc.payload = reinterpret_cast<const uint8_t *>(event);
  enc.payload_len = std::strlen(event);
  enc.check_json = true;
  expect(mwcp::encode_frame(enc, ewire, sizeof(ewire), &ewire_n, edec, sizeof(edec), &edec_n) == mwcp::kOk,
         "encode log");
  print_wire("event", ewire, ewire_n);
  uint32_t dropped_before = svc.logs_dropped();
  for (int i = 0; i < 100; i++)
    svc.push_log_at("flood-log", 2000, "info");
  int drained = 0;
  while (svc.next_event(event, sizeof(event), &event_code))
    drained++;
  expect(drained == 0 && svc.logs_dropped() >= dropped_before + 100, "same-ms log flood dropped");
  expect(call(svc, link, 2900, sid, 32, 0x0030,
              "{\"streams\":[{\"id\":\"logs\",\"max_rate_hz\":20}],\"event_budget_bps\":1000}", &cap),
         "budget subscribe");
  expect(svc.stream_hz(4) == 20 && svc.stream_hz(0) == 0, "log rate does not stick to telemetry");
  uint32_t used = 0;
  int admitted = 0;
  for (int i = 0; i < 12; i++) {
    svc.push_log_at("budget-log", static_cast<uint32_t>(3000 + i * 50), "info");
    if (svc.next_event(event, sizeof(event), &event_code)) {
      enc.payload = reinterpret_cast<const uint8_t *>(event);
      enc.payload_len = std::strlen(event);
      enc.wire_seq = static_cast<uint32_t>(i + 2);
      expect(mwcp::encode_frame(enc, ewire, sizeof(ewire), &ewire_n, edec, sizeof(edec), &edec_n) == mwcp::kOk,
             "encode budget log");
      used += static_cast<uint32_t>(ewire_n);
      admitted++;
    }
  }
  expect(admitted > 0 && admitted < 12 && used <= 1000, "wire budget stops log flood");

  mwcp_host::RadarView radar{};
  radar.seen_frame = true;
  radar.last_frame_ms = 5000;
  radar.has_presence = true;
  radar.presence = true;
  radar.presence_ms = 4000;
  radar.has_xy = true;
  radar.local_x = 10;
  radar.local_y = 20;
  radar.position_ms = 0;
  radar.in_boundary = true;
  radar.has_distance = true;
  radar.distance_cm = 321;
  radar.distance_ms = 4100;
  radar.has_breath = true;
  radar.breath = 16.5f;
  radar.breath_ms = 4200;
  radar.has_heart = true;
  radar.heart = 72.0f;
  radar.heart_ms = 4300;
  radar.source_seq = 7;
  svc.set_radar(&radar);
  expect(call(svc, link, 5900, sid, 33, 0x0030,
              "{\"streams\":[{\"id\":\"telemetry\",\"max_rate_hz\":20},{\"id\":\"logs\",\"max_rate_hz\":20}],\"event_"
              "budget_bps\":8000}",
              &cap),
         "telemetry subscribe");
  svc.poll(5999);
  svc.push_log_at("after-telemetry", 5999, "info");
  expect(!link.may_queue_event() == false, "link idle before forward");
  expect(mwcp_forward_events(svc, link) == 1, "production forward takes telemetry");
  std::vector<uint8_t> telem_wire;
  int writes = 0;
  for (int i = 0; i < 80 && (link.tx.active || link.event_ready); i++) {
    link.pump(
        [&](const uint8_t *data, size_t n) {
          if (writes == 0) {
            writes++;
            telem_wire.insert(telem_wire.end(), data, data + 1);
            return 1;
          }
          if (writes == 1) {
            writes++;
            return 0;
          }
          writes++;
          telem_wire.insert(telem_wire.end(), data, data + n);
          return static_cast<int>(n);
        },
        5999);
  }
  expect(link.tx.short_writes > 0 && link.tx.zero_writes > 0, "short and zero writes counted");
  print_wire("event", telem_wire.data(), telem_wire.size());
  mwcp::Parser telem_parser;
  char telem_json[mwcp_host::kMaxEventJson];
  telem_json[0] = 0;
  uint16_t telem_code = 0;
  std::pair<char *, uint16_t *> telem_slot(telem_json, &telem_code);
  telem_parser.push(
      telem_wire.data(), telem_wire.size(), 5999,
      [](const mwcp::Frame &frame, void *user) {
        auto *dst = static_cast<std::pair<char *, uint16_t *> *>(user);
        size_t n =
            frame.payload_length < mwcp_host::kMaxEventJson - 1 ? frame.payload_length : mwcp_host::kMaxEventJson - 1;
        std::memcpy(dst->first, frame.payload, n);
        dst->first[n] = 0;
        *dst->second = frame.code;
      },
      [](mwcp::Status, void *) {}, &telem_slot);
  expect(telem_code == 0x8001 && std::strlen(telem_json) > 768, "forwarded telemetry is larger than the old 768 path");
  expect(std::strstr(telem_json, "\"distance.cm\"") != nullptr &&
             std::strstr(telem_json, "\"breath_rate\"") != nullptr &&
             std::strstr(telem_json, "\"heart_rate\"") != nullptr &&
             std::strstr(telem_json, "\"sample_ms\":4100") != nullptr &&
             std::strstr(telem_json, "\"position_quality\":\"valid\"") != nullptr,
         "metrics and fresh position");
  expect(mwcp_forward_events(svc, link) == 1, "log follows telemetry");
  std::vector<uint8_t> log_wire;
  for (int i = 0; i < 40 && (link.tx.active || link.event_ready); i++) {
    link.pump(
        [&](const uint8_t *data, size_t n) {
          log_wire.insert(log_wire.end(), data, data + n);
          return static_cast<int>(n);
        },
        6000);
  }
  expect(!log_wire.empty(), "log frame left the queue");
  svc.poll(6100);
  expect(svc.next_event(event, sizeof(event), &event_code) &&
             std::strstr(event, "\"position_quality\":\"stale\"") != nullptr,
         "stale at 6000");
  radar.presence = false;
  svc.poll(6200);
  expect(svc.next_event(event, sizeof(event), &event_code) && std::strstr(event, "local_cm") == nullptr &&
             std::strstr(event, "\"value\":false") != nullptr,
         "nobody has no target");
  radar.has_presence = false;
  svc.poll(6300);
  expect(svc.next_event(event, sizeof(event), &event_code) && std::strstr(event, "\"quality\":\"unknown\"") != nullptr,
         "unknown presence");
  expect(call(svc, link, 7000, sid, 40, 0x0030,
              "{\"streams\":[{\"id\":\"logs\",\"max_rate_hz\":20}],\"event_budget_bps\":8000}", &cap),
         "secret log subscribe");
  const char *secret_logs[] = {"{\"password\":\"MARKER_SECRET\"}", "password='alpha MARKER_SECRET'",
                               "wifi_password=MARKER_SECRET"};
  for (int i = 0; i < 3; i++) {
    svc.push_log_at(secret_logs[i], static_cast<uint32_t>(7100 + i * 50), "warn");
    expect(mwcp_forward_events(svc, link) == 1, "secret log forwarded");
    std::vector<uint8_t> secret_wire;
    for (int n = 0; n < 40 && (link.tx.active || link.event_ready); n++) {
      link.pump(
          [&](const uint8_t *data, size_t len) {
            secret_wire.insert(secret_wire.end(), data, data + len);
            return static_cast<int>(len);
          },
          7200);
    }
    print_wire("event", secret_wire.data(), secret_wire.size());
    char decoded[mwcp_host::kMaxEventJson];
    decoded[0] = 0;
    mwcp::Parser secret_parser;
    secret_parser.push(
        secret_wire.data(), secret_wire.size(), 7200,
        [](const mwcp::Frame &frame, void *user) {
          auto *dst = static_cast<char *>(user);
          size_t n =
              frame.payload_length < mwcp_host::kMaxEventJson - 1 ? frame.payload_length : mwcp_host::kMaxEventJson - 1;
          std::memcpy(dst, frame.payload, n);
          dst[n] = 0;
        },
        [](mwcp::Status, void *) {}, decoded);
    expect(std::strstr(decoded, "MARKER") == nullptr && std::strstr(decoded, "SECRET") == nullptr &&
               std::strstr(decoded, "<redacted>") != nullptr,
           "secret absent from forwarded log frame");
  }

  int slot_i = stored_slot(mem);
  expect(slot_i >= 0, "blob present");
  if (slot_i >= 0) {
    uint8_t saved[4096];
    std::memcpy(saved, mem.data[slot_i], mem.len[slot_i]);
    std::memset(mem.data[slot_i] + 12, 0, 24);
    std::memcpy(mem.data[slot_i] + 12, "18446744073709551615", 20);
    uint32_t crc = blob_crc(mem.data[slot_i] + 12, mem.len[slot_i] - 12);
    std::memcpy(mem.data[slot_i] + 8, &crc, 4);
    svc.load_storage();
    expect(svc.revision_u64() == 0xffffffffffffffffull, "loaded uint64 max");
    uint8_t before[4096];
    std::memcpy(before, mem.data[slot_i], mem.len[slot_i]);
    int pubs = g_published;
    expect(!svc.apply_ha_number("install.z_cm", 400, 9000), "ha rejects max revision");
    expect(svc.revision_u64() == 0xffffffffffffffffull && g_published == pubs &&
               std::memcmp(before, mem.data[slot_i], mem.len[slot_i]) == 0,
           "ha max has no storage side effect");
    char commit[180];
    std::snprintf(commit, sizeof(commit),
                  "{\"base_revision\":\"18446744073709551615\",\"op_id\":\"bbbbbbbb-0000-4000-8000-000000000099\","
                  "\"changes\":{\"install.z_cm\":400}}");
    expect(call(svc, link, 9100, sid, 90, 0x0022, commit, &cap), "usb max request id");
    print_wire("response", cap.wire.data(), cap.wire.size());
    expect(std::strstr(cap.json, "STORAGE_FAILED") != nullptr && svc.revision_u64() == 0xffffffffffffffffull &&
               std::memcmp(before, mem.data[slot_i], mem.len[slot_i]) == 0,
           "usb max does not wrap");
    (void) saved;
  }

  struct Cred {
    bool write_ok;
    bool sync_ok;
    bool read_ok;
    bool wrote;
    bool synced;
    char ssid[33];
    char pass[65];
  } cred{};
  cred.write_ok = cred.sync_ok = cred.read_ok = true;
  mwcp_host::PersistOps ops{};
  ops.user = &cred;
  ops.write = [](void *user, const char *ssid, const char *password) {
    auto *c = static_cast<Cred *>(user);
    c->wrote = true;
    if (!c->write_ok)
      return false;
    std::snprintf(c->ssid, sizeof(c->ssid), "%s", ssid);
    std::snprintf(c->pass, sizeof(c->pass), "%s", password);
    return true;
  };
  ops.sync = [](void *user) {
    auto *c = static_cast<Cred *>(user);
    c->synced = true;
    return c->sync_ok;
  };
  ops.readback = [](void *user, char *ssid, size_t ssid_cap, char *password, size_t pass_cap) {
    auto *c = static_cast<Cred *>(user);
    if (!c->read_ok)
      return false;
    std::snprintf(ssid, ssid_cap, "%s", c->ssid);
    std::snprintf(password, pass_cap, "%s", c->pass);
    return true;
  };
  std::snprintf(cred.ssid, sizeof(cred.ssid), "%s", "old");
  std::snprintf(cred.pass, sizeof(cred.pass), "%s", "old-pass-1");
  expect(mwcp_host::persist_credentials(ops, "home", "secretpass", "old", "old-pass-1") && cred.wrote && cred.synced,
         "adapter persist success");
  cred.write_ok = false;
  cred.wrote = cred.synced = false;
  expect(!mwcp_host::persist_credentials(ops, "home", "secretpass", "old", "old-pass-1") && !cred.synced,
         "adapter write failure");
  cred.write_ok = true;
  cred.sync_ok = false;
  std::snprintf(cred.ssid, sizeof(cred.ssid), "%s", "old");
  std::snprintf(cred.pass, sizeof(cred.pass), "%s", "old-pass-1");
  expect(!mwcp_host::persist_credentials(ops, "home", "secretpass", "old", "old-pass-1"), "adapter sync failure");
  expect(std::strcmp(cred.ssid, "old") == 0 && std::strcmp(cred.pass, "old-pass-1") == 0,
         "sync failure restores previous credentials");
  cred.sync_ok = true;
  cred.read_ok = false;
  expect(!mwcp_host::persist_credentials(ops, "home", "secretpass", "old", "old-pass-1"), "adapter readback failure");
  expect(std::strcmp(mwcp_host::scan_auth_name(false), "open") == 0 &&
             std::strcmp(mwcp_host::scan_auth_name(true), "wpa2_psk") != 0,
         "auth is not guessed");

  if (g_failed) {
    std::fprintf(stderr, "mwcp close test failed %d\n", g_failed);
    return 1;
  }
  std::printf("mwcp close test passed\n");
  return 0;
}
