#include "mwcp_codec.h"
#include "mwcp_json.h"
#include "r60abd1_transform.h"

#include <cmath>
#include <cstdio>
#include <cstring>
#include <string>
#include <vector>

#ifdef _WIN32
#include <windows.h>
#endif

namespace {

int g_failed = 0;

void expect(bool ok, const char *message) {
  if (ok)
    return;
  std::fprintf(stderr, "FAIL %s\n", message);
  g_failed++;
}

std::string read_file(const char *path) {
  FILE *file = std::fopen(path, "rb");
  if (!file)
    return "";
  std::string data;
  char buf[4096];
  size_t n = 0;
  while ((n = std::fread(buf, 1, sizeof(buf), file)) > 0)
    data.append(buf, n);
  std::fclose(file);
  return data;
}

int hex_nibble(char c) {
  if (c >= '0' && c <= '9')
    return c - '0';
  if (c >= 'a' && c <= 'f')
    return c - 'a' + 10;
  if (c >= 'A' && c <= 'F')
    return c - 'A' + 10;
  return -1;
}

bool parse_hex(const std::string &hex, std::vector<uint8_t> *out) {
  out->clear();
  if (hex.size() % 2)
    return false;
  for (size_t i = 0; i < hex.size(); i += 2) {
    const int hi = hex_nibble(hex[i]);
    const int lo = hex_nibble(hex[i + 1]);
    if (hi < 0 || lo < 0)
      return false;
    out->push_back(static_cast<uint8_t>((hi << 4) | lo));
  }
  return true;
}

std::string to_hex(const uint8_t *data, size_t len) {
  static const char *digits = "0123456789abcdef";
  std::string out(len * 2, '0');
  for (size_t i = 0; i < len; i++) {
    out[i * 2] = digits[data[i] >> 4];
    out[i * 2 + 1] = digits[data[i] & 0x0f];
  }
  return out;
}

bool extract_string(const std::string &json, size_t from, const char *key, std::string *value, size_t *next) {
  const std::string pattern = std::string("\"") + key + "\"";
  const size_t at = json.find(pattern, from);
  if (at == std::string::npos)
    return false;
  size_t i = json.find(':', at + pattern.size());
  if (i == std::string::npos)
    return false;
  i++;
  while (i < json.size() && (json[i] == ' ' || json[i] == '\n' || json[i] == '\r' || json[i] == '\t'))
    i++;
  if (i >= json.size() || json[i] != '"')
    return false;
  i++;
  value->clear();
  while (i < json.size()) {
    const char c = json[i++];
    if (c == '"') {
      *next = i;
      return true;
    }
    if (c != '\\') {
      value->push_back(c);
      continue;
    }
    if (i >= json.size())
      return false;
    const char esc = json[i++];
    if (esc == 'u') {
      if (i + 4 > json.size())
        return false;
      unsigned unit = 0;
      for (int n = 0; n < 4; n++) {
        const int nib = hex_nibble(json[i++]);
        if (nib < 0)
          return false;
        unit = (unit << 4) | static_cast<unsigned>(nib);
      }
      if (unit < 0x80)
        value->push_back(static_cast<char>(unit));
      else if (unit < 0x800) {
        value->push_back(static_cast<char>(0xc0 | (unit >> 6)));
        value->push_back(static_cast<char>(0x80 | (unit & 0x3f)));
      } else {
        value->push_back(static_cast<char>(0xe0 | (unit >> 12)));
        value->push_back(static_cast<char>(0x80 | ((unit >> 6) & 0x3f)));
        value->push_back(static_cast<char>(0x80 | (unit & 0x3f)));
      }
      continue;
    }
    if (esc == '"' || esc == '\\' || esc == '/')
      value->push_back(esc);
    else if (esc == 'n')
      value->push_back('\n');
    else if (esc == 't')
      value->push_back('\t');
    else
      return false;
  }
  return false;
}

bool extract_uint(const std::string &json, size_t from, const char *key, unsigned long long *value, size_t *next) {
  const std::string pattern = std::string("\"") + key + "\"";
  const size_t at = json.find(pattern, from);
  if (at == std::string::npos)
    return false;
  size_t i = json.find(':', at + pattern.size());
  if (i == std::string::npos)
    return false;
  i++;
  while (i < json.size() && (json[i] == ' ' || json[i] == '\n'))
    i++;
  unsigned long long n = 0;
  bool any = false;
  while (i < json.size() && json[i] >= '0' && json[i] <= '9') {
    n = n * 10 + static_cast<unsigned>(json[i] - '0');
    i++;
    any = true;
  }
  if (!any)
    return false;
  *value = n;
  *next = i;
  return true;
}

struct Captured {
  std::vector<mwcp::Frame> frames;
  std::vector<std::string> payloads;
  int errors;
};

void on_frame(const mwcp::Frame &frame, void *user) {
  Captured *captured = static_cast<Captured *>(user);
  captured->frames.push_back(frame);
  captured->payloads.push_back(std::string(reinterpret_cast<const char *>(frame.payload), frame.payload_length));
}

void on_error(mwcp::Status, void *user) { static_cast<Captured *>(user)->errors++; }

void test_vectors(const std::string &json) {
  std::string ascii;
  size_t next = 0;
  expect(extract_string(json, 0, "ascii", &ascii, &next), "crc ascii");
  const uint32_t crc = mwcp::crc32c(reinterpret_cast<const uint8_t *>(ascii.data()), ascii.size());
  char crc_hex[9];
  std::snprintf(crc_hex, sizeof(crc_hex), "%08x", crc);
  std::string expected_crc;
  expect(extract_string(json, 0, "hex", &expected_crc, &next), "crc hex");
  expect(expected_crc == crc_hex, "crc32c check");

  size_t from = json.find("\"frames\"");
  expect(from != std::string::npos, "frames");
  for (int n = 0; n < 3; n++) {
    std::string id, payload, decoded_hex, wire_hex, crc_field;
    unsigned long long kind = 0, session = 0, request = 0, code = 0, seq = 0, payload_len = 0;
    expect(extract_string(json, from, "id", &id, &from), "id");
    expect(extract_uint(json, from, "kind", &kind, &from), "kind");
    expect(extract_uint(json, from, "session_id", &session, &from), "session");
    expect(extract_uint(json, from, "request_id", &request, &from), "request");
    expect(extract_uint(json, from, "code", &code, &from), "code");
    expect(extract_uint(json, from, "wire_seq", &seq, &from), "seq");
    expect(extract_string(json, from, "payload_text", &payload, &from), "payload");
    expect(extract_uint(json, from, "payload_utf8_length", &payload_len, &from), "len");
    expect(extract_string(json, from, "crc32c_hex", &crc_field, &from), "frame crc");
    expect(extract_string(json, from, "decoded_hex", &decoded_hex, &from), "decoded");
    expect(extract_string(json, from, "wire_hex", &wire_hex, &from), "wire");
    expect(payload.size() == payload_len, id.c_str());
    mwcp::EncodeInput input;
    input.kind = static_cast<uint8_t>(kind);
    input.session_id = static_cast<uint32_t>(session);
    input.request_id = static_cast<uint32_t>(request);
    input.code = static_cast<uint16_t>(code);
    input.wire_seq = static_cast<uint32_t>(seq);
    input.payload = reinterpret_cast<const uint8_t *>(payload.data());
    input.payload_len = payload.size();
    input.check_json = true;
    uint8_t wire[mwcp::kMaxWire];
    uint8_t decoded[mwcp::kMaxDecoded];
    size_t wire_len = 0, decoded_len = 0;
    const mwcp::Status status =
        mwcp::encode_frame(input, wire, sizeof(wire), &wire_len, decoded, sizeof(decoded), &decoded_len);
    expect(status == mwcp::kOk, "encode");
    expect(to_hex(decoded, decoded_len) == decoded_hex, "decoded bytes");
    expect(to_hex(wire, wire_len) == wire_hex, "wire bytes");
    std::vector<uint8_t> parsed;
    expect(parse_hex(wire_hex, &parsed), "parse wire");
    Captured captured;
    mwcp::Parser parser;
    parser.push(parsed.data(), parsed.size(), 0, on_frame, on_error, &captured);
    expect(captured.frames.size() == 1 && captured.payloads[0] == payload, "decode payload");
  }

  size_t cobs_at = json.find("\"cobs_cases\"");
  expect(cobs_at != std::string::npos, "cobs cases");
  for (int n = 0; n < 3; n++) {
    std::string id, decoded_hex, encoded_hex;
    expect(extract_string(json, cobs_at, "id", &id, &cobs_at), "cobs id");
    expect(extract_string(json, cobs_at, "decoded_hex", &decoded_hex, &cobs_at), "cobs decoded");
    expect(extract_string(json, cobs_at, "encoded_hex", &encoded_hex, &cobs_at), "cobs encoded");
    std::vector<uint8_t> decoded;
    expect(parse_hex(decoded_hex, &decoded), "cobs hex");
    uint8_t encoded[600];
    size_t encoded_len = 0;
    expect(mwcp::cobs_encode(decoded.data(), decoded.size(), encoded, sizeof(encoded), &encoded_len) == mwcp::kOk,
           "cobs encode");
    expect(to_hex(encoded, encoded_len) == encoded_hex, id.c_str());
  }
}

void test_limits_and_recovery() {
  std::vector<uint8_t> payload(mwcp::kMaxPayload, 'a');
  payload[0] = '{';
  payload[1] = '"';
  payload[2] = 'k';
  payload[3] = '"';
  payload[4] = ':';
  payload[5] = '"';
  payload[mwcp::kMaxPayload - 2] = '"';
  payload[mwcp::kMaxPayload - 1] = '}';
  mwcp::EncodeInput input = {1, 1, 2, 2, 1, payload.data(), payload.size(), true};
  uint8_t wire[mwcp::kMaxWire];
  uint8_t decoded[mwcp::kMaxDecoded];
  size_t wire_len = 0, decoded_len = 0;
  expect(mwcp::encode_frame(input, wire, sizeof(wire), &wire_len, decoded, sizeof(decoded), &decoded_len) == mwcp::kOk,
         "max payload");
  expect(decoded_len == mwcp::kMaxDecoded, "decoded limit");
  expect(wire_len <= mwcp::kMaxWire, "wire limit");
  input.payload_len = mwcp::kMaxPayload + 1;
  expect(mwcp::encode_frame(input, wire, sizeof(wire), &wire_len, decoded, sizeof(decoded), &decoded_len) ==
             mwcp::kPayloadTooLarge,
         "over payload");

  const char *bad[] = {"{\"a\":1,\"a\":2}", "[1]", "{\"n\":9007199254740993}", "{\"n\":1e999}"};
  const char *errors[] = {"duplicate_key", "root", "unsafe_integer", "unsafe_integer"};
  for (int i = 0; i < 4; i++) {
    expect(!mwcp::json_check(reinterpret_cast<const uint8_t *>(bad[i]), std::strlen(bad[i])), bad[i]);
    expect(std::strcmp(mwcp::json_error(), errors[i]) == 0, errors[i]);
  }
  const uint8_t bad_utf8[] = {'{', '"', 'a', '"', ':', '"', 0xff, '"', '}'};
  expect(!mwcp::json_check(bad_utf8, sizeof(bad_utf8)), "bad utf8 json");

  uint8_t block[508];
  std::memset(block, 0x11, sizeof(block));
  uint8_t encoded[600];
  uint8_t back[600];
  size_t encoded_len = 0, back_len = 0;
  expect(mwcp::cobs_encode(block, 254, encoded, sizeof(encoded), &encoded_len) == mwcp::kOk, "254");
  expect(encoded[0] == 0xff && encoded[encoded_len - 1] == 0x01, "254 code");
  expect(mwcp::cobs_decode(encoded, encoded_len, back, sizeof(back), &back_len) == mwcp::kOk && back_len == 254,
         "254 decode");
  expect(mwcp::cobs_encode(block, 508, encoded, sizeof(encoded), &encoded_len) == mwcp::kOk, "508");
  expect(mwcp::cobs_decode(encoded, encoded_len, back, sizeof(back), &back_len) == mwcp::kOk && back_len == 508,
         "508 decode");
}

void test_transform() {
  using esphome::r60abd1::CalibrationParams;
  using esphome::r60abd1::Vec2;
  using esphome::r60abd1::apply;
  const struct {
    float lx, ly, lz, x, y, z, yaw, pitch, roll, ex, ey, ez;
    bool inside;
  } cases[] = {
      {0, 100, 0, 10, 20, 220, 0, 0, 0, 10, 120, 220, true},
      {0, 100, 0, 0, 0, 0, 90, 0, 0, 100, 0, 0, true},
      {0, 100, 0, 0, 0, 200, 0, 90, 0, 0, 0, 300, true},
      {30, 0, 0, 0, 0, 220, 0, 0, 90, 0, 0, 190, true},
      {0, 150, 0, 5, -5, 100, 90, 0, 0, 155, -5, 100, false},
      {-40, -10, 5, 12, -8, 180, 30, 12, -8, -25.498558f, 4.880307f, 167.632462f, false},
  };
  for (size_t i = 0; i < sizeof(cases) / sizeof(cases[0]); i++) {
    CalibrationParams cal;
    cal.radar_x = cases[i].x;
    cal.radar_y = cases[i].y;
    cal.radar_z = cases[i].z;
    cal.yaw = cases[i].yaw;
    cal.pitch = cases[i].pitch;
    cal.roll = cases[i].roll;
    if (i == 0) {
      cal.polygon.push_back(Vec2{0, 0});
      cal.polygon.push_back(Vec2{100, 0});
      cal.polygon.push_back(Vec2{100, 200});
      cal.polygon.push_back(Vec2{0, 200});
    }
    const auto got = apply(cases[i].lx, cases[i].ly, cases[i].lz, cal);
    expect(std::fabs(got.room.x - cases[i].ex) < 1e-3, "room x");
    expect(std::fabs(got.room.y - cases[i].ey) < 1e-3, "room y");
    expect(std::fabs(got.room_z - cases[i].ez) < 1e-3, "room z");
    if (i == 0)
      expect(got.in_boundary, "inside");
  }
  CalibrationParams edge;
  edge.polygon.push_back(Vec2{0, 0});
  edge.polygon.push_back(Vec2{100, 0});
  edge.polygon.push_back(Vec2{100, 100});
  edge.polygon.push_back(Vec2{0, 100});
  const auto on_edge = apply(50, 0, 0, edge);
  const auto vertex = apply(0, 0, 0, edge);
  const auto outside = apply(150, 10, 0, edge);
  expect(on_edge.in_boundary && vertex.in_boundary && !outside.in_boundary, "edge policy");
}

void test_json_bounds_and_duplicates() {
  const char *bad[] = {"{\"a\":1, ", "{\"a\":1,\"\\u0061\":2}", "{\"n\":9007199254740993e0}",
                       "{\"n\":9007199254740993.0}"};
  const char *errors[] = {"truncated", "duplicate_key", "unsafe_integer", "unsafe_integer"};
  for (int i = 0; i < 4; i++) {
    expect(!mwcp::json_check(reinterpret_cast<const uint8_t *>(bad[i]), std::strlen(bad[i])), bad[i]);
    expect(std::strcmp(mwcp::json_error(), errors[i]) == 0, errors[i]);
  }
  const char *good = "{\"ok\":true}";
  for (size_t cut = 0; cut < std::strlen(good); cut++) {
    std::vector<uint8_t> exact_cut(good, good + cut);
    expect(!mwcp::json_check(exact_cut.empty() ? nullptr : exact_cut.data(), cut), "truncated prefix");
  }
  const char *samples_all[] = {"{\"a\":1}",           "[1,2]",     "\"abc\"", "\"a\\nb\"", "1.5e1",
                               "{\"k\":\"\\u4e2d\"}", "{\"a\":1, "};
  for (const char *sample : samples_all) {
    const size_t len = std::strlen(sample);
    for (size_t cut = 0; cut < len; cut++) {
      std::vector<uint8_t> exact_sample(sample, sample + cut);
      expect(!mwcp::json_check(exact_sample.empty() ? nullptr : exact_sample.data(), cut),
             "exact heap truncated prefix");
    }
  }
#ifdef _WIN32
  SYSTEM_INFO info;
  GetSystemInfo(&info);
  const size_t page = info.dwPageSize;
  uint8_t *block = static_cast<uint8_t *>(VirtualAlloc(0, page * 2, MEM_RESERVE | MEM_COMMIT, PAGE_READWRITE));
  expect(block != 0, "guard alloc");
  DWORD old = 0;
  expect(VirtualProtect(block + page, page, PAGE_NOACCESS, &old) != 0, "guard protect");
  const char *truncated = "{\"a\":1, ";
  const size_t n = std::strlen(truncated);
  uint8_t *exact = block + page - n;
  std::memcpy(exact, truncated, n);
  expect(!mwcp::json_check(exact, n), "guard truncated object");
  const char *samples[] = {"{\"a\":1}", "[1,2]", "\"abc\"", "\"a\\nb\"", "1.5e1", "{\"k\":\"\\u4e2d\"}"};
  for (const char *sample : samples) {
    const size_t len = std::strlen(sample);
    for (size_t cut = 0; cut < len; cut++) {
      uint8_t *ptr = block + page - (cut == 0 ? 1 : cut);
      if (cut)
        std::memcpy(ptr, sample, cut);
      expect(!mwcp::json_check(cut ? ptr : block + page - 1, cut), "guard prefix");
    }
  }
  VirtualFree(block, 0, MEM_RELEASE);
#endif
}

void test_shared_json_cases(const char *vector_path) {
  std::string path = vector_path;
  const size_t slash = path.find_last_of("/\\");
  path =
      (slash == std::string::npos ? std::string("protocol/fixtures/") : path.substr(0, slash + 1)) + "json-cases.json";
  const std::string json = read_file(path.c_str());
  expect(!json.empty(), "json cases");
  size_t from = 0;
  int seen = 0;
  while (true) {
    std::string text;
    std::string expect_code;
    size_t next = 0;
    if (!extract_string(json, from, "text", &text, &next))
      break;
    from = next;
    size_t expect_at = 0;
    if (!extract_string(json, from, "expect", &expect_code, &expect_at))
      break;
    from = expect_at;
    const bool ok = mwcp::json_check(reinterpret_cast<const uint8_t *>(text.data()), text.size());
    if (expect_code == "accept")
      expect(ok, text.c_str());
    else {
      expect(!ok, text.c_str());
      expect(std::strcmp(mwcp::json_error(), expect_code.c_str()) == 0, expect_code.c_str());
    }
    seen++;
  }
  expect(seen >= 20, "json case count");
  std::string threshold_path = vector_path;
  const size_t mark = threshold_path.find_last_of("/\\");
  threshold_path =
      (mark == std::string::npos ? std::string("protocol/fixtures/") : threshold_path.substr(0, mark + 1)) +
      "double-overflow-threshold.txt";
  std::string threshold = read_file(threshold_path.c_str());
  while (!threshold.empty() && (threshold.back() == '\n' || threshold.back() == '\r'))
    threshold.pop_back();
  expect(std::strcmp(mwcp::json_overflow_threshold(), threshold.c_str()) == 0, "overflow threshold");
}

void test_parser_noise_and_half_frame() {
  const char *payload = "{}";
  mwcp::EncodeInput input = {1, 1, 2, 2, 1, reinterpret_cast<const uint8_t *>(payload), 2, true};
  uint8_t wire[mwcp::kMaxWire];
  uint8_t decoded[mwcp::kMaxDecoded];
  size_t wire_len = 0, decoded_len = 0;
  expect(mwcp::encode_frame(input, wire, sizeof(wire), &wire_len, decoded, sizeof(decoded), &decoded_len) == mwcp::kOk,
         "probe frame");
  Captured captured;
  mwcp::Parser parser;
  const uint8_t noise[] = {'E', 'S', 'P', '-', 'R', 'O', 'M', 0x00};
  parser.push(noise, sizeof(noise), 0, on_frame, on_error, &captured);
  parser.push(wire, 4, 10, on_frame, on_error, &captured);
  parser.poll(2010, on_error, &captured);
  parser.push(wire, wire_len, 2020, on_frame, on_error, &captured);
  expect(captured.frames.size() == 1, "recovered frame");
  expect(parser.stats().timeouts >= 1, "half-frame timeout");
}

struct FuzzStats {
  uint32_t frames = 0;
  uint32_t errors = 0;
  uint32_t by_status[16] = {};
};

void on_fuzz_frame(const mwcp::Frame &, void *user) { static_cast<FuzzStats *>(user)->frames++; }

void on_fuzz_error(mwcp::Status s, void *user) {
  FuzzStats *st = static_cast<FuzzStats *>(user);
  st->errors++;
  const unsigned idx = static_cast<unsigned>(s);
  if (idx < 16)
    st->by_status[idx]++;
}

void test_sticky_10_frames_and_100k_mutations() {
  // P-03: 10-frame sticky stream with consecutive empty delimiter frames and 1..100 byte chunks
  std::vector<uint8_t> stream;
  uint8_t wire[mwcp::kMaxWire];
  uint8_t decoded[mwcp::kMaxDecoded];
  for (uint32_t i = 1; i <= 10; i++) {
    char body[32];
    const int n = std::snprintf(body, sizeof(body), "{\"seq\":%u}", static_cast<unsigned>(i));
    mwcp::EncodeInput in = {1, 0x1000, i, 2, i, reinterpret_cast<const uint8_t *>(body), static_cast<size_t>(n), true};
    size_t wire_len = 0, decoded_len = 0;
    expect(mwcp::encode_frame(in, wire, sizeof(wire), &wire_len, decoded, sizeof(decoded), &decoded_len) == mwcp::kOk,
           "sticky10 encode");
    stream.push_back(0x00);
    stream.push_back(0x00);
    stream.insert(stream.end(), wire, wire + wire_len);
    stream.push_back(0x00);
    stream.push_back(0x00);
  }
  uint32_t rng = 0x5eed1234u;
  auto next_rng = [&rng]() -> uint32_t {
    rng ^= rng << 13;
    rng ^= rng >> 17;
    rng ^= rng << 5;
    return rng;
  };
  Captured cap = {{}, {}, 0};
  mwcp::Parser p10;
  size_t off = 0;
  while (off < stream.size()) {
    size_t chunk = (next_rng() % 100u) + 1u;
    if (off + chunk > stream.size())
      chunk = stream.size() - off;
    p10.push(stream.data() + off, chunk, static_cast<uint32_t>(off), on_frame, on_error, &cap);
    off += chunk;
  }
  expect(cap.frames.size() == 10 && cap.errors == 0, "sticky 10 frames random chunks");

  // P-14: Deterministic seed (0x5eed1234) 100,000-mutation campaign
  const char *seed_json = "{\"client\":{\"name\":\"mmwave\",\"version\":\"1.0\"},\"n\":123}";
  mwcp::EncodeInput base_in = {
      1, 0x1000, 7, 1, 1, reinterpret_cast<const uint8_t *>(seed_json), std::strlen(seed_json), true};
  size_t base_wire_len = 0, base_dec_len = 0;
  expect(mwcp::encode_frame(base_in, wire, sizeof(wire), &base_wire_len, decoded, sizeof(decoded), &base_dec_len) ==
             mwcp::kOk,
         "fuzz base frame");

  rng = 0x5eed1234u;
  FuzzStats fstats;
  mwcp::Parser fuzz_parser;
  uint8_t mut[128];
  for (uint32_t iter = 0; iter < 100000u; iter++) {
    const uint32_t mode = next_rng() & 3u;
    size_t len = 0;
    if (mode < 2u) {
      len = base_wire_len <= sizeof(mut) ? base_wire_len : sizeof(mut);
      std::memcpy(mut, wire, len);
      const uint32_t flips = (next_rng() % 4u) + 1u;
      for (uint32_t f = 0; f < flips; f++) {
        mut[next_rng() % len] ^= static_cast<uint8_t>((next_rng() % 255u) + 1u);
      }
      mut[len - 1] = 0x00;
    } else if (mode == 2u) {
      len = (next_rng() % 60u) + 1u;
      for (size_t k = 0; k + 1 < len; k++)
        mut[k] = static_cast<uint8_t>(next_rng() & 0xffu);
      mut[len - 1] = 0x00;
      std::vector<uint8_t> exact_json(mut, mut + len);
      (void) mwcp::json_check(exact_json.data(), exact_json.size());
    } else {
      len = (next_rng() % (base_dec_len > 4 ? base_dec_len : 8)) + 1u;
      if (len > sizeof(mut) - 2)
        len = sizeof(mut) - 2;
      std::memcpy(mut, decoded, len < base_dec_len ? len : base_dec_len);
      mut[next_rng() % len] ^= static_cast<uint8_t>((next_rng() % 255u) + 1u);
      uint8_t cobs_buf[128];
      size_t cobs_len = 0;
      if (mwcp::cobs_encode(mut, len, cobs_buf + 1, sizeof(cobs_buf) - 2, &cobs_len) == mwcp::kOk) {
        cobs_buf[0] = 0x00;
        cobs_buf[cobs_len + 1] = 0x00;
        std::vector<uint8_t> exact_cobs(cobs_buf, cobs_buf + cobs_len + 2);
        fuzz_parser.push(exact_cobs.data(), exact_cobs.size(), iter, on_fuzz_frame, on_fuzz_error, &fstats);
        continue;
      }
    }
    std::vector<uint8_t> exact_mut(mut, mut + len);
    fuzz_parser.push(exact_mut.data(), exact_mut.size(), iter, on_fuzz_frame, on_fuzz_error, &fstats);
  }
  expect(fstats.errors > 50000u, "100k mutations exercised error paths");
  // Verify parser immediately recovers on a valid frame after 100,000 mutated inputs
  Captured after_fuzz = {{}, {}, 0};
  const uint8_t delim = 0x00;
  fuzz_parser.push(&delim, 1, 100001u, on_frame, on_error, &after_fuzz);
  fuzz_parser.push(wire, base_wire_len, 100002u, on_frame, on_error, &after_fuzz);
  expect(after_fuzz.frames.size() == 1, "parser recovers cleanly after 100,000 mutations");
}

}  // namespace

int main(int argc, char **argv) {
  const char *path = argc > 1 ? argv[1] : "protocol/fixtures/protocol-vectors.json";
  const std::string json = read_file(path);
  expect(!json.empty(), "read vectors");
  if (!json.empty())
    test_vectors(json);
  test_limits_and_recovery();
  test_json_bounds_and_duplicates();
  test_shared_json_cases(path);
  test_parser_noise_and_half_frame();
  test_sticky_10_frames_and_100k_mutations();
  test_transform();
  if (g_failed) {
    std::fprintf(stderr, "%d failure(s)\n", g_failed);
    return 1;
  }
  std::printf("mwcp c++ host test passed\n");
  return 0;
}
