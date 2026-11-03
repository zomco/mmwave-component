#include "mwcp_service.h"
#include "radar_observe.h"
#include "mwcp_diag_fmt.h"
#include <cstring>
#if defined(MWCP_LOG_PRESSURE_HZ) && MWCP_LOG_PRESSURE_HZ > 0
#include <esp_heap_caps.h>
#endif

#include "mwcp_codec.h"
#include "mwcp_json.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

namespace mwcp_host {
namespace {

void sha256_block(uint32_t h[8], const uint8_t block[64]);

void sha256(const uint8_t *data, size_t len, uint8_t out[32]) {
  uint32_t h[8] = {0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a, 0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19};
  size_t off = 0;
  while (off + 64 <= len) {
    sha256_block(h, data + off);
    off += 64;
  }
  uint8_t block[64];
  memset(block, 0, sizeof(block));
  size_t rem = len - off;
  if (rem)
    memcpy(block, data + off, rem);
  block[rem] = 0x80;
  uint64_t bits = static_cast<uint64_t>(len) * 8;
  if (rem >= 56) {
    sha256_block(h, block);
    memset(block, 0, sizeof(block));
  }
  for (int i = 0; i < 8; i++)
    block[63 - i] = static_cast<uint8_t>(bits >> (8 * i));
  sha256_block(h, block);
  for (int i = 0; i < 8; i++) {
    out[i * 4] = static_cast<uint8_t>(h[i] >> 24);
    out[i * 4 + 1] = static_cast<uint8_t>(h[i] >> 16);
    out[i * 4 + 2] = static_cast<uint8_t>(h[i] >> 8);
    out[i * 4 + 3] = static_cast<uint8_t>(h[i]);
  }
}

void sha256_block(uint32_t h[8], const uint8_t block[64]) {
  static const uint32_t k[64] = {
      0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5,
      0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174,
      0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
      0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967,
      0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
      0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
      0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
      0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2};
  uint32_t w[64];
  for (int i = 0; i < 16; i++)
    w[i] = (uint32_t) block[i * 4] << 24 | (uint32_t) block[i * 4 + 1] << 16 | (uint32_t) block[i * 4 + 2] << 8 |
           block[i * 4 + 3];
  for (int i = 16; i < 64; i++) {
    uint32_t s0 = (w[i - 15] >> 7 | w[i - 15] << 25) ^ (w[i - 15] >> 18 | w[i - 15] << 14) ^ (w[i - 15] >> 3);
    uint32_t s1 = (w[i - 2] >> 17 | w[i - 2] << 15) ^ (w[i - 2] >> 19 | w[i - 2] << 13) ^ (w[i - 2] >> 10);
    w[i] = w[i - 16] + s0 + w[i - 7] + s1;
  }
  uint32_t a = h[0], b = h[1], c = h[2], d = h[3], e = h[4], f = h[5], g = h[6], hh = h[7];
  for (int i = 0; i < 64; i++) {
    uint32_t s1 = (e >> 6 | e << 26) ^ (e >> 11 | e << 21) ^ (e >> 25 | e << 7);
    uint32_t ch = (e & f) ^ (~e & g);
    uint32_t t1 = hh + s1 + ch + k[i] + w[i];
    uint32_t s0 = (a >> 2 | a << 30) ^ (a >> 13 | a << 19) ^ (a >> 22 | a << 10);
    uint32_t maj = (a & b) ^ (a & c) ^ (b & c);
    hh = g;
    g = f;
    f = e;
    e = d + t1;
    d = c;
    c = b;
    b = a;
    a = t1 + s0 + maj;
  }
  h[0] += a;
  h[1] += b;
  h[2] += c;
  h[3] += d;
  h[4] += e;
  h[5] += f;
  h[6] += g;
  h[7] += hh;
}

int fail(char *out, size_t cap, const char *code, const char *msg, const char *field, const char *details) {
  if (field && details)
    return snprintf(out, cap,
                    "{\"ok\":false,\"error\":{\"code\":\"%s\",\"message\":\"%s\",\"field\":\"%s\",\"details\":%s}}",
                    code, msg, field, details);
  if (field)
    return snprintf(out, cap, "{\"ok\":false,\"error\":{\"code\":\"%s\",\"message\":\"%s\",\"field\":\"%s\"}}", code,
                    msg, field);
  if (details)
    return snprintf(out, cap, "{\"ok\":false,\"error\":{\"code\":\"%s\",\"message\":\"%s\",\"details\":%s}}", code, msg,
                    details);
  return snprintf(out, cap, "{\"ok\":false,\"error\":{\"code\":\"%s\",\"message\":\"%s\"}}", code, msg);
}

const char *job_error_message(const char *code) {
  if (code == nullptr)
    return "Job failed";
  if (strcmp(code, "RADAR_UNAVAILABLE") == 0)
    return "Radar is unavailable";
  if (strcmp(code, "RADAR_TIMEOUT") == 0)
    return "Radar operation timed out";
  if (strcmp(code, "VERIFY_FAILED") == 0)
    return "Verification failed";
  if (strcmp(code, "STORAGE_FAILED") == 0)
    return "Storage operation failed";
  if (strcmp(code, "UNSUPPORTED") == 0)
    return "Unsupported operation";
  if (strcmp(code, "BUSY") == 0)
    return "Job resource is busy";
  if (strcmp(code, "INTERNAL_ERROR") == 0)
    return "Internal job error";
  return "Job failed";
}

bool hex32(const char *s, size_t n) {
  if (n != 32)
    return false;
  for (size_t i = 0; i < n; i++) {
    char c = s[i];
    if (!((c >= '0' && c <= '9') || (c >= 'a' && c <= 'f')))
      return false;
  }
  return true;
}

bool uuid_ok(const char *s, size_t n) {
  if (n != 36)
    return false;
  const int dash[] = {8, 13, 18, 23};
  int di = 0;
  for (size_t i = 0; i < n; i++) {
    if (di < 4 && static_cast<int>(i) == dash[di]) {
      if (s[i] != '-')
        return false;
      di++;
      continue;
    }
    char c = s[i];
    if (!((c >= '0' && c <= '9') || (c >= 'a' && c <= 'f')))
      return false;
  }
  return true;
}

const char *skip_ws(const char *p, const char *end) {
  while (p < end && (*p == ' ' || *p == '\n' || *p == '\r' || *p == '\t'))
    p++;
  return p;
}

bool capture_value(const char **pp, const char *end, const char **vs, const char **ve) {
  const char *p = skip_ws(*pp, end);
  if (p >= end)
    return false;
  *vs = p;
  if (*p == '"') {
    p++;
    while (p < end) {
      if (*p == '\\') {
        p += 2;
        continue;
      }
      if (*p == '"') {
        *ve = p + 1;
        *pp = p + 1;
        return true;
      }
      p++;
    }
    return false;
  }
  if (*p == '{' || *p == '[') {
    char open = *p;
    char close = open == '{' ? '}' : ']';
    int depth = 0;
    bool str = false;
    for (; p < end; p++) {
      if (str) {
        if (*p == '\\') {
          p++;
          continue;
        }
        if (*p == '"')
          str = false;
        continue;
      }
      if (*p == '"') {
        str = true;
        continue;
      }
      if (*p == open)
        depth++;
      else if (*p == close) {
        depth--;
        if (depth == 0) {
          *ve = p + 1;
          *pp = p + 1;
          return true;
        }
      }
    }
    return false;
  }
  while (p < end && *p != ',' && *p != '}' && *p != ']' && *p != ' ' && *p != '\n')
    p++;
  *ve = p;
  *pp = p;
  return *ve > *vs;
}

bool walk_object(const char *s, size_t n, bool (*cb)(const char *, size_t, const char *, size_t, void *), void *user) {
  const char *p = skip_ws(s, s + n);
  const char *end = s + n;
  if (p >= end || *p != '{')
    return false;
  p++;
  p = skip_ws(p, end);
  if (p < end && *p == '}')
    return true;
  while (p < end) {
    p = skip_ws(p, end);
    if (p >= end || *p != '"')
      return false;
    const char *ks = ++p;
    while (p < end && *p != '"')
      p++;
    if (p >= end)
      return false;
    size_t klen = static_cast<size_t>(p - ks);
    p++;
    p = skip_ws(p, end);
    if (p >= end || *p != ':')
      return false;
    p++;
    const char *vs = nullptr;
    const char *ve = nullptr;
    if (!capture_value(&p, end, &vs, &ve))
      return false;
    if (!cb(ks, klen, vs, static_cast<size_t>(ve - vs), user))
      return false;
    p = skip_ws(p, end);
    if (p < end && *p == ',') {
      p++;
      continue;
    }
    return p < end && *p == '}';
  }
  return false;
}

struct Find {
  const char *key;
  const char *vs;
  size_t vn;
  bool found;
};

bool find_cb(const char *k, size_t kn, const char *v, size_t vn, void *user) {
  Find *f = static_cast<Find *>(user);
  if (kn == strlen(f->key) && memcmp(k, f->key, kn) == 0) {
    f->vs = v;
    f->vn = vn;
    f->found = true;
  }
  return true;
}

bool find_key(const char *json, size_t n, const char *key, const char **vs, size_t *vn) {
  Find f{key, nullptr, 0, false};
  if (!walk_object(json, n, find_cb, &f) || !f.found)
    return false;
  *vs = f.vs;
  *vn = f.vn;
  return true;
}

bool unquote(const char *v, size_t n, char *out, size_t cap) {
  if (n < 2 || v[0] != '"' || v[n - 1] != '"' || cap == 0)
    return false;
  size_t w = 0;
  for (size_t i = 1; i + 1 < n; i++) {
    unsigned char c = static_cast<unsigned char>(v[i]);
    if (c == '\\') {
      if (i + 1 >= n - 1)
        return false;
      char e = v[++i];
      if (e == '"' || e == '\\' || e == '/')
        c = static_cast<unsigned char>(e);
      else if (e == 'n')
        c = '\n';
      else if (e == 'r')
        c = '\r';
      else if (e == 't')
        c = '\t';
      else
        return false;
    }
    if (w + 1 >= cap)
      return false;
    out[w++] = static_cast<char>(c);
  }
  out[w] = 0;
  return true;
}

bool json_escape(const char *in, char *out, size_t cap) {
  if (!in || !out || cap == 0)
    return false;
  size_t w = 0;
  for (const unsigned char *p = reinterpret_cast<const unsigned char *>(in); *p; p++) {
    const char *rep = nullptr;
    char tmp[2] = {static_cast<char>(*p), 0};
    if (*p == '"' || *p == '\\') {
      char esc[3] = {'\\', static_cast<char>(*p), 0};
      rep = esc;
      if (w + 2 >= cap)
        return false;
      out[w++] = '\\';
      out[w++] = static_cast<char>(*p);
      continue;
    }
    if (*p == '\n' || *p == '\r' || *p == '\t') {
      if (w + 2 >= cap)
        return false;
      out[w++] = '\\';
      out[w++] = *p == '\n' ? 'n' : (*p == '\r' ? 'r' : 't');
      continue;
    }
    if (*p < 0x20)
      return false;
    if (w + 1 >= cap)
      return false;
    out[w++] = tmp[0];
    (void) rep;
  }
  out[w] = 0;
  return true;
}

bool ident_char(unsigned char c) {
  return (c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') || (c >= '0' && c <= '9') || c == '_';
}

char lower_char(char c) {
  if (c >= 'A' && c <= 'Z')
    return static_cast<char>(c - 'A' + 'a');
  return c;
}

bool secret_key_at(const char *p, const char *key) {
  size_t n = strlen(key);
  for (size_t i = 0; i < n; i++) {
    if (!p[i] || lower_char(p[i]) != key[i])
      return false;
  }
  return !ident_char(static_cast<unsigned char>(p[n]));
}

const char *secret_value_end(const char *v) {
  if (*v == '"' || *v == '\'') {
    char quote = *v;
    v++;
    while (*v) {
      if (*v == '\\' && v[1]) {
        v += 2;
        continue;
      }
      if (*v == quote)
        return v + 1;
      v++;
    }
    return v;
  }
  while (*v && *v != ' ' && *v != '\t' && *v != ',' && *v != ';' && *v != '\n' && *v != '\r' && *v != '}' && *v != ']')
    v++;
  return v;
}

const char *secret_keys[] = {"wifi_password", "ota_password", "ap_password", "sta_password",
                             "api_key",       "password",     "passwd",      "psk"};
const int kSecretKeys = 8;

bool secret_hit(const char *p, const char **key) {
  for (int i = 0; i < kSecretKeys; i++) {
    if (secret_key_at(p, secret_keys[i])) {
      if (key)
        *key = secret_keys[i];
      return true;
    }
  }
  return false;
}

size_t utf8_len_at(const char *p) {
  unsigned char c = static_cast<unsigned char>(*p);
  size_t need = 1;
  if ((c & 0xE0) == 0xC0)
    need = 2;
  else if ((c & 0xF0) == 0xE0)
    need = 3;
  else if ((c & 0xF8) == 0xF0)
    need = 4;
  if (need == 1)
    return 1;
  for (size_t i = 1; i < need; i++) {
    if ((static_cast<unsigned char>(p[i]) & 0xC0) != 0x80)
      return 1;
  }
  return need;
}

bool parse_num(const char *v, size_t n, double *out) {
  char buf[64];
  if (n == 0 || n >= sizeof(buf))
    return false;
  memcpy(buf, v, n);
  buf[n] = 0;
  char *end = nullptr;
  *out = strtod(buf, &end);
  return end && *end == 0;
}

bool on_step(double value, double minv, double step) {
  double q = (value - minv) / step;
  double nearest =
      q >= 0 ? static_cast<double>(static_cast<long>(q + 0.5)) : static_cast<double>(static_cast<long>(q - 0.5));
  double diff = q - nearest;
  if (diff < 0)
    diff = -diff;
  return diff <= 1e-6 && value >= minv - 1e-9 && value <= (minv + step * 100000);
}

bool parse_u64(const char *s, uint64_t *out) {
  if (!s || !*s)
    return false;
  uint64_t v = 0;
  for (const char *p = s; *p; p++) {
    if (*p < '0' || *p > '9')
      return false;
    const uint64_t digit = static_cast<uint64_t>(*p - '0');
    if (v > (0xffffffffffffffffull - digit) / 10ull)
      return false;
    v = v * 10ull + digit;
  }
  *out = v;
  return true;
}

int revcmp(const char *a, const char *b) {
  uint64_t xa = 0;
  uint64_t xb = 0;
  const bool oa = parse_u64(a, &xa);
  const bool ob = parse_u64(b, &xb);
  if (!oa || !ob)
    return strcmp(a, b);
  if (xa < xb)
    return -1;
  if (xa > xb)
    return 1;
  return 0;
}

void rev_inc(char *rev) {
  uint64_t v = 0;
  if (!parse_u64(rev, &v) || v == 0xffffffffffffffffull)
    return;
  v++;
  char tmp[24];
  int n = snprintf(tmp, sizeof(tmp), "%llu", static_cast<unsigned long long>(v));
  if (n > 0 && n < static_cast<int>(sizeof(tmp)))
    strncpy(rev, tmp, 23);
}

const char *kCaps[] = {
    "{\"kind\":\"feature\",\"id\":\"presence\",\"supported\":true,\"expected_interval_ms\":null,\"stale_after_ms\":"
    "null}",
    "{\"kind\":\"feature\",\"id\":\"distance.cm\",\"supported\":true,\"unit\":\"cm\",\"minimum\":0,\"maximum\":65535,"
    "\"expected_interval_ms\":null,\"stale_after_ms\":null}",
    "{\"kind\":\"feature\",\"id\":\"position.xy\",\"supported\":true,\"max_targets\":1,\"target_id_stable\":false,"
    "\"expected_interval_ms\":2000,\"stale_after_ms\":6000}",
    "{\"kind\":\"feature\",\"id\":\"diagnostics.local_z\",\"supported\":true,\"unit\":\"cm\",\"minimum\":-32767,"
    "\"maximum\":32767,\"expected_interval_ms\":null,\"stale_after_ms\":null}",
    "{\"kind\":\"feature\",\"id\":\"speed.cm_s\",\"supported\":false}",
    "{\"kind\":\"feature\",\"id\":\"motion.state\",\"supported\":true,\"minimum\":0,\"maximum\":2}",
    "{\"kind\":\"feature\",\"id\":\"body.movement\",\"supported\":true,\"minimum\":0,\"maximum\":100,\"expected_"
    "interval_ms\":null}",
    "{\"kind\":\"metric\",\"id\":\"breath_rate\",\"supported\":true,\"unit\":\"1/"
    "min\",\"minimum\":0,\"maximum\":35,\"expected_interval_ms\":null,\"medical\":false}",
    "{\"kind\":\"metric\",\"id\":\"heart_rate\",\"supported\":true,\"unit\":\"bpm\",\"minimum\":60,\"maximum\":120,"
    "\"expected_interval_ms\":null,\"medical\":false}",
    "{\"kind\":\"feature\",\"id\":\"sleep.state\",\"supported\":true,\"expected_interval_ms\":null,\"stale_after_ms\":"
    "null}",
    "{\"kind\":\"feature\",\"id\":\"areas.occupancy\",\"supported\":true,\"max_targets\":1}",
    "{\"kind\":\"config\",\"id\":\"install.x_cm\",\"type\":\"number\",\"unit\":\"cm\",\"minimum\":-2000,\"maximum\":"
    "2000,\"step\":1,\"writable\":true,\"domain\":\"host\",\"label_key\":\"install.x\",\"restart_required\":false}",
    "{\"kind\":\"config\",\"id\":\"install.y_cm\",\"type\":\"number\",\"unit\":\"cm\",\"minimum\":-2000,\"maximum\":"
    "2000,\"step\":1,\"writable\":true,\"domain\":\"host\",\"label_key\":\"install.y\",\"restart_required\":false}",
    "{\"kind\":\"config\",\"id\":\"install.z_cm\",\"type\":\"number\",\"unit\":\"cm\",\"minimum\":50,\"maximum\":600,"
    "\"step\":1,\"writable\":true,\"domain\":\"host\",\"label_key\":\"install.z\",\"restart_required\":false}",
    "{\"kind\":\"config\",\"id\":\"install.yaw_deg\",\"type\":\"number\",\"unit\":\"deg\",\"minimum\":-180,\"maximum\":"
    "180,\"step\":0.1,\"writable\":true,\"domain\":\"host\",\"label_key\":\"install.yaw\",\"restart_required\":false}",
    "{\"kind\":\"config\",\"id\":\"install.pitch_deg\",\"type\":\"number\",\"unit\":\"deg\",\"minimum\":-90,"
    "\"maximum\":90,\"step\":0.5,\"writable\":true,\"domain\":\"host\",\"label_key\":\"install.pitch\",\"restart_"
    "required\":false}",
    "{\"kind\":\"config\",\"id\":\"install.roll_deg\",\"type\":\"number\",\"unit\":\"deg\",\"minimum\":-90,\"maximum\":"
    "90,\"step\":0.5,\"writable\":true,\"domain\":\"host\",\"label_key\":\"install.roll\",\"restart_required\":false}",
    "{\"kind\":\"config\",\"id\":\"geometry.boundary_cm\",\"type\":\"array\",\"unit\":\"cm\",\"writable\":true,"
    "\"domain\":\"host\",\"label_key\":\"geometry.boundary\",\"restart_required\":false,\"schema_id\":\"polygon.xy."
    "v1\",\"min_items\":3,\"max_items\":64}",
    "{\"kind\":\"config\",\"id\":\"areas.definitions\",\"type\":\"array\",\"unit\":\"cm\",\"writable\":true,\"domain\":"
    "\"host\",\"label_key\":\"areas.definitions\",\"restart_required\":false,\"schema_id\":\"r60.areas.v1\",\"min_"
    "items\":0,\"max_items\":3}",
};
const char *kActions[] = {
    "{\"action_id\":\"device.restart\",\"verification\":\"none\",\"confirm\":true,\"resource\":\"restart\",\"deadline_"
    "ms\":8000}",
    "{\"action_id\":\"radar.reset_module\",\"verification\":\"none\",\"confirm\":true,\"resource\":\"radar\","
    "\"deadline_ms\":2000}",
};

bool allowed_key(const char *k, size_t n, const char *const *list) {
  for (int i = 0; list[i]; i++) {
    if (strlen(list[i]) == n && memcmp(list[i], k, n) == 0)
      return true;
  }
  return false;
}

struct Allow {
  const char *const *list;
  bool bad;
  char field[64];
};

bool allow_cb(const char *k, size_t kn, const char *, size_t, void *user) {
  Allow *a = static_cast<Allow *>(user);
  if (!allowed_key(k, kn, a->list)) {
    a->bad = true;
    size_t n = kn < 63 ? kn : 63;
    memcpy(a->field, k, n);
    a->field[n] = 0;
    return false;
  }
  return true;
}

int64_t orient(int32_t ax, int32_t ay, int32_t bx, int32_t by, int32_t cx, int32_t cy) {
  return static_cast<int64_t>(bx - ax) * (cy - ay) - static_cast<int64_t>(by - ay) * (cx - ax);
}

bool segments_cross(int16_t ax, int16_t ay, int16_t bx, int16_t by, int16_t cx, int16_t cy, int16_t dx, int16_t dy) {
  int64_t o1 = orient(ax, ay, bx, by, cx, cy);
  int64_t o2 = orient(ax, ay, bx, by, dx, dy);
  int64_t o3 = orient(cx, cy, dx, dy, ax, ay);
  int64_t o4 = orient(cx, cy, dx, dy, bx, by);
  return o1 * o2 < 0 && o3 * o4 < 0;
}

bool redact_into(const char *in, char *out, size_t cap) {
  if (!out || cap == 0)
    return false;
  size_t w = 0;
  if (!in) {
    out[0] = 0;
    return true;
  }
  const char *p = in;
  while (*p && w + 1 < cap) {
    bool keyed = (p == in) || !ident_char(static_cast<unsigned char>(p[-1]));
    const char *hit = nullptr;
    if (keyed)
      secret_hit(p, &hit);
    if (hit) {
      const char *sep = p + strlen(hit);
      while (*sep == ' ' || *sep == '\t')
        sep++;
      if (*sep == '"' || *sep == '\'')
        sep++;
      while (*sep == ' ' || *sep == '\t')
        sep++;
      if (*sep == '=' || *sep == ':') {
        const char *val = sep + 1;
        while (*val == ' ' || *val == '\t')
          val++;
        bool next_key = false;
        const char *ignored = nullptr;
        if ((val == in || !ident_char(static_cast<unsigned char>(val[-1]))) && secret_hit(val, &ignored)) {
          const char *nsep = val + strlen(ignored);
          while (*nsep == ' ' || *nsep == '\t' || *nsep == '"' || *nsep == '\'')
            nsep++;
          next_key = *nsep == '=' || *nsep == ':';
        }
        const char *end = next_key ? val : secret_value_end(val);
        size_t prefix = static_cast<size_t>(sep + 1 - p);
        if (w + prefix + 10 >= cap)
          break;
        memcpy(out + w, p, prefix);
        w += prefix;
        memcpy(out + w, "<redacted>", 10);
        w += 10;
        p = end;
        continue;
      }
      return false;
    }
    size_t need = utf8_len_at(p);
    if (w + need >= cap)
      break;
    memcpy(out + w, p, need);
    w += need;
    p += need;
  }
  out[w] = 0;
  return true;
}

}  // namespace

bool redact_secrets(const char *in, char *out, size_t cap) { return redact_into(in, out, cap); }

bool commit_area_view(char *published, size_t published_cap, char *global_value, size_t global_cap, bool commit_ok,
                      const char *committed) {
  if (!commit_ok || !published || !global_value || !committed)
    return false;
  if (strlen(committed) + 1 > published_cap || strlen(committed) + 1 > global_cap)
    return false;
  memcpy(published, committed, strlen(committed) + 1);
  memcpy(global_value, committed, strlen(committed) + 1);
  return true;
}

void Service::begin(const Identity &id, const char *boot_id) {
  id_ = id;
  memset(boot_id_, 0, sizeof(boot_id_));
  if (boot_id)
    strncpy(boot_id_, boot_id, 32);
  session_live_ = false;
  session_id_ = 0;
  seen_max_ = 0;
  sub_telemetry_ = sub_status_ = sub_config_ = sub_jobs_ = sub_logs_ = false;
  memset(replay_, 0, sizeof(replay_));
  memset(jobs_, 0, sizeof(jobs_));
  event_n_ = 0;
  restart_pending_ = false;
  strcpy(wifi_state_, "disconnected");
  wifi_ssid_[0] = 0;
  strcpy(wifi_ip_, "null");
  wifi_rssi_known_ = false;
  strcpy(wifi_error_, "null");
}

void Service::set_storage(const StoragePort &port) {
  storage_port_ = port;
  have_storage_ = true;
}
void Service::set_wifi(const WifiPort &port) {
  wifi_port_ = port;
  have_wifi_ = true;
}
void Service::set_radar(RadarView *radar) { radar_ = radar; }
void Service::push_log(const char *message) { push_log_at(message, 0, "info"); }

void Service::push_log_at(const char *message, uint32_t sample_ms, const char *level) {
  if (!message || (!logs_enabled_ && !sub_logs_))
    return;
  clock_ms_ = sample_ms;
  // Static: the logger callback can invoke this at any stack depth, and these
  // scratch buffers together exceed what the 3.5 KiB main task stack can spare.
  // Single-threaded (the in_log_ guard prevents reentry); every buffer is
  // written before it is read.
  static char clean[513];
  if (!redact_secrets(message, clean, sizeof(clean))) {
    logs_dropped_++;
    return;
  }
  static char escaped[1025];
  if (!json_escape(clean, escaped, sizeof(escaped))) {
    logs_dropped_++;
    return;
  }
  if (!sub_logs_)
    return;
  static char body[1200];
  int wr =
      snprintf(body, sizeof(body),
               "{\"sample_ms\":%lu,\"level\":\"%s\",\"source\":\"host\",\"message\":\"%s\",\"dropped_before\":%lu}",
               static_cast<unsigned long>(sample_ms), level && level[0] ? level : "info", escaped,
               static_cast<unsigned long>(logs_dropped_));
  if (wr < 0 || static_cast<size_t>(wr) >= sizeof(body)) {
    logs_dropped_++;
    return;
  }
  emit_event(0x8005, body);
}

void Service::note_observation() {
  if (radar_)
    radar_->source_seq++;
}

void Service::export_install(float *x, float *y, float *z, float *yaw, float *pitch, float *roll) const {
  if (x)
    *x = static_cast<float>(x_cm_);
  if (y)
    *y = static_cast<float>(y_cm_);
  if (z)
    *z = static_cast<float>(z_cm_);
  if (yaw)
    *yaw = static_cast<float>(yaw_tenth_) / 10.0f;
  if (pitch)
    *pitch = static_cast<float>(pitch_half_) / 2.0f;
  if (roll)
    *roll = static_cast<float>(roll_half_) / 2.0f;
}

bool Service::apply_ha_number(const char *key, float value, uint32_t now_ms) {
  char changes[96];
  snprintf(changes, sizeof(changes), "{\"%s\":%.4g}", key, static_cast<double>(value));
  return apply_ha_changes(changes, now_ms);
}

bool Service::apply_ha_changes(const char *changes, uint32_t now_ms) {
  if (!changes || strcmp(storage_, "recovery_required") == 0 || tokens_ <= 0)
    return false;
  if (revision_u64() == 0xffffffffffffffffull)
    return false;
  const char *field = nullptr;
  const char *ecode = "INVALID_ARGUMENT";
  if (!apply_changes(reinterpret_cast<const uint8_t *>(changes), strlen(changes), nullptr, 0, &field, &ecode, false))
    return false;
  const int32_t saved_x = x_cm_, saved_y = y_cm_, saved_z = z_cm_;
  const int16_t saved_yaw = yaw_tenth_, saved_pitch = pitch_half_, saved_roll = roll_half_;
  const bool saved_boundary = boundary_set_;
  const uint8_t saved_bn = boundary_n_;
  Point saved_pts[64];
  memcpy(saved_pts, boundary_, sizeof(saved_pts));
  Area saved_areas[3];
  memcpy(saved_areas, areas_, sizeof(saved_areas));
  char saved_rev[24];
  strncpy(saved_rev, revision_, sizeof(saved_rev) - 1);
  if (!apply_changes(reinterpret_cast<const uint8_t *>(changes), strlen(changes), nullptr, 0, &field, &ecode, true))
    return false;
  const bool same = x_cm_ == saved_x && y_cm_ == saved_y && z_cm_ == saved_z && yaw_tenth_ == saved_yaw &&
                    pitch_half_ == saved_pitch && roll_half_ == saved_roll && boundary_set_ == saved_boundary &&
                    boundary_n_ == saved_bn && memcmp(boundary_, saved_pts, sizeof(saved_pts)) == 0 &&
                    memcmp(areas_, saved_areas, sizeof(saved_areas)) == 0;
  if (same) {
    x_cm_ = saved_x;
    y_cm_ = saved_y;
    z_cm_ = saved_z;
    yaw_tenth_ = saved_yaw;
    pitch_half_ = saved_pitch;
    roll_half_ = saved_roll;
    boundary_set_ = saved_boundary;
    boundary_n_ = saved_bn;
    memcpy(boundary_, saved_pts, sizeof(saved_pts));
    memcpy(areas_, saved_areas, sizeof(saved_areas));
    return true;
  }
  bump_revision();
  if (!persist_config()) {
    x_cm_ = saved_x;
    y_cm_ = saved_y;
    z_cm_ = saved_z;
    yaw_tenth_ = saved_yaw;
    pitch_half_ = saved_pitch;
    roll_half_ = saved_roll;
    boundary_set_ = saved_boundary;
    boundary_n_ = saved_bn;
    memcpy(boundary_, saved_pts, sizeof(saved_pts));
    memcpy(areas_, saved_areas, sizeof(saved_areas));
    strncpy(revision_, saved_rev, sizeof(revision_) - 1);
    return false;
  }
  tokens_--;
  if (token_ms_ == 0)
    token_ms_ = now_ms;
  if (publish_hook_)
    publish_hook_(publish_user_);
  return true;
}

bool Service::has_commit(const char *op_id) const {
  if (!op_id)
    return false;
  for (int i = 0; i < kCommitRing; i++)
    if (commits_[i].used && strcmp(commits_[i].op_id, op_id) == 0)
      return true;
  return false;
}

int Service::area_count() const {
  int n = 0;
  for (int i = 0; i < 3; i++)
    if (areas_[i].used)
      n++;
  return n;
}

bool Service::area_point(int index, int point, int *x, int *y) const {
  int seen = 0;
  for (int i = 0; i < 3; i++) {
    if (!areas_[i].used)
      continue;
    if (seen == index) {
      if (point < 0 || point >= areas_[i].n)
        return false;
      if (x)
        *x = areas_[i].points[point].x;
      if (y)
        *y = areas_[i].points[point].y;
      return true;
    }
    seen++;
  }
  return false;
}

bool Service::area_slot(int index, int *slot, bool *enabled, int *points) const {
  int seen = 0;
  for (int i = 0; i < 3; i++) {
    if (!areas_[i].used)
      continue;
    if (seen == index) {
      if (slot)
        *slot = areas_[i].slot;
      if (enabled)
        *enabled = areas_[i].enabled;
      if (points)
        *points = areas_[i].n;
      return true;
    }
    seen++;
  }
  return false;
}

const char *Service::area_name(int index) const {
  int seen = 0;
  for (int i = 0; i < 3; i++) {
    if (!areas_[i].used)
      continue;
    if (seen == index)
      return areas_[i].name;
    seen++;
  }
  return "";
}

bool Service::export_area_text(uint8_t slot, char *out, size_t cap) const {
  if (!out || cap == 0 || slot > 2)
    return false;
  out[0] = 0;
  for (int i = 0; i < 3; i++) {
    if (!areas_[i].used || areas_[i].slot != slot || !areas_[i].enabled || areas_[i].n < 3)
      continue;
    size_t used = 0;
    for (int p = 0; p < areas_[i].n; p++) {
      char pair[24];
      int wr = snprintf(pair, sizeof(pair), "%s%d,%d", p ? ";" : "", areas_[i].points[p].x, areas_[i].points[p].y);
      if (wr < 0 || used + static_cast<size_t>(wr) >= cap)
        return false;
      memcpy(out + used, pair, static_cast<size_t>(wr) + 1);
      used += static_cast<size_t>(wr);
    }
    return true;
  }
  return true;
}

bool Service::apply_area_text(uint8_t slot, const char *text, uint32_t now_ms) {
  if (slot > 2)
    return false;
  int xs[12];
  int ys[12];
  int n = 0;
  if (text && text[0]) {
    const char *p = text;
    while (*p) {
      if (n >= 12)
        return false;
      char *e1 = nullptr;
      double x = strtod(p, &e1);
      if (e1 == p || *e1 != ',')
        return false;
      char *e2 = nullptr;
      double y = strtod(e1 + 1, &e2);
      if (e2 == e1 + 1)
        return false;
      if (x != x || y != y || x < -2000.0 || x > 2000.0 || y < -2000.0 || y > 2000.0)
        return false;
      int ix = static_cast<int>(x >= 0 ? x + 0.5 : x - 0.5);
      int iy = static_cast<int>(y >= 0 ? y + 0.5 : y - 0.5);
      double dx = x - ix;
      double dy = y - iy;
      if (dx < 0)
        dx = -dx;
      if (dy < 0)
        dy = -dy;
      if (dx > 0.0001 || dy > 0.0001)
        return false;
      xs[n] = ix;
      ys[n] = iy;
      n++;
      if (*e2 == ';')
        p = e2 + 1;
      else if (*e2 == 0)
        break;
      else
        return false;
      if (*p == 0)
        break;
    }
    if (n < 3)
      return false;
  }
  // Static scratch: HA text callbacks and the MWCP dispatch path both reach
  // this from the 3.5 KiB main task stack; single-threaded, written first.
  static char body[2048];
  int used = snprintf(body, sizeof(body), "{\"areas.definitions\":[");
  if (used < 0 || static_cast<size_t>(used) >= sizeof(body))
    return false;
  bool any = false;
  for (int s = 0; s < 3; s++) {
    int existing = -1;
    for (int a = 0; a < 3; a++) {
      if (areas_[a].used && areas_[a].slot == static_cast<uint8_t>(s)) {
        existing = a;
        break;
      }
    }
    if (s != static_cast<int>(slot) && existing < 0)
      continue;
    char name[33];
    memset(name, 0, sizeof(name));
    bool enabled = false;
    char pts_json[400];
    pts_json[0] = 0;
    if (s == static_cast<int>(slot)) {
      if (existing >= 0)
        strncpy(name, areas_[existing].name, 32);
      else
        snprintf(name, sizeof(name), "area%u", slot);
      enabled = n >= 3;
      for (int p = 0; p < n; p++) {
        char pair[24];
        int wr = snprintf(pair, sizeof(pair), "%s[%d,%d]", p ? "," : "", xs[p], ys[p]);
        if (wr < 0 || static_cast<size_t>(wr) >= sizeof(pair) ||
            strlen(pts_json) + static_cast<size_t>(wr) >= sizeof(pts_json))
          return false;
        strcat(pts_json, pair);
      }
    } else {
      strncpy(name, areas_[existing].name, 32);
      enabled = areas_[existing].enabled;
      for (int p = 0; p < areas_[existing].n; p++) {
        char pair[24];
        int wr = snprintf(pair, sizeof(pair), "%s[%d,%d]", p ? "," : "", areas_[existing].points[p].x,
                          areas_[existing].points[p].y);
        if (wr < 0 || static_cast<size_t>(wr) >= sizeof(pair) ||
            strlen(pts_json) + static_cast<size_t>(wr) >= sizeof(pts_json))
          return false;
        strcat(pts_json, pair);
      }
    }
    char name_esc[80];
    if (!json_escape(name, name_esc, sizeof(name_esc)))
      return false;
    static char slotj[520];
    int wr = snprintf(slotj, sizeof(slotj), "%s{\"slot\":%d,\"enabled\":%s,\"name\":\"%s\",\"points_cm\":[%s]}",
                      any ? "," : "", s, enabled ? "true" : "false", name_esc, pts_json);
    if (wr < 0 || static_cast<size_t>(wr) >= sizeof(slotj) ||
        strlen(body) + static_cast<size_t>(wr) + 3 >= sizeof(body))
      return false;
    strcat(body, slotj);
    any = true;
  }
  if (strlen(body) + 2 >= sizeof(body))
    return false;
  strcat(body, "]}");
  return apply_ha_changes(body, now_ms);
}

void Service::export_boundary(int16_t *xy, int *n) const {
  if (n)
    *n = boundary_set_ ? boundary_n_ : 0;
  if (!xy || !boundary_set_)
    return;
  for (int i = 0; i < boundary_n_; i++) {
    xy[i * 2] = boundary_[i].x;
    xy[i * 2 + 1] = boundary_[i].y;
  }
}

uint64_t Service::revision_u64() const {
  uint64_t v = 0;
  for (const char *p = revision_; *p; p++) {
    if (*p < '0' || *p > '9')
      return 0;
    v = v * 10ull + static_cast<uint64_t>(*p - '0');
  }
  return v;
}

bool Service::config_z(int *out) const {
  if (!out)
    return false;
  *out = z_cm_;
  return true;
}

int Service::record_count() const { return count_records(); }

int Service::count_records() const {
  int n = 0;
  for (int i = 0; i < kJobCap; i++)
    if (jobs_[i].used)
      n++;
  return n;
}

void Service::note_wifi_state(bool connected, const char *ssid, const char *ip, bool rssi_known, int rssi) {
  for (int i = 0; i < kJobCap; i++) {
    if (jobs_[i].used && jobs_[i].active) {
      if (strcmp(jobs_[i].action_id, "wifi.provision") == 0)
        return;  // the provision flow owns the state until it terminates
    }
  }
  if (have_wifi_ && scan_job_[0] && scan_pending_)
    return;  // scan bookkeeping restores the state itself on completion
  const char *state = connected ? "connected" : "disconnected";
  const bool changed = strcmp(wifi_state_, state) != 0 || strcmp(wifi_ssid_, ssid ? ssid : "") != 0 ||
                       strcmp(wifi_ip_, ip ? ip : "null") != 0 || wifi_rssi_known_ != rssi_known;
  wifi_rssi_ = rssi;
  wifi_rssi_known_ = rssi_known;
  if (!changed)
    return;
  strncpy(wifi_state_, state, sizeof(wifi_state_) - 1);
  wifi_state_[sizeof(wifi_state_) - 1] = 0;
  snprintf(wifi_ssid_, sizeof(wifi_ssid_), "%s", ssid ? ssid : "");
  snprintf(wifi_ip_, sizeof(wifi_ip_), "%s", ip && ip[0] ? ip : "null");
}

void Service::expire_session() {
  session_live_ = false;
  session_id_ = 0;
  sub_telemetry_ = sub_status_ = sub_config_ = sub_jobs_ = sub_logs_ = false;
  event_n_ = 0;
  memset(replay_, 0, sizeof(replay_));
}

bool Service::session_ok(uint32_t session, uint32_t now_ms) {
  if (!session_live_ || session != session_id_)
    return false;
  if (now_ms - touched_ms_ >= kSessionTtlMs) {
    expire_session();
    return false;
  }
  return true;
}

void Service::bump_revision() { rev_inc(revision_); }

bool Service::emit_event(uint16_t code, const char *json) {
  bool want = (code == 0x8001 && sub_telemetry_) || (code == 0x8002 && sub_status_) ||
              (code == 0x8003 && sub_config_) || (code == 0x8004 && sub_jobs_) || (code == 0x8005 && sub_logs_);
  if (!want || !json)
    return false;
  int stream = code == 0x8001 ? 0 : code == 0x8002 ? 1 : code == 0x8003 ? 2 : code == 0x8004 ? 3 : 4;
  int rate = stream_rate_[stream];
  if (rate <= 0) {
    if (code == 0x8005)
      logs_dropped_++;
    else
      tx_overflow_++;
    return false;
  }
  uint32_t gap = 1000u / static_cast<uint32_t>(rate);
  if (gap == 0)
    gap = 1;
  if (stream_sent_[stream] && clock_ms_ - stream_last_ms_[stream] < gap) {
    if (code == 0x8005)
      logs_dropped_++;
    else if (code == 0x8001)
      telemetry_coalesced_++;
    else
      tx_overflow_++;
    return false;
  }
  static uint8_t wire_buf[mwcp::kMaxWire];
  static uint8_t decoded_buf[mwcp::kMaxDecoded];
  mwcp::EncodeInput enc{};
  enc.kind = 3;
  enc.session_id = session_id_;
  enc.request_id = 0;
  enc.code = code;
  enc.wire_seq = event_wire_seq_ == 0 ? 1 : event_wire_seq_;
  enc.payload = reinterpret_cast<const uint8_t *>(json);
  enc.payload_len = strlen(json);
  enc.check_json = true;
  size_t wire_len = 0;
  size_t decoded_len = 0;
  if (mwcp::encode_frame(enc, wire_buf, sizeof(wire_buf), &wire_len, decoded_buf, sizeof(decoded_buf), &decoded_len) !=
      mwcp::kOk) {
    if (code == 0x8005)
      logs_dropped_++;
    else
      tx_overflow_++;
    return false;
  }
  if (budget_window_ == 0 || clock_ms_ - budget_window_ >= 1000) {
    budget_window_ = clock_ms_;
    budget_left_ = event_budget_;
    admitted_wire_ = 0;
  }
  if (static_cast<int>(wire_len) > budget_left_) {
    if (code == 0x8005)
      logs_dropped_++;
    else if (code == 0x8001)
      telemetry_coalesced_++;
    else
      tx_overflow_++;
    return false;
  }
  if (event_n_ >= 8) {
    int drop = -1;
    if (code != 0x8005) {
      for (int i = 0; i < event_n_; i++)
        if (event_code_[i] == 0x8005) {
          drop = i;
          break;
        }
    }
    if (drop < 0) {
      if (code == 0x8005)
        logs_dropped_++;
      else
        tx_overflow_++;
      return false;
    }
    memmove(event_q_[drop], event_q_[drop + 1], sizeof(event_q_[0]) * static_cast<size_t>(event_n_ - drop - 1));
    memmove(event_code_ + drop, event_code_ + drop + 1,
            sizeof(event_code_[0]) * static_cast<size_t>(event_n_ - drop - 1));
    event_n_--;
    logs_dropped_++;
  }
  size_t n = strlen(json);
  if (n >= sizeof(event_q_[0])) {
    if (code == 0x8005)
      logs_dropped_++;
    else
      tx_overflow_++;
    return false;
  }
  budget_left_ -= static_cast<int>(wire_len);
  admitted_wire_ += static_cast<uint32_t>(wire_len);
  stream_sent_[stream] = true;
  stream_last_ms_[stream] = clock_ms_;
  event_wire_seq_++;
  memcpy(event_q_[event_n_], json, n + 1);
  event_code_[event_n_++] = code;
  return true;
}

bool Service::next_event(char *out, size_t cap, uint16_t *code) {
  if (event_n_ == 0 || !out || cap == 0)
    return false;
  if (strlen(event_q_[0]) + 1 > cap) {
    tx_overflow_++;
    memmove(event_q_[0], event_q_[1], sizeof(event_q_[0]) * (event_n_ - 1));
    memmove(event_code_, event_code_ + 1, sizeof(event_code_[0]) * (event_n_ - 1));
    event_n_--;
    return false;
  }
  strcpy(out, event_q_[0]);
  *code = event_code_[0];
  memmove(event_q_[0], event_q_[1], sizeof(event_q_[0]) * (event_n_ - 1));
  memmove(event_code_, event_code_ + 1, sizeof(event_code_[0]) * (event_n_ - 1));
  event_n_--;
  return true;
}

void Service::redact(char *text) const {
  char *p = text;
  while (*p) {
    if ((p[0] == 'p' || p[0] == 'P') && strncmp(p + 1, "assword", 7) == 0) {
      memcpy(p, "redacted", 8);
    }
    p++;
  }
}

static const uint32_t kMagic = 0x4d574331;

struct Blob {
  uint32_t magic;
  uint32_t schema;
  uint32_t crc;
  char revision[24];
  int32_t x, y, z;
  int16_t yaw_tenth, pitch_half, roll_half;
  uint8_t boundary_set;
  uint8_t boundary_n;
  int16_t boundary[128];
  uint8_t area_used[3];
  uint8_t area_slot[3];
  uint8_t area_enabled[3];
  char area_name[3][33];
  uint8_t area_n[3];
  int16_t area_xy[3][24];
  uint8_t commit_used[4];
  char commit_op[4][40];
  uint8_t commit_sha[4][32];
  char commit_rev[4][24];
};

static uint32_t blob_crc(const Blob &b) {
  const uint8_t *p = reinterpret_cast<const uint8_t *>(&b.revision);
  size_t n = sizeof(Blob) - offsetof(Blob, revision);
  uint32_t crc = 0xFFFFFFFFu;
  for (size_t i = 0; i < n; i++) {
    crc ^= p[i];
    for (int bit = 0; bit < 8; bit++)
      crc = (crc >> 1) ^ (0x82F63B78u & (0u - (crc & 1u)));
  }
  return crc ^ 0xFFFFFFFFu;
}

void Service::fill_blob(void *blob) const {
  Blob *b = static_cast<Blob *>(blob);
  memset(b, 0, sizeof(*b));
  b->magic = kMagic;
  b->schema = 1;
  strncpy(b->revision, revision_, sizeof(b->revision) - 1);
  b->x = x_cm_;
  b->y = y_cm_;
  b->z = z_cm_;
  b->yaw_tenth = yaw_tenth_;
  b->pitch_half = pitch_half_;
  b->roll_half = roll_half_;
  b->boundary_set = boundary_set_ ? 1 : 0;
  b->boundary_n = boundary_n_;
  for (int i = 0; i < boundary_n_ && i < 64; i++) {
    b->boundary[i * 2] = boundary_[i].x;
    b->boundary[i * 2 + 1] = boundary_[i].y;
  }
  for (int i = 0; i < 3; i++) {
    b->area_used[i] = areas_[i].used ? 1 : 0;
    b->area_slot[i] = areas_[i].slot;
    b->area_enabled[i] = areas_[i].enabled ? 1 : 0;
    strncpy(b->area_name[i], areas_[i].name, 32);
    b->area_n[i] = areas_[i].n;
    for (int p = 0; p < areas_[i].n && p < 12; p++) {
      b->area_xy[i][p * 2] = areas_[i].points[p].x;
      b->area_xy[i][p * 2 + 1] = areas_[i].points[p].y;
    }
  }
  for (int i = 0; i < 4; i++) {
    b->commit_used[i] = commits_[i].used ? 1 : 0;
    strncpy(b->commit_op[i], commits_[i].op_id, 39);
    memcpy(b->commit_sha[i], commits_[i].sha, 32);
    strncpy(b->commit_rev[i], commits_[i].revision, 23);
  }
  b->crc = blob_crc(*b);
}

void Service::read_blob(const void *blob) {
  const Blob &b = *static_cast<const Blob *>(blob);
  strncpy(revision_, b.revision, sizeof(revision_) - 1);
  x_cm_ = b.x;
  y_cm_ = b.y;
  z_cm_ = b.z;
  yaw_tenth_ = b.yaw_tenth;
  pitch_half_ = b.pitch_half;
  roll_half_ = b.roll_half;
  boundary_set_ = b.boundary_set != 0;
  boundary_n_ = b.boundary_n > 64 ? 64 : b.boundary_n;
  for (int i = 0; i < boundary_n_; i++) {
    boundary_[i].x = b.boundary[i * 2];
    boundary_[i].y = b.boundary[i * 2 + 1];
  }
  for (int i = 0; i < 3; i++) {
    areas_[i].used = b.area_used[i] != 0;
    areas_[i].slot = b.area_slot[i];
    areas_[i].enabled = b.area_enabled[i] != 0;
    strncpy(areas_[i].name, b.area_name[i], 32);
    areas_[i].n = b.area_n[i] > 12 ? 12 : b.area_n[i];
    for (int p = 0; p < areas_[i].n; p++) {
      areas_[i].points[p].x = b.area_xy[i][p * 2];
      areas_[i].points[p].y = b.area_xy[i][p * 2 + 1];
    }
  }
  for (int i = 0; i < 4; i++) {
    commits_[i].used = b.commit_used[i] != 0;
    strncpy(commits_[i].op_id, b.commit_op[i], sizeof(commits_[i].op_id) - 1);
    memcpy(commits_[i].sha, b.commit_sha[i], 32);
    strncpy(commits_[i].revision, b.commit_rev[i], sizeof(commits_[i].revision) - 1);
  }
}

void Service::load_storage() {
  if (!have_storage_)
    return;
  Blob slots[2];
  bool ok[2] = {false, false};
  for (int i = 0; i < 2; i++) {
    memset(&slots[i], 0, sizeof(slots[i]));
    if (!storage_port_.load(storage_port_.user, i, reinterpret_cast<uint8_t *>(&slots[i]), sizeof(Blob)))
      continue;
    if (slots[i].magic != kMagic || slots[i].schema != 1)
      continue;
    if (slots[i].crc != blob_crc(slots[i]))
      continue;
    ok[i] = true;
  }
  int both_present = 0;
  int bad = 0;
  for (int i = 0; i < 2; i++) {
    bool loaded = storage_port_.load(storage_port_.user, i, reinterpret_cast<uint8_t *>(&slots[i]), sizeof(Blob));
    if (!loaded)
      continue;
    both_present++;
    if (!ok[i])
      bad++;
  }
  if (both_present == 2 && bad == 2) {
    strcpy(storage_, "recovery_required");
    return;
  }
  int best = -1;
  for (int i = 0; i < 2; i++) {
    if (!ok[i])
      continue;
    if (best < 0 || revcmp(slots[i].revision, slots[best].revision) > 0)
      best = i;
  }
  if (best >= 0) {
    read_blob(&slots[best]);
    durable_ = true;
    strcpy(storage_, bad ? "degraded" : "healthy");
  }
}

bool Service::persist_config() {
  if (!have_storage_) {
    strcpy(storage_, "degraded");
    return false;
  }
  Blob cur[2];
  bool ok[2] = {false, false};
  int dest = 0;
  for (int i = 0; i < 2; i++) {
    if (!storage_port_.load(storage_port_.user, i, reinterpret_cast<uint8_t *>(&cur[i]), sizeof(Blob)))
      continue;
    if (cur[i].magic == kMagic && cur[i].crc == blob_crc(cur[i]))
      ok[i] = true;
  }
  if (ok[0] && (!ok[1] || revcmp(cur[0].revision, cur[1].revision) >= 0))
    dest = 1;
  if (ok[1] && (!ok[0] || revcmp(cur[1].revision, cur[0].revision) > 0))
    dest = 0;
  Blob b;
  fill_blob(&b);
  if (!storage_port_.store(storage_port_.user, dest, reinterpret_cast<const uint8_t *>(&b), sizeof(Blob))) {
    strcpy(storage_, "degraded");
    return false;
  }
  if (storage_port_.sync && !storage_port_.sync(storage_port_.user)) {
    strcpy(storage_, "degraded");
    return false;
  }
  Blob back;
  memset(&back, 0, sizeof(back));
  bool (*reader)(void *, int, uint8_t *, size_t) = storage_port_.readback ? storage_port_.readback : storage_port_.load;
  if (!reader(storage_port_.user, dest, reinterpret_cast<uint8_t *>(&back), sizeof(back)) ||
      memcmp(&back, &b, sizeof(b)) != 0) {
    strcpy(storage_, "degraded");
    return false;
  }
  strcpy(storage_, "healthy");
  durable_ = true;
  return true;
}

bool Service::migrate_legacy(const LegacyInstall &legacy) {
  if (strcmp(storage_, "recovery_required") == 0)
    return false;
  Blob probe;
  if (have_storage_) {
    for (int i = 0; i < 2; i++) {
      if (storage_port_.load(storage_port_.user, i, reinterpret_cast<uint8_t *>(&probe), sizeof(probe)) &&
          probe.magic == kMagic && probe.crc == blob_crc(probe))
        return false;
    }
  }
  x_cm_ = static_cast<int32_t>(legacy.x);
  y_cm_ = static_cast<int32_t>(legacy.y);
  z_cm_ = static_cast<int32_t>(legacy.z);
  yaw_tenth_ = static_cast<int16_t>(legacy.yaw * 10);
  pitch_half_ = static_cast<int16_t>(legacy.pitch * 2);
  roll_half_ = static_cast<int16_t>(legacy.roll * 2);
  boundary_set_ = legacy.has_polygon && legacy.polygon_n >= 3;
  boundary_n_ = boundary_set_ ? static_cast<uint8_t>(legacy.polygon_n) : 0;
  for (int i = 0; i < boundary_n_ && i < 64; i++) {
    boundary_[i].x = legacy.polygon_xy[i * 2];
    boundary_[i].y = legacy.polygon_xy[i * 2 + 1];
  }
  strcpy(revision_, "1");
  return persist_config();
}

void Service::reclaim(uint32_t now_ms) {
  for (int i = 0; i < kJobCap; i++) {
    if (!jobs_[i].used || jobs_[i].active || !jobs_[i].has_finished)
      continue;
    uint32_t elapsed = now_ms - jobs_[i].finished_ms;
    if (elapsed >= kJobKeepMs)
      jobs_[i].used = false;
  }
}

bool Service::resource_busy(const char *resource, char *active_id, size_t cap) const {
  for (int i = 0; i < kJobCap; i++) {
    if (!jobs_[i].used || !jobs_[i].active)
      continue;
    if (strcmp(jobs_[i].resource, "restart") == 0 || strcmp(resource, "restart") == 0 ||
        strcmp(jobs_[i].resource, resource) == 0) {
      strncpy(active_id, jobs_[i].id, cap - 1);
      active_id[cap - 1] = 0;
      return true;
    }
  }
  return false;
}

bool Service::same_op(const char *op_id, const uint8_t sha[32], char *job_id, size_t cap, bool *reuse) const {
  *reuse = false;
  for (int i = 0; i < kJobCap; i++) {
    if (!jobs_[i].used || strcmp(jobs_[i].op_id, op_id) != 0)
      continue;
    strncpy(job_id, jobs_[i].id, cap - 1);
    job_id[cap - 1] = 0;
    *reuse = memcmp(jobs_[i].sha, sha, 32) != 0;
    return true;
  }
  for (int i = 0; i < kCommitRing; i++) {
    if (!commits_[i].used || strcmp(commits_[i].op_id, op_id) != 0)
      continue;
    *reuse = memcmp(commits_[i].sha, sha, 32) != 0;
    return false;
  }
  return false;
}

bool Service::admit_job(uint32_t now_ms, const char *op_id, const uint8_t sha[32], const char *action,
                        const char *resource, bool confirm_required, const char *confirm, char *out, size_t cap,
                        bool *created) {
  *created = false;
  char existing[16] = "";
  bool reuse = false;
  if (same_op(op_id, sha, existing, sizeof(existing), &reuse)) {
    if (reuse) {
      fail(out, cap, "OP_ID_REUSE", "op_id reused", "op_id", nullptr);
      return false;
    }
    snprintf(out, cap, "{\"ok\":true,\"result\":{\"job_id\":\"%s\"}}", existing);
    return true;
  }
  if (confirm_required && (!confirm || strcmp(confirm, action) != 0)) {
    fail(out, cap, "INVALID_ARGUMENT", "confirm must equal action_id", "confirm", nullptr);
    return false;
  }
  char active[16];
  if (resource_busy(resource, active, sizeof(active))) {
    char details[96];
    snprintf(details, sizeof(details), "{\"field\":\"action_id\",\"active_job_id\":\"%s\",\"resource\":\"%s\"}", active,
             resource);
    fail(out, cap, "BUSY", "Resource busy", nullptr, details);
    return false;
  }
  reclaim(now_ms);
  if (count_records() >= kJobCap) {
    fail(out, cap, "BUSY", "Job capacity", nullptr, "{\"reason\":\"capacity\",\"retry_after_ms\":1000}");
    return false;
  }
  int slot = -1;
  for (int i = 0; i < kJobCap; i++)
    if (!jobs_[i].used) {
      slot = i;
      break;
    }
  if (slot < 0) {
    fail(out, cap, "BUSY", "Job capacity", nullptr, "{\"reason\":\"capacity\",\"retry_after_ms\":1000}");
    return false;
  }
  Job &job = jobs_[slot];
  memset(&job, 0, sizeof(job));
  job.used = true;
  job.active = true;
  snprintf(job.id, sizeof(job.id), "job-%lu", static_cast<unsigned long>(next_job_++));
  strncpy(job.op_id, op_id, sizeof(job.op_id) - 1);
  strncpy(job.action_id, action, sizeof(job.action_id) - 1);
  memcpy(job.sha, sha, 32);
  strncpy(job.resource, resource, sizeof(job.resource) - 1);
  strcpy(job.state, "running");
  strcpy(job.stage, strcmp(action, "device.restart") == 0 ? "restarting" : "queued");
  job.started_ms = now_ms;
  *created = true;
  snprintf(out, cap, "{\"ok\":true,\"result\":{\"job_id\":\"%s\"}}", job.id);
  static char ev[512];
  write_job(job, ev, sizeof(ev));
  emit_event(0x8004, ev);
  return true;
}

void Service::finish_job(Job *job, uint32_t now_ms, bool ok, const char *error) {
  job->active = false;
  job->has_finished = true;
  job->finished_ms = now_ms;
  strcpy(job->state, ok ? "succeeded" : "failed");
  strcpy(job->stage, ok ? "done" : "failed");
  if (error) {
    strncpy(job->error_code, error, sizeof(job->error_code) - 1);
    job->error_code[sizeof(job->error_code) - 1] = 0;
  }
  static char ev[512];
  write_job(*job, ev, sizeof(ev));
  emit_event(0x8004, ev);
}

void Service::restore_wifi_state_after_scan() {
  strcpy(wifi_state_, scan_prev_connected_ ? "connected" : "disconnected");
}

void Service::write_job(const Job &job, char *out, size_t cap) const {
  const bool failed = job.has_finished && strcmp(job.state, "failed") == 0;
  char result[64] = "null";
  char error[256] = "null";
  if (failed) {
    const char *code = job.error_code[0] ? job.error_code : "INTERNAL_ERROR";
    snprintf(error, sizeof(error), "{\"code\":\"%s\",\"message\":\"%s\"}", code, job_error_message(code));
  } else if (job.has_finished) {
    strcpy(result, "{\"verified\":false,\"verification\":\"none\"}");
  }
  if (job.has_finished) {
    snprintf(
        out, cap,
        "{\"job_id\":\"%s\",\"op_id\":\"%s\",\"action_id\":\"%s\",\"state\":\"%s\",\"stage\":\"%s\",\"progress\":null,"
        "\"started_ms\":%lu,\"finished_ms\":%lu,\"result\":%s,\"error\":%s}",
        job.id, job.op_id, job.action_id, job.state, job.stage, static_cast<unsigned long>(job.started_ms),
        static_cast<unsigned long>(job.finished_ms), result, error);
  } else {
    snprintf(
        out, cap,
        "{\"job_id\":\"%s\",\"op_id\":\"%s\",\"action_id\":\"%s\",\"state\":\"%s\",\"stage\":\"%s\",\"progress\":null,"
        "\"started_ms\":%lu,\"finished_ms\":null,\"result\":null,\"error\":null}",
        job.id, job.op_id, job.action_id, job.state, job.stage, static_cast<unsigned long>(job.started_ms));
  }
}

void Service::poll(uint32_t now_ms) {
  clock_ms_ = now_ms;
#if defined(MWCP_LOG_PRESSURE_HZ) && MWCP_LOG_PRESSURE_HZ > 0
  // DIAGNOSTIC log-pressure source (2026-10-26 r2 review R2-A): the stress
  // soak needs a LOG stream that provably flows; the natural radar stream
  // is silent when nothing changes, and a silent device with a LOG
  // subscription is not pressure. Enabled ONLY in the dedicated stress-
  // diagnostic profile via MWCP_LOG_PRESSURE_HZ; production images compile
  // none of this. Messages carry a monotonic sequence so continuity is
  // verifiable from the evidence.
  if (sub_logs_ && now_ms - log_pressure_ms_ >= 1000 / MWCP_LOG_PRESSURE_HZ) {
    log_pressure_ms_ = now_ms;
    // R18-H18-01: memory-safety rework.  The previous revision declared
    // msg[160] and immediately called strlen(msg) on UNINITIALIZED stack
    // (the seq-initializing snprintf had been removed), and never advanced
    // log_pressure_seq_.  The formatter now lives in mwcp_diag_fmt.h: a
    // pure, bounded, always-initialized function whose snprintf results are
    // all checked and which never emits a truncated number; the sequence is
    // initialized and monotonic.  Diagnostic profiles only: production
    // images compile this whole block (and the formatter call) to nothing.
    char msg[MWCP_DIAG_PRESSURE_MSG_LEN];
    unsigned seq = ++log_pressure_seq_;
    int fields = mwcp_diag::format_pressure(msg, sizeof(msg), static_cast<unsigned long>(seq),
                                            static_cast<unsigned>(heap_caps_get_free_size(MALLOC_CAP_8BIT)),
                                            static_cast<unsigned>(heap_caps_get_minimum_free_size(MALLOC_CAP_8BIT)),
                                            static_cast<unsigned>(heap_caps_get_largest_free_block(MALLOC_CAP_8BIT)));
    static bool diag_fmt_selftest_done_ = false;
    if (!diag_fmt_selftest_done_) {
      // One-shot self-test of the same transactional formatter the host test
      // executes. NUL sits at the last complete field, not at cap-1. A cap
      // that cannot hold "pressure-seq=1" (14 chars + NUL) returns 0 fields.
      // Sentinels live past the writable cap, not inside the snprintf window.
      char buf[MWCP_DIAG_PRESSURE_MSG_LEN + 8];
      memset(buf, 0xA5, sizeof(buf));
      char *b = buf + 4;
      int f1 = mwcp_diag::format_pressure(b, MWCP_DIAG_PRESSURE_MSG_LEN, 4294967295UL, 4294967295U, 4294967295U,
                                          4294967295U);
      bool st1 = f1 == 4 && strlen(b) == 80 && b[80] == '\0' && static_cast<unsigned char>(buf[3]) == 0xA5 &&
                 static_cast<unsigned char>(b[MWCP_DIAG_PRESSURE_MSG_LEN]) == 0xA5 &&
                 strcmp(b, "pressure-seq=4294967295 free=4294967295 "
                           "min_free=4294967295 max_block=4294967295") == 0;
      char tiny_g[12 + 2];
      memset(tiny_g, 0xA5, sizeof(tiny_g));
      int f2 = mwcp_diag::format_pressure(tiny_g, 12, 1, 2, 3, 4);
      bool st2 = f2 == 0 && tiny_g[0] == '\0' && static_cast<unsigned char>(tiny_g[12]) == 0xA5;
      char z[6];
      memset(z, 0x5A, sizeof(z));
      int f3 = mwcp_diag::format_pressure(z, 4, 7, 8, 9, 10);
      bool st3 = f3 == 0 && z[0] == '\0' && static_cast<unsigned char>(z[4]) == 0x5A;
      char r19[32];
      memset(r19, 0xA5, sizeof(r19));
      int f4 = mwcp_diag::format_pressure(r19, 23, 1, 12345, 4, 5);
      bool st4 = f4 == 1 && strcmp(r19, "pressure-seq=1") == 0 && static_cast<unsigned char>(r19[23]) == 0xA5;
      char repeat[24];
      memset(repeat, 0xA5, sizeof(repeat));
      int f5a = mwcp_diag::format_pressure(repeat, sizeof(repeat), 1, 2, 3, 4);
      int f5b = mwcp_diag::format_pressure(repeat, 24, 4294967295UL, 1, 2, 3);
      bool st5 = f5a == 2 && f5b == 1 && strcmp(repeat, "pressure-seq=4294967295") == 0;
      push_log_at((st1 && st2 && st3 && st4 && st5) ? "diag_fmt_selftest=pass" : "diag_fmt_selftest=FAIL", now_ms,
                  "info");
      diag_fmt_selftest_done_ = true;
    }
    if (fields >= 1)
      push_log_at(msg, now_ms, "info");
  }
#endif
  if (session_live_ && now_ms - touched_ms_ >= kSessionTtlMs)
    expire_session();
  if (tokens_ < kTokenCap && now_ms - token_ms_ >= 1000) {
    uint32_t steps = (now_ms - token_ms_) / 1000;
    tokens_ += static_cast<int>(steps);
    if (tokens_ > kTokenCap)
      tokens_ = kTokenCap;
    token_ms_ += steps * 1000;
  }
  if (have_wifi_ && scan_job_[0] && scan_pending_) {
    bool truncated = false;
    WifiAp tmp[kScanCap];
    int n = wifi_port_.poll_scan(wifi_port_.user, tmp, kScanCap, &truncated);
    if (n == -2) {
      for (int i = 0; i < kJobCap; i++)
        if (jobs_[i].used && strcmp(jobs_[i].id, scan_job_) == 0 && jobs_[i].active)
          finish_job(&jobs_[i], now_ms, false, "VERIFY_FAILED");
      scan_pending_ = false;
      restore_wifi_state_after_scan();
    } else if (n >= 0) {
      for (int i = 0; i < n; i++)
        for (int j = i + 1; j < n; j++)
          if (tmp[j].rssi > tmp[i].rssi) {
            WifiAp s = tmp[i];
            tmp[i] = tmp[j];
            tmp[j] = s;
          }
      scan_n_ = n > kScanCap ? kScanCap : n;
      scan_truncated_ = truncated || n > kScanCap;
      memcpy(scan_, tmp, sizeof(WifiAp) * static_cast<size_t>(scan_n_));
      for (int i = 0; i < kJobCap; i++)
        if (jobs_[i].used && strcmp(jobs_[i].id, scan_job_) == 0)
          finish_job(&jobs_[i], now_ms, true, nullptr);
      scan_pending_ = false;
      restore_wifi_state_after_scan();
    } else if (scan_deadline_ms_ != 0 && static_cast<int32_t>(now_ms - scan_deadline_ms_) >= 0) {
      for (int i = 0; i < kJobCap; i++)
        if (jobs_[i].used && strcmp(jobs_[i].id, scan_job_) == 0 && jobs_[i].active)
          finish_job(&jobs_[i], now_ms, false, "RADAR_TIMEOUT");
      scan_pending_ = false;
      restore_wifi_state_after_scan();
    }
  }
  for (int i = 0; i < kJobCap; i++) {
    if (!jobs_[i].used || !jobs_[i].active)
      continue;
    if (strcmp(jobs_[i].action_id, "wifi.provision") == 0 && have_wifi_) {
      char ip[40];
      int rssi = 0;
      int st = wifi_port_.poll_connect(wifi_port_.user, ip, sizeof(ip), &rssi);
      if (st > 0 && (ip[0] == 0 || strcmp(ip, "0.0.0.0") == 0))
        st = 0;
      if (st == 0 && provision_deadline_ms_ != 0 && static_cast<int32_t>(now_ms - provision_deadline_ms_) >= 0)
        st = -1;
      if (st == 0)
        continue;
      if (st > 0) {
        if (!wifi_port_.persist(wifi_port_.user, wifi_ssid_, saved_pass_)) {
          wifi_port_.rollback(wifi_port_.user);
          strcpy(wifi_state_, "disconnected");
          strcpy(wifi_ip_, "null");
          wifi_rssi_known_ = false;
          strcpy(wifi_error_, "STORAGE_FAILED");
          finish_job(&jobs_[i], now_ms, false, "STORAGE_FAILED");
        } else {
          strcpy(wifi_state_, "connected");
          strncpy(wifi_ip_, ip[0] ? ip : "192.168.1.50", sizeof(wifi_ip_) - 1);
          wifi_rssi_ = rssi;
          wifi_rssi_known_ = true;
          strcpy(wifi_error_, "null");
          memset(saved_pass_, 0, sizeof(saved_pass_));
          finish_job(&jobs_[i], now_ms, true, nullptr);
        }
      } else {
        wifi_port_.rollback(wifi_port_.user);
        strcpy(wifi_state_, "disconnected");
        strcpy(wifi_ip_, "null");
        wifi_rssi_known_ = false;
        strcpy(wifi_error_, "VERIFY_FAILED");
        memset(saved_pass_, 0, sizeof(saved_pass_));
        finish_job(&jobs_[i], now_ms, false, "VERIFY_FAILED");
      }
    }
  }
  if (logs_enabled_ && debug_until_ms_ && now_ms >= debug_until_ms_)
    debug_until_ms_ = 0;
  int telem_rate = stream_rate_[0] > 0 ? stream_rate_[0] : 1;
  uint32_t telem_gap = 1000u / static_cast<uint32_t>(telem_rate);
  if (telem_gap == 0)
    telem_gap = 1;
  telem_gap_ms_ = static_cast<int>(telem_gap);
  if (sub_telemetry_ && session_live_ && radar_ && (!stream_sent_[0] || now_ms - stream_last_ms_[0] >= telem_gap)) {
    // Static scratch: poll() runs from the main loop task whose default stack
    // cannot hold 1.8 KiB of serialization locals on top of the loop depth.
    static char body[1200];
    const TelemetryShape shape = telemetry_shape(*radar_, now_ms);
    const bool known_presence = shape.known_presence;
    const bool present = shape.present;
    const char *pos_q = shape.position_quality;
    const char *presence_value = shape.presence_value;
    const char *presence_q = shape.presence_quality;
    const char *targets_q = shape.targets_quality;
    static char metrics[640];
    metrics[0] = 0;
    auto add_metric = [&](const char *key, bool known, bool unsupported, double value, uint32_t sample_ms,
                          bool integral) {
      char one[160];
      const char *q = unsupported ? "unsupported" : (known ? "valid" : "unknown");
      int wr = 0;
      if (!known || unsupported) {
        wr = snprintf(one, sizeof(one), "%s\"%s\":{\"value\":null,\"quality\":\"%s\",\"sample_ms\":null}",
                      metrics[0] ? "," : "", key, q);
      } else if (integral) {
        wr = snprintf(one, sizeof(one), "%s\"%s\":{\"value\":%.0f,\"quality\":\"valid\",\"sample_ms\":%lu}",
                      metrics[0] ? "," : "", key, value, static_cast<unsigned long>(sample_ms));
      } else {
        wr = snprintf(one, sizeof(one), "%s\"%s\":{\"value\":%.1f,\"quality\":\"valid\",\"sample_ms\":%lu}",
                      metrics[0] ? "," : "", key, value, static_cast<unsigned long>(sample_ms));
      }
      if (wr < 0 || static_cast<size_t>(wr) >= sizeof(one) || strlen(metrics) + strlen(one) >= sizeof(metrics))
        return;
      strcat(metrics, one);
    };
    add_metric("distance.cm", radar_->has_distance, false, radar_->distance_cm, radar_->distance_ms, true);
    add_metric("breath_rate", radar_->has_breath, false, radar_->breath, radar_->breath_ms, false);
    add_metric("heart_rate", radar_->has_heart, false, radar_->heart, radar_->heart_ms, false);
    add_metric("diagnostics.local_z", radar_->has_xy, false, radar_->local_z, radar_->position_ms, true);
    add_metric("speed.cm_s", false, true, 0, 0, true);
    add_metric("motion.state", false, false, 0, 0, true);
    add_metric("body.movement", false, false, 0, 0, true);
    add_metric("sleep.state", false, false, 0, 0, true);
    add_metric("areas.occupancy", false, false, 0, 0, true);
    if (!present || !radar_->has_xy) {
      snprintf(body, sizeof(body),
               "{\"source_seq\":%lu,\"sent_ms\":%lu,\"origin\":\"hardware\",\"presence\":{\"value\":%s,\"quality\":\"%"
               "s\",\"sample_ms\":%s},"
               "\"targets_quality\":\"%s\",\"targets_ms\":%s,\"targets\":%s,\"metrics\":{%s}}",
               static_cast<unsigned long>(radar_->source_seq), static_cast<unsigned long>(now_ms), presence_value,
               presence_q, known_presence ? "0" : "null", targets_q, present && radar_->has_xy ? "0" : "null",
               present ? "[]" : "null", metrics);
      if (known_presence) {
        char sample[16];
        snprintf(sample, sizeof(sample), "%lu", static_cast<unsigned long>(radar_->presence_ms));
        snprintf(body, sizeof(body),
                 "{\"source_seq\":%lu,\"sent_ms\":%lu,\"origin\":\"hardware\",\"presence\":{\"value\":%s,\"quality\":"
                 "\"valid\",\"sample_ms\":%s},"
                 "\"targets_quality\":\"%s\",\"targets_ms\":null,\"targets\":%s,\"metrics\":{%s}}",
                 static_cast<unsigned long>(radar_->source_seq), static_cast<unsigned long>(now_ms),
                 radar_->presence ? "true" : "false", sample, targets_q, present ? "[]" : "null", metrics);
      }
    } else {
      const char *boundary = radar_->in_boundary ? "inside" : "outside";
      snprintf(
          body, sizeof(body),
          "{\"source_seq\":%lu,\"sent_ms\":%lu,\"origin\":\"hardware\",\"presence\":{\"value\":true,\"quality\":"
          "\"valid\",\"sample_ms\":%lu},"
          "\"targets_quality\":\"%s\",\"targets_ms\":%lu,\"targets\":[{\"id\":\"t0\",\"local_cm\":[%d,%d],\"room_cm\":["
          "%.1f,%.1f],"
          "\"position_quality\":\"%s\",\"position_ms\":%lu,\"boundary\":\"%s\",\"speed_cm_s\":null}],\"metrics\":{%s}}",
          static_cast<unsigned long>(radar_->source_seq), static_cast<unsigned long>(now_ms),
          static_cast<unsigned long>(radar_->presence_ms), pos_q, static_cast<unsigned long>(radar_->position_ms),
          radar_->local_x, radar_->local_y, static_cast<double>(radar_->room_x), static_cast<double>(radar_->room_y),
          pos_q, static_cast<unsigned long>(radar_->position_ms), boundary, metrics);
    }
    if (last_source_seq_sent_ == radar_->source_seq && telemetry_held_)
      telemetry_coalesced_++;
    last_source_seq_sent_ = radar_->source_seq;
    telemetry_held_ = true;
    for (int i = 0; i < event_n_; i++)
      if (event_code_[i] == 0x8001) {
        memmove(event_q_[i], event_q_[i + 1], sizeof(event_q_[0]) * static_cast<size_t>(event_n_ - i - 1));
        memmove(event_code_ + i, event_code_ + i + 1, sizeof(event_code_[0]) * static_cast<size_t>(event_n_ - i - 1));
        event_n_--;
        telemetry_coalesced_++;
        break;
      }
    emit_event(0x8001, body);
  }
}

bool Service::handle(uint32_t now_ms, uint32_t session, uint32_t request, uint16_t code, const uint8_t *payload,
                     size_t len, char *out, size_t cap, uint32_t *out_session) {
  clock_ms_ = now_ms;
  rx_frames_++;
  if (now_ms - rpc_window_ms_ >= 1000) {
    rpc_window_ms_ = now_ms;
    rpc_count_ = 0;
  }
  if (rpc_count_ >= 10) {
    *out_session = session_live_ ? session_id_ : 0;
    fail(out, cap, "RATE_LIMITED", "RPC limited", nullptr, "{\"retry_after_ms\":1000}");
    return true;
  }
  rpc_count_++;
  if (code != 0x0001) {
    if (!session_ok(session, now_ms))
      return false;
    touched_ms_ = now_ms;
    *out_session = session_id_;
  }
  uint8_t dig[32];
  sha256(payload, len, dig);
  if (code != 0x0001 && session_live_) {
    for (int i = 0; i < kReplay; i++) {
      if (replay_[i].used && replay_[i].request_id == request) {
        if (replay_[i].code == code && memcmp(replay_[i].sha, dig, 32) == 0) {
          if (static_cast<size_t>(replay_[i].len) + 1 > cap)
            return false;
          memcpy(out, replay_[i].body, replay_[i].len + 1);
          return true;
        }
        fail(out, cap, "ID_REUSE", "request_id reused", "request_id", nullptr);
        return true;
      }
    }
    if (request <= seen_max_ && request != 0) {
      fail(out, cap, "REQUEST_EXPIRED", "request expired", "request_id", nullptr);
      return true;
    }
  }
  const char *json = reinterpret_cast<const char *>(payload);
  int wrote = -1;
  if (code == 0x0001) {
    const char *vs = nullptr;
    size_t vn = 0;
    char nonce[40];
    double major = 0, max_payload = 0;
    if (!find_key(json, len, "nonce", &vs, &vn) || !unquote(vs, vn, nonce, sizeof(nonce)) ||
        !hex32(nonce, strlen(nonce))) {
      *out_session = 0;
      wrote = fail(out, cap, "INVALID_ARGUMENT", "bad nonce", "nonce", nullptr);
    } else if (!find_key(json, len, "max_payload", &vs, &vn) || !parse_num(vs, vn, &max_payload)) {
      *out_session = 0;
      wrote = fail(out, cap, "INVALID_ARGUMENT", "bad max_payload", "max_payload", nullptr);
    } else if (max_payload < 4096) {
      *out_session = 0;
      wrote = fail(out, cap, "LIMIT_UNSUPPORTED", "max_payload", "max_payload", nullptr);
    } else {
      const char *pvs = nullptr;
      size_t pvn = 0;
      if (find_key(json, len, "protocol", &pvs, &pvn)) {
        const char *mv = nullptr;
        size_t mn = 0;
        if (!find_key(pvs, pvn, "major", &mv, &mn) || !parse_num(mv, mn, &major) || major != 1) {
          *out_session = 0;
          wrote = fail(out, cap, "VERSION_UNSUPPORTED", "major", "protocol", nullptr);
        }
      } else {
        *out_session = 0;
        wrote = fail(out, cap, "VERSION_UNSUPPORTED", "major", "protocol", nullptr);
      }
    }
    if (wrote < 0) {
      if (session_live_ && strcmp(nonce_, nonce) == 0) {
        *out_session = session_id_;
      } else {
        session_id_ = next_session_++;
        if (session_id_ == 0 || session_id_ == 0xfffffffe)
          session_id_ = next_session_++;
        session_live_ = true;
        touched_ms_ = now_ms;
        seen_max_ = 1;
        strncpy(nonce_, nonce, 32);
        sub_telemetry_ = sub_status_ = sub_config_ = sub_jobs_ = sub_logs_ = false;
        for (int i = 0; i < 5; i++)
          stream_rate_[i] = 0;
        memset(replay_, 0, sizeof(replay_));
        event_n_ = 0;
        *out_session = session_id_;
      }
      const char *sha = id_.git_sha ? id_.git_sha : "";
      wrote = snprintf(
          out, cap,
          "{\"ok\":true,\"result\":{\"nonce\":\"%s\",\"protocol\":{\"major\":1,\"minor\":0},\"boot_id\":\"%s\","
          "\"session_ttl_ms\":15000,\"limits\":{\"max_payload\":4096,\"rpc_inflight\":1,\"max_targets\":%d,\"event_"
          "budget_bps\":8000},"
          "\"identity\":{\"device_id\":\"%s\",\"configured_model\":\"%s\",\"dimension\":\"%s\",\"firmware_version\":\"%"
          "s\"},"
          "\"cap_revision\":\"%s\"}}",
          nonce_, boot_id_, id_.max_targets, id_.device_id, id_.configured_model, id_.dimension, id_.firmware_version,
          id_.cap_revision);
      (void) sha;
    }
  } else if (code == 0x0002) {
    wrote = snprintf(out, cap, "{\"ok\":true,\"result\":{\"uptime_ms\":%lu}}", static_cast<unsigned long>(now_ms));
  } else if (code == 0x0003) {
    uint32_t sid = session_id_;
    wrote = snprintf(out, cap, "{\"ok\":true,\"result\":{\"closed\":true}}");
    *out_session = sid;
    expire_session();
  } else if (code == 0x0010) {
    wrote = snprintf(out, cap,
                     "{\"ok\":true,\"result\":{\"device_id\":\"%s\",\"boot_id\":\"%s\",\"configured_model\":\"%s\","
                     "\"dimension\":\"%s\","
                     "\"firmware_version\":\"%s\",\"git_sha\":%s,\"release_channel\":\"%s\",\"build_profile\":\"%s\","
                     "\"host_protocol\":\"MWCP/1\","
                     "\"radar_identity\":null}}",
                     id_.device_id, boot_id_, id_.configured_model, id_.dimension, id_.firmware_version,
                     id_.git_sha ? id_.git_sha : "null", id_.release_channel, id_.build_profile);
    if (id_.git_sha) {
      wrote = snprintf(out, cap,
                       "{\"ok\":true,\"result\":{\"device_id\":\"%s\",\"boot_id\":\"%s\",\"configured_model\":\"%s\","
                       "\"dimension\":\"%s\","
                       "\"firmware_version\":\"%s\",\"git_sha\":\"%s\",\"release_channel\":\"%s\",\"build_profile\":\"%"
                       "s\",\"host_protocol\":\"MWCP/1\","
                       "\"radar_identity\":null}}",
                       id_.device_id, boot_id_, id_.configured_model, id_.dimension, id_.firmware_version, id_.git_sha,
                       id_.release_channel, id_.build_profile);
    }
  } else if (code == 0x0012) {
    const char *link = "waiting";
    unsigned long last = 0;
    bool known = false;
    if (radar_ && radar_->seen_frame) {
      known = true;
      last = radar_->last_frame_ms;
      link = now_ms - radar_->last_frame_ms >= 2000 ? "stale" : "healthy";
    }
    wrote = snprintf(out, cap,
                     "{\"ok\":true,\"result\":{\"uptime_ms\":%lu,\"radar_link\":\"%s\",\"last_radar_frame_ms\":%s,"
                     "\"config_revision\":\"%s\","
                     "\"config_storage\":\"%s\",\"active_jobs\":[],\"counters\":{\"rx_frames\":%lu,\"rx_crc_errors\":0,"
                     "\"rx_oversize\":0,"
                     "\"invalid_requests\":%lu,\"radar_frames\":%lu,\"radar_errors\":%lu,\"telemetry_coalesced\":%lu,"
                     "\"logs_dropped\":%lu,\"tx_overflow\":%lu}}}",
                     static_cast<unsigned long>(now_ms), link, known ? "0" : "null", revision_, storage_,
                     static_cast<unsigned long>(rx_frames_), static_cast<unsigned long>(invalid_requests_),
                     static_cast<unsigned long>(radar_ ? radar_->frames : 0),
                     static_cast<unsigned long>(radar_ ? radar_->errors : 0),
                     static_cast<unsigned long>(telemetry_coalesced_), static_cast<unsigned long>(logs_dropped_),
                     static_cast<unsigned long>(tx_overflow_));
    if (known) {
      char lastbuf[16];
      snprintf(lastbuf, sizeof(lastbuf), "%lu", last);
      wrote = snprintf(out, cap,
                       "{\"ok\":true,\"result\":{\"uptime_ms\":%lu,\"radar_link\":\"%s\",\"last_radar_frame_ms\":%s,"
                       "\"config_revision\":\"%s\","
                       "\"config_storage\":\"%s\",\"active_jobs\":[],\"counters\":{\"rx_frames\":%lu,\"rx_crc_errors\":"
                       "0,\"rx_oversize\":0,"
                       "\"invalid_requests\":%lu,\"radar_frames\":%lu,\"radar_errors\":%lu,\"telemetry_coalesced\":%lu,"
                       "\"logs_dropped\":%lu,\"tx_overflow\":%lu}}}",
                       static_cast<unsigned long>(now_ms), link, lastbuf, revision_, storage_,
                       static_cast<unsigned long>(rx_frames_), static_cast<unsigned long>(invalid_requests_),
                       static_cast<unsigned long>(radar_->frames), static_cast<unsigned long>(radar_->errors),
                       static_cast<unsigned long>(telemetry_coalesced_), static_cast<unsigned long>(logs_dropped_),
                       static_cast<unsigned long>(tx_overflow_));
    }
  } else if (code == 0x0021 || code == 0x0022) {
    const char *vs = nullptr;
    size_t vn = 0;
    char base[24];
    char op[40] = "";
    if (!find_key(json, len, "base_revision", &vs, &vn) || !unquote(vs, vn, base, sizeof(base))) {
      wrote = fail(out, cap, "INVALID_ARGUMENT", "base_revision", "base_revision", nullptr);
    } else if (code == 0x0022) {
      if (!find_key(json, len, "op_id", &vs, &vn) || !unquote(vs, vn, op, sizeof(op)) || !uuid_ok(op, strlen(op))) {
        wrote = fail(out, cap, "INVALID_ARGUMENT", "op_id", "op_id", nullptr);
      } else {
        for (int i = 0; i < kCommitRing; i++) {
          if (!commits_[i].used || strcmp(commits_[i].op_id, op) != 0)
            continue;
          if (memcmp(commits_[i].sha, dig, 32) != 0) {
            wrote = fail(out, cap, "OP_ID_REUSE", "op_id reused", "op_id", nullptr);
          } else {
            wrote = snprintf(out, cap,
                             "{\"ok\":true,\"result\":{\"op_id\":\"%s\",\"revision\":\"%s\",\"persisted\":true,"
                             "\"restart_required\":false}}",
                             op, commits_[i].revision);
          }
          break;
        }
      }
    }
    if (wrote < 0) {
      if (strcmp(storage_, "recovery_required") == 0) {
        wrote = fail(out, cap, "STORAGE_FAILED", "recovery required", nullptr, nullptr);
      } else if (revision_u64() == 0xffffffffffffffffull) {
        wrote = fail(out, cap, "STORAGE_FAILED", "revision limit", "base_revision", nullptr);
      } else if (revcmp(base, revision_) != 0) {
        char details[64];
        snprintf(details, sizeof(details), "{\"current_revision\":\"%s\"}", revision_);
        wrote = fail(out, cap, "REVISION_CONFLICT", "Configuration changed", "base_revision", details);
      } else if (!find_key(json, len, "changes", &vs, &vn)) {
        wrote = fail(out, cap, "INVALID_ARGUMENT", "changes", "changes", nullptr);
      } else if (code == 0x0022 && tokens_ <= 0) {
        wrote = fail(out, cap, "RATE_LIMITED", "Write limited", nullptr, "{\"retry_after_ms\":1000}");
      } else {
        const char *field = nullptr;
        const char *ecode = "INVALID_ARGUMENT";
        const int32_t saved_x = x_cm_;
        const int32_t saved_y = y_cm_;
        const int32_t saved_z = z_cm_;
        const bool saved_boundary = boundary_set_;
        const uint8_t saved_bn = boundary_n_;
        Point saved_pts[64];
        memcpy(saved_pts, boundary_, sizeof(saved_pts));
        Area saved_areas[3];
        memcpy(saved_areas, areas_, sizeof(saved_areas));
        const int16_t saved_yaw = yaw_tenth_;
        const int16_t saved_pitch = pitch_half_;
        const int16_t saved_roll = roll_half_;
        auto restore = [&]() {
          x_cm_ = saved_x;
          y_cm_ = saved_y;
          z_cm_ = saved_z;
          boundary_set_ = saved_boundary;
          boundary_n_ = saved_bn;
          memcpy(boundary_, saved_pts, sizeof(saved_pts));
          memcpy(areas_, saved_areas, sizeof(saved_areas));
          yaw_tenth_ = saved_yaw;
          pitch_half_ = saved_pitch;
          roll_half_ = saved_roll;
        };
        if (!apply_changes(reinterpret_cast<const uint8_t *>(vs), vn, nullptr, 0, &field, &ecode, false)) {
          restore();
          wrote = fail(out, cap, ecode, "invalid changes", field, nullptr);
        } else if (code == 0x0021) {
          restore();
          wrote = snprintf(
              out, cap, "{\"ok\":true,\"result\":{\"valid\":true,\"base_revision\":\"%s\",\"restart_required\":false}}",
              revision_);
        } else if (!apply_changes(reinterpret_cast<const uint8_t *>(vs), vn, nullptr, 0, &field, &ecode, true)) {
          restore();
          wrote = fail(out, cap, ecode, "invalid changes", field, nullptr);
        } else {
          char saved_rev[24];
          strncpy(saved_rev, revision_, sizeof(saved_rev) - 1);
          tokens_--;
          if (token_ms_ == 0)
            token_ms_ = now_ms;
          bump_revision();
          Commit saved_commit = commits_[commit_next_ % kCommitRing];
          int saved_next = commit_next_;
          Commit &c = commits_[commit_next_ % kCommitRing];
          int commit_slot = commit_next_ % kCommitRing;
          commit_next_++;
          memset(&c, 0, sizeof(c));
          c.used = true;
          strncpy(c.op_id, op, sizeof(c.op_id) - 1);
          memcpy(c.sha, dig, 32);
          strncpy(c.revision, revision_, sizeof(c.revision) - 1);
          bool persisted = persist_config();
          if (!persisted) {
            restore();
            strncpy(revision_, saved_rev, sizeof(revision_) - 1);
            commits_[commit_slot] = saved_commit;
            commit_next_ = saved_next;
            tokens_++;
            wrote = fail(out, cap, "STORAGE_FAILED", "persist failed", nullptr, nullptr);
          } else {
            wrote = snprintf(out, cap,
                             "{\"ok\":true,\"result\":{\"op_id\":\"%s\",\"revision\":\"%s\",\"persisted\":true,"
                             "\"restart_required\":false}}",
                             op, revision_);
            emit_event(0x8003, "{\"origin\":\"host\"}");
            if (publish_hook_)
              publish_hook_(publish_user_);
          }
        }
      }
    }
  } else if (code == 0x0023) {
    const char *vs = nullptr;
    size_t vn = 0;
    char op[40];
    if (!find_key(json, len, "op_id", &vs, &vn) || !unquote(vs, vn, op, sizeof(op))) {
      wrote = fail(out, cap, "INVALID_ARGUMENT", "op_id", "op_id", nullptr);
    } else {
      bool found = false;
      const char *rev = revision_;
      for (int i = 0; i < kCommitRing; i++)
        if (commits_[i].used && strcmp(commits_[i].op_id, op) == 0) {
          found = true;
          rev = commits_[i].revision;
        }
      wrote = snprintf(out, cap, "{\"ok\":true,\"result\":{\"found\":%s,\"revision\":%s,\"current_revision\":\"%s\"}}",
                       found ? "true" : "false", found ? rev : "null", revision_);
      if (found) {
        wrote = snprintf(out, cap,
                         "{\"ok\":true,\"result\":{\"found\":true,\"revision\":\"%s\",\"current_revision\":\"%s\"}}",
                         rev, revision_);
      }
    }
  } else if (code == 0x0041 || code == 0x0051 || code == 0x0052) {
    const char *vs = nullptr;
    size_t vn = 0;
    char op[40];
    char action[32] = "wifi.scan";
    char confirm[40] = "";
    const char *resource = "wifi";
    bool need_confirm = false;
    if (!find_key(json, len, "op_id", &vs, &vn) || !unquote(vs, vn, op, sizeof(op)) || !uuid_ok(op, strlen(op))) {
      wrote = fail(out, cap, "INVALID_ARGUMENT", "op_id", "op_id", nullptr);
    } else if (code == 0x0041) {
      if (!find_key(json, len, "action_id", &vs, &vn) || !unquote(vs, vn, action, sizeof(action))) {
        wrote = fail(out, cap, "INVALID_ARGUMENT", "action_id", "action_id", nullptr);
      } else if (strcmp(action, "device.restart") != 0 && strcmp(action, "radar.reset_module") != 0) {
        wrote = fail(out, cap, "UNSUPPORTED", "Unsupported action", nullptr, "{\"field\":\"action_id\"}");
      } else {
        need_confirm = true;
        resource = strcmp(action, "device.restart") == 0 ? "restart" : "radar";
        if (find_key(json, len, "confirm", &vs, &vn))
          unquote(vs, vn, confirm, sizeof(confirm));
        bool created = false;
        if (!admit_job(now_ms, op, dig, action, resource, need_confirm, confirm, out, cap, &created))
          wrote = 1;
        else {
          wrote = static_cast<int>(strlen(out));
          if (created && strcmp(action, "device.restart") == 0)
            restart_pending_ = true;
          if (created && strcmp(action, "radar.reset_module") == 0) {
            const int rc = reset_module_ ? reset_module_(reset_user_) : -1;
            if (reset_module_)
              reset_sends_++;
            for (int i = 0; i < kJobCap; i++)
              if (jobs_[i].used && jobs_[i].active && strcmp(jobs_[i].action_id, action) == 0)
                finish_job(&jobs_[i], now_ms, rc == 0, rc == 0 ? nullptr : "RADAR_UNAVAILABLE");
          }
        }
      }
    } else if (code == 0x0052) {
      char ssid[33];
      char auth[16];
      char password[80];
      if (!find_key(json, len, "ssid", &vs, &vn) || !unquote(vs, vn, ssid, sizeof(ssid)) ||
          !find_key(json, len, "auth", &vs, &vn) || !unquote(vs, vn, auth, sizeof(auth)) ||
          !find_key(json, len, "password", &vs, &vn) || !unquote(vs, vn, password, sizeof(password))) {
        wrote = fail(out, cap, "INVALID_ARGUMENT", "wifi", "ssid", nullptr);
      } else if (strcmp(auth, "open") != 0 && strcmp(auth, "wpa2_psk") != 0) {
        wrote = fail(out, cap, "UNSUPPORTED", "auth", "auth", nullptr);
      } else if (strcmp(auth, "open") == 0 && password[0]) {
        wrote = fail(out, cap, "INVALID_ARGUMENT", "open password", "password", nullptr);
      } else if (strcmp(auth, "wpa2_psk") == 0 && strlen(password) < 8) {
        wrote = fail(out, cap, "INVALID_ARGUMENT", "psk length", "password", nullptr);
      } else {
        bool created = false;
        if (!admit_job(now_ms, op, dig, "wifi.provision", "wifi", false, nullptr, out, cap, &created))
          wrote = 1;
        else {
          wrote = static_cast<int>(strlen(out));
          if (created) {
            strncpy(saved_ssid_, wifi_ssid_, sizeof(saved_ssid_) - 1);
            strncpy(wifi_ssid_, ssid, sizeof(wifi_ssid_) - 1);
            strncpy(saved_pass_, password, sizeof(saved_pass_) - 1);
            memset(password, 0, sizeof(password));
            strcpy(wifi_state_, "connecting");
            provision_deadline_ms_ = now_ms + 60000;
            strncpy(provision_ssid_, wifi_ssid_, sizeof(provision_ssid_) - 1);
            strcpy(wifi_error_, "null");
            if (have_wifi_)
              wifi_port_.start_connect(wifi_port_.user, wifi_ssid_, saved_pass_, auth);
          }
        }
      }
    } else {
      bool created = false;
      if (!admit_job(now_ms, op, dig, "wifi.scan", "wifi", false, nullptr, out, cap, &created))
        wrote = 1;
      else {
        wrote = static_cast<int>(strlen(out));
        if (created) {
          scan_prev_connected_ = strcmp(wifi_state_, "connected") == 0;
          strcpy(wifi_state_, "scanning");
          scan_deadline_ms_ = now_ms + 15000;
          scan_job_[0] = 0;
          scan_truncated_ = false;
          for (int i = 0; i < kJobCap; i++)
            if (jobs_[i].used && jobs_[i].active && strcmp(jobs_[i].action_id, "wifi.scan") == 0)
              strncpy(scan_job_, jobs_[i].id, sizeof(scan_job_) - 1);
          ScanStart started = have_wifi_ ? wifi_port_.start_scan(wifi_port_.user) : ScanStart::kUnsupported;
          if (started != ScanStart::kStarted) {
            const char *code = started == ScanStart::kUnsupported ? "UNSUPPORTED" : "RADAR_UNAVAILABLE";
            for (int i = 0; i < kJobCap; i++)
              if (jobs_[i].used && jobs_[i].active && strcmp(jobs_[i].id, scan_job_) == 0)
                finish_job(&jobs_[i], now_ms, false, code);
            scan_job_[0] = 0;
            restore_wifi_state_after_scan();
          } else {
            scan_pending_ = true;
            scan_generation_++;
            scan_n_ = 0;
          }
        }
      }
    }
  } else if (code == 0x0042) {
    const char *vs = nullptr;
    size_t vn = 0;
    char idbuf[40] = "missing";
    bool by_op = false;
    if (find_key(json, len, "job_id", &vs, &vn))
      unquote(vs, vn, idbuf, sizeof(idbuf));
    else if (find_key(json, len, "op_id", &vs, &vn)) {
      unquote(vs, vn, idbuf, sizeof(idbuf));
      by_op = true;
    }
    const Job *found = nullptr;
    for (int i = 0; i < kJobCap; i++) {
      if (!jobs_[i].used)
        continue;
      if ((by_op && strcmp(jobs_[i].op_id, idbuf) == 0) || (!by_op && strcmp(jobs_[i].id, idbuf) == 0))
        found = &jobs_[i];
    }
    if (!found) {
      wrote = snprintf(out, cap,
                       "{\"ok\":true,\"result\":{\"job_id\":\"%s\",\"op_id\":null,\"action_id\":\"unknown\",\"state\":"
                       "\"unknown\",\"stage\":null,"
                       "\"progress\":null,\"started_ms\":null,\"finished_ms\":null,\"result\":null,\"error\":null}}",
                       by_op ? "missing" : idbuf);
    } else {
      static char job_json[512];
      write_job(*found, job_json, sizeof(job_json));
      wrote = snprintf(out, cap, "{\"ok\":true,\"result\":%s}", job_json);
    }
  } else if (code == 0x0050) {
    wrote = snprintf(
        out, cap,
        "{\"ok\":true,\"result\":{\"state\":\"%s\",\"ssid\":\"%s\",\"ip\":%s,\"rssi_dbm\":%s,\"last_error\":%s}}",
        wifi_state_, wifi_ssid_, strcmp(wifi_ip_, "null") == 0 ? "null" : wifi_ip_, wifi_rssi_known_ ? "0" : "null",
        strcmp(wifi_error_, "null") == 0 ? "null" : wifi_error_);
    if (strcmp(wifi_ip_, "null") != 0 || wifi_rssi_known_ || strcmp(wifi_error_, "null") != 0) {
      char rssi[16] = "null";
      char err[40] = "null";
      if (wifi_rssi_known_)
        snprintf(rssi, sizeof(rssi), "%d", wifi_rssi_);
      if (strcmp(wifi_error_, "null") != 0)
        snprintf(err, sizeof(err), "\"%s\"", wifi_error_);
      wrote = snprintf(
          out, cap,
          "{\"ok\":true,\"result\":{\"state\":\"%s\",\"ssid\":\"%s\",\"ip\":%s,\"rssi_dbm\":%s,\"last_error\":%s}}",
          wifi_state_, wifi_ssid_, strcmp(wifi_ip_, "null") == 0 ? "null" : wifi_ip_, rssi, err);
      if (strcmp(wifi_ip_, "null") != 0) {
        wrote = snprintf(out, cap,
                         "{\"ok\":true,\"result\":{\"state\":\"%s\",\"ssid\":\"%s\",\"ip\":\"%s\",\"rssi_dbm\":%s,"
                         "\"last_error\":%s}}",
                         wifi_state_, wifi_ssid_, wifi_ip_, rssi, err);
      }
    }
  } else if (code == 0x0030) {
    sub_telemetry_ = sub_status_ = sub_config_ = sub_jobs_ = sub_logs_ = false;
    for (int i = 0; i < 5; i++)
      stream_rate_[i] = 0;
    const char *vs = nullptr;
    size_t vn = 0;
    char accepted[320] = "";
    if (find_key(json, len, "streams", &vs, &vn)) {
      auto take = [&](const char *id, bool *flag, int rate_index) {
        const char *hit = nullptr;
        for (size_t i = 0; i + strlen(id) + 6 < vn; i++) {
          if (memcmp(vs + i, "\"id\":\"", 6) == 0 && memcmp(vs + i + 6, id, strlen(id)) == 0 &&
              vs[i + 6 + strlen(id)] == '"')
            hit = vs + i;
        }
        if (!hit)
          return;
        const char *obj = hit;
        while (obj > vs && *obj != '{')
          obj--;
        const char *end = hit;
        while (end < vs + vn && *end != '}')
          end++;
        int rate = 1;
        for (const char *q = obj; q + 12 < end; q++) {
          if (memcmp(q, "max_rate_hz", 11) == 0) {
            const char *n = q + 11;
            while (n < end && (*n == '"' || *n == ':' || *n == ' '))
              n++;
            rate = atoi(n);
            break;
          }
        }
        if (rate < 0)
          rate = 0;
        if (rate > 20)
          rate = 20;
        *flag = true;
        stream_rate_[rate_index] = rate;
        stream_sent_[rate_index] = false;
        char piece[48];
        snprintf(piece, sizeof(piece), "%s{\"id\":\"%s\",\"max_rate_hz\":%d}", accepted[0] ? "," : "", id, rate);
        if (strlen(accepted) + strlen(piece) < sizeof(accepted))
          strcat(accepted, piece);
      };
      take("telemetry", &sub_telemetry_, 0);
      take("status", &sub_status_, 1);
      take("config", &sub_config_, 2);
      take("jobs", &sub_jobs_, 3);
      take("logs", &sub_logs_, 4);
      if (sub_telemetry_ && stream_rate_[0] > 0)
        telem_gap_ms_ = 1000 / stream_rate_[0];
    }
    double budget = 8000;
    if (find_key(json, len, "event_budget_bps", &vs, &vn))
      parse_num(vs, vn, &budget);
    if (budget > 8000)
      budget = 8000;
    if (budget < 1000)
      budget = 1000;
    event_budget_ = static_cast<int>(budget);
    budget_left_ = event_budget_;
    wrote = snprintf(out, cap, "{\"ok\":true,\"result\":{\"streams\":[%s],\"event_budget_bps\":%d}}", accepted,
                     event_budget_);
  } else if (code == 0x0011 || code == 0x0040) {
    const char *const *table = code == 0x0011 ? kCaps : kActions;
    int count = code == 0x0011 ? 19 : 2;
    const char *rev = code == 0x0011 ? id_.cap_revision : "actions-1";
    const char *vs = nullptr;
    size_t vn = 0;
    int start = 0;
    if (find_key(json, len, "cursor", &vs, &vn) && !(vn == 4 && memcmp(vs, "null", 4) == 0)) {
      char cursor[80];
      if (!unquote(vs, vn, cursor, sizeof(cursor))) {
        wrote = fail(out, cap, "INVALID_ARGUMENT", "Bad cursor", "cursor", nullptr);
      } else {
        char prefix[16];
        snprintf(prefix, sizeof(prefix), "%lu:", static_cast<unsigned long>(session_id_));
        if (strncmp(cursor, prefix, strlen(prefix)) != 0)
          wrote = fail(out, cap, "INVALID_ARGUMENT", "Bad cursor", "cursor", nullptr);
        else {
          const char *rest = cursor + strlen(prefix);
          const char *colon = strchr(rest, ':');
          bool digits = colon && colon > rest;
          for (const char *p = rest; digits && p < colon; p++)
            if (*p < '0' || *p > '9')
              digits = false;
          unsigned long off = 0;
          if (!digits || static_cast<size_t>(colon - rest) > 9) {
            wrote = fail(out, cap, "INVALID_ARGUMENT", "Bad cursor", "cursor", nullptr);
          } else {
            for (const char *p = rest; p < colon; p++)
              off = off * 10ul + static_cast<unsigned long>(*p - '0');
            if (off > static_cast<unsigned long>(count))
              wrote = fail(out, cap, "INVALID_ARGUMENT", "Bad cursor", "cursor", nullptr);
            else if (strcmp(colon + 1, rev) != 0) {
              char details[64];
              snprintf(details, sizeof(details), "{\"current_revision\":\"%s\"}", rev);
              wrote = fail(out, cap, "REVISION_CONFLICT", "Snapshot changed", "cursor", details);
            } else
              start = static_cast<int>(off);
          }
        }
      }
    }
    if (wrote < 0) {
      int n = start + kPage < count ? kPage : count - start;
      if (n < 0)
        n = 0;
      static char items[1800];
      items[0] = 0;
      for (int i = 0; i < n; i++) {
        if (i)
          strcat(items, ",");
        strcat(items, table[start + i]);
      }
      if (start + kPage < count)
        wrote = snprintf(out, cap,
                         "{\"ok\":true,\"result\":{\"revision\":\"%s\",\"items\":[%s],\"next_cursor\":\"%lu:%d:%s\"}}",
                         rev, items, static_cast<unsigned long>(session_id_), start + kPage, rev);
      else
        wrote = snprintf(out, cap, "{\"ok\":true,\"result\":{\"revision\":\"%s\",\"items\":[%s],\"next_cursor\":null}}",
                         rev, items);
    }
  } else if (code == 0x0020) {
    const char *keys[] = {"install.x_cm",      "install.y_cm",     "install.z_cm",         "install.yaw_deg",
                          "install.pitch_deg", "install.roll_deg", "geometry.boundary_cm", "areas.definitions"};
    const int count = 8;
    int start = 0;
    const char *cvs = nullptr;
    size_t cvn = 0;
    if (find_key(json, len, "cursor", &cvs, &cvn) && !(cvn == 4 && memcmp(cvs, "null", 4) == 0)) {
      char cursor[80];
      if (!unquote(cvs, cvn, cursor, sizeof(cursor)) || strncmp(cursor, "cfg:", 4) != 0) {
        wrote = fail(out, cap, "INVALID_ARGUMENT", "Bad cursor", "cursor", nullptr);
      } else {
        char prefix[24];
        snprintf(prefix, sizeof(prefix), "cfg:%lu:", static_cast<unsigned long>(session_id_));
        if (strncmp(cursor, prefix, strlen(prefix)) != 0)
          wrote = fail(out, cap, "INVALID_ARGUMENT", "Bad cursor", "cursor", nullptr);
        else {
          const char *rest = cursor + strlen(prefix);
          const char *colon = strchr(rest, ':');
          bool digits = colon && colon > rest;
          for (const char *p = rest; digits && p < colon; p++)
            if (*p < '0' || *p > '9')
              digits = false;
          unsigned long off = 0;
          if (!digits)
            wrote = fail(out, cap, "INVALID_ARGUMENT", "Bad cursor", "cursor", nullptr);
          else {
            for (const char *p = rest; p < colon; p++)
              off = off * 10ul + static_cast<unsigned long>(*p - '0');
            if (off > 8)
              wrote = fail(out, cap, "INVALID_ARGUMENT", "Bad cursor", "cursor", nullptr);
            else if (strcmp(colon + 1, revision_) != 0)
              wrote = fail(out, cap, "REVISION_CONFLICT", "Snapshot changed", "cursor", nullptr);
            else
              start = static_cast<int>(off);
          }
        }
      }
    }
    if (wrote < 0) {
      // Pagination scratch is static: the CONFIG_READ builder needs several
      // kilobytes that the 3.5 KiB main task stack cannot hold alongside the
      // dispatch frame. Single-threaded main-loop path, written before read.
      static char items[3600];
      items[0] = 0;
      bool page_ok = true;
      int n = start + 2 < count ? 2 : count - start;
      for (int i = 0; i < n && page_ok; i++) {
        static char one[1700];
        one[0] = 0;
        const char *key = keys[start + i];
        int item_wr = -1;
        if (strcmp(key, "install.x_cm") == 0)
          item_wr = snprintf(one, sizeof(one), "{\"key\":\"install.x_cm\",\"value\":%ld}", static_cast<long>(x_cm_));
        else if (strcmp(key, "install.y_cm") == 0)
          item_wr = snprintf(one, sizeof(one), "{\"key\":\"install.y_cm\",\"value\":%ld}", static_cast<long>(y_cm_));
        else if (strcmp(key, "install.z_cm") == 0)
          item_wr = snprintf(one, sizeof(one), "{\"key\":\"install.z_cm\",\"value\":%ld}", static_cast<long>(z_cm_));
        else if (strcmp(key, "install.yaw_deg") == 0)
          item_wr = snprintf(one, sizeof(one), "{\"key\":\"install.yaw_deg\",\"value\":%.1f}",
                             static_cast<double>(yaw_tenth_) / 10.0);
        else if (strcmp(key, "install.pitch_deg") == 0)
          item_wr = snprintf(one, sizeof(one), "{\"key\":\"install.pitch_deg\",\"value\":%.1f}",
                             static_cast<double>(pitch_half_) / 2.0);
        else if (strcmp(key, "install.roll_deg") == 0)
          item_wr = snprintf(one, sizeof(one), "{\"key\":\"install.roll_deg\",\"value\":%.1f}",
                             static_cast<double>(roll_half_) / 2.0);
        else if (strcmp(key, "geometry.boundary_cm") == 0) {
          if (!boundary_set_)
            item_wr = snprintf(one, sizeof(one), "{\"key\":\"geometry.boundary_cm\",\"value\":null}");
          else {
            static char poly[1500];
            poly[0] = 0;
            bool fit = true;
            for (int p = 0; p < boundary_n_ && fit; p++) {
              char pair[24];
              int wr = snprintf(pair, sizeof(pair), "%s[%d,%d]", p ? "," : "", boundary_[p].x, boundary_[p].y);
              if (wr < 0 || static_cast<size_t>(wr) >= sizeof(pair) ||
                  strlen(poly) + static_cast<size_t>(wr) >= sizeof(poly))
                fit = false;
              else
                strcat(poly, pair);
            }
            item_wr = snprintf(one, sizeof(one), "{\"key\":\"geometry.boundary_cm\",\"value\":[%s]}", poly);
            if (!fit)
              item_wr = -1;
          }
        } else {
          static char areas_json[1600];
          areas_json[0] = 0;
          bool fit = true;
          for (int a = 0; a < 3 && fit; a++) {
            if (!areas_[a].used)
              continue;
            char name_esc[80];
            if (!json_escape(areas_[a].name, name_esc, sizeof(name_esc))) {
              fit = false;
              break;
            }
            char pts_json[400];
            pts_json[0] = 0;
            for (int p = 0; p < areas_[a].n && fit; p++) {
              char pair[24];
              int wr =
                  snprintf(pair, sizeof(pair), "%s[%d,%d]", p ? "," : "", areas_[a].points[p].x, areas_[a].points[p].y);
              if (wr < 0 || static_cast<size_t>(wr) >= sizeof(pair) ||
                  strlen(pts_json) + static_cast<size_t>(wr) >= sizeof(pts_json))
                fit = false;
              else
                strcat(pts_json, pair);
            }
            char slotj[480];
            int wr = snprintf(slotj, sizeof(slotj), "%s{\"slot\":%u,\"enabled\":%s,\"name\":\"%s\",\"points_cm\":[%s]}",
                              areas_json[0] ? "," : "", areas_[a].slot, areas_[a].enabled ? "true" : "false", name_esc,
                              pts_json);
            if (wr < 0 || static_cast<size_t>(wr) >= sizeof(slotj) ||
                strlen(areas_json) + static_cast<size_t>(wr) >= sizeof(areas_json))
              fit = false;
            else
              strcat(areas_json, slotj);
          }
          item_wr = fit ? snprintf(one, sizeof(one), "{\"key\":\"areas.definitions\",\"value\":[%s]}", areas_json) : -1;
        }
        if (item_wr < 0 || static_cast<size_t>(item_wr) >= sizeof(one) ||
            strlen(items) + static_cast<size_t>(item_wr) + 2 >= sizeof(items)) {
          page_ok = false;
          break;
        }
        if (items[0])
          strcat(items, ",");
        strcat(items, one);
      }
      if (!page_ok) {
        wrote = fail(out, cap, "PAYLOAD_TOO_LARGE", "config page", nullptr, nullptr);
      } else {
        int included = 0;
        static char accepted_items[3600];
        accepted_items[0] = 0;
        static char piece[1700];
        piece[0] = 0;
        const char *cursor = items;
        while (included < n && *cursor) {
          if (*cursor == ',')
            cursor++;
          const char *end = cursor;
          int depth = 0;
          bool in_str = false;
          bool esc = false;
          for (; *end; end++) {
            if (in_str) {
              if (esc)
                esc = false;
              else if (*end == '\\')
                esc = true;
              else if (*end == '"')
                in_str = false;
              continue;
            }
            if (*end == '"')
              in_str = true;
            else if (*end == '{' || *end == '[')
              depth++;
            else if (*end == '}' || *end == ']') {
              depth--;
              if (depth == 0) {
                end++;
                break;
              }
            }
          }
          size_t piece_n = static_cast<size_t>(end - cursor);
          if (piece_n == 0 || piece_n >= sizeof(piece))
            break;
          memcpy(piece, cursor, piece_n);
          piece[piece_n] = 0;
          static char trial_items[3600];
          int items_wr =
              snprintf(trial_items, sizeof(trial_items), "%s%s%s", accepted_items, accepted_items[0] ? "," : "", piece);
          if (items_wr < 0 || static_cast<size_t>(items_wr) >= sizeof(trial_items))
            break;
          static char trial[4096];
          int next = start + included + 1;
          int trial_wr =
              next < count
                  ? snprintf(trial, sizeof(trial),
                             "{\"ok\":true,\"result\":{\"revision\":\"%s\",\"items\":[%s],\"next_cursor\":\"cfg:%lu:%d:"
                             "%s\"}}",
                             revision_, trial_items, static_cast<unsigned long>(session_id_), next, revision_)
                  : snprintf(trial, sizeof(trial),
                             "{\"ok\":true,\"result\":{\"revision\":\"%s\",\"items\":[%s],\"next_cursor\":null}}",
                             revision_, trial_items);
          if (trial_wr < 0 || static_cast<size_t>(trial_wr) >= sizeof(trial) ||
              !mwcp::json_check(reinterpret_cast<const uint8_t *>(trial), static_cast<size_t>(trial_wr)))
            break;
          if (snprintf(accepted_items, sizeof(accepted_items), "%s", trial_items) < 0)
            break;
          included++;
          cursor = end;
        }
        if (included == 0) {
          wrote = fail(out, cap, "PAYLOAD_TOO_LARGE", "config page", nullptr, nullptr);
        } else if (start + included < count) {
          wrote = snprintf(
              out, cap,
              "{\"ok\":true,\"result\":{\"revision\":\"%s\",\"items\":[%s],\"next_cursor\":\"cfg:%lu:%d:%s\"}}",
              revision_, accepted_items, static_cast<unsigned long>(session_id_), start + included, revision_);
        } else {
          wrote =
              snprintf(out, cap, "{\"ok\":true,\"result\":{\"revision\":\"%s\",\"items\":[%s],\"next_cursor\":null}}",
                       revision_, accepted_items);
        }
        if (included > 0 && (wrote < 0 || static_cast<size_t>(wrote) >= cap))
          wrote = fail(out, cap, "PAYLOAD_TOO_LARGE", "config page", nullptr, nullptr);
      }
    }
  } else if (code == 0x0031) {
    const char *sv = nullptr;
    size_t sn = 0;
    char removed[120] = "";
    if (!find_key(json, len, "streams", &sv, &sn))
      wrote = fail(out, cap, "INVALID_ARGUMENT", "streams", "streams", nullptr);
    else {
      auto drop = [&](const char *id, bool *flag) {
        bool hit = false;
        for (size_t i = 0; i + strlen(id) + 2 < sn; i++)
          if (sv[i] == '"' && memcmp(sv + i + 1, id, strlen(id)) == 0 && sv[i + 1 + strlen(id)] == '"')
            hit = true;
        if (!hit || !*flag)
          return;
        *flag = false;
        if (removed[0])
          strncat(removed, ",", sizeof(removed) - strlen(removed) - 1);
        strncat(removed, "\"", sizeof(removed) - strlen(removed) - 1);
        strncat(removed, id, sizeof(removed) - strlen(removed) - 1);
        strncat(removed, "\"", sizeof(removed) - strlen(removed) - 1);
      };
      drop("telemetry", &sub_telemetry_);
      drop("status", &sub_status_);
      drop("config", &sub_config_);
      drop("jobs", &sub_jobs_);
      drop("logs", &sub_logs_);
      wrote = snprintf(out, cap, "{\"ok\":true,\"result\":{\"removed\":[%s]}}", removed);
    }
  } else if (code == 0x0053) {
    const char *jv = nullptr;
    size_t jn = 0;
    char job[16];
    if (!find_key(json, len, "job_id", &jv, &jn) || !unquote(jv, jn, job, sizeof(job)) || strcmp(job, scan_job_) != 0)
      wrote = fail(out, cap, "INVALID_ARGUMENT", "scan job", "job_id", nullptr);
    else if (scan_pending_)
      wrote = fail(out, cap, "BUSY", "scan running", "job_id", nullptr);
    else {
      int start = 0;
      const char *cv = nullptr;
      size_t cn = 0;
      if (find_key(json, len, "cursor", &cv, &cn) && !(cn == 4 && memcmp(cv, "null", 4) == 0)) {
        char cursor[24];
        if (!unquote(cv, cn, cursor, sizeof(cursor)))
          wrote = fail(out, cap, "INVALID_ARGUMENT", "Bad cursor", "cursor", nullptr);
        else {
          unsigned long off = 0;
          for (const char *p = cursor; *p && wrote < 0; p++) {
            if (*p < '0' || *p > '9')
              wrote = fail(out, cap, "INVALID_ARGUMENT", "Bad cursor", "cursor", nullptr);
            else
              off = off * 10ul + static_cast<unsigned long>(*p - '0');
          }
          if (wrote < 0 && off > static_cast<unsigned long>(scan_n_))
            wrote = fail(out, cap, "INVALID_ARGUMENT", "Bad cursor", "cursor", nullptr);
          else if (wrote < 0)
            start = static_cast<int>(off);
        }
      }
      if (wrote < 0) {
        static char items[800];
        items[0] = 0;
        int n = start + 2 < scan_n_ ? 2 : scan_n_ - start;
        if (n < 0)
          n = 0;
        bool fit = true;
        for (int i = 0; i < n && fit; i++) {
          char ssid_esc[80];
          if (!json_escape(scan_[start + i].ssid, ssid_esc, sizeof(ssid_esc)))
            fit = false;
          char one[160];
          int wr =
              snprintf(one, sizeof(one), "{\"ssid\":\"%s\",\"rssi_dbm\":%d,\"auth\":\"%s\",\"hidden\":%s}", ssid_esc,
                       scan_[start + i].rssi, scan_[start + i].auth, scan_[start + i].hidden ? "true" : "false");
          if (wr < 0 || static_cast<size_t>(wr) >= sizeof(one) || strlen(items) + strlen(one) + 2 >= sizeof(items))
            fit = false;
          else {
            if (i)
              strcat(items, ",");
            strcat(items, one);
          }
        }
        if (!fit)
          wrote = fail(out, cap, "PAYLOAD_TOO_LARGE", "scan page", nullptr, nullptr);
        else {
          const bool more = start + 2 < scan_n_;
          char next[16];
          if (more)
            snprintf(next, sizeof(next), "\"%d\"", start + 2);
          wrote = snprintf(out, cap, "{\"ok\":true,\"result\":{\"items\":[%s],\"next_cursor\":%s,\"truncated\":%s}}",
                           items, more ? next : "null", scan_truncated_ ? "true" : "false");
        }
      }
    }
  } else {
    invalid_requests_++;
    wrote = fail(out, cap, "UNSUPPORTED", "Unsupported", nullptr, nullptr);
  }
  if (wrote < 0 || static_cast<size_t>(wrote) >= cap)
    return false;
  if (code != 0x0001 && code != 0x0003 && session_live_) {
    if (request > seen_max_)
      seen_max_ = request;
    if (static_cast<size_t>(wrote) < sizeof(replay_[0].body)) {
      Replay &r = replay_[replay_next_++ % kReplay];
      memset(&r, 0, sizeof(r));
      r.used = true;
      r.request_id = request;
      r.code = code;
      memcpy(r.sha, dig, 32);
      r.len = static_cast<uint16_t>(wrote);
      memcpy(r.body, out, static_cast<size_t>(wrote) + 1);
    }
  }
  return true;
}

bool Service::apply_changes(const uint8_t *payload, size_t len, char *, size_t, const char **field, const char **code,
                            bool publish) {
  const char *json = reinterpret_cast<const char *>(payload);
  static const char *keys[] = {"install.x_cm",         "install.y_cm",      "install.z_cm",
                               "install.yaw_deg",      "install.pitch_deg", "install.roll_deg",
                               "geometry.boundary_cm", "areas.definitions", nullptr};
  Allow allow{keys, false, {0}};
  if (!walk_object(json, len, allow_cb, &allow) || allow.bad) {
    static char field_buf[64];
    strncpy(field_buf, allow.field, sizeof(field_buf) - 1);
    *field = field_buf;
    *code = allow.bad ? "UNSUPPORTED" : "INVALID_ARGUMENT";
    return false;
  }
  const char *vs = nullptr;
  size_t vn = 0;
  double num = 0;
  if (find_key(json, len, "install.z_cm", &vs, &vn)) {
    if (!parse_num(vs, vn, &num) || num < 50 || num > 600 || !on_step(num, 50, 1)) {
      *field = "install.z_cm";
      *code = (num < 50 || num > 600) ? "OUT_OF_RANGE" : "INVALID_ARGUMENT";
      return false;
    }
    if (publish)
      z_cm_ = static_cast<int32_t>(num);
  }
  if (find_key(json, len, "install.yaw_deg", &vs, &vn)) {
    if (!parse_num(vs, vn, &num) || num < -180 || num > 180 || !on_step(num, -180, 0.1)) {
      *field = "install.yaw_deg";
      *code = (num < -180 || num > 180) ? "OUT_OF_RANGE" : "INVALID_ARGUMENT";
      return false;
    }
    if (publish)
      yaw_tenth_ = static_cast<int16_t>(num * 10.0 + (num >= 0 ? 0.5 : -0.5));
  }
  if (find_key(json, len, "install.pitch_deg", &vs, &vn)) {
    if (!parse_num(vs, vn, &num) || num < -90 || num > 90 || !on_step(num, -90, 0.5)) {
      *field = "install.pitch_deg";
      *code = "OUT_OF_RANGE";
      return false;
    }
    if (publish)
      pitch_half_ = static_cast<int16_t>(num * 2.0 + (num >= 0 ? 0.5 : -0.5));
  }
  if (find_key(json, len, "install.roll_deg", &vs, &vn)) {
    if (!parse_num(vs, vn, &num) || num < -90 || num > 90 || !on_step(num, -90, 0.5)) {
      *field = "install.roll_deg";
      *code = "OUT_OF_RANGE";
      return false;
    }
    if (publish)
      roll_half_ = static_cast<int16_t>(num * 2.0 + (num >= 0 ? 0.5 : -0.5));
  }
  if (find_key(json, len, "areas.definitions", &vs, &vn)) {
    if (vn < 2 || vs[0] != '[') {
      *field = "areas.definitions";
      *code = "INVALID_ARGUMENT";
      return false;
    }
    Area parsed[3];
    memset(parsed, 0, sizeof(parsed));
    int count = 0;
    const char *p = vs + 1;
    const char *end = vs + vn;
    p = skip_ws(p, end);
    if (p < end && *p != ']') {
      while (p < end && *p != ']') {
        const char *obj_s = nullptr;
        const char *obj_e = nullptr;
        if (!capture_value(&p, end, &obj_s, &obj_e) || obj_s[0] != '{') {
          *field = "areas.definitions";
          *code = "INVALID_ARGUMENT";
          return false;
        }
        if (count >= 3) {
          *field = "areas.definitions";
          *code = "INVALID_ARGUMENT";
          return false;
        }
        const char *sv = nullptr;
        size_t sn = 0;
        double slotv = -1;
        if (!find_key(obj_s, static_cast<size_t>(obj_e - obj_s), "slot", &sv, &sn) || !parse_num(sv, sn, &slotv) ||
            slotv < 0 || slotv > 2 || slotv != static_cast<int>(slotv)) {
          *field = "slot";
          *code = "INVALID_ARGUMENT";
          return false;
        }
        for (int i = 0; i < count; i++)
          if (parsed[i].slot == static_cast<uint8_t>(slotv)) {
            *field = "slot";
            *code = "INVALID_ARGUMENT";
            return false;
          }
        if (!find_key(obj_s, static_cast<size_t>(obj_e - obj_s), "enabled", &sv, &sn) ||
            !((sn == 4 && memcmp(sv, "true", 4) == 0) || (sn == 5 && memcmp(sv, "false", 5) == 0))) {
          *field = "enabled";
          *code = "INVALID_ARGUMENT";
          return false;
        }
        const bool enabled = sn == 4;
        char name[33];
        name[0] = 0;
        if (!find_key(obj_s, static_cast<size_t>(obj_e - obj_s), "name", &sv, &sn) ||
            !unquote(sv, sn, name, sizeof(name))) {
          *field = "name";
          *code = "INVALID_ARGUMENT";
          return false;
        }
        if (!find_key(obj_s, static_cast<size_t>(obj_e - obj_s), "points_cm", &sv, &sn) || sn < 2 || sv[0] != '[') {
          *field = "points_cm";
          *code = "INVALID_ARGUMENT";
          return false;
        }
        Point pts[12];
        int pn = 0;
        const char *pp = sv + 1;
        const char *pend = sv + sn;
        pp = skip_ws(pp, pend);
        if (!(pp < pend && *pp == ']')) {
          while (pp < pend && *pp != ']') {
            const char *ps = nullptr;
            const char *pe = nullptr;
            if (!capture_value(&pp, pend, &ps, &pe) || ps[0] != '[') {
              *field = "points_cm";
              *code = "INVALID_ARGUMENT";
              return false;
            }
            if (pn >= 12) {
              *field = "points_cm";
              *code = "INVALID_ARGUMENT";
              return false;
            }
            char *e1 = nullptr;
            double x = strtod(ps + 1, &e1);
            if (e1 == ps + 1)
              return false;
            const char *yp = skip_ws(e1, pe);
            if (*yp != ',')
              return false;
            char *e2 = nullptr;
            double y = strtod(yp + 1, &e2);
            if (x < -2000 || x > 2000 || y < -2000 || y > 2000) {
              *field = "points_cm";
              *code = "OUT_OF_RANGE";
              return false;
            }
            pts[pn].x = static_cast<int16_t>(x);
            pts[pn].y = static_cast<int16_t>(y);
            pn++;
            pp = skip_ws(pp, pend);
            if (pp < pend && *pp == ',')
              pp++;
          }
        }
        if (pn >= 3) {
          int64_t area = 0;
          for (int i = 0; i < pn; i++) {
            int j = (i + 1) % pn;
            area += static_cast<int64_t>(pts[i].x) * pts[j].y - static_cast<int64_t>(pts[j].x) * pts[i].y;
          }
          if (area == 0) {
            *field = "points_cm";
            *code = "INVALID_ARGUMENT";
            return false;
          }
          for (int i = 0; i < pn; i++) {
            for (int j = i + 1; j < pn; j++) {
              if (abs(i - j) <= 1 || (i == 0 && j == pn - 1))
                continue;
              if (segments_cross(pts[i].x, pts[i].y, pts[(i + 1) % pn].x, pts[(i + 1) % pn].y, pts[j].x, pts[j].y,
                                 pts[(j + 1) % pn].x, pts[(j + 1) % pn].y)) {
                *field = "points_cm";
                *code = "INVALID_ARGUMENT";
                return false;
              }
            }
            for (int j = 0; j < i; j++)
              if (pts[i].x == pts[j].x && pts[i].y == pts[j].y) {
                *field = "points_cm";
                *code = "INVALID_ARGUMENT";
                return false;
              }
          }
        }
        if (enabled && pn < 3) {
          *field = "points_cm";
          *code = "INVALID_ARGUMENT";
          return false;
        }
        if (!enabled && pn != 0 && pn < 3) {
          *field = "points_cm";
          *code = "INVALID_ARGUMENT";
          return false;
        }
        parsed[count].used = true;
        parsed[count].slot = static_cast<uint8_t>(slotv);
        parsed[count].enabled = enabled;
        strncpy(parsed[count].name, name, 32);
        parsed[count].n = static_cast<uint8_t>(pn);
        if (pn)
          memcpy(parsed[count].points, pts, sizeof(Point) * static_cast<size_t>(pn));
        count++;
        p = skip_ws(p, end);
        if (p < end && *p == ',')
          p++;
        p = skip_ws(p, end);
      }
    }
    if (publish)
      memcpy(areas_, parsed, sizeof(parsed));
  }
  if (find_key(json, len, "install.x_cm", &vs, &vn)) {
    if (!parse_num(vs, vn, &num) || num < -2000 || num > 2000 || !on_step(num, -2000, 1)) {
      *field = "install.x_cm";
      *code = "OUT_OF_RANGE";
      return false;
    }
    if (publish)
      x_cm_ = static_cast<int32_t>(num);
  }
  if (find_key(json, len, "install.y_cm", &vs, &vn)) {
    if (!parse_num(vs, vn, &num) || num < -2000 || num > 2000) {
      *field = "install.y_cm";
      *code = "OUT_OF_RANGE";
      return false;
    }
    if (publish)
      y_cm_ = static_cast<int32_t>(num);
  }
  if (find_key(json, len, "geometry.boundary_cm", &vs, &vn)) {
    if (vn == 4 && memcmp(vs, "null", 4) == 0) {
      if (publish) {
        boundary_set_ = false;
        boundary_n_ = 0;
      }
    } else if (vs[0] != '[') {
      *field = "geometry.boundary_cm";
      *code = "INVALID_ARGUMENT";
      return false;
    } else {
      Point pts[64];
      int n = 0;
      const char *p = vs + 1;
      const char *end = vs + vn;
      while (p < end && *p != ']') {
        p = skip_ws(p, end);
        if (*p == ']')
          break;
        if (*p != '[') {
          *field = "geometry.boundary_cm";
          *code = "INVALID_ARGUMENT";
          return false;
        }
        p++;
        char *e1 = nullptr;
        double x = strtod(p, &e1);
        if (e1 == p)
          return false;
        p = skip_ws(e1, end);
        if (*p != ',')
          return false;
        p++;
        char *e2 = nullptr;
        double y = strtod(p, &e2);
        p = skip_ws(e2, end);
        if (*p != ']')
          return false;
        p++;
        if (x < -2000 || x > 2000 || y < -2000 || y > 2000) {
          *field = "geometry.boundary_cm";
          *code = "OUT_OF_RANGE";
          return false;
        }
        if (n >= 64) {
          *field = "geometry.boundary_cm";
          *code = "INVALID_ARGUMENT";
          return false;
        }
        pts[n].x = static_cast<int16_t>(x);
        pts[n].y = static_cast<int16_t>(y);
        n++;
        p = skip_ws(p, end);
        if (*p == ',')
          p++;
      }
      if (n < 3) {
        *field = "geometry.boundary_cm";
        *code = "INVALID_ARGUMENT";
        return false;
      }
      for (int i = 0; i < n; i++)
        for (int j = 0; j < i; j++)
          if (pts[i].x == pts[j].x && pts[i].y == pts[j].y) {
            *field = "geometry.boundary_cm";
            *code = "INVALID_ARGUMENT";
            return false;
          }
      if (pts[0].x == pts[n - 1].x && pts[0].y == pts[n - 1].y) {
        *field = "geometry.boundary_cm";
        *code = "INVALID_ARGUMENT";
        return false;
      }
      int64_t area = 0;
      for (int i = 0; i < n; i++) {
        int j = (i + 1) % n;
        area += static_cast<int64_t>(pts[i].x) * pts[j].y - static_cast<int64_t>(pts[j].x) * pts[i].y;
      }
      if (area == 0) {
        *field = "geometry.boundary_cm";
        *code = "INVALID_ARGUMENT";
        return false;
      }
      for (int i = 0; i < n; i++)
        for (int j = i + 1; j < n; j++) {
          if (abs(i - j) <= 1 || (i == 0 && j == n - 1))
            continue;
          int i2 = (i + 1) % n;
          int j2 = (j + 1) % n;
          if (segments_cross(pts[i].x, pts[i].y, pts[i2].x, pts[i2].y, pts[j].x, pts[j].y, pts[j2].x, pts[j2].y)) {
            *field = "geometry.boundary_cm";
            *code = "INVALID_ARGUMENT";
            return false;
          }
        }
      if (publish) {
        boundary_set_ = true;
        boundary_n_ = static_cast<uint8_t>(n);
        memcpy(boundary_, pts, sizeof(Point) * static_cast<size_t>(n));
      }
    }
  }
  (void) code;
  return true;
}

}  // namespace mwcp_host
