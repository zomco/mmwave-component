#include "mmwave_host.h"

#include "mwcp_wifi_adapter.h"

#include <cstdlib>

#include "r60abd1.h"
#include "radar_observe.h"
#include "mwcp_codec.h"

#include "esphome/components/logger/logger.h"
#include "esphome/components/wifi/wifi_component.h"
#include "esphome/core/application.h"
#include "esphome/core/log.h"

// A scan is only started when ESPHome can prove which scan a completion
// belongs to. The pinned patch (scripts/apply_esphome_patch.py) provides
// start_scan_for_component() and the completion listener; without it,
// wifi.scan fails with UNSUPPORTED instead of guessing.
#if defined(MWCP_WIFI_SCAN_OWNERSHIP) && defined(USE_WIFI_SCAN_COMPLETION_LISTENERS)
#define MWCP_OWNED_SCAN 1
#endif

#include "driver/usb_serial_jtag.h"
#include "esp_mac.h"
#include "esp_random.h"
#include "esp_system.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

namespace esphome {
namespace mmwave_host {
namespace {

static const char *const TAG = "mmwave_host";

#ifdef MWCP_OWNED_SCAN
int copy_current_scan(void *user, mwcp_host::WifiAp *out, int cap, bool *truncated) {
  (void) user;
  int n = 0;
  if (truncated)
    *truncated = false;
  auto *wifi = wifi::global_wifi_component;
  if (wifi == nullptr)
    return 0;
  // Runs from the WiFi component's main-loop event processing
  // (wifi_loop_ -> wifi_process_event_), not from the Wi-Fi event task, so the
  // results are stable without taking the cross-task scan results lock.
  for (const auto &item : wifi->get_scan_result()) {
    if (n >= cap) {
      if (truncated)
        *truncated = true;
      break;
    }
    snprintf(out[n].ssid, sizeof(out[n].ssid), "%s", item.get_ssid().c_str());
    out[n].rssi = item.get_rssi();
    snprintf(out[n].auth, sizeof(out[n].auth), "%s", mwcp_host::scan_auth_name(item.get_with_auth()));
    out[n].hidden = item.get_is_hidden();
    n++;
  }
  return n;
}

class ScanCompletionListener : public wifi::WiFiScanCompletionListener {
 public:
  void set_owner(mwcp_host::ScanOwner *owner) { owner_ = owner; }

  void on_wifi_scan_completion(uint32_t generation, uint32_t status, uint16_t number) override {
    if (owner_ == nullptr)
      return;
    owner_->on_completion(generation, status, number, copy_current_scan, nullptr);
  }

 private:
  mwcp_host::ScanOwner *owner_{nullptr};
};

ScanCompletionListener g_scan_completion_listener;
#endif  // MWCP_OWNED_SCAN

}  // namespace

void MwcpHost::on_error(mwcp::Status, void *) {}

void MwcpHost::on_frame(const mwcp::Frame &frame, void *user) {
  if (frame.kind != 1 || frame.payload == nullptr)
    return;
  auto *self = static_cast<MwcpHost *>(user);
  // Deferred dispatch (F-10 fix): see the member comment in the header.
  // The stash owns a bounded payload copy (G2-R3-01) - a later frame in the
  // same parser push, even a bad-CRC one, cannot rewrite what will be
  // dispatched. Full-slot policy (idempotent resend overwrite / different
  // request dropped and counted) is in DeferredRequest.
  self->deferred_.stash(frame);
}

bool MwcpHost::load_slot(void *user, int slot, uint8_t *dst, size_t len) {
  auto *self = static_cast<MwcpHost *>(user);
  if (!self->prefs_ready_ || slot < 0 || slot > 1)
    return false;
  return self->slot_pref_[slot].load(dst, len);
}

bool MwcpHost::sync_storage(void *) { return global_preferences->sync(); }

bool MwcpHost::store_slot(void *user, int slot, const uint8_t *src, size_t len) {
  auto *self = static_cast<MwcpHost *>(user);
  if (!self->prefs_ready_ || slot < 0 || slot > 1)
    return false;
  return self->slot_pref_[slot].save(src, len);
}

mwcp_host::ScanStart MwcpHost::platform_start_scan(void *user, uint32_t *generation) {
#ifndef MWCP_OWNED_SCAN
  // Stock ESPHome cannot attribute scan completions to a request; refusing here
  // makes wifi.scan return UNSUPPORTED instead of publishing another scan's
  // access points as this request's result.
  (void) user;
  (void) generation;
  return mwcp_host::ScanStart::kUnsupported;
#else
  auto *self = static_cast<MwcpHost *>(user);
  if (!self->scan_completion_registered_ || wifi::global_wifi_component == nullptr)
    return mwcp_host::ScanStart::kUnsupported;
  mwcp_host::OwnedWifiApi api{};
  api.user = self;
  api.disabled = [](void *) { return wifi::global_wifi_component->is_disabled(); };
  api.roaming = [](void *) { return wifi::global_wifi_component->is_roaming(); };
  api.request_suppression = [](void *) {
#ifdef USE_WIFI_RUNTIME_ROAMING_SUPPRESSION
    wifi::global_wifi_component->request_roaming_suppression();
#endif
  };
  api.release_suppression = [](void *) {
#ifdef USE_WIFI_RUNTIME_ROAMING_SUPPRESSION
    wifi::global_wifi_component->release_roaming_suppression();
#endif
  };
  api.start = [](void *, uint32_t *gen) { return wifi::global_wifi_component->start_scan_for_component(gen); };
  return mwcp_host::acquire_owned_scan(api, generation);
#endif
}

void MwcpHost::platform_finish_scan(void *) {
#ifdef USE_WIFI_RUNTIME_ROAMING_SUPPRESSION
  if (wifi::global_wifi_component != nullptr)
    wifi::global_wifi_component->release_roaming_suppression();
#endif
}

mwcp_host::ScanStart MwcpHost::start_scan(void *user) {
  auto *self = static_cast<MwcpHost *>(user);
  return self->scan_owner_.start(millis());
}

int MwcpHost::poll_scan(void *user, mwcp_host::WifiAp *out, int cap, bool *truncated) {
  auto *self = static_cast<MwcpHost *>(user);
  return self->scan_owner_.poll(millis(), out, cap, truncated);
}

bool MwcpHost::start_connect(void *user, const char *ssid, const char *password, const char *auth) {
  auto *self = static_cast<MwcpHost *>(user);
  if (wifi::global_wifi_component == nullptr)
    return false;
  (void) auth;
  wifi::WiFiAP current = wifi::global_wifi_component->get_sta();
  snprintf(self->saved_ssid_, sizeof(self->saved_ssid_), "%s", current.get_ssid().c_str());
  snprintf(self->saved_pass_, sizeof(self->saved_pass_), "%s", current.get_password().c_str());
  wifi::WiFiAP ap;
  ap.set_ssid(ssid);
  ap.set_password(password);
  // Provisioning must win the radio: set_sta() replaces the network list with
  // this AP, points the retry state machine at it and skips the cooldown, so
  // the YAML network's reconnect loop cannot steal the connect window back
  // (G2 F-2: the provision job raced the absent-SSID retry storm and always
  // missed its deadline). persist_wifi() repeats the set_sta on success; the
  // rollback below restores the saved network either way.
  wifi::global_wifi_component->set_sta(ap);
  wifi::global_wifi_component->start_connecting(ap);
  snprintf(self->wanted_ssid_, sizeof(self->wanted_ssid_), "%s", ssid);
  self->connect_state_ = 0;
  self->connect_ip_[0] = 0;
  return true;
}

int MwcpHost::poll_connect(void *user, char *ip, size_t ip_cap, int *rssi) {
  auto *self = static_cast<MwcpHost *>(user);
  if (wifi::global_wifi_component == nullptr)
    return -1;
  if (!wifi::global_wifi_component->is_connected())
    return 0;
  char ssid[33]{};
  wifi::global_wifi_component->wifi_ssid_to(ssid);
  if (self->wanted_ssid_[0] && std::strcmp(ssid, self->wanted_ssid_) != 0)
    return 0;
  auto ips = wifi::global_wifi_component->wifi_sta_ip_addresses();
  if (ips.empty())
    return 0;
  char buf[40]{};
  ips[0].str_to(buf);
  if (buf[0] == 0 || std::strcmp(buf, "0.0.0.0") == 0)
    return 0;
  snprintf(ip, ip_cap, "%s", buf);
  snprintf(self->connect_ip_, sizeof(self->connect_ip_), "%s", buf);
  *rssi = wifi::global_wifi_component->wifi_rssi();
  self->connect_state_ = 1;
  return 1;
}

bool MwcpHost::persist_wifi(void *user, const char *ssid, const char *password) {
  (void) user;
  if (wifi::global_wifi_component == nullptr || ssid == nullptr || password == nullptr)
    return false;
  const uint32_t hash = wifi::global_wifi_component->has_sta() ? App.get_config_version_hash() : 88491487UL;
  auto pref = global_preferences->make_preference<wifi::SavedWifiSettings>(hash, true);
  mwcp_host::PersistOps ops{};
  ops.user = &pref;
  ops.write = [](void *slot, const char *wssid, const char *wpass) {
    auto *stored = static_cast<ESPPreferenceObject *>(slot);
    wifi::SavedWifiSettings save{};
    strncpy(save.ssid, wssid, sizeof(save.ssid) - 1);
    strncpy(save.password, wpass, sizeof(save.password) - 1);
    return stored->save(&save);
  };
  ops.sync = [](void *) { return global_preferences->sync(); };
  ops.readback = [](void *slot, char *out_ssid, size_t ssid_cap, char *out_pass, size_t pass_cap) {
    auto *stored = static_cast<ESPPreferenceObject *>(slot);
    wifi::SavedWifiSettings got{};
    if (!stored->load(&got))
      return false;
    snprintf(out_ssid, ssid_cap, "%s", got.ssid);
    snprintf(out_pass, pass_cap, "%s", got.password);
    return true;
  };
  wifi::SavedWifiSettings previous{};
  bool have_prev = pref.load(&previous);
  if (!mwcp_host::persist_credentials(ops, ssid, password, have_prev ? previous.ssid : "",
                                      have_prev ? previous.password : ""))
    return false;
  wifi::WiFiAP sta;
  sta.set_ssid(ssid);
  sta.set_password(password);
  wifi::global_wifi_component->set_sta(sta);
  return true;
}

bool MwcpHost::rollback_wifi(void *user) {
  auto *self = static_cast<MwcpHost *>(user);
  if (wifi::global_wifi_component == nullptr)
    return false;
  wifi::WiFiAP ap;
  ap.set_ssid(self->saved_ssid_);
  ap.set_password(self->saved_pass_);
  // Mirror start_connect(): give the retry state machine the saved network
  // back, or it would keep retrying the failed provision target.
  if (self->saved_ssid_[0])
    wifi::global_wifi_component->set_sta(ap);
  wifi::global_wifi_component->start_connecting(ap);
  memset(self->saved_pass_, 0, sizeof(self->saved_pass_));
  return true;
}

void MwcpHost::setup() {
  uint8_t mac[6]{};
  esp_read_mac(mac, ESP_MAC_WIFI_STA);
  uint32_t r0 = esp_random();
  uint32_t r1 = esp_random();
  uint16_t r2 = static_cast<uint16_t>(esp_random());
  uint8_t raw[16];
  memcpy(raw, mac, 6);
  raw[6] = static_cast<uint8_t>(r0);
  raw[7] = static_cast<uint8_t>(r0 >> 8);
  raw[8] = static_cast<uint8_t>(r0 >> 16);
  raw[9] = static_cast<uint8_t>(r0 >> 24);
  raw[10] = static_cast<uint8_t>(r1);
  raw[11] = static_cast<uint8_t>(r1 >> 8);
  raw[12] = static_cast<uint8_t>(r1 >> 16);
  raw[13] = static_cast<uint8_t>(r1 >> 24);
  raw[14] = static_cast<uint8_t>(r2);
  raw[15] = static_cast<uint8_t>(r2 >> 8);
  for (int i = 0; i < 16; i++)
    snprintf(boot_id_ + i * 2, 3, "%02x", raw[i]);
  snprintf(device_id_, sizeof(device_id_), "%02x%02x%02x%02x%02x%02x", mac[0], mac[1], mac[2], mac[3], mac[4], mac[5]);
  mwcp_host::Identity id{};
  id.device_id = device_id_;
  id.configured_model = "r60abd1";
  id.dimension = "2D";
  id.firmware_version = "mwcp-host";
#ifdef MWCP_GIT_SHA
  id.git_sha = MWCP_GIT_SHA;
#else
  id.git_sha = nullptr;
#endif
  id.release_channel = "development";
  id.build_profile = "host-enabled";
  id.cap_revision = "r60-cap-1";
  id.max_targets = 1;
  service_.begin(id, boot_id_);
  slot_pref_[0] = global_preferences->make_preference(1536, 0x4d573001, true);
  slot_pref_[1] = global_preferences->make_preference(1536, 0x4d573002, true);
  prefs_ready_ = true;
  mwcp_host::StoragePort storage{};
  storage.load = load_slot;
  storage.store = store_slot;
  storage.user = this;
  storage.sync = sync_storage;
  mwcp_host::WifiPort wifi{start_scan, poll_scan, start_connect, poll_connect, persist_wifi, rollback_wifi, this};
  service_.set_storage(storage);
  service_.set_wifi(wifi);
  service_.set_radar(&radar_view_);
  service_.set_publish_hook([](void *user) { static_cast<MwcpHost *>(user)->apply_to_radar(); }, this);
  mwcp_host::ScanPlatform scan_platform{platform_start_scan, platform_finish_scan, this};
  scan_owner_.configure(scan_platform);
#ifdef MWCP_OWNED_SCAN
  static bool completion_listener_added = false;
  if (!completion_listener_added && wifi::global_wifi_component != nullptr) {
    g_scan_completion_listener.set_owner(&scan_owner_);
    wifi::global_wifi_component->add_scan_completion_listener(&g_scan_completion_listener);
    completion_listener_added = true;
  }
  scan_completion_registered_ = completion_listener_added;
#else
  scan_completion_registered_ = false;
#endif
  if (!scan_completion_registered_)
    ESP_LOGE(TAG, "Wi-Fi scan unavailable; wifi.scan will fail with UNSUPPORTED");
  service_.set_radar_action(
      [](void *user) {
        auto *radar = static_cast<r60abd1::R60ABD1Component *>(user);
        if (!radar)
          return -1;
        radar->reset_module();
        return 0;
      },
      radar_);
  service_.load_storage();
  if (radar_ != nullptr && !service_.has_durable() && strcmp(service_.storage_state(), "recovery_required") != 0) {
    mwcp_host::LegacyInstall legacy{};
    const auto &cal = radar_->calibration();
    legacy.x = cal.radar_x;
    legacy.y = cal.radar_y;
    legacy.z = cal.radar_z;
    legacy.yaw = cal.yaw;
    legacy.pitch = cal.pitch;
    legacy.roll = cal.roll;
    legacy.has_polygon = !cal.polygon.empty();
    legacy.polygon_n = static_cast<int>(cal.polygon.size());
    if (legacy.polygon_n > 64)
      legacy.polygon_n = 64;
    for (int i = 0; i < legacy.polygon_n; i++) {
      legacy.polygon_xy[i * 2] = static_cast<int16_t>(cal.polygon[static_cast<size_t>(i)].x);
      legacy.polygon_xy[i * 2 + 1] = static_cast<int16_t>(cal.polygon[static_cast<size_t>(i)].y);
    }
    service_.migrate_legacy(legacy);
  }
  apply_to_radar();
  if (radar_ != nullptr) {
    radar_->set_host_observer(
        [](const r60abd1::R60HostObservation &sample, void *user) {
          auto *self = static_cast<MwcpHost *>(user);
          // P-G2-01: kind 5 does not set has_presence. Kind 1 is a real
          // 0x80 0x01 report or a 0x80 0x81 query reply, nothing else.
          mwcp_host::apply_observation(self->radar_view_, sample.kind, sample.presence, sample.distance_cm,
                                       sample.local_x, sample.local_y, sample.local_z, sample.room_x, sample.room_y,
                                       sample.in_boundary, sample.rate, sample.sample_ms);
          self->service().note_observation();
        },
        this);
  }
  // The rings must hold a full maximal frame (4096-byte payload + header +
  // COBS overhead ~ 4144 wire bytes): with the original 1024-byte rings a
  // max-legal CONFIG_VALIDATE/COMMIT killed the USB data path outright on
  // hardware - the peripheral stopped delivering RX while the CPU kept
  // running (G2 bench finding F-10). 4608 >= any wire frame, so a maximal
  // burst never has to wrap a full ring.
  usb_serial_jtag_driver_config_t cfg = {};
  cfg.rx_buffer_size = 4608;
  cfg.tx_buffer_size = 4608;
  const esp_err_t err = usb_serial_jtag_driver_install(&cfg);
  if (err != ESP_OK && err != ESP_ERR_INVALID_STATE)
    ESP_LOGW(TAG, "usb install %d", static_cast<int>(err));
  if (logger::global_logger != nullptr) {
    logger::global_logger->add_log_callback(this, [](void *self, uint8_t, const char *, const char *message, size_t) {
      auto *host = static_cast<MwcpHost *>(self);
      if (host->in_log_)
        return;
      host->in_log_ = true;
      host->service().push_log_at(message ? message : "", millis(), "info");
      host->in_log_ = false;
    });
  }
  // RSSI is sampled by a dedicated low-priority task (see sample_rssi_()):
  // esp_wifi_sta_get_ap_info() behind wifi_rssi() can stall for the whole
  // Wi-Fi driver-busy window, and calling it from loop() froze the TX pump
  // on the G2 bench (batch 5-7 "USB wedge").
  xTaskCreate(rssi_task_trampoline_, "mwcp_rssi", 3072, this, 1, reinterpret_cast<TaskHandle_t *>(&rssi_task_));
}

void MwcpHost::rssi_task_trampoline_(void *arg) {
  auto *self = static_cast<MwcpHost *>(arg);
  while (true) {
    vTaskDelay(pdMS_TO_TICKS(2000));
    self->sample_wifi_state_();
  }
}

// Runs in the low-priority sampling task: every query here may block on the
// Wi-Fi driver lock for the duration of a driver-busy window, which is fine
// away from loop() - only RSSI/SSID freshness suffers.
void MwcpHost::sample_wifi_state_() {
  auto *wifi = wifi::global_wifi_component;
  if (wifi == nullptr || !wifi->is_connected())
    return;
  if (service_.scan_pending())
    return;
  char ssid[33]{};
  wifi->wifi_ssid_to(ssid);
  const int rssi = wifi->wifi_rssi();
  char ip[40] = "null";
  const auto ips = wifi->wifi_sta_ip_addresses();
  if (!ips.empty()) {
    char buf[40]{};
    ips[0].str_to(buf);
    if (buf[0] != 0 && strcmp(buf, "0.0.0.0") != 0)
      snprintf(ip, sizeof(ip), "%s", buf);
  }
  portENTER_CRITICAL(&wifi_cache_mux_);
  memcpy(live_ssid_, ssid, sizeof(live_ssid_));
  strlcpy(live_ip_, ip, sizeof(live_ip_));
  live_rssi_ = rssi;
  have_rssi_ = true;
  portEXIT_CRITICAL(&wifi_cache_mux_);
}

void MwcpHost::apply_to_radar() {
  if (radar_ == nullptr)
    return;
  float x = 0, y = 0, z = 0, yaw = 0, pitch = 0, roll = 0;
  service_.export_install(&x, &y, &z, &yaw, &pitch, &roll);
  radar_->set_host_applying(true);
  radar_->set_radar_x(x);
  radar_->set_radar_y(y);
  radar_->set_radar_z(z);
  radar_->set_yaw(yaw);
  radar_->set_pitch(pitch);
  radar_->set_roll(roll);
  radar_->clear_polygon();
  int16_t xy[128];
  int n = 0;
  service_.export_boundary(xy, &n);
  for (int i = 0; i < n; i++)
    radar_->add_polygon_point(xy[i * 2], xy[i * 2 + 1]);
  for (uint8_t i = 0; i < 3; i++)
    radar_->clear_area(i);
  for (int i = 0; i < service_.area_count(); i++) {
    int slot = 0, points = 0;
    bool enabled = false;
    if (!service_.area_slot(i, &slot, &enabled, &points) || !enabled)
      continue;
    for (int p = 0; p < points; p++) {
      int x = 0, y = 0;
      if (service_.area_point(i, p, &x, &y))
        radar_->add_area_point(static_cast<uint8_t>(slot), static_cast<float>(x), static_cast<float>(y));
    }
  }
  radar_->set_host_applying(false);
  publish_areas_to_ha();
}

void MwcpHost::bind_area_slot(uint8_t slot, text::Text *entity, std::string *global) {
  if (slot > 2)
    return;
  area_text_[slot] = entity;
  area_global_[slot] = global;
}

void MwcpHost::publish_areas_to_ha() {
  for (uint8_t slot = 0; slot < 3; slot++) {
    if (area_text_[slot] == nullptr && area_global_[slot] == nullptr)
      continue;
    char text[256];
    if (!service_.export_area_text(slot, text, sizeof(text)))
      text[0] = 0;
    char published[256];
    char global_value[256];
    if (!mwcp_host::commit_area_view(published, sizeof(published), global_value, sizeof(global_value), true, text))
      continue;
    if (area_global_[slot] != nullptr)
      *area_global_[slot] = global_value;
    if (area_text_[slot] != nullptr)
      area_text_[slot]->publish_state(published);
  }
}

bool MwcpHost::commit_area_text(uint8_t slot, const char *text) {
  if (!service_.apply_area_text(slot, text, millis()))
    return false;
  apply_to_radar();
  return true;
}

bool MwcpHost::submit_polygon(const char *text) {
  // Static scratch: HA text callbacks reach this from the small main task
  // stack; single-threaded and written before read.
  static char changes[640];
  if (!text || !text[0]) {
    snprintf(changes, sizeof(changes), "{\"geometry.boundary_cm\":null}");
  } else {
    static char poly[520];
    poly[0] = 0;
    const char *p = text;
    int n = 0;
    while (*p && n < 64) {
      char *e1 = nullptr;
      double x = strtod(p, &e1);
      if (e1 == p || *e1 != ',')
        return false;
      char *e2 = nullptr;
      double y = strtod(e1 + 1, &e2);
      if (e2 == e1 + 1)
        return false;
      char pair[32];
      snprintf(pair, sizeof(pair), "%s[%.4g,%.4g]", n ? "," : "", x, y);
      if (strlen(poly) + strlen(pair) >= sizeof(poly))
        return false;
      strcat(poly, pair);
      n++;
      p = (*e2 == ';') ? e2 + 1 : e2;
      if (*p == 0)
        break;
      if (p == e2)
        return false;
    }
    if (n < 3)
      return false;
    snprintf(changes, sizeof(changes), "{\"geometry.boundary_cm\":[%s]}", poly);
  }
  if (!service_.apply_ha_changes(changes, millis()))
    return false;
  apply_to_radar();
  return true;
}

bool MwcpHost::submit_number(const char *key, float value) {
  if (!service_.apply_ha_number(key, value, millis()))
    return false;
  apply_to_radar();
  return true;
}

void MwcpHost::loop() {
  const uint32_t now = millis();
  // Keep the service's WIFI_STATUS fields truthful for a YAML-connected
  // device (G2 F-8). All Wi-Fi queries live in the sampling task; this path
  // only copies the cache - wifi_ssid_to()/wifi_rssi() from loop() stalled
  // the main loop for whole driver-busy windows (G2 bench, batches 5-7
  // "USB wedge").
  if (wifi::global_wifi_component != nullptr) {
    const bool live_connected = wifi::global_wifi_component->is_connected();
    char live_ssid[33];
    char live_ip[40];
    int live_rssi = 0;
    bool rssi_known = false;
    portENTER_CRITICAL(&wifi_cache_mux_);
    memcpy(live_ssid, live_ssid_, sizeof(live_ssid));
    strlcpy(live_ip, live_ip_, sizeof(live_ip));
    if (live_connected && have_rssi_) {
      live_rssi = live_rssi_;
      rssi_known = true;
    }
    portEXIT_CRITICAL(&wifi_cache_mux_);
    service_.note_wifi_state(live_connected, live_ssid, live_connected ? live_ip : "null", rssi_known, live_rssi);
  }
  int n = usb_serial_jtag_read_bytes(rx_, sizeof(rx_), 0);
  if (n > 0)
    parser_.push(rx_, static_cast<size_t>(n), now, on_frame, on_error, this);
  parser_.poll(now, on_error, this);
  // Deferred dispatch (F-10 fix): dispatch the stashed request only after
  // the parser has consumed everything the driver had, keeping the USB RX
  // FIFO drained during the long parse. The stash owns its payload
  // (G2-R3-01); dispatching reads the stash synchronously, and nothing
  // rewrites it until the next on_frame.
  if (deferred_.has()) {
    mwcp_dispatch_request(service_, link_, now, deferred_.session_id_, deferred_.request_id_, deferred_.code_,
                          deferred_.payload_, deferred_.payload_length_);
    deferred_.clear();
  }
  // G2-R3-01 (r3d): forward the kept same-id/different-body conflict to the
  // Service AFTER the original request. The Service's replay cache answers
  // ID_REUSE (protocol 3.2) without executing the conflicting body. The
  // slot is static and single; this stays bounded and keeps the RX
  // callback copy-only.
  if (deferred_.has_conflict()) {
    mwcp_dispatch_request(service_, link_, now, deferred_.conflict_session_, deferred_.conflict_request_,
                          deferred_.conflict_code_, deferred_.conflict_payload_, deferred_.conflict_length_);
    deferred_.clear_conflict();
  }
  link_.pump([&](const uint8_t *data, size_t want) { return usb_serial_jtag_write_bytes(data, want, 0); }, now);
  scan_owner_.tick(now);
  service_.poll(now);
  mwcp_forward_events(service_, link_);
  if (service_.restart_pending() && link_.control_accepted_by_driver() && usb_serial_jtag_wait_tx_done(0) == ESP_OK) {
    service_.ack_restart();
    esp_restart();
  }
}

}  // namespace mmwave_host
}  // namespace esphome
