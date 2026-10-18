#include "mmwave_host.h"

#include "r60abd1.h"

#include "esphome/components/logger/logger.h"
#include "esphome/core/log.h"

#include "driver/usb_serial_jtag.h"
#include "esp_heap_caps.h"
#include "esp_mac.h"
#include "esp_random.h"
#include "esp_system.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

namespace esphome {
namespace mmwave_host {
namespace {

static_assert(sizeof(StackType_t) == 1, "ESP-IDF RISC-V high-water mark is not bytes");

const char *reset_reason_name(esp_reset_reason_t reason) {
  switch (reason) {
    case ESP_RST_POWERON:
      return "power_on";
    case ESP_RST_EXT:
      return "external";
    case ESP_RST_SW:
      return "software";
    case ESP_RST_PANIC:
      return "panic";
    case ESP_RST_INT_WDT:
      return "int_wdt";
    case ESP_RST_TASK_WDT:
      return "task_wdt";
    case ESP_RST_WDT:
      return "wdt";
    case ESP_RST_DEEPSLEEP:
      return "deep_sleep";
    case ESP_RST_BROWNOUT:
      return "brownout";
    case ESP_RST_SDIO:
      return "sdio";
    default:
      return "unknown";
  }
}

}  // namespace

void MwcpHost::setup() {
  G0BootEntropy entropy{};
  esp_read_mac(entropy.mac, ESP_MAC_WIFI_STA);
  entropy.r0 = esp_random();
  entropy.r1 = esp_random();
  entropy.r2 = static_cast<uint16_t>(esp_random());
  link_.set_boot(entropy);
  reset_reason_ = reset_reason_name(esp_reset_reason());
  usb_serial_jtag_driver_config_t cfg = {};
  cfg.rx_buffer_size = 1024;
  cfg.tx_buffer_size = 1024;
  const esp_err_t err = usb_serial_jtag_driver_install(&cfg);
  usb_install_err_ = static_cast<int>(err);
  usb_exclusive_ = err == ESP_OK;
  usb_shared_ = err == ESP_ERR_INVALID_STATE;
  if (logger::global_logger != nullptr) {
    logger::global_logger->add_log_callback(this, [](void *self, uint8_t, const char *, const char *, size_t) {
      auto *host = static_cast<MwcpHost *>(self);
      if (host->link_.encoding || host->link_.tx.active) {
        host->link_.logs_dropped++;
        return;
      }
      host->link_.logs_seen++;
    });
  }
}

void MwcpHost::loop() {
  const int64_t started = esp_timer_get_time();
  const uint32_t now = millis();
  link_.poll_session(now);
  if (usb_exclusive_) {
    uint8_t buf[128];
    const int n = usb_serial_jtag_read_bytes(buf, sizeof(buf), 0);
    if (n > 0) {
      link_.parser.push(buf, static_cast<size_t>(n), now, [](const mwcp::Frame &frame, void *user) {
        static_cast<MwcpHost *>(user)->on_frame_(frame);
      }, [](mwcp::Status status, void *user) {
        static_cast<MwcpHost *>(user)->note_error_(status);
      }, this);
    }
    link_.parser.poll(now, [](mwcp::Status status, void *user) {
      static_cast<MwcpHost *>(user)->note_error_(status);
    }, this);
    link_.tx.pump([](const uint8_t *data, size_t want) {
      return usb_serial_jtag_write_bytes(data, want, 0);
    }, now);
  }
  free_heap_ = esp_get_free_heap_size();
  min_heap_ = esp_get_minimum_free_heap_size();
  largest_block_ = heap_caps_get_largest_free_block(MALLOC_CAP_8BIT);
  stack_high_water_ = uxTaskGetStackHighWaterMark(nullptr);
  const int64_t elapsed = esp_timer_get_time() - started;
  if (elapsed > max_loop_us_) max_loop_us_ = elapsed;
}

void MwcpHost::on_frame_(const mwcp::Frame &frame) {
  link_.rx_frames++;
  if (frame.kind != 1) return;
  const uint32_t now = millis();
  if (frame.code == 0x0001) {
    char nonce[33];
    if (!G0Link::read_nonce(frame.payload, frame.payload_length, nonce)) {
      link_.invalid_requests++;
      return;
    }
    link_.accept_hello(nonce, frame.request_id, now);
    return;
  }
  if (frame.code == 0x0002) {
    link_.accept_ping(frame.request_id, frame.session_id, now);
    return;
  }
  if (frame.code == 0x0012) {
    link_.accept_status(frame.request_id, frame.session_id, now, meter_());
    return;
  }
  link_.invalid_requests++;
}

void MwcpHost::note_error_(mwcp::Status status) { link_.note_rx(status); }

G0Meter MwcpHost::meter_() const {
  G0Meter meter;
  meter.uptime_ms = millis();
  meter.free_heap = free_heap_;
  meter.min_free_heap = min_heap_;
  meter.largest_free_block = largest_block_;
  meter.stack_high_water_bytes = stack_high_water_;
  meter.max_loop_us = static_cast<uint32_t>(max_loop_us_ > 0xffffffffLL ? 0xffffffffLL : max_loop_us_);
  meter.reset_reason = reset_reason_;
  meter.usb_exclusive = usb_exclusive_;
  meter.usb_install_err = usb_install_err_;
  if (!radar_) {
    meter.radar_link = "unknown";
    return meter;
  }
  meter.radar_known = true;
  const R60ProbeStats stats = radar_->probe_stats();
  meter.radar_frames = stats.valid_frames;
  meter.radar_errors = stats.parse_errors;
  meter.radar_targets = stats.target_observations;
  if (stats.valid_frames > 0) {
    meter.radar_frame_known = true;
    meter.last_radar_frame_ms = stats.last_valid_frame_ms;
    meter.radar_link = stats.link_stale(millis(), 2000) ? "stale" : "healthy";
  } else {
    meter.radar_link = "waiting";
  }
  return meter;
}

}  // namespace mmwave_host
}  // namespace esphome
