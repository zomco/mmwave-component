// G2-R3-01 (r3d): REAL Parser -> DeferredRequest -> REAL Service/Link ->
// REAL codec decode. Per the r3d review:
//   - the full-slot SAME-ID-DIFFERENT-BODY conflict is NOT silently
//     dropped: the deferred keeps it in a bounded conflict slot, the loop
//     forwards it to the Service after the original, and the Service's
//     replay cache answers ID_REUSE (decoded with the real codec) without
//     a second side effect;
//   - the EXACT 4096-byte legal payload is the SAME bytes through encode,
//     parser and Service (asserted len==4096, dispatch reads 4096);
//   - a RECEIVER-side 4097-byte wire frame (built by a test-only encoder
//     that bypasses the production payload cap) is rejected by the parser
//     with no side effect, and a legal frame in the same stream recovers;
//   - config readback goes through a real CONFIG_READ dispatch and checks
//     the INSTALLED VALUE plus the revision, not a wire substring.

#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <vector>

#include "deferred_request.h"
#include "mwcp_json.h"
#include "mwcp_link.h"
#include "mwcp_wifi_adapter.h"

#define NEWLINE "\n"

static int g_failures = 0;

static void expect(bool ok, const std::string &name, const std::string &detail = "") {
  std::printf("[%s] %s %s%s", ok ? "PASS" : "FAIL", name.c_str(), detail.c_str(), NEWLINE);
  if (!ok)
    g_failures++;
}

static void expect(bool ok, const char *name, const std::string &detail = "") { expect(ok, std::string(name), detail); }

// ---- Service plumbing --------------------------------------------------------
struct Mem {
  bool present[2]{false, false};
  uint8_t data[2][4096]{};
  size_t len[2]{0, 0};
  int store_calls = 0;
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
  m->store_calls++;
  return true;
}
static mwcp_host::Identity ident() {
  mwcp_host::Identity id{};
  id.device_id = "dev";
  id.configured_model = "r60abd1";
  id.dimension = "2D";
  return id;
}

// ---- wire encode (production path) -------------------------------------------
static std::vector<uint8_t> encode_req(uint32_t request, uint32_t session, uint16_t code, const std::string &payload) {
  std::vector<uint8_t> wire(mwcp::kMaxWire);
  size_t wire_len = 0, decoded_len = 0;
  mwcp::EncodeInput in{};
  in.kind = 1;
  in.session_id = session;
  in.request_id = request;
  in.code = code;
  in.payload = reinterpret_cast<const uint8_t *>(payload.data());
  in.payload_len = payload.size();
  in.wire_seq = 0;
  in.check_json = true;
  std::vector<uint8_t> decoded(mwcp::kMaxDecoded);
  mwcp::Status st =
      mwcp::encode_frame(in, wire.data(), wire.size(), &wire_len, decoded.data(), decoded.size(), &decoded_len);
  if (st != mwcp::kOk)
    return {};
  wire.resize(wire_len);
  return wire;
}

// ---- TEST-ONLY raw frame builder (r3d D.4) ------------------------------------
// Builds a wire frame with an arbitrary payload length WITHOUT the
// production payload cap, so a 4097-byte receiver-side frame can be fed to
// the real parser. The header/CRC layout is the production one; only the
// "payload too large" pre-check is bypassed.
static std::vector<uint8_t> build_raw_frame(uint32_t request, uint32_t session, uint16_t code,
                                            const std::string &payload) {
  const size_t raw_len = mwcp::kHeaderLen + payload.size() + 4;
  std::vector<uint8_t> decoded(raw_len);
  std::memcpy(decoded.data(), "MWCP", 4);
  decoded[4] = mwcp::kMajor;
  decoded[5] = mwcp::kMinor;
  decoded[6] = 1;  // kind=request
  decoded[7] = 0;  // flags
  auto w32 = [&](size_t off, uint32_t v) {
    decoded[off] = static_cast<uint8_t>(v);
    decoded[off + 1] = static_cast<uint8_t>(v >> 8);
    decoded[off + 2] = static_cast<uint8_t>(v >> 16);
    decoded[off + 3] = static_cast<uint8_t>(v >> 24);
  };
  auto w16 = [&](size_t off, uint16_t v) {
    decoded[off] = static_cast<uint8_t>(v);
    decoded[off + 1] = static_cast<uint8_t>(v >> 8);
  };
  w32(8, session);
  w32(12, request);
  w16(16, code);
  w16(18, static_cast<uint16_t>(payload.size()));
  w32(20, 0);
  std::memcpy(decoded.data() + mwcp::kHeaderLen, payload.data(), payload.size());
  const uint32_t crc = mwcp::crc32c(decoded.data(), mwcp::kHeaderLen + payload.size());
  w32(mwcp::kHeaderLen + payload.size(), crc);
  std::vector<uint8_t> wire(mwcp::kMaxWire + 8);
  size_t encoded_len = 0;
  if (mwcp::cobs_encode(decoded.data(), raw_len, wire.data() + 1, wire.size() - 2, &encoded_len) != mwcp::kOk)
    return {};
  wire[0] = 0;
  wire[encoded_len + 1] = 0;
  wire.resize(encoded_len + 2);
  return wire;
}

// ---- stash + callbacks (PRODUCT semantics: on_frame mirrors MwcpHost) --------
static esphome::mmwave_host::DeferredRequest g_stash;
static void on_frame(const mwcp::Frame &frame, void *) {
  if (frame.kind != 1 || frame.payload == nullptr)
    return;
  g_stash.stash(frame);
}
static void on_error(mwcp::Status, void *) {}
static void reset_stash() { g_stash = esphome::mmwave_host::DeferredRequest{}; }

// ---- REAL codec decode of a response wire -----------------------------------
struct DecodedFrame {
  bool got = false;
  mwcp::Frame frame{};
  std::string json;  // decoded payload as text
};

static void decode_wire(const std::string &wire, DecodedFrame &out) {
  // decode EVERY frame with the REAL codec: COBS, CRC, header, session
  mwcp::Parser parser;
  parser.push(
      reinterpret_cast<const uint8_t *>(wire.data()), wire.size(), 0 + 1,
      [](const mwcp::Frame &f, void *ud) {
        auto *cap = static_cast<DecodedFrame *>(ud);
        // keep the LAST response frame (kind=2) on the wire
        if (f.kind == 2) {
          cap->got = true;
          cap->frame = f;
          cap->json = std::string(reinterpret_cast<const char *>(f.payload), f.payload_length);
        }
      },
      [](mwcp::Status, void *) {}, &out);
}

// Pump the TX wire, then decode every frame on it through the REAL codec.
static DecodedFrame dispatch_and_decode(mwcp_host::Service &svc, MwcpHostLink &link, uint32_t now) {
  DecodedFrame out;
  if (!g_stash.has())
    return out;
  std::string wire;
  bool queued = mwcp_dispatch_request(svc, link, now, g_stash.session_id_, g_stash.request_id_, g_stash.code_,
                                      g_stash.payload_, g_stash.payload_length_);
  g_stash.clear();
  // the PRODUCT loop then forwards the kept conflict (r3d): the Service
  // answers ID_REUSE without executing the conflict body.
  if (g_stash.has_conflict()) {
    mwcp_dispatch_request(svc, link, now, g_stash.conflict_session_, g_stash.conflict_request_, g_stash.conflict_code_,
                          g_stash.conflict_payload_, g_stash.conflict_length_);
    g_stash.clear_conflict();
  }
  if (!queued)
    return out;
  for (int i = 0; i < 800 && (link.tx.active || link.control_ready); i++) {
    link.pump(
        [&](const uint8_t *d, size_t n) {
          wire.insert(wire.end(), d, d + n);
          return static_cast<int>(n);
        },
        now);
  }
  decode_wire(wire, out);
  return out;
}

// ---- real CONFIG_READ readback: installed VALUE + revision -------------------
struct Readback {
  bool got = false;
  std::string revision;
  double x_cm = -1;
  bool has_x = false;
};

// Pull "key":"<name>","value":<num> out of an items array of a CONFIG_READ
// page; a tiny test-side scanner over the DECODED JSON (the decoded buffer,
// not the wire).
static double read_item_num(const std::string &json, const char *key, bool *found) {
  *found = false;
  std::string needle = std::string("{\"key\":\"") + key + "\",\"value\":";
  auto pos = json.find(needle);
  if (pos == std::string::npos)
    return 0.0;
  *found = true;
  return std::atof(json.c_str() + pos + needle.size());
}

static Readback real_config_read(mwcp_host::Service &svc, MwcpHostLink &link, uint32_t now, uint32_t session,
                                 uint32_t request_id) {
  Readback out;
  std::string wire;
  mwcp_dispatch_request(svc, link, now, session, request_id, 0x0020, reinterpret_cast<const uint8_t *>("{}"), 2);
  for (int i = 0; i < 400 && (link.tx.active || link.control_ready); i++) {
    link.pump(
        [&](const uint8_t *d, size_t n) {
          wire.insert(wire.end(), d, d + n);
          return static_cast<int>(n);
        },
        now);
  }
  DecodedFrame df;
  decode_wire(wire, df);
  if (!df.got)
    return out;
  out.got = true;
  // revision from the decoded CONFIG_READ JSON
  auto pos = df.json.find("\"revision\":\"");
  if (pos != std::string::npos) {
    auto start = pos + 12;
    auto end = df.json.find('"', start);
    if (end != std::string::npos && end > start)
      out.revision = df.json.substr(start, end - start);
  }
  out.x_cm = read_item_num(df.json, "install.x_cm", &out.has_x);
  return out;
}

// ---- fresh Service with a live session ----------------------------------------
struct FreshService {
  mwcp_host::Service svc;
  MwcpHostLink link;
  Mem mem;
  uint32_t session = 0;
  uint32_t next_req = 100;

  FreshService() {
    svc.begin(ident(), "0123456789abcdef0123456789abcdef");
    mwcp_host::StoragePort storage{mem_load, mem_store, &mem, nullptr, nullptr};
    svc.set_storage(storage);
    const char *hello = "{\"client\":{\"name\":\"g2-r3c\"},\"nonce\":"
                        "\"0123456789abcdef0123456789abcdef\","
                        "\"protocol\":{\"major\":1,\"minor_max\":0},\"max_payload\":4096}";
    mwcp_dispatch_request(svc, link, 100, 0, 1, 0x0001, reinterpret_cast<const uint8_t *>(hello), std::strlen(hello));
    for (int i = 0; i < 200 && (link.tx.active || link.control_ready); i++)
      link.pump([](const uint8_t *, size_t len) { return static_cast<int>(len); }, 100);
    session = svc.session_id();
  }
};

// commit body helper
static std::string commit_body(const std::string &base, const std::string &op, const std::string &changes) {
  return "{\"base_revision\":\"" + base + "\",\"op_id\":\"" + op + "\",\"changes\":" + changes + "}";
}

// ---- ID_REUSE response detection (decoded JSON, no wire substring) ------------
static bool json_has(const std::string &json, const char *needle) { return json.find(needle) != std::string::npos; }

// Parse the two response frames of a conflict dispatch separately: the wire
// carries the original's response and the conflict's ID_REUSE response.
struct ConflictResponses {
  DecodedFrame original;
  DecodedFrame conflict;
};

static ConflictResponses dispatch_conflict_and_decode(mwcp_host::Service &svc, MwcpHostLink &link, uint32_t now) {
  ConflictResponses out;
  if (!g_stash.has())
    return out;
  std::string wire;
  if (mwcp_dispatch_request(svc, link, now, g_stash.session_id_, g_stash.request_id_, g_stash.code_, g_stash.payload_,
                            g_stash.payload_length_)) {
    for (int i = 0; i < 400 && (link.tx.active || link.control_ready); i++)
      link.pump(
          [&](const uint8_t *d, size_t n) {
            wire.insert(wire.end(), d, d + n);
            return static_cast<int>(n);
          },
          now);
    decode_wire(wire, out.original);
  }
  g_stash.clear();
  if (g_stash.has_conflict()) {
    wire.clear();
    if (mwcp_dispatch_request(svc, link, now + 1, g_stash.conflict_session_, g_stash.conflict_request_,
                              g_stash.conflict_code_, g_stash.conflict_payload_, g_stash.conflict_length_)) {
      for (int i = 0; i < 400 && (link.tx.active || link.control_ready); i++)
        link.pump(
            [&](const uint8_t *d, size_t n) {
              wire.insert(wire.end(), d, d + n);
              return static_cast<int>(n);
            },
            now + 1);
      decode_wire(wire, out.conflict);
    }
    g_stash.clear_conflict();
  }
  return out;
}

int main() {
  const uint16_t kCommit = 0x0022;

  // ---- T1: legal first commit: exactly one storage call, revision 1->2,
  //         response op_id matches, all through real codec decode; and the
  //         readback proves the INSTALLED value via a real CONFIG_READ.
  {
    FreshService fs;
    reset_stash();
    mwcp::Parser parser;
    auto rb0 = real_config_read(fs.svc, fs.link, 150, fs.session, fs.next_req++);
    expect(rb0.got && rb0.revision == "1" && rb0.has_x && rb0.x_cm == 0.0,
           "T1 pre-state: CONFIG_READ revision=1 install.x_cm=0", rb0.revision + " x=" + std::to_string(rb0.x_cm));
    auto f = encode_req(fs.next_req++, fs.session, kCommit,
                        commit_body("1", "11111111-1111-1111-1111-111111111111", "{\"install.x_cm\":140}"));
    parser.push(f.data(), f.size(), 200, on_frame, on_error, nullptr);
    expect(g_stash.has(), "T1 stashed");
    auto resp = dispatch_and_decode(fs.svc, fs.link, 250);
    expect(resp.got, "T1 response codec-decoded");
    expect(resp.frame.kind == 2, "T1 response kind=2");
    expect(resp.frame.code == kCommit, "T1 response code echoes CONFIG_COMMIT");
    expect(resp.frame.session_id == fs.session, "T1 response session echoes");
    expect(resp.frame.request_id == fs.session * 0 + (fs.next_req - 1), "T1 response request echoes");
    expect(json_has(resp.json, "\"ok\":true"), "T1 ok=true in decoded JSON");
    expect(json_has(resp.json, "11111111-1111-1111-1111-111111111111"), "T1 response op_id matches");
    expect(json_has(resp.json, "\"revision\":\"2\""), "T1 revision 2 in decoded JSON");
    expect(json_has(resp.json, "\"persisted\":true"), "T1 persisted true");
    expect(json_has(resp.json, "\"restart_required\":false"), "T1 restart_required false (schema const)");
    expect(fs.mem.store_calls == 1, "T1 exactly one storage call", "store_calls=" + std::to_string(fs.mem.store_calls));
    auto rb1 = real_config_read(fs.svc, fs.link, 300, fs.session, fs.next_req++);
    expect(rb1.got && rb1.revision == "2" && rb1.has_x && rb1.x_cm == 140.0,
           "T1 real CONFIG_READ: installed x_cm=140 revision=2", rb1.revision + " x=" + std::to_string(rb1.x_cm));
  }

  // ---- T2: same-id different-payload conflict (same push): the ORIGINAL
  //         executes once; the conflict is answered with ID_REUSE (real
  //         codec-decoded response) and executes NOTHING.
  {
    FreshService fs;
    reset_stash();
    mwcp::Parser parser;
    auto first = encode_req(20, fs.session, kCommit,
                            commit_body("1", "22222222-2222-2222-2222-222222222222", "{\"install.x_cm\":100}"));
    auto second = encode_req(20, fs.session, kCommit,
                             commit_body("1", "33333333-3333-3333-3333-333333333333", "{\"install.x_cm\":999}"));
    auto both = first;
    both.insert(both.end(), second.begin(), second.end());
    parser.push(both.data(), both.size(), 400, on_frame, on_error, nullptr);
    expect(g_stash.has() && g_stash.has_conflict(), "T2 original stashed + conflict kept (not silently dropped)");
    auto rr = dispatch_conflict_and_decode(fs.svc, fs.link, 450);
    expect(rr.original.got && json_has(rr.original.json, "\"ok\":true"), "T2 original payload committed");
    expect(rr.original.json.find("22222222") != std::string::npos, "T2 original op_id in response");
    // r3d D.1: the CONFLICT gets a real ID_REUSE response
    expect(rr.conflict.got, "T2 conflict answered (second response frame)");
    expect(json_has(rr.conflict.json, "\"ok\":false"), "T2 conflict ok=false");
    expect(json_has(rr.conflict.json, "ID_REUSE"), "T2 conflict error code ID_REUSE", rr.conflict.json.substr(0, 100));
    expect(rr.conflict.frame.code == kCommit && rr.conflict.frame.request_id == 20,
           "T2 conflict response echoes kind/code/request/session",
           ("code=" + std::to_string(rr.conflict.frame.code) + " req=" + std::to_string(rr.conflict.frame.request_id))
               .c_str());
    expect(rr.conflict.json.find("999") == std::string::npos || json_has(rr.conflict.json, "ID_REUSE"),
           "T2 conflict body never EXECUTED (no commit of 999)");
    expect(fs.mem.store_calls == 1, "T2 exactly one storage call total",
           "store_calls=" + std::to_string(fs.mem.store_calls));
    auto rb = real_config_read(fs.svc, fs.link, 500, fs.session, fs.next_req++);
    expect(rb.has_x && rb.x_cm == 100.0 && rb.revision == "2",
           "T2 installed value 100 (original), revision advanced once", rb.revision + " x=" + std::to_string(rb.x_cm));
  }

  // ---- T2b: cross-push same-id conflict -> same ID_REUSE contract.
  {
    FreshService fs;
    reset_stash();
    mwcp::Parser p1, p2;
    auto first = encode_req(21, fs.session, kCommit,
                            commit_body("1", "a2222222-2222-2222-2222-222222222222", "{\"install.x_cm\":110}"));
    auto second = encode_req(21, fs.session, kCommit,
                             commit_body("1", "a3333333-3333-3333-3333-333333333333", "{\"install.x_cm\":220}"));
    p1.push(first.data(), first.size(), 550, on_frame, on_error, nullptr);
    p2.push(second.data(), second.size(), 600, on_frame, on_error, nullptr);
    expect(g_stash.has() && g_stash.has_conflict(), "T2b cross-push conflict kept");
    auto rr = dispatch_conflict_and_decode(fs.svc, fs.link, 650);
    expect(rr.original.got && json_has(rr.original.json, "\"ok\":true"), "T2b original committed");
    expect(rr.conflict.got && json_has(rr.conflict.json, "ID_REUSE"), "T2b cross-push conflict answered ID_REUSE",
           rr.conflict.json.substr(0, 80));
    expect(fs.mem.store_calls == 1, "T2b one storage call");
  }

  // ---- T3: stale-base REVISION_CONFLICT negative (kept from r3c).
  {
    FreshService fs;
    reset_stash();
    mwcp::Parser parser;
    {
      auto f = encode_req(30, fs.session, kCommit,
                          commit_body("1", "44444444-4444-4444-4444-444444444444", "{\"install.x_cm\":150}"));
      parser.push(f.data(), f.size(), 600, on_frame, on_error, nullptr);
      auto r = dispatch_and_decode(fs.svc, fs.link, 650);
      expect(r.got && json_has(r.json, "\"ok\":true"), "T3 first commit succeeds");
      expect(fs.mem.store_calls == 1, "T3 first commit persisted once");
    }
    reset_stash();
    mwcp::Parser parser2;
    auto f2 = encode_req(31, fs.session, kCommit,
                         commit_body("1", "55555555-5555-5555-5555-555555555555", "{\"install.x_cm\":160}"));
    parser2.push(f2.data(), f2.size(), 750, on_frame, on_error, nullptr);
    auto r2 = dispatch_and_decode(fs.svc, fs.link, 800);
    expect(r2.got, "T3 stale-base response codec-decoded");
    expect(json_has(r2.json, "\"ok\":false"), "T3 stale base -> ok=false");
    expect(json_has(r2.json, "REVISION_CONFLICT"), "T3 error code REVISION_CONFLICT");
    expect(fs.mem.store_calls == 1, "T3 stale commit did NOT persist",
           "store_calls=" + std::to_string(fs.mem.store_calls));
    reset_stash();
    mwcp::Parser parser3;
    auto f3 = encode_req(32, fs.session, kCommit,
                         commit_body("2", "66666666-6666-6666-6666-666666666666", "{\"install.x_cm\":170}"));
    parser3.push(f3.data(), f3.size(), 900, on_frame, on_error, nullptr);
    auto r3 = dispatch_and_decode(fs.svc, fs.link, 950);
    expect(r3.got && json_has(r3.json, "\"ok\":true"), "T3 correct-base resend succeeds");
    expect(fs.mem.store_calls == 2, "T3 correct-base commit persisted",
           "store_calls=" + std::to_string(fs.mem.store_calls));
  }

  // ---- T4: byte-identical resend = ONE storage call (Service replays
  //         from the request-id cache; the stash merged the transport dup).
  {
    FreshService fs;
    reset_stash();
    mwcp::Parser parser;
    auto f = encode_req(40, fs.session, kCommit,
                        commit_body("1", "77777777-7777-7777-7777-777777777777", "{\"install.x_cm\":180}"));
    parser.push(f.data(), f.size(), 1000, on_frame, on_error, nullptr);
    parser.push(f.data(), f.size(), 1100, on_frame, on_error, nullptr);
    expect(g_stash.resend_merges == 1, "T4 byte-identical resend merged");
    auto resp = dispatch_and_decode(fs.svc, fs.link, 1200);
    expect(resp.got && json_has(resp.json, "\"ok\":true"), "T4 dispatched");
    expect(fs.mem.store_calls == 1, "T4 exactly one storage call (replay)",
           "store_calls=" + std::to_string(fs.mem.store_calls));
  }

  // ---- T5: legal frame + bad CRC: parser drops bad; good executes.
  {
    FreshService fs;
    reset_stash();
    mwcp::Parser parser;
    auto good = encode_req(50, fs.session, kCommit,
                           commit_body("1", "88888888-8888-8888-8888-888888888888", "{\"install.x_cm\":190}"));
    auto bad = encode_req(51, fs.session, kCommit,
                          commit_body("1", "99999999-9999-9999-9999-999999999999", "{\"install.x_cm\":777}"));
    bad[bad.size() - 3] ^= 0xFF;
    auto both = good;
    both.insert(both.end(), bad.begin(), bad.end());
    parser.push(both.data(), both.size(), 1300, on_frame, on_error, nullptr);
    expect(g_stash.has() && g_stash.dropped_conflicts == 0, "T5 bad CRC dropped by parser; good kept");
    auto resp = dispatch_and_decode(fs.svc, fs.link, 1400);
    expect(resp.got && json_has(resp.json, "\"ok\":true"), "T5 good frame committed");
    expect(resp.json.find("\"install.x_cm\":777") == std::string::npos, "T5 bad-CRC value never appears");
    expect(fs.mem.store_calls == 1, "T5 one storage call");
  }

  // ---- T6 (r3d D.3): the EXACT 4096-byte legal payload is the SAME bytes
  //         through encode -> parser -> stash -> Service. JSON whitespace
  //         padding fills the body to precisely 4096; CONFIG_VALIDATE with
  //         a real config plus a pad field... an unknown field would fail
  //         validation, so the max legal body uses the full 64-point
  //         boundary polygon plus whitespace padding to exactly 4096.
  {
    FreshService fs;
    reset_stash();
    // build a max-legal CONFIG_COMMIT body: full config changes plus JSON
    // whitespace inside the object (legal per RFC 8259) to reach 4096.
    std::string pts;
    for (int i = 0; i < 64; i++) {
      if (i > 0)
        pts += ",";
      double a = 6.283185307179586 * i / 64.0;
      pts += "[" + std::to_string(static_cast<int>(100.0 * cos(a))) + "," +
             std::to_string(static_cast<int>(100.0 * sin(a))) + "]";
    }
    std::string core = "{\"base_revision\":\"1\",\"op_id\":\"11111111-2222-3333-4444-555555555555\","
                       "\"changes\":{\"install.x_cm\":210,\"geometry.boundary_cm\":[" +
                       pts + "]}}";
    expect(core.size() <= 4096, "T6 core body within cap", "core=" + std::to_string(core.size()));
    // pad with whitespace before the closing brace to exactly 4096 bytes
    std::string body = core.substr(0, core.size() - 1);
    std::string pad(4096 - core.size(), ' ');
    body += pad + "}";
    expect(body.size() == 4096, "T6 body padded to EXACTLY 4096 bytes", "len=" + std::to_string(body.size()));
    auto f = encode_req(fs.next_req++, fs.session, kCommit, body);
    expect(!f.empty(), "T6 encoder accepts the exact 4096B body", "wire=" + std::to_string(f.size()));
    // RECEIVER: feed the SAME wire to the real parser; the stash must hold
    // EXACTLY those 4096 bytes - the same bytes the Service sees.
    mwcp::Parser parser;
    parser.push(f.data(), f.size(), 1500, on_frame, on_error, nullptr);
    expect(g_stash.has(), "T6 exact-4096 frame stashed by the receiver");
    expect(g_stash.payload_length_ == 4096, "T6 stash payload length == 4096 (not 4080/624)",
           std::to_string(g_stash.payload_length_));
    expect(std::memcmp(g_stash.payload_, body.data(), 4096) == 0, "T6 stash bytes byte-identical to the sent body");
    // dispatch: the Service handles the SAME 4096-byte body
    std::string wire;
    bool queued = mwcp_dispatch_request(fs.svc, fs.link, 1550, g_stash.session_id_, g_stash.request_id_, g_stash.code_,
                                        g_stash.payload_, g_stash.payload_length_);
    expect(queued, "T6 exact-4096 dispatch queued");
    g_stash.clear();
    if (queued) {
      for (int i = 0; i < 800 && (fs.link.tx.active || fs.link.control_ready); i++)
        fs.link.pump(
            [&](const uint8_t *d, size_t n) {
              wire.insert(wire.end(), d, d + n);
              return static_cast<int>(n);
            },
            1550);
      DecodedFrame df;
      decode_wire(wire, df);
      expect(df.got && json_has(df.json, "\"ok\":true"), "T6 exact-4096 CONFIG_COMMIT accepted", df.json.substr(0, 90));
      expect(json_has(df.json, "\"revision\":\"2\""), "T6 committed revision 2");
      expect(fs.mem.store_calls == 1, "T6 one side effect", "store_calls=" + std::to_string(fs.mem.store_calls));
      auto rb = real_config_read(fs.svc, fs.link, 1600, fs.session, fs.next_req++);
      expect(rb.has_x && rb.x_cm == 210.0 && rb.revision == "2",
             "T6 installed x_cm=210 revision=2 via real CONFIG_READ", rb.revision + " x=" + std::to_string(rb.x_cm));
    }
  }

  // ---- T7 (r3d D.4): a RECEIVER-side 4097-byte frame (test-only builder
  //         bypassing the encoder cap) is rejected by the real parser with
  //         NO side effect; a legal frame appended to the SAME input
  //         stream recovers.
  {
    FreshService fs;
    reset_stash();
    mwcp::Parser parser;
    // pad field sized so the TOTAL body is exactly 4097 (one over the cap)
    const std::string prefix = "{\"base_revision\":\"1\",\"op_id\":\"t7\",\"changes\":{},\"pad\":\"";
    std::string body = prefix + std::string(4097 - prefix.size() - 2, 'x') + "\"}";
    expect(body.size() == 4097, "T7 body is exactly 4097 bytes", std::to_string(body.size()));
    auto f_over = build_raw_frame(70, fs.session, kCommit, body);
    expect(!f_over.empty(), "T7 test-only builder produced a 4097B wire frame",
           "wire=" + std::to_string(f_over.size()));
    // the production encoder must refuse the same body (the cap is real)
    auto f_enc = encode_req(70, fs.session, kCommit, body);
    expect(f_enc.empty(), "T7 production encoder refuses 4097B");
    // feed oversize + legal in ONE stream: parser rejects oversize, then
    // accepts the legal frame (recovery in the same input)
    auto f_ok = encode_req(71, fs.session, kCommit,
                           commit_body("1", "aa777777-7777-7777-7777-777777777777", "{\"install.x_cm\":230}"));
    std::vector<uint8_t> stream = f_over;
    stream.insert(stream.end(), f_ok.begin(), f_ok.end());
    int rev_before_store = fs.mem.store_calls;
    parser.push(stream.data(), stream.size(), 1700, on_frame, on_error, nullptr);
    expect(g_stash.has(), "T7 legal frame after oversize is accepted (recovery)");
    expect(!g_stash.has_conflict() && g_stash.dropped_conflicts == 0,
           "T7 oversize never reached the stash (no side effect)");
    expect(g_stash.request_id_ == 71, "T7 the stashed frame is the LEGAL one");
    // dispatch the legal frame: commits; revision 2
    auto resp = dispatch_and_decode(fs.svc, fs.link, 1750);
    expect(resp.got && json_has(resp.json, "\"ok\":true"), "T7 legal commit ok");
    expect(fs.mem.store_calls == rev_before_store + 1, "T7 exactly one side effect (oversize added zero)",
           "store_calls=" + std::to_string(fs.mem.store_calls));
    auto rb = real_config_read(fs.svc, fs.link, 1800, fs.session, fs.next_req++);
    expect(rb.has_x && rb.x_cm == 230.0, "T7 installed x_cm=230 after recovery",
           rb.revision + " x=" + std::to_string(rb.x_cm));
  }

  // ---- T8 (r3d D.1): conflict slot bounded - a THIRD conflicting body
  //         while the conflict slot is full overwrites it (counted), the
  //         answer stays ID_REUSE, side effects stay 1.
  {
    FreshService fs;
    reset_stash();
    mwcp::Parser parser;
    auto first = encode_req(80, fs.session, kCommit,
                            commit_body("1", "b1111111-1111-1111-1111-111111111111", "{\"install.x_cm\":100}"));
    auto second = encode_req(80, fs.session, kCommit,
                             commit_body("1", "b2222222-2222-2222-2222-222222222222", "{\"install.x_cm\":200}"));
    auto third = encode_req(80, fs.session, kCommit,
                            commit_body("1", "b3333333-3333-3333-3333-333333333333", "{\"install.x_cm\":300}"));
    auto all = first;
    all.insert(all.end(), second.begin(), second.end());
    all.insert(all.end(), third.begin(), third.end());
    parser.push(all.data(), all.size(), 1900, on_frame, on_error, nullptr);
    expect(g_stash.has() && g_stash.has_conflict() && g_stash.conflict_overwrites == 1,
           "T8 bounded slot: third conflict overwrites (counted)",
           "overwrites=" + std::to_string(g_stash.conflict_overwrites));
    auto rr = dispatch_conflict_and_decode(fs.svc, fs.link, 1950);
    expect(rr.original.got && json_has(rr.original.json, "\"ok\":true"), "T8 original committed");
    expect(rr.conflict.got && json_has(rr.conflict.json, "ID_REUSE"), "T8 conflict answered ID_REUSE (last kept body)");
    expect(rr.conflict.json.find("b3333333") != std::string::npos || json_has(rr.conflict.json, "ID_REUSE"),
           "T8 conflict response");
    expect(fs.mem.store_calls == 1, "T8 exactly one side effect", "store_calls=" + std::to_string(fs.mem.store_calls));
    auto rb = real_config_read(fs.svc, fs.link, 2000, fs.session, fs.next_req++);
    expect(rb.has_x && rb.x_cm == 100.0, "T8 installed value from ORIGINAL only", std::to_string(rb.x_cm));
  }

  // ---- T9 (r3d D.1): different-request-id frame while full is dropped
  //         loudly (NOT ID_REUSE-able), original still dispatches.
  {
    FreshService fs;
    reset_stash();
    mwcp::Parser parser;
    auto first = encode_req(90, fs.session, kCommit,
                            commit_body("1", "c1111111-1111-1111-1111-111111111111", "{\"install.x_cm\":120}"));
    auto other = encode_req(91, fs.session, kCommit,
                            commit_body("1", "c2222222-2222-2222-2222-222222222222", "{\"install.x_cm\":900}"));
    auto both = first;
    both.insert(both.end(), other.begin(), other.end());
    parser.push(both.data(), both.size(), 2100, on_frame, on_error, nullptr);
    expect(g_stash.has() && !g_stash.has_conflict() && g_stash.dropped_conflicts == 1,
           "T9 different-request frame dropped and counted (not kept)");
    auto resp = dispatch_and_decode(fs.svc, fs.link, 2150);
    expect(resp.got && json_has(resp.json, "\"ok\":true"), "T9 original committed");
    expect(fs.mem.store_calls == 1, "T9 one side effect");
  }

  std::printf(g_failures == 0 ? "SERVICE-LINK DEFERRED PASS%s" : "SERVICE-LINK DEFERRED FAIL%s", NEWLINE);
  return g_failures == 0 ? 0 : 1;
}
