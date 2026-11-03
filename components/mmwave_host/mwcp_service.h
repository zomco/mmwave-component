#pragma once

#include <stddef.h>
#include <stdint.h>

namespace mwcp_host {

static const int kJobCap = 8;
static const uint32_t kJobKeepMs = 300000;
static const int kReplay = 4;
static const int kPage = 2;
static const int kScanCap = 64;
static const int kTokenCap = 32;
static const int kCommitRing = 4;
static const uint32_t kSessionTtlMs = 15000;
static const int kMaxEventJson = 2048;

struct RadarView {
  bool seen_frame = false;
  uint32_t last_frame_ms = 0;
  uint32_t frames = 0;
  uint32_t errors = 0;
  bool has_presence = false;
  bool presence = false;
  uint32_t presence_ms = 0;
  bool has_xy = false;
  int16_t local_x = 0;
  int16_t local_y = 0;
  int16_t local_z = 0;
  float room_x = 0;
  float room_y = 0;
  bool in_boundary = true;
  uint32_t position_ms = 0;
  bool has_distance = false;
  uint16_t distance_cm = 0;
  uint32_t distance_ms = 0;
  bool has_breath = false;
  float breath = 0;
  uint32_t breath_ms = 0;
  bool has_heart = false;
  float heart = 0;
  uint32_t heart_ms = 0;
  uint32_t source_seq = 0;
};

struct WifiAp {
  char ssid[33];
  int8_t rssi;
  char auth[12];
  bool hidden;
};

struct StoragePort {
  bool (*load)(void *user, int slot, uint8_t *dst, size_t len);
  bool (*store)(void *user, int slot, const uint8_t *src, size_t len);
  void *user;
  bool (*sync)(void *user) = nullptr;
  bool (*readback)(void *user, int slot, uint8_t *dst, size_t len) = nullptr;
};

/// Outcome of a Wi-Fi scan start request.
enum class ScanStart : uint8_t {
  kStarted = 0,  ///< The dependency accepted the scan and owns the radio.
  kUnsupported,  ///< This build cannot attribute scan completions; never guess.
  kBusy,         ///< The radio is already scanning (ours, a roam, or a driver refusal).
  kRefused,      ///< Scanning is not allowed right now (WiFi disabled or not connected).
};

struct WifiPort {
  ScanStart (*start_scan)(void *user);
  int (*poll_scan)(void *user, WifiAp *out, int cap, bool *truncated);
  bool (*start_connect)(void *user, const char *ssid, const char *password, const char *auth);
  int (*poll_connect)(void *user, char *ip, size_t ip_cap, int *rssi);
  bool (*persist)(void *user, const char *ssid, const char *password);
  bool (*rollback)(void *user);
  void *user;
};

struct Identity {
  const char *device_id;
  const char *configured_model;
  const char *dimension;
  const char *firmware_version;
  const char *git_sha;
  const char *release_channel;
  const char *build_profile;
  const char *cap_revision;
  int max_targets;
};

struct LegacyInstall {
  float x;
  float y;
  float z;
  float yaw;
  float pitch;
  float roll;
  bool has_polygon;
  int polygon_n;
  int16_t polygon_xy[128];
};

class Service {
 public:
  void begin(const Identity &id, const char *boot_id);
  void set_storage(const StoragePort &port);
  void set_wifi(const WifiPort &port);
  void set_radar(RadarView *radar);
  void note_observation();
  void load_storage();
  bool migrate_legacy(const LegacyInstall &legacy);
  bool handle(uint32_t now_ms, uint32_t session, uint32_t request, uint16_t code, const uint8_t *payload, size_t len,
              char *out, size_t cap, uint32_t *out_session);
  void poll(uint32_t now_ms);
  bool next_event(char *out, size_t cap, uint16_t *code);
  const char *boot_id() const { return boot_id_; }
  const char *revision() const { return revision_; }
  const char *storage_state() const { return storage_; }
  bool has_durable() const { return durable_; }
  int record_count() const;
  bool restart_pending() const { return restart_pending_; }
  void ack_restart() { restart_pending_ = false; }
  uint32_t session_id() const { return session_id_; }
  int write_tokens() const { return tokens_; }
  bool config_z(int *out) const;
  void export_boundary(int16_t *xy, int *n) const;
  void export_install(float *x, float *y, float *z, float *yaw, float *pitch, float *roll) const;
  bool apply_ha_number(const char *key, float value, uint32_t now_ms);
  bool apply_ha_changes(const char *changes, uint32_t now_ms);
  void set_publish_hook(void (*fn)(void *user), void *user) {
    publish_hook_ = fn;
    publish_user_ = user;
  }
  int area_count() const;
  bool has_commit(const char *op_id) const;
  bool area_slot(int index, int *slot, bool *enabled, int *points) const;
  bool area_point(int index, int point, int *x, int *y) const;
  uint64_t revision_u64() const;
  int reset_sends() const { return reset_sends_; }
  void push_log(const char *message);
  void push_log_at(const char *message, uint32_t sample_ms, const char *level);
  uint32_t logs_dropped() const { return logs_dropped_; }
  uint32_t unsent_events() const { return tx_overflow_; }
  void note_unsent_event() { tx_overflow_++; }
  bool export_area_text(uint8_t slot, char *out, size_t cap) const;
  uint32_t admitted_wire() const { return admitted_wire_; }
  int stream_hz(int index) const { return index >= 0 && index < 5 ? stream_rate_[index] : 0; }
  bool apply_area_text(uint8_t slot, const char *text, uint32_t now_ms);
  const char *area_name(int index) const;
  void set_radar_action(int (*reset_module)(void *user), void *user) {
    reset_module_ = reset_module;
    reset_user_ = user;
  }
  const char *wifi_state() const { return wifi_state_; }
  const char *wifi_ssid() const { return wifi_ssid_; }
  /// True while a wifi.scan job owns the radio. The host component must not
  /// touch blocking esp_wifi getters in this window (G2 bench finding: the
  /// main loop stalled for the whole scan duration, freezing the TX pump).
  bool scan_pending() const { return scan_pending_; }
  /// Push the live Wi-Fi link truth (the host component calls this when it
  /// changes). WIFI_STATUS renders these fields; without it a YAML-connected
  /// device reported "disconnected" forever because only the provision flow
  /// ever updated them (G2 hardware finding F-8). Skipped while a provision
  /// job or a component scan owns the transitional state.
  void note_wifi_state(bool connected, const char *ssid, const char *ip, bool rssi_known, int rssi);

 private:
  struct Replay {
    bool used;
    uint32_t request_id;
    uint16_t code;
    uint8_t sha[32];
    uint16_t len;
    char body[2048];
  };
  struct Commit {
    bool used;
    char op_id[40];
    uint8_t sha[32];
    char revision[24];
  };
  struct Job {
    bool used;
    bool active;
    char id[16];
    char op_id[40];
    char action_id[32];
    uint8_t sha[32];
    char resource[12];
    char state[12];
    char stage[16];
    uint32_t started_ms;
    uint32_t finished_ms;
    bool has_finished;
    char error_code[32];
  };
  struct Point {
    int16_t x;
    int16_t y;
  };
  struct Area {
    bool used;
    uint8_t slot;
    bool enabled;
    char name[33];
    uint8_t n;
    Point points[12];
  };

  bool session_ok(uint32_t session, uint32_t now_ms);
  void expire_session();
  int find_replay(uint32_t request, uint16_t code, const uint8_t sha[32]) const;
  void store_replay(uint32_t request, uint16_t code, const uint8_t sha[32], const char *body);
  bool admit_job(uint32_t now_ms, const char *op_id, const uint8_t sha[32], const char *action, const char *resource,
                 bool confirm_required, const char *confirm, char *out, size_t cap, bool *created);
  void reclaim(uint32_t now_ms);
  bool resource_busy(const char *resource, char *active_id, size_t cap) const;
  int count_records() const;
  bool same_op(const char *op_id, const uint8_t sha[32], char *job_id, size_t cap, bool *reuse) const;
  void finish_job(Job *job, uint32_t now_ms, bool ok, const char *error);
  void restore_wifi_state_after_scan();
  void write_job(const Job &job, char *out, size_t cap) const;
  bool apply_changes(const uint8_t *payload, size_t len, char *err, size_t err_cap, const char **field,
                     const char **code, bool publish);
  bool persist_config();
  void fill_blob(void *blob) const;
  void read_blob(const void *blob);
  void bump_revision();
  bool emit_event(uint16_t code, const char *json);
  void redact(char *text) const;

  Identity id_{};
  char boot_id_[33]{};
  uint32_t session_id_ = 0;
  uint32_t next_session_ = 0x1000;
  uint32_t touched_ms_ = 0;
  uint32_t seen_max_ = 0;
  char nonce_[33]{};
  bool session_live_ = false;
  bool sub_telemetry_ = false;
  bool sub_status_ = false;
  bool sub_config_ = false;
  bool sub_jobs_ = false;
  bool sub_logs_ = false;
  // Diagnostic log-pressure source state (only compiled with
  // MWCP_LOG_PRESSURE_HZ; see Service::poll in mwcp_service.cpp).
  uint32_t log_pressure_ms_ = 0;
  uint32_t log_pressure_seq_ = 0;
  int event_budget_ = 8000;
  uint32_t rpc_window_ms_ = 0;
  int rpc_count_ = 0;
  int tokens_ = kTokenCap;
  uint32_t token_ms_ = 0;
  Replay replay_[kReplay]{};
  int replay_next_ = 0;
  Commit commits_[kCommitRing]{};
  int commit_next_ = 0;
  Job jobs_[kJobCap]{};
  uint32_t next_job_ = 1;
  char revision_[24] = "1";
  char storage_[24] = "healthy";
  int32_t x_cm_ = 0;
  int32_t y_cm_ = 0;
  int32_t z_cm_ = 220;
  int16_t yaw_tenth_ = 0;
  int16_t pitch_half_ = 0;
  int16_t roll_half_ = 0;
  bool boundary_set_ = false;
  uint8_t boundary_n_ = 0;
  Point boundary_[64]{};
  Area areas_[3]{};
  StoragePort storage_port_{};
  bool have_storage_ = false;
  bool durable_ = false;
  WifiPort wifi_port_{};
  bool have_wifi_ = false;
  RadarView *radar_ = nullptr;
  char wifi_state_[16] = "disconnected";
  char wifi_ssid_[33]{};
  char wifi_ip_[40] = "null";
  int wifi_rssi_ = 0;
  bool wifi_rssi_known_ = false;
  char wifi_error_[32] = "null";
  char saved_ssid_[33]{};
  char saved_pass_[65]{};
  bool have_saved_wifi_ = false;
  int scan_n_ = 0;
  bool scan_truncated_ = false;
  bool scan_prev_connected_ = false;
  WifiAp scan_[kScanCap]{};
  char scan_job_[16]{};
  bool logs_enabled_ = false;
  uint32_t debug_until_ms_ = 0;
  uint32_t logs_dropped_ = 0;
  uint32_t rx_frames_ = 0;
  uint32_t invalid_requests_ = 0;
  uint32_t telemetry_coalesced_ = 0;
  uint32_t tx_overflow_ = 0;
  bool restart_pending_ = false;
  char event_q_[8][kMaxEventJson]{};
  uint16_t event_code_[8]{};
  int event_n_ = 0;
  uint32_t last_source_seq_sent_ = 0;
  bool telemetry_held_ = false;
  int telem_gap_ms_ = 1000;
  uint32_t last_telem_ms_ = 0;
  int budget_left_ = 8000;
  uint32_t budget_window_ = 0;
  int (*reset_module_)(void *) = nullptr;
  void *reset_user_ = nullptr;
  int reset_sends_ = 0;
  uint32_t scan_deadline_ms_ = 0;
  uint32_t provision_deadline_ms_ = 0;
  char provision_ssid_[33]{};
  uint32_t logs_ring_drop_ = 0;
  void (*publish_hook_)(void *) = nullptr;
  void *publish_user_ = nullptr;
  int stream_rate_[5] = {0, 0, 0, 0, 0};
  bool stream_sent_[5] = {false, false, false, false, false};
  uint32_t stream_last_ms_[5] = {0, 0, 0, 0, 0};
  uint32_t clock_ms_ = 0;
  uint32_t event_wire_seq_ = 1;
  uint32_t admitted_wire_ = 0;
  uint32_t scan_generation_ = 0;
  bool scan_pending_ = false;
};

bool redact_secrets(const char *in, char *out, size_t cap);
bool commit_area_view(char *published, size_t published_cap, char *global_value, size_t global_cap, bool commit_ok,
                      const char *committed);

}  // namespace mwcp_host
