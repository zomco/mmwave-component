# MWCP/1 design differences awaiting review

Status: **待评审.** None of these items is a private wire-format change. The protocol is not frozen.

| ID | Clause | Evidence | Impact | Minimal proposal |
| --- | --- | --- | --- | --- |
| DD-01 | Installer `closed` means release | esp-web-tools 10.4.0 `src/connect.ts` calls `port.close()` without `await`. `install-dialog.ts` reopens the port and calls `_initialize(true)` unless `new_install_improv_wait_time` is 0. No public method returns the close promise. | Both console and installer can believe they own the port. | WP-3 should own `navigator.serial.requestPort()` / `port.open()` / `await port.close()`. User closes the installer, then clicks connect. Success of our own `await port.open()` is the only release proof. Set manifest `new_install_improv_wait_time: 0` so the new firmware is not stuck in Improv. Do not patch `navigator.serial`, shadow DOM, or `node_modules`. |
| DD-02 | Locked ESPHome/ESP-IDF | CI uses `esphome/build-action@v7` with default `version: latest`. Publish requires an exact version only at dispatch time. No version is stored in this tree. | G0 driver and logger results cannot be pinned. | Record the exact ESPHome and IDF versions on the first authorized build. Do not claim a lock now. |
| DD-03 | One USB owner | Production `esphome-config/common/base.yaml` sets `logger.hardware_uart: USB_SERIAL_JTAG`. `tests/common/_device.yaml` enables `improv_serial` on that same port. Most test YAMLs leave `logger:` bare. `reboot_timeout` is unset. | Source predicts a second USB consumer and an offline reboot. Not measured. | Host profile must remove stock Improv Serial, stop plaintext logger output, and set Wi-Fi/API `reboot_timeout: 0s`. Keep old profiles unlabeled as MWCP. |
| DD-04 | Polygon capacity | `g_polygon.max_restore_data_length` is 254. Measured: 21 points of `-2000,-2000` fit in 251 bytes; the 22nd does not. A 64-point JSON commit of the same points is 1001 bytes, under 4096. | Current globals cannot store the draft maximum. Truncation would violate the protocol. | Keep schema max 64 until review. WP-2 must use a new snapshot store, not the 254-byte global. |
| DD-05 | Polygon validation | Firmware skips malformed points and does not test self-intersection. The draft rejects the whole transaction. | HA text entry and MWCP would disagree if WP-2 only wraps the current parser. | Simulator and schema follow the draft. Do not change firmware in this phase. |
| DD-06 | Speed placeholder | `publish_target_frame_` writes speed `0` because the module does not report speed. | Exporting 0 would invent a measurement. | Capability `speed.cm_s.supported` is false. Telemetry uses null. |
| DD-07 | Intervals | README says position/distance every 2 s. Firmware throttles position publish to 1000 ms and clears presence after 1000 ms without UART bytes. Draft 2000/6000 was not measured. | A stale timer based on the draft could mark live data stale, or the reverse. | Fixture uses `expected_interval_ms: null` until hardware. |
| DD-08 | Install ranges | Number entities: x/y -2000..2000 step 1, z 50..400 step 1, yaw -180..180 step 0.1, pitch/roll -90..90 step 0.5. CONFIG_SCHEMA allows any positive `radar_z`. | Web and HA could accept different heights. | Descriptor uses the number-entity range. Review before widening. |
| DD-09 | Bad JSON after a valid CRC | Draft parse order reaches JSON before command-body errors, but also says only a valid envelope with a bad command returns an error. | One side might answer `INVALID_ARGUMENT`; the other might only count a codec error. | Both codecs reject the frame and do not execute. No application response. Review if a response is required. |
| DD-10 | String limits | JSON Schema `maxLength` counts characters. The draft limits UTF-8 bytes. | A Chinese SSID can pass `maxLength` and exceed the byte limit. | Schema annotation `x-maxUtf8Bytes`. Not a wire change. |
| DD-11 | Edge points | Existing ray cast marks square points `(50,0)` and `(0,0)` inside and `(150,10)` outside. | Changing the predicate would move HA and web boundaries. | Freeze the current result. Do not "correct" it here. |
| DD-12 | Console open buffer | Draft says 16384. esp-web-tools 10.4.0 opens with 8192. | Different buffers are acceptable if documented. | Do not change the installer. Console open, when implemented, should use the draft 16384 unless review says otherwise. |
| DD-13 | Equivalent JSON keys | Resolved in this remediation. Both sides now reject `{"a":1,"\u0061":2}` after decoding escapes. | Was a real split. | Keep the decoded-key rule. Not optional. |
| DD-14 | Integral numbers with exponents | `9007199254740993e0` and `9007199254740993.0` are integers outside `±(2^53-1)`. Non-integral finite numbers such as `1.5` stay allowed. | Using `Number()` would hide the overflow. | Clarification of the existing safe-integer rule, implemented on both sides. 待评审 only as confirmation. |
| DD-15 | Unknown response fields | Draft says unknown response fields may be ignored and unknown request fields must be rejected. Response/event schemas now set `x-open-object`. Requests stay closed. | A future minor field must not break the client. | Confirm this reading. Requests are still rejected. |

`AUTH_REQUIRED` is not a v1 code. R60 local Z is `diagnostics.local_z`, not a 3D product. `inject_mock_data` is not an MWCP action.

## G0 preparation dispositions

These items are not resolved. G0 hardware remains not_run.

| ID | Suggestion | This round |
| --- | --- | --- |
| DD-01 | The diagnostic page connects only after a user click. Its own `port.open()` success is the handoff evidence. A future manifest should set `new_install_improv_wait_time: 0`. Do not patch `node_modules`. | Not run on hardware |
| DD-02 | The first authorized `esphome compile` must record exact ESPHome/IDF versions. Do not claim a lock now. | ESPHome is not installed here; compile is not_run |
| DD-03 | The host YAML removes Improv, sets logger `baud_rate: 0`, and sets Wi-Fi/API `reboot_timeout: 0s`. Old profiles are not labeled MWCP. | Config written; not flashed or driver-tested |
| DD-07 | Reporting intervals stay `expected_interval_ms: null` until hardware counts exist. | Not measured |
