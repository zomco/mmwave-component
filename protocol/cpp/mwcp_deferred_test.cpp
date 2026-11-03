// G2-R3-01 integration test: real RX bytes -> real Parser -> deferred stash
// -> dispatch sink. Links the real mwcp_codec.cpp/mwcp_json.cpp (no ESPHome),
// and the stash callback reproduces the product's on_frame semantics exactly
// (mmwave_host/mmwave_host.cpp: stash into DeferredRequest).
//
// The review's exact counterexample lives in test 1: one push carrying a
// legal request=42 frame with payload {"x":1} followed by a bad-CRC frame of
// the same length carrying {"x":2}; only the original legal payload may be
// dispatched.

#include <cstdio>
#include <cstring>
#include <string>
#include <vector>

#include "deferred_request.h"
using namespace esphome;

namespace {

int g_failures = 0;

struct Sink {
  bool dispatched = false;
  uint32_t session = 0;
  uint32_t request = 0;
  uint16_t code = 0;
  std::string payload;
};

// Product-shaped callback: stash into DeferredRequest exactly like
// MwcpHost::on_frame (shallow-copy is what the review proved broken).
esphome::mmwave_host::DeferredRequest g_stash;
int g_callbacks = 0;
int g_errors = 0;

void on_frame(const mwcp::Frame &frame, void *) {
  if (frame.kind != 1 || frame.payload == nullptr)
    return;
  g_callbacks++;
  g_stash.stash(frame);
}

void on_error(mwcp::Status, void *) { g_errors++; }

// Dispatch = copy the stashed request out into the sink (what loop() does,
// minus the Service which needs ESPHome).
Sink dispatch_stash() {
  Sink sink;
  if (!g_stash.has())
    return sink;
  sink.dispatched = true;
  sink.session = g_stash.session_id_;
  sink.request = g_stash.request_id_;
  sink.code = g_stash.code_;
  sink.payload.assign(reinterpret_cast<const char *>(g_stash.payload_), g_stash.payload_length_);
  return sink;
}

void feed(mwcp::Parser &parser, const std::vector<uint8_t> &bytes, uint32_t now = 100) {
  if (bytes.empty())
    return;
  parser.push(bytes.data(), bytes.size(), now, on_frame, on_error, nullptr);
  parser.poll(now, on_error, nullptr);
}

std::vector<uint8_t> encode(uint32_t request, uint32_t session, uint16_t code, const std::string &payload) {
  std::vector<uint8_t> wire(mwcp::kMaxCobs);
  size_t wire_len = 0;
  std::vector<uint8_t> decoded(mwcp::kMaxDecoded);
  size_t decoded_len = 0;
  mwcp::EncodeInput in{};
  in.kind = 1;
  in.session_id = session;
  in.request_id = request;
  in.code = code;
  in.payload = reinterpret_cast<const uint8_t *>(payload.data());
  in.payload_len = payload.size();
  in.wire_seq = 0;
  in.check_json = false;
  mwcp::Status enc_st =
      mwcp::encode_frame(in, wire.data(), wire.size(), &wire_len, decoded.data(), decoded.size(), &decoded_len);
  if (enc_st != mwcp::kOk) {
    std::printf("ENCODE FAILED for request %u status=%d\n", request, static_cast<int>(enc_st));
    g_failures++;
    return {};
  }
  wire.resize(wire_len);
  return wire;
}

void reset() {
  g_stash = esphome::mmwave_host::DeferredRequest{};
  g_callbacks = 0;
  g_errors = 0;
}

void expect(bool ok, const char *name, const std::string &detail = "") {
  std::printf("[%s] %s %s\n", ok ? "PASS" : "FAIL", name, detail.c_str());
  if (!ok)
    g_failures++;
}

}  // namespace

int main() {
  const uint16_t kCodeCommit = 0x0022;  // CONFIG_COMMIT

  // --- Test 1: the review's exact counterexample --------------------------
  // One push: legal request=42 {"x":1} + same-length bad-CRC frame {"x":2}.
  reset();
  {
    mwcp::Parser parser;
    auto good = encode(42, 1, kCodeCommit, "{\"x\":1}");
    auto bad = encode(43, 1, kCodeCommit, "{\"x\":2}");
    bad[bad.size() - 3] ^= 0xFF;  // corrupt CRC (last bytes before delimiter)
    auto both = good;
    both.insert(both.end(), bad.begin(), bad.end());
    feed(parser, both);
    Sink sink = dispatch_stash();
    expect(g_callbacks == 1 && g_errors == 1, "T1 bad-CRC trailer: one callback one error",
           "callbacks=" + std::to_string(g_callbacks) + " errors=" + std::to_string(g_errors));
    expect(sink.dispatched && sink.request == 42 && sink.payload == "{\"x\":1}", "T1 only the legal payload dispatched",
           "payload=" + sink.payload + " request=" + std::to_string(sink.request));
    expect(sink.payload.find('2') == std::string::npos, "T1 no bad-frame byte leaked");
  }

  // --- Test 2: legal + trailing bad-COBs frame ----------------------------
  reset();
  {
    mwcp::Parser parser;
    auto good = encode(7, 1, kCodeCommit, "{\"a\":1}");
    auto bad = encode(8, 1, kCodeCommit, "{\"a\":2}");
    bad[2] ^= 0xFF;  // corrupt the COBS block
    auto both = good;
    both.insert(both.end(), bad.begin(), bad.end());
    feed(parser, both);
    Sink sink = dispatch_stash();
    expect(sink.dispatched && sink.request == 7 && sink.payload == "{\"a\":1}",
           "T2 bad-COBs trailer cannot rewrite the stash", "payload=" + sink.payload);
  }

  // --- Test 3: legal + trailing raw noise ---------------------------------
  reset();
  {
    mwcp::Parser parser;
    auto good = encode(9, 1, kCodeCommit, "{\"n\":1}");
    auto both = good;
    const char *noise = "\x00garbage\xff\x00noise";
    both.insert(both.end(), noise, noise + 15);
    feed(parser, both);
    Sink sink = dispatch_stash();
    expect(sink.dispatched && sink.payload == "{\"n\":1}", "T3 trailing noise cannot rewrite the stash",
           "payload=" + sink.payload);
  }

  // --- Test 4: two legal frames (different requests) in one push ----------
  reset();
  {
    mwcp::Parser parser;
    auto first = encode(10, 1, kCodeCommit, "{\"first\":1}");
    auto second = encode(11, 1, kCodeCommit, "{\"second\":1}");
    auto both = first;
    both.insert(both.end(), second.begin(), second.end());
    feed(parser, both);
    Sink sink = dispatch_stash();
    // The slot was full when the second arrived: a DIFFERENT request id is
    // not ID_REUSE-able (rpc_inflight=1 makes it a protocol violation), so
    // it is dropped loudly and counted (r3d contract).
    expect(g_stash.dropped_conflicts == 1, "T4 different request dropped loudly",
           "drops=" + std::to_string(g_stash.dropped_conflicts));
    expect(sink.dispatched && sink.request == 10 && sink.payload == "{\"first\":1}", "T4 first request intact",
           "payload=" + sink.payload);
  }

  // --- Test 5: same-request resend overwrites (idempotent) ----------------
  reset();
  {
    mwcp::Parser parser;
    auto first = encode(20, 1, kCodeCommit, "{\"try\":1}");
    auto resend = encode(20, 1, kCodeCommit, "{\"try\":1}");
    auto both = first;
    both.insert(both.end(), resend.begin(), resend.end());
    feed(parser, both);
    Sink sink = dispatch_stash();
    expect(g_stash.resend_merges == 1, "T5 byte-identical resend merged (idempotent)",
           "overwrites=" + std::to_string(g_stash.resend_merges));
    expect(sink.dispatched && sink.request == 20 && sink.payload == "{\"try\":1}",
           "T5 payload unchanged by identical resend", "callbacks=" + std::to_string(g_callbacks));
  }

  // --- Test 6: max payload -------------------------------------------------
  reset();
  {
    mwcp::Parser parser;
    std::string big = "{\"pad\":\"" + std::string(4080, 'z') + "\"}";
    auto frame = encode(30, 1, kCodeCommit, big);
    feed(parser, frame);
    Sink sink = dispatch_stash();
    expect(sink.dispatched && sink.payload == big && sink.payload.size() <= 4096, "T6 max payload stashed byte-exact",
           "len=" + std::to_string(sink.payload.size()));
  }

  // --- Test 7: chunk boundaries (1-byte pushes) ---------------------------
  reset();
  {
    mwcp::Parser parser;
    auto frame = encode(31, 1, kCodeCommit, "{\"chunked\":true}");
    uint32_t t = 100;
    for (size_t i = 0; i < frame.size(); i++) {
      std::vector<uint8_t> one{frame[i]};
      parser.push(one.data(), 1, t++, on_frame, on_error, nullptr);
      parser.poll(t, on_error, nullptr);
    }
    Sink sink = dispatch_stash();
    expect(g_callbacks == 1 && sink.dispatched && sink.payload == "{\"chunked\":true}",
           "T7 byte-by-byte chunking delivers once, stash intact", "callbacks=" + std::to_string(g_callbacks));
  }

  // --- Test 8: legal frame now, different legal frame in a LATER push -----
  reset();
  {
    mwcp::Parser parser;
    feed(parser, encode(40, 1, kCodeCommit, "{\"kept\":1}"));
    feed(parser, encode(41, 1, kCodeCommit, "{\"late\":1}"));
    Sink sink = dispatch_stash();
    expect(g_stash.dropped_conflicts == 1 && sink.request == 40, "T8 later different request cannot displace the stash",
           "drops=" + std::to_string(g_stash.dropped_conflicts));
  }

  // --- Test 9: same id resent with a DIFFERENT payload (later push) -----
  // r3d contract: the conflict is NOT silently dropped - it is kept in the
  // bounded conflict slot and the loop forwards it to the Service, whose
  // replay cache answers ID_REUSE. The original pending request and payload
  // are untouched.
  reset();
  {
    mwcp::Parser parser;
    feed(parser, encode(50, 1, kCodeCommit, "{\"v\":1}"));
    feed(parser, encode(50, 1, kCodeCommit, "{\"v\":2}"));
    Sink sink = dispatch_stash();
    expect(g_stash.has_conflict() && g_stash.conflict_forwards == 1 && g_stash.resend_merges == 0 &&
               g_stash.dropped_conflicts == 0,
           "T9 same-id different-payload kept as a conflict (ID_REUSE path)",
           "forwards=" + std::to_string(g_stash.conflict_forwards) +
               " drops=" + std::to_string(g_stash.dropped_conflicts));
    expect(sink.dispatched && sink.request == 50 && sink.payload == "{\"v\":1}",
           "T9 the ORIGINAL payload is dispatched", "payload=" + sink.payload);
    // the kept conflict carries the conflicting body and identity
    std::string conflict_body(reinterpret_cast<const char *>(g_stash.conflict_payload_), g_stash.conflict_length_);
    expect(conflict_body == "{\"v\":2}" && g_stash.conflict_request_ == 50,
           "T9 conflict slot holds the second body for the ID_REUSE answer", "conflict=" + conflict_body);
  }

  // --- Test 9b: same id + different payload in the SAME push -------------
  reset();
  {
    mwcp::Parser parser;
    auto first = encode(51, 1, kCodeCommit, "{\"a\":1}");
    auto second = encode(51, 1, kCodeCommit, "{\"a\":2}");
    auto both = first;
    both.insert(both.end(), second.begin(), second.end());
    feed(parser, both);
    Sink sink = dispatch_stash();
    expect(sink.dispatched && sink.payload == "{\"a\":1}", "T9b same-push same-id different-payload keeps the original",
           "payload=" + sink.payload + " forwards=" + std::to_string(g_stash.conflict_forwards));
    expect(g_stash.has_conflict(), "T9b the second body is kept for the Service's ID_REUSE answer");
  }

  // --- Test 9c: same id, different payload LENGTH -------------------------
  reset();
  {
    mwcp::Parser parser;
    feed(parser, encode(52, 1, kCodeCommit, "{\"pad\":123}"));
    feed(parser, encode(52, 1, kCodeCommit, "{\"pad\":1}"));
    Sink sink = dispatch_stash();
    expect(sink.payload == "{\"pad\":123}", "T9c same-id shorter payload is a conflict (length mismatch)",
           "payload=" + sink.payload);
    expect(g_stash.has_conflict(), "T9c the shorter body is kept for the ID_REUSE answer");
  }

  // --- Test 9d: same id, different CODE -----------------------------------
  reset();
  {
    mwcp::Parser parser;
    feed(parser, encode(53, 1, kCodeCommit, "{\"x\":1}"));
    feed(parser, encode(53, 1, 0x0021, "{\"x\":1}"));  // CONFIG_VALIDATE
    Sink sink = dispatch_stash();
    expect(sink.payload == "{\"x\":1}" && sink.code == kCodeCommit,
           "T9d same-id different-code is a conflict (original code kept)", "code=" + std::to_string(sink.code));
    expect(g_stash.has_conflict() && g_stash.conflict_code_ == 0x0021,
           "T9d the different-code frame is kept for the ID_REUSE answer");
  }

  // --- Test 9e: byte-identical resend across chunked pushes --------------
  reset();
  {
    mwcp::Parser parser;
    auto frame = encode(54, 1, kCodeCommit, "{\"same\":true}");
    feed(parser, frame);
    uint32_t tt = 200;
    for (size_t i = 0; i < frame.size(); i++) {
      std::vector<uint8_t> one{frame[i]};
      parser.push(one.data(), 1, tt++, on_frame, on_error, nullptr);
      parser.poll(tt, on_error, nullptr);
    }
    Sink sink = dispatch_stash();
    expect(g_stash.resend_merges == 1 && sink.payload == "{\"same\":true}",
           "T9e byte-identical chunked resend merges, payload unchanged",
           "merges=" + std::to_string(g_stash.resend_merges));
  }

  std::printf(g_failures == 0 ? "DEFERRED INTEGRATION PASS\n" : "DEFERRED INTEGRATION FAIL\n");
  return g_failures == 0 ? 0 : 1;
}
