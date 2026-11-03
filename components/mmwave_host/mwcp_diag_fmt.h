// mwcp_diag_fmt.h — R18-H18-01: bounded, fully-initialized formatter for the
// DIAGNOSTIC log-pressure message (heap stats piggyback).
//
// Contract:
//   - out is ALWAYS NUL-terminated within cap (cap > 0 required);
//   - fields are appended in order (seq, free, min_free, max_block) and a
//     field is only kept when its COMPLETE rendering fits — a truncated
//     number is never emitted (r17 finding: max_block=491 was a cut 49152);
//   - returns the count of complete fields (0..4);
//   - no dynamic allocation, no ESP dependencies — host-compilable.
//
// Worst-case full rendering (max 32-bit decimals, 10 digits each):
//   "pressure-seq=" (13) + 10 + " free=" (6) + 10 + " min_free=" (10) + 10
//   + " max_block=" (11) + 10 = 80 chars + NUL = 81 bytes.
// Callers should provide MWCP_DIAG_PRESSURE_MSG_LEN (96) or more.

#ifndef MWCP_DIAG_FMT_H
#define MWCP_DIAG_FMT_H

#include <cstdio>    // snprintf
#include <stddef.h>  // size_t

#define MWCP_DIAG_PRESSURE_MSG_LEN 96

namespace mwcp_diag {

// Worst-case full rendering length (without NUL): all four fields with the
// maximum 32-bit decimal widths. Compile-time check helper for callers.
constexpr size_t kMaxSeqDigits = 10;
constexpr size_t kMaxU32Digits = 10;
constexpr size_t worst_case_len = 13 /* "pressure-seq=" */ + kMaxSeqDigits + 6 /* " free=" */ + kMaxU32Digits +
                                  10 /* " min_free=" */ + kMaxU32Digits + 11 /* " max_block=" */ + kMaxU32Digits;

// Formats "pressure-seq=<seq> free=<free> min_free=<minf> max_block=<maxb>"
// into out (cap bytes).  Returns the number of complete fields (0..4).
// field 1 = seq, 2 = +free, 3 = +min_free, 4 = +max_block.
// out is always NUL-terminated when cap > 0; never emits a partial number.
inline int format_pressure(char *out, size_t cap, unsigned long seq, unsigned free_b, unsigned min_free_b,
                           unsigned max_block_b) {
  // H19-01 (r19): TRANSACTIONAL appends.  snprintf on truncation has
  // already written part of the field — a truncated field is rolled back
  // by restoring the NUL at the last COMPLETE field boundary before
  // returning, so the output ALWAYS matches the returned field count
  // (no half numbers: "free=12" can never come from "free=12345").
  if (cap == 0)
    return 0;
  size_t used = 0;  // offset of the NUL terminating the last complete field
  int fields = 0;
  int n = snprintf(out, cap, "pressure-seq=%lu", seq);
  if (n < 0 || static_cast<size_t>(n) >= cap) {
    out[used] = '\0';
    return fields;
  }
  used += static_cast<size_t>(n);
  fields = 1;
  n = snprintf(out + used, cap - used, " free=%u", free_b);
  if (n < 0 || static_cast<size_t>(n) >= cap - used) {
    out[used] = '\0';
    return fields;
  }
  used += static_cast<size_t>(n);
  fields = 2;
  n = snprintf(out + used, cap - used, " min_free=%u", min_free_b);
  if (n < 0 || static_cast<size_t>(n) >= cap - used) {
    out[used] = '\0';
    return fields;
  }
  used += static_cast<size_t>(n);
  fields = 3;
  n = snprintf(out + used, cap - used, " max_block=%u", max_block_b);
  if (n < 0 || static_cast<size_t>(n) >= cap - used) {
    out[used] = '\0';
    return fields;
  }
  used += static_cast<size_t>(n);
  fields = 4;
  return fields;
}

}  // namespace mwcp_diag

#endif  // MWCP_DIAG_FMT_H
