#include "mwcp_codec.h"

#include "mwcp_json.h"

namespace mwcp {
namespace {

uint32_t table[256];
bool table_ready = false;

void init_table() {
  if (table_ready) return;
  for (uint32_t n = 0; n < 256; n++) {
    uint32_t crc = n;
    for (int i = 0; i < 8; i++) crc = (crc >> 1) ^ (0x82f63b78u & (0u - (crc & 1u)));
    table[n] = crc;
  }
  table_ready = true;
}

void write_u16(uint8_t *buf, size_t offset, uint16_t value) {
  buf[offset] = static_cast<uint8_t>(value & 0xff);
  buf[offset + 1] = static_cast<uint8_t>((value >> 8) & 0xff);
}

void write_u32(uint8_t *buf, size_t offset, uint32_t value) {
  buf[offset] = static_cast<uint8_t>(value & 0xff);
  buf[offset + 1] = static_cast<uint8_t>((value >> 8) & 0xff);
  buf[offset + 2] = static_cast<uint8_t>((value >> 16) & 0xff);
  buf[offset + 3] = static_cast<uint8_t>((value >> 24) & 0xff);
}

uint16_t read_u16(const uint8_t *buf, size_t offset) {
  return static_cast<uint16_t>(buf[offset] | (buf[offset + 1] << 8));
}

uint32_t read_u32(const uint8_t *buf, size_t offset) {
  return static_cast<uint32_t>(buf[offset] | (buf[offset + 1] << 8) | (buf[offset + 2] << 16) | (buf[offset + 3] << 24));
}

}  // namespace

uint32_t crc32c(const uint8_t *data, size_t len) {
  init_table();
  uint32_t crc = 0xffffffffu;
  for (size_t i = 0; i < len; i++) crc = table[(crc ^ data[i]) & 0xff] ^ (crc >> 8);
  return crc ^ 0xffffffffu;
}

Status cobs_encode(const uint8_t *in, size_t in_len, uint8_t *out, size_t out_cap, size_t *out_len) {
  if (out_cap < in_len + in_len / 254 + 1) return kBufferTooSmall;
  size_t n = 1;
  size_t code_index = 0;
  uint8_t code = 1;
  for (size_t i = 0; i < in_len; i++) {
    if (in[i] == 0) {
      out[code_index] = code;
      code_index = n;
      out[n++] = 0;
      code = 1;
    } else {
      out[n++] = in[i];
      code++;
      if (code == 0xff) {
        out[code_index] = code;
        code_index = n;
        out[n++] = 0;
        code = 1;
      }
    }
  }
  out[code_index] = code;
  *out_len = n;
  return kOk;
}

Status cobs_decode(const uint8_t *in, size_t in_len, uint8_t *out, size_t out_cap, size_t *out_len) {
  if (in_len == 0) return kBadCobs;
  size_t n = 0;
  size_t i = 0;
  while (i < in_len) {
    const uint8_t code = in[i];
    if (code == 0) return kBadCobs;
    i++;
    const size_t end = i + code - 1;
    if (end > in_len) return kBadCobs;
    while (i < end) {
      if (in[i] == 0) return kBadCobs;
      if (n >= out_cap) return kBufferTooSmall;
      out[n++] = in[i++];
    }
    if (code != 0xff) {
      if (n >= out_cap) return kBufferTooSmall;
      out[n++] = 0;
    }
  }
  if (n == 0 || out[n - 1] != 0) return kBadCobs;
  *out_len = n - 1;
  return kOk;
}

Status encode_frame(const EncodeInput &in, uint8_t *wire, size_t wire_cap, size_t *wire_len, uint8_t *decoded, size_t decoded_cap, size_t *decoded_len) {
  if (in.payload_len > kMaxPayload) return kPayloadTooLarge;
  if (in.check_json && !json_check(in.payload, in.payload_len)) return kBadJson;
  const size_t raw_len = kHeaderLen + in.payload_len + 4;
  if (decoded_cap < raw_len) return kBufferTooSmall;
  decoded[0] = 'M';
  decoded[1] = 'W';
  decoded[2] = 'C';
  decoded[3] = 'P';
  decoded[4] = kMajor;
  decoded[5] = kMinor;
  decoded[6] = in.kind;
  decoded[7] = 0;
  write_u32(decoded, 8, in.session_id);
  write_u32(decoded, 12, in.request_id);
  write_u16(decoded, 16, in.code);
  write_u16(decoded, 18, static_cast<uint16_t>(in.payload_len));
  write_u32(decoded, 20, in.wire_seq);
  for (size_t i = 0; i < in.payload_len; i++) decoded[kHeaderLen + i] = in.payload[i];
  write_u32(decoded, kHeaderLen + in.payload_len, crc32c(decoded, kHeaderLen + in.payload_len));
  if (wire_cap < 2) return kBufferTooSmall;
  size_t encoded_len = 0;
  const Status cobs = cobs_encode(decoded, raw_len, wire + 1, wire_cap - 2, &encoded_len);
  if (cobs != kOk) return cobs;
  if (encoded_len > kMaxCobs) return kOversize;
  wire[0] = 0;
  wire[encoded_len + 1] = 0;
  *wire_len = encoded_len + 2;
  *decoded_len = raw_len;
  return kOk;
}

Status decode_frame(const uint8_t *decoded, size_t decoded_len, Frame *frame, bool check_json) {
  if (decoded_len < kHeaderLen + 4 || decoded_len > kMaxDecoded) return kBadLength;
  if (decoded[0] != 'M' || decoded[1] != 'W' || decoded[2] != 'C' || decoded[3] != 'P') return kBadHeader;
  if (decoded[4] != kMajor || decoded[5] != kMinor || decoded[7] != 0) return kBadHeader;
  if (decoded[6] != 1 && decoded[6] != 2 && decoded[6] != 3) return kBadHeader;
  const uint16_t payload_len = read_u16(decoded, 18);
  if (payload_len > kMaxPayload) return kPayloadTooLarge;
  if (decoded_len != kHeaderLen + payload_len + 4) return kBadLength;
  if (crc32c(decoded, kHeaderLen + payload_len) != read_u32(decoded, kHeaderLen + payload_len)) return kBadCrc;
  if (!utf8_check(decoded + kHeaderLen, payload_len)) return kBadUtf8;
  if (check_json && !json_check(decoded + kHeaderLen, payload_len)) return kBadJson;
  frame->kind = decoded[6];
  frame->session_id = read_u32(decoded, 8);
  frame->request_id = read_u32(decoded, 12);
  frame->code = read_u16(decoded, 16);
  frame->payload_length = payload_len;
  frame->wire_seq = read_u32(decoded, 20);
  frame->payload = decoded + kHeaderLen;
  return kOk;
}

const char *json_error() { return json_error_code(); }

Parser::Parser() : len_(0), discarding_(false), have_time_(false), last_ms_(0), stats_() {}

void Parser::push(const uint8_t *data, size_t len, uint32_t now_ms, FrameHandler on_frame, ErrorHandler on_error, void *user) {
  for (size_t i = 0; i < len; i++) {
    const uint8_t byte = data[i];
    last_ms_ = now_ms;
    have_time_ = true;
    if (byte == 0) {
      if (discarding_) {
        discarding_ = false;
        len_ = 0;
        continue;
      }
      if (len_ == 0) continue;
      finish(on_frame, on_error, user);
      continue;
    }
    if (discarding_) continue;
    if (len_ >= kMaxCobs) {
      discarding_ = true;
      len_ = 0;
      fail(kOversize, on_error, user);
      continue;
    }
    buf_[len_++] = byte;
  }
}

void Parser::poll(uint32_t now_ms, ErrorHandler on_error, void *user) {
  if (!discarding_ && len_ > 0 && have_time_ && now_ms - last_ms_ >= kHalfFrameMs) {
    discarding_ = true;
    len_ = 0;
    fail(kTimeout, on_error, user);
  }
}

void Parser::finish(FrameHandler on_frame, ErrorHandler on_error, void *user) {
  size_t decoded_len = 0;
  const Status decoded_status = cobs_decode(buf_, len_, decoded_, sizeof(decoded_), &decoded_len);
  len_ = 0;
  if (decoded_status != kOk) {
    fail(kBadCobs, on_error, user);
    return;
  }
  Frame frame;
  const Status status = decode_frame(decoded_, decoded_len, &frame, true);
  if (status != kOk) {
    fail(status, on_error, user);
    return;
  }
  stats_.frames++;
  if (on_frame) on_frame(frame, user);
}

void Parser::fail(Status status, ErrorHandler on_error, void *user) {
  if (status == kBadCobs) stats_.bad_cobs++;
  else if (status == kBadCrc) stats_.bad_crc++;
  else if (status == kBadUtf8) stats_.bad_utf8++;
  else if (status == kBadJson) stats_.bad_json++;
  else if (status == kOversize || status == kPayloadTooLarge || status == kBadLength) stats_.oversize++;
  else if (status == kTimeout) stats_.timeouts++;
  else stats_.bad_header++;
  if (on_error) on_error(status, user);
}

}  // namespace mwcp
