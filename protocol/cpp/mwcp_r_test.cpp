#include "mwcp_link.h"

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
  if (m->fail_store || len > sizeof(m->data[0]))
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

static void hello(mwcp_host::Service &svc, MwcpHostLink &link, uint32_t *sid) {
  const char *body = "{\"client\":{\"name\":\"mmwave-web-console\",\"version\":\"0.1.0\"},\"nonce\":"
                     "\"0123456789abcdef0123456789abcdef\","
                     "\"protocol\":{\"major\":1,\"minor_max\":0},\"max_payload\":4096}";
  mwcp_dispatch_request(svc, link, 1000, 0, 1, 0x0001, reinterpret_cast<const uint8_t *>(body), std::strlen(body));
  *sid = svc.session_id();
}

int main() {
  Mem mem{};
  mwcp_host::Service svc;
  MwcpHostLink link;
  auto id = ident();
  svc.begin(id, "0123456789abcdef0123456789abcdef");
  mwcp_host::StoragePort storage{mem_load, mem_store, &mem};
  svc.set_storage(storage);
  uint32_t sid = 0;
  hello(svc, link, &sid);
  expect(link.control_ready && link.control_len > 20, "control queued");
  bool all_zero = true;
  for (size_t i = 0; i < link.control_len; i++)
    if (link.control[i] != 0)
      all_zero = false;
  expect(!all_zero, "queued frame is not zeros");

  std::vector<uint8_t> sent;
  auto write_all = [&](const uint8_t *data, size_t want) {
    sent.insert(sent.end(), data, data + want);
    return static_cast<int>(want);
  };
  for (int i = 0; i < 80 && (link.tx.active || link.control_ready); i++)
    link.pump(write_all, 1000);
  expect(sent.size() == link.control_completed || !sent.empty(), "pump emitted bytes");
  expect(!(sent.size() > 8 && sent[1] == 0 && sent[2] == 0 && sent[3] == 0 && sent[4] == 0),
         "pump is not an all-zero payload");
  mwcp::Parser parser;
  int frames = 0;
  parser.push(
      sent.data(), sent.size(), 1000,
      [](const mwcp::Frame &frame, void *user) {
        (*static_cast<int *>(user))++;
        expect(frame.kind == 2 && frame.payload_length > 10, "decoded response");
      },
      [](mwcp::Status, void *) {}, &frames);
  expect(frames == 1, "production bytes decode");
  std::printf("FRAME ");
  for (uint8_t b : sent)
    std::printf("%02x", b);
  std::printf("\n");

  MwcpHostLink stalled;
  stalled.queue_json(2, 1, 2, 0x0002, "{\"ok\":true,\"result\":{\"uptime_ms\":1}}", true);
  int zeros = 0;
  stalled.pump(
      [&](const uint8_t *, size_t) {
        zeros++;
        return 0;
      },
      0);
  stalled.pump([&](const uint8_t *, size_t) { return 0; }, 250);
  expect(!stalled.tx.active && stalled.tx.timeouts == 1, "zero write abandons");

  auto drain = [&]() {
    for (int i = 0; i < 80 && (link.tx.active || link.control_ready); i++)
      link.pump(write_all, 1000);
  };
  const char *commit = "{\"base_revision\":\"1\",\"op_id\":\"01234567-89ab-cdef-0123-456789abcdef\",\"changes\":{"
                       "\"geometry.boundary_cm\":[[1,1],[2,1],[1,2]]}}";
  expect(mwcp_dispatch_request(svc, link, 1100, sid, 3, 0x0022, reinterpret_cast<const uint8_t *>(commit),
                               std::strlen(commit)),
         "commit dispatched");
  drain();
  int16_t before[8];
  int n = 0;
  svc.export_boundary(before, &n);
  expect(n == 3 && before[0] == 1 && before[1] == 1, "triangle stored");
  const char *bad_val =
      "{\"base_revision\":\"2\",\"changes\":{\"geometry.boundary_cm\":[[100,100],[200,100],[100,200]]}}";
  expect(mwcp_dispatch_request(svc, link, 1200, sid, 4, 0x0021, reinterpret_cast<const uint8_t *>(bad_val),
                               std::strlen(bad_val)),
         "validate dispatched");
  drain();
  int16_t after[8];
  int n2 = 0;
  svc.export_boundary(after, &n2);
  expect(n2 == n && std::memcmp(before, after, sizeof(int16_t) * static_cast<size_t>(n * 2)) == 0,
         "validate does not replace triangle");
  const char *yaw = "{\"base_revision\":\"2\",\"changes\":{\"install.yaw_deg\":999}}";
  char out[512];
  uint32_t os = 0;
  svc.handle(1300, sid, 5, 0x0021, reinterpret_cast<const uint8_t *>(yaw), std::strlen(yaw), out, sizeof(out), &os);
  expect(std::strstr(out, "OUT_OF_RANGE") != nullptr, "yaw 999 rejected");
  const char *areas = "{\"base_revision\":\"2\",\"changes\":{\"areas.definitions\":\"invalid\"}}";
  svc.handle(1400, sid, 6, 0x0021, reinterpret_cast<const uint8_t *>(areas), std::strlen(areas), out, sizeof(out), &os);
  expect(std::strstr(out, "INVALID_ARGUMENT") != nullptr, "invalid areas rejected");

  for (int i = 0; i < 8; i++) {
    char body[180];
    std::snprintf(body, sizeof(body),
                  "{\"base_revision\":\"%d\",\"op_id\":\"0000000%d-1111-2222-3333-444444444444\",\"changes\":{"
                  "\"install.z_cm\":%d}}",
                  i + 2, i + 1, 50 + i);
    uint32_t s2 = 0;
    svc.handle(2000 + static_cast<uint32_t>(i), sid, static_cast<uint32_t>(20 + i), 0x0022,
               reinterpret_cast<const uint8_t *>(body), std::strlen(body), out, sizeof(out), &s2);
  }
  expect(svc.revision_u64() == 10, "revision reached 10");
  mwcp_host::Service cold;
  cold.begin(id, "fedcba9876543210fedcba9876543210");
  cold.set_storage(storage);
  cold.load_storage();
  expect(cold.revision_u64() == 10, "cold start keeps 10 not 9");

  char cursor[64];
  std::snprintf(cursor, sizeof(cursor), "{\"cursor\":\"%lu:-1:r60-cap-1\"}", static_cast<unsigned long>(sid));
  svc.handle(3000, sid, 40, 0x0011, reinterpret_cast<const uint8_t *>(cursor), std::strlen(cursor), out, sizeof(out),
             &os);
  expect(std::strstr(out, "INVALID_ARGUMENT") != nullptr, "negative cursor rejected");

  int sends = 0;
  svc.set_radar_action(
      [](void *user) {
        (*static_cast<int *>(user))++;
        return 0;
      },
      &sends);
  const char *reset = "{\"action_id\":\"radar.reset_module\",\"op_id\":\"aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee\","
                      "\"params\":{},\"confirm\":\"radar.reset_module\"}";
  svc.handle(3100, sid, 41, 0x0041, reinterpret_cast<const uint8_t *>(reset), std::strlen(reset), out, sizeof(out),
             &os);
  svc.handle(3200, sid, 42, 0x0041, reinterpret_cast<const uint8_t *>(reset), std::strlen(reset), out, sizeof(out),
             &os);
  expect(sends == 1, "same op_id resets once");

  const char *sub = "{\"streams\":[{\"id\":\"telemetry\",\"max_rate_hz\":1}],\"event_budget_bps\":8000}";
  svc.handle(3300, sid, 43, 0x0030, reinterpret_cast<const uint8_t *>(sub), std::strlen(sub), out, sizeof(out), &os);
  mwcp_host::RadarView radar{};
  radar.seen_frame = true;
  svc.set_radar(&radar);
  for (int i = 0; i < 20; i++)
    svc.poll(3300 + 20000 + static_cast<uint32_t>(i));
  char ev[256];
  uint16_t code = 0;
  int events = 0;
  while (svc.next_event(ev, sizeof(ev), &code))
    events++;
  expect(events == 0, "expired session emits no telemetry");
  (void) drain;

  if (g_failed)
    return 1;
  std::printf("mwcp r test passed\n");
  return 0;
}
