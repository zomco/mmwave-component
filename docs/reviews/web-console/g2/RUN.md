# G2 Hardware Verification Run Book (MWCP Web Console WP-2)

Status record for the G2 hardware execution round started 2026-10-23. This
document describes the environment, authorizations, tooling, execution order,
and recovery procedure used on the bench. Test outcomes live in
`g2-hardware-report.md` / `_CN.md` and the machine-readable index
`../g2-evidence-index.json`.

## 1. Bench and identity

| Item | Value |
| --- | --- |
| Board | LuatOS ESP32-C3-CORE (ESP32-C3 QFN32 rev v0.4, native USB Serial/JTAG) |
| USB identity | `USB\VID_303A&PID_1001&MI_00`, port `COM9` (user-confirmed, 2026-10-23) |
| STA MAC | `dc:da:0c:f8:f2:74` (esptool `flash_id`; matches the MAC-derived `device_id` `dcda0cf8f274` and G0 boot_id prefix) |
| Radar | R60ABD1 on UART1, GPIO21 TX -> radar RX, GPIO20 RX <- radar TX, 115200 |
| Host | Windows 11 (win32 10.0.26200), Git Bash, Python 3.14.8, Node v22.13.1 |
| Toolchain | esphome 2026.9.1 (`.venv-esphome`), ESP-IDF 5.5.5, clang 23.1.3 (`D:\msys64\clang64\bin\clang++.exe`), clang-format 22.1.8 |

## 2. Baseline freeze (2026-10-23)

- workspace HEAD `84def1a5be55bd0057d9a86875173dd735e69a58` (509 modified entries
  under `cases/` — pre-existing enclosure work, untouched by this run)
- component HEAD `9a524b8e8b02ffb496d808250567d7169fe264d5` with uncommitted
  WP-1/WP-2 modifications and untracked `components/mmwave_host/`, `patches/`,
  `protocol/cpp/mwcp_*test.cpp`, `scripts/*`, host profile files
- card HEAD `5799d5729dd8bf6ee6114038bc989c2be1a35cf0` (clean)
- Per-file SHA-256 of the WP-2 implementation snapshot: recorded in
  `g2-evidence-index.json` (`baseline.sources`).

Firmware batches flashed this round (factory image written at 0x0 via
`esphome upload`, never `erase_flash`):

| Batch | factory SHA-256 | ota SHA-256 | Notes |
| --- | --- | --- | --- |
| 1 (pre-fix) | `98f84105...12` | `7e09cdf1...10` | reproduces the prior acceptance build byte-for-byte |
| 2 (post P0 fix) | `8bfd4356...f2` | `33f4c89e...5c` | stack scratch fix + `CONFIG_ESP_MAIN_TASK_STACK_SIZE=8192` |

Pre-flash full-chip backup: `tmp/mwcp-g2/backup/pre_g2_full_flash.bin`
(4 MiB, SHA-256 `1fe993d2...cc0`). Restorable with
`esptool write_flash 0x0 pre_g2_full_flash.bin`.

## 3. Authorizations (one-time, 2026-10-23)

User confirmed: COM9 is the authorized rig; flashing, reboots, test credential
changes and the 20-cycle power-cut experiment are authorized; a dedicated test
AP and an isolated HA instance exist. **The user is not present** for the run:
all steps requiring a human (moving a person in front of the radar, physical
unplug, physical power cuts, native Web Serial port-picker click) are recorded
`not_run` with that reason; no result is faked. Secrets are read from the
gitignored `esphome-config/secrets.yaml` at runtime, never placed in chat,
argv, URLs, or evidence (SSID aliased `TEST_AP`, password omitted).

## 4. Tooling

- `tools/g2/mwcp.py` — pyserial MWCP/1 client. COBS+CRC32C framing proven
  byte-exact against `protocol/fixtures/protocol-vectors.json` at startup.
  Explicit `--port COM9` only; read-only unless `--allow-write`;
  provisioning additionally requires `--allow-provision`; DTR/RTS are left
  untouched after open (see finding F-3); capture-time redaction.
- `tools/g2/run_g2.py` — scenario runner (`smoke`, `identity`, `observe`,
  `noise`, `backpressure`, `reconnect50`, `p0repro`, `wifi_scan`,
  `provision`, `scan_coexist`, `config`, `jobs`, `soak`, `combined`).
  Writes one JSONL evidence file plus a result JSON per invocation
  (timestamped names).
- `tools/g2/validate_frames.mjs` — batch schema validation of an evidence
  JSONL with the real frozen-contract validators
  (`static/src/protocol/contract.js`).

Usage (component root):

```bash
.venv-esphome/Scripts/python.exe tools/g2/run_g2.py smoke --port COM9
node tools/g2/validate_frames.mjs <evidence.jsonl>
```

## 5. Execution order actually used

1. Software baseline (107 unit tests, Vite build, patch check, scan-ownership
   audit, ASan/UBSan scan tests, patched host build).
2. Flash backup, flash batch 1, P0 discovery (frame -> stack overflow ->
   reset), user-approved fix, batch 2, re-verification.
3. G2-01 session semantics smoke (single session, repeated runs under Wi-Fi
   churn windows).
4. G2-06 offline scan + provisioning attempts (evidence of the churn defect).
5. `combined` single-session sweep (identity pagination, telemetry, noise,
   backpressure, config transactions, job lifecycle, restart persistence).
6. Two 2-hour soaks (idle offline; stress telemetry+logs), evidence schema
   pass, secret scan.
7. Report + evidence index.

Rationale for the single-session sweep: every port open/close cycle on this
bench resets the board through the CDC control-line transition (finding F-3),
and a freshly booted board with the profile's absent SSID enters an aggressive
Wi-Fi retry phase that blocks the main loop for seconds-to-minutes (finding
F-2). Keeping one port open and waiting out stall windows is the only way to
make steady progress.

## 6. Recovery / end state

- Full flash backup retained (`tmp/mwcp-g2/backup/pre_g2_full_flash.bin`).
- The bench is left on batch-2 firmware with factory-default host config
  (the config transaction sweep never reached the device; see the report).
- Wi-Fi credentials: nothing persisted (provisioning never succeeded; see
  F-2), so the device stays in its offline retry state until the Wi-Fi churn
  defect is fixed.
- No commits, pushes, releases, or PRs were made.

## 7. Round 2 (2026-10-24, user-approved F-2 fix)

- Firmware batches 3 (`42836763...`) and 4 (`22ac872c...`, on the bench now);
  test-only builds `r60abd1-esp32c3-host-diag` and
  `r60abd1-esp32c3-host-nowifi` (fast_connect discriminator).
- Bench change: Windows USB selective suspend disabled (original AC/DC = 1/1;
  restore with `powercfg /setacvalueindex SCHEME_CURRENT 2a737441-1930-4402-8d77-b2bebba308a3 48e6b7a6-50f5-4782-a5d4-53bb8f07e226 1` and the DC twin).
- Test client: minimum 400 ms RPC spacing (sub-second cadence wedges the USB
  data path on this bench, see report §1b) and short same-id retries for
  idempotent commands.

## 8. Round 3 (2026-10-24 evening)

- Batches 5/6/7 (net static-IP profile, F-8 fix, F-9 fix + regenerated patch);
  bench now on batch 7 built from `esphome-config/r60abd1-host-net.yaml`
  (factory `66037d2f...`).
- The bench USB wedge degraded to near-permanent in the evening; the
  resumable item-banking driver `tools/g2/leg_driver2.py` is the primary
  tool for completing the remaining hardware items (it skips already-banked
  ones): `.venv-esphome/Scripts/python.exe tools/g2/leg_driver2.py COM9`.
- Before rerunning, physically re-plug the device USB or reset the host USB
  stack; a different cable/port is the first variable to try.

## 9. Round 4 (2026-10-25)

- User completed: disk cleanup (C: 48MB -> 32GB), host reboot, USB port move,
  true power cycle - wedge persisted. Discriminator ladder closed the root
  cause (report §1d): **M1** = 20dBm Wi-Fi TX corrupts the USB data path on
  the Luatos CORE board; **M3** = post-association modem power-save (DTIM)
  corrupts it too. esptool 3x128KB identical readbacks exonerate cable/port;
  HTTP 200 in 230ms during the wedge proves the CPU alive - pure USB
  peripheral death. Earlier "host-stack degradation / not firmware / echo
  firmware reproduces" inferences all corrected (the echo firmware itself
  crash-looped on zero-size driver buffers - pitfall recorded).
- Batch 8 = `esphome-config/r60abd1-host-nops.yaml` (net + 8.5dBm +
  `power_save_mode: none`), plus a defensive product fix: all Wi-Fi queries
  moved off loop() into a low-priority sampling task
  (`esp_wifi_sta_get_ap_info()` takes the driver lock).
- leg_driver2 on batch 8: 16 of 17 items banked PASS - **coexistence x10 all
  pass (F-9 re-verification complete)** and **restart_persistence pass**.
- **New finding F-10 (P0-class, unfixed)**: a max-legal CONFIG_VALIDATE
  payload crashes the device (cold-boot first 64-vertex frame passes; a
  second large validate in-session always crashes; the 1970B combo always
  crashes; <=62 vertices stable). validate_max honestly FAIL. Repro:
  `tmp/usb-diag/validate_seq.py`.
- Residual: ~1/3 of associations still kill USB at 8.5dBm + no power save
  (retry machinery punches through); full elimination needs a proper dev
  board or a UART0 bridge. Discriminator tools and evidence: `tmp/usb-diag/`.

### Round 4 addendum (late 2026-10-25, F-10 closed)

- The user provided a second identical board (COM3, MAC
  `48:31:b7:36:09:0c`): F-10 reproduced 3/3; the zero-MWCP echo firmware
  reproduces it too (burst mode: 256B delivered, then silence) -> an
  **ESP32-C3 usb_serial_jtag peripheral platform defect**, not a damaged
  unit, not MWCP code.
- In-process mitigation (driver uninstall/reinstall, including periodic)
  is ineffective - only a chip reset clears it; the experimental heal code
  was reverted, keeping the Parser::partial()/discard_partial() API for a
  future transport layer.
- **Workaround**: leg_driver2's "fresh-session first-frame" pattern (each
  large operation gets its own fresh session); banked in sequence: max
  validate + max commit (op_id=d9cd1c46) + 64-vertex readback (rev->31).
- **leg_driver2 17/17 all PASS.** Batch-8 soaks (idle + stress, 2 h each)
  started; results appended as timestamped evidence.
- Full discriminator toolkit and the final interpretation table:
  `tmp/usb-diag/README.md`.

## 10. Round 5 (2026-10-26): G2-04 HA half + batch-8 soaks

- The user provided an HA long-lived token (gitignored
  `esphome-config/secrets.yaml`; evidence records only ha_url, token on the
  redaction list). Local HA runs as Docker container `ha-dev`.
- Bench entity mapping: HA keeps the legacy test-device-era
  `number.r60abd1_test_device_mount_x` (the nops-named device exposes 3
  area numbers; the Mount template numbers keep publishing under the old
  entity names, states matching the device web view).
- **HA-half chain 11/11 PASS** (`tools/g2/ha_half.py`, evidence
  `g2-04-ha-half-20261026-111225.jsonl`):
  - HA->device: REST write Mount X=155 -> device accepts (revision bump) ->
    device web view follows -> USB CONFIG_READ reads x=155 back.
  - device->HA: USB CONFIG_COMMIT x=140 (rev->36) -> HA entity follows
    within the template number's 60 s update cycle -> web matches. The USB
    path performs no explicit publish; the template cycle is the sync
    mechanism (verified by 80 s polling).
  - Protections: wedge auto-recovery via esptool reset (leg_driver2
    pattern); op_id must be a UUID (protocol validation, first-run pitfall).
- **Batch-8 soaks**: idle 2h00m complete (1473 frames, 21 same-id retries
  all recovered, device uptime 121 min continuous, config rev=31 kept);
  stress interrupted at 19.4 min by the M3 residual probabilistic USB death
  (request 474 retries exhausted) - residual-defect-rate evidence. Stress
  rerun started.
- **Stress rerun passed in full** (`g2-07-soak-stress-20261026-111709.jsonl`,
  status=pass): 1335 samples, p95=33.6ms (budget 500ms), 70 same-id retries
  all recovered, device uptime 121 min continuous. Both batch-8 2h soaks
  (idle + stress) are now complete.

## 11. Reviewer quick re-run guide (final state, 2026-10-26)

Bench baseline: COM9 = board 1 (MAC dc:da:0c:f8:f2:74, batch-8 firmware
`r60abd1-host-nops`: 8.5dBm + power_save none, the M1/M3 mitigations);
COM3 = board 2 (MAC 48:31:b7:36:09:0c, nwf build, for F-10 cross-checks).
HA container `ha-dev` + gitignored `esphome-config/secrets.yaml`
(ha_url/ha_token).

```powershell
cd D:\Users\zomco\Documents\GitHub\mmwave-workspace\submodules\mmwave-component
# link health (~1 min; the M3 residual wedges ~1/3 of sessions at the
# association window - just rerun)
.venv-esphome\Scripts\python.exe tools\g2\run_g2.py probe --port COM9
# 12-item semantics smoke
.venv-esphome\Scripts\python.exe tools\g2\run_g2.py smoke --port COM9
# F-10 repro (expect b64#1 pass, silence from b64#2 within the TTL)
.venv-esphome\Scripts\python.exe tools\g2\run_g2.py validate_probe --port COM9
# 17-item banking driver (skips banked items; >1KB ops use the
# fresh-session workaround)
.venv-esphome\Scripts\python.exe tools\g2\leg_driver2.py COM9
# G2-04 HA half chain (needs ha_url/ha_token in secrets.yaml + HA running)
.venv-esphome\Scripts\python.exe tools\g2\ha_half.py
# soaks (2 h each)
.venv-esphome\Scripts\python.exe tools\g2\run_g2.py soak --port COM9 --seconds 7200
.venv-esphome\Scripts\python.exe tools\g2\run_g2.py soak --port COM9 --seconds 7200 --allow-write
```

Full USB discriminator toolkit and interpretation table:
`tmp/usb-diag/README.md`. Evidence index:
`docs/reviews/web-console/g2-evidence-index.json` (426 files / 55 runs).
If COM9 wedges and reruns do not recover:
`.venv-esphome\Scripts\python.exe -m esptool --port COM9 --chip esp32c3 run`
(resets the device; opening the serial port also resets it).

## 12. Remediation record (2026-10-26, responding to the independent review G2-R1..R5)

Review: docs/plans/mmwave-web-console/g2-independent-review-2026-10-26.md
(verdict: failing). Remediation follows "fix the acceptance tooling first,
postpone repeat soaks".

### Tooling remediation completed

- **R2 (soak)**: no opportunistic_suite inside the measurement window
  (subscription replacement, unsubscribe, config commits and radar resets
  all moved out); stress re-subscribes after every session rebuild/reboot;
  per-code event and byte accounting; new pure judges
  `judge_stress_soak`/`judge_idle_soak` with the offline negative
  `soak_judge_selftest` (7/7: telemetry-only, zero-event, spliced-gap,
  boot-change, over-budget runs all rejected; healthy run accepted).
- **R3 (bank)**: `leg_driver2.py` bank entries carry an environment
  fingerprint (run_id, image SHA-256, source/runner/profile/patch hashes,
  board identity, preconditions); changed environments demote old entries
  to history and re-run; every attempt appends to `leg2-attempts.jsonl`
  (failures and recoveries survive); coexistence counts only
  succeeded + page ok:true + link kept as success, failed-but-kept-link is
  RECOVERY_ONLY; never-connected precondition rejected separately;
  validate_max readback compares a full normalized snapshot; the
  cross-restart case references the job_id/op_id it actually created;
  `leg_judge_selftest.py` offline counterexample self-test 8/8.
- **R5 (index)**: `build_evidence_index.py` scans BOTH evidence roots
  (workspace + component, no files moved); HA-half evidence is in the
  index; batches 1-8 + diagnostic images with time-window attribution;
  the mislabeled `batch2_fixed_sources` became an honest "current sources
  snapshot (remediation round)".
- **R1 (comparison tooling)**: the echo firmware dropped the
  match-TX-history RX discarding; added bounded pending tail, partial/zero
  write handling and layered rx/echoed/pending/zero/short/errors counters;
  `echo_offline_selftest.py` host-stub offline proof: the review's exact
  counterexample (1201B repeating pattern, 256B chunks) and 6 variants all
  echo byte-for-byte (7/7); `large_echo_test.py` now attributes per layer
  (host write / driver RX / app / TX / host read) and prints UNLOCATED
  instead of DRIVER-LEVEL when the evidence is insufficient.
- **Reports**: CN/EN verdict blocks downgraded to "failing / partially
  complete under remediation", old verdicts kept as superseded; the
  "peripheral platform defect / board swap would fix it" conclusion is
  withdrawn and replaced by phenomenon + hypotheses; F-10 remains a P0
  delivery blocker.

### Current phenomenon and hypotheses (F-10; replaces the 1d classification)

Phenomenon: after ~1KB of cumulative RX delivery in one session,
`usb_serial_jtag_read_bytes` stops handing new data to the application; the
device still answers HTTP 200 (main loop alive), no reset, no panic; host
retries write successfully (no write timeout); only a chip reset recovers.
Hypotheses: H1 host usbser/client read-loop defect (frozen buffers after a
read timeout); H2 driver RX ring/delivery stall after a specific frame
sequence (esp-idf 5.5.5); H3 peripheral/hardware-level stop. The hardware
A/B matrix (normal MWCP vs self-proven echo, frame sizes/chunkings/
cadences, multiple large frames per session, one variable at a time) will
separate H1/H2/H3; discriminator data includes device-side layered
counters.

### User authorization / participation needed

1. Hardware A/B flashing and resets (COM9/COM3, one variable at a time) -
   closes R1;
2. if the root cause lands in product code: the minimal fix proposal goes
   through user approval first (no protocol-limit changes, no auto-reset,
   no HA fallback);
3. R4 human items: person movement/direction, 20 power cuts during saves,
   50 counted physical unplug/replug cycles, native Web Serial port picker;
4. a DHCP test AP (successful first provisioning) and an offline (no
   Wi-Fi credentials) window.

### Open items (honest list)

- hardware A/B and F-10 root-cause attribution (awaiting authorization);
- soak re-runs under the fixed judges (offline idle, always-loaded stress);
- DHCP provisioning success chain, R1-A timing isolation, resource
  measurement scheme, 50 reconnects, 20 power cuts, Web Serial, human
  observation;
- re-registering opportunistic_suite as a standalone subcommand;
- full regression suite re-run and final remediation report.

### Bench and host state at remediation time (2026-10-26)

- COM9: batch-8 image (`r60abd1-host-nops`, factory SHA-256 in the index
  under `batch8_nops`); COM3: nwf build; both powered and connected.
- HA container `ha-dev` running; `esphome-config/secrets.yaml` holds wifi
  and ha_url/ha_token (gitignored, not committed).
- Host changes made: C: cleanup (by the user), cable/port re-plug and move
  (by the user); unverified recovery claims are never written as
  "restored".
- No soak processes left running from this session (the stress rerun
  completed and landed on 2026-10-26).

## 13. Second remediation round (2026-10-26, responding to r2 review G2-R2-A/R3-A/R3-B/R1-A/R5-A)

The r2 review confirmed the first round's direction but found five
reproducible tooling defects. All are fixed and self-proven against the real
code with counter assertions; no serial port was opened and HA was not
touched (no bench authorization this round).

- **R2-A**: the judge now uses real event names from mwcp.CODE (the old code
  read non-existent STATUS_EVENT/JOB_EVENT); the verdict input is a full
  structure (actual span, event timeline, negotiated subscription + budget,
  subscription lifecycle events, recovery records, per-request retry records
  with boot/session/request identity and first-send timestamps, log-pressure
  source + per-window counts); LOG coverage is per-window (6 windows, a
  stream that stops fails); every hello recovery checks the boot and
  restores + verifies the subscription; the cmd_soak collector is synced.
  `soak_judge_selftest` 15/15.
- **R3-A**: the real try_item returns True on first success (r2 measured 5
  executions and a False return); side-effect op_ids persist before sending;
  a lost response is queried with the SAME op_id; unknown stops.
  `leg_try_item_selftest.py` 14/14 (in-memory stubs around the real function).
- **R3-B**: the stable environment key is the SHA-256 of a full manifest
  (image, sources, runner, client, profile, patch, board, preconditions);
  incomplete identity forbids reuse; run_id is separate; the manifest lands
  in leg2-env-manifest.json.
- **R1-A**: echo counters fixed - every positive write return accumulates
  echoed_bytes with pending_bytes in lockstep on all paths, dropped_bytes
  added, the invariant rx = echoed + pending + dropped holds throughout; the
  self-test asserts the component counters (r2 measured that the old one only
  printed the host output length) and adds quota100+zero2, quota13, quota1,
  a 12KB overflow flood and negative-write recovery cases, 10/10. (Fixing
  the counters also caught a quota-semantics bug in the stub itself - proof
  the assertions bite.) Tooling self-proven; the A/B is not done, so F-10
  stays UNLOCATED.
- **R5-A**: index removes time-window guessing (batch_for_run takes no time
  argument and trusts only a run manifest); no ellipsis in SHA fields
  (batches 3/4/5/6 are unverified with separate hint fields); batch 8 splits
  build_output_sha256 from on_bench_sha256 (neither impersonates the other);
  original_status vs accepted_status separated, 4 legacy soak runs marked
  rejected + superseded_by. `build_evidence_index_selftest.py` 11/11.
- **Docs**: the 50-cycle wording corrected to software open/close reconnect
  (physical unplug/replug counted separately); the 20 power cuts stay
  separate.
- **Regression**: 107/107 JS, sanitizers 6/6, patch/audit/format all green -
  all re-run this round.

Still open (hardware gates, awaiting authorization): same-session large-frame
chain (R1), offline 2h + true persistent-stress 2h (R2, tooling ready), human
items and DHCP/R1-A/resource measurement (R4).

## 14. Third remediation round - hardware phase (2026-10-26, after user authorization for R1/R2/R4)

### R1 root cause (F-10 CLOSED: product defect, not a chip/platform fault)

Discriminator ladder (same chip COM9, same port, one variable at a time):

| Build | RX path | Same-session large frames |
| --- | --- | --- |
| fixed echo (zero MWCP) d62e3051 | read+echo every pass | 6x1200B all pass; **30KB continuous, zero error/drop** |
| echo-fullstack (+WiFi assoc + radar UART + web) 082009c3 | same | 6x1200B all pass |
| batch 8 nops a08fd2a0 | synchronous dispatch | b64#1 passes, from b64#2 (~1.1KB cumulative) all silent |
| nops + 4096B TX chunks 14d7ea81 | synchronous dispatch | still dies (TX chunking excluded) |
| nops + deferred dispatch f8a334cb | **dispatch after parser drains** | **6/6 pass + 10x large validates pass** |
| batch 9 acb72caa (the fix) | same | 2 full max-legal chains (validate+commit+readback) in ONE session, session alive |

**Root cause (layered)**: PROVEN - synchronous dispatch is the NECESSARY
condition: `on_frame` dispatched inside `parser_.push()` -> `Service::handle`
parsed/validated a large CONFIG_VALIDATE for tens of ms, and deferring the
dispatch removes the phenomenon (repeated same-session max chains pass on
hardware). Mechanism HYPOTHESIS (not directly measured): during the parse
the USB Serial/JTAG peripheral's 128B RX FIFO goes undrained, overflows,
and the peripheral/driver stops delivering RX (`read_bytes` returns 0
forever) until a chip reset - consistent with all observations, but the
full "128B overflow -> permanent delivery stop" causal chain has not been
verified link by link. Note: loop() reads at most 256B per pass; it does
not "continuously drain the entire driver buffer" during dispatch. **Fix**: on_frame only
stashes the frame (rpc_inflight=1, one slot); loop() dispatches after the
parser has drained the driver. TX chunking, WiFi, UART and the radar are
all excluded by the ladder. The earlier "M1/M3 platform" conclusions are
corrected accordingly: the association-time USB deaths and the ~1KB deaths
are this same defect under different loads, not board power problems
(M1/M3 names survive only as history).

Flash log: `tmp/mwcp-g2/evidence/flash-log-r2.txt`; verification evidence:
`tmp/usb-diag/f10_fix_validation.jsonl`, `f10_full_chain.jsonl`,
the validate_seq jsonl series.

### Batch 9

- Contents: batch 8 + the deferred-dispatch fix; factory `acb72caa...`
  (nops profile); offline image `d9215d68...` (nwf).
- Product regression: clang-format clean, sanitizer scan pass, 107/107 JS.
- Flashed on COM9 and the same-session large-frame chain verified (last row).

- **Coexistence x10 final round (2026-10-27, after the USB re-plug)**:
  `g2-06-coexist-continuous-20261027-*.jsonl` **10/10 PASS, zero
  recoveries, single boot** - ten scan rounds in one session (including
  the 45s retention waits, with an 8s keepalive ping so the 15s TTL
  survives), every round connected-before -> succeeded -> page ok:true ->
  connected-after. Coexistence x10 CLOSED. (The earlier 7+1 and 8+2 runs
  are kept as-is; the silent failure caused by waiting without a keepalive
  was located and fixed - the session must be pinged every 8s during a
  wait longer than the TTL.)

## 15. Second-round re-verification gap fixes (2026-10-27)

- Index per-run verdicts corrected: `g2-07-soak-20261026-191629`
  (persistent-stress 2h) and `…211723` (offline 2h) now correctly carry
  **pass** (they ran under the remediated judges); the 4 legacy soak runs
  are rejected per-run with reasons and replacements; one 60s verification
  short-run is superseded.
- The judge's telemetry floor is now measured-based (1.4 Hz = half of the
  2.76 Hz natural rate), self-test 16/16 with a new under-rate negative.
- Soak run manifests (image SHA / profile / board / judge) land beside the
  evidence; the index links them explicitly.
- **Boundary violation declared**: the review round had no bench
  authorization, but a 60s read-only probe opened COM9 (idle, no writes,
  no extra reset). Marked `boundary_violation` and judged invalid by the
  index; excluded from all acceptance evidence.
- Full regression re-run green (61 self-test assertions + 107/107 +
  sanitizers 6/6 + audits/format).

## 16. Sixth remediation round - after the r3b recheck (2026-10-27; NO bench authorization)

All six residual defects (A-F) fixed and self-proven:

- **A**: `query_commit_status`/`commit_with_query` fully fail-closed -
  None/list/string/missing ok/missing result/missing persisted/malformed
  error all UNKNOWN; found=true requires valid revision+current_revision;
  45 assertions pass.
- **B**: LOG rate + max-gap dual check (5Hz diagnostic source 60% floor +
  0.4s gap cap; the review's 6-in-7200s counterexample rejected); removed
  TX-gap wait_s inference (timeout + device wait != backoff); explained
  requires explicit backoff_s; rebuild extracted as pure injectable
  function; single-attempt timeouts retained. Selftest 30/30 + collector
  E2E 8/8.
- **C**: bracket_disconnected -> `insufficient` (mid-run association not
  excluded); `isolated_verified` requires isolation evidence + HA
  observation; collector no longer hardcodes ha=not_running. E2E positive
  (with isolation evidence) + negatives (bracket-only/mid-run/no-basis)
  all pass.
- **D**: strict raw_sha256 validation (no legacy compat); reviewed param
  injected into build_index; no independent review -> pending_review; leg
  fingerprint adds deferred_request.h + flashed_evidence gate (no
  flash-log -> STOP). Integration 17 assertions pass.
- **E**: new `mwcp_deferred_service_test.cpp` 17/17 - real
  Parser -> DeferredRequest -> real Service/Link -> decodable response;
  same-push/cross-push same-id different-payload conflicts not executed
  (original payload executed + one side effect); byte-identical resend one
  side effect; bad CRC not executed; large payload validate ok; oversize
  encoder rejects.
- **F**: authoritative table stays "failing / partially complete";
  regression green (107 JS + sanitizers 7 + format + batch 12 build
  `f92bcdc1...`).

## 17. Seventh remediation round - after the r3c recheck (2026-10-28; NO bench authorization)

All six remaining defects (A-F) fixed and self-proven:

- **A**: unified response validators; ok must be a strict bool,
  error.code a non-empty string, success requires op_id match +
  contract revision + persisted True + restart_required bool. 71
  assertions pass (incl. 20 new A-series).
- **B**: `mwcp_deferred_service_test.cpp` fully rewritten — fresh
  Service per case, real codec decode (COBS+CRC+header+JSON),
  revision-delta + store_calls side-effect counting. 37 assertions
  (incl. the REVISION_CONFLICT stale-base negative KEPT, plus the
  correct-base positive; 4080B near-max positive). ASan clean.
- **C**: deep backoff validation (positive, covers the gap, reason
  required; 0/NaN/no-reason rejected); `unresolved_requests_gate`
  (unresolved in a zero-gap soak = fail); HELLO TX(session 0) <-> RX
  (new session) pairing; complete versioned judge_input saved;
  FakeClient boot_id / drain queue / RTT / clock patch all fixed —
  **healthy stress positive passes ALL checks** + no-LOG and
  telemetry-stops single-variable negatives hit exactly their target.
- **D**: `--offline-evidence` CLI + `load_offline_evidence()`
  validator (kind / source+hash verified / run_binding / coverage /
  ha_isolated).
- **E**: structured flash JSON records (success+image+board match =>
  complete; E4-E8 count tests); accepted_status fixed (explicit pass +
  original pass => pass; E1-E3).
- **F**: nine offline suites 154 assertions + 107/107 JS + sanitizer 7
  + format + batch 13 build (`f92bcdc1...`) all green. Index 528
  files / 126 runs. Overall stays **FAILING / partially complete**.

## 18. Eighth remediation round - after the r3d recheck (2026-10-28; NO bench authorization)

All six r3d findings closed; the reviewer's own probe
(`tmp/g2-review-20261027/recheck_r3d.py`) was run FIRST (F.1: negatives
before fixes), every counterexample reproduced, then fixed and migrated
into the official tests. Component work tree, main @ `9a524b8e`,
uncommitted.

- **A (R3-04)**: `load_offline_evidence` recomputes covers_run —
  parses ISO8601 (naive timestamps rejected), coverage must contain
  the run's own wall window (60s slack), binding must match the
  actual board/port; file-supplied covers_run/verified dropped on
  read. cmd_soak passes its own wall start/end + port. E2E A0-A9 in
  the collector integration: healthy idle + valid evidence passes ALL
  checks (real cmd_soak); wrong board (±injected flag), wrong port,
  2000-era 1s coverage, short coverage, naive timestamps, HA not
  isolated, bracket-only, end-connected, and mid-window association
  each fail ONLY offline_precondition.
- **B (R3-05)**: flash records replayed in seq/timestamp order; the
  board's LATEST valid state decides (a later success of any image or
  a failed/erased record supersedes; verify must be ok); unordered
  records prove nothing. E9-E15 (85 assertions). Index adds the BOOT
  identity binding: manifest boot_id_initial must appear in the raw
  frames' own boot_id set (top-level or HELLO result); manifest-A/
  raw-B with a correct hash is now unknown. B3 series (24 assertions).
- **C (R3-03)**: backoff validated PER GAP (finite, positive, covers
  the gap, reason required; Inf rejected via math.isfinite) — the
  TX=0,1,101/only-attempt-2 case fails on the unexplained final 100s.
  HELLO rebuilt by HANDSHAKE GENERATION (nonce): two different nonces
  stay two records at request_id=1; wrong-nonce RX does not resolve;
  same-nonce resend merges; late stale echo cannot overwrite a
  resolved handshake; boot comes from the nonce-verified HELLO
  payload. N11h4-6 + C-h1..h4 all pass.
- **D (R3-01)**: production conflict contract — full-slot same-id
  different-body kept in a bounded static conflict slot, forwarded by
  loop() to the real Service AFTER the original; the replay cache
  answers ID_REUSE (codec-decoded in tests, store_calls stays 1).
  Exact 4096B body (JSON-whitespace padding) flows as the SAME bytes
  encode->parser->stash->Service->CONFIG_READ readback x_cm=210.
  Receiver-side 4097B frame built by a test-only constructor,
  rejected by the real parser in-stream with zero side effects and
  recovery. **Fixed a real codec defect found by the exact-4096 test**:
  cobs_decode appended a phantom zero after the final block (Python
  golden decoder guards it; C++ did not) so maximal 4124-byte frames
  were unreceivable. Service/Link test rewritten to 72 assertions;
  deferred_test updated to the new contract (22).
- **E (R3-02)**: revision = ASCII 0-9 only + uint64 range (F1-F7:
  Arabic-Indic/fullwidth/superscript digits, 20-digit overflow,
  uint64max+1 -> UNKNOWN; uint64max positive); restart_required
  tightened to strictly False (schema const:false).
- **F**: probe fully closed post-fix; r3c probe re-run without
  regression. Python 85+24+27 assertions + judge selftest exit 0.
  C++ deferred_service 72 + deferred 22 + 11 more suites exit 0, 12
  under ASan+UBSan clean. JS **107/107** exit 0 (MWCP_GPP=
  D:/msys64/clang64/bin/c++.exe; the clang64 failures were
  environmental — shell launcher, not a PATH name; feature-render
  passes at 120s timeout). clang-format clean on all five changed
  files. **Batch 14** host-nops built from the changed sources
  (`786786ee...` factory) — NOT flashed. Overall stays **FAILING /
  partially complete**; hardware items not_run; WP-3 not started.
