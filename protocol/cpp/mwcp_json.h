#pragma once

#include <stddef.h>
#include <stdint.h>

namespace mwcp {

bool json_check(const uint8_t *data, size_t len);
bool utf8_check(const uint8_t *data, size_t len);
const char *json_error_code();
const char *json_overflow_threshold();

}  // namespace mwcp
