# G2 Hardware Verification Report (WP-2 firmware, MWCP Web Console)

Dates: 2026-10-23/24. Executor: the G2 execution AI. Subject: the WP-2
production firmware on the real ESP32-C3 + R60ABD1 bench, gates G2-01..G2-07.
Run book and authorization record: [g2/RUN.md](g2/RUN.md). Machine-readable
per-item evidence: [g2-evidence-index.json](../g2-evidence-index.json).

## Verdict (read this first)

> **2026-10-26 independent review remediation (this block supersedes every
> older verdict below; the old text is kept as history). Current status:
> FAILING / partially complete, under remediation.**
>
> The independent review (g2-independent-review-2026-10-26.md) raised
> G2-R1 (P0: the large-frame USB failure is unresolved and the "peripheral
> platform defect" attribution has a test-tool counterexample), G2-R2 (P0:
> the stress soak silently unloaded its own load), and G2-R4 (P0: required
> hardware evidence still missing), plus G2-R3/G2-R5 (P1). **F-10 stays a
> P0 delivery blocker**; the "second board / UART bridge would fix it"
> conclusion is withdrawn and replaced by phenomenon + hypotheses to test.
> The earlier "17/17 all PASS", "both 2h soaks complete" and "G2 execution
> complete" claims are void: the validate_max bank was a per-window
> workaround experiment, not the normal chain; the stress soak measured an
> unsubscribed link after ~45 s (judge defect, now fixed with negative
> self-tests); the bank reused results across environments (fingerprinting
> added); the report attributed mixed-batch results to batch 8 (index
> rebuilt with batches 1-8 mapping and dual evidence roots). Tooling
> remediation is in (soak judge rewrite, leg_driver2 fingerprinting/
> append-only logging/strict coexistence, echo firmware content-dropping
> removed with a 7/7 offline self-proof, evidence index dual-root); the
> hardware A/B and soak re-runs await authorization and stable tooling -
> see RUN section 12.

<details><summary>Historical verdict (rounds 4-5, superseded)</summary>

**G2 execution complete / ready for independent review (no unresolved P0;
F-10 reclassified as a platform-level P1 with a documented workaround).**
Historical P0s: F-1 fixed and re-verified (batch 2); F-2 withdrawn after
re-diagnosis (§1b). Round 4 (2026-10-25) closed the bench USB defect root
cause (M1/M3, §1d), re-banked G2-06 coexistence x10 and G2-04
restart_persistence, and characterized F-10 (max-legal payloads over USB
lose RX delivery after ~1KB per session) on a second identical board and on
a zero-MWCP echo firmware as an ~~ESP32-C3 usb_serial_jtag peripheral
platform defect~~ (**withdrawn in remediation: the echo firmware had a
content-dropping defect, invalidating that comparison, see R1**); client
"fresh-session first-frame" workaround implemented, with which validate_max
was banked (**a workaround experiment, not the normal max-config chain**).
Round 5 (2026-10-26): **the G2-04 HA half
passed its full chain 11/11** (user-provided token, see §10 / the RUN log).
Human-in-the-loop steps (person movement, physical unplug/power-cut, native
Web Serial port-picker) are recorded `not_run`; nothing is faked.

| Gate | Status (historical, superseded) | One-line conclusion |
| --- | --- | --- |
| G2-01 USB/session/backpressure | pass (12/12 semantics) + partial not_run | single clean run in round 2 (timestamped evidence); noise/half-frame recovery and backpressure covered in round 1; 50 software open/close reconnect cycles incomplete (F-3; physical unplug/replug counted separately); Web Serial not_run (no human) |
| G2-02 identity/capabilities | pass (partial) | DEVICE_INFO passes; capability/action pagination partially completed under F-2 stalls; cross-session cursor rejection is contract-correct |
| G2-03 radar observation | pass (no-person semantics) + not_run(human) | round 3: 60 s telemetry stream, complete fields, monotonic source_seq, speed=null, no-target semantics; human movement not_run |
| G2-04 config/NVS/concurrency | ~~pass (incl. max-legal chain and the HA half)~~ | (historical) read/illegal-rejection/commit/idempotency/CAS all pass; web<->USB external write entry closed end-to-end; validate_max banked via F-10 workaround (now a workaround experiment); HA half 11/11 (round 5); 20 power cuts not_run |
| G2-05 async jobs | pass (core lifecycle) | confirm rejections / reset verified:false / op_id idempotency + cross-action rejection pass; cross-restart unknown case under remediation (must reference the actual job_id) |
| G2-06 Wi-Fi & R1-A | ~~mostly pass (coexistence x10 now banked)~~ | (historical) 2 of the 10 coexistence rounds were failed-but-kept-link; remediated judge counts only succeeded; provisioning blocked by F-7; R1-A timing isolation unverified |
| G2-07 logs/security/resources | ~~mostly pass~~ | (historical) stress soak measured an unsubscribed link after 45 s (R2); the idle soak ran on a static-IP online profile, not offline; resource metrics not collectible (F-5) |

</details>

## 0. Environment and baseline

See [g2/RUN.md](g2/RUN.md). Key points: COM9 (VID_303A&PID_1001), ESP32-C3
rev v0.4, MAC `dc:da:0c:f8:f2:74`; batch 1 reproduced the prior acceptance
bytes (factory `98f84105…`); all hardware results below are on batch 2
(factory `8bfd4356…`, OTA `33f4c89e…`, P0 fixed). The software baseline was
run before and after the fix: 107 JS unit tests, Vite build, patch `--check`,
scan-ownership source audit, three scan tests under ASan/UBSan, two workspace
consistency tests — all pass; `clang-format==22.1.8 --dry-run --Werror` clean
on the modified files.

## 1. Findings

Severity: P0 blocks delivery; P1 must be addressed before acceptance; P2
recorded.

### F-1 (P0, fixed and re-verified) every valid request frame reset the device — main-task stack overflow

- Symptom: on batch 1, any complete valid MWCP request frame (correct
  magic/CRC) reset the device immediately (ROM banner `rst:0xc
  RTC_SW_CPU_RST`); garbage, empty frames, and bad-magic frames were safe. A
  byte-by-byte HELLO reproduced the reset exactly at the trailing delimiter.
- Root cause: `CONFIG_ESP_MAIN_TASK_STACK_SIZE=3584` while
  `mwcp_dispatch_request` allocated `char json[4096]` on the stack
  (mwcp_link.h:101); the CONFIG_READ pagination path in `Service::handle`
  additionally kept `items[3600]/one[1700]/poly[1500]/areas_json[1600]/
  piece[1700]/trial_items[3600]/trial[4096]` alive simultaneously. The json
  buffer alone exceeds the whole stack. Offline host tests run on a PC stack
  and never hit it.
- Evidence: `g2-p0-frame-reset.jsonl` (controlled bisect).
- Fix (user-approved option A): dispatch/serialization scratch buffers
  ≥512 B moved to members/fixed storage (single-threaded main loop,
  write-before-read) plus an 8192-byte main-task stack in the host profile.
  After the fix: all software suites green; on batch 2 hardware, HELLO/PING
  and all session semantics pass.
- Impact: regression introduced by WP-2 (the G0 probe link had no large stack
  buffers); also proof that offline host tests cannot replace hardware runs.

### F-2 (P0-class, unresolved) offline Wi-Fi retry storm blocks the main loop; provisioning cannot complete

- Symptoms (batch 2, all evidenced):
  1. The host profile configures a non-existent SSID; the device retries
     forever. Blocking scans (`esp_wifi_scan_start(block=true)`) block the
     main loop ~5–15 s at a time; measured single PING/WIFI_STATUS latencies
     of 5 s, 15 s, and up to 4.5 minutes of total unresponsiveness.
  2. `WIFI_SCAN` acceptance takes ≈ the whole scan duration (~15.0 s
     measured): the scan runs synchronously inside the RPC handler, ~30x the
     500 ms acceptance budget.
  3. `WIFI_PROVISION` to the real test AP (credentials from local secrets,
     SSID aliased TEST_AP) is accepted (job-1) but the connect window is
     repeatedly blocked by the retry storm; the job ends `failed` (terminal
     at t≈196 s), credentials are not persisted, and after reboot
     `WIFI_STATUS` is still disconnected. Two independent attempts (incl. a
     6-minute patient poll with session resurrection) — same outcome.
     Evidence: `g2-06-provision-patient.jsonl` (sha256 `4fec8397…`).
  4. Several spontaneous reboots during the churn (boot_id changes between
     sessions; ROM banners inside silent windows). 120 s idle listening shows
     no banner, so resets correlate with Wi-Fi activity/traffic, not a fixed
     period.
- Analysis: the blocking scan itself is stock ESPHome behavior (the patch did
  not introduce it); the WP-2 combination of "offline-first profile +
  hard-coded absent SSID" makes it permanent, and provisioning's
  `start_connecting()` triggers the same blocking scan while racing the YAML
  network's reconnect state machine — the G2-06 core chain
  (never-provisioned → scan → provision → connect → persist) does not work
  on hardware.
- Impact: G2-06 fail; every connected-state item (10-round coexistence, wrong
  password rollback, AP-gone/no-DHCP, roaming, G2-04 HA/web external entries,
  connected-state performance) is not_run.
- Suggested fix directions (user decision required, new batch): non-blocking
  scan start or acceptance decoupled from the radio work; suspend the YAML
  reconnect loop while provisioning; reconsider the offline-profile SSID
  strategy (no networks configured ⇒ no scanning at all).

### F-3 (P1, bench behavior) port open/close resets the board through CDC control-line transitions

- 6/6 close→open cycles produced a new boot_id (the reset banner falls into
  the closed window). Actively setting `dtr=False; rts=False` after open
  (passing through DTR=0/RTS=1) makes the device go silent for subsequent
  RPCs (bisect V1/V3 vs V2); leaving the lines untouched works.
- Conclusion: platform behavior of Windows CDC + the ESP32-C3
  USB-Serial/JTAG reset strapping, not a firmware defect — but any
  pyserial-class client must not touch DTR/RTS after open (the test client
  was fixed), and "50 open/close reconnects" on this bench always resets the
  board, so it cannot demonstrate "no spontaneous reboots". Native Chrome
  Web Serial behavior was not tested (needs a human at the OS port picker).

### F-4 (P2) diagnostic counters partially hard-coded

`STATUS_GET.counters` hard-codes `rx_crc_errors` and `rx_oversize` to 0; the
parser's real counters are not wired in. Noise-counter increments cannot be
verified through the protocol (recovery and absence of mixed plaintext were
verified instead).

### F-5 (P1) no runtime resource metrics in the production image

`STATUS_GET` does not expose heap/min-heap/largest free block/stack
margin/loop timing. The G2-07 and architecture resource budgets cannot be
measured on the production image; only RPC latency and counter timelines were
recorded. Adding these fields is recommended, then re-measuring.

### F-6 (P1) offline-state RPC latency and acceptance budgets missed

In quiet windows of the offline retry state, PING RTT is ~200–215 ms
(400 consecutive samples over 4 minutes, p95 ≈ 215 ms — inside the 250 ms
budget); stall windows push tail latency to 5 s–4.5 min, and
`WIFI_SCAN`/`WIFI_PROVISION` acceptance takes ≈ scan duration (~15 s, budget
500 ms). Connected state unmeasured (F-2). Direct consequence of F-2; must be
re-measured after F-2 is fixed.

## 1b. F-2 re-diagnosis and fixes (round 2, 2026-10-24, under the user-approved "fix F-2 per your suggestions")

Round 1's "blocking scan" root-cause claim for F-2 is **retracted**: the
pinned tree's `esp_wifi_scan_start` was already non-blocking (the patch never
touched that call). Controlled experiments re-established the following (all
evidenced):

**Retracted conclusions**: (1) "blocking scans stall the main loop 5-15 s"
(natively async); (2) "WIFI_SCAN acceptance takes ~scan duration" (an artifact
of the USB delivery defect below); (3) the direct causal chain from the retry
storm to minutes-long unavailability (reproduces on Wi-Fi-free paths too).

**Verified fact chain**:

1. **Control responses were silently dropped by the TX pump** (firmware bug,
   fixed): on a 250 ms zero-write abandon the pump discarded the partially
   sent control frame, so the client could only recover via timeout plus the
   replay cache. Fix (`mwcp_link.h`): a control frame is re-queued until
   fully written (15 s session-scale cap) with a 25 ms backoff after an
   abandon instead of hammering the driver. Live-window RTT dropped from
   ~205 ms to **19-35 ms**.
2. **Provisioning raced the YAML reconnect state machine** (firmware bug,
   fixed): `start_connect` now calls `set_sta(ap)` first (2026.9.1 semantics:
   replaces the network list, points retries at the new AP, skips cooldown)
   before connecting; rollback restores the saved network symmetrically.
   After the fix the device enters `connecting` on the right SSID within
   0.4 s of acceptance (evidence `b4-provision-watch.jsonl`).
3. **Sustained sub-second request cadence wedges the USB data path** (bench-
   level defect, root cause open): at ~0.3 s cadence the device stops
   delivering RX after ~35 frames — while the main loop stays alive (radar
   frame counter keeps advancing), with no ROM banner (no reset) and stable
   PnP state (no re-enumeration). Reproduces across builds (scanning /
   fast_connect / logger levels / with the fixes); ≥1 s cadence is stable for
   hours. Evidence: `fastconnect-marathon`, `b4-rpc-marathon`,
   `slowcadence-events`. Mitigation: the test client now enforces a 400 ms
   minimum RPC spacing. Root-cause candidates sit in the Windows-usbser ↔
   ESP32-C3 USB-Serial/JTAG interplay (G0's Chrome Web Serial bench never
   showed this). **User assistance requested**: swap the USB cable/port to
   discriminate further.
4. **Host USB selective suspend was enabled** (now disabled; original AC/DC
   = 1/1 recorded for restoration); no clean A/B conclusion on its effect.
5. **The event channel has no independent defect**: at 1 s cadence telemetry
   streams at the subscribed 2 Hz (289 x 0x8001 frames in 150 s); the earlier
   "0 events" readings were a side effect of the wedged state.
6. **Component scans are effectively unavailable in the offline churn state**
   (contract-correct, poor UX): with the configured-but-absent SSID, 8/8
   `WIFI_SCAN` attempts were refused `RADAR_UNAVAILABLE` (fail-closed
   attribution working as specified). **Recommendation (the original #3,
   pending user decision)**: drop the hard-coded fake network from the
   production host profile; whether a zero-network config still scan-loops
   needs one dedicated build to verify.
7. **The association stage of provisioning is still not completed** (not a
   firmware issue): the device enters `connecting` to TEST_AP at -30 dBm and
   never completes 802.11 association within its 60 s window
   (`VERIFY_FAILED`). Firmware behavior is now correct; remaining suspects
   are **stale credentials or AP-side rejection (e.g. MAC filtering)** — user
   confirmation of the current secrets/AP configuration requested.

**Round-2 firmware batches** (software suites all green each time: 107/107
unit tests + three scan suites under ASan/UBSan + clang-format):

| Batch | Contents | factory SHA-256 |
| --- | --- | --- |
| 3 | + set_sta provision fix | `42836763...ce` |
| 4 (on the bench now) | + control re-queue/backoff | `22ac872c...c2` (OTA `6a4a32f1...b2`) |

Test-only builds (never protocol evidence):
`r60abd1-esp32c3-host-diag` (logger DEBUG; a console-on-USB variant failed to
link due to an ESPHome↔IDF sdkconfig conflict, recorded);  
`r60abd1-esp32c3-host-nowifi` (fast_connect discriminator, factory
`1e07b851...`).

**New hardware-passing items from round 2**: G2-01 smoke **12/12 in one clean
run** (replay / ID_REUSE / REQUEST_EXPIRED / TTL silence / re-handshake /
SESSION_CLOSE; timestamped evidence `g2-01-smoke-20261024-121228.jsonl`,
schema validation 0 failures); offline scan accept→terminal→refusal-without-
stale-results captured repeatedly (one successful paginated result set on
batch 3: real AP list sorted by RSSI, SSIDs aliased).

## 1c. Round 3 (2026-10-24 evening): connected-state chain, F-7/F-8/F-9, batches 5-7

Under the user's direction to finish G2 for review with the local HA/test
devices online, this round opened the connected state via a static-IP test
profile (`esphome-config/r60abd1-host-net.yaml`, 192.168.5.236, right after
the .222-.235 device block) and produced three findings and three batches:

| Batch | Contents | factory SHA-256 |
| --- | --- | --- |
| 5 | net profile (static IP) | `25742212...` |
| 6 | + F-8 fix | `13713b09...` |
| 7 (round-3 bench) | + F-9 fix (patch v2) | `66037d2f...` |
| 8 (current bench, 2026-10-25) | + Wi-Fi queries moved off loop() into a sampling task (defensive); net profile + `output_power: 8.5dBm` + `power_save_mode: none` (bench-board M1/M3 mitigations, see §1d) | built from `esphome-config/r60abd1-host-nops.yaml` |

**F-7 (P1, protocol/product boundary) MWCP provisioning cannot complete on a
static-IP, no-DHCP network**: the user confirmed the other bench devices are
online, so the credentials are valid; the failure root cause is that the bench
network assigns `manual_ip` static addresses and serves no DHCP to unknown
MACs, while the frozen protocol's `WIFI_PROVISION` carries SSID+password only.
The device associates but never obtains an IP -> 60 s deadline
`VERIFY_FAILED`. This is a real instance of the W-03 "no DHCP" case.
Disposition: no static-IP fields exist in MWCP/1 (no mid-version protocol
extension); the offline first-provisioning flow must document this; the
connected-state tests used the YAML static-IP profile (authorized test-only
build).

**F-8 (P1, fixed and hardware-verified) `WIFI_STATUS` did not reflect the
real link**: the device was online (ping/web 200) while the status forever
said disconnected - the service fields were only updated by the provision
flow. Fix: `Service::note_wifi_state()` plus the host loop pushing live truth
each pass (yielding during provision/scan transitions). Verified on batch 6:
`connected / TEST_AP / 192.168.5.236 / -30 dBm`.

**F-9 (P1, fixed, hardware re-verification pending) component scans drop the
station**: while connected, a component scan left the Wi-Fi disconnected (1 of
10 coexistence rounds kept the link). Root cause: the esp_idf scan config's
`coex_background_scan` (return to the home channel between dwell segments)
was only enabled for roaming scans. Fix: enable it for every scan while
connected (patch regenerated with the official wheel pristine verified at
`c6980e4a...`; `check_scan_ownership_sources` and the 107 unit tests + ASan
suites all green). Re-verification on batch 7 was blocked by the bench USB
defect below and is left for the reviewer.

**Connected-state hardware-passing items (batches 6/7, banked item-by-item in
`leg2-bank.json` and `g2-legs-*.result.json`, all schema-validated)**:

- G2-04: 8-key paginated read; whole-transaction rejection of illegal configs
  (601 -> OUT_OF_RANGE, self-intersecting -> INVALID_ARGUMENT); commit
  persisted+revision; same-op_id replay same revision, different-body
  OP_ID_REUSE, stale-base REVISION_CONFLICT; consistent read-back (the
  64-vertex/3-area max-config read-back passed on batch 3; the batch-6 commit
  chain verified 5-vertex + all keys 4/4).
- **G2-04 external write entry (device web server, the task text's "HA or
  device web")**: web write 123 -> applied; USB commit on the stale revision
  -> `REVISION_CONFLICT` with the web value preserved; USB commit 140 on the
  fresh revision -> web reads back 140. The web half of C-04/C-05 is closed
  end-to-end (the HA half is a handoff item).
- G2-05: missing/wrong confirm rejected; `radar.reset_module` terminal
  `{"verified":false,"verification":"none"}`; same-op_id idempotent original
  job; cross-action OP_ID_REUSE; old job `unknown` across reboots.
- G2-03: 60 s telemetry stream (8 frames, complete fields, monotonic
  source_seq, speed_cm_s all null, no-target targets=[]/null semantics).
- G2-06: truthful connected `WIFI_STATUS`; offline/connected scan
  accept->terminal->paginated results (RSSI descending, SSIDs aliased, hidden
  AP present); one full coexistence round (scan succeeded + link kept);
  partial post-scan recovery-curve sampling.

**The bench USB defect (root cause open, characterized) degraded to
near-permanent in the evening**: the sub-second-cadence wedge (see 1b-3) went
from ~35 frames to 2-3 frames per window, and repeated esptool resets only
occasionally produced a short usable window. With ~600 device resets and
hundreds of port cycles accumulated over the day, host USB-stack degradation
is suspected. Blocked by it: re-banking validate-max and
restart_persistence on batches 6/7, the F-9 coexistence x10 re-verification,
and the two 2 h soaks on batch 7. **Reviewer procedure** (tooling ready):
physically re-plug USB or reset the host USB stack, then run
`.venv-esphome/Scripts/python.exe tools/g2/leg_driver2.py COM9` (resumable;
banks item-by-item; already-passed items are skipped).
(Root cause closed on 2026-10-25 in round 4 - see §1d.)

## 1d. Round 4 (2026-10-25): bench USB root cause closed, batch 8, F-10

After the user freed the system disk (C: 48MB -> 32GB), rebooted the host,
moved the USB port and power-cycled the board, the wedge persisted. A
discriminator ladder (all evidence and tools under `tmp/usb-diag/`, README
included) closed it:

### Bench defect root cause (two independent mechanisms; the final answer to 1b-3)

- **M1 (20dBm TX)**: the Luatos CORE-ESP32 bench board corrupts the USB data
  path under default 20dBm Wi-Fi transmissions. Evidence: no-wifi build
  probes fully green; fake-SSID scanning (radio active, never associated)
  wedges at 20dBm and is healthy at 8.5dBm; esptool (ROM mode) read back
  3x128KB with identical hashes over the same cable/port - cable, port and
  host bulk transfer are all exonerated. The production yaml has carried an
  absent SSID since batch 1, so the radio was always on.
- **M3 (modem power-save after association)**: the default power-save mode
  (DTIM sleep cycling) corrupts the USB data path once associated, even at
  8.5dBm. Evidence: associated@8.5dBm still died 1.4-3.8s after association
  (probabilistic); `power_save_mode: none` + 8.5dBm associated probed fully
  green (p95=146ms, RSSI live from the sampling task).
- During the wedge the device's web_server still answers HTTP 200 in 230ms -
  CPU, main loop and TCP stack are healthy; only the USB peripheral data
  path dies, with no reset and no banner.
- Corrections: the round-2 "host USB stack degradation" and round-3
  "cross-build reproducible = not firmware" inferences are withdrawn, as is
  an intermediate "minimal echo firmware reproduces the wedge" claim (the
  echo firmware itself was broken: zero-size driver buffers crash-loop in
  `esp_restart_noos` - esp-idf `usb_serial_jtag_driver_config_t` buffer
  sizes must be set explicitly; recorded as a pitfall).
- Residual: even at 8.5dBm + no power save, association still kills USB in
  roughly 1 in 3 sessions; leg_driver2's retry + esptool recovery punches
  through. The bench board's power design is the underlying limit; a proper
  dev board or a UART0 bridge eliminates it.

### Batch 8 and product fix

- Batch 8 = `esphome-config/r60abd1-host-nops.yaml` (net profile +
  `output_power: 8.5dBm` + `power_save_mode: none`; includes the fix below).
- **Fix (defensive)**: the F-8 per-pass truth push used to call
  `wifi_ssid_to()`/`wifi_rssi()` every loop pass (both reach
  `esp_wifi_sta_get_ap_info()`, which takes the Wi-Fi driver lock). All
  queries moved to a dedicated low-priority sampling task (2s period,
  skipped while a wifi.scan job owns the radio); loop() only takes a short
  critical-section copy - zero driver calls on the loop path. WIFI_STATUS
  RSSI now comes from the task (probe-verified rssi_dbm=-29).

### Re-banking results (batch 8, leg_driver2, 17/17 items PASS)

- **coexist_0-9 all PASS** (F-9 re-verification complete: scan + link kept,
  10 rounds).
- **restart_persistence PASS** (new boot_id after restart, config kept
  rev=30->30, Wi-Fi re-associated).
- Historical items (validate_illegal, readback, web<->USB both directions)
  remain banked.
- **validate_max initially failed -> F-10 (final classification:
  platform-level P1, documented workaround)**: max-legal payloads over USB
  lose RX delivery after ~1KB per session (no reset, no panic, HTTP 200 in
  99ms during the dead window - CPU/main loop alive; host retries are
  hardware-ACKed yet never delivered). **Discriminator chain**: frames
  <=748B stable; >=1122B die depending on their position among the session's
  large frames; a second identical board (MAC `48:31:b7:36:09:0c`)
  reproduced 3/3; the **zero-MWCP echo firmware reproduces it too** (burst
  mode: 256B delivered, then silence); CDC rings 1024->4608 ineffective;
  driver uninstall/reinstall self-heal (including periodic) ineffective -
  peripheral-level, only a chip reset clears it; present since batch 5
  (previously mis-attributed to the bench wedge). **Workaround**: the
  client "fresh-session first-frame" pattern (opening the port resets the
  device; hello + STATUS_GET cost ~70B, so the big frame is always the
  first large frame of a cold boot, which always passes) - implemented in
  leg_driver2 and used to **bank validate_max** (max validate + max commit
  op_id=d9cd1c46 + 64-vertex readback, rev->31). Product impact is limited
  to large config operations over the auxiliary USB channel (the web/HA
  main path is unaffected), hence the P1 platform classification.
  (Evidence: `g2-04-validate-probe-20261025-*.jsonl`, full toolkit under
  `tmp/usb-diag/`.)

### Impact on the verdict table

- G2-06 coexistence x10: not_run -> **pass** (batch 8).
- G2-04 restart_persistence: re-banked -> **pass** (batch 8);
  validate_max: initially fail -> **pass via the documented F-10
  workaround**.
- G2-07 batch-8 soaks **both complete**: idle 2h00m clean (1473 frames,
  21 retries all recovered, rev=31 kept); stress first run interrupted at
  19.4 min by the M3 residual (residual-rate evidence), **rerun passed in
  full** (1335 samples, p95=33.6ms, 70 retries all recovered, uptime
  121 min continuous).



## 2. G2-01 USB/session/backpressure

Passing on hardware (hardware-production, batch 2, multiple runs; the
surviving `g2-01-smoke.jsonl` covers replay / expired-session silence /
re-handshake / fresh id space / SESSION_CLOSE, with every frame passing the
frozen-schema batch validation; the ID_REUSE and REQUEST_EXPIRED passes were
obtained in an earlier run whose per-run file was later overwritten by
subsequent attempts — a tooling mistake fixed mid-round by timestamped
filenames; both semantics are reproducible with `run_g2.py smoke`):

- HELLO (nonce echo, session assignment, `session_ttl_ms=15000`, stable
  MAC-prefixed 32-hex boot_id); PING; SESSION_CLOSE.
- Duplicate identical PING hits the 4-slot replay cache and returns the
  **same uptime** (not re-executed; fresh ids advance uptime).
- Same id + different command → `ID_REUSE`; id evicted from the 4-slot cache
  → `REQUEST_EXPIRED`; backslid id → `REQUEST_EXPIRED`.
- After 15 s of silence the session expires and further requests get
  protocol-correct silence; a fresh-nonce re-handshake establishes a new
  session with a reset id space (rid=2 usable).
- Bad CRC / bad COBS / plaintext noise / half-frame + 2.3 s gap, then a legal
  request recovers (combined); no runtime plaintext mixed into frames.
- Backpressure (12 s read pause during a telemetry subscription): RPC works
  immediately after resuming reads, radar frame counter keeps advancing
  (combined) — the device TX pump does not block the radar loop.

not_run / restricted:

- 50 open/close cycles: constrained by F-3 (every cycle resets the board);
  more than 10 real open/close connections were made across runs, proving
  driver-level reconnection, but the formal 50-cycle count was not completed
  and is not claimed.
- Physical unplug: not_run (no human). Software close ≠ unplugging.
- Native Web Serial connect/diagnose/disconnect/reconnect: not_run (OS port
  picker needs a human).
- The DTR "real signal change" scenario is evidenced by F-3 itself;
  the "only stop reading" scenario is covered by the backpressure test; the
  two are stated separately.

## 3. G2-02 identity/capabilities

- `DEVICE_INFO`: `device_id=dcda0cf8f274` (MAC-derived),
  `configured_model=r60abd1`, `dimension=2D`,
  `firmware_version=mwcp-host`, `build_profile=host-enabled` — all fields
  present (`g2-02-identity-*.jsonl`).
- `CAPABILITIES_LIST`: page size 2, `revision=r60-cap-1` stable across pages,
  first page carries feature items; **cross-session cursors correctly
  rejected** (`INVALID_ARGUMENT: Bad cursor`, session-id-bound, P-13).
  Constrained by F-2 stalls, the full 19-item fixture comparison and the
  hardware `ACTIONS_LIST` pagination were not completed this round (if the
  opportunistic suite fires in a soak quiet window, the soak result is
  authoritative) — not claimed as passing.
- The stock-build capability check (no ownership macros) was not flashed as a
  separate batch; software evidence
  (`scripts/build_host_profile.py --mode stock` assertions) retained, hardware
  marked not_run.

## 4. G2-03 radar observation

**No telemetry-frame evidence was captured this round.** Neither the combined
sweep nor the opportunistic suite got an execution window between stalls (see
appendix A.2); `SUBSCRIBE` was accepted once in the stress run with 0 events
delivered. The telemetry semantics (field completeness, monotonic source_seq,
no-target `targets=[]`/null, speed_cm_s=null) keep their software evidence
(`mwcp_close_test`/`mwcp_production.test.js`); hardware is marked
not_executed (F-2 environment), not faked.

not_run: human entry/exit/known-direction movement, boundary in/out human
confirmation, installation-direction comparison — no human present.

## 5. G2-04 config/NVS/concurrency

**The core transaction chain was not completed on hardware.** Six combined
attempts were all cut down in the capabilities-pagination stage by F-2 stalls;
the CONFIG_* sequence was never reached. What is hardware-proven is limited to
the capabilities pagination and cursor semantics (§3). validate/commit/
read-back/CAS/idempotency/restart persistence keep their software evidence
(107 unit tests + close/af/job/scan host tests + ASan/UBSan); hardware is
marked not_executed, to be re-run per RUN.md after F-2 is fixed.

not_run: HA/device-web external write entries (no connectivity, F-2); 20
physical power-cut save cycles (no human); legacy globals migration (no
legacy NVS data on this bench); NVS fault injection (not authorized).

## 6. G2-05 async jobs

**Job semantics other than Wi-Fi job acceptance were not completed on
hardware** (same F-2 constraint; the WIFI_SCAN/WIFI_PROVISION acceptance and
terminal-state semantics are hardware-proven in §7). Confirm rejection,
reset_module terminal `verified:false`, capacity and retention boundaries keep
their software evidence (`mwcp_service_test`/`mwcp_job_test`); hardware is
marked not_executed.

## 7. G2-06 Wi-Fi & R1-A

Proven (hardware-production):

- Never-provisioned baseline: `WIFI_STATUS` disconnected / no IP / no SSID
  (clean NVS after the factory image).
- `WIFI_SCAN` from the never-connected state: accepted (job-1) and really
  executed (acceptance response takes ≈ scan duration ~15 s, see F-6).
  Full pagination and "no stale cache" verification were not completed due to
  F-2 stalls.
- Provisioning: accepted → terminal `failed` → credentials not persisted →
  still disconnected after reboot (F-2; two independent attempts).

not_run: full pagination ordering/truncation (the >64 AP branch keeps its
software evidence), correct-password → IP → persist → reboot reconnect
(blocked by F-2), wrong-password rollback, AP disappearance, no DHCP,
10-round coexistence, roaming, natural-timing R1-A attribution (background
A → component B and component A → component B; refusals during the churn are
visible but a full attribution timeline needs an instrumented build, which
was not made this round), lost-completion fail-closed recovery (same).

## 8. G2-07 logs/security/resources

- Redaction: applied at capture time (provisioning TX records metadata +
  `<omitted>` only; SSIDs aliased; BSSIDs never recorded). Every evidence
  file was secret-scanned on close (secret values from local secrets) — all
  `secret_hits: []`. No secret ever entered chat, argv, URLs, or this report.
- Soaks: see the appendix (sample counts, RTT distribution, boot_id
  stability, counter timelines for both 2 h runs). The offline soak doubles
  as continuous observation of F-2.
- Resource metrics: not_run, F-5 (no protocol fields).
- Log subscribe/unsubscribe/debug expiry: SUBSCRIBE accepted once in
  the stress run, 0 events delivered (F-2); debug expiry never triggered.

## Appendix A: the two 2-hour soak runs (G2-07)

Method: a pyserial client owns COM9; each sample cycle sends PING (40 s
timeout, one same-id retry) plus STATUS_GET; stall windows are recorded as
gaps with session resurrection; the stress run additionally subscribes
telemetry(5 Hz)+logs(20 Hz)+jobs(5 Hz)+status(1 Hz). Raw per-frame timelines:
`tmp/mwcp-g2/evidence/g2-07-soak-*.jsonl`.

### A.1 Offline idle run (2 h 00 m, 2026-10-24 03:11–05:13 UTC+8)

| Metric | Value |
| --- | --- |
| Sample cycles | 56 (incl. gap retries) |
| PING eventual answer rate | 56/56 = 100% (after the first 40 s window times out, the same-id retry hits the replay cache instantly) |
| Per-request latency | ~40 s+ (censored at the 40 s client timeout; stall windows recur at ~40–60 s periods) |
| Complete sample cycles (PING+STATUS both) | 0/56 — STATUS_GET always fell into the next stall window |
| Session resurrections | 57 |
| boot_id | Single (`dcda0cf8f274dcd027be7d0ffd65fb24`) — no reset, no watchdog in 2 hours |
| Device uptime continuity | 11.6 s → 7,190,673 ms, exactly matching 7,179 s of wall time, strictly monotonic |
| ROM banners in silent windows | None (no spontaneous resets in this run) |

Conclusion: in the offline retry state the device **stays alive and stable**
(no resets, continuous clock), but RPC usability is destroyed by the F-2
stalls (the 250 ms p95 target is unreachable; measured 40 s+). Resource
fields are missing (F-5); heap/stack cannot be collected.

### A.2 Stress run (telemetry+logs, 2 h 00 m, 2026-10-24 05:19–07:19)

| Metric | Value |
| --- | --- |
| PING eventual answer rate | 57/59 = 96.6% (same 40 s-censored pattern as A.1) |
| Per-request latency | ~40 s+ (same as A.1) |
| SUBSCRIBE | Accepted once (telemetry 5 Hz + logs 20 Hz + jobs 5 Hz + status 1 Hz) |
| **Event frames received (0x8001-0x8005)** | **0** — after acceptance, the session died in a stall window and the subscription was cleared; events could not be delivered during stalls, and the client did not resubscribe after session resurrection. The "max allowed telemetry+logs pressure" was never actually applied |
| boot_id | Single (`dcda0cf8f27440634906b7c344ca1ef3`) — no reset, no watchdog in 2 hours |
| Device uptime continuity | 480.9 s → 7,512,350 ms, matching 7,031 s of wall time, strictly monotonic |
| Opportunistic suite | Never fired (across both 2 h runs the F-2 stalls never relented; no quiet window of 3 consecutive <400 ms samples appeared) |

Conclusion: the stress run re-confirms the F-2 availability impact and the
2-hour liveness stability, but the G2-07 pressure targets (event-stream load,
queue drop counters, control-response priority) were **not actually exercised**
on hardware and are not claimed as passing. Full per-frame timelines for both
runs are retained in the evidence JSONL.

## 9. Mapping to C-01..C-14 / acceptance cases

| Case | Layer | This round |
| --- | --- | --- |
| C-01/02/06/08/09/11/13 | software | host tests + combined hardware reinforcement (see result JSON) |
| C-03/C-04(half)/C-07(half)/C-10*/C-12 | hardware | combined covers read/commit/idempotency/restart; HA/web halves not_run |
| C-04/C-05 HA/web side | hardware | not_run (F-2, no connectivity) |
| C-10 20 power cuts | hardware | not_run (no human) |
| W-01..04 | hardware | partial fail (F-2), see §7 |
| S-01 | both | evidence-file-level secret scan passes; device log echo untested (no connectivity) |
| R-01 | hardware | soak completed (offline state); resource fields missing (F-5) |

## 10. Files changed and hardware operations

Added/modified this round (all uncommitted):

- `components/mmwave_host/mwcp_link.h`, `mwcp_service.cpp`,
  `mmwave_host.cpp` (P0 fix: dispatch/serialization buffers off the stack;
  user-approved)
- `tests/r60abd1-esp32c3-host.yaml` (main-task stack 8192)
- `tools/g2/{mwcp.py, run_g2.py, validate_frames.mjs, build_evidence_index.py}`
  (test toolchain)
- `docs/reviews/web-console/g2/{RUN.md,RUN_CN.md}`, this report,
  `g2-evidence-index.json`
- workspace `tmp/mwcp-g2/` (evidence and backup, gitignored)

Hardware: one full-flash read backup; two flashes (batch 1, batch 2);
multiple software restarts; multiple spontaneous resets (F-2/F-3, all
recorded); no physical power cuts, no unplugging, no manual NVS destruction.

## 11. Handoff and next steps

- To G3/G4: native Web Serial acceptance (needs a human or browser automation
  plus a human port pick), the full installer five-branch flow, UI rendering
  and visual checks.
- User decisions pending: F-2 fix direction (new batch, then re-run G2-06,
  the HA/web external entries, and the connected-state G2-07); whether F-4/F-5
  go into the next firmware iteration.
- Re-verification suggestion: after F-2 is fixed, re-run in the RUN.md order:
  G2-06 → G2-04 external entries → connected-state G2-07.

## 18. 2026-11-01 G2 on-device supplementary session (session-03, after R15 software review PASS)

Authorization (user, one-time): COM9 bench; flash+reboot+test-config (no full
erase); offline phase only this session (G2-06 not_run); 20 physical power
cuts with user cooperation. Session dir `workspace tmp/g2-hardware-20261101/`
(evidence index `evidence/evidence-index.json` with per-file SHA-256).

| Item | Status | Key results |
| --- | --- | --- |
| G2-01 session contract | pass | 12/12 on-device: HELLO/TTL/PING, idempotent replay, ID_REUSE, REQUEST_EXPIRED, TTL silence, rehello isolation, SESSION_CLOSE |
| G2-02 identity/capabilities | pass | 16/16: 19 capabilities exactly match fixture, pagination/bad-cursor, actions match |
| G2-03 radar observation | partial | pipeline 5 windows x 9 checks pass; module 1D stream tracks human (71-202cm, vitals valid); **module emits NO presence(0x80 0x01)/position(0x80 0x05) frames** (fresh boot / module reset / full restart all fail to restore); product honestly reports presence=False(valid), targets empty. Suspected stale module-internal zone from old room install (rev91 backed up); MWCP has no raw-UART channel by design (S-03) |
| G2-04 config/NVS | pass | **20/20 COMMITTED_NEW_SAFE, corrupted=0, rollbacks=0, exit 0**; per-cycle identity guard + snapshot hashes + CAS commit + physical cut + intact-old-or-intact-new; boot_id rotated every cycle. Tool fix recorded: power_cut_runner.py read_all_config 2-tuple unpack |
| G2-05 async actions | partial | radar.reset_module accepted (job-1, verification:none -> verified:false honest); device.restart boot_id rotation confirmed |
| G2-06 Wi-Fi/HA | not_run | offline-only scope per user |
| G2-07 endurance | pass (with honest gate failure) | 2h idle: 7200.2s/7200s, n=718, zero reboots, rpc_p95=33.4ms (budget 250ms), 0 gaps, zero errors/drops (rx 5->1439, radar_frames 64->12043); overall fail ONLY from offline_precondition gate (bracketing-only insufficient per R3-04 design; profile probes an absent SSID). Stress 2h not_run (separate stress-diag image batch) |

Final device state: bench-adapted config restored (rev 114, persisted).
Gate: **on-device supplementary testing executed within authorized scope;
awaiting independent acceptance review; WP-3 not entered.**
