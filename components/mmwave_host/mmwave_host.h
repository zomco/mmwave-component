#pragma once

#include "deferred_request.h"
#include "mwcp_link.h"
#include "mwcp_service.h"
#include "mwcp_wifi_adapter.h"

#include "esphome/components/text/text.h"
#include "esphome/core/component.h"
#include "esphome/core/preferences.h"

#include "freertos/FreeRTOS.h"

#include <string>

namespace esphome {
namespace r60abd1 {
class R60ABD1Component;
}

namespace mmwave_host {

class MwcpHost : public Component {
 public:
  void setup() override;
  void loop() override;
  float get_setup_priority() const override { return -200.0f; }
  void set_radar(r60abd1::R60ABD1Component *radar) { radar_ = radar; }
  bool submit_number(const char *key, float value);
  bool submit_polygon(const char *text);
  bool commit_area_text(uint8_t slot, const char *text);
  void bind_area_slot(uint8_t slot, text::Text *entity, std::string *global);
  void publish_areas_to_ha();
  bool area_text(uint8_t slot, char *out, size_t cap) const { return service_.export_area_text(slot, out, cap); }
  void apply_to_radar();

  mwcp_host::Service &service() { return service_; }

 private:
  static bool load_slot(void *user, int slot, uint8_t *dst, size_t len);
  static bool store_slot(void *user, int slot, const uint8_t *src, size_t len);
  static bool sync_storage(void *user);
  static mwcp_host::ScanStart platform_start_scan(void *user, uint32_t *generation);
  static void platform_finish_scan(void *user);
  static mwcp_host::ScanStart start_scan(void *user);
  static int poll_scan(void *user, mwcp_host::WifiAp *out, int cap, bool *truncated);
  static bool start_connect(void *user, const char *ssid, const char *password, const char *auth);
  static int poll_connect(void *user, char *ip, size_t ip_cap, int *rssi);
  static bool persist_wifi(void *user, const char *ssid, const char *password);
  static bool rollback_wifi(void *user);
  static void on_frame(const mwcp::Frame &frame, void *user);
  static void on_error(mwcp::Status status, void *user);
  static void rssi_task_trampoline_(void *arg);
  void sample_wifi_state_();

  r60abd1::R60ABD1Component *radar_{nullptr};
  mwcp_host::Service service_{};
  mwcp_host::RadarView radar_view_{};
  MwcpHostLink link_{};
  mwcp::Parser parser_{};
  uint8_t rx_[256]{};
  bool tx_drained_{false};
  ESPPreferenceObject slot_pref_[2]{};
  bool prefs_ready_{false};
  char boot_id_[33]{};
  char device_id_[16]{};
  mwcp_host::ScanOwner scan_owner_{};
  bool scan_completion_registered_{false};
  text::Text *area_text_[3]{};
  std::string *area_global_[3]{};
  int connect_state_{0};
  char connect_ip_[40]{};
  int connect_rssi_{0};
  // WiFi truth cache for the per-pass F-8 push. Every esphome wifi query
  // behind wifi_ssid_to()/wifi_rssi() reaches esp_wifi_sta_get_ap_info(),
  // which takes the Wi-Fi driver lock and stalls for the whole driver-busy
  // window (roaming/coex scan included) - calling them from loop() froze
  // the main loop and the TX pump on the G2 bench (batches 5-7 "USB
  // wedge"). A dedicated low-priority task fills this cache; loop() only
  // takes a short critical-section copy.
  // Deferred dispatch (F-10 fix): on_frame stashes the request and loop()
  // dispatches it after parser_.push() has consumed everything the driver
  // had, so the USB RX FIFO keeps being drained while a large
  // CONFIG_VALIDATE is parsed. The stash OWNS a bounded payload copy
  // (G2-R3-01): a shallow Frame copy would alias the parser's decoded
  // buffer, which later frames (including bad-CRC ones) rewrite. The
  // full-slot policy lives in DeferredRequest (idempotent resend may
  // overwrite; a different request is dropped loudly and counted).
  DeferredRequest deferred_;
  void *rssi_task_{nullptr};  // TaskHandle_t
  portMUX_TYPE wifi_cache_mux_ = portMUX_INITIALIZER_UNLOCKED;
  char live_ssid_[33]{};
  char live_ip_[40]{};
  volatile int live_rssi_{0};
  volatile bool have_rssi_{false};
  char wanted_ssid_[33]{};
  char saved_ssid_[33]{};
  char saved_pass_[65]{};
  bool in_log_{false};
};

}  // namespace mmwave_host
}  // namespace esphome
