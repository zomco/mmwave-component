#include "mwcp_json.h"

#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>

namespace mwcp {
namespace {

const char *g_error = "";
int utf8_seq(const uint8_t *data, size_t len, size_t i);
size_t encode_utf8(unsigned cp, uint8_t out[4]);

void set_error(const char *error) { g_error = error; }

bool is_ws(uint8_t b) { return b == ' ' || b == '\t' || b == '\n' || b == '\r'; }

class Parser {
 public:
  Parser(const uint8_t *data, size_t len) : data_(data), len_(len), i_(0), span_count_(0) {}

  bool value(int depth) {
    skip();
    if (depth > 8) return fail("depth");
    if (ended()) return fail("truncated");
    const uint8_t b = at(i_);
    if (b == '{') return object(depth);
    if (b == '[') return array(depth);
    if (b == '"') return string(0, 0);
    if (b == 't') return literal("true");
    if (b == 'f') return literal("false");
    if (b == 'n') return literal("null");
    if (b == '-' || (b >= '0' && b <= '9')) return number();
    return fail("syntax");
  }

  void skip() {
    while (i_ < len_ && is_ws(at(i_))) i_++;
  }

  size_t index() const { return i_; }

 private:
  bool ended() const { return i_ >= len_; }

  uint8_t at(size_t index) const { return data_[index]; }

  bool fail(const char *error) {
    set_error(error);
    return false;
  }

  bool literal(const char *text) {
    for (size_t n = 0; text[n] != 0; n++) {
      if (i_ + n >= len_ || at(i_ + n) != static_cast<uint8_t>(text[n])) return fail("syntax");
    }
    while (*text) {
      i_++;
      text++;
    }
    return true;
  }

  bool number() {
    const size_t start = i_;
    if (ended()) return fail("truncated");
    if (at(i_) == '-') {
      i_++;
      if (ended()) return fail("truncated");
    }
    if (at(i_) < '0' || at(i_) > '9') return fail("number");
    if (at(i_) == '0') i_++;
    else while (i_ < len_ && at(i_) >= '0' && at(i_) <= '9') i_++;
    if (i_ < len_ && at(i_) == '.') {
      i_++;
      if (ended() || at(i_) < '0' || at(i_) > '9') return fail("number");
      while (i_ < len_ && at(i_) >= '0' && at(i_) <= '9') i_++;
    }
    if (i_ < len_ && (at(i_) == 'e' || at(i_) == 'E')) {
      i_++;
      if (ended()) return fail("truncated");
      if (at(i_) == '+' || at(i_) == '-') {
        i_++;
        if (ended()) return fail("truncated");
      }
      if (at(i_) < '0' || at(i_) > '9') return fail("number");
      while (i_ < len_ && at(i_) >= '0' && at(i_) <= '9') i_++;
    }
    return classify_number(start, i_);
  }

  uint8_t span_digit(size_t int_begin, size_t int_len, size_t frac_begin, size_t pos) const {
    if (pos < int_len) return at(int_begin + pos);
    return at(frac_begin + (pos - int_len));
  }

  bool span_zero(size_t int_begin, size_t int_len, size_t frac_begin, size_t begin, size_t end) const {
    for (size_t pos = begin; pos < end; pos++) {
      if (span_digit(int_begin, int_len, frac_begin, pos) != '0') return false;
    }
    return true;
  }

  bool integer_span(size_t int_begin, size_t int_len, size_t frac_begin, size_t begin, size_t end, long long extra_zeros) {
    while (begin + 1 < end && span_digit(int_begin, int_len, frac_begin, begin) == '0') begin++;
    if (begin >= end || span_digit(int_begin, int_len, frac_begin, begin) == '0') return true;
    const size_t significant = end - begin;
    if (extra_zeros < 0) extra_zeros = 0;
    if (significant > 16 || extra_zeros > 16 || significant + static_cast<size_t>(extra_zeros) > 16) return fail("unsafe_integer");
    if (significant + static_cast<size_t>(extra_zeros) < 16) return true;
    const char *limit = "9007199254740991";
    for (size_t n = 0; n < 16; n++) {
      const char ch = n < significant ? static_cast<char>(span_digit(int_begin, int_len, frac_begin, begin + n)) : '0';
      if (ch == limit[n]) continue;
      return ch > limit[n] ? fail("unsafe_integer") : true;
    }
    return true;
  }

  bool overflows_binary64(size_t int_begin, size_t int_len, size_t frac_begin, size_t total, long long place) const {
    if (place > 308) return true;
    if (place < 308) return false;
    const char *threshold = json_overflow_threshold();
    size_t pos = 0;
    while (pos < total && span_digit(int_begin, int_len, frac_begin, pos) == '0') pos++;
    for (size_t i = 0; threshold[i] != 0; i++) {
      const char ours = pos < total ? static_cast<char>(span_digit(int_begin, int_len, frac_begin, pos++)) : '0';
      if (ours == threshold[i]) continue;
      return ours > threshold[i];
    }
    return true;
  }

  bool finite_fraction(size_t int_begin, size_t int_len, size_t frac_begin, size_t total, long long exp) {
    size_t first = 0;
    while (first < total && span_digit(int_begin, int_len, frac_begin, first) == '0') first++;
    if (first >= total) return true;
    const long long place = first < int_len
        ? static_cast<long long>(int_len - 1 - first) + exp
        : -static_cast<long long>(first - int_len + 1) + exp;
    if (place < -400) return true;
    if (overflows_binary64(int_begin, int_len, frac_begin, total, place)) return fail("number");
    return true;
  }

  bool classify_number(size_t start, size_t end) {
    size_t i = start;
    if (at(i) == '-') i++;
    const size_t int_begin = i;
    while (i < end && at(i) >= '0' && at(i) <= '9') i++;
    const size_t int_end = i;
    size_t frac_begin = i;
    size_t frac_end = i;
    if (i < end && at(i) == '.') {
      i++;
      frac_begin = i;
      while (i < end && at(i) >= '0' && at(i) <= '9') i++;
      frac_end = i;
    }
    long long exp = 0;
    int exp_sign = 1;
    bool exp_big = false;
    if (i < end && (at(i) == 'e' || at(i) == 'E')) {
      i++;
      if (i < end && at(i) == '+') i++;
      else if (i < end && at(i) == '-') {
        exp_sign = -1;
        i++;
      }
      while (i < end && at(i) >= '0' && at(i) <= '9') {
        const int digit = at(i) - '0';
        i++;
        if (exp_big) continue;
        if (exp > 1000000) {
          exp_big = true;
          continue;
        }
        exp = exp * 10 + digit;
      }
    }
    if (exp_big) exp = 1000000;
    exp *= exp_sign;
    const size_t int_len = int_end - int_begin;
    const size_t frac_len = frac_end - frac_begin;
    const size_t total = int_len + frac_len;
    if (total == 0) return fail("number");
    const long long right = static_cast<long long>(frac_len) - exp;
    if (right <= 0) return integer_span(int_begin, int_len, frac_begin, 0, total, -right);
    if (right < static_cast<long long>(total)) {
      const size_t split = total - static_cast<size_t>(right);
      if (span_zero(int_begin, int_len, frac_begin, split, total)) return integer_span(int_begin, int_len, frac_begin, 0, split, 0);
    } else if (span_zero(int_begin, int_len, frac_begin, 0, total)) {
      return true;
    }
    return finite_fraction(int_begin, int_len, frac_begin, total, exp);
  }

  bool string(uint8_t *decoded, size_t *decoded_len) {
    if (ended() || at(i_) != '"') return fail(ended() ? "truncated" : "string");
    i_++;
    size_t bytes = 0;
    size_t out_n = 0;
    while (i_ < len_) {
      const uint8_t b = at(i_);
      if (b == '"') {
        i_++;
        if (bytes > 4096) return fail("string_limit");
        if (decoded_len) *decoded_len = out_n;
        return true;
      }
      if (b == '\\') {
        if (i_ + 1 >= len_) return fail("truncated");
        const uint8_t esc = at(i_ + 1);
        uint8_t produced[4];
        size_t produced_n = 0;
        if (esc == '"' || esc == '\\' || esc == '/') {
          produced[0] = esc;
          produced_n = 1;
          i_ += 2;
        } else if (esc == 'b' || esc == 'f' || esc == 'n' || esc == 'r' || esc == 't') {
          const uint8_t map = esc == 'b' ? 8 : esc == 'f' ? 12 : esc == 'n' ? 10 : esc == 'r' ? 13 : 9;
          produced[0] = map;
          produced_n = 1;
          i_ += 2;
        } else if (esc == 'u') {
          if (i_ + 5 >= len_) return fail("truncated");
          unsigned unit = 0;
          if (!hex4(i_ + 2, &unit)) return fail("string");
          i_ += 6;
          if (unit >= 0xD800 && unit <= 0xDBFF) {
            if (i_ + 5 >= len_) return fail("truncated");
            if (at(i_) != '\\' || at(i_ + 1) != 'u') return fail("surrogate");
            unsigned low = 0;
            if (!hex4(i_ + 2, &low) || low < 0xDC00 || low > 0xDFFF) return fail("surrogate");
            unit = 0x10000u + ((unit - 0xD800u) << 10) + (low - 0xDC00u);
            i_ += 6;
          } else if (unit >= 0xDC00 && unit <= 0xDFFF) return fail("surrogate");
          produced_n = encode_utf8(unit, produced);
        } else return fail("string");
        bytes += produced_n;
        if (decoded) {
          if (out_n + produced_n > 192) return fail("string_limit");
          for (size_t n = 0; n < produced_n; n++) decoded[out_n++] = produced[n];
        }
        continue;
      }
      if (b < 0x20) return fail("string");
      const int seq = utf8_seq(data_, len_, i_);
      if (seq <= 0) return fail("utf8");
      if (decoded) {
        if (out_n + static_cast<size_t>(seq) > 192) return fail("string_limit");
        for (int n = 0; n < seq; n++) decoded[out_n++] = at(i_ + static_cast<size_t>(n));
      }
      bytes += static_cast<size_t>(seq);
      i_ += static_cast<size_t>(seq);
    }
    return fail("truncated");
  }

  bool hex4(size_t at_index, unsigned *out) const {
    if (at_index + 3 >= len_) return false;
    unsigned value = 0;
    for (size_t n = 0; n < 4; n++) {
      const uint8_t c = at(at_index + n);
      value <<= 4;
      if (c >= '0' && c <= '9') value += c - '0';
      else if (c >= 'a' && c <= 'f') value += c - 'a' + 10;
      else if (c >= 'A' && c <= 'F') value += c - 'A' + 10;
      else return false;
    }
    *out = value;
    return true;
  }

  bool object(int depth) {
    const int saved = span_count_;
    const bool ok = parse_object(depth);
    span_count_ = saved;
    return ok;
  }

  bool parse_object(int depth) {
    if (ended() || at(i_) != '{') return fail("syntax");
    i_++;
    const int base = span_count_;
    skip();
    if (ended()) return fail("truncated");
    if (at(i_) == '}') {
      i_++;
      return true;
    }
    while (true) {
      if (span_count_ - base >= 64) return fail("keys");
      skip();
      if (ended()) return fail("truncated");
      const size_t content_begin = i_ + 1;
      if (!string(0, 0)) return false;
      const size_t content_end = i_ - 1;
      for (int k = base; k < span_count_; k++) {
        if (same_decoded_key(spans_[k].begin, spans_[k].end, content_begin, content_end)) return fail("duplicate_key");
      }
      if (span_count_ >= kMaxSpans) return fail("keys");
      spans_[span_count_].begin = static_cast<uint16_t>(content_begin);
      spans_[span_count_].end = static_cast<uint16_t>(content_end);
      span_count_++;
      skip();
      if (ended()) return fail("truncated");
      if (at(i_) != ':') return fail("syntax");
      i_++;
      if (!value(depth + 1)) return false;
      skip();
      if (ended()) return fail("truncated");
      if (at(i_) == '}') {
        i_++;
        return true;
      }
      if (at(i_) != ',') return fail("syntax");
      i_++;
    }
  }

  bool array(int depth) {
    if (ended() || at(i_) != '[') return fail("syntax");
    i_++;
    int count = 0;
    skip();
    if (ended()) return fail("truncated");
    if (at(i_) == ']') {
      i_++;
      return true;
    }
    while (true) {
      if (count >= 256) return fail("items");
      if (!value(depth + 1)) return false;
      count++;
      skip();
      if (ended()) return fail("truncated");
      if (at(i_) == ']') {
        i_++;
        return true;
      }
      if (at(i_) != ',') return fail("syntax");
      i_++;
    }
  }

  struct DecodeCursor {
    size_t i;
    uint8_t extra[3];
    uint8_t extra_n;
    uint8_t extra_i;
  };

  bool same_decoded_key(size_t a0, size_t a1, size_t b0, size_t b1) const {
    DecodeCursor left = {a0, {0, 0, 0}, 0, 0};
    DecodeCursor right = {b0, {0, 0, 0}, 0, 0};
    for (;;) {
      int ca = 0;
      int cb = 0;
      if (!pull_decoded(left, a1, &ca) || !pull_decoded(right, b1, &cb)) return false;
      if (ca != cb) return false;
      if (ca < 0) return true;
    }
  }

  bool pull_decoded(DecodeCursor &cursor, size_t end, int *out) const {
    if (cursor.extra_i < cursor.extra_n) {
      *out = cursor.extra[cursor.extra_i++];
      return true;
    }
    cursor.extra_i = 0;
    cursor.extra_n = 0;
    if (cursor.i >= end) {
      *out = -1;
      return true;
    }
    const uint8_t b = at(cursor.i);
    if (b != '\\') {
      const int seq = utf8_seq(data_, end, cursor.i);
      if (seq <= 0 || cursor.i + static_cast<size_t>(seq) > end) return false;
      *out = at(cursor.i);
      for (int n = 1; n < seq; n++) cursor.extra[cursor.extra_n++] = at(cursor.i + static_cast<size_t>(n));
      cursor.i += static_cast<size_t>(seq);
      return true;
    }
    if (cursor.i + 1 >= end) return false;
    const uint8_t esc = at(cursor.i + 1);
    if (esc == '"' || esc == '\\' || esc == '/') {
      *out = esc;
      cursor.i += 2;
      return true;
    }
    if (esc == 'b' || esc == 'f' || esc == 'n' || esc == 'r' || esc == 't') {
      *out = esc == 'b' ? 8 : esc == 'f' ? 12 : esc == 'n' ? 10 : esc == 'r' ? 13 : 9;
      cursor.i += 2;
      return true;
    }
    if (esc != 'u' || cursor.i + 5 >= end) return false;
    unsigned unit = 0;
    if (!hex4(cursor.i + 2, &unit)) return false;
    cursor.i += 6;
    if (unit >= 0xD800 && unit <= 0xDBFF) {
      if (cursor.i + 5 >= end || at(cursor.i) != '\\' || at(cursor.i + 1) != 'u') return false;
      unsigned low = 0;
      if (!hex4(cursor.i + 2, &low) || low < 0xDC00 || low > 0xDFFF) return false;
      unit = 0x10000u + ((unit - 0xD800u) << 10) + (low - 0xDC00u);
      cursor.i += 6;
    } else if (unit >= 0xDC00 && unit <= 0xDFFF) return false;
    uint8_t utf8[4];
    const size_t n = encode_utf8(unit, utf8);
    *out = utf8[0];
    for (size_t nbyte = 1; nbyte < n; nbyte++) cursor.extra[cursor.extra_n++] = utf8[nbyte];
    return true;
  }

  const uint8_t *data_;
  size_t len_;
  size_t i_;
  struct KeySpan {
    uint16_t begin;
    uint16_t end;
  };
  static const int kMaxSpans = 64 * 8;
  KeySpan spans_[kMaxSpans];
  int span_count_;
};

size_t encode_utf8(unsigned cp, uint8_t out[4]) {
  if (cp < 0x80) {
    out[0] = static_cast<uint8_t>(cp);
    return 1;
  }
  if (cp < 0x800) {
    out[0] = static_cast<uint8_t>(0xc0 | (cp >> 6));
    out[1] = static_cast<uint8_t>(0x80 | (cp & 0x3f));
    return 2;
  }
  if (cp < 0x10000) {
    out[0] = static_cast<uint8_t>(0xe0 | (cp >> 12));
    out[1] = static_cast<uint8_t>(0x80 | ((cp >> 6) & 0x3f));
    out[2] = static_cast<uint8_t>(0x80 | (cp & 0x3f));
    return 3;
  }
  out[0] = static_cast<uint8_t>(0xf0 | (cp >> 18));
  out[1] = static_cast<uint8_t>(0x80 | ((cp >> 12) & 0x3f));
  out[2] = static_cast<uint8_t>(0x80 | ((cp >> 6) & 0x3f));
  out[3] = static_cast<uint8_t>(0x80 | (cp & 0x3f));
  return 4;
}

int utf8_seq(const uint8_t *data, size_t len, size_t i) {
  if (i >= len) return 0;
  const uint8_t b = data[i];
  if (b <= 0x7f) return 1;
  if (b >= 0xc2 && b <= 0xdf && i + 1 < len && (data[i + 1] & 0xc0) == 0x80) return 2;
  if ((b & 0xf0) == 0xe0 && i + 2 < len) {
    const uint8_t c1 = data[i + 1];
    if ((c1 & 0xc0) != 0x80 || (data[i + 2] & 0xc0) != 0x80) return 0;
    if (b == 0xe0 && c1 < 0xa0) return 0;
    if (b == 0xed && c1 >= 0xa0) return 0;
    return 3;
  }
  if (b >= 0xf0 && b <= 0xf4 && i + 3 < len) {
    const uint8_t c1 = data[i + 1];
    if ((c1 & 0xc0) != 0x80 || (data[i + 2] & 0xc0) != 0x80 || (data[i + 3] & 0xc0) != 0x80) return 0;
    if (b == 0xf0 && c1 < 0x90) return 0;
    if (b == 0xf4 && c1 >= 0x90) return 0;
    return 4;
  }
  return 0;
}

}  // namespace

const char *json_error_code() { return g_error; }

const char *json_overflow_threshold() {
  return "179769313486231580793728971405303415079934132710037826936173778980444968292764750946649017977587207096330286416692887910946555547851940402630657488671505820681908902000708383676273854845817711531764475730270069855571366959622842914819860834936475292719074168444365510704342711559699508093042880177904174497792";
}

bool utf8_check(const uint8_t *data, size_t len) {
  size_t i = 0;
  while (i < len) {
    const int seq = utf8_seq(data, len, i);
    if (seq <= 0) return false;
    i += static_cast<size_t>(seq);
  }
  return true;
}

bool json_check(const uint8_t *data, size_t len) {
  g_error = "";
  if (len >= 3 && data && data[0] == 0xef && data[1] == 0xbb && data[2] == 0xbf) {
    set_error("bom");
    return false;
  }
  Parser parser(data, len);
  if (!parser.value(1)) return false;
  parser.skip();
  if (parser.index() != len) {
    set_error("trailing");
    return false;
  }
  if (len == 0) {
    set_error("root");
    return false;
  }
  size_t i = 0;
  while (i < len && is_ws(data[i])) i++;
  if (i >= len || data[i] != '{') {
    set_error("root");
    return false;
  }
  return true;
}

}  // namespace mwcp
