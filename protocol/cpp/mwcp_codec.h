#pragma once

#include <stddef.h>
#include <stdint.h>

namespace mwcp {

enum Status {
  kOk = 0,
  kBadCobs = 1,
  kOversize = 2,
  kBadHeader = 3,
  kBadCrc = 4,
  kBadUtf8 = 5,
  kBadJson = 6,
  kBadLength = 7,
  kBufferTooSmall = 8,
  kTimeout = 9,
  kPayloadTooLarge = 10
};

static const size_t kHeaderLen = 24;
static const size_t kMaxPayload = 4096;
static const size_t kMaxDecoded = 4124;
static const size_t kMaxCobs = 4141;
static const size_t kMaxWire = 4143;
static const uint32_t kHalfFrameMs = 2000;
static const uint8_t kMajor = 1;
static const uint8_t kMinor = 0;

struct Frame {
  uint8_t kind;
  uint32_t session_id;
  uint32_t request_id;
  uint16_t code;
  uint16_t payload_length;
  uint32_t wire_seq;
  const uint8_t *payload;
};

struct EncodeInput {
  uint8_t kind;
  uint32_t session_id;
  uint32_t request_id;
  uint16_t code;
  uint32_t wire_seq;
  const uint8_t *payload;
  size_t payload_len;
  bool check_json;
};

struct ParserStats {
  uint32_t frames;
  uint32_t bad_cobs;
  uint32_t bad_crc;
  uint32_t bad_header;
  uint32_t bad_utf8;
  uint32_t bad_json;
  uint32_t oversize;
  uint32_t timeouts;
};

typedef void (*FrameHandler)(const Frame &frame, void *user);
typedef void (*ErrorHandler)(Status status, void *user);

uint32_t crc32c(const uint8_t *data, size_t len);
Status cobs_encode(const uint8_t *in, size_t in_len, uint8_t *out, size_t out_cap, size_t *out_len);
Status cobs_decode(const uint8_t *in, size_t in_len, uint8_t *out, size_t out_cap, size_t *out_len);
Status encode_frame(const EncodeInput &in, uint8_t *wire, size_t wire_cap, size_t *wire_len, uint8_t *decoded, size_t decoded_cap, size_t *decoded_len);
Status decode_frame(const uint8_t *decoded, size_t decoded_len, Frame *frame, bool check_json);
const char *json_error();

class Parser {
 public:
  Parser();
  void push(const uint8_t *data, size_t len, uint32_t now_ms, FrameHandler on_frame, ErrorHandler on_error, void *user);
  void poll(uint32_t now_ms, ErrorHandler on_error, void *user);
  const ParserStats &stats() const { return stats_; }

 private:
  void finish(FrameHandler on_frame, ErrorHandler on_error, void *user);
  void fail(Status status, ErrorHandler on_error, void *user);

  uint8_t buf_[kMaxCobs];
  size_t len_;
  bool discarding_;
  bool have_time_;
  uint32_t last_ms_;
  uint8_t decoded_[kMaxDecoded];
  ParserStats stats_;
};

}  // namespace mwcp
