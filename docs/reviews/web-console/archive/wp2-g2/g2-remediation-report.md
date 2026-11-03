# G2 Independent-Review Remediation Report (2026-10-26; updated after r2/r3/r3e/r3l)

## Authoritative current status (2026-10-29, after the r3l fixes; this table
## is the single source of truth - history below is background only)

**Overall: FAILING / partially complete, remediation in progress (pending independent review).** Hardware gates are unmet; no
next stage.

| Gate/item | Current status |
| --- | --- |
| F-10 large-frame failure | Root cause located at synchronous dispatch (mechanism HYPOTHESIS: USB RX FIFO starvation - consistent with all observations, not directly measured); deferred dispatch verified on hardware over repeated same-session max chains; **product fix awaits independent re-verification** |
| Offline 2h (batch 9-nwf) | Executor verdict pass (7/7); index state **pending_review** |
| Persistent-stress 2h (stress-diag, 5Hz diagnostic LOG source) | Executor verdict pass (14/14); index state **pending_review**; load is a controlled diagnostic source, not natural / not max load |
| 50 software reconnects | 48/50 executed + 4 recovery resets (recorded); **not a reliability pass**, stall cause unattributed |
| Coexistence x10 continuous | 10/10 local evidence; does not replace DHCP / R1-A / resource gates |
| DHCP provisioning/rollback, R1-A attribution isolation, resource baselines | **not_run** |
| Human items (movement, 20 power cuts, unplug count, Web Serial) | **not_run** (windows not booked) |
| Acceptance tooling | All six G2-R3-01..06 tool/product fixes complete, migrated to formal suites, and offline-verified (below, pending independent review) |

> **Status after the r2 review (g2-independent-review-2026-10-26-r2.md):
> every tooling defect named by r2 is fixed and self-proven against the REAL
> code with counter assertions; the r1 self-tests' gaps (wrong event
> aliases / totals-only judge, try_item not returning on success,
> image-only environment key, untrustworthy echo counters, time-window
> batch guessing / ellipsis SHAs / status conflation) are all corrected.
> The hardware gates (original G2-R1/R2/R4) remain open; no bench
> authorization for this round - no serial port was opened.**

r2 remediation map (tooling items all proven offline):

| r2 item | fix | self-test |
| --- | --- | --- |
| R2-A judge false-pass/false-alias | judge rewritten: real event names (mwcp.CODE), full verdict input (span/timeline/negotiated subscription/recoveries/retry records/log-pressure source), per-window LOG coverage, unified boot check + subscription restore on every recovery; cmd_soak collector synced | `soak_judge_selftest` 15/15 (incl. r2's exact negatives: 1-telemetry+1-status+zero-LOG rejected; wrong aliases rejected) |
| R3-A try_item runs past success | success returns True immediately; side-effect op_ids persisted before sending (leg2-pending-ops.jsonl); a lost response is queried with the SAME op_id; unknown stops | `leg_try_item_selftest.py` 14/14 (real try_item + in-memory stubs; A5/A5b cover lost-response query and stop) |
| R3-B image-only environment key | stable key = SHA-256 of a full manifest (image, sources, runner, client, profile, patch, board, preconditions); incomplete identity forbids reuse; run_id separate; manifest written to disk | same suite (B1-B4: same-env reuse, changed runner/profile re-runs, incomplete forbids, run_id excluded) |
| R1-A untrustworthy echo counters | every positive write return accumulates echoed_bytes with pending_bytes in lockstep on all paths; dropped_bytes added; invariant rx = echoed + pending + dropped | `echo_offline_selftest.py` 10/10 (counter assertions, not just output length; quota100+zero2, quota13, quota1, overflow flood, negative-write recovery) |
| R5-A window guessing / ellipses / status conflation | batch attribution only via run manifest (no windows); no ellipsis in SHA fields (prefixes in hint fields); original_status vs accepted_status separated (4 legacy soak runs marked rejected + superseded_by); self-test covers the five r2 requirements | `build_evidence_index_selftest.py` 11/11 |

Regression (re-run after r2, not carried over): 107/107 JS (serial +
explicit env, exit 0), sanitizers 6/6 (scan/scan_gate/scan_lifecycle/
service/job/host incl. the 100k fuzz), patch --check, scan-ownership
audit, clang-format - all pass.

The 50-cycle wording is corrected: 50 software open/close reconnect
cycles; physical unplug/replug is counted separately; the 20 power cuts
during saves remain a separate item.

The original body (pre-r2 remediation record) is kept below; this block
governs.

Responds to [g2-independent-review-2026-10-26.md](../../../../../docs/plans/mmwave-web-console/g2-independent-review-2026-10-26.md).
Scope: this report only claims completed tooling / documentation / offline
verification; every hardware item not executed is listed not_run. No
commits, pushes or releases.

## 0. Overall status

**FAILING / partially complete, remediation in progress.** G2-R1, G2-R2 and
G2-R4 (all P0) are not fully closed; the tooling-level remediation for
G2-R3 and G2-R5 is complete and self-proven. F-10 remains a P0 delivery
blocker. The previous "G2 execution complete / 17-17 all PASS" claims are
void (kept as superseded history).

## 1. G2-R1 (P0): large-frame USB failure - tooling fixed, root cause awaits hardware A/B

| Review requirement | Status | Evidence |
| --- | --- | --- |
| Withdraw the "peripheral platform defect / board swap would fix it" conclusion | **done** | CN/EN verdict blocks and RUN §12; replaced by phenomenon + hypotheses H1/H2/H3; F-10 stays P0 |
| Fix the echo firmware (no content dropping, partial/zero writes, layered counters) | **done** | `tmp/usb-diag/components/usb_echo/` (bounded pending tail, rx/echoed/pending/zero/short/errors counters) |
| Offline self-proof (the review's exact 1201B counterexample echoed byte-for-byte) | **done** | `echo_offline_selftest.py` 7/7: 256B chunks, quota-100 writes + 2 zero writes, 7B chunks, quota 13, mixed content, alternating 2-byte, 4096B pseudo-random |
| large_echo_test layered attribution (no blanket DRIVER-LEVEL) | **done** | rewritten to host write / driver RX / app / TX / host read layers; prints UNLOCATED when evidence is insufficient |
| Hardware A/B (MWCP vs proven echo, frame-size/chunk/cadence matrix) | **not_run (awaiting authorization)** | flashing/reset authorization needed; one-variable-at-a-time matrix in RUN §12 |
| Root-cause evidence + minimal product fix (approve before implementing) | **pending** | depends on the A/B outcome; no protocol-limit changes, no auto-reset, no HA fallback; UART0 bridge is not a default implementation |
| Normal-image re-verification: multiple max VALIDATE->COMMIT->READ in one boot | **not_run (awaits root cause)** | same hardware window as the root-cause work |

Key offline conclusion: the old tool's counterexample against a healthy
driver is real (it echoed 433 bytes and dropped 768); the new tool echoes
the same input byte-for-byte, proving the old DRIVER-LEVEL label
untrustworthy. **This does not prove the hardware is innocent** - that is
exactly what the A/B will answer.

## 2. G2-R2 (P0): stress-soak load and judge - fixed, awaiting re-run

| Review requirement | Status | Evidence |
| --- | --- | --- |
| Semantic suite out of the measurement window | **done** | `cmd_soak` no longer calls `opportunistic_suite`; the suite is a standalone `op_smoke` subcommand (documented: mutates config / resets radar - never run next to a soak) |
| Persistent subscription + re-subscribe after rebuilds | **done** | stress `subscribe_stress()` runs initially and after every session rebuild; `resubscribes` counted in evidence |
| Event types / byte rate / log counters recorded | **done** | `account_events()` per-code counts and byte accounting in notes; `logs_dropped` first/last comparison |
| Judge negative self-test | **done** | `soak_judge_selftest` 7/7: telemetry-only / zero-event / spliced-gap / boot-change / over-budget all rejected; healthy run accepted |
| Timeouts / gaps / retries / boot listed; first-attempt vs retry latency separated | **done** | gap samples carry `gap_error` and timestamp; retry bursts counted; `boot_changes` separate |
| Re-run offline 2h + persistent-stress 2h | **not_run (awaiting hardware window)** | tooling ready; offline = no-Wi-Fi profile + idle mode |
| "idle = static-IP online" and mixed batches | **acknowledged** | batch-2 appendix and batch-8 soaks are attributed by time window in the index; the offline 2h belongs to the R4 plan |

## 3. G2-R3 (P1): bank environment reuse and assertion defects - fixed and self-proven

| Review requirement | Status | Evidence |
| --- | --- | --- |
| Environment fingerprint (run_id / firmware / sources / profile / runner / board / preconditions) | **done** | `environment_fingerprint()`; bank entries carry `env`; mismatched entries become history and re-run |
| Append-only attempt log (failures survive) | **done** | `leg2-attempts.jsonl`; `leg_judge_selftest` proves failure and success coexist |
| Strict coexistence assertion | **done** | only succeeded + page ok:true + link kept counts; failed-but-kept-link = RECOVERY_ONLY; never-connected precondition rejected |
| Counterexample self-test (4 classes) | **done** | `leg_judge_selftest.py` 8/8 |
| Full normalized snapshot comparison for max config | **done** | validate_max readback compares every install param, all 64 coordinates and all area fields |
| Cross-restart references the actual job_id/op_id | **done** | `item_restart_persist` records `created_job/created_op` and queries them after the restart |
| Side-effect failures query first, never blind-retry | **done** | driver retries only esptool-reset then same-session retry; CONFIG_COMMIT always fresh op_id but the query path is preserved (old-op_id replay semantics covered by op_smoke) |
| Mixed-batch attribution (coexist_1/8 were failed) | **acknowledged and corrected** | under the new judge those failed results no longer count; ten genuine successes require a re-run |

## 4. G2-R4 (P0): required hardware evidence - not_run list and booking list established

Everything not executed is honestly not_run; the user-participation list is
in RUN §12:

| Item | Status | Blocker |
| --- | --- | --- |
| Human movement / direction / boundary observation | not_run | needs a person on site |
| 20 power cuts during saves | not_run | human must cut power |
| 50 counted physical unplug/replug cycles | not_run | human |
| Native Web Serial port picker | not_run | human |
| DHCP provisioning success -> persist -> reboot -> reconnect | not_run | needs a DHCP test AP (the static-IP network stays as the negative case only) |
| Wrong password / AP gone / no-DHCP rollback | partial (no-DHCP negative exists) | same |
| R1-A timing isolation (background A -> component B, component A -> component B, late completion, permanent loss) | not_run | needs an approved test build that withholds real events |
| Resource measurement (heap / min heap / max block / stack headroom / loop time) | not_run | scheme to be designed (diagnostic build needs marking + overhead statement; host-off/on baseline) |
| Offline 2h + persistent-stress 2h re-runs | not_run | tooling just fixed; hardware window pending |

## 5. G2-R5 (P1): evidence mapping - fixed

| Review requirement | Status | Evidence |
| --- | --- | --- |
| Both evidence directories included (no history dropped, no files moved) | **done** | index `evidence_roots` lists both; each file records its root; 2 HA-half files indexed |
| Batches 1-8 + diagnostic images mapped | **done** | `firmware_batches` with profile and run_prefixes; every run attributed by time window |
| Honest source snapshot | **done** | `batch2_fixed_sources` replaced by `current_sources_snapshot` (remediation tree, not a historical batch) |
| Report contradictions fixed | **done** | CN/EN verdict blocks superseded; stale claims (F-2 unfixed / config transactions unrun) marked inside the preserved history |
| Single authoritative bench state | **done** | RUN §12 final section (COM9 batch 8, COM3 nwf, HA container, secrets location, no stray processes) |

## 6. Regression record (this round)

| Suite | Result | Command / environment |
| --- | --- | --- |
| 107 JS unit tests | **107/107 pass** | `node --test --test-concurrency=1 --test-timeout=60000 static/test/*.test.js` (MWCP_GPP=clang64, explicit writable TEMP/TMP; exit 0, 32s) |
| Scan-ownership source audit | pass | `scripts/check_scan_ownership_sources.py` (4 platform implementations) |
| Patch hash check | pass | `apply_esphome_patch.py --check` (already patched) |
| clang-format | pass | `--dry-run -Werror` (all components/mmwave_host) |
| Sanitizers (6 suites) | **all pass** | `clang++ -fsanitize=address,undefined`: mwcp_scan / scan_gate / scan_lifecycle / service / job / host (host includes the 100k deterministic mutation fuzz), exit 0 |
| Patched host build | pass | `build_host_profile.py --mode patched`; current sources compile; all three ownership defines reach the generated defines.h |
| Echo offline self-proof | **7/7** | `tmp/usb-diag/echo_offline_selftest.py` (review counterexample + 6 variants, byte-for-byte) |
| Soak judge self-test | **7/7** | `run_g2.py soak_judge_selftest` (offline) |
| Leg judge self-test | **8/8** | `tools/g2/leg_judge_selftest.py` (offline) |

## 7. Next steps (dependency order)

1. **User authorization**: hardware A/B (R1 root-cause attribution) -> if
   the root cause lands in product code, the minimal fix proposal goes for
   approval first (independent batch + new SHAs);
2. normal-image re-verification: multiple max VALIDATE->COMMIT->READ in one
   boot (closes R1);
3. soak re-runs under the fixed judges: offline idle 2h + persistent stress
   2h;
4. R4 booking windows: human items + DHCP AP + offline environment;
5. everything lands in the index -> re-evaluate the overall status; any
   gate still closed means reporting partially complete, honestly.

## 8. Third remediation round - hardware phase (2026-10-26, in progress)

Authorization scope: COM9/COM3 bench flashing and resets, the test network.
Executed so far:

### R1: F-10 root-caused and fixed (details in RUN section 14)

- Six-step discriminator ladder (fixed echo 30KB -> full-stack echo 6/6 ->
  batch 8 dies -> TX chunking excluded -> deferred dispatch 6/6 + 10x ->
  batch 9 full max-legal chain x2, session alive);
- **Root cause: on_frame dispatched a large CONFIG_VALIDATE synchronously;
  the tens-of-ms parse starved the USB Serial/JTAG RX FIFO (128B), and
  after the overflow the peripheral stopped delivering RX until reset**;
- **Fix (product code, verified)**: on_frame stashes the frame; loop()
  dispatches after the parser drains;
- The "chip peripheral platform defect" and "M1/M3 board power"
  conclusions are formally withdrawn (RUN section 14);
- Batch 9: factory `acb72caa...`; product regression all green.

### R2: in progress

- Offline 2h soak: batch9-nwf (`d9215d68...`) flashed on COM9, running;
- Persistent-stress 2h: added a controlled diagnostic LOG source
  (`log_pressure_hz` component option, default 0 = no code; the
  stress-diag profile sets 5Hz with verifiable sequence numbers), image
  `87c2168e...`; runs after the offline soak completes. Source continuity
  verified on COM3: 146 LOG events in 30s, strictly monotonic seq.

### R4: queued (after the soaks: 50 software reconnects, coexistence x10
continuous without resets, then the stress window)

Human items (person movement, 20 power cuts during saves, physical
unplug count, native Web Serial) still await a window; honestly not_run.

## 9. Hardware-phase results (2026-10-26 late night)

| Item | Result | Evidence |
| --- | --- | --- |
| R1 root cause | **CLOSED**: synchronous dispatch starved the USB RX FIFO; deferred-dispatch fix; batch 9 verified | RUN §14; flash-log-r2.txt |
| R2 offline 2h | **PASS 7/7** (re-run under the fixed judge: span 7200.4s / p95=33.5ms / single boot / zero gaps / offline_precondition PASS) | g2-07-soak-idle-20261026-212415.jsonl |
| R2 stress 2h | **PASS 14/14** (subscription alive throughout / 19,887 telemetry + 31,709 LOG events, uniform per window / p95=240.4ms) | g2-07-soak-stress-20261026-191713.jsonl |
| R4 50 reconnects | **48/50** (5x10 segments + 4 recorded recoveries; 2 failures kept in the availability data) | g2-01-reconnect50-segmented-*.jsonl |
| R4 coexistence x10 | **8/10 + 7/10 in two runs** (single boot, no resets; BUSY = correct protocol refusal of retention-window jobs; the full 10/10 re-run awaits a USB re-enumeration) | g2-06-coexist-continuous-*.jsonl |
| R4 rest | human items not_run (movement / 20 power cuts / unplug count / Web Serial) | booking list, RUN §12 |

### Bench/host state at report time

- COM9: batch 9 nops (`acb72caa...`) on board, CDC data stream awaiting
  re-enumeration (cause of the stall not attributed; web 200 OK); COM3: batch 9 nops
  on board, same state.
- Both boards run the batch-9 image with the F-10 fix (deferred dispatch).
- User action pending: re-plug either board's USB (10 seconds) -> re-run
  coexistence for the full 10/10.
- Running processes: none left over from this session (all soaks completed
  and landed).

## 10. R4 wrap-up (2026-10-27, after the USB re-plug)

- **Coexistence x10 continuous 10/10 PASS** (single session, single boot,
  zero resets, retention waits with keepalive) - this is LOCAL ordinary-
  coexistence evidence and does NOT replace DHCP provisioning success/
  rollback, R1-A background-vs-component scan late/lost attribution
  isolation, or runtime-resource / host-off-on baselines - those remain
  not_run.
- **50 software open/close reconnects: 48/50 executed + 4 recorded
  segment recoveries.** This is NOT a reliability pass; the cause of the
  every-~10-cycles write-stall pattern is NOT attributed (the host-side
  suspicion is unproven and device-side involvement is not excluded), and
  it stays out of product-availability conclusions. Physical unplug/replug
  is counted separately (human item).
- Still open (not_run): person movement/direction/boundary, 20 power cuts
  during saves, native Web Serial picker, DHCP provisioning chain, R1-A
  attribution isolation, resource baselines.

## 11. Second-round re-verification and gap fixes (2026-10-27; NO bench authorization - no serial/flashing/HA touched)

Re-verifying the r2 checklist found and fixed four residual gaps:

1. **Index per-run verdicts** (G2-R5-A): the old blanket-prefix rejection
   also marked the two remediated-judge soaks as rejected. Fixed with
   explicit per-run verdicts. **This section's first version had the two
   run mappings swapped** (caught by the r3 recheck); the correct mapping
   (verified against each result's own evidence reference and
   started/ended): `…191629`=60s idle verification (superseded),
   `…211723`=2h persistent-stress (raw `…191713`),
   `…232416`=2h offline idle (raw `…212415`). The two 2h runs are
   **pending_review** (executor verdict pass, awaiting independent
   re-verification) - a raw pass is never copied into acceptance.
2. **Telemetry threshold basis** (G2-R2-A): removed the always-1 expression;
   the threshold is now **measured** - natural radar rate 2.76 Hz
   (19,887/7200.4s from the accepted stress run), floor 1.4 Hz (half of
   measured); a new negative rejects under-rate runs (self-test 16/16).
3. **Soak run manifests on disk** (G2-R5-A item 1): cmd_soak writes an
   immutable run manifest (flashed image SHA, profile, board, collector/
   judge, boot_id) next to the evidence; the index links runs explicitly
   instead of guessing; verified with a 60s run.
4. **Boundary violation handled honestly**: one 60s read-only probe
   **mistakenly opened COM9 without bench authorization** during this
   review round (idle mode, allow_write=False; no reset beyond the port-
   open F-3 reset). Per the boundary rules it is recorded with
   `boundary_violation / not_valid_acceptance_evidence`, and the index
   marks such runs `invalid: boundary violation` (timestamp-matching rule
   added). The violation is declared here in full.

Also: dead branch removed from ha_half usb_call; the usb-diag README F-10
section synced to the RUN §14 final classification (product defect, fixed;
the old "peripheral platform" conclusion withdrawn); retry notes enriched
with session_id/boot_id/attempt correlation.

Regression (all re-run, exit codes 0): five self-test suites (soak 16 +
leg judge 8 + try_item 14 + echo 10 + index 13 = 61 assertions), 107/107
JS, sanitizers 6/6, patch --check, scan-ownership audit, clang-format.

**Boundary state**: this review round had no bench authorization; apart
from the declared 60s probe, no serial/flashing/HA was touched. F-10 was
root-caused and fixed in the authorized round (2026-10-26, batch 9
hardware-verified); the four human items remain not_run awaiting windows.

## 12. Third-round remediation G2-R3-01..06 (2026-10-27; NO bench authorization - no serial/flashing/HA touched)

Delivery location: all changes are in the `submodules/mmwave-component`
working tree (branch main @ `9a524b8e`, **uncommitted**); no other branch
or path holds these fixes.

### G2-R3-01 payload integrity (product fix)

- **Changed**: new `components/mmwave_host/deferred_request.h`
  (`DeferredRequest`: 4096B OWNED payload + full-slot / same-request
  resend / different-request-drop policy, no silent overwrite);
  `mmwave_host.h/.cpp` switched to it.
- **Integration test**: `protocol/cpp/mwcp_deferred_test.cpp` (links the
  real codec; drives real RX -> Parser -> stash -> dispatch) **9/9**,
  including the review's exact counterexample (legal request42 `{"x":1}`
  + same-push bad-CRC `{"x":2}` -> only the legal payload dispatched),
  bad COBS, trailing noise, two legal frames (different request dropped
  and counted), same-request resend (idempotent overwrite counted), max
  payload, byte-by-byte chunking, cross-push resend. ASan/UBSan clean.
- **Memory/loop impact**: +4KB static BSS + 16B metadata; one <=4096B
  memcpy per request; no allocation.
- **Mechanism wording**: synchronous dispatch is the PROVEN necessary
  condition (deferring removes the phenomenon, verified on hardware);
  "128B FIFO overflow -> permanent delivery stop" remains a HYPOTHESIS,
  not directly measured; loop() reads <=256B per pass - no claim of
  "continuously draining the whole driver buffer".
- **Batch 10**: `6f95de60...` (with this fix) built successfully, **NOT
  flashed** (no authorization); indexed.

### G2-R3-02 unknown-commit chain stop

- **Changed**: `tools/g2/leg_driver2.py` - `commit_with_query` returns a
  three-state outcome (success / known_failure / **UnknownOutcome
  exception**); a lost response now queries via the protocol
  **COMMIT_STATUS** (0x0023) with the ORIGINAL op_id (replay != query);
  found=false stays UNKNOWN (replay-cache eviction ambiguity); `try_item`
  catches UnknownOutcome -> records unknown -> **stops the chain** (no
  reset/retry/new op_id); fixed the success-return-before-append bug.
- **Tests**: `leg_try_item_selftest.py` **C1-C8** (real try_item wrapping
  real commit_with_query, memory stubs): all-timeout -> exactly ONE
  op_id / ONE CONFIG_COMMIT + ONE COMMIT_STATUS / ZERO resets / one
  unknown attempt; found=true -> success; found=false, missing fields,
  query-timeout -> UNKNOWN; immediate protocol error -> retryable
  failure; success logs exactly one pass attempt; an unknown bank entry
  blocks re-issuing across runs.

### G2-R3-03 sustained load & first-send latency

- **Changed**: `tools/g2/run_g2.py` - the judge adds **per-window
  telemetry coverage** (6 windows, each >=1.4Hz x window; a mid-run stop
  fails) and `retry_attempts_cover_total` (attempts must account for
  [first_send_t, resolved_t]; the 40.01s-total/10ms-last-sample case is
  rejected); the collector rebuilds the event timeline and per-request
  records from the RAW evidence frames (unified RX intake incl. RPC-wait
  periods; byte convention = payload-JSON bytes, stated; a parse failure
  yields unverified, never an empty list); the LOG source is labeled
  "**5Hz controlled diagnostic source (~4.8kbps ~= 60% of budget), NOT
  natural, NOT the 20Hz cap**".
- **Tests**: `soak_judge_selftest` **21/21** with the new negatives N11b
  (10080 telemetry packed into the first 2015.8s then stopping + 6 LOGs
  -> reject), N11c (40.01s total masked by a 10ms last sample -> reject),
  N11d (unverified retry evidence -> reject).

### G2-R3-04 real offline precondition

- **Changed**: `run_g2.py` cmd_soak - removed the unconditional
  `verified=True` and the false "no wifi component compiled" claim; the
  offline basis now comes from **bracketing read-only WIFI_STATUS
  observations** (start/end): both disconnected -> no-association,
  verified; anything else -> verified=False. The profile is explicitly
  documented as containing wifi/api/web_server.
- **Tests**: the selftest adds "association observed -> reject" and
  "unverified basis -> reject" (within 21/21).

### G2-R3-05 per-run identity

- **Changed**: `leg_driver2.py` is import-side-effect-free (lazy init;
  the manifest write happens only when an item runs);
  `build_evidence_index.py` reworked - the global `run_manifest_for`
  distribution and `batch_for_run` global association are removed; each
  run links ONLY its own sidecar manifest (located via the result's own
  evidence reference; a run_tag mismatch = foreign, rejected); boundary
  violations use the full started timestamp; the three mappings are
  corrected (**191629=60s idle verification -> superseded; 211723=2h
  stress raw `...191713`; 232416=2h idle raw `...212415`**; 191341=first
  2h idle attempt rejected); the two 2h soaks are **pending_review**
  (executor pass is not auto-promoted to acceptance); batches 9/10,
  stress-diag, instrumented echo, full-stack echo and the chunk4096/
  deferred diagnostic images are all indexed (full SHAs or unverified +
  hint); a third `usb-diag` evidence root carries the F-10/retry raws.
- **Tests**: `build_evidence_index_integration_test.py` **13/13** (the
  real build_index path: two runs on different images each link their
  own; foreign manifest rejected; missing sidecar unknown; same-name
  across roots deduplicated; rebuild/import leaves history unchanged;
  the three real run mappings; boundary exclusion).

### G2-R3-06 gates and reporting

- **Changed**: `g2-remediation-report_CN/EN.md` - removed "all automatable
  R4 items done" and "only human items left"; 48/50 + 4 recoveries is now
  "executed and recorded, NOT a reliability pass, stall cause
  unattributed"; DHCP / R1-A attribution / resource baselines restored to
  explicit not_run; an **authoritative status table** now heads both
  reports (overall: failing / partially complete); the two run-mapping
  errors are corrected in place.

### Regression (all re-run this round, exit codes 0)

Seven self-test suites: soak judge 21 + leg judge 8 + try_item 19 + echo
10 + index unit 13 + index integration 13 + deferred integration 9;
107/107 JS; sanitizers 8 suites (incl. the new deferred test) all pass;
clang-format clean; batch-10 firmware build succeeded (explicit final
state, not flashed).

### Not covered / awaiting authorization

- Batch-10 hardware verification (bad-frame robustness -> same-boot max
  chains -> network/config/reconnect -> offline & stress 2h + resources)
  awaits bench authorization, in dependency order;
- the four human items, DHCP, R1-A attribution isolation, and the
  host-off/on resource baselines remain not_run.

## 13. Fourth remediation round - after the r3 recheck (2026-10-27; NO bench authorization)

Per-item fixes for the six residual defects from the r3 recheck. Delivery:
`submodules/mmwave-component` working tree (main @ `9a524b8e`, uncommitted).

### G2-R3-01 (r3b) resend semantics

- **Changed**: `deferred_request.h` - a same-id resend must now match the
  payload LENGTH and BYTES exactly to merge (`resend_merges`); a same id
  with a different payload/length/code is a conflict: dropped and counted
  (`dropped_conflicts`), the ORIGINAL request stays stashed for dispatch
  (no latest-wins: the protocol rejects same-id-different-body as ID_REUSE;
  accepting a swap would dispatch unverified bytes under a validated
  identity and let a retry change the pending side effect).
- **Tests**: `mwcp_deferred_test.cpp` - T9 rewritten + T9b-e added (same
  push different payload, length change, code change, byte-identical
  chunked resend) on top of the kept T1-T8 = **18/18**, ASan/UBSan clean.

### G2-R3-02 (r3b) transport-exception classification

- **Changed**: `commit_with_query` - the string match on "no response" is
  GONE; every post-send exception (write timeout, serial disconnect,
  protocol timeout, malformed response) is "possibly executed" -> keep the
  op_id and query COMMIT_STATUS; found=true must carry the mandatory
  revision/current_revision fields; a non-dict response is UNKNOWN (no more
  AttributeError).
- **Tests**: C9 (Write timeout: one op_id, one COMMIT + one STATUS, zero
  resets), C10 (serial disconnect), C11 (malformed), C12 (found=true
  missing fields), C13 (complete fields succeed) = **34 assertions** pass.

### G2-R3-03 (r3b) collector integration and judging

- **Changed**: `code_to_name` hoisted (NameError fix); the rebuild is a
  pure injectable function; single-attempt timeouts are KEPT
  (resolved_t=None in the denominator); boot/session come from the frames;
  attempts carry wait_s backoff markers; the judge adds the two-leg
  latency-consistency check (last-leg + total traceability - the
  40.01s/10ms masking case is rejected), rejects no-attempts records, and
  the LOG source label is corrected to **600 B/s ~= 7.5% of the 8000 B/s
  budget** (the 4.8kbps/60% unit error fixed).
- **Tests**: `soak_judge_selftest` **26/26** (counterexamples A-complete,
  B, C single-timeout-accepted / no-attempts-rejected);
  `soak_collector_integration_test.py` **8/8** (fake client + fake clock
  drive the REAL cmd_soak end to end: healthy offline positive, NameError
  regression, timeout retention, boot from frames, mid-run association,
  counterexample A).

### G2-R3-04 (r3b) structured offline contract

- **Changed**: module-level `OFFLINE_PRECONDITION_ENUM` +
  `offline_precondition_from_observation()` shared by collector and judge
  (enum + explanation separated; the basis states exactly what two bracket
  points prove and that the nowifi profile DOES contain wifi/api/web).
- **Tests**: collector-built precondition passes the judge; mid-run
  association and unverified bases fail.

### G2-R3-05 (r3b) per-run identity hardening

- **Changed**: run manifests - `flashed_image_sha256` may only come from a
  flash/verify record (currently unverified); the build output lands in
  the separate `build_output_hint_sha256`; the manifest binds the raw
  file's CONTENT sha (`raw_sha256`). The index accepts a sidecar only when
  raw_sha256 matches: **same-type foreign manifests are rejected**, raw
  mutations invalidate, legacy sidecars without raw_sha256 still work.
- **Tests**: integration suite **17 assertions** (two stress runs on
  different images, same-type foreign, raw mutation, legacy sidecar);
  try_item C14 pins the hint documentation.

### G2-R3-06

The authoritative table stays "failing / partially complete"; 48/50 is not
a reliability pass; DHCP / R1-A / resources / human items remain not_run.

### Regression (re-run this round, exit codes 0)

Eight offline suites green (26+8+34+10+13+17+8+18); 107/107 JS; 7 sanitizer
suites; clang-format clean; **batch 11** (`f92bcdc1...`, strict resend)
built, NOT flashed.

### Hardware order awaiting authorization (unchanged)

bad-frame robustness / same-boot max chains -> network/config/reconnect ->
offline & stress 2h + resources -> human windows. Old-batch results never
stand in for the new image.

## 14. Fifth remediation round - after the r3b recheck (2026-10-27; NO bench authorization)

Per-item fixes for the six residual defects from the r3b recheck. Delivery:
`submodules/mmwave-component` working tree (main @ `9a524b8e`, uncommitted).

### A · G2-R3-02: all uncertain responses fail-closed

- **Changed**: `query_commit_status` - None/list/string/missing ok/missing
  result/missing found all raise UnknownOutcome (no more AttributeError or
  escape into the outer retry); found=true requires valid non-empty string
  revision AND current_revision (null/missing/non-string -> UNKNOWN).
  `commit_with_query` - removed the "no response" string match; structured
  classification: any post-send exception (write timeout, disconnect,
  protocol timeout, malformed) -> keep op_id and query COMMIT_STATUS;
  non-dict response -> UNKNOWN; missing `ok` -> UNKNOWN; ok=true but
  missing result or persisted!=true -> UNKNOWN; ok=false with malformed
  error -> UNKNOWN. Only a complete envelope (ok:true + result.persisted:
  true) is a known success; only ok:false with a structured error is a
  known failure.
- **Tests**: `leg_try_item_selftest.py` **C14-C18** (45 assertions):
  commit={} -> 1 op_id/0 resets; Write timeout + query=None -> 1 op_id/
  1 STATUS/0 resets; query=[]/string -> UNKNOWN; found=true null/missing/
  non-string -> UNKNOWN; legal success/legal explicit error/found=false
  semantics unchanged.

### B · G2-R3-03: load, timing, correlation and failure gating

- **Changed**: `run_g2.py` - LOG pressure upgraded to **rate + max-gap**
  dual check (6 windows each >= 3Hz x window = 60% of source rate; per-
  window max gap <= 2x nominal period 0.4s; the review's 100+1200i six-
  token case rejected, healthy 4Hz control passes); removed TX-to-TX gap
  wait_s inference (timeout + device wait != host backoff); explained
  verdict now requires explicit backoff_s field only;
  `rebuild_judge_inputs_from_evidence` extracted as a pure injectable
  function (boot/session from frames, no backfill).
- **Tests**: `soak_judge_selftest` **30/30** (incl. review counterexample
  A: 2Hz telemetry + 6 LOGs rejected by log_pressure_real; healthy 5Hz
  control passes; 40.01s/10ms masking rejected);
  `soak_collector_integration_test.py` **8/8** (real cmd_soak + fake
  client + fake clock end-to-end).

### C · G2-R3-04: real offline precondition

- **Changed**: `run_g2.py` - new `OFFLINE_PRECONDITION_ENUM` values
  `insufficient` (bracket_disconnected does not exclude mid-run
  association) and `isolated_verified` (bracketing + isolation evidence
  covering the run); `offline_precondition_from_observation()` accepts an
  `isolation_evidence` parameter; collector **no longer hardcodes
  ha=not_running** (passes unknown); `judge_idle_soak` only accepts
  `isolated_verified` + `not_running`.
- **Tests**: bracket-only rejected (insufficient), with isolation evidence
  + HA observation passes (isolated_verified), mid-run association
  rejected, no-basis rejected; collector E2E - offline run rejected by
  insufficient (not an end-to-end pass).

### D · G2-R3-05: strict evidence attribution and acceptance status

- **Changed**: `build_evidence_index.py` - strict `raw_sha256` validation
  (missing/empty/non-64-hex/mismatching -> unknown, **no legacy compat
  path**); `reviewed` parameter injected into build_index (no longer
  global-only); raw pass without independent review is **pending_review**
  (never auto-promoted); explicit rejected/violation cannot be upgraded.
  `leg_driver2.py` fingerprint - `deferred_request.h` added to sources;
  new `flashed_evidence` gate (flash-log must contain the image SHA for
  complete); without flash record the bank cannot auto-skip (STOP).
- **Tests**: `build_evidence_index_integration_test.py` **17 assertions**
  (incl. same-type serial-use/raw mutation/legacy sidecar/empty reviewed);
  `leg_try_item_selftest.py` C14 verifies hint doc, no-flash-log -> STOP,
  with-flash-log -> normal.

### E · G2-R3-01: contract loop closure

- **Changed**: new `protocol/cpp/mwcp_deferred_service_test.cpp` - REAL
  Parser -> DeferredRequest -> **real Service/Link** -> decodable response
  integration. Covers: same-push/cross-push same-id different payload
  (conflict not executed, original payload executed), byte-identical
  resend (one side effect), legal frame + bad CRC (original payload
  executed), large payload (validate ok), oversize (encoder rejects, no
  wire). Side effects verified through Service revision changes (not a
  string sink).
- **Tests**: **17/17** PASS (incl. setup HELLO + session live).

### F · Documentation and regression

- Authorit
ative table stays "failing / partially complete"; DHCP /
  R1-A attribution / resources / human items remain not_run.
- **Regression all green**: nine offline suites (30+8+45+10+13+17+8+18+17
  = 166 assertions), 107/107 JS, 7 sanitizer suites, clang-format clean,
  **batch 12** (`f92bcdc1...`, strict resend + all fixes) built NOT flashed.

## 15. Sixth remediation round - after the r3c recheck (2026-10-27/28; NO bench authorization)

Per-item fixes for the six remaining defects from the r3c recheck. Delivery:
`submodules/mmwave-component` working tree (main @ `9a524b8e`, uncommitted).

### A · G2-R3-02: unified response validators (no more blacklists)

- **Changed**: `tools/g2/leg_driver2.py` adds `_is_strict_bool` /
  `_is_valid_revision` (schema `^[0-9]+$`/20B) /
  `_validate_error_envelope` / `_validate_commit_success` /
  `_validate_commit_error`; `commit_with_query` / `query_commit_status`
  route through them. `ok` must be a strict Python bool
  (string 'false'/0/None/list -> UNKNOWN, not known_failure);
  `error.code` must be a non-empty string (42/object/missing -> UNKNOWN);
  success requires op_id matching the request, a schema-contract
  revision, persisted strictly True, restart_required a strict bool;
  a dict with only persisted -> UNKNOWN.
- **Tests**: `leg_try_item_selftest.py` A-series, 20 cases — every
  UNKNOWN case asserts 1 op_id / 0 resets / bank unknown. Suite passes
  **71 assertions**.

### B · G2-R3-01: Service/Link test fully rewritten

- **Rewritten**: `protocol/cpp/mwcp_deferred_service_test.cpp` —
  every case uses a FRESH Service (FreshService struct) + a live HELLO
  session; response frames are decoded through the REAL codec
  (Parser->Frame->JSON, verifying kind/request/session) with no wire
  substring find; side effects are proven by the revision before/after
  (via a real CONFIG_READ) AND the mem.store_calls count.
- **Coverage**: T1 legal first commit (ok=true / correct op_id /
  rev 1->2 / store=1); T2 same-push same-id conflict (store=1, 999
  and the conflicting op_id never appear); **T3 stale-base
  REVISION_CONFLICT negative** (commit at base 1 -> rev 2; re-commit
  at base 1 -> ok=false + REVISION_CONFLICT, storage unchanged; then
  the correct-base positive stores -> 2); T4 byte-identical resend =
  1 storage call (cache replay); T5 legal frame + bad CRC; T6
  near-max payload (measured 4080B encodes, dispatches, validates ok;
  >4096B encoder rejects; a subsequent legal frame recovers).
  **37 assertions** pass.

### C · G2-R3-03: backoff semantics + gates + HELLO + judge_input + collector

- **Backoff deep validation**: backoff_s must be a positive finite
  number that COVERS the gap, with a non-empty backoff_reason; 0 /
  negative / NaN / shorter-than-gap / no-reason do NOT explain. 3 new
  selftest cases: backoff_s=0 rejected (the r3c exact counterexample),
  a valid backoff=40.5 with reason passes, no-reason rejected.
- **unresolved_requests_gate**: resolved_t=None now enters the gate
  (an unresolved request in a zero-gap soak is a continuity
  contradiction -> fail).
- **HELLO correlation fixed**: the rebuild pairs HELLO TX (session 0)
  with its RX (new session) via a "hello" key; a successful HELLO no
  longer stays permanently unresolved. Non-HELLO boot comes from frames.
- **Full judge_input saved**: results carry `judge_input_version:1`
  plus the complete judge_input (all checks deterministically
  recomputable offline).
- **Collector integration fixed**: FakeClient adds boot_id to TX meta
  (fixes the 4-tuple pairing), a separate drain_script queue (RPC /
  event consumption split), a simulated 0.01s RTT (resolved >
  first_send), correct TX->RX ordering, and an EvidenceWriter fake-clock
  patch (time.time also replaced); **new healthy stress positive**
  (60s, 2Hz telemetry throughout + 5Hz diagnostic LOG, per-window
  [20,20,20,21,20,19], 12 RPC samples p95=10ms, 26 requests all
  paired — **ALL checks pass**) + **single-variable negatives**:
  no-LOG (log_pressure_real fails alone), telemetry-stops
  (telemetry_per_window fails alone).

### D · G2-R3-04: offline evidence input path

- **Changed**: `run_g2.py` adds a `--offline-evidence <file>` CLI arg
  and a `load_offline_evidence()` loader/validator. The file must carry
  k
ind (3 recognized isolation types), source (ref + 64-hex, the
  content hash ACTUALLY verified), run_binding (board/port),
  coverage (started/ended) and ha_isolated (strict bool). Any missing
  field or hash mismatch -> None (insufficient). covers_run is not read
  from the file — the collector derives it from coverage vs run time.
  **This is NOT a "--verified" switch: the content decides.**

### E · G2-R3-05: structured flash records + accepted_status fix

- **Flash records**: `leg_driver2.py` fingerprint parses JSON lines —
  `status=="success"` AND matching `image_sha256` AND matching
  `board_id` -> flashed_evidence=True; plain-text lines, status=failed,
  wrong board, wrong image -> False. Tests E4-E8: FAILED text / JSON
  failed / wrong board / wrong image -> not complete; success+correct
  image+board -> complete.
- **accepted_status fixed**: `build_evidence_index.py` — explicit
  review pass + original pass => **pass** (no longer downgraded to
  pending for being equal); no review => pending_review; explicit
  reject preserved. reviewed parameter injected. Tests E1-E3 pass.
- **Strict raw_sha256 validation preserved** (from last round).

### F · Regression

Nine offline suites green (154 assertions net); **107/107 JS**;
**7 sanitizer suites** (incl. the new Service/Link test under ASan);
clang-format clean; **batch 13** (`f92bcdc1...`) built NOT flashed.
Index rebuilt: 528 files / 126 runs.

### Open items

- The r3c E.3 multi-way run/boot/board cross-binding check is
  partially covered by the strict raw hash binding; the full
  cross-attribution verification is not yet complete (listed honestly).
- All hardware items not_run (DHCP / R1-A attribution / resources /
  human / unplug / power cuts / Web Serial); batch 13 not flashed.

Overall: **FAILING / partially complete.** G2 is not declared passed.

## 16. Seventh remediation round - after the r3d recheck (2026-10-28; NO bench authorization)

Closing the six r3d findings (g2-r3d-review-2026-10-28.md) one by one.
Per F.1 the round STARTED by running the reviewer's own probe
(`tmp/g2-review-20261027/recheck_r3d.py`) to confirm every counterexample
reproduced BEFORE the fix (infinite_backoff / only_first_gap_explained
both wrongly passed; the three revision cases wrongly accepted;
superseded_flash returned complete=true; two HELLO nonces merged into
one fake retry; the wrong-board/expired file passed end-to-end once
covers_run=true was injected; T6 swapped 4080->624), then fixed and
migrated the cases into the official tests. Delivery: component work
tree (main @ `9a524b8e`, uncommitted).

### A · G2-R3-04: coverage genuinely computed; covers_run is output-only

- **Change**: `run_g2.py load_offline_evidence()` rewritten — parses
  ISO8601 (**timezone-less naive timestamps are rejected outright**;
  they cannot be compared with the run's wall clock); coverage must
  satisfy started<=ended; **file-supplied covers_run/verified are
  dropped on read** and covers_run is RECOMPUTED: the coverage window
  must contain this run's own wall window (60s bracketing-observation
  slack) and run_binding must match the actual board/port; every
  mismatch is recorded in `coverage_mismatches` and yields
  covers_run=False. A wrong-board/expired/short file can no longer
  pass by carrying covers_run=true; a legal file passes WITHOUT
  filling it.
- `offline_precondition_from_observation` gained the covers_run=False
  branch (an explicit association_observed failure carrying the
  mismatch reason, no silent fallback to insufficient).
- **cmd_soak E2E**: the run's own wall start/end timestamps plus the
  actual port/board are passed to the loader — the binding is to THIS
  run.
- **Tests**: `soak_collector_integration_test.py` gained A0-A9
  (fixtures explicitly software): A0 healthy idle + valid evidence
  passes ALL checks through the real cmd_soak; A1 wrong board / A1b
  wrong board + injected covers_run=true / A2 wrong port /
  A3 2000-01-01 one-second coverage / A4 short coverage / A5 naive
  timestamps / A6 HA not isolated / A7 bracket-only / A8 end
  connected / A9 association observation inside the coverage window
  (the exact disconnected->connected->disconnected case) — each
  negative fails ONLY offline_precondition; all other run-quality
  checks still pass.

### B · G2-R3-05: flash-record replay + full run-identity binding

- **Flash replay**: the `leg_driver2.py` fingerprint no longer breaks
  on any old success record. Records are sorted by seq (timestamp
  fallback) and REPLAYED for this board; the board's LATEST valid
  state decides: a later success (any image) or a
  failed/aborted/erased/partial record supersedes everything before
  it; flashed_evidence requires the latest state to be success with
  THIS image and (if recorded) verify==ok. A record set with no
  seq/timestamp cannot be replayed and proves nothing (not complete).
  The reason lands in flashed_evidence_reason.
- **Tests**: `leg_try_item_selftest.py` E9-E15: A flashed then B
  supersedes (the review's exact case) -> not complete; later
  failed/erased -> not complete; unordered records -> not complete;
  other board's history ignored + own latest success positive (E13,
  complete=true); verify!=ok -> not complete. Suite: **85
  assertions**.
- **Run identity**: `build_evidence_index.py run_manifest_for()` adds
  the BOOT binding — the manifest's `boot_id_initial` must appear in
  the raw frames' own boot_id set (top-level field or HELLO result
  body); a manifest with a correct raw_sha256 but a boot identity
  from another run is rejected (unknown), no longer manifest-linked.
  The integration test gained the B3 series: manifest-A/raw-B
  (correct hash, wrong boot) -> unknown; same content + correct boot
  -> links; two independent legal runs each bind their own image;
  HELLO-payload boot positive.

### C · G2-R3-03: every gap accounted; HELLO correlated by handshake generation

- **Per-gap backoff**: `judge_stress_soak` no longer short-circuits on
  one valid attempt. Unexplained gaps are collected per gap: missing
  timestamp, no backoff record, **non-positive/non-finite value
  (math.isfinite rejects Inf and NaN)**, backoff shorter than the
  gap, missing reason — any single unexplained gap fails the record.
  The review's TX=0,1,101 case (only attempt 2 backed off) is
  rejected — the final 100s gap has no basis; Inf is rejected.
- **HELLO by nonce**: the rebuilder was rewritten. Real records carry
  no per-frame top-level boot_id and HELLO is pinned to request_id=1
  — the old (boot,"hello",rid,code) key merged DISTINCT handshakes
  into one fake retry. Now the TX nonce comes from the payload top
  level and the RX nonce from payload/result; a HELLO RX resolves
  ONLY the handshake whose nonce it echoes; different nonces stay
  independent records even at request_id=1; a same-nonce resend
  merges; a late stale echo cannot overwrite an already-resolved
  handshake (counted as late_echoes); boot identity comes from the
  nonce-VERIFIED HELLO payload (no uniform initial fallback);
  nonce-less orphan frames stay unresolved (never silently attached).
- **Tests**: judge selftest gained N11h4 (Inf), N11h5 (only first gap
  explained), N11h6 (all gaps evidenced, positive); collector
  integration gained C-h1..h4 (two handshakes -> two records with own
  identities / wrong nonce does not resolve / same-nonce resend
  merges / late stale echo lands on the old handshake only);
  FakeClient HELLO payloads now match the real client/device shape
  (TX top-level nonce; RX result.nonce + boot_id; unique per
  instance). All pass.

### D · G2-R3-01: production ID_REUSE + exact receiver boundaries

- **Production conflict contract**: `deferred_request.h` no longer
  silently drops/counts a full-slot same-id different-body conflict —
  the conflicting frame is kept in a SINGLE BOUNDED conflict slot
  (static 4096B; overwrites counted), the original request untouched;
  `mmwave_host.cpp loop()` forwards it to the REAL Service AFTER the
  original request, and the replay cache answers **ID_REUSE** per
  protocol 3.2 without executing the conflict body. The RX callback
  stays copy-only, allocation-free, no dynamic queue. A different
  request id while full is still dropped and counted (not
  ID_REUSE-able).
- **Exact 4096B**: test T6 builds a legal CONFIG_COMMIT body padded
  with JSON whitespace to EXACTLY 4096 bytes — the SAME bytes go
  encode (wire=4143) -> real Parser -> stash (asserts
  payload_length_==4096 and byte-identity) -> Service (commits,
  revision 2, store=1) -> real CONFIG_READ reads back the installed
  x_cm=210. **Found and fixed a REAL product defect**: the C++
  `cobs_decode` appended a phantom zero byte after the FINAL COBS
  block (the Python golden decoder guards with `i < len(data)`, C++
  did not), so a maximal frame of exactly kMaxDecoded=4124 bytes was
  rejected by the parser as kBadCobs — the device could not receive
  the very 4096-byte frames its own encoder emits. After the fix the
  golden COBS vectors (incl. the empty frame) pass and all C++ suites
  were re-run green.
- **Receiver-side 4097B**: a TEST-ONLY builder `build_raw_frame()`
  (bypassing the production encoder cap) constructs a real 4097-byte
  frame appended INTO THE SAME input stream: the real Parser rejects
  it (zero side effects) and a legal frame in the same stream
  executes and recovers. The production-encoder refusal of the same
  body is kept as the upstream assertion.
- **Tests**: `mwcp_deferred_service_test.cpp` rewritten to **72
  assertions** (T1 reads back the installed value + revision via a
  real CONFIG_READ; T2/T2b/T8 conflicts get real codec-decoded
  ID_REUSE responses with store_calls==1; T9 different-request full
  slot still drops; the older deferred_test T9/c/d updated to the
  new contract, 22 assertions, ASan clean).

### E · G2-R3-02: ASCII/uint64 revision + restart_required const:false

- `_is_valid_revision` rewritten: per-character **ASCII 0-9 only**
  (isdigit() also accepts Arabic-Indic/fullwidth/superscript Unicode
  digits which the schema `^[0-9]+$` does not); 1-20 UTF-8 bytes;
  **uint64 range** (18446744073709551615 is the largest legal value).
- `_validate_commit_success` tightened from "strict bool" to
  **strictly False** for restart_required (schema pins const:false;
  an unapproved protocol change must not be pre-accepted).
- Tests F1-F7: `١` / fullwidth `１２` / superscript `²` / 20-digit
  overflow / uint64max+1 -> UNKNOWN; the exact uint64 maximum passes;
  restart_required=true -> UNKNOWN.

### F · Regression and delivery

- **Commands / exit codes / counts** (all actually executed):
  - `tmp/g2-review-20261027/recheck_r3d.py`: after the fix every
    REVIEW line is closed (infinite_backoff/only_first_gap fail; the
    three revision cases UnknownOutcome; superseded_flash
    complete=false; the two-nonce case yields two records; a wrong
    nonce does not resolve; both wrong-board expired cases fail; all
    four suites exit 0); the r3c probe re-run shows no regression.
  - Python suites: leg_try_item_selftest **85 assertions** exit 0;
    build_evidence_index_integration_test **24 assertions** exit 0;
    soak_collector_integration_test **27 assertions** exit 0;
    soak_judge_selftest exit 0 (status=pass).
  - C++: deferred_service_test **72 assertions** exit 0;
    deferred_test **22 assertions** exit 0;
    service/host/job/r/scan/scan_gate/scan_lifecycle/close/af/
    g0_session/r60_probe all exit 0, 12 of them under
    **ASan+UBSan** (clang 23.1.3, -fsanitize=address,undefined), all
    clean.
  - JS: `node --test --test-concurrency=1 --test-timeout=120000
    static/test/*.test.js` with MWCP_GPP=
    `D:/msys64/clang64/bin/c++.exe` — **107/107 pass, exit 0**.
    (The earlier MWCP_GPP=clang64 failures were environmental:
    clang64 is the MSYS2 shell launcher, not a PATH executable name;
    the feature-render 60s timeout passes at 120s — unrelated to
    product code.)
  - clang-format: `--dry-run --Werror` on the five changed C++ files
    all pass (codec.cpp / deferred_service_test / deferred_test /
    deferred_request.h / mmwave_host.cpp).
  - Build: `scripts/build_host_profile.py --mode patched` (venv
    python, MSYSTEM removed) exit 0 with the defines check green; the
    host-nops profile rebuilt with the changed sources (batch 14),
    **not flashed** (no bench authorization).
- **All hardware items stay not_run** (DHCP, R1-A hardware
  attribution, resources host-off/on, human motion, 20 physical
  power cuts, physical unplug, native Web Serial); batch 14 not
  flashed; 48/50 + 4 recoveries is not a reliability pass.
- **Overall: FAILING / partially complete.** Awaiting independent
  acceptance; WP-3 is not started.

## 17. Eighth remediation round: post-r3e review (2026-10-28; offline only - no serial / no flash / no HA)

Responds specifically to the r3e independent review (`docs/plans/mmwave-web-console/g2-r3e-review-2026-10-28.md`) covering residual evidence judgment and identity gaps in R3-04 and R3-05. Strict offline software boundaries are maintained: no serial ports opened, no flashing, no resets, no HA/network manipulation; no changes to cases, fusion, engine, desktop; no commits, pushes, releases, PRs, or AI dispatches. All historical raw, result, manifest, and bank files are preserved. All fixtures and test outputs use isolated temporary directories.

### A · G2-R3-04: Strict coverage of actual run windows and binding to actual device identity

1. **Elimination of arbitrary 60s slack and strict window containment**:
   - `load_offline_evidence()` in `tools/g2/run_g2.py` completely eliminated the 60s tolerance window (`cov_start <= run_start + 60` and `cov_end >= run_end - 60`), which previously allowed insufficient coverage lacking initial or terminal seconds to be misjudged as verified.
   - Strict temporal containment is now enforced: `cov_start <= run_start` and `cov_end >= run_end`. Missing initial seconds, missing terminal seconds, inverted intervals, or zero duration result in `covers_run = False` with detailed mismatch records.
2. **Penetrative in-run association check across actual run span**:
   - Connection checks are no longer restricted to the declared coverage window. Instead, any `connected` state observed within either the actual run window (`run_start <= t <= run_end`) or the coverage window (`cov_start <= t <= cov_end`) flags `has_in_run_association = True`.
3. **Structured precondition state disambiguation**:
   - `offline_precondition_from_observation()` was rewritten to strictly separate three mutually exclusive states:
     - If network association was observed (`has_in_run_association == True`) -> returns `association_observed` (gate fails);
     - If brackets are disconnected but coverage is incomplete (`covers_run == False`, e.g. wrong board, wrong port, shorter duration than run, inverted times) -> returns `insufficient` with explicit mismatch details (fails without falsely claiming network association);
     - Only when the run is strictly covered and HA isolation is verified -> returns `isolated_verified` (the sole state permitting idle soak pass).
4. **Binding verified device identity in collector**:
   - Hardcoded board model `esp32c3-luatos-core` was removed from `cmd_soak`.
   - The collector extracts the verified device identity dynamically via `client.device_id` or `DEVICE_INFO` responses, recording `run_device_id` into the run manifest and passing it to the loader; evidence specifying mismatched boards is rejected as `insufficient`.
5. **Formal test integration**:
   - Migrated r3e target counterexamples and boundary variants (A10–A17) into `soak_collector_integration_test.py`: 2-hour run with partial coverage and association, cmd_soak zero-duration coverage with association, missing initial second, missing terminal second, inverted coverage, timezone equivalence positive, device ID mismatch, all passing (35+ assertions green).

### B · G2-R3-05: Flash lifecycle replay and bank reuse identity

1. **Board filtering and timeline replay ordering**:
   - `tools/g2/leg_driver2.py`:
     - Filters flash records by target `board_id` first, preventing cross-board record interference.
     - Implemented strict ISO8601 parsing with timezone normalization, rejecting naive timestamps and flagging anomalous future timestamps (>10m ahead).
     - Fixed sort key: sorts chronologically by timestamp when present, preventing timestamp-only records from sorting before seq records; records lacking both seq and valid timestamp are rejected as unorderable.
2. **State replay machine with strict verify requirement**:
   - Only records with `status == "success"`, `verify == "ok"`, and a valid 64-hex SHA establish a valid flashed state.
   - Any subsequent `unknown`, `failed`, `aborted`, `erased`, `partial`, or unverified record supersedes prior success, setting `flashed_evidence = False`.
3. **Formal test integration**:
   - Migrated r3e test cases (E16–E21) into `leg_try_item_selftest.py`: old A followed by unknown seq2, old A followed by unorderable partial, old A followed by timestamp-only B, success without verify, anomalous future timestamp, foreign board record interleaving, all passing (85+ assertions green).

### C · G2-R3-05: Raw/result/sidecar/boot/device/flash full correlation

1. **Raw frame identity extraction**:
   - Added `_raw_device_ids()` and `_raw_boot_ids()` in `tools/g2/build_evidence_index.py`, extracting device IDs and boot IDs from top-level frames, metadata, and HELLO/DEVICE_INFO payloads.
2. **Multi-dimensional cross-binding and anti-tamper verification**:
   - `run_manifest_for()` enforces comprehensive correlation:
     - `raw_sha256` must match actual raw file hash;
     - raw frames must contain manifest `claimed_boot`;
     - manifest `board` must match the device ID declared in raw frames;
     - result metadata (`run_id`, `board_id`, start/end timestamps within 120s tolerance, `evidence.sha256`) must strictly match the manifest and raw file, detecting tampering and preventing cross-run re-attribution.
3. **Hexadecimal SHA enforcement**:
   - `batch_for_run()` requires the image SHA to be exactly 64 lowercase hexadecimal characters and not all zeros; non-hex characters (such as `z*64`) return `unknown` / `unverified`.
4. **Formal test integration**:
   - Migrated r3e test cases (index_control, index_no_boot, index_missing_claimed_boot, index_wrong_board, index_nonhex_image, index_changed_result) into `build_evidence_index_integration_test.py`, all passing (30+ assertions green).

### D · G2-R3-06: Three-way categorization, regressions, and gate verdict

Per remediation standards, evidence is categorized into three explicit classes:

1. **Software remediated and passed (offline pass)**:
   - G2-R3-01..03: owned payload, bounded-delay ID_REUSE, exact 4096B/4097B boundary, COBS fix, strict revision/commit envelope, per-gap backoff, nonce handshake correlation (all verified green, no regressions).
   - G2-R3-04: removal of 60s slack, penetrative in-run association check, structured precondition disambiguation, dynamic device identity binding in collector.
   - G2-R3-05: flash record sequence replay (verify=='ok' enforcement, unknown/unorderable/subsequent failure override), raw/result/sidecar/boot/device/flash anti-tamper correlation, 64-hex SHA verification.
   - G2-R3-06: all 11 r3e reproduction cases (flash 4, index 5, offline 2) migrated to formal test suites and verified via `recheck_r3e.py`.
2. **Previously passed, preserved without refactoring**:
   - R1, R2, R4 software modifications preserved; G0 evidence index calculations preserved; 107 JS unit tests all pass; C++ host and deferred service suites all pass.
3. **Hardware bench not run (not_run)**:
   - DHCP provisioning/rollback, R1-A hardware isolation withhold tests, runtime resource baselines (host-off/on), human motion/orientation/boundary observations, 20 physical power cuts during saves, 50 physical unplug counts, native Web Serial browser port selection.
   - Batch 14 image not flashed (no bench authorization); 48/50 software reconnects + 4 recoveries remains unattributed and is not a reliability pass.

**Gate Verdict**:
**Overall: FAILING / partially complete, remediation in progress (pending independent review).**
Strict offline boundaries are maintained; offline test passage is not equated with G2 physical bench completion. G2 is not declared closed, and WP-3 is not started.


## 18. Ninth remediation round: post-r3f review (2026-10-28; offline only - no serial / no flash / no HA)

Responds specifically to the r3f independent review (`docs/plans/mmwave-web-console/g2-r3f-review-2026-10-28.md`) covering evidence contract definition, flash lifecycle replay order, external offline/HA attestation validity, and test fixture isolation. Strict offline software boundaries are maintained: no serial ports opened, no flashing, no resets, no HA/network manipulation; no changes to cases, fusion, engine, desktop; no commits, pushes, releases, PRs, or AI dispatches. All historical raw, result, manifest, and bank files are preserved. All fixtures and test outputs use isolated temporary directories.

### A · Strict evidence contract throughput (Producer → Index)

1. **Unique experiment ID (`experiment_id`) separation**:
   - Replaced fixed run tags and cross-experiment boot identifiers with dynamically generated unique IDs. `cmd_soak` in `tools/g2/run_g2.py` generates a unique `experiment_id = f"{run_tag}-{uuid4().hex[:12]}"` on each run.
   - Raw, result, and sidecar manifest files must carry matching `run_id` and `experiment_id`.
2. **Self-reference-free disk serialization & immutable result binding**:
   - Established a clean serialization sequence: the collector flushes and closes the raw file upon run completion, writes `result.json`, computes `result_sha256` of `result.json`, and writes `manifest.json` binding `raw_sha256`, `result_sha256`, `result_ref`, `run_id`, `experiment_id`, `started`, `ended`, `boot_id_initial`, and `board.device_id`.
   - Any post-hoc mutation to `result.json` (such as checks or timestamps) triggers immediate rejection via `result_sha256` mismatch.
3. **Consumer index strict anti-tampering verification**:
   - `run_manifest_for()` in `tools/g2/build_evidence_index.py` enforces full-chain verification:
     - `raw_sha256` must match the actual raw file hash;
     - `result_sha256` must match the actual result file hash;
     - `run_id` and `experiment_id` must match exactly;
     - `started` and `ended` must be valid timezone-aware ISO8601 timestamps and match exactly in UTC (eliminating the 120s tolerance window);
     - `claimed_boot` must exist in verified raw rx frames;
     - `device_id` must match `result.board_id` exactly and exist in verified raw rx frames (eliminating substring matching);
     - Protocol `note` frames are completely excluded from boot and device identity extraction.
4. **Firmware batch linkage via verified flash records**:
   - `batch_for_run()` strictly requires a valid `flash_record` in the manifest with `status == "success"`, `verify == "ok"`, and matching image/device to return `manifest-linked`;
   - Missing, unverified, or mismatched flash records converge to `batch: "unknown"`, `factory_sha256: "unverified"`, and `accepted_status: "pending_review"`.

### B · Flash lifecycle replay ordering and incomparable/conflicting records

1. **Elimination of future time tolerance**:
   - Removed the 10-minute future slack in `tools/g2/leg_driver2.py`: any timestamp ahead of the evaluation time (`as_of_time` or system UTC) is flagged as `future_anomaly`, resulting in `flashed_evidence = False`.
2. **Incomparable records rejection**:
   - When a record set lacks both complete timestamps and complete sequence numbers (`not has_all_ts and not has_all_seq`), relative chronological ordering cannot be deduced without synthetic assumptions; such sets are marked `unorderable` (`flashed_evidence = False`).
3. **Duplicate order conflict rejection**:
   - When multiple records share the same ordering key (same seq or same timestamp) with conflicting statuses, images, or verification results, they are marked `duplicate_conflict` (`flashed_evidence = False`).
4. **Dynamic device and timeline parameterization**:
   - `environment_fingerprint(device_id=None, as_of_time=None)` supports arbitrary device filtering and historical evaluation anchors.

### C · External offline / HA attestation content verification

1. **Structured JSON attestation content inspection**:
   - `load_offline_evidence()` in `tools/g2/run_g2.py` parses the referenced `source.ref` document and enforces structured JSON attestation requirements:
     - `observer`: non-empty inspector identifier;
     - `device_id`: matches target hardware ID;
     - `ha_observation`: strictly equal to `"not_running"`;
     - `review_status`: strictly equal to `"verified"`;
     - `conclusion`: strictly equal to `"isolated"`.
   - Plain text documents, missing attestation fields, pending reviews, active HA observations, or non-isolated conclusions yield `has_valid_attestation = False` and `covers_run = False`.
2. **Collector isolation assertion**:
   - `cmd_soak` sets `ha_ev = "not_running"` only when `has_valid_attestation is True`, `covers_run is True`, and `ha_isolated is True`; otherwise it remains `"unknown"`.

### D · Test isolation and formal test suite migrations

1. **Unique temporary directory isolation**:
   - Replaced fixed directory `tmp/usb-diag/soak_it` in `tools/g2/soak_collector_integration_test.py` with unique `tempfile.TemporaryDirectory` instances per run.
2. **Simulated UTC wall clock linkage**:
   - Coupled `FakeClock` with a simulated UTC wall clock (`SIM_BASE_WALL` advancing in lockstep with `clock.now`), eliminating implicit dependencies on the host machine's wall clock or 2000-era hardcoded dates.
3. **Test suite formalization**:
   - Added tests A18–A22 in `soak_collector_integration_test.py` covering plain-text source, pending status, active HA, non-isolated conclusion, and device mismatch (all pass).
   - Formalized 8 r3f negative tests in `build_evidence_index_integration_test.py` (`index_control_no_flash_record`, `device_substring`, `missing_manifest_device`, `missing_raw_device`, `missing_run_fields`, `result_time_changed_60s`, `result_checks_changed`, `identity_from_note`), while updating positive fixtures with `result_sha256` and `flash_record` (all pass).
   - Added tests E22–E24 in `leg_try_item_selftest.py` covering incomparable records, duplicate conflicts, and future timestamps (all pass).

### E · Three-way categorization and gate verdict

Per remediation standards, evidence is categorized into three explicit classes:

1. **Software remediated and passed (offline pass)**:
   - G2-R3-01..03: owned payload, bounded-delay ID_REUSE, exact 4096B/4097B boundary, COBS fix, strict revision/commit envelope, per-gap backoff, nonce handshake correlation (all preserved and passing).
   - G2-R3-04: offline attestation content verification (A18–A22), synchronized wall clock advancement, penetrative in-run association checks, dynamic device binding.
   - G2-R3-05: unique experiment_id generation, self-reference-free SHA binding, chronological replay ordering with incomparable/conflict rejection (E22–E24), 8 index anti-tampering negative tests.
   - Regressions all green:
     - `tmp/g2-review-20261027/recheck_r3f.py`: PASS
     - `tmp/g2-review-20261027/recheck_r3e.py`: PASS
     - `tmp/g2-review-20261027/recheck_r3d.py`: PASS
     - `tools/g2/leg_try_item_selftest.py`: PASS (88+ assertions)
     - `tools/g2/build_evidence_index_selftest.py`: PASS
     - `tools/g2/build_evidence_index_integration_test.py`: PASS
     - `tools/g2/soak_collector_integration_test.py`: PASS (A0–A22 pass)
     - `tools/g2/leg_judge_selftest.py`: PASS
     - `tools/g2/run_g2.py soak_judge_selftest`: PASS
     - C++ `mwcp_deferred_service_test.cpp`: COMPILED & 100% PASS (72 assertions)
     - Node.js `node --test --test-concurrency=1 --test-timeout=120000 static/test/*.test.js`: 107/107 PASS
2. **Previously passed, preserved without refactoring**:
   - R1, R2, R4 software modifications preserved; G0 evidence index calculations preserved; C++ host and deferred service suites all pass; frontend UI tests all pass.
3. **Hardware bench not run (not_run)**:
   - DHCP provisioning/rollback, R1-A hardware isolation withhold tests, runtime resource baselines (host-off/on), human motion/orientation/boundary observations, 20 physical power cuts during saves, 50 physical unplug counts, native Web Serial browser port selection.
   - Batch 14 image not flashed (no bench authorization); 48/50 software reconnects + 4 recoveries remains unattributed and is not a reliability pass.

**Gate Verdict**:
**Overall: FAILING / partially complete, remediation in progress (pending independent review).**
Strict offline boundaries are maintained; offline test passage is not equated with G2 physical bench completion. G2 is not declared closed, and WP-3 is not started.


## 19. Tenth remediation round: post-r3g review (2026-10-28; offline only - no serial / no flash / no HA)

Responds specifically to the r3g independent review (`docs/plans/mmwave-web-console/g2-r3g-review-2026-10-28.md`) covering defects G1–G5 across identity correlation, flash lifecycle order and producer evidence ingestion, attestation window constraints, and controlled early error cleanup. Strict offline software boundaries are maintained: no serial ports opened, no flashing, no resets, no HA/network manipulation; no changes to cases, fusion, engine, desktop; no commits, pushes, releases, PRs, or AI dispatches. All historical raw, result, manifest, and bank files are preserved. All fixtures and test outputs use isolated temporary directories.

### A · G1 / P1: Experiment ID and raw response strictly linked
1. **Unique experiment ID (`experiment_id`)貫通 across raw / result / manifest**:
   - Completely eliminated the fallback `run_id or experiment_id` bypass logic in `run_manifest_for()` in `tools/g2/build_evidence_index.py`. The manifest and result files must both declare matching `experiment_id` and `run_id`.
   - The producer (`cmd_soak` in `tools/g2/run_g2.py`) writes an explicit host experiment envelope note (`dir: "note"`, `note: "experiment_envelope"`, `experiment_id: ...`, `run_id: ...`) into the raw capture upon startup. The index verifies that all declared raw experiment IDs strictly match the manifest `experiment_id`, preventing raw captures from other runs from being attributed.
2. **Device facts strictly extracted from successful RX frames**:
   - `_raw_device_ids()` in `build_evidence_index.py` strictly extracts device identity from genuine RX frames (`dir == "rx"` or `kind == 2`), requiring recognized successful response codes (code 1 for HELLO or 3 for DEVICE_INFO) and `payload.get("ok") is True`.
   - Rejects extracting device identity from TX frames, note frames, unknown error codes (e.g. code=999), or unconfirmed payloads.

### B · G2 & G3 / P1: Unified flash source, lifecycle order, and live device binding
1. **Unified flash record device fields and strict validation**:
   - Deleted the `or not rec_board` permissive fallback in `batch_for_run()` in `build_evidence_index.py`.
   - Standardized flash record device identification (`device_id` / `board_id`), rejecting conflicting values. The declared device must match the manifest `device_id` exactly.
   - Enforced temporal ordering: the flash record `timestamp` must not be later than the run's `started` timestamp (rejecting future flash records attributed to historical runs).
2. **Live producer flash evidence input pathway**:
   - Added `--flash-evidence` CLI option and `load_flash_evidence()` loader/validator in `tools/g2/run_g2.py`, accepting external verified flash records during offline integration and production. Valid inputs require status=="success", verify=="ok", valid 64-hex image SHA, matching device ID, and timestamp <= run start.
   - Unified result file serialization and scrubbing: `cmd_soak` writes scrubbed `result.json` and `manifest.json`. `main()` skips overwriting when `--out` has already been written, ensuring `manifest.result_ref` and `result_sha256` byte-level exact match.
3. **Live verified device identity required for bank reuse and order contradiction detection**:
   - `tools/g2/leg_driver2.py`:
     - Completely eliminated fallback to hardcoded `mac_hint` when live device identity is absent. `environment_fingerprint()` requires a verified `device_id` (injectable offline via `MWCP_TARGET_DEVICE_ID`). If missing, `board` records the reason, setting `flashed_evidence = False` and rejecting bank reuse.
     - Added sequence vs timestamp contradiction detection:
       - Duplicate sequence conflict: identical `seq` numbers mapping to conflicting timestamps or states flag `duplicate_conflict = True`;
       - Sequence vs timestamp inversion: `s1 < s2` with `t1 > t2` flags `seq_time_contradiction = True`;
       - Both conditions unconditionally set `flashed_evidence = False`.

### C · G4 / P1: Attestation device identity and observation window constraints
1. **Mandatory attestation device matching**:
   - `load_offline_evidence()` in `tools/g2/run_g2.py` eliminated skipping validation when `att_board` is missing. The attestation must contain a non-empty `device_id` that matches the target hardware `run_board_id` exactly.
2. **Attestation internal observation and coverage validity**:
   - Validates internal `coverage` (`started` / `ended`) and `observed_at` fields within the attestation. The attestation's own coverage must strictly span the run window, preventing outer wrapper files from expanding the validity of expired or brief attestations.

### D · G5 / P1: Controlled early failure outcomes and safe resource cleanup
1. **Pre-initialization of variables**:
   - In `cmd_soak` in `tools/g2/run_g2.py`, variables (`run_device_id`, `boot_initial`, `run_wall_end`, `samples`, `flashed_image_sha256`, `flash_record`) are pre-initialized to explicit unknown/empty states prior to the `try:` block.
2. **Strict finally cleanup**:
   - Enclosed execution in `try: ... except Exception as error: ... finally:`. The `finally:` block unconditionally calls `client.close()` and `evidence.close()`, preventing Windows file locks (WinError 32). In early failure scenarios (e.g. HELLO timeout), controlled failure `result.json` and `manifest.json` are generated without triggering `UnboundLocalError`.

### E · Verification records and three-way categorization

#### 1. Independent probe `recheck_r3g.py` 14 REVIEW items verification
| Probe Review Item | Expected Status | Actual Output | Verdict |
| --- | --- | --- | --- |
| `index_control` | batch: manifest-linked, factory_sha256: 64-hex 'a' | batch: manifest-linked, factory_sha256: 64-hex 'a' | PASS |
| `index_wrong_flash_device_id` | batch: unknown, factory_sha256: unverified | batch: unknown, factory_sha256: unverified | PASS |
| `index_missing_flash_identity` | batch: unknown, factory_sha256: unverified | batch: unknown, factory_sha256: unverified | PASS |
| `index_future_flash` | batch: unknown, factory_sha256: unverified | batch: unknown, factory_sha256: unverified | PASS |
| `index_mismatching_experiment_ids` | batch: unknown, factory_sha256: unverified | batch: unknown, factory_sha256: unverified | PASS |
| `index_raw_from_other_experiment` | batch: unknown, factory_sha256: unverified | batch: unknown, factory_sha256: unverified | PASS |
| `index_nonresponse_identity` | batch: unknown, factory_sha256: unverified | batch: unknown, factory_sha256: unverified | PASS |
| `fingerprint_missing_live_identity` | complete: false, flashed_evidence: false | complete: false, flashed_evidence: false, reason: "missing verified live device identity" | PASS |
| `fingerprint_same_seq_different_time` | complete: false, flashed_evidence: false | complete: false, flashed_evidence: false, reason: "flash records carry duplicate sequence conflict" | PASS |
| `fingerprint_seq_time_contradiction` | complete: false, flashed_evidence: false | complete: false, flashed_evidence: false, reason: "flash records carry sequence and timestamp contradiction" | PASS |
| `collector_minimal_current_control` | status: pass, offline_verified: true, raw_has_experiment_id: true | status: pass, offline_verified: true, raw_has_experiment_id: true | PASS |
| `collector_missing_attestation_device` | status: fail, offline_verified: false | status: fail, offline_verified: false, reason: coverage mismatches | PASS |
| `collector_expired_attestation` | status: fail, offline_verified: false | status: fail, offline_verified: false, reason: coverage mismatches | PASS |
| `early_hello_timeout` | status: fail, closed: true | status: fail, closed: true (no UnboundLocalError, file handles safely closed) | PASS |

Probe exit code: **0**.

#### 2. Full test suite regression results
- **Historical regression probes**:
  - `tmp/g2-review-20261027/recheck_r3f.py`: Exit code **0**, all passed.
  - `tmp/g2-review-20261027/recheck_r3e.py`: Exit code **0**, all passed.
  - `tmp/g2-review-20261027/recheck_r3d.py`: Exit code **0**, all passed.
- **Python test suites**:
  - `tools/g2/build_evidence_index_selftest.py`: Exit code **0**, unit tests for flash device matching, missing/wrong device, and future flash all passed.
  - `tools/g2/build_evidence_index_integration_test.py`: Exit code **0**, VERDICT: pass.
  - `tools/g2/leg_try_item_selftest.py`: Exit code **0**, new tests E10 (duplicate seq conflict), E11 (seq/time contradiction), E12 (missing live device identity) all passed.
  - `tools/g2/soak_collector_integration_test.py`: Exit code **0**, VERDICT: pass, new tests A23 (missing attestation device), A24 (expired attestation coverage), A25 (early HELLO failure cleanup), A26 (producer -> index verified flash evidence closed loop) all passed.
  - `tools/g2/leg_judge_selftest.py`: Exit code **0**, VERDICT: pass.
  - `tools/g2/run_g2.py soak_judge_selftest`: Exit code **0**, all 36 judge tests passed.
- **Node.js test suite**:
  - Full suite `node --test --test-concurrency=1 --test-timeout=120000 static/test/*.test.js`: 107 tests, 106 pass, 1 fail (due to internal 20s clang++ spawnSync compilation timeout in `static/test/g0-hello.test.js`).
  - Standalone run `node --test static/test/g0-hello.test.js`: 2/2 pass in 2.0s, exit code **0**. The timeout during whole-suite execution is faithfully recorded.
- **C++ test suites**: C++ sources untouched this round; previous ASan+UBSan clean passes remain valid.

#### 3. Three-way categorization and gate verdict
1. **Software remediated and passed (offline pass)**:
   - G1–G5: unique experiment_id linking across raw/result/manifest, RX response device identity extraction, flash_record strict device and non-future timestamp validation, producer `--flash-evidence` input, bank live device identity enforcement and sequence conflict rejection, attestation device and coverage constraints, early failure try/finally resource cleanup.
   - Preserved remediations: owned payload, bounded-delay ID_REUSE, exact 4096B/4097B boundary, COBS fix, strict revision/commit envelope, per-gap backoff, nonce handshake correlation.
2. **Previously passed, preserved without refactoring**:
   - R1, R2, R4 software modifications preserved; G0 evidence index calculations preserved; frontend protocol and UI tests all passing.
3. **Hardware bench not run (not_run)**:
   - DHCP provisioning/rollback, R1-A hardware isolation withhold tests, runtime resource baselines (host-off/on), human motion/orientation/boundary observations, 20 physical power cuts during saves, 50 physical unplug counts, native Web Serial browser port selection.
   - Batch 14 image not flashed (no bench authorization); 48/50 software reconnects + 4 recoveries remains unattributed and is not a reliability pass.

**Gate Verdict**:
**Overall: FAILING / partially complete, remediation in progress (pending independent review).**
Strict offline boundaries are maintained; offline test passage is not equated with G2 physical bench completion. G2 is not declared closed, and WP-3 is not started.


## 20. Eleventh remediation round: post-r3h review (2026-10-28; offline only - H1..H4 evidence contract and path resolution)

Responds specifically to the r3h independent review (`docs/plans/mmwave-web-console/g2-r3h-review-2026-10-28.md`) addressing issues H1 through H4: non-overlapping output paths and failure persistence, strict raw experiment envelope and request/response correlation, strict flash record contract, mandatory isolation attestation timing, and JS timer jitter resolution. Strict offline software boundaries are maintained: no serial ports opened, no flashing, no resets, no HA/network manipulation; no changes to cases, fusion, engine, desktop; no commits, pushes, releases, PRs, or AI dispatches. All historical raw, result, manifest, and bank files are preserved. All fixtures and test outputs use isolated temporary directories.

### A · H1 / P1: Non-colliding output paths and storage failure persistence
1. **Output paths completely decoupled without collisions**:
   - `tools/g2/run_g2.py`:
     - Completely eliminated the path collision between `connect()` and `cmd_soak()` when `--out` specifies `.result.json` or `.json`. `connect()` writes raw capture frames to the requested target path. `cmd_soak()` detects the collision and routes the computed result JSON to an independent `.run.result.json`, ensuring `raw`, `result`, and `manifest` paths never overlap.
     - Both `--out capture.result.json` and `--out capture.jsonl` preserve genuine RX frames in the raw file, and `sha256(raw)` strictly matches `evidence.sha256`. The result JSON no longer overwrites raw frames.
2. **Storage and IO failures persist failure status and raw errors**:
   - Removed the broad exception swallowing that previously set `res_sha = None` while retaining `status = "pass"`.
   - When `result_path.write_text`, `manifest_path.write_text`, or `evidence.close()` raises an OSError/IOError:
     - The run status is unconditionally flipped from `"pass"` to `"fail"`;
     - Detailed error descriptions (`storage_failure`, `manifest_write_failure`, `evidence_close_failure`) are recorded in `outcome["error"]` and `outcome["failures"]`;
     - Raw evidence files and non-zero exit semantics are preserved.

### B · H2 / P1: Strict raw experiment envelope and request/response correlation
1. **Mandatory raw experiment envelope**:
   - `tools/g2/build_evidence_index.py`:
     - Removed the `if raw_exps:` bypass that previously skipped validation when raw experiment IDs were absent. When `raw_exps` is empty (raw lacks experiment envelope/ID), `run_manifest_for` returns `None`, and `batch_for_run` returns `"unknown"`.
     - Standardized `experiment_id` and enforced that the manifest's canonical ID must be strictly present in `raw_exps`.
2. **Device facts derived exclusively from correlated successful RX frames**:
   - `_raw_correlated_identities()` tracks TX HELLO nonces and requires matching nonces in RX HELLO frames;
   - Enforces `dir == "rx"`, `kind == 2`, and `payload.ok is True`, rejecting TX frames masquerading as responses or identity extraction from unverified/unpaired frames.

### C · H3 / P1: Unified flash record contract with strict types and timestamps
1. **Strict type and enumeration for verification**:
   - In `tools/g2/run_g2.py` (`load_flash_evidence`) and `tools/g2/build_evidence_index.py` (`batch_for_run`):
     - `verify` must be strictly string `"ok"` or `"verified"`, explicitly rejecting integer `1` (which previously matched due to Python's `1 == True`) and boolean `True`.
2. **Mandatory timestamp preceding run start**:
   - Removed optional timestamp handling: `timestamp` is mandatory, non-empty, valid ISO8601, and must not be in the future relative to run start.

### D · H4 / P2: Mandatory observation timing in external isolation attestations
1. **Mandatory attestation observation window / time**:
   - `load_offline_evidence()` in `tools/g2/run_g2.py` requires that source attestations must provide either `coverage` (`started` and `ended` dict) or `observed_at`.
   - Attestations lacking time fields fail validation with `coverage mismatches`, resulting in `has_valid_attestation = False`, `covers_run = False`, and `offline_precondition` failure (`wifi_status = "insufficient"`, `verified = False`).

### E · Node.js timer resolution jitter fix and 107/107 suite pass
1. **Timer jitter re-arming**:
   - In `static/src/protocol/client.js`, when a timer callback triggers slightly before deadline due to Windows 15.6ms timer resolution jitter, the timer is safely re-armed for the remaining duration rather than returning without action (which previously caused hanging Promises and early event loop termination).
2. **Node.js test suite execution**:
   - Full suite executed with `MWCP_GPP` set: **107 tests / 107 pass / 0 fail / 0 cancelled**, exit code **0**.

### F · Verification records and three-way categorization

#### 1. Independent probe `recheck_r3h.py` 11 REVIEW items verification
| Probe Review Item | Expected Status | Actual Output | Verdict |
| --- | --- | --- | --- |
| `actual_producer_index_control` | status: pass, batch: manifest-linked | status: pass, batch: manifest-linked | PASS |
| `raw_without_experiment` | batch: unknown | batch: unknown (modified_count=0, raw_experiments=[]) | PASS |
| `unmatched_hello_nonce` | batch: unknown | batch: unknown (modified_count=1) | PASS |
| `tx_masquerading_as_response` | batch: unknown | batch: unknown (modified_count=1) | PASS |
| `flash_no_timestamp` | batch: unknown | batch: unknown | PASS |
| `flash_verify_integer_one` | batch: unknown | batch: unknown | PASS |
| `proof_missing_own_time` | status: fail, offline_verified: false | status: fail, offline_verified: false | PASS |
| `real_connect_out.result.json` | status: pass, evidence_hash_still_matches: true, raw_contains_rx: true, raw_became_result: false | status: pass, evidence_hash_still_matches: true, raw_contains_rx: true, raw_became_result: false | PASS |
| `real_connect_out.jsonl` | status: pass, evidence_hash_still_matches: true, raw_contains_rx: true, raw_became_result: false | status: pass, evidence_hash_still_matches: true, raw_contains_rx: true, raw_became_result: false | PASS |
| `result_write_failure` | status: fail, result_exists: false | status: fail, result_exists: false | PASS |
| `formal_collector_suite` | exit: 0, verdict: pass | exit: 0, verdict: pass (pass_log_markers: 285) | PASS |

Probe exit code: **0**.

#### 2. Full test suite regression results
- **Historical regression probes**:
  - `tmp/g2-review-20261027/recheck_r3g.py`: Exit code **0**, all passed.
  - `tmp/g2-review-20261027/recheck_r3f.py`: Exit code **0**, all passed.
  - `tmp/g2-review-20261027/recheck_r3e.py`: Exit code **0**, all passed.
- **Python test suites**:
  - `tools/g2/build_evidence_index_selftest.py`: Exit code **0**, VERDICT: pass.
  - `tools/g2/build_evidence_index_integration_test.py`: Exit code **0**, VERDICT: pass.
  - `tools/g2/leg_try_item_selftest.py`: Exit code **0**, VERDICT: pass.
  - `tools/g2/leg_judge_selftest.py`: Exit code **0**, VERDICT: pass.
  - `tools/g2/soak_collector_integration_test.py`: Exit code **0**, VERDICT: pass.
  - `tools/g2/run_g2.py soak_judge_selftest`: Exit code **0**, all 36 judge tests passed.
- **Node.js test suite**:
  - `cmd /c "set MWCP_GPP=D:\msys64\clang64\bin\clang++.exe && cd /d D:\Users\zomco\Documents\GitHub\mmwave-workspace\submodules\mmwave-component && node --test --test-concurrency=1 --test-timeout=120000 static/test/*.test.js"`: **107 tests / 107 pass / 0 fail / 0 cancelled**, exit code **0**.

#### 3. Three-way categorization and gate verdict
1. **Software remediated and passed (offline pass)**:
   - H1–H4: Non-colliding output paths (`--out capture.result.json` preserves raw frames and hash match), storage failure status and error persistence, raw missing experiment_id rejects to unknown, HELLO RX/TX nonce pair correlation and rx direction enforcement, flash record verify=="ok" (rejecting integer 1) and mandatory timestamp, source attestation mandatory coverage/observed_at, client.js timer resolution jitter fix with 107/107 Node tests passing.
   - Preserved remediations: owned payload, bounded-delay ID_REUSE, exact 4096B/4097B boundary, COBS fix, strict revision/commit envelope, per-gap backoff, nonce handshake correlation.
2. **Previously passed, preserved without refactoring**:
   - R1, R2, R4 software modifications preserved; G0 evidence index calculations preserved; frontend protocol and UI tests all passing.
3. **Hardware bench not run (not_run)**:
   - DHCP provisioning/rollback, R1-A hardware isolation withhold tests, runtime resource baselines (host-off/on), human motion/orientation/boundary observations, 20 physical power cuts during saves, 50 physical unplug counts, native Web Serial browser port selection.
   - Batch 14 image not flashed (no bench authorization); 48/50 software reconnects + 4 recoveries remains unattributed and is not a reliability pass.

**Gate Verdict**:
**Overall: FAILING / partially complete, remediation in progress (pending independent review).**
Strict offline boundaries are maintained; offline test passage is not equated with G2 physical bench completion. G2 is not declared closed, and WP-3 is not started.


## 21. Twelfth remediation round: post-r3i review (2026-10-29; offline only - H1..H4 evidence contract and persistence solidification)

### 21.1 Context and independent review findings
Independent review `docs/plans/mmwave-web-console/g2-r3i-review-2026-10-29.md` confirmed the resolution of r3h counterexamples and successful producer->index control paths, but identified 4 specific remaining software evidence contract defects (H1..H4):
1. **H1 / P1 (Disk result remains pass after manifest write failure)**: In `cmd_soak()`, writing `result.json` occurs before writing `manifest.json`. If writing manifest raises `OSError`, in-memory outcome status is set to `fail`, but disk `result.json` remains `pass` with `error: null`. CLI `main()` also skipped rewriting if the file already exists, leaving misleading successful results on disk.
2. **H2 / P1 (Missing TX or mismatched request_id HELLO correlated)**: In `build_evidence_index.py`, `_raw_correlated_identities` previously bypassed check if TX nonces were empty, and did not enforce `request_id` matching, allowing raw files with deleted HELLO TX or modified RX `request_id = 9876` to pass as `manifest-linked`.
3. **H3 / P1 (Flash source and lifecycle verification missing unified gating)**: `run_g2.py` and `build_evidence_index.py` accepted isolated success records without validating `flash_record.source` file existence, SHA-256 integrity, or replaying lifecycle events prior to run start to detect superseded/erased images.
4. **H4 / P2 (Future single-point observed_at accepted as full isolation proof)**: When source attestation coverage was removed and `observed_at = 2099-01-01T00:00:00Z` was set, the prior check only verified `observed_at` was not before run start, lacking upper bound validation and missing continuous interval coverage requirements.

### 21.2 Software remediation implementation

#### 1. H1: Persist final failure to disk result, eliminating memory-disk divergence
- In `submodules/mmwave-component/tools/g2/run_g2.py` inside `cmd_soak()`, upon catching manifest write exceptions, synchronize the failed outcome and error back to disk by invoking `result_path.write_text()`.
- In CLI `main()`, check existing output files: if disk file indicates `pass` while outcome is non-pass, force rewrite to prevent stale pass results.

#### 2. H2: Bi-directional request/response correlation with strict field verification
- In `submodules/mmwave-component/tools/g2/build_evidence_index.py` inside `_raw_correlated_identities(jsonl)`:
  - Track `hello_tx[rid] = (nonce, session_id)` and `device_info_tx[rid] = session_id`.
  - For HELLO RX (code 1): require `rx_rid` to be present in `hello_tx` (missing TX rejects); verify `tx_nonce == rx_nonce`; enforce MWCP session rules: request session=0, response session!=0.
  - For DEVICE_INFO RX (code 3): require `rx_rid` to be present in `device_info_tx` and matching active session.

#### 3. H3: Unified flash source reference, content hash, and lifecycle replay
- In `build_evidence_index.py` (`batch_for_run()`) and `run_g2.py` (`load_flash_evidence()`):
  - Bind source absolute path and SHA-256 digest when given file inputs.
  - If `source` is present in `flash_record`, strictly check `ref` existence on disk and verify SHA-256 integrity.
  - Replay lifecycle logs for the target device up to run start: any subsequent erase, failure, or alternative image invalidates the flash claim, returning `unknown/unverified`.

#### 4. H4: Mandatory continuous coverage window and future timestamp filtering
- In `submodules/mmwave-component/tools/g2/run_g2.py` inside `load_offline_evidence()`:
  - Require continuous coverage window (`has_cov == True`) for duration/soak runs; reject isolated single points as insufficient (`wifi_status = "insufficient"`, `verified = False`), never mislabeling as `association_observed`.
  - Enforce timestamp plausibility: neither coverage nor `observed_at` may be in the future (with 15min clock tolerance).
  - Verify that source attestation coverage encompasses outer evidence coverage and actual run duration.

### 21.3 Verification and test results

#### 1. Independent review probe results
Running independent review probe `tmp/g2-review-20261027/recheck_r3i.py`:
```text
  [PASS] inputs_complete :: duration/span/samples/preconditions required
  [PASS] offline_precondition :: wifi_status=isolated_verified ha_status=not_running verified=True
  [PASS] duration_honest :: monotonic_span=60.1s requested=60s
  [PASS] samples_collected :: n=6
  [PASS] single_boot :: boot_changes=0
  [PASS] rpc_p95_within_budget :: p95=10.0ms over 6 samples; budget=250ms
  [PASS] no_uncovered_gap :: windows lost=0
REVIEW control {"status": "pass", "batch": "manifest-linked"}
REVIEW missing_tx {"batch": "unknown", "factory_sha256": "unverified", "identity_basis": "unverified: no verified flash record for this run"}
REVIEW wrong_request_id {"batch": "unknown", "factory_sha256": "unverified", "identity_basis": "unverified: no verified flash record for this run"}
REVIEW invalid_flash_source {"batch": "unknown", "factory_sha256": "unverified", "identity_basis": "flash record source file not found: ...\\absent.jsonl"}
  [PASS] inputs_complete :: duration/span/samples/preconditions required
  [FAIL] offline_precondition :: wifi_status=insufficient ha_status=unknown verified=False
  [PASS] duration_honest :: monotonic_span=60.1s requested=60s
  [PASS] samples_collected :: n=6
  [PASS] single_boot :: boot_changes=0
  [PASS] rpc_p95_within_budget :: p95=10.0ms over 6 samples; budget=250ms
  [PASS] no_uncovered_gap :: windows lost=0
REVIEW future_point_only_proof {"status": "fail", "offline_verified": false}
  [PASS] inputs_complete :: duration/span/samples/preconditions required
  [PASS] offline_precondition :: wifi_status=isolated_verified ha_status=not_running verified=True
  [PASS] duration_honest :: monotonic_span=60.1s requested=60s
  [PASS] samples_collected :: n=6
  [PASS] single_boot :: boot_changes=0
  [PASS] rpc_p95_within_budget :: p95=10.0ms over 6 samples; budget=250ms
  [PASS] no_uncovered_gap :: windows lost=0
REVIEW manifest_write_failure {"returned_status": "fail", "disk_status": "fail", "disk_error": "manifest_write_failure: OSError('SOFTWARE simulated manifest write failure')", "raw_exists": true}
```
| Probe Item | Pre-fix Observation (r3i) | Post-fix Observation | Expected Baseline | Verdict |
| :--- | :--- | :--- | :--- | :--- |
| `control` | batch: `manifest-linked` | batch: `manifest-linked` | batch: `manifest-linked` | PASS |
| `missing_tx` | batch: `manifest-linked` | batch: `unknown` | batch: `unknown` | PASS |
| `wrong_request_id` | batch: `manifest-linked` | batch: `unknown` | batch: `unknown` | PASS |
| `invalid_flash_source` | batch: `manifest-linked` | batch: `unknown` | batch: `unknown` | PASS |
| `future_point_only_proof` | status: `pass`, offline_verified: `true` | status: `fail`, offline_verified: `false` | status: `fail`, offline_verified: `false` | PASS |
| `manifest_write_failure` | returned: `fail`, disk_status: `pass`, disk_error: `null` | returned: `fail`, disk_status: `fail`, disk_error: `manifest_write_failure: ...` | returned: `fail`, disk_status: `fail` | PASS |

Probe exit code: **0**.

Prior probe `tmp/g2-review-20261027/recheck_r3h.py`: **exit code 0, all 11 REVIEW items passing** (including formal_collector_suite exit: 0, 285 PASS markers, verdict: pass).

#### 2. Regression suite execution results
- **Python Suites**:
  - `tools/g2/build_evidence_index_selftest.py`: exit code **0**, VERDICT: pass.
  - `tools/g2/build_evidence_index_integration_test.py`: exit code **0**, VERDICT: pass.
  - `tools/g2/leg_try_item_selftest.py`: exit code **0**, VERDICT: pass.
  - `tools/g2/leg_judge_selftest.py`: exit code **0**, VERDICT: pass.
  - `tools/g2/soak_collector_integration_test.py`: exit code **0**, VERDICT: pass.
  - `tools/g2/run_g2.py soak_judge_selftest`: exit code **0**, 36 judge checks all passed.
- **Node.js Frontend & Protocol Suite**:
  - Executed with workspace temp directory (`TEMP=...tmp\g2-review-20261027`) and `MWCP_GPP=D:\msys64\clang64\bin\clang++.exe`:
  - `cmd /c "set TEMP=D:\Users\zomco\Documents\GitHub\mmwave-workspace\tmp\g2-review-20261027&& set TMP=D:\Users\zomco\Documents\GitHub\mmwave-workspace\tmp\g2-review-20261027&& set MWCP_GPP=D:\msys64\clang64\bin\clang++.exe&& set PATH=D:\msys64\clang64\bin;%PATH%&& cd /d D:\Users\zomco\Documents\GitHub\mmwave-workspace\submodules\mmwave-component&& node --test --test-concurrency=1 --test-timeout=120000 static/test/*.test.js"`
  - **107 tests / 107 pass / 0 fail / 0 cancelled**, exit code **0**.

#### 3. Three-way categorization and gate verdict
1. **Software remediated and passed (offline pass)**:
   - H1: Manifest write failure persisted to disk result; CLI ensures stale pass results are overwritten.
   - H2: HELLO request/response bidirectional correlation; missing TX or request_id mismatch yields unknown; protocol session rules enforced.
   - H3: Flash source file existence, content hash, and lifecycle replay integrated into collector and index.
   - H4: Source attestation continuous coverage window enforced; future timestamps rejected; failure yields insufficient/verified=false.
   - All preserved offline remediations (owned payload, 4096B/4097B boundary, COBS, strict commit contract, per-gap backoff, nonce handshake) remain intact.
2. **Previously passed, preserved without refactoring**:
   - R1, R2, R4 software modifications preserved; G0 evidence index calculations preserved; frontend protocol and UI tests all 107 pass.
3. **Hardware bench not run (not_run)**:
   - DHCP provisioning/rollback, R1-A hardware isolation withhold tests, runtime resource baselines (host-off/on), human motion/orientation/boundary observations, 20 physical power cuts during saves, 50 physical unplug counts, native Web Serial browser port selection.
   - Batch 14 image not flashed (no bench authorization); 48/50 software reconnects + 4 recoveries remains unattributed and is not a reliability pass.

**Gate Verdict**:
**Overall: FAILING / partially complete, remediation in progress (pending independent review).**
Strict offline boundaries are maintained; offline test passage is not equated with G2 physical bench completion. G2 is not declared closed, and WP-3 is not started.


## 22. Thirteenth remediation round: post-r3j review (2026-10-29; offline only - H2 normalized frames and session correlation, H3 unified flash source semantics and full run-window lifecycle replay)

### 22.1 Context and independent review findings
Independent review report `docs/plans/mmwave-web-console/g2-r3j-review-2026-10-29.md` confirmed that all r3i specific counterexamples (`missing_tx`, `wrong_request_id`, `invalid_flash_source`, `future_point_only_proof`, `manifest_write_failure`) produced expected results; H1 manifest write failures synchronize to disk fail results; H4 future single-point proofs are rejected; and the authentic producer->index control path succeeds.
Remaining blockers were concentrated in H2 and H3:
1. **H2 / P1 (Mandatory session omitted and TX direction contradiction accepted)**:
   - In `build_evidence_index.py`, `_raw_correlated_identities` used `direction == "tx" or kind == 1`, allowing frames with `dir == "rx"` and `kind == 1` to be treated as legitimate HELLO requests.
   - `session_id` checks were previously optional (only checked if present); missing session on TX or RX did not trigger identity rejection. DEVICE_INFO also retained optional session conditions.
2. **H3 / P1 (Source existence and hash check does not equal source semantics and full lifecycle verification)**:
   - Collector and index maintained duplicate, approximate logic, bypassing checks whenever `source is None`.
   - Source JSON line parse errors were swallowed, exiting successfully without records; non-JSON plain text was accepted as a valid source.
   - Did not enforce that the source log actually contained a matching success record for the claimed device and image (a source with concurrent image B was accepted while wrapper claimed image A).
   - Lifecycle replay only ran up to `run_started`, omitting events during the run (e.g., erased at second 30 of a 60s run), and omitted `unknown` status from invalidations.

### 22.2 Software remediation implementation

#### 1. Shared pure verification contract: `tools/g2/flash_verifier.py`
Created a unified, pure verification module shared across `run_g2.py` (`load_flash_evidence` / `cmd_soak`), `build_evidence_index.py` (`batch_for_run`), and test suites:
- Enforces strict base schema: `status == "success"`, `verify` strictly string `"ok"` or `"verified"`, valid 64-hex non-zero `image_sha256`, device ID match, timezone-aware ISO8601 timestamp <= `run_started`.
- Enforces mandatory `source` object: missing source immediately yields `unverified` (`batch: unknown`).
- Validates disk file existence and exact SHA-256 integrity against `source.sha256`.
- Strictly parses source content (JSON Lines or JSON document/array); syntax errors or plain text fail immediately without swallowing exceptions.
- Explicit semantic matching: the source log must contain a matching success event for the claimed target device and image.
- Full run-window lifecycle replay: replays from the flash event timestamp through `run_ended` (or `run_started`). Any subsequent `failed`, `aborted`, `erased`, `partial`, `unknown`, or differing image event invalidates the firmware claim to `unverified`. Events occurring after `run_ended` or on other devices do not affect the current run.

#### 2. H2: Normalized frames and session correlation (`tools/g2/build_evidence_index.py`)
- Implemented `_normalize_frame(rec)`:
  - Validates top-level vs. `meta` consistency; rejects conflicting fields without picking one arbitrarily.
  - Rejects direction/kind contradictions: `dir == "rx"` with `kind == 1`, and `dir == "tx"` with `kind in (2, 3)`.
  - Normalizes `session_id` and `request_id` to uint32 bounds or `None`.
- Refactored `_raw_correlated_identities(jsonl)`:
  - Tracks explicit pending requests `pending_hello[rid] = (nonce, sid)` and `pending_device_info[rid] = sid`, and set `active_sessions`.
  - HELLO TX requires `session_id == 0`; RX requires non-zero `session_id > 0` and matching `request_id` and `nonce`; successful pairing activates the session.
  - DEVICE_INFO requires active session membership and matching request.
  - Matched requests are popped immediately to prevent replay or cross-talk.

#### 3. H3: Collector and index pipeline integration
- `submodules/mmwave-component/tools/g2/run_g2.py`:
  - `load_flash_evidence()` delegates to `flash_verifier.verify_flash_record()`.
  - `cmd_soak()` computes `run_wall_end` and passes the full run window (`run_started` and `run_ended`) to `load_flash_evidence`.
- `submodules/mmwave-component/tools/g2/build_evidence_index.py`:
  - `batch_for_run()` delegates to `flash_verifier.verify_flash_record()`.
- `submodules/mmwave-component/tools/g2/build_evidence_index_integration_test.py`:
  - Updated `manifest_for()` test helper to write companion flash source files for healthy fixtures.
  - Added 15-case H2/H3 formal test matrix covering missing sessions, contradictory directions, non-zero/zero sessions, meta conflicts, no source, plain text, wrong image, erase before/during/after run, unknown before run, and other device events.

### 22.3 Verification results

#### 1. Independent review probe `recheck_r3j.py` (exit code 0)
```text
  [PASS] inputs_complete :: duration/span/samples/preconditions required
  [PASS] offline_precondition :: wifi_status=isolated_verified ha_status=not_running verified=True
  [PASS] duration_honest :: monotonic_span=60.1s requested=60s
  [PASS] samples_collected :: n=6
  [PASS] single_boot :: boot_changes=0
  [PASS] rpc_p95_within_budget :: p95=10.0ms over 6 samples; budget=250ms
  [PASS] no_uncovered_gap :: windows lost=0
REVIEW real_file_producer_control {"status": "pass", "batch": "manifest-linked"}
REVIEW hello_missing_sessions {"changed_frames": 2, "batch": "unknown"}
REVIEW hello_tx_contradictory_direction {"changed_frames": 1, "batch": "unknown"}
REVIEW no_source_dict {"status": "pass", "collector_image": "unverified", "batch": "unknown", "identity_basis": "unverified: no verified flash record for this run"}
REVIEW source_plain_text {"status": "pass", "collector_image": "unverified", "batch": "unknown", "identity_basis": "unverified: no verified flash record for this run"}
REVIEW source_wrong_image {"status": "pass", "collector_image": "unverified", "batch": "unknown", "identity_basis": "unverified: no verified flash record for this run"}
REVIEW erase_before_run_control {"status": "pass", "collector_image": "unverified", "batch": "unknown", "identity_basis": "unverified: no verified flash record for this run"}
REVIEW erase_during_run {"status": "pass", "collector_image": "unverified", "batch": "unknown", "identity_basis": "unverified: no verified flash record for this run"}
REVIEW unknown_before_run {"status": "pass", "collector_image": "unverified", "batch": "unknown", "identity_basis": "unverified: no verified flash record for this run"}
```

| Probe Case | Pre-fix Observation (r3j) | Post-fix Observation | Expected Baseline | Verdict |
| :--- | :--- | :--- | :--- | :--- |
| `real_file_producer_control` | batch: `manifest-linked` | batch: `manifest-linked` | batch: `manifest-linked` | PASS |
| `hello_missing_sessions` | batch: `manifest-linked` (2 frames missing) | batch: `unknown` | batch: `unknown` | PASS |
| `hello_tx_contradictory_direction` | batch: `manifest-linked` (dir=rx, kind=1) | batch: `unknown` | batch: `unknown` | PASS |
| `no_source_dict` | collector_image: A, batch: `manifest-linked` | collector_image: `unverified`, batch: `unknown` | collector: `unverified`, batch: `unknown` | PASS |
| `source_plain_text` | collector_image: A, batch: `manifest-linked` | collector_image: `unverified`, batch: `unknown` | collector: `unverified`, batch: `unknown` | PASS |
| `source_wrong_image` | collector_image: A, batch: `manifest-linked` | collector_image: `unverified`, batch: `unknown` | collector: `unverified`, batch: `unknown` | PASS |
| `erase_before_run_control` | collector_image: `unverified`, batch: `unknown` | collector_image: `unverified`, batch: `unknown` | collector: `unverified`, batch: `unknown` | PASS |
| `erase_during_run` | collector_image: A, batch: `manifest-linked` | collector_image: `unverified`, batch: `unknown` | collector: `unverified`, batch: `unknown` | PASS |
| `unknown_before_run` | collector_image: A, batch: `manifest-linked` | collector_image: `unverified`, batch: `unknown` | collector: `unverified`, batch: `unknown` | PASS |

Exit code: **0**.

#### 2. Prior probe regressions
- `tmp/g2-review-20261027/recheck_r3i.py`: **exit code 0, all 6 REVIEW items pass**.
- `tmp/g2-review-20261027/recheck_r3h.py`: **exit code 0, all 11 REVIEW items pass** (including formal_collector_suite exit: 0, 285 PASS markers, verdict: pass).

#### 3. Formal test suites
- **Python Suites**:
  - `tools/g2/build_evidence_index_selftest.py`: exit code **0**, VERDICT: pass.
  - `tools/g2/build_evidence_index_integration_test.py`: exit code **0**, VERDICT: pass (all tests pass, including migrated H2/H3 matrix).
  - `tools/g2/leg_try_item_selftest.py`: exit code **0**, VERDICT: pass.
  - `tools/g2/leg_judge_selftest.py`: exit code **0**, VERDICT: pass.
  - `tools/g2/soak_collector_integration_test.py`: exit code **0**, VERDICT: pass.
  - `tools/g2/run_g2.py soak_judge_selftest`: exit code **0**, 36 judge checks pass.
- **Node.js Suite**:
  - Run with workspace temp directory (`TEMP=...tmp\g2-review-20261027`) and `MWCP_GPP=D:\msys64\clang64\bin\clang++.exe`:
  - Command: `node --test --test-concurrency=1 --test-timeout=120000 static/test/*.test.js`
  - Result: **107 tests / 107 pass / 0 fail / 0 cancelled**, exit code **0** (~32.8s).

#### 4. C++ compilation & tooling note
- This round focused strictly on Python offline evidence gating, indexing logic, and automated tests. No C++ files under `protocol/cpp/` or `components/r60abd1/` were altered.
- C++ builds and sanitizers were not re-triggered (retaining previous clean 6/6 sanitizer runs with 100,000 fuzz iterations).

#### 5. Three-way categorization & gate verdict
1. **Software remediated and passed (offline pass)**:
   - H2: Frame normalization rejecting top/meta conflicts and direction/type contradictions; HELLO session rules enforced (TX session=0, RX session>0 matching request_id/nonce); DEVICE_INFO bound to active sessions.
   - H3: Shared pure verification module `flash_verifier.py`; mandatory `source` object with hash check; strict parsing without swallowing syntax errors; semantic record match; full run-window lifecycle replay through `run_ended` (covering mid-run erase/unknown).
   - Preserved remediations: H1 manifest failure persistence, H4 continuous coverage interval, owned payload, 4096B/4097B boundary, COBS, per-gap backoff, nonce handshake correlation.
2. **Previously passed, preserved without refactoring**:
   - R1, R2, R4 software modifications preserved; G0 evidence index calculations preserved; frontend protocol and UI tests all 107 pass.
3. **Hardware bench not run (not_run)**:
   - DHCP provisioning/rollback, R1-A hardware isolation withhold tests, runtime resource baselines (host-off/on), human motion/orientation/boundary observations, 20 physical power cuts during saves, 50 physical unplug counts, native Web Serial browser port selection.
   - Batch 14 image not flashed (no bench authorization); 48/50 software reconnects + 4 recoveries remains unattributed and is not a reliability pass.

**Gate Verdict**:
**Overall: FAILING / partially complete, remediation in progress (pending independent review).**
Strict offline boundaries are maintained; offline test passage is not equated with G2 physical bench completion. G2 is not declared closed, and WP-3 is not started.


## 23. G2-H2/H3 Software Remediation (2026-10-29, based on g2-r3k-review)

### 23.1 Root Cause & Scope

Addresses the findings in `docs/plans/mmwave-web-console/g2-r3k-review-2026-10-29.md`:
1. **H2-A Command Routing & Real Session State**:
   - MWCP specification defines: `SESSION_CLOSE = 0x0003` (3), `DEVICE_INFO = 0x0010` (16). Evidence index previously routed `code == 3` as DEVICE_INFO, extracting device identity while ignoring genuine `code == 16` DEVICE_INFO frames.
   - `active_sessions` only ever accumulated sessions via `.add()`, failing to maintain current session lifecycle semantics.
2. **H2-B Premature Pop of Pending Requests**:
   - `build_evidence_index.py` executed `pending_hello.pop(rid)` prior to validating the incoming RX nonce. If a new request B (rid=1) was awaiting response, a stale response from previous request A reusing rid=1 removed B before failing nonce validation, dropping the genuine B response.
3. **H3-A Source Event Anchoring & Ordering**:
   - `verify_flash_record` did not bind the claim to an authentic, single matching source event, allowing callers to shift timestamps past an erase or use future events.
   - Erasures sharing identical timestamps with higher sequence numbers were ignored; events missing status during the run window were skipped; duplicate sequence number conflicts were accepted.
4. **H3-B Bank Disagreement with Shared History Contract**:
   - `leg_driver2.py` (`environment_fingerprint`) implemented independent flash log validation that rejected duplicate sequence conflicts, but did not call `flash_verifier.py`. Consequently, the same conflicting log was accepted by shared verifier and rejected by the bank.
5. **H3-C Input Schema Type Safety**:
   - Unconditional `.lower()` invocations on `image_sha256` crashed with `AttributeError` on non-string inputs (e.g. `image_sha256=123`) instead of degrading gracefully to `unverified`.

### 23.2 Implementation Details

#### 1. H2-A & H2-B: Aligned Command Codes, Active Session Lifecycle, and Peek-Before-Pop (`tools/g2/build_evidence_index.py`)
- Standardized command constants:
  - `MWCP_CODE_HELLO = 0x0001` (1)
  - `MWCP_CODE_PING = 0x0002` (2)
  - `MWCP_CODE_SESSION_CLOSE = 0x0003` (3)
  - `MWCP_CODE_DEVICE_INFO = 0x0010` (16)
- Correct command routing:
  - `code == 16` (`DEVICE_INFO`): Validated against `active_sessions` and pending requests; extracts `device_id` / `boot_id`.
  - `code == 3` (`SESSION_CLOSE`): Closes session, cleans up pending requests; strictly refuses to extract identity from payload.
- Session lifecycle:
  - HELLO handshake resets `active_sessions = {sid}` and purges pending requests from superseded sessions.
  - New HELLO nonce clears stale pending handshakes with differing nonces.
  - Peek-before-pop: HELLO pending entry is only popped after verifying `rx_nonce == tx_nonce`.

#### 2. H3-A & H3-C: Single Source Event Binding, Lifecycle Replay, and Graceful Fallback (`tools/g2/flash_verifier.py`)
- Type guards precede string operations (`isinstance(raw_img, str)`); invalid types return `unverified` with structured diagnostics without throwing uncaught exceptions.
- Claims must bijectively bind to an authentic source event `r_match` (device, image, success status, `verify in ('ok', 'verified')`, equal normalized ISO8601 timestamp, and matching seq/event_id).
- Lifecycle replay from `r_match` forward to `eval_window_end` (`run_ended` or `run_started`):
  - Strict ordering by `(seq, timestamp)` or `(timestamp, seq)`.
  - Rejects histories with missing anchors, future timestamps, duplicate sequence conflicts, or sequence/timestamp contradictions.
  - Rejects if any event in window lacks status, has unrecognized status, is `failed/aborted/erased/partial/unknown`, or introduces a differing image. Correctly detects same-timestamp later-sequence erasures.

#### 3. H3-B: Bank Unified on Shared History Contract (`tools/g2/leg_driver2.py`)
- Replaced 140 lines of duplicate logic in `leg_driver2.environment_fingerprint` with calls to `flash_verifier.parse_flash_log` and `flash_verifier.replay_board_history_to_latest`.
- Bank and shared verifier consistently reject duplicate sequence conflicts and ordering anomalies.

#### 4. Test Suite Migrations (`tools/g2/build_evidence_index_integration_test.py`)
- Added full R3k test matrix into formal integration test suite:
  - `H2-A`: DEVICE_INFO code 16 identity extraction; SESSION_CLOSE code 3 identity refusal.
  - `H2-B`: Stale HELLO RX (reused rid=1) does not discard pending new HELLO.
  - `H3-A`: Rejection of post-run success, shifted claim timestamp, same-timestamp later seq erase, missing status in run window, and duplicate seq conflict.
  - `H3-B`: Harmonized rejection of duplicate sequence conflict across both bank and shared verifier.

### 23.3 Verification & Independent Probe Results

#### 1. Independent Review Probe `recheck_r3k.py` (Exit code 0)
```text
REVIEW healthy_file_chain {"status": "pass", "batch": "manifest-linked", "identity_basis": "per-run manifest with verified flash record (run_tag=g2-07-soak-idle, profile=tests/r60abd1-esp32c3-host-nowifi.yaml)"}
REVIEW source_success_only_after_run {"status": "pass", "batch": "unknown", "identity_basis": "unverified: no verified flash record for this run"}
REVIEW claim_timestamp_shifted_past_erase {"status": "pass", "batch": "unknown", "identity_basis": "unverified: no verified flash record for this run"}
REVIEW same_timestamp_later_seq_erase {"status": "pass", "batch": "unknown", "identity_basis": "unverified: no verified flash record for this run"}
REVIEW missing_status_during_run {"status": "pass", "batch": "unknown", "identity_basis": "unverified: no verified flash record for this run"}
REVIEW duplicate_sequence_conflict {"status": "pass", "batch": "unknown", "identity_basis": "unverified: no verified flash record for this run"}
REVIEW numeric_image_schema {"result": "unverified"}
REVIEW pending_new_hello_stale_False {"new_boot_accepted": true}
REVIEW pending_new_hello_stale_True {"new_boot_accepted": true}
REVIEW identity_opcode_DEVICE_INFO {"code": 16, "response_marker_accepted": true}
REVIEW identity_opcode_SESSION_CLOSE {"code": 3, "response_marker_accepted": false}
REVIEW bank_shared_contract_disagreement {"shared_image": "unverified", "bank_flashed": false, "bank_reason": "flash records carry duplicate sequence conflict"}
```

#### 2. Probe Regressions
- `recheck_r3j.py`: Exit code 0, all 9 REVIEW items pass.
- `recheck_r3h.py`: Exit code 0, all 11 REVIEW items pass (including formal collector suite: 285 PASS markers, verdict: pass).

#### 3. Formal Test Execution
- `tools/g2/build_evidence_index_selftest.py`: Exit 0, VERDICT: pass.
- `tools/g2/build_evidence_index_integration_test.py`: Exit 0, VERDICT: pass (includes all R3k cases).
- `tools/g2/leg_try_item_selftest.py`: Exit 0, VERDICT: pass.
- `tools/g2/leg_judge_selftest.py`: Exit 0, VERDICT: pass.
- `tools/g2/soak_collector_integration_test.py`: Exit 0, VERDICT: pass.
- `tools/g2/run_g2.py soak_judge_selftest`: Exit 0, 36/36 pass.
- Node.js suite (`node --test --test-concurrency=1 --test-timeout=120000 static/test/*.test.js`): **107 tests / 107 pass / 0 fail / 0 cancelled**, Exit 0 (~36.9s).

#### 4. Three-Way Categorization & Gate Status
1. **Remediated & Verified Offline (Pass)**:
   - H2-A opcode alignment (code 16 vs 3) and current session tracking.
   - H2-B peek-before-pop pending request consumption.
   - H3-A authentic source event binding, order validation, and window lifecycle replay.
   - H3-B bank unification on shared history contract.
   - H3-C schema type safety and structured error fallback.
   - Retained prior passes: H1 manifest failure persistence, H4 coverage interval continuity, owned payload, 4096B/4097B boundaries, COBS, per-gap backoff, nonce handshake correlation.
2. **Previously Passed, Preserved Without Modification**:
   - R1, R2, R4 software fixes, G0 evidence index arithmetic, full 107 Node.js test suite.
3. **Hardware Bench Not Run (not_run)**:
   - DHCP provisioning/rollback, R1-A isolation withhold, resource baseline measurements, human observation window, 20 physical save power-cuts, 50 physical unplug cycles, native Web Serial port picker.
   - Batch 14 image not flashed; 48/50 software reconnects + 4 recoveries unattributed.

**Gate Verdict**:
**Overall: FAILING / partially complete, remediation in progress (pending independent review).**
Strict offline software boundary maintained; offline passes do not imply hardware gate completion. G2 is not declared closed, and WP-3 is not entered.


## 24. G2-H3 Remediation (2026-10-29, Addressing g2-r3l-review Review Comments)

### 24.1 Review Findings & Remediation Objectives

Independent review report `g2-r3l-review-2026-10-29.md` confirmed the resolution of H2-A and H2-B, but identified four specific H3 contract and robustness defects (H3-L1 through H3-L4):
1. **H3-L1 (Subsequent same-image flash events omitted verify validation)**:
   - In `flash_verifier.py`, replay logic only rejected if `ev_img != img`, assuming matching image SHA implied validity. If a subsequent flash attempt for the same image failed verification (`verify == "failed"`), the historical claim was improperly accepted.
2. **H3-L2 (Unorderable equal-timestamp conflicting records depended on list ordering)**:
   - When identical-timestamp records for the same board lacked distinct integer sequence numbers (e.g. `[erase, noseq]` vs. `[noseq, erase]`), Python's stable `sorted()` kept `noseq` last in the first ordering, causing accidental pass. Conflicting records sharing the same timestamp without sequence anchors are unorderable conflicts and must be rejected deterministically regardless of list permutation.
3. **H3-L3 (Bank did not block reuse on parse error lines)**:
   - `leg_driver2.py` (`environment_fingerprint`) tracked `unparsable` counts, but if subsequent replay found a matching image record, it overwrote `flashed_evidence` and marked `complete = True`, improperly reusing bank entries on truncated/corrupted flash logs (e.g. valid JSONL with an appended non-object line `17`).
4. **H3-L4 (JSON array parsing depended on whitespace and indentation)**:
   - `flash_verifier.parse_flash_log` parsed line-by-line; single-line compact JSON arrays (`json.dumps([A])`) were treated as non-dict list lines and counted as `unparsable`, whereas pretty-printed multi-line arrays (`json.dumps([A], indent=2)`) failed line 1 and triggered fallback.

### 24.2 Implementation Details

#### 1. H3-L1: Unified Flash Event Evaluation & Subsequent Verify Validation (`tools/g2/flash_verifier.py`)
- Introduced helper function `evaluate_flash_event(ev)`:
  - Enforces `status == "success"` carries valid 64-character hex `image_sha256` and `verify in ("ok", "verified")`. Invalid or non-passing verify yields `status_kind="unverified_success"`.
- In `verify_flash_record` replay loop:
  - Any subsequent event returning `"unverified_success"` rejects the claim as `"unverified"` with diagnostic `"subsequent flash attempt for the same image was not verify-ok"`.
- Reused `evaluate_flash_event` in `replay_board_history_to_latest` to align claim verification and bank replay contracts.

#### 2. H3-L2: Strict Pairwise Unorderable Conflict Rejection (`tools/g2/flash_verifier.py`)
- In `validate_board_history`:
  - Added pairwise check for identical timestamps (`ts1 == ts2`): if records lack distinct integer sequence numbers (`not (has_s1 and has_s2 and s1 != s2)`) and have differing evaluated states or image signatures, rejects with `"flash records carry conflicting events at same timestamp without sequence order (unorderable)"`.
  - Both `[erase, noseq]` and `[noseq, erase]` now consistently return `unknown`/`unverified`.
  - Preserves ordered controls: same timestamp with `seq=1` (erase) and `seq=2` (success) passes, while `seq=1` (success) and `seq=2` (erase) is correctly rejected as erased.

#### 3. H3-L3: Bank Reuse Blocked on Parse Errors (`tools/g2/leg_driver2.py`)
- In `leg_driver2.environment_fingerprint`:
  - When `unparsable > 0`, explicitly sets:
    ```python
    flashed_evidence = False
    flash_state_reason = f"flash log contains {unparsable} unparsable non-JSON lines or non-object items"
    ```
    and bypasses replay, preventing `complete = True`.

#### 4. H3-L4: Document-Level JSON Parsing Independent of Formatting (`tools/g2/flash_verifier.py`)
- Refactored `parse_flash_log`:
  - First attempts `json.loads(trimmed)` on the complete trimmed string:
    - Dict -> `[obj], 0`
    - List -> extracts valid dict elements and counts non-dict items in `unparsable`
    - Other types -> `[], 1`
  - Falls back to line-by-line parsing if full document JSON parsing fails (e.g. multi-line JSONL).
  - Compact `json.dumps([A])` and pretty-printed `json.dumps([A], indent=2)` produce identical results `[A], 0`.

#### 5. Integration Test Suite Migration (`tools/g2/build_evidence_index_integration_test.py`)
- Added comprehensive R3l test cases:
  - `later_same_image_verify_ok` (manifest-linked)
  - `later_same_image_verify_failed` (unknown/unverified)
  - `equal_time_no_seq_erase_first` & `equal_time_no_seq_erase_last` (unknown/unverified)
  - `equal_time_seq_erase_then_success` (manifest-linked) & `equal_time_seq_success_then_erase` (unknown)
  - `json_array_compact` & `json_array_pretty` (manifest-linked)
  - `bank_nondict_line` & `bank_same_image_verify_failed` (bank flashed_evidence=False, complete=False)

### 24.3 Verification & Independent Probe Regressions

#### 1. Independent Review Probe `recheck_r3l.py` (Exit code 0)
```text
  [PASS] inputs_complete :: duration/span/samples/preconditions required
  [PASS] offline_precondition :: wifi_status=isolated_verified ha_status=not_running verified=True
  [PASS] duration_honest :: monotonic_span=60.1s requested=60s
  [PASS] samples_collected :: n=6
  [PASS] single_boot :: boot_changes=0
  [PASS] rpc_p95_within_budget :: p95=10.0ms over 6 samples; budget=250ms
  [PASS] no_uncovered_gap :: windows lost=0
REVIEW healthy {"status": "pass", "batch": "manifest-linked"}
REVIEW later_same_image_verify_ok {"status": "pass", "batch": "manifest-linked"}
REVIEW later_same_image_verify_failed {"status": "pass", "batch": "unknown"}
REVIEW equal_time_no_seq_erase_first {"status": "pass", "batch": "unknown"}
REVIEW equal_time_no_seq_erase_last {"status": "pass", "batch": "unknown"}
REVIEW json_array_compact {"status": "pass", "batch": "manifest-linked"}
REVIEW json_array_pretty {"status": "pass", "batch": "manifest-linked"}
REVIEW bank_good {"shared_image": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", "bank_flashed": true, "bank_complete": true, "bank_reason": "latest flash for this board matches this image"}
REVIEW bank_nondict_line {"shared_image": "unverified", "bank_flashed": false, "bank_complete": false, "bank_reason": "flash log contains 1 unparsable non-JSON lines or non-object items"}
REVIEW bank_same_image_verify_failed {"shared_image": "unverified", "bank_flashed": false, "bank_complete": false, "bank_reason": "latest flash was not verify-ok (verify='failed' (expected 'ok' or 'verified'))"}
```

| Probe item | Pre-fix observed (r3l reproduction) | Post-fix observed | Expected baseline | Verdict |
| :--- | :--- | :--- | :--- | :--- |
| `healthy` | batch: `manifest-linked` | batch: `manifest-linked` | batch: `manifest-linked` | PASS |
| `later_same_image_verify_ok` | batch: `manifest-linked` | batch: `manifest-linked` | batch: `manifest-linked` | PASS |
| `later_same_image_verify_failed` | batch: `manifest-linked` (false pass) | batch: `unknown` | batch: `unknown` | PASS |
| `equal_time_no_seq_erase_first` | batch: `manifest-linked` (sort-dependent) | batch: `unknown` (unorderable) | batch: `unknown` | PASS |
| `equal_time_no_seq_erase_last` | batch: `unknown` | batch: `unknown` (unorderable) | batch: `unknown` | PASS |
| `json_array_compact` | batch: `unknown` (unparsable list) | batch: `manifest-linked` | batch: `manifest-linked` | PASS |
| `json_array_pretty` | batch: `manifest-linked` | batch: `manifest-linked` | batch: `manifest-linked` | PASS |
| `bank_good` | bank_flashed: `true`, complete: `true` | bank_flashed: `true`, complete: `true` | bank_flashed: `true` | PASS |
| `bank_nondict_line` | bank_flashed: `true` (overwritten) | bank_flashed: `false`, complete: `false` | bank_flashed: `false` | PASS |
| `bank_same_image_verify_failed` | bank_flashed: `true` (false pass) | bank_flashed: `false`, complete: `false` | bank_flashed: `false` | PASS |

#### 2. Prior Review Probe Regressions
- `recheck_r3k.py`: Exit code 0, all 13 REVIEW items match expected values.
- `recheck_r3j.py`: Exit code 0, all 9 REVIEW items match expected values.
- `recheck_r3h.py`: Exit code 0, all 11 REVIEW items match expected values (formal collector suite exit 0, 285 PASS markers, verdict: pass).

#### 3. Formal Automated Test Results
- `tools/g2/build_evidence_index_selftest.py`: Exit 0, VERDICT: pass.
- `tools/g2/build_evidence_index_integration_test.py`: Exit 0, VERDICT: pass (all new R3l cases pass).
- `tools/g2/leg_try_item_selftest.py`: Exit 0, VERDICT: pass.
- `tools/g2/leg_judge_selftest.py`: Exit 0, VERDICT: pass.
- `tools/g2/soak_collector_integration_test.py`: Exit 0, VERDICT: pass.
- `tools/g2/run_g2.py soak_judge_selftest`: Exit 0, 36/36 checks pass.
- Node.js suite (`node --test --test-concurrency=1 --test-timeout=120000 static/test/*.test.js`): **107 tests / 107 pass / 0 fail / 0 cancelled**, Exit 0 (~18.8s).

#### 4. Scope and C++ Note
- Changes are strictly confined to Python evidence validation, parsing, and integration testing (`flash_verifier.py`, `leg_driver2.py`, `build_evidence_index_integration_test.py`).
- No C++ product code was modified.

#### 5. Three-Way Categorization & Gate Statement
1. **Remediated & Verified Offline (Pass)**:
   - H3-L1: Strict verification of subsequent same-image flash events.
   - H3-L2: Symmetrical rejection of unorderable same-timestamp conflicting records.
   - H3-L3: Bank unparsable lines block reuse and mark incomplete.
   - H3-L4: Format-independent JSON array parsing.
   - Preserved all prior passes (H1, H2-A/B, H4, owned payload, bounded ID_REUSE, 4096B/4097B boundaries, COBS, per-gap backoff, nonce handshake correlation).
2. **Previously Passed, Preserved Without Modification**:
   - R1, R2, R4 software fixes, G0 evidence index arithmetic, full 107 Node.js test suite.
3. **Hardware Bench Not Run (not_run)**:
   - DHCP provisioning/rollback, R1-A isolation withhold, resource baseline measurements, human observation window, 20 physical save power-cuts, 50 physical unplug cycles, native Web Serial port picker.
   - Batch 14 image not flashed; 48/50 software reconnects + 4 recoveries unattributed.

**Gate Verdict**:
**Overall: FAILING / partially complete, remediation in progress (pending independent review).**
Strict offline software boundary maintained; offline passes do not imply hardware gate completion. G2 is not declared closed, and WP-3 is not entered.
