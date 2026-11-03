#pragma once

#include "mwcp_service.h"

#include <stddef.h>
#include <stdint.h>

namespace mwcp_host {

struct PersistOps {
  bool (*write)(void *user, const char *ssid, const char *password);
  bool (*sync)(void *user);
  bool (*readback)(void *user, char *ssid, size_t ssid_cap, char *password, size_t pass_cap);
  void *user;
};

bool persist_credentials(const PersistOps &ops, const char *ssid, const char *password, const char *prev_ssid,
                         const char *prev_pass);
const char *scan_auth_name(bool with_auth);

/// Dependency calls behind one component-owned scan.
///
/// Production maps these directly onto WiFiComponent; host tests inject a fake
/// that mirrors the patched contract. Keeping the decision logic here (instead
/// of inside the Espressif glue) means the refusal, busy and suppression rules
/// are executed by the same code in tests and on hardware.
struct OwnedWifiApi {
  bool (*disabled)(void *user);
  bool (*roaming)(void *user);
  void (*request_suppression)(void *user);
  void (*release_suppression)(void *user);
  bool (*start)(void *user, uint32_t *generation);
  void *user;
};

/// Acquire the radio for one component-owned scan.
///
/// Returns kStarted only after the dependency accepted the scan and wrote its
/// generation. No station connection is required: first-time provisioning on a
/// never-provisioned device scans while offline, and AP fallback or cooldown
/// states do not block the request. Refuses when WiFi is disabled (kRefused),
/// when the connection state machine or a roaming scan owns the radio, when an
/// earlier component request has not completed, or when the driver rejected
/// the start (kBusy). Roaming suppression is held only across the scan: it is
/// requested before the driver call and released on refusal here, or later
/// through ScanPlatform::finish.
ScanStart acquire_owned_scan(const OwnedWifiApi &api, uint32_t *generation);

/// Platform side of an owned scan.
struct ScanPlatform {
  /// Start one owned scan; write the dependency's generation on success.
  ScanStart (*start)(void *user, uint32_t *generation);
  /// Called once when ownership ends, for any reason, so the platform can
  /// release whatever it held for the scan (roaming suppression in production).
  void (*finish)(void *user);
  void *user;
};

/// Serialsises one scan request against the dependency's asynchronous
/// completion.
///
/// The dependency reports exactly one completion per accepted scan, carrying
/// the generation that start() returned. Completions for scans this owner no
/// longer waits for are counted and dropped; the dependency's exclusive gate
/// ensures a completion while no request is pending belongs to a background
/// scan and is never delivered to a request. A success is published only when
/// its records were retrievable: a completion that announces records but
/// yields none (a memory shortage after the scan) fails the request instead of
/// publishing an empty list. Generation matching replaces the old
/// fingerprint/drain heuristics, so no fixed delays or loop-order assumptions
/// are involved.
class ScanOwner {
 public:
  using CopyFn = int (*)(void *user, WifiAp *out, int cap, bool *truncated);

  /// Stop waiting for a scan after this bound; the dependency still owns the
  /// radio until its completion arrives (a late completion is ignored here and
  /// must not be attributed to a newer request).
  static const uint32_t kHoldBoundMs = 60000;

  void configure(const ScanPlatform &platform);

  /// Arm and start one scan. kBusy while an earlier request still owns the
  /// radio; the dependency's own outcome otherwise.
  ScanStart start(uint32_t now_ms);

  /// 0..kScanCap: one completed result; -1: pending; -2: no request or failure.
  int poll(uint32_t now_ms, WifiAp *out, int cap, bool *truncated);

  /// Stop counting the request as waiting after the hold bound, without
  /// reopening the dependency's ownership. A completion that arrives later is
  /// dropped here instead of being published; processing that event is what
  /// reopens ownership for a new request.
  void tick(uint32_t now_ms);

  /// Called by the dependency's completion listener with the generation that
  /// start() returned. Copies the just-finished scan through `copy` while the
  /// dependency still holds the records.
  void on_completion(uint32_t generation, uint32_t status, uint16_t number, CopyFn copy, void *user);

  bool waiting() const { return phase_ == WAIT; }
  uint32_t ignored_completions() const { return ignored_; }

 private:
  enum Phase : uint8_t { IDLE, WAIT, COMPLETE, FAILED };

  void release_hold();
  int deliver(WifiAp *out, int cap, bool *truncated);

  ScanPlatform platform_{};
  Phase phase_{IDLE};
  uint32_t start_ms_{0};
  uint32_t active_generation_{0};
  bool hold_{false};
  int snapshot_count_{-1};
  bool snapshot_truncated_{false};
  WifiAp snapshot_[kScanCap]{};
  uint32_t ignored_{0};
};

}  // namespace mwcp_host
