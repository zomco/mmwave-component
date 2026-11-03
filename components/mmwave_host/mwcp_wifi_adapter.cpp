#include "mwcp_wifi_adapter.h"

#include <string.h>

namespace mwcp_host {

static bool restore_previous(const PersistOps &ops, const char *prev_ssid, const char *prev_pass) {
  if (!prev_ssid || !prev_pass)
    return false;
  if (!ops.write(ops.user, prev_ssid, prev_pass))
    return false;
  if (!ops.sync(ops.user))
    return false;
  char got_ssid[33];
  char got_pass[65];
  memset(got_ssid, 0, sizeof(got_ssid));
  memset(got_pass, 0, sizeof(got_pass));
  if (!ops.readback(ops.user, got_ssid, sizeof(got_ssid), got_pass, sizeof(got_pass)))
    return false;
  return strcmp(got_ssid, prev_ssid) == 0 && strcmp(got_pass, prev_pass) == 0;
}

bool persist_credentials(const PersistOps &ops, const char *ssid, const char *password, const char *prev_ssid,
                         const char *prev_pass) {
  if (!ops.write || !ops.sync || !ops.readback || !ssid || !password)
    return false;
  if (!ops.write(ops.user, ssid, password))
    return false;
  if (!ops.sync(ops.user)) {
    restore_previous(ops, prev_ssid, prev_pass);
    return false;
  }
  char got_ssid[33];
  char got_pass[65];
  memset(got_ssid, 0, sizeof(got_ssid));
  memset(got_pass, 0, sizeof(got_pass));
  if (!ops.readback(ops.user, got_ssid, sizeof(got_ssid), got_pass, sizeof(got_pass)) || strcmp(got_ssid, ssid) != 0 ||
      strcmp(got_pass, password) != 0) {
    restore_previous(ops, prev_ssid, prev_pass);
    return false;
  }
  return true;
}

const char *scan_auth_name(bool with_auth) { return with_auth ? "unknown" : "open"; }

ScanStart acquire_owned_scan(const OwnedWifiApi &api, uint32_t *generation) {
  if (generation == nullptr || api.start == nullptr)
    return ScanStart::kUnsupported;
  if (api.disabled != nullptr && api.disabled(api.user))
    return ScanStart::kRefused;
  if (api.roaming != nullptr && api.roaming(api.user))
    return ScanStart::kBusy;

  if (api.request_suppression != nullptr)
    api.request_suppression(api.user);
  uint32_t gen = 0;
  if (!api.start(api.user, &gen)) {
    // The dependency refused the start: the connection state machine or a
    // roaming scan owns the radio, an earlier component request is still
    // pending, or the driver rejected the scan. Undo the suppression request.
    if (api.release_suppression != nullptr)
      api.release_suppression(api.user);
    return ScanStart::kBusy;
  }
  *generation = gen;
  return ScanStart::kStarted;
}

void ScanOwner::configure(const ScanPlatform &platform) {
  platform_ = platform;
  phase_ = IDLE;
  active_generation_ = 0;
  hold_ = false;
  snapshot_count_ = -1;
  snapshot_truncated_ = false;
  ignored_ = 0;
}

void ScanOwner::release_hold() {
  if (!hold_)
    return;
  hold_ = false;
  if (platform_.finish != nullptr)
    platform_.finish(platform_.user);
}

ScanStart ScanOwner::start(uint32_t now_ms) {
  if (phase_ == WAIT)
    return ScanStart::kBusy;
  if (phase_ == COMPLETE || phase_ == FAILED) {
    // An earlier completion was never polled; drop it before starting again.
    phase_ = IDLE;
    snapshot_count_ = -1;
    snapshot_truncated_ = false;
  }
  if (platform_.start == nullptr)
    return ScanStart::kUnsupported;

  uint32_t generation = 0;
  const ScanStart result = platform_.start(platform_.user, &generation);
  if (result != ScanStart::kStarted)
    return result;

  active_generation_ = generation;
  start_ms_ = now_ms;
  snapshot_count_ = -1;
  snapshot_truncated_ = false;
  phase_ = WAIT;
  hold_ = true;
  return ScanStart::kStarted;
}

void ScanOwner::on_completion(uint32_t generation, uint32_t status, uint16_t number, CopyFn copy, void *user) {
  if (phase_ != WAIT || generation != active_generation_) {
    // A completion for a scan this owner already abandoned; publishing it
    // would answer a later request with an earlier scan's access points.
    ignored_++;
    return;
  }
  release_hold();
  if (status != 0) {
    phase_ = FAILED;
    return;
  }
  if (number > 0) {
    if (copy == nullptr) {
      phase_ = FAILED;
      return;
    }
    bool truncated = false;
    int n = copy(user, snapshot_, kScanCap, &truncated);
    if (n <= 0) {
      // The scan announced records but none were retrievable (memory shortage
      // after the scan). Never publish that as a successful empty scan.
      phase_ = FAILED;
      return;
    }
    if (n > kScanCap)
      n = kScanCap;
    snapshot_count_ = n;
    snapshot_truncated_ = truncated || number > static_cast<uint16_t>(n);
  } else {
    snapshot_count_ = 0;
    snapshot_truncated_ = false;
  }
  phase_ = COMPLETE;
}

int ScanOwner::deliver(WifiAp *out, int cap, bool *truncated) {
  int n = snapshot_count_;
  if (n < 0)
    n = 0;
  bool trunc = snapshot_truncated_;
  if (n > cap) {
    n = cap;
    trunc = true;
  }
  if (n > 0 && out != nullptr)
    memcpy(out, snapshot_, sizeof(WifiAp) * static_cast<size_t>(n));
  if (truncated)
    *truncated = trunc;
  phase_ = IDLE;
  snapshot_count_ = -1;
  snapshot_truncated_ = false;
  return n;
}

int ScanOwner::poll(uint32_t now_ms, WifiAp *out, int cap, bool *truncated) {
  (void) now_ms;
  if (truncated)
    *truncated = false;
  if (phase_ == COMPLETE)
    return deliver(out, cap, truncated);
  if (phase_ == FAILED) {
    phase_ = IDLE;
    snapshot_count_ = -1;
    snapshot_truncated_ = false;
    return -2;
  }
  if (phase_ == WAIT)
    return -1;
  return -2;
}

void ScanOwner::tick(uint32_t now_ms) {
  if (phase_ != WAIT)
    return;
  if (now_ms - start_ms_ < kHoldBoundMs)
    return;
  // The dependency did not report our completion within the bound. Stop
  // counting this request as waiting and release the suppression hold, but do
  // not claim the radio can be reused: the dependency keeps ownership until
  // the completion event is processed, and a late completion is ignored here.
  phase_ = IDLE;
  active_generation_ = 0;
  release_hold();
}

}  // namespace mwcp_host
