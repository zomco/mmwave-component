# WP-0 / WP-1 phase report

Date: 2026-10-19 (initial draft 2026-10-18). Packages: WP-0 and WP-1 (including G0 hardware verification closure and G1 contract closure). Committed or published: no. Current Phase Verdict: **G1 Freeze Candidate, Pending Independent Acceptance (All `DD-01`..`DD-15` Closed, including User-Approved & Applied `DD-07` C2 & `DD-08` C2)** (Sections 1–20 preserve historical round logs; G0 hardware verification and G1 contract closure are governed by Sections 21–22 and [`g0-evidence-index.json`](./g0-evidence-index.json)).

[中文](wp0-wp1-phase-report_CN.md)

## 1. Baseline

| Item | Value |
| --- | --- |
| Workspace | `468b4144a0653c5adde66351a2d8f7e94a0763c8` on `main`, the design commit |
| mmwave-component | `f01ac84fa72dd5b3f479cb1e674572f5cea95c1b` |
| mmwave-card | `5799d5729dd8bf6ee6114038bc989c2be1a35cf0`, read only |
| Node | v22.13.1, npm 11.17.0 |
| esp-web-tools | lockfile resolves 10.4.0; `package.json` still says `^10.1.1`. Lockfile not changed |
| improv-wifi-serial-sdk | 2.8.0, transitive |
| esptool-js | 0.6.0, transitive; the app does not depend on it directly |
| ESPHome / ESP-IDF | Unpinned. CI uses `esphome/build-action@v7` default `latest`. `esphome` is not installed here. See DD-02 |
| Host C++ | `D:\Build\mingw64\bin\g++.exe` 13.3.0, `-std=c++14 -fno-exceptions -fno-rtti -static` |

Existing enclosure edits were left untouched. This phase did not reset files or edit `cases/`, enclosure skills, mmwave-fusion, mmwave-engine, mmwave-desktop, or mmwave-card. Pre-existing untracked `docs/rd03/*.step` and `docs/rd03d/*.step` were not touched.

## 2. Files

Added only. Not wired into the installer page and not registered as an ESPHome component:

| Path | Purpose |
| --- | --- |
| `static/src/protocol/` | DOM-free JS codec, strict JSON, client, in-memory simulator, transform, flash handoff |
| `static/test/protocol-*.test.js`, `flash-handoff.test.js` | Host tests |
| `protocol/cpp/` | Independent C++14 codec and host test |
| `protocol/fixtures/json-cases.json` | Shared JSON expected results for JS and C++ |
| `static/protocol-browser.html`, `protocol-browser-entry.js`, `vite.protocol.config.js` | Browser `ProtocolClient` entry. Not the installer page |
| `docs/protocol/` | Draft schema, R60 fixture, coordinate vectors, review diffs |
| `docs/reviews/web-console/` | This report and the uncompiled G0 probe YAML |

`static/src/App.jsx` was not modified. The simulator is not loaded by the current site.

## 3. G0

No board, port, flash permission, or network scope was named. No serial device was opened, reset, or flashed.

| ID | Status | Evidence |
| --- | --- | --- |
| G0-01 | not_run | Source shows PC path is ESP32-C3 native USB Serial/JTAG. Radar UART is GPIO21 TX to radar RX and GPIO20 RX from radar TX. R60 baud is 115200 on that UART, not the PC `port.open` baud. Catalog art is `reference-concept`. `r60abd1.cpp` has one `loop()` UART reader. No enumerated device or photo. |
| G0-02 | not_run | Production logger is pinned to `USB_SERIAL_JTAG`, and shared `_device.yaml` also enables `improv_serial`. That is two USB consumers. The probe YAML was not compiled. Logger callbacks after `baud_rate: 0` were not measured. |
| G0-03 | not_run | Current YAML does not set Wi-Fi/API `reboot_timeout: 0s`. Source predicts an offline reboot. No 2-hour run. |
| G0-04 | not_run | Version 10.4.0 source confirms `closed` is not a completed `port.close()`, and install completion reopens the port for Improv. Browser success, failure, cancel, close, and unplug paths were not run. The handoff proposal is DD-01. Fake-port tests do not prove the OS released the port. |
| G0-05 | not_run | No heap, stack, loop, or dropped-frame comparison. Static buffer caps in section 6 are not device measurements. |

G0 did not pass. Hardware-independent WP-1 draft work continued. The protocol is not frozen.

## 4. WP-1 delivered

- Draft JSON Schema for registered requests, results, events, and the closed error-code list. `AUTH_REQUIRED` was not added.
- Separate JS and C++ codecs. Both read `protocol-vectors.json` and compare bytes. They do not encode with one library and decode with the same library as proof.
- Strict JSON: no BOM, no duplicate keys, depth, safe integers, invalid UTF-8.
- Client and in-memory simulator: handshake, request ids, cache, old session, page conflict, dropped commit then query, no automatic write replay, rate limit, control priority, 1D/2D/empty/unknown/zero. Simulator output is marked `origin: "simulation"`.
- Coordinate vectors include nonzero pitch/roll, negative coordinates, 1D projection along local +Y, and the current ray-cast edge results. The C++ test calls `r60abd1_transform.h`. The JS test checks the card source.

## 5. Commands and results

```text
cd submodules/mmwave-component/static
node --test test/protocol-codec.test.js test/protocol-session.test.js test/protocol-schema.test.js test/protocol-coordinates.test.js test/flash-handoff.test.js
```

Exit code 0. `node --test test/*.test.js` then also exited 0, including the existing installer tests: 29 passed.

```text
D:\Build\mingw64\bin\g++.exe -std=c++14 -fno-exceptions -fno-rtti -static -Wall -Wextra -Werror ^
  -I protocol\cpp -I components\r60abd1 ^
  -o %TEMP%\opencode\mwcp_host_test.exe ^
  protocol\cpp\mwcp_host_test.cpp protocol\cpp\mwcp_codec.cpp protocol\cpp\mwcp_json.cpp
%TEMP%\opencode\mwcp_host_test.exe docs\plans\mmwave-web-console\protocol-vectors.json
```

Output: `mwcp c++ host test passed`, exit code 0.

Reproducible fault: flip the first decoded byte of golden frame `ping-request`, COBS-wrap it, and the parser counts it as corrupt and does not execute; the original golden frame is then delivered. A half frame left idle for 2000 ms on the injected clock is discarded, and a legal frame after the next `00` recovers. Both JS and C++ tests assert this.

## 6. Memory and latency

Not measured on an ESP32. Static caps:

| Buffer | Bytes |
| --- | --- |
| COBS accumulation | 4141 |
| Decoded frame | 4124 |
| Maximum wire including delimiters | 4143 |
| JSON depth / keys / array items | 8 / 64 / 256 |
| `Parser::object()` host stack, `-fno-inline -fstack-usage` | 64 |
| `parse_object()` host stack | 96 |
| `json_check()` host stack, including 512 key spans | 2144 |
| `classify_number()` host stack, `-fno-inline` | 192 |
| `finite_fraction()` host stack, after H2 | 80 |
| `exceeds_double_max()` host stack | 96 |

Before this fix, `object()` contained `bytes[64][192]`. Host g++ `-O2 -fstack-usage` measured that frame at 12976 static bytes in `C:\Users\zomco\AppData\Local\Temp\opencode\mwcp_json_before.su`. It was not 64 pointers. The check path now stores key offsets in the one `Parser` and compares decoded Unicode, including `\u` escapes. Nested `object()` calls restore the span count, so they do not keep a per-call 12 KiB table. A 252-byte unique key is accepted. Long numbers are scanned in place; `digits[128]` and `tmp[96]` are gone. The overflow check does not treat “greater than `DBL_MAX`” as non-finite. binary64 round-ties-to-even overflows only at `2^1024 - 2^970`. The digit string is `protocol/fixtures/double-overflow-threshold.txt`, checked against that formula. It no longer calls `strtod`. A depth-8 number path sums the measured frames to 4368 bytes, or 4416 if `span_digit` (48) is also live. That sum does not include unmeasured libc frames; this path does not call `strtod`. At `-O2`, `json_check` is 2144 and `value` is 272. These figures are host g++ 13.3.0, not ESP32 measurements. There is still no device RPC sample, so the architecture latency budget is unverified.

## 7. Passed, simulation-only, still needs hardware

Passed: golden-vector cross-check, COBS/CRC/sticky frames/noise recovery, schema and R60 fixture checks, in-memory session and config-conflict tests, coordinate source comparison.

Simulation only: handshake, pagination, dropped-commit query, rate limit, priority, 1D/2D semantics. The simulator is marked `simulation` and is not a device.

Still needs hardware: all of G0-01 through G0-05, real R60 timing, the five browser installer paths, heap/stack/loop, and a long run without Wi-Fi.

## 8. Differences, failures, not run

DD-01 through DD-13 are in `docs/protocol/design-differences.md`, all awaiting review. No failing test was deleted.

The F1–F5 rerun had no failed assertion, but its browser cleanup could hang. Section 12 corrects that. Still not run: G0-01 through G0-05, firmware compilation, ESP32 stack/heap, Ubuntu browser, a live GitHub Actions run, and the five installer browser flash paths. The protocol browser check is a local loopback, not a serial device.

Needed from the user: a named ESP32-C3 board, confirmation that its USB port is native rather than a UART bridge, radar wiring, a port that may be flashed, and a disposable test network. No device will be opened or flashed without that authorization.

Secret check: the probe and this report contain no Wi-Fi password, API key, or OTA password. Provisioning was not implemented on a firmware path that could store a password.

## 9. Remediation R1–R9

This is a software regression fix. It is not a G0 pass and it does not freeze the protocol.

| Item | Cause | Fix | Regression | Result |
| --- | --- | --- | --- | --- |
| R1 | `object()` called `string()` after `skip()` without checking `i_ < len_` | Bounds checks in `protocol/cpp/mwcp_json.cpp` | `test_json_bounds_and_duplicates`, including a Windows `VirtualProtect` guard page | C++ host test exit 0. No `0xC0000005` |
| R2 | Tests read the parent golden file and the sibling card | Component copy `protocol/fixtures/protocol-vectors.json`; card check moved to workspace `tests/unit/test_mwcp_sources.py` | Isolated tree `C:\Users\zomco\AppData\Local\Temp\opencode\mwcp-independent\static`, `node --test test/*.test.js` | Exit 0, 37 passed |
| R3 | Default `createClock()` never advances | Default is `createRealClock()`; fake clock must be injected | `real clock times out`, `fake clock is explicit` | Passed. `pending` is empty after timeout, and the next RPC can run |
| R4 | Simulator mutated state before validation; client accepted a request frame as a response | `validateRequest` / `validateResponse` before side effects and RPC completion | `invalid commit and ping`, `late response and request frame` | Missing `op_id` does not increment `writeCount`. A request frame does not complete an RPC |
| R5 | C++ compared raw key bytes; exponent integers took the float path | Both sides compare decoded keys and treat integral `e` / `.0` forms as integers | `duplicate escaped keys` and the same strings in the C++ test | `{"a":1,"\u0061":2}` and `9007199254740993e0` are rejected on both sides |
| R6 | `stale()` subtracted device `sample_ms` from client time | `qualityOf()` uses `sent_ms - sample_ms` plus monotonic time since receive | `freshness uses device sent_ms` | A device already up for an hour can still show a just-received sample as valid |
| R7 | Subscribe echoed the budget; `events` grew without limit | First fix only coalesced telemetry. Section 10 makes every subscribed event share the negotiated wire-byte budget. RPC responses do not count. Client keeps at most 32 events | `telemetry budget`, then `mixed events stay inside 1000 and 8000 byte windows` | Telemetry regression still sends 1 of 100 frames. Mixed events sent 966 bytes and held 10 under a 1000 B/s cap |
| R8 | `SESSION_CLOSE` left the session usable; expiry ran only on the next request | `expire()`; `clock.advance` calls `poll()` | Close and the 15-second idle `emitTelemetry` check in the same test | Old session cannot PING. Expired session does not emit telemetry. Persisted revision is not rolled back |
| R9 | Schema allowed any presence value; `properties[key]` followed the prototype; an assertion used `ok \|\| true` | `presenceSample`, `if/then`, `hasOwn`; response objects set `x-open-object` | `schema rejects bad presence`; an invalid sample for every command | String presence, unknown+true, and `__proto__` fail. The tautology is gone |
| revision | `Number(revision)+1` stalls at 2^53 | `nextRevision()` uses `BigInt` | Same test, `9007199254740992` | Result is `9007199254740993` |

The earlier report said the C++ codec covered noise and half-frame recovery. At that time only the JS test did. `test_parser_noise_and_half_frame` now executes that path.

Host-simulated limits, not ESP32 measurements: every subscribed event shares the negotiated encoded-wire budget; RPC responses do not count and stay priority 0; telemetry, config, and status keep the latest held payload; log queue is 8; held events are capped at 16; client events are 32; parser buffers remain 4141/4124. Device heap was not measured.

Commands:

```text
cd submodules/mmwave-component/static
node --test test/*.test.js
npm run build
```

That earlier `node --test` exited 0 with 37 passed, before the F1–F5 tests existed. `npm run build` of the installer page succeeded and does not prove `ProtocolClient` is browser-safe. The current count is in section 10. The isolated checkout also passed 37 tests at that earlier point; it was not rebuilt for F1–F5.

```text
D:\Build\mingw64\bin\g++.exe -std=c++14 -fno-exceptions -fno-rtti -static -Wall -Wextra -Werror ^
  -I protocol\cpp -I components\r60abd1 ^
  -o %TEMP%\opencode\mwcp_host_test.exe ^
  protocol\cpp\mwcp_host_test.cpp protocol\cpp\mwcp_codec.cpp protocol\cpp\mwcp_json.cpp
%TEMP%\opencode\mwcp_host_test.exe protocol\fixtures\protocol-vectors.json
```

Exit 0. The guard-page test is inside that executable.

## 10. Acceptance F1–F5

Software regressions only. Not a G0 pass and not a protocol freeze.

| Item | Cause | Fix | Regression | Result |
| --- | --- | --- | --- | --- |
| F1 | `contract.js` read the schema with `node:fs`; the installer build never loaded `ProtocolClient` | JSON import of `docs/protocol/schema/mwcp-v1.schema.json`. Browser entry does not import `simulator.js`, which still uses `node:crypto` | `protocol-browser.test.js` | One Windows run completed HELLO/PING, but cleanup waited on `server.close()` while Chrome still held the socket. That hang is G1, not evidence that the browser path is reliable |
| F2 | `object()` reserved `bytes[64][192]`, 12976 static bytes | Span offsets in the one `Parser`; decoded-key compare | C++ host test, including the guard page, plus the 252-byte key and `\u00e9` cases | `object()` 64, `parse_object()` 96, `json_check()` 2144. Host only |
| F3 | Exponent underflow and oversized integers could disagree, and `1e999` was labeled `number` | Shared `protocol/fixtures/json-cases.json`, 26 cases, read by JS and C++ | `shared JSON fixture` and `test_shared_json_cases` | `1e-2`, `1.2e-3`, `0.01`, `1e-1` accept. `9007199254740993e0`, `9007199254740993.0`, and `1e999` are `unsafe_integer` |
| F4 | Budget and rate limit covered telemetry only. `bumpExternal` after an explicit `expire()` could throw | All subscribed events share wire bytes. RPC is priority 0 and is not counted | Mixed-window test and explicit `expire()` | Those tests did not advance the clock without `poll()`. Natural expiry still sent `CONFIG_CHANGED`. Corrected in section 12 |
| F5 | A successful `write()` refreshed liveness, and expiry depended on `link()` calling `client.poll()` | Client arms its own 15s timer only after HELLO/RPC response. Heartbeat stays 5s. No side-effect replay | `client liveness does not treat a successful write`, `successful pings keep the session` | Dropped replies go offline. Successful pings over 20s stay online. Telemetry alone does not renew. A later PING rejects `session_expired` |

```text
cd submodules/mmwave-component/static
node --test test/*.test.js
```

Exit 0. 43 passed, including the headless Chrome test.

```text
D:\Build\mingw64\bin\g++.exe -std=c++14 -fno-exceptions -fno-rtti -static -Wall -Wextra -Werror ^
  -I protocol\cpp -I components\r60abd1 ^
  -o %TEMP%\opencode\mwcp_host_test.exe ^
  protocol\cpp\mwcp_host_test.cpp protocol\cpp\mwcp_codec.cpp protocol\cpp\mwcp_json.cpp
%TEMP%\opencode\mwcp_host_test.exe protocol\fixtures\protocol-vectors.json
```

Output: `mwcp c++ host test passed`, exit 0.

```text
D:\Build\mingw64\bin\g++.exe -std=c++14 -fno-inline -fstack-usage -fno-exceptions -fno-rtti -Wall -Wextra -Werror -c ^
  -I protocol\cpp -o %TEMP%\opencode\mwcp_json_noinline.o protocol\cpp\mwcp_json.cpp
```

`object()` 64, `parse_object()` 96, `json_check()` 2144. Not an ESP32 measurement.

## 12. Acceptance G1–G4

Not a G0 pass and not a protocol freeze. Host tests and one Windows browser run passed. Ubuntu and GitHub Actions were not executed here.

| Item | Cause | Fix | Regression | Result |
| --- | --- | --- | --- | --- |
| G1 | Browser test hardcoded `C:\Program Files\Google\Chrome\Application\chrome.exe` and called `taskkill` without waiting. `finally` awaited `server.close()` while Chrome still held the HTTP connection, so the suite could hang. Pipes had no timeout | `static/test/browser-harness.js` discovers `MWCP_CHROME`, common Windows/Linux paths, or `which`. Spawn uses `stdio: ignore`. Timeouts cover build, start, CDP, and page result. Cleanup kills only the spawned process tree, destroys sockets, then closes the server. `web.yml` and `publish-pages.yml` install Chrome with `browser-actions/setup-chrome@v2` and run `npm run test:unit` and `npm run test:browser` | Windows `node --test --test-timeout=20000 test/protocol-browser.test.js`; invalid executable test | Windows browser test exit 0 in 8.5s. Body had `"ok":true`. Invalid path failed in about 20ms and left no live process. Full `npm test` exit 0, 50 passed, process exited. Ubuntu: not_run. WSL failed to start (`networkingMode Mirrored`, `0x8007054f`) and `docker version` did not return. GitHub Actions run: not_run |
| G2 | A new `hello()` left the old 15s timer. `expireLocal()` rejected the new handshake. `hello()` also cleared `sessionLive` before noticing `rpc_inflight` | `endSession()` bumps `generation` and clears heartbeat and liveness before a new hello, but only after the pending check. Timer and timeout callbacks no-op when the generation or pending slot changed. Side-effect requests are still not retried | `protocol-g-fixes.test.js` | 14.9s rehandshake, delayed old callback, in-flight `hello()`, failed hello retry, and old heartbeat overlap passed |
| G3 | `classify_number()` copied into `digits[128]` and `tmp[96]`, rejecting legal numbers under the 4096-byte payload cap | Scan the input in place. Integer width is counted without a large buffer. Non-integers use a 40-byte scientific probe only for the finite check | Shared `json-cases.json`, read by JS and C++ | `0.` + 100 zeros + `1` (109 bytes) and `1.` + 150 zeros (158 bytes) accept. A 4090-byte `1.` + zeros accepts. `9007199254740993` with a long `.0` tail is `unsafe_integer`. `1.` + 400 zeros + `1e400` is `number`. C++ host test exit 0, including guard page, Unicode duplicate keys, noise, and half-frame recovery |
| G4 | Event send checked that a session object existed, not that `now` was still inside its 15s deadline. Tests called `poll()` or `expire()` | `sessionAlive()` is used by `offerEvent` and `releaseEvents`. A session timer expires without `poll()`. A release timer sends a held event when the budget window opens, then expiry drops anything still held. `disconnect()`, close, unsubscribe, and a new nonce clear old events. Config state is still updated | Direct client and device, clock advanced 16000ms, no `poll()` or `expire()` | Session, subscriptions, and held events were cleared. `bumpExternal` updated `install.x_cm` and sent 0 more event bytes. Status, jobs, and logs were not sent. A rate-held telemetry frame was sent at the next window, then dropped after expiry |

```text
cd submodules/mmwave-component/static
node --test --test-timeout=20000 test/protocol-browser.test.js
npm test
npm run build
```

Browser command exit 0. `npm test` exit 0, 50 passed. `npm run build` exit 0.

```text
D:\Build\mingw64\bin\g++.exe -std=c++14 -fno-exceptions -fno-rtti -static -Wall -Wextra -Werror ^
  -I protocol\cpp -I components\r60abd1 ^
  -o %TEMP%\opencode\mwcp_host_test.exe ^
  protocol\cpp\mwcp_host_test.cpp protocol\cpp\mwcp_codec.cpp protocol\cpp\mwcp_json.cpp
%TEMP%\opencode\mwcp_host_test.exe protocol\fixtures\protocol-vectors.json
```

Output: `mwcp c++ host test passed`, exit 0.

```text
python -m unittest tests.unit.test_mwcp_sources -v
```

Exit 0, 2 tests, from the workspace. This test reads the sibling card; the isolated component run does not.

Isolated tree `C:\Users\zomco\AppData\Local\Temp\opencode\mwcp-g4-isolated` contains this component's protocol, schema, transform header, and static tests. `npm ci` was run there. `node --test --test-timeout=120000 test/*.test.js` exit 0, 50 passed. The same g++ host command exit 0. It does not use the parent design files or a sibling repository.

No new npm dependency. The lockfile was not changed.

## 13. G-round conclusion

This paragraph records the G1–G4 round only. It is not the current coverage claim. That round had host regressions and one Windows Chrome loopback. Ubuntu and GitHub Actions were not_run. Section 14 is the later H1–H3 round.

## 14. Acceptance H1–H3

Not a G0 pass and not a protocol freeze. The earlier 50/50 result did not cover these boundary cases.

| Item | Cause | Fix | Regression | Result |
| --- | --- | --- | --- | --- |
| H1 | `handleFrame()` accepted a response if the timeout callback had not run. A suspended clock could complete a late PING and refresh liveness. Old timer callbacks also cleared `livenessTimer` / `heartbeat` before checking generation | Requests and the session store absolute deadlines. Receive, poll, and new RPC check `now >= deadline` even if no callback has run. Callbacks check generation and timer identity before clearing the current handle | `protocol-h-fixes.test.js`, using `clock.jump()` | t=0 HELLO, t=14000 PING, jump to 30000, late PING rejected, `sessionLive` false, `lastResponseAt` stayed 0. Request-only timeout, exact session boundary, late HELLO, callback-before-response, old callback versus new handle, telemetry-only, and heartbeat all passed |
| H2 | `finite_fraction()` truncated to 17 digits and called `strtod`. The 330-byte input is Infinity in JS and was accepted by C++ | First fix compared with exact `DBL_MAX`. That is not the JS rounding threshold. Section 16 uses `2^1024 - 2^970` | Shared `json-cases.json` | The 330-byte input stays `number`. The 329-byte input that rounds to a finite maximum is accepted. See section 16 |
| H3 | CDP `send()` had no command timeout, and close/error did not reject pending commands. `--test-skip-pattern protocol-browser` did not match the test name, so `test:unit` still launched Chrome | `connectCdp()` times out each command and rejects pending commands on close/error. Browser tests moved to `test/browser/`. `test:unit` is `test/*.test.js` only. `npm test` runs unit and browser once each. CI still runs both scripts | `protocol-cdp.test.js` and `test:unit` / `test:browser` | Hung command, close, error, late response, and empty page failed within their deadlines. `MWCP_CHROME=mwcp-missing-browser npm run test:unit` exit 0, 59 passed, no browser launch. The same env `npm run test:browser` exit 1, `ENOENT`, not a false pass. Normal Windows `npm run test:browser` exit 0 |

```text
cd submodules/mmwave-component/static
$env:MWCP_CHROME='mwcp-missing-browser'; npm run test:unit
$env:MWCP_CHROME='mwcp-missing-browser'; npm run test:browser
Remove-Item Env:MWCP_CHROME
npm run test:browser
npm test
npm run build
```

Invalid-browser unit exit 0, 59 passed. Invalid-browser browser command exit 1. Normal browser command exit 0. `npm test` exit 0, 61 passed. `npm run build` exit 0.

C++ host test: `mwcp c++ host test passed`, exit 0. `python -m unittest tests.unit.test_mwcp_sources -v` exit 0, 2 tests.

Isolated tree `C:\Users\zomco\AppData\Local\Temp\opencode\mwcp-h3-isolated`: `npm ci`, then Node 61 passed and the g++ host test passed. It does not read parent design files or a sibling repository.

No new npm dependency. Lockfile unchanged.

## 15. Conclusion

H1 and H3 passed the later recheck. The H2 row above is corrected in section 16. H3 also has a Windows headless Chrome HELLO/PING result. Ubuntu browser and a live GitHub Actions run remain not_run. G0-01 through G0-05 remain not_run. The protocol is not frozen. WP-2/WP-3 must not start. Nothing was committed, pushed, flashed, or published. This returns to the original designer for an independent review.

## 16. H2 rounding boundary

H1 and H3 passed the designer’s recheck. The previous H2 row is not the current rule: comparing with the exact decimal of `DBL_MAX` rejects some values that `Number()` rounds to a finite maximum.

Cause: round-ties-to-even overflows when the exact value is at least the midpoint `(DBL_MAX + 2^1024) / 2 = 2^1024 - 2^970`, not when it merely exceeds `DBL_MAX`.

Failing input that must be accepted: `1.7976931348623158` + 300 zeros + `1e308`, payload 329 bytes. JS `Number()` is `1.7976931348623157e+308`, finite. The previous 330-byte input with an extra `9` remains `Infinity` and is rejected as `number`.

The threshold digits are generated from that formula, stored in `double-overflow-threshold.txt`, and checked by the JS test. The C++ host test checks that `json_overflow_threshold()` matches the file. Integers outside `±(2^53-1)` are still `unsafe_integer`.

New shared cases include the 329-byte accept, its negative, `e+308`, `E308`, a shifted decimal point, a non-integer just below the midpoint, and a non-integer just above it. Accept cases also assert that JS conversion is finite. Rejected overflow cases assert `number`, not merely that both sides agree.

Stack frames did not grow: `overflows_binary64` 96, `finite_fraction` 80, `json_check` 2144. `-O2` `value` remains 272. Host only.

`npm run test:unit` exit 0, 59 passed. `npm run test:browser` exit 0, 2 passed. `npm test` exit 0, 61 passed. `npm run build` exit 0. C++ host test exit 0. Workspace `test_mwcp_sources` exit 0, 2 tests.

Ubuntu, GitHub Actions, and G0 remain not_run. Protocol is not frozen. Nothing was committed or flashed.

## 17. G0 preparation

G0 is **not complete**. No hardware authorization, no port opened, no flash. Passing software tests is not a G0 pass. This is not ready for a G1 review.

| Item | Status | Evidence |
| --- | --- | --- |
| G0-01 | not_run | No board photo, schematic, or measured USB path |
| G0-02 | not_run | Host YAML compiled on pinned ESPHome; see section 18. It was not run on a device, so USB exclusivity is unproven |
| G0-03 | not_run | No two-hour offline run |
| G0-04 | not_run | No flash success, failure, cancel, close, or unplug |
| G0-05 | not_run | No heap, stack, or latency comparison |

Baseline: workspace `468b4144a0653c5adde66351a2d8f7e94a0763c8`, component `f01ac84fa72dd5b3f479cb1e674572f5cea95c1b`, plus uncommitted protocol/G0 files. Node v22.13.1, npm 11.17.0, Python 3.14.7, esp-web-tools lockfile 10.4.0. `esphome` is not on PATH; the isolated install is in section 18. `esp32-c3-devkitm-1` is a compile placeholder only.

Prepared files are under `docs/reviews/web-console/g0/`: `baseline.yaml`, `host.yaml`, `components/mmwave_host/`, `RUN.md`. Diagnostic page: `static/g0-diag.html`. `node --test test/g0-diag.test.js` exit 0 is a simulator self-test.

Stop: the user must name the board, USB path, R60 wiring, port VID/PID, whether it is a disposable test unit, which firmware may be flashed, whether the current firmware must be kept, and that full-chip erase stays forbidden by default. No device will be opened before that.

## 18. G0-R software remediation

G0 is still not complete. This section records software compile and host regressions only. No port was opened and nothing was flashed. Link-time size is not G0-05.

Isolated toolchain: `esphome==2026.9.1`, ESP-IDF 5.5.5, riscv32-esp-elf GCC 14.2.0 (`esp-14.2.0_20260121`), bundled esptool.py 4.12.0. Builds stayed in a temp directory, not the repo. Both `esphome compile` commands exited 0.

| Firmware | OTA SHA256 | factory SHA256 | Link-time RAM | Link-time flash |
| --- | --- | --- | --- | --- |
| host | `8D5E8A9CFB3C11B1676CE79AD234EF78305F24224050DA2CC1CC6F36144A92D7` | `1F4EFB06EA0A206886926F1FF39B6D52517ED68EA678A9F96D63C4F9F8393300` | 120072 / 321296 | 766826 / 1835008 |
| baseline | `E4E20DD0D8F70E546500251144AA0401A21D1A4A5CAC0C6C3CE1001FDE2B948E` | `E01669731DAB02044B2BF2E25E9F1830C8D9B83ABB98B4BECA213703A733D485` | 102556 / 321296 | 764188 / 1835008 |

Host uses 17516 more RAM bytes and 2638 more flash bytes than baseline. That is link-time size, not runtime heap, stack, or loop time.

| Item | Result |
| --- | --- |
| G0-R1 | C++ namespace is `esphome::mmwave_host::MwcpHost`. The IDF toolchain ignores a plain `-I` build flag, so protocol headers go through `add_cxx_build_flag`. The two protocol sources must be separate translation units; one unity include makes `Parser` ambiguous. Host logger is UART0 with `baud_rate: 0`. `hardware_uart: USB_SERIAL_JTAG` compiles USB init and fails to link against `CONFIG_ESP_CONSOLE_NONE`. sdkconfig has `CONFIG_ESP_CONSOLE_NONE=y`. |
| G0-R2 | `node --test test/g0-diag.test.js` passed 3 tests, exit 0. `npm test` exit 0, 64 passed. Simulator only, not a serial port. |
| G0-R3 | Radar counters use `R60ProbeStats`, not `frame_id_`. `r60_probe_stats_test.cpp` passed and is compiled into the host firmware. Not measured on a device. |
| G0-R4 | Send path uses member buffers and a 64-byte timeout-0 pump. Host test passed and the code is in the host firmware. Not measured on a device. |
| G0-R5 | `boot_id` is MAC plus two `esp_random()` values. Session IDs increment. Diagnostic log cap is 200 and evidence cap is 8000. Compiled, not measured on a device. |

G0-01 through G0-05 remain not_run. The protocol is not frozen. WP-2/WP-3 must not start. Nothing was committed, pushed, or flashed.

## 19. G0-S software preparation

Software preparation **passed**. This is not a G0 hardware pass. The firmware hashes in section 18 are obsolete and do not represent the current code.

| Item | Status | Cause and change | Regression |
| --- | --- | --- | --- |
| G0-S1 | pass | Four `%02x` MAC bytes plus two `%08lx` values made 24 hex characters, so schema `hex32` rejected HELLO. `g0_format_boot_id()` uses 6 MAC bytes and 10 random bytes, and `%02x` keeps leading zeros. The same function builds the HELLO JSON. | Output from `g0_hello_emit` completes a handshake through the existing `ProtocolClient` / `validateResponse`. Truncating it to 24 characters is still rejected. Reboot identity and session isolation are covered. |
| G0-S2 | pass | Disconnect increments a generation. A late select does not open, and a late open is closed. `releaseLock()` follows `cancel()`. A failed close keeps the port. Read and write locks are independent. The page subscribes to state. | `test/g0-diag.test.js` uses real `ReadableStream` / `WritableStream` and `ProtocolClient` on the controller transport. Button clicks trigger the connection. |
| G0-S3 | pass | Capture keeps a start record, measures local monotonic RTT, counts `rpc_inflight` gaps, and truncates with a counter. Unmeasured fields come from device status; healthy or zero is not substituted. Baseline `g0_meter` logs one line every 5s and does not open MWCP. | Capture tests passed. The baseline line is parsed from the firmware formatter. A two-hour device sample remains not_run. |
| G0-S4 | pass | Continuous zero writes are abandoned after 250ms. A partial frame sets resync and the next frame is prefixed with `0x00`. Session end drops the old queue. HELLO clears the queue first and does not switch session if enqueue fails. | `g0_session_test.cpp` covers stall, partial failure, expiry, HELLO while occupied, and parser resync. |
| G0-S5 | pass here; prior failure not reproduced | The failing test was not skipped or weakened. On this machine, Chrome `155.0.8059.84`, `npm run test:browser` passed 2/2 three times in a row. The independently reported `cdp closed` did not recur, its cause is not identified, and the assertion is unchanged. | `npm run test:unit` 65/65, exit 0. C++ `g0_session_test` and `r60_probe_stats_test` exited 0. |

Compile command: isolated `esphome==2026.9.1`, ESP-IDF 5.5.5, `esphome compile` of `docs/reviews/web-console/g0/host.yaml` and `baseline.yaml`, both exit 0. Artifacts are under `C:\Users\zomco\AppData\Local\Temp\opencode\esphome-data\build\`. Link-time size is not runtime heap or stack.

| Firmware | OTA SHA256 | factory SHA256 | Link-time RAM | Link-time flash |
| --- | --- | --- | --- | --- |
| host | `9971612CC6749B7A74EC069E4376A5657F41C48AE4C93DE007167EA584E83C08` | `470F7FEB96B2E8F7F0CB0D3E7A4FAA1B35F208D86BD39A97F76FC63E4A931694` | 120112 / 321296 | 767510 / 1835008 |
| baseline | `D5C7DE3C8986EA531407D936D7023820D4C23591A934166272EAE063B3ACB82C` | `2101FBEFF36C69F59EA9B0B20A22F03C073A6771DD4F03290ECB03AD347C979E` | 102588 / 321296 | 765218 / 1835008 |

Workspace `468b4144a0653c5adde66351a2d8f7e94a0763c8`, component `f01ac84fa72dd5b3f479cb1e674572f5cea95c1b`, plus uncommitted changes. G0 source snapshot hash `89776E4C23A3951825DA9CD4B89628D5A9846B6009BF93B4F0C8EE0B04A4A49A`. Stack high-water is labeled FreeRTOS words because ESP-IDF 5.5.5 `task.h` says words; on this 32-bit target one word is 4 bytes. That is not a device measurement.

| Hardware item | Status |
| --- | --- |
| G0-01 | not_run |
| G0-02 | not_run |
| G0-03 | not_run |
| G0-04 | not_run |
| G0-05 | not_run |

Still required from the user: board and native USB path, R60ABD1 wiring and power, port VID/PID, whether it is a disposable test unit, which firmware may be flashed, whether the current firmware must be kept, and that full-chip erase stays forbidden. No port will be opened and nothing will be flashed before that. The protocol is not frozen. Nothing was committed and WP-2/WP-3 did not start.

## 20. G0-T software remediation

Software preparation **passed** after G0-T1–T4. This is not a G0 hardware pass. Section 19's firmware hashes and its "one word is 4 bytes" stack label are obsolete and superseded here.

| Item | Status | Cause and change | Regression |
| --- | --- | --- | --- |
| G0-T1 | pass | `static/test/g0-hello.test.js` hardcoded `D:\Build\mingw64\bin\g++.exe` and a Windows temp path, so the test could not run on a Linux runner. It now resolves a compiler from `MWCP_GPP` or PATH (`where.exe` / `which`), builds in `mkdtempSync(join(tmpdir(), 'mwcp-g0-hello-'))`, uses `platform()` / `join` / the `.exe` suffix, bounds compile (20s) and run (5s) with `spawnSync` timeouts, and always `rmSync` cleans up. A missing compiler throws instead of skipping. The CI workflows install `g++` and set `MWCP_GPP`. | Firmware emitter output still completes a `ProtocolClient` handshake. |
| G0-T2 | pass | A permanently-pending write left `phase=online`, the port open, and `capture.stopped=false`. `disconnect()` now sets `closing` first, calls `endCapture('disconnect')`, and bounds every wait by `ioWaitMs`. On a stuck write/cancel/close it moves to `error` with guidance `resources held; retry disconnect before connecting again`, retains the port, and rejects to the caller (the page catches it). | `test/g0-diag.test.js` cases "a hung write..." and "cancel and open...". Negative check: removing `endCapture('disconnect')` fails the test. |
| G0-T3 | pass | `sampleOnce` read the global capture after `await`, so a late result polluted the next run; errors and events were unbounded. Each sample is now bound to its run object and generation, `stopCapture` detaches the run, samples roll into bounded segments (`maxSamples` 64, `maxSegments` 120 ≈ 2h at 1 Hz) with a gap count, errors/events are capped (`maxErrors` / `maxEvents` 32) with dropped counters, and `exportEvidence()` reports segments, coverage, `missing`, `gaps`, and `healthy`. | "capture runs do not accept late results and stay bounded": late results land in run A, not run B; 5 forced errors keep 2 and drop 3 with `healthy:false`. |
| G0-T4 | pass | ESP-IDF 5.5.5 RISC-V `portSTACK_TYPE` is `uint8_t`, so `uxTaskGetStackHighWaterMark` returns **bytes**; `stack_high_water_words` with `stack_word_bytes=4` was a 4× overestimate. The fields are now `stack_high_water_bytes`, `stack_high_water_unit:"bytes"`, and `stack_type_bytes:1`; `static_assert(sizeof(StackType_t)==1)` guards both firmwares; evidence is in `docs/reviews/web-console/g0/stack-unit.json`. | C++ and JS assert `600`, reject `2400`, and reject any `stack_word_bytes`. Negative check: a patched words×4 header fails `g0_session_test` with "raw mark is already bytes". |

Commands and results:
- `npm run test:unit` 68/68, exit 0 (was 65; +3 new g0-diag cases).
- `node --test test/g0-diag.test.js test/g0-hello.test.js` 9/9, exit 0 (with `MWCP_GPP`).
- C++ `g0_session_test` and `r60_probe_stats_test` exit 0 (g++ 13.3.0, `-Wall -Wextra -Werror -static-libgcc -static-libstdc++`).
- `npm run test:browser` 2/2, exit 0, Chrome 155.0.8059.84.
- `npm run build` exit 0.
- `esphome==2026.9.1` / ESP-IDF 5.5.5 compiled `host.yaml` and `baseline.yaml`, both exit 0.

| Firmware | OTA SHA256 | factory SHA256 | Link-time RAM | Link-time flash |
| --- | --- | --- | --- | --- |
| host | `DF0DA7283D78E899B478F6092C125528964FABCED6FB4EF49F7B5ACDD8674026` | `72C87C3DB3AAEF9A9C1968F2994365230D63FF33B3D0F50BE7B52A725CE56DD6` | 120112 / 321296 | 767502 / 1835008 |
| baseline | `7E0B7077A8D8A0594184C7F46924BC0A05969BC583F2777E96E0ADDA6CB4D1B8` | `EDD243713F65C6B86DDA7642AF140898A24EABAD804A23E54B17AF14186BB21D` | 102588 / 321296 | 765210 / 1835008 |

Workspace `468b4144a0653c5adde66351a2d8f7e94a0763c8`, component `f01ac84fa72dd5b3f479cb1e674572f5cea95c1b`, plus uncommitted changes. G0 source snapshot hash `E673FFB3717040CACEB19835F245A1ED03C76C62336F4FCD79BC33A5D0D4E114` — SHA256 over the sorted `sha256<space>relative-path` list of the 76 files under `docs/reviews/web-console/g0`, `protocol/cpp`, `static/src/g0`, `static/src/protocol`, `static/test`, `components/r60abd1`, and `docs/protocol/schema/mwcp-v1.schema.json`. That method is written here because the section-18/19 method was not recorded.

Cross-platform execution on Linux/WSL and GitHub Actions was not run here; the test and CI now support it, but the Linux run stays **blocked** until executed. Link-time size is not runtime heap or stack, and none of this is a device measurement.

| Hardware item | Status |
| --- | --- |
| G0-01 | not_run |
| G0-02 | not_run |
| G0-03 | not_run |
| G0-04 | not_run |
| G0-05 | not_run |

The hardware prerequisites are unchanged from section 19 and remain unanswered. No port was opened and nothing was flashed. The protocol is not frozen. Nothing was committed, pushed, or published, and WP-2/WP-3 did not start.

## 21. G0-U software remediation (Round 2 revisions and Round 3 port reuse lifecycle fix)

### Correction notice on approval status
The previous report's statement that "software preparation passed" was **premature** and was formally retracted/corrected based on independent review findings:
1. **U2 residual (close timeout late completion)**: When `port.close()` timed out and subsequently resolved late in the background, a subsequent `disconnect()` call attempted to close an already-closed port, throwing `InvalidStateError` per the Web Serial specification and leaving the controller permanently blocked. Previous tests used an over-simplified stateless mock port that allowed repeated `close()` calls, creating a false negative.
2. **U2 residual (port object reuse lifecycle)**: Close state was previously tracked using `closedPorts = new WeakSet()` permanently tied to the port object. When the same port object was reopened via `connect()`, its old closed status was never invalidated; subsequent `disconnect()` calls hit `closedPorts` and bypassed `port.close()`, leaving the underlying port in `opened` state while the controller reported `closed`, causing a third connect to fail with `streams before open`.
3. **U3 residual (destructive snapshot segmentation)**: `exportEvidence()` internally called `flushSegment(capture)`, forcefully committing uncompleted segments to the bounded segment store. With `maxSamples=2, maxSegments=1`, sampling once -> export -> sample once -> export resulted in the second segment being converted to summary-only with dropped raw samples (`raw=1, summary=1, healthy=false`), diverging completely from uninterrupted sampling (`raw=2, summary=0, healthy=true`). Export frequency corrupted retention capacity and health assessment.

This round provides a complete, robust fix for all residual issues, verified under a strict Web Serial state machine, lifecycle epoch tracking model, and non-destructive snapshot model.

| Item | Status | Root cause and implementation | Regression verification |
| --- | --- | --- | --- |
| G0-U1 | pass | `findCompiler()` executed `existsSync(process.env.MWCP_GPP)`, mistaking command names like `g++` for file paths in current working directory, causing CI workflow `MWCP_GPP=g++` to fail. `resolveCompiler()` now accepts both existing absolute/relative paths and command names resolved via PATH (`which` / `where.exe`). When explicit configuration is invalid or missing from PATH/filesystem, it throws an explicit error immediately rather than silently switching compilers or skipping. `.github/workflows/web.yml` and `publish-pages.yml` document this dual support. | 7-case regression matrix in `static/test/g0-hello.test.js` covers unset auto-discovery, `MWCP_GPP=g++` via PATH, valid absolute path with spaces, invalid path, invalid command name, empty config, and missing compiler. Verified running under actual workflow configuration `MWCP_GPP=g++`. |
| G0-U2 | pass | **Root cause**: <br>1. The controller did not track close operations per port instance. Delayed `port.close()` operations running in the background caused subsequent disconnects to re-invoke `close()` on closing/closed ports, throwing `InvalidStateError`;<br>2. `closedPorts` was a `WeakSet` permanently bound to the port instance. Reopening the same port didn't invalidate the closed status, causing subsequent disconnects to skip `p.close()` and leaving the underlying port opened.<br>**Fix**:<br>1. Introduced open lifecycle epoch model: `portEpochs = new WeakMap()` tracks current open epoch per port, `closedPortEpochs = new WeakMap()` tracks closed epochs, and `portCloseStates = new Map()` tracks `{ epoch, promise, status, error }`;<br>2. In `connect()`, increment the port epoch (`nextEpoch`) prior to `selected.open()`, invalidating any old closed marks for new lifecycles;<br>3. `requestClosePort(p)` verifies that closed status matches `currentEpoch`; reuses in-flight Promises for concurrent close calls within the same epoch, and allows safe retries after failures;<br>4. Bounded timeouts keep the background operation alive; upon late resolution, `handlePortClosed(p, epoch)` verifies epoch before clearing controller references, removing `unreleasedPorts`, and lifting `guidance` blockers;<br>5. Strict port and epoch isolation ensures old cleanup closures never touch newly connected ports or newer lifecycles;<br>6. Unified `disconnect()`, late `open` cleanup, `unreleasedPorts` retry, and `failRead` across epoch-aware `requestClosePort`. | Added `createStrictPort` in `static/test/g0-diag.test.js` enforcing Web Serial state transitions (`closed`, `opening`, `opened`, `closing`), throwing `InvalidStateError` on redundant calls. 11 strict regressions all passed:<br>1. Normal connection with close timeout followed by late success enables reconnection;<br>2. Late open followed by close timeout and late success enables reconnection;<br>3. Late close failure safely retries;<br>4. Permanently hanging close continuously refuses reconnect with bounded API wait;<br>5. Duplicate disconnect dedupes to a single close invocation;<br>6. Old cleanup tasks do not affect newly connected ports;<br>7. **Same port object reopened across 3 consecutive connect->handshake->disconnect rounds** (`openCount=3, closeCount=3`);<br>8. Same port close timeout late success, then reopened and closed normally;<br>9. Previously closed port, next round open times out then succeeds late -> executes cleanup close;<br>10. Duplicate disconnect does not increase close count in same lifecycle on reused port;<br>11. Old tasks do not affect subsequent lifecycle, and failures maintain safe blocking. |
| G0-U3 | pass | **Root cause**: `exportEvidence()` contained destructive side-effects by calling `flushSegment(capture)`, mutating segment boundaries and prematurely triggering summary degradation and history eviction.<br>**Fix**:<br>1. Removed `flushSegment` from `exportEvidence()`, turning exports into strictly non-destructive snapshots;<br>2. In-flight pending samples are exposed via `pendingSegment` with explicit `is_pending_tail: true` and `uncommitted_snapshot: true` flags;<br>3. `recordSample` flushes only when `maxSamples` is reached, ensuring identical retention and health regardless of whether intermediate exports occur 0 times, 1 time, or frequently;<br>4. Preserved all array boundedness, distinct raw/summary/dropped counts, and sequence reconstruction checks. | Added 5 new snapshot and boundedness regressions in `static/test/g0-diag.test.js` all passing:<br>1. With `maxSamples=2, maxSegments=1`, Path A (sample->sample->export) and Path B (sample->export->sample->export) yield identical results (2 raw samples, 0 summary, 0 dropped, `healthy: true`);<br>2. Interleaved sampling and export across segment and coverage boundaries maintains sample conservation;<br>3. Identical sequences with zero vs frequent exports yield identical final evidence and metrics;<br>4. Consecutive exports without new samples do not mutate controller state;<br>5. Exports after clean stop, after error response, and after capacity exhaustion conform to specifications. |

### Commands and results
- **Windows 11 environment (Node v22.13.1, npm 11.17.0, MinGW g++ 13.3.0, Chrome 155.0.8059.84)**:
  - `npm run test:unit` (with `MWCP_GPP=g++`): **94/94 passed**, exit code 0 (was 78, Round 2 +11, Round 3 +5, total 94 suites).
  - `node --test test/g0-diag.test.js`: **33/33 passed**, exit code 0.
  - `node --test test/g0-hello.test.js`: **2/2 passed**, exit code 0.
  - `npm run test:browser`: **2/2 passed**, exit code 0 (Chrome 155.0.8059.84).
  - `npm run build`: **passed**, exit code 0 (Vite 8.3.1 production build).
  - C++ host contract tests:
    - `mwcp_host_test` (`-std=c++14 -fno-exceptions -fno-rtti -static`): **passed**, exit code 0, 100% protocol vectors pass.
    - `g0_session_test` (`-std=c++14 -static`): **passed**, exit code 0.
    - `r60_probe_stats_test` (`-std=c++14 -static`): **passed**, exit code 0.
  - Python tests:
    - `python -m unittest discover -s tests -p test_releases.py -v`: **20/20 passed**, exit code 0.
    - `python -m unittest tests/unit/test_mwcp_sources.py -v`: **2/2 passed**, exit code 0.
- **Linux environment (WSL2 Ubuntu-22.04 LTS, kernel 6.6.87.2-microsoft-standard-WSL2, Node v22.13.1, npm 10.9.2, g++ 13.3.0, Python 3.12.3, Chromium 155.0.8059.79 snap) real execution**:
  - `npm ci`: Frontend dependencies installed per `package-lock.json` cleanly, 50 packages with 0 vulnerabilities.
  - `MWCP_GPP=g++ npm run test:unit`: **94/94 passed**, exit code 0 (0 failed, 0 skipped).
  - `npm run test:browser`: **2/2 passed**, exit code 0 (Chromium 155.0.8059.79 snap running non-root, clean browser bundle without Node API leakage, fast-failure guard verified).
  - `npm run build`: **passed**, exit code 0 (Vite v8.3.4 production build succeeded, all platform bundles packaged).
  - C++ `mwcp_host_test protocol/fixtures/protocol-vectors.json` (`-std=c++14 -fno-exceptions -fno-rtti -static`): **passed**, exit code 0.
  - C++ `g0_session_test` (`-std=c++14 -static`): **passed**, exit code 0.
  - C++ `r60_probe_stats_test` (`-std=c++14 -static`): **passed**, exit code 0.
  - Python `python3 -m unittest discover -s tests -p test_releases.py -v`: **20/20 passed**, exit code 0.
  - Python `python3 -m unittest tests/unit/test_mwcp_sources.py -v`: **2/2 passed**, exit code 0.

### Unexecuted items and limitations
- **Remote GitHub Actions CI status**:
  - Strictly adhering to constraints: no unauthorized commits pushed and no remote GitHub Actions workflows triggered; remote CI remains pending push/dispatch. Full unit tests, browser tests, production build, C++ host tests, and Python test suites have been executed directly on local Windows 11 and Linux (WSL2 Ubuntu 22.04) environments.
- **Physical hardware execution (LuatOS ESP32C3-CORE + R60ABD1 real hardware)**:
  - Authorized after explicit 4-point confirmation: board is LuatOS ESP32C3-CORE, native USB Serial/JTAG (`VID: 303A, PID: 1001`), port `COM9`; radar R60ABD1 wiring confirmed (GPIO21 TX / GPIO20 RX); dedicated test device without backup need; authorized flashing `baseline.yaml` and `host.yaml` and endurance testing.
  - **G0-01 (Parallel USB & Radar Communication)**: **PASS**. Native USB Serial/JTAG established an active MWCP session; radar communicates on GPIO20/21 with `radar_link: "healthy"`, valid radar frames advancing from 796 to 822 across 5s (~5.7 Hz), parse errors 0, active target count updating continuously (`origin != simulation`).
  - **G0-02 (USB Ownership & Stream Purity)**: **PASS**. Monitored steady-state USB stream after flashing `host.yaml`; captured 0 bytes of unsolicited output; zero plain-text logger emission, no Improv contention; telemetry confirms `usb_exclusive: true`, `usb_install_err: 0`.
  - **G0-05 (Resource & Runtime Overhead Comparison)**: **PASS**. Measured live device metrics on the same hardware running `baseline.yaml` vs `host.yaml`:
    - Runtime Free Heap: Baseline `212,476 B` vs Host `192,868 B` (delta `19,608 B` ≈ 19.15 KiB, within the `<= 24,576 B` (24 KiB) hard limit; see `g0-evidence-index.json` `gates.G0-05.metrics`);
    - Largest Free Block: `114,688 B` on both (a single-point equality; it does not by itself prove absence of fragmentation, see Section 22.2 clarification 2);
    - FreeRTOS Stack High-Water: Baseline `6,172 B` vs Host `2,908 B` (ESP-IDF RISC-V 1 byte/unit, $> 2.9$ KiB safety headroom remaining);
    - Loop Max Latency: Baseline `3,162 us` vs Host `2,676 us` (both $< 4$ ms, far below the 16 ms budget threshold);
    - Radar Communication: Both maintained `healthy` with 0 parse errors.
  - **G0-03 (Offline 2-Hour Endurance Test)**: **PASS**. Executed fully automated continuous sampling across 7,200 seconds (120 minutes) on the offline-configured hardware (`reboot_timeout: 0s`):
    - 7,198 out of 7,198 1 Hz telemetry queries succeeded (100.00% success rate, 0 error responses);
    - Zero unintended reboots occurred (`reboot_detected: false`, `boot_id: dcda0cf8f2741d72537c31049c579aea` was maintained strictly unchanged across the entire test);
    - Monotonic uptime (`uptime_ms`) advanced continuously from 28,645 ms to 7,228,453 ms (net advance of 7,199,808 ms);
    - Radar streaming remained healthy and uninterrupted: R60ABD1 valid frames advanced by 34,878 frames (from 148 to 35,026, averaging ~4.84 Hz), with 0 parse errors;
    - Free Heap was 192,864 B at start and end (range `192,672..194,672 B`, 0 B net drift), minimum FreeRTOS stack headroom 2,844 bytes, and peak loop latency 4.535 ms (far below the 16 ms limit);
    - The full non-destructive evidence JSON is stored outside the repository at `C:\Users\zomco\.gemini\antigravity\brain\def311e0-e1d9-4cb7-a5ea-9df7a0d0ff47\scratch\g0-03-evidence.json` (`3,498,699` bytes; SHA-256 in Section 22.2 and `g0-evidence-index.json`); only the aggregate summary and 5 milestone samples are kept in-repo (no separate progress log file was produced).
  - **G0-04 (Installer to Diagnostic Handoff & Web Serial)**: **PASS**. Verified directly in Chrome 155 via Web Serial over the board's native USB port (`COM9`):
    - Traversed the complete lifecycle: `selecting -> opening -> handshaking -> online -> online capture -> disconnecting -> closed`;
    - Zero `InvalidStateError` upon disconnect or reconnect; port epoch stream locks cleanly released;
    - Non-destructive bounded telemetry segments (`segments` and `pending_tail`) and data exports conform strictly to protocol schema.

### Firmware hashes and source snapshot
Firmware C++ code and YAML profiles were untouched. Firmware hashes from section 20 remain valid:
- Host OTA: `DF0DA7283D78E899B478F6092C125528964FABCED6FB4EF49F7B5ACDD8674026`
- Host factory: `72C87C3DB3AAEF9A9C1968F2994365230D63FF33B3D0F50BE7B52A725CE56DD6`
- Baseline OTA: `7E0B7077A8D8A0594184C7F46924BC0A05969BC583F2777E96E0ADDA6CB4D1B8`
- Baseline factory: `EDD243713F65C6B86DDA7642AF140898A24EABAD804A23E54B17AF14186BB21D`

Workspace `468b4144a0653c5adde66351a2d8f7e94a0763c8`, component `f01ac84fa72dd5b3f479cb1e674572f5cea95c1b`, plus uncommitted changes.
Latest G0 source snapshot hash across 76 files (sorted `sha256 relative_path` manifest hashed with SHA-256):
**`242D8366DFA15E0A45AC0F4467AD24FFE7ED3649201CCB3758C353DB0675BAA2`**。

| Hardware item | Status | Judgment and Direct Evidence |
| --- | --- | --- |
| G0-01 | **pass** | Native USB Serial/JTAG handshake successful, R60ABD1 frames steady at 5.7 Hz, 0 parse errors, active targets |
| G0-02 | **pass** | Host firmware steady-state USB 0 bytes non-protocol output, zero text logs, `usb_exclusive: true`, `usb_install_err: 0` |
| G0-03 | **pass** | 2-hour offline endurance test 7,198/7,198 OK (100%), 0 reboots (boot_id constant), +34,878 radar frames (`0x80/0x05` XY coordinate frames +3,599 = 0.50 Hz), heap start/end 192,864 B (range `192,672..194,672 B`, 0 B net drift) |
| G0-04 | **pass** | Real Chrome 155 Web Serial on `g0-diag.html` connect/handshake/online capture/disconnect/reconnect clean lifecycle, no `InvalidStateError` (Note: the 5 `esp-web-tools` installer dialog UI branches remain mandatory WP-3 / B-04 / G3 / G4 verification items) |
| G0-05 | **pass** | Same-board measurements (identical to `g0-evidence-index.json` `gates.G0-05.metrics`): link-time Flash delta `+2,292 B` (`767,502 − 765,210`, budget `<= 92,160 B`), OTA/factory bin deltas both `+2,288 B`; link-time RAM delta `+17,524 B` (`.dram0.bss` `+17,704 B`); runtime free heap delta `19,608 B` (`212,476 − 192,868`, hard limit `<= 24,576 B`); 2-hour minimum stack headroom `2,844 B` (budget `>= 2,048 B`); 2-hour peak loop latency `4,535 us` (target `<= 8,000 us`, hard limit `16,000 us`) |

---

## 22. WP-1 / G1 Protocol Contract Closure, Coverage Matrix & WP-2/WP-3 Interface Handoff Checklist

### 22.1 Phase Verdict & Baseline State

- **Phase Review Status**: **G1 Remediation Candidate, Pending Independent Re-review (All G1-R1..G1-R5 Remediations & Regressions Completed)**
- **Strict Scope & Boundary Statement**:
  - This phase solidifies the G0 hardware verification evidence index, self-contained component protocol specifications (Chinese and English), categorized design differences register (`DD-01`..`DD-15`), full 24-command/event Schema and simulator contract coverage, and the 100,000-input deterministic mutation fuzz test (`P-14`) in C++14 (exact-sized buffer tightening + ASan/UBSan memory checks).
  - **Passing simulator and contract tests does NOT mean production firmware features are complete**: WP-2 production services (`ConfigService` dual-slot NVS, `JobService`, `WiFiService`, production `R60Adapter`) and WP-3 production Web Console UI have not started.
  - **Category C items (`DD-07`, `DD-08`) have been explicitly approved by the user and applied across all three targets**:
    1. **`DD-07` (Option C2 Adopted)**: Based on G0-03 2-hour hardware endurance (`3,599` frames / `7,199.8 s` = `0.50 Hz`), `position.xy` in `r60abd1-capabilities.json` and `simulator.js` is set to `"expected_interval_ms": 2000, "stale_after_ms": 6000`, while unbucketed non-coordinate fields remain `null`.
    2. **`DD-08` (Option C2 Adopted: Synchronously Widened to `50..600 cm`)**: Synchronized `install.z_cm` / `num_radar_z` across `docs/protocol/fixtures/r60abd1-capabilities.json`, `static/src/protocol/simulator.js`, and `tests/common/r60abd1.yaml` to `50..600 cm` (step `1`).

| Baseline Dimension | Verified Value |
| :--- | :--- |
| Workspace HEAD | `86fc3ea156a13df3410a9fec619a7a7e72203fb6` (`86fc3ea`, advanced from `4847402` by user enclosure commit; this task did not touch `cases/` or other submodules) |
| `submodules/mmwave-component` HEAD | `9a524b8e8b02ffb496d808250567d7169fe264d5` (`9a524b8`) |
| `submodules/mmwave-card` HEAD | `5799d5729dd8bf6ee6114038bc989c2be1a35cf0` (`5799d57`, read-only) |
| G0 Baseline 76-File Source Snapshot SHA-256 | `242D8366DFA15E0A45AC0F4467AD24FFE7ED3649201CCB3758C353DB0675BAA2` |
| G1 Post-Remediation 76-File Source Snapshot SHA-256 | **`FE6391B1787574D0DA4E12D0B95A20AD075D7A7A7D4D1FC64EE6B14502589030`** |
| Protocol Golden Vectors (Dual-Source Identity) | `docs/plans/mmwave-web-console/protocol-vectors.json` and `submodules/mmwave-component/protocol/fixtures/protocol-vectors.json` byte-for-byte identical (enforced by `test_mwcp_sources.py`) |

---

### 22.2 G0 Hardware Verification Evidence Index & Three Technical Clarifications (Work Item A)

All G0 hardware testbed metadata, compiler/framework versions, firmware binary SHA-256 digests, G0-01..G0-05 metrics, and 2-hour endurance milestone samples are indexed in:
- **Evidence Index**: [`docs/reviews/web-console/g0-evidence-index.json`](./g0-evidence-index.json)
- **2-Hour Endurance Raw Evidence**: `C:\Users\zomco\.gemini\antigravity\brain\def311e0-e1d9-4cb7-a5ea-9df7a0d0ff47\scratch\g0-03-evidence.json` (`3,498,699` bytes, SHA-256: `075451aaac7d63afc0d75a88812af85fad0e5cea8d64d88901d60fa7291561f8`)

#### Three Mandatory Technical Clarifications
1. **Aggregate Radar Frame Rate (`radar_frames`) vs. Per-Field Update Cadence (`radar_targets`)**:
   - Across the `7,199.8 s` (`7,198` samples) G0-03 run, `R60ProbeStats::valid_frames` (`radar_frames`) increased from `148` to `35,026` (`+34,878` frames, mean **`4.84 Hz`**, `4..8 frames/s`). This counter aggregates **all valid R60 UART control words** (heartbeat, presence `0x80/0x01`, motion `0x80/0x02`, body movement `0x80/0x03`, distance `0x80/0x04`, XY position `0x80/0x05`, breath, heart rate, sleep).
   - By contrast, `R60ProbeStats::target_observations` (`radar_targets`) **counts only `0x80/0x05` 2D XY coordinate frames** and increased from `14` to `3,613` (`+3,599` frames over `7,199.8 s`), proving an exact **`2,000 ms` (`0.50 Hz`)** hardware reporting interval, while `R60ABD1Component::publish_position_()` further throttles publishing to `>= 1,000 ms`.
   - **Rule**: Never conflate the `~4.84 Hz` aggregate UART frame rate with per-field update intervals for `position.xy`, `presence`, `breath_rate`, or `heart_rate`.
2. **Single-Point `largest_free_block` Equality vs. Long-Term Fragmentation Proof**:
   - Equal `largest_free_block` (`114,688 B`) in G0-05 point-in-time snapshots combined with `0 B` net `free_heap` drift over 2 hours in G0-03 (`192,864 B` start and end, `192,672..194,672 B` range) proves the static-buffer G0 probe does not leak memory.
   - However, a single-point `largest_free_block` comparison alone does not prove absence of fragmentation under arbitrary dynamic allocations; WP-2 production firmware must therefore preserve static/bounded buffers and zero per-frame heap allocation.
3. **Diagnostic Page Web Serial Lifecycle vs. `esp-web-tools` 5 UI Branches**:
   - G0-04 verified real-hardware Web Serial open/handshake/5Hz capture/disconnect/reconnect in Chrome `155.0.7632.160` on `g0-diag.html`, and unit tests (`flash-handoff.test.js`, `g0-diag.test.js`) verified the port release state machine.
   - The 5 full `esp-web-tools` UI dialog branches (install success -> console, install failure, user cancel, dialog close, physical unplug during install) have not yet been executed end-to-end on real hardware in the production console UI and remain mandatory WP-3 / B-04 / G3 / G4 verification items.

---

### 22.3 G1 Protocol & Contract Coverage Matrix (Deliverable 5)

| Plan ID | Requirement Summary | Spec Section (`docs/protocol/README.md`) | Schema / Golden Vector / Fixture | JS Test Files (`static/test/`) | C++ / Python Test Files | Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **P-01** | `CRC32C (Castagnoli)` check value for `"123456789"` is `0xe3069283` (wire LE `83 92 06 e3`) | Section 2.3 | `protocol-vectors.json` (`crc32c_check`) | `protocol-codec.test.js` | `protocol/cpp/mwcp_host_test.cpp` | **PASS (Dual-Stack)** |
| **P-02** | Golden vectors (`HELLO` req/resp, UTF-8 CJK frame, 254B COBS block frame) encode/decode byte-for-byte | Sections 2.1–2.3 | `protocol-vectors.json` (`frames`, `cobs_vectors`) | `protocol-codec.test.js` | `protocol/cpp/mwcp_host_test.cpp`, `test_mwcp_sources.py` | **PASS (Dual-Stack)** |
| **P-03** | Single-byte streaming, 1..100B pseudo-random chunking, 10-frame sticky packets, consecutive empty `0x00` delimiters | Sections 2.1, 2.3 | `protocol-vectors.json` | `protocol-codec.test.js` | `protocol/cpp/mwcp_host_test.cpp` (`test_sticky_10_frames_and_100k_mutations`) | **PASS (Dual-Stack)** |
| **P-04** | Boot garbage bytes, bad COBS, bad CRC32C, bad magic/version/kind/flags silently dropped & counted, immediate recovery on next valid frame | Section 2.3 (`DD-09`) | `mwcp-v1.schema.json` | `protocol-codec.test.js` | `protocol/cpp/mwcp_host_test.cpp` | **PASS (Dual-Stack)** |
| **P-05** | `MAX_PAYLOAD = 4096 B` accepted, `4097 B` rejected (`payload_too_large`), `MAX_COBS = 4141 B` overflow discarded until next `0x00` | Section 2.3 | `mwcp-v1.schema.json` | `protocol-codec.test.js`, `protocol-schema.test.js` | `protocol/cpp/mwcp_host_test.cpp` | **PASS (Dual-Stack)** |
| **P-06** | Partial frame `HALF_FRAME_MS = 2000 ms` timeout discards buffer, increments `timeouts`, and recovers on next valid frame | Section 2.3 | — | `protocol-codec.test.js` | `protocol/cpp/mwcp_host_test.cpp` | **PASS (Dual-Stack)** |
| **P-07** | Strict UTF-8 & JSON constraints: depth `<=8`, keys `<=64`, array `<=256`, no BOM, literal & `\uXXXX` duplicate keys rejected (`DD-13`), integer & exponent-integer `±(2^53-1)` bounds (`DD-14`), binary64 overflow threshold parity | Section 2.4 (`DD-13`, `DD-14`) | `json-cases.json`, `double-overflow-threshold.txt` | `protocol-codec.test.js`, `protocol-h-fixes.test.js` | `protocol/cpp/mwcp_host_test.cpp` | **PASS (Dual-Stack)** |
| **P-08** | `HELLO` version negotiation, 32-hex `nonce`/`boot_id`, `max_payload < 4096` -> `LIMIT_UNSUPPORTED`, major mismatch -> `VERSION_UNSUPPORTED` | Section 3.1 | `mwcp-v1.schema.json` (`helloRequest`, `helloResult`) | `protocol-session.test.js`, `g0-hello.test.js` | `protocol/cpp/g0_session_test.cpp` | **PASS (Dual-Stack + HW G0-01)** |
| **P-09** | 4-slot response replay cache: same `request_id`+payload replays cached response; same ID + different payload -> `ID_REUSE`; evicted old ID -> `REQUEST_EXPIRED` | Section 3.2 | `mwcp-v1.schema.json` (`errorEnvelope`) | `protocol-session.test.js`, `protocol-regression.test.js` | — (ported to WP-2 service layer) | **PASS (JS Contract/Simulator)** |
| **P-10** | `session_ttl_ms = 15000`, 5s `PING` renewal, device `event` frames do not self-renew, suspended clock expiry re-handshake, `SESSION_CLOSE` | Sections 3.2–3.3 | `mwcp-v1.schema.json` | `protocol-session.test.js`, `protocol-f-fixes.test.js`, `protocol-g-fixes.test.js` | `protocol/cpp/g0_session_test.cpp` | **PASS (JS + C++ G0)** |
| **P-11** | Paginated reads (`CAPABILITIES_LIST`, `CONFIG_READ`, `ACTIONS_LIST`, `WIFI_SCAN_RESULTS`) and mid-pagination `revision` change -> `REVISION_CONFLICT` | Section 5.1 | `mwcp-v1.schema.json` | `protocol-session.test.js`, `protocol-schema.test.js` | — | **PASS (JS Contract/Simulator)** |
| **P-12** | Event rate limit, `event_budget_bps (1000..8000)`, control response priority over events, `telemetry_coalesced` & `logs_dropped` counters | Section 5.2 | `mwcp-v1.schema.json` | `protocol-f-fixes.test.js`, `protocol-g-fixes.test.js`, `protocol-session.test.js` | `protocol/cpp/g0_session_test.cpp` | **PASS (JS + C++ G0)** |
| **P-13** | RPC rate limiting (10 RPC/s) and persistent write token bucket exhaustion -> `RATE_LIMITED` (`retry_after_ms`) | Section 3.4 | `mwcp-v1.schema.json` | `protocol-session.test.js` | — | **PASS (JS Contract/Simulator)** |
| **P-14** | Deterministic pseudo-random seed (`0x5eed1234`) **100,000-input mutation fuzz test** (exact-sized buffer allocation + ASan/UBSan, covering frame parser `mwcp::Parser` and JSON validator `mwcp::json_check`), 0 out-of-bounds reads, 0 crashes, bounded state, immediate recovery on valid frame | Sections 2.3–2.4 | `protocol-vectors.json` | `MWCP_GPP=g++ npm run test:unit` | `protocol/cpp/mwcp_host_test.cpp` (`test_sticky_10_frames_and_100k_mutations`) | **PASS (C++14 100,000 Mutations + ASan/UBSan)** |
| **T-02..T-10** | Telemetry snapshot structure, `source_seq`, `sent_ms`/`sample_ms` age estimation, `origin`, `quality` (`unknown/unsupported/invalid` -> `value: null`), 1D `range_cm` vs 2D `local_cm/room_cm` non-mixing, R60 `speed_cm_s: null` (`DD-06`), `position.xy` `2000/6000 ms` (`DD-07` C2), 3D rotation matrix & ray-casting edge points (`DD-11`) | Section 5.2 | `mwcp-v1.schema.json`, `protocol-vectors.json`, `r60abd1-capabilities.json` | `protocol-coordinates.test.js`, `protocol-schema.test.js`, `protocol-g-fixes.test.js` | `protocol/cpp/mwcp_host_test.cpp`, `test_rotation_convention.py` | **PASS (JS + C++ + Python)** |
| **C-01..C-12** | Config read, side-effect-free `CONFIG_VALIDATE`, `UNKNOWN_FIELD`, `OUT_OF_RANGE` (including `install.z_cm` `50..600 cm` `DD-08` C2), polygon geometry validation (self-intersection/zero-area/duplicate closing vertex rejected atomically `DD-05`), `REVISION_CONFLICT`, `op_id` idempotency & `OP_ID_REUSE`, `COMMIT_STATUS` | Section 5.3 | `mwcp-v1.schema.json` | `protocol-schema.test.js`, `protocol-session.test.js`, `protocol-h-fixes.test.js` | — (WP-2 firmware implementation) | **PASS (JS Contract/Simulator)** |
| **C-13** | **Maximum Valid R60 Configuration Capacity Proof**: `CONFIG_COMMIT` with all R60 host config keys (`install.z_cm = 600`) + geometrically valid 64-vertex convex polygon (`polygonIssues === []`) passes Schema, simulator & frame encoding (`~1.15 KiB <= 4096 B`) | Section 5.3 (`DD-04`, `DD-08`) | `mwcp-v1.schema.json`, `r60abd1-capabilities.json` | `protocol-schema.test.js` | — | **PASS (JS Contract/Simulator)** |
| **C-14** | 64-bit decimal string `revision` monotonic increment without precision loss | Sections 2.4, 5.3 | `mwcp-v1.schema.json` | `protocol-g-fixes.test.js` | — | **PASS (JS Contract/Simulator)** |
| **A-01..A-03** | Actions list, `confirm === action_id` check, per-resource mutex (`BUSY`), `op_id` deduplication, `verification: "none"` -> `verified: false`, `device.restart` new `boot_id` recovery | Section 5.4 | `mwcp-v1.schema.json`, `r60abd1-capabilities.json` | `protocol-schema.test.js` | — | **PASS (JS Contract/Simulator)** |
| **W-01..W-04** | `WIFI_STATUS` never returns password, `WIFI_SCAN` + `WIFI_SCAN_RESULTS` sorted by `rssi_dbm` desc with 64-item cap, `WIFI_PROVISION` (`open` vs `wpa2_psk`), CJK SSID `x-maxUtf8Bytes: 32`, zero password echo | Section 5.4 (`DD-10`) | `mwcp-v1.schema.json` | `protocol-schema.test.js` | — | **PASS (JS Contract/Simulator)** |
| **S-01..S-04** | Requests reject unknown fields (`UNKNOWN_FIELD`), responses/events allow unknown fields via `x-open-object: true` (`DD-15`), prototype pollution keys blocked, `AUTH_REQUIRED`/`inject_mock_data`/`raw_uart_tx` excluded | Sections 2.4, 3.4 (`DD-15`) | `mwcp-v1.schema.json` | `protocol-schema.test.js`, `protocol-g-fixes.test.js` | — | **PASS (JS Contract/Simulator)** |
| **G0-01..G0-05** | LuatOS ESP32C3-CORE (`USB\VID_303A&PID_1001`) + R60ABD1 parallel communication, USB exclusive ownership, 2-hour `7,198`-sample offline endurance with 0 reboots & 0 heap drift, Chrome 155 Web Serial lifecycle, resource overhead comparison | Sections 1.2, 5.2 | [`g0-evidence-index.json`](./g0-evidence-index.json) | `g0-diag.test.js`, `g0-hello.test.js` | `g0_session_test.cpp`, `r60_probe_stats_test.cpp` | **PASS (Real Hardware + Dual-OS Regressions)** |

---

### 22.4 WP-2 (Firmware Services) & WP-3 (Frontend Console) Interface Handoff Checklist (Deliverable 6)

To enable unambiguous implementation in WP-2 and WP-3 after G1 acceptance, module boundaries and hard constraints are frozen as follows:

| Module Name | Target Package | Protocol Commands / Events | Persistence, Idempotency & Concurrency Rules | Buffer & Memory Caps (ESP32-C3 Hard Budget) | Prohibited Actions (Red Lines) | Mandatory G2 / G3 Acceptance Tests |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **`HostLink` & `SessionService`** | WP-2 (Firmware) | `HELLO (0x0001)`, `PING (0x0002)`, `SESSION_CLOSE (0x0003)` | Single active session; `boot_id` generated per boot via hardware RNG (32 lowercase hex); 4-slot `(request_id, code, sha256, resp)` replay cache; `15,000 ms` TTL; 10 RPC/s rate limit | Static RX COBS buffer `4,143 B`; static TX frame buffer `4,143 B`; 64B non-blocking `tx_pump` (abandons frame after `250 ms` zero-write and marks resync); **0 per-frame heap allocation** | Never block on `USB_SERIAL_JTAG` writes waiting for host read; never enable stock `improv_serial` or plaintext serial `logger`; never renew session TTL on device `event` frames | `G2-01` Hardware handshake, replay deduplication, `ID_REUSE`, `REQUEST_EXPIRED`, DTR hang non-blocking `loop()` |
| **`CapabilitiesService` & `StatusService`** | WP-2 (Firmware) | `DEVICE_INFO (0x0010)`, `CAPABILITIES_LIST (0x0011)`, `STATUS_GET (0x0012)`, `STATUS_CHANGED (0x8002)` | `CAPABILITIES_LIST` paginated from static read-only descriptor table bound to build-time `cap_revision`; `STATUS_GET` reports `uptime_ms`, `radar_link`, `config_revision`, `config_storage`, and 9 standard `counters` | Descriptors stored in Flash (`rodata`), zero static/dynamic RAM | Never report `radar_link: "error"` merely because `targets: []`; never infer `radar_identity` from USB VID/PID | `G2-02` R60 hardware capability pagination parity with `r60abd1-capabilities.json` |
| **`TelemetryService` & `R60Adapter`** | WP-2 (Firmware) | `SUBSCRIBE (0x0030)`, `UNSUBSCRIBE (0x0031)`, `TELEMETRY (0x8001)` | No subscriptions by default on new session; enforces `1..20 Hz` cap and `1,000..8,000 bps` wire budget; does not invent new `source_seq` when observations have not changed | Telemetry TX queue depth `= 1` (retains latest snapshot only, incrementing `telemetry_coalesced` on overwrite) | Never export R60 placeholder `0` as `speed_cm_s: 0` (must be `null`, `DD-06`); never parse text logs or add a second UART reader | `G2-03` R60 hardware 2D coordinates, presence, independent vital timestamps, and room transform parity |
| **`ConfigService`** | WP-2 (Firmware) | `CONFIG_READ (0x0020)`, `CONFIG_VALIDATE (0x0021)`, `CONFIG_COMMIT (0x0022)`, `COMMIT_STATUS (0x0023)`, `CONFIG_CHANGED (0x8003)` | **Dual-slot atomic persistence** (full snapshot + `schema_version` + `CRC32C` + monotonic `uint64` decimal string `revision`); stores last 4 `(op_id, sha256, revision)`; shared token bucket (capacity 32, refill 1/s); one-time boot migration from legacy `globals` | Fixed-size struct snapshot supporting 64-vertex `int16_t` polygon (replacing legacy 254B `g_polygon` string, `DD-04`) | Never mutate runtime state before NVS commit succeeds; never silently reset to factory when both slots are corrupt (must enter `recovery_required`); never skip bad polygon vertices or allow self-intersection (`DD-05`) | `G2-04` 64-vertex max R60 config commit, power-cycle persistence, `REVISION_CONFLICT`, bidirectional HA card & console sync |
| **`JobService`** | WP-2 (Firmware) | `ACTIONS_LIST (0x0040)`, `ACTION_START (0x0041)`, `JOB_GET (0x0042)`, `JOB_CHANGED (0x8004)` | Resource locks (`wifi`, `radar`, `restart`) allow at most 1 active job per resource (`BUSY` on conflict); enforces `confirm === action_id`; capacity reservation invariant: `protected_completed + active_reservation <= 8` (total task records strictly `<= 8` across all states); strict admission sequence: 1. `op_id` idempotency verified first (identical payload returns existing `job_id` even at full capacity, different payload returns `OP_ID_REUSE`); 2. Resource mutex check; 3. Capacity check returns `BUSY` (`{ reason: "capacity", retry_after_ms: 1000 }`) with **zero side effects** (Wi-Fi `state`/`ssid` unmutated, no task created, no events); 4. State mutated and job admitted only after all checks pass; completed history retains up to 8 entries managed by completion order (completion-order FIFO); protection condition is `elapsed < 300,000 ms` (never prematurely evicted); natural reclamation condition is `elapsed >= 300,000 ms` (reclaims slot at or beyond 300,000 ms; exact boundaries: `299,999 ms` protected, `300,000 ms` and `300,001 ms` reclaimable, unexpired records unaffected); resets volatile table & locks on reboot with fresh 32-hex `boot_id` | Bounded static job history table (retains last `8` completed job summaries, strictly satisfies `protected_completed + active_reservation <= 8`, active jobs never evicted) | Never claim hardware verification for `verification: "none"` actions (must complete with `verified: false`); never mark `device.restart` as `succeeded` before reboot | `G2-05` Hardware `device.restart` and `radar.reset_module`, concurrent `BUSY`, 5-minute completion protection (< 300000ms) and natural reclamation (>= 300000ms), capacity reservation admission control, post-reboot `boot_id` change verification |
| **`WiFiService`** | WP-2 (Firmware) | `WIFI_STATUS (0x0050)`, `WIFI_SCAN (0x0051)`, `WIFI_PROVISION (0x0052)`, `WIFI_SCAN_RESULTS (0x0053)` | Scan deadline 15s, results paginated by `rssi_dbm` desc; provision deadline 60s (save old credential ref -> connect -> obtain IP -> persist -> succeed; rollback to old network on failure) | Bounded scan table up to `64` AP entries; password kept only in explicitly zeroed temporary buffer | **Never** echo `password` in any response, event, log, error, or cache; never downgrade unsupported auth to `open`; never trigger `reboot_timeout` when offline | `G2-06` Hardware AP scan pagination, valid-password provision, bad-password rollback without dropping USB session, zero password leak check |
| **`LogService`** | WP-2 (Firmware) | `LOG (0x8005)` (controlled via `SUBSCRIBE` `logs` stream) | Disabled by default; max default level `info`; `debug` auto-reverts to `info` after 60s; redacts secrets before ring-buffer insertion | Static bounded ring buffer (drops oldest and increments `dropped_before` / `logs_dropped` when full) | Never allow diagnostic logging to trigger recursive logging loops; never log plaintext Wi-Fi/API/OTA secrets | `G2-07` Log subscription toggle, ring-buffer overflow `dropped_before` counter, and secret redaction |
| **`ProtocolClient` / Console Store / Flash Handoff** | WP-3 (Frontend) | All 19 commands & 5 events | Single in-flight RPC queue; 5s `PING` heartbeat; detects `boot_id` change to clear drafts and re-read; treats own `await port.open()` success as sole handoff proof (`DD-01`) | Bounded ring arrays and non-destructive export snapshots for telemetry and logs (following G0-U3 pattern) | Never hardcode controls by `model_id` without `CAPABILITIES_LIST` descriptors; never auto-retry timed-out `CONFIG_COMMIT` with a new `op_id`; never display unsaved drafts as authoritative device output | `G3-01..G3-06` Full console UI, graphical polygon editor, 5 installer handoff branches, EN/ZH i18n, and accessibility |

---

### 22.5 Categorized Dual-Platform Verification Commands & Results

Strictly differentiating between actually run in this round, previously passed, and not rerun items:

1. **Actually Run in This Round (Exact Boundary Hardening & Hardened Regression Round)**:
   - **Windows 11 Environment (Node v22.13.1, MinGW g++ 13.3.0, Python 3.12, Chrome 155)**:
     - `$env:MWCP_GPP="D:\Build\mingw64\bin\g++.exe"; npm run test:unit`: **All unit test suites passed** (baseline updated to **106 / 106 passed**, exit code `0`, includes positive/negative Schema validation for all 24 commands/events, 64-vertex convex polygon max R60 config commit, `4096B/4097B` boundaries, `DD-07` C2, `DD-08` C2 `50..600 cm`, `A-01..A-03`, `W-01..W-04`, `P-03` sticky streams, C++ emitter integration, and dedicated G1-R1..G1-R5 regression suites; specially hardened with **G1-R2-A 3 controlled-clock exact boundary tests**: `299999ms` protected rejecting new jobs at full capacity, `300000ms` oldest record naturally reclaimable and admitting new job, `300001ms` sustainably reclaimable with unexpired records unaffected, and G1-R2-B reboot memory assertion strictly bounded at `<= 8` records).
     - `npm run test:browser`: **2 / 2 passed**, exit code `0`.
   - **Linux Environment (WSL2 Ubuntu 22.04 LTS, Node v22.13.1)**:
     - `node --test test/protocol-schema.test.js`: **14 / 14 passed**, exit code `0` (fully passes all protocol schema and job lifecycle suites including the 3 G1-R2-A exact boundary tests and G1-R2-B `<= 8` records assertion).

2. **Previously Passed Items (Independently Verified in G0/G1 Prior Rounds, Maintained Without Regression)**:
   - `npm run build`: Production bundle passed (Vite v8.3.4, exit code `0`).
   - C++14 Host Tests (`-std=c++14 -fno-exceptions -fno-rtti -Wall -Wextra -Werror -static`):
     - `mwcp_host_test` (golden vectors, `P-03` 10-frame sticky stream & 1..100B random chunking, `P-14` **100,000-input deterministic mutation fuzz test**): **`mwcp c++ host test passed`**, exit code `0` (verified under WSL2 with ASan/UBSan `-fsanitize=address,undefined` for zero out-of-bounds reads and zero leaks).
     - `g0_session_test`: **`g0 session test passed`**, exit code `0`.
     - `r60_probe_stats_test`: **`g0 probe host test passed`**, exit code `0`.
   - Python Unit Tests:
     - `python -m unittest discover -s submodules/mmwave-component/tests -p "test_releases.py" -v`: **20 / 20 passed**, exit code `0`.
     - `python -m unittest discover -s tests/unit -p "test_*.py" -v` (including `test_mwcp_sources.py` 2 tests, `test_rotation_convention.py` 7 tests, etc.): **239 / 239 passed**, exit code `0`.

3. **Not Rerun Items**:
   - **G0 Real Hardware Serial Port Tests**: In compliance with strict red lines (no connecting to serial ports, no flashing, no erasing, no power-cycling physical devices), real hardware serial port tests were not run in this round and are not rerun by default after already passing independent G0 acceptance.

---

## 23. G1 Acceptance Remediation (G1-R1..G1-R5) Root Causes, Remediation Matrix & Verification Verdict

### 23.1 R1–R5 Remediation Matrix

| Defect ID | Root Cause & Attribution | Modified Files | Regression Test Name | Actual Command & Result | Residual Limitations & Boundary |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **G1-R1** | **Multi-Source Contract Divergence & Undecided Semantics**: Slot structure in `areas.definitions` diverged between simulator (`area.slots`) and Schema/fixture; action name `radar.reset_module` conflicted with legacy simulator names `radar.reinitialize` / `wifi.clear`; `confirm` semantics in Schema allowed boolean `true` while docs required exact match with `action_id`; R60 install angle steps and bounds differed across docs, simulator, and firmware. | `docs/protocol/fixtures/r60abd1-capabilities.json`<br>`docs/protocol/schema/mwcp-v1.schema.json`<br>`static/src/protocol/schema.js`<br>`static/src/protocol/geometry.js`<br>`static/src/protocol/contract.js`<br>`static/src/protocol/simulator.js`<br>`docs/protocol/README_CN.md`<br>`docs/protocol/README.md`<br>`docs/protocol/design-differences_CN.md`<br>`docs/protocol/design-differences.md` | `static/test/protocol-schema.test.js`:<br>`G1-R1 regression: R60 capabilities/config/actions match fixture and confirm requires exact action_id string` | `npm run test:unit` (all test suites passed):<br>- `CAPABILITIES_LIST` pagination matches fixture byte-for-byte;<br>- `ACTIONS_LIST` declares only `device.restart` and `radar.reset_module`;<br>- `confirm` passed as `null/false/true/wrong_string` returns `INVALID_ARGUMENT`, only exact `action_id` starts job. | Simulator strictly mirrors R60 8 config keys and 2 supported actions; production firmware service layer (WP-2) must implement this exact contract and never add undeclared actions. |
| **G1-R2** | **Simulator Mock Defect, Missing Capacity Admission & Lifecycle Flaws (R2-A/R2-B)**:<br>1. **Capacity Admission & 5-Minute Protection Window Breakdown (R2-A Final Remediation & Exact Boundary Hardening)**: In the prior round, while eviction order was adjusted, `trimCompletedJobs()` unconditionally called `shift()` when length exceeded 8, and `createJob()` lacked capacity admission checks; the prior regression test lines 599–602 even asserted that a 9th task within 5 minutes could evict the 1st task; this led to accepting tasks beyond capacity (totaling 10 active+completed records), and completing a 9th task evicted the earliest task after only ~10s, returning `unknown` on `JOB_GET` and breaking idempotency; <br>2. **Reboot Memory Leak (R2-B)**: Simulator reboot only filtered for current boot and failed to clear past-boot jobs, leaking up to 24 records after 15 reboots without bounds; `boot_id` was not generated as a fresh random value;<br>3. **Fake Completion & Verification Overreach**: `device.restart` declared `verification: "none"` but falsely reported `succeeded` before rebooting. | `static/src/protocol/simulator.js`<br>`docs/plans/mmwave-web-console/implementation-handoff.md`<br>`docs/protocol/README_CN.md`<br>`docs/protocol/README.md` | `static/test/protocol-schema.test.js`:<br>- `G1-R2 regression: active job is never evicted by completed jobs and preserves resource lock`<br>- `G1-R2-A regression: completed jobs FIFO by completion order, 5-minute retention window, failed jobs and session reconnection`<br>- `G1-R2-A exact boundary: oldest completed record at elapsed 299999 ms with a controlled clock`<br>- `G1-R2-A exact boundary: oldest completed record at elapsed 300000 ms with a controlled clock`<br>- `G1-R2-A exact boundary: oldest completed record at elapsed 300001 ms with a controlled clock`<br>- `G1-R2-B regression: reboot lifecycle, memory boundedness across 100 reboots, lock release, and boot_id uniqueness`<br>- `async actions, job lifecycle, reboot recovery and Wi-Fi flows follow contract semantics` | `npm run test:unit` (all test suites passed):<br>- Overturned flawed test expectations; established strict capacity reservation invariant: `protected_completed + active_reservation <= 8`, total task records strictly bounded to `<= 8` across all states;<br>- Strict admission check order: idempotency first (identical payload returns existing `job_id` even when capacity full, altered payload returns `OP_ID_REUSE`) -> resource mutex check -> capacity check returns `BUSY` (`{ reason: "capacity", retry_after_ms: 1000 }`) with **zero side effects** (Wi-Fi `state`/`ssid` unmutated) -> state mutation & job admission;<br>- Strict 5-minute retention window: protection condition is `elapsed < 300,000 ms` (rejects new jobs at full capacity, never evicts protected records); natural reclamation condition is `elapsed >= 300,000 ms` (at or beyond 300,000 ms);<br>- Controlled-clock exact boundary hardening: at `299,999 ms` original task is queryable and full-capacity new job returns `BUSY`; at `300,000 ms` original record naturally reclaims and new job is admitted; at `300,001 ms` sustainably reclaimable; unexpired records unaffected;<br>- 100 consecutive reboots bounded at `<= 8` records, past jobs become `unknown`, mutex locks released, fresh 32-hex `boot_id` generated, NVS persisted config/revision preserved;<br>- `device.restart` strictly prohibited from being marked `succeeded` before reboot; `radar.reset_module` and `verification: none` actions finish with `verified: false`, never claiming false hardware verification. | Simulator strictly follows bounded memory (<=8), capacity reservation, 5-minute absolute protection (<300,000ms), natural reclamation (>=300,000ms), and completion-order FIFO eviction; production firmware (WP-2) must implement identical bounded RAM task table scheduling and zero-side-effect admission rejection rules. |
| **G1-R3** | **Structured Config Schema & Business Validation Gaps**: `r60.areas.v1`, `polygon.xy.v1`, and `range.window.v1` permitted self-intersecting polygons, collinear bad points, and negative ranges as open arrays in Schema; disabled area slots (`enabled: false`) with empty arrays `[]` or preserved polygons were not handled uniformly; 1D `range.window_cm` was conflated with R60. | `docs/protocol/schema/mwcp-v1.schema.json`<br>`static/src/protocol/schema.js`<br>`static/src/protocol/contract.js`<br>`static/src/protocol/simulator.js` | `static/test/protocol-schema.test.js`:<br>`G1-R3 regression: strict structured config validation across schema, CONFIG_VALIDATE, and CONFIG_COMMIT` | `npm run test:unit` (all test suites passed):<br>- Floating slot, duplicate slot, slot unknown fields, non-array points, 2-point degenerate polygon, self-intersection, >12 vertices, out-of-range coords, misaligned step rejected in both VALIDATE and COMMIT;<br>- Disabled slot empty array `[]` and preserved valid polygons both accepted. | 64-vertex convex polygon maximum capacity verified via `C-13` (`~1.15 KiB <= 4096 B`). |
| **G1-R4** | **Hardware Evidence Index Deficiencies**: `radar_uart` in index file misstated as `UART2 GPIO16/17` (actual physical wiring and host/baseline.yaml are `UART1 GPIO21 TX / GPIO20 RX`); lacked explicit artifact SHA-256 digests, ELF section sizes, and 76-file snapshot mapping; endurance test referenced a non-existent summary file. | `docs/reviews/web-console/g0-evidence-index.json`<br>`docs/reviews/web-console/wp0-wp1-phase-report_CN.md`<br>`docs/reviews/web-console/wp0-wp1-phase-report.md` | `static/test/protocol-schema.test.js`:<br>`G1-R4 regression: G0 evidence index matches host.yaml/baseline.yaml and is arithmetically self-consistent` | `node --test test/protocol-schema.test.js` (all passed):<br>- Automated verification confirms `g0-evidence-index.json` matches `host.yaml`/`baseline.yaml` pins (GPIO21/20 115200);<br>- Arithmetic checks verify Flash/RAM/BSS/Heap deltas and G0-03 7,198 sample start/end values;<br>- All referenced file paths physically exist on disk; removed references to non-existent summary files. | Raw 3.5 MB endurance sample JSON is preserved in external conversation storage `scratch/g0-03-evidence.json`; only aggregate metrics and 5 milestone samples are kept in-repo to prevent bloating git tree. |
| **G1-R5** | **Documentation Coherence, Bilingual Sync Flaws & Workflow Path Legacy**: English and Chinese READMEs had regressions in R60 8-config steps, ranges, and action deadlines; `design-differences` referenced non-existent workflow `.github/workflows/publish-firmware.yml`; reports and specifications contained fragile fixed test case counts; firmware handoff doc lacked explicit task capacity (8), completion-order FIFO, and reboot lifecycle requirements; P-03/P-14 lacked memory sanitizer proof under exact-sized tight buffers. | `docs/protocol/README_CN.md`<br>`docs/protocol/README.md`<br>`docs/protocol/design-differences_CN.md`<br>`docs/protocol/design-differences.md`<br>`docs/plans/mmwave-web-console/implementation-handoff.md`<br>`docs/reviews/web-console/wp0-wp1-phase-report_CN.md`<br>`docs/reviews/web-console/wp0-wp1-phase-report.md`<br>`protocol/cpp/mwcp_host_test.cpp` | `static/test/protocol-schema.test.js`:<br>`G1-R5 regression: referenced paths exist and bilingual protocol READMEs mirror the R60 fixture`<br>C++14 `mwcp_host_test` (ASan + UBSan) | `node --test test/protocol-schema.test.js` (all passed);<br>Bilingual `DD-02` corrected to actual workflow `publish.yml`; handoff doc Section 6 updated with full task lifecycle specification; removed fragile fixed test counts covered by full unit test suites; in Linux WSL2, `g++ -fsanitize=address,undefined` executed 100,000 tight-buffer mutations with exit code 0, 0 out-of-bounds reads, 0 crashes. | Bilingual docs, Schema/Fixture, design differences, and firmware handoff achieve exact field-by-field parity; explicit statements added that `device.restart` cannot be marked `succeeded` before reboot and `verification: none` actions finish with `verified: false`. |

### 23.2 Three Boundary Declarations (Production vs. Simulation vs. Real Hardware)
1. **Hardware-Verified Baseline (G0)**: On LuatOS ESP32C3-CORE + R60ABD1 physical hardware, gates G0-01 through G0-05 have been verified, including the 2-hour offline endurance run (7,198 samples, 0 reboots, 0 heap leaks, net advance of 34,878 valid radar frames); compiled firmware binaries are indexed in `docs/reviews/web-console/g0-evidence-index.json`.
2. **Current Simulator Scope (Contract Stub Only)**: `static/src/protocol/simulator.js` serves solely as a contract stub for frontend UI development without attached hardware. It mirrors the 8 R60 configs, 2 confirmed actions, structured polygon/area validations, and session lifecycle. **Passing simulator tests does NOT indicate that the WP-2 firmware service layer is complete.**
3. **Future Production Firmware Boundary (WP-2)**: Dual-slot atomic NVS (`ConfigService`), real asynchronous job scheduling (`JobService`), live Wi-Fi scanning and provision state machine (`WiFiService`), and zero-copy UART drivers will be implemented in WP-2 and verified on physical G0 hardware.

### 23.3 Final Phase Verdict

**Verdict**: **"G1 Remediation Candidate, Pending Independent Re-review"**.
This round resolves all G1-R1 through G1-R5 acceptance findings, executes dual-platform automated regressions and Sanitizer memory verification, does not self-declare protocol freeze, and does not enter WP-2/WP-3.

## 24. WP-2 production firmware core (software). G2 hardware is not_run

The user reported that G1 passed independent final review, including G1-R1..R5 and the last documentation and boundary tests (`test:unit` 106/106). That acceptance is recorded here. It does not make this section a G2 hardware pass. The JS simulator remains a contract stub.

### 24.1 What was implemented

Production code is `components/mmwave_host/`, separate from the G0 probe under `docs/reviews/web-console/g0/`. `HostTransport` is the ESPHome USB Serial/JTAG owner plus `MwcpTxPump` (64-byte, 250 ms zero-write abandon, leading `0x00` resync). `SessionService`, `ConfigService`, `JobService`, `WiFiService`, and `LogService` live in `mwcp_service.cpp` and are host-tested with injected storage, Wi-Fi, clock, and radar view. `R60ABD1Component` gained a null-by-default observer. HA publish behavior is unchanged when no host is attached. Old `tests/r60abd1-esp32c3.yaml` still includes Improv and does not load `mmwave_host`.

`tests/r60abd1-esp32c3-host.yaml` is the host-enabled profile: native USB owned by MWCP, logger `UART0` at `baud_rate: 0`, `CONFIG_ESP_CONSOLE_NONE`, `wifi`/`api` `reboot_timeout: 0s`, no `improv_serial`. Radar UART remains GPIO21 TX / GPIO20 RX at 115200. Entity names come from `tests/common/r60abd1_mwcp.yaml`, which is the shared radar core without the device package.

Known difference, not a silent protocol edit: the G1 simulator reclaims expired jobs before the `op_id` check. Production follows the accepted handoff order: idempotency, then resource mutex, then reclaim, then capacity. A full protected table still returns the original `job_id`.

### 24.2 Commands actually run this round

| Command | Result |
| --- | --- |
| `g++ -std=c++14 -fno-exceptions -fno-rtti -Wall -Wextra -Werror` `protocol/cpp/mwcp_service_test.cpp` | `mwcp service test passed`, exit 0 |
| `esphome==2026.9.1` / ESP-IDF 5.5.5 `compile tests/r60abd1-esp32c3-host.yaml` | exit 0. RAM 149656/321296. Flash 882008/1835008 |
| same toolchain `compile tests/r60abd1-esp32c3.yaml` | exit 0. RAM 107704/321296. Flash 940384/1835008 |

Host OTA SHA-256 `9920F0EC415C3C81B8D0600BEBD3F13678D3934FDC51CF63B42D4CA0B88DDDE4`. Host factory SHA-256 `270D84486B9F0876A8AEDA8D24C368DA26D1105C1B3F5A9BF5C5583DDFDA510C`. These are link-time sizes, not runtime heap or stack, and not G0 probe measurements.

Workspace `86fc3ea156a13df3410a9fec619a7a7e72203fb6`. Component `9a524b8e8b02ffb496d808250567d7169fe264d5` plus uncommitted G1 and this WP-2 work. Nothing was committed, pushed, published, or flashed.

### 24.3 G2 matrix

| ID | Status | Plan cases | Environment | What ran | Evidence | Why not pass |
| --- | --- | --- | --- | --- | --- | --- |
| G2-01 | not_run | P-08..P-10, P-04..P-06 | host test + compile only | HELLO, replay, `ID_REUSE`, session TTL, USB exclusive compile | `mwcp_service_test` | No authorized port. DTR hang and real handshake not measured |
| G2-02 | not_run | P-11 | host code | Capability table copied from the R60 fixture, page size 2 | source | Hardware pagination not run |
| G2-03 | not_run | T-02..T-10 | observer hook | `speed_cm_s` stays null; observer is not a second UART reader | `r60abd1.cpp` | No live radar sample this round |
| G2-04 | not_run | C-01..C-14 | host test | Validate has no side effect; commit CAS, idempotency, `OP_ID_REUSE`, failed persist rolls back, dual-slot corruption is `recovery_required` | `mwcp_service_test` | No power-cycle, no HA card sync on a device |
| G2-05 | not_run | A-01..A-03 | host test | Full table idempotency, 299999 protected, 300000 reclaimed, capacity `BUSY` does not start Wi-Fi, restart stays `running` until reboot, reboot clears jobs and keeps revision | `mwcp_service_test` | No real `device.restart` or `radar.reset_module` |
| G2-06 | not_run | W-01..W-04 | host test + firmware port | Status has no password field; scan sort/cap and provision rollback are in the service; firmware calls `start_scanning` / `start_connecting` / `save_wifi_sta` | source | No live AP scan or bad-password rollback |
| G2-07 | not_run | S-01..S-04, R-01 | partial | Logs default off; password buffer cleared after provision | source | Ring overflow and secret scan not measured on device |

Runtime heap, minimum free heap, largest block, stack high-water, host loop time, and RPC latency for this production image were not measured. Do not reuse G0 probe numbers for them.

### 24.4 WP-3 handoff

Supported now in firmware, not in the console UI: HELLO/PING/SESSION_CLOSE, DEVICE_INFO, paginated CAPABILITIES_LIST, STATUS_GET, CONFIG_VALIDATE/COMMIT/COMMIT_STATUS, ACTION_START/JOB_GET for `device.restart` and `radar.reset_module`, WIFI_STATUS/SCAN/PROVISION, SUBSCRIBE for telemetry. CONFIG_READ and WIFI_SCAN_RESULTS paging are not complete in this build. Queued events are flushed on a later loop when the TX pump is idle. Unknown job state means no record, not proof the action never ran. `verification: none` finishes `verified: false`. Dual-slot corruption does not factory-reset. No BLE, no raw UART, no mock injection.

### 24.5 Still required before any hardware run

Name the board and native USB path, current VID/PID, GPIO wiring, the host OTA hash above, whether current firmware must be kept, and that full-chip erase stays forbidden. G0 authorization does not cover this image. No port was opened.

## 25. WP-2 independent-review remediation (R1–R9). Not a G2 pass

Section 24 overstated several commands as implemented. This section replaces those claims. G2-01–G2-07 stay `not_run`. Compile success is not production completion.

| ID | Change | Test actually run | Still not done |
| --- | --- | --- | --- |
| R1 | `MwcpHostLink::queue_json` copies encoded bytes into the pump buffer. `mwcp_dispatch_request` does not call `handle` when a control frame is already queued. Restart waits for `usb_serial_jtag_wait_tx_done(0)` after the driver accepted the control frame. | `protocol/cpp/mwcp_r_test.cpp` plus `static/test/mwcp-production.test.js`: captured wire is not all zeros; JS `decodeWire` + `validateResponse(HELLO)` passed | Host-received completion is the IDF wait, not a USB analyzer. No hardware backpressure run |
| R2 | Host profile number `set_action` calls `submit_number`, which persists through `ConfigService` and then `apply_to_radar`. Number lambdas in that profile read `calibration()`, not globals. Old `r60abd1.yaml` is unchanged | Host YAML compiled. Software apply path is in `mmwave_host.cpp` | No automated HA/web round-trip test. Polygon text and area text still write globals. Cold-start HA sync is not_run |
| R3 | `CONFIG_VALIDATE` calls `apply_changes(..., publish=false)` and restores the full boundary array. `yaw=999` and non-array `areas.definitions` are rejected | `mwcp_r_test`: triangle bytes unchanged after validate; yaw and invalid areas rejected | Area slot geometry, disabled-slot rules, and per-field step matrix are not fully implemented |
| R4 | Slot choice uses uint64 decimal compare, not `strcmp`. `persist_config` readbacks the stored blob before `persisted:true` | `mwcp_r_test`: commit through revision 10, new object `load_storage` returns 10 | The host test storage is one buffer, not a separate volatile cache and flash. Power-fail injection is not_run |
| R5 | Negative cursors are rejected before indexing. `CONFIG_READ`, `UNSUBSCRIBE`, and `WIFI_SCAN_RESULTS` no longer return `UNSUPPORTED` | Negative cursor assertion in `mwcp_r_test`. HELLO JSON passed the frozen schema | `CONFIG_READ` currently returns only x/z, not a full 8-key page. `UNSUBSCRIBE` clears every stream. `WIFI_SCAN_RESULTS` does not yet page the scan table. These are partial, not “done but untested on hardware” |
| R6 | `radar.reset_module` calls the injected adapter. Same `op_id` does not call it again | `mwcp_r_test`: send count stays 1 | No device UART capture. `verified` stays false |
| R7 | Connect success requires a non-empty IP other than `0.0.0.0` and the requested SSID. Provision has a 60 s deadline | Code review of `poll_connect` / service deadline. Not a live AP test | Scan completion, auth mapping, and credential rollback were not re-proven against a radio |
| R8 | `poll` expires the session without a new request and stops telemetry | `mwcp_r_test`: 20 polls after TTL produced 0 events | Rate/budget, stale targets, breath/heart observer, and the log ring are not covered by that test |
| R9 | Production test is `node --test test/mwcp-production.test.js` with `MWCP_GPP`. It is part of `npm run test:unit`. `device_id` is the STA MAC. `git_sha` comes from `git rev-parse` at codegen, or null | JS test passed. `esphome==2026.9.1` compiled host and old `r60abd1-esp32c3.yaml`, both exit 0 | Runtime heap, stack, and RPC latency were not measured. Do not reuse G0 probe numbers |

Host OTA SHA-256 after this round: `2ABCB5E2D640671EC78189E931AC0170D2487742A6E0B0326907A2580F9BD639`. Factory: `B4F074FFCADBE25F40E0ADAE6D118016DC6EA0F0C90E5A0E323BB49E72093B08`. Link-time RAM 154968/321296, flash 886188/1835008.

Nothing was flashed, committed, or published. G2 is not passed.

## 26. Follow-up software remediation (A–F). Still not a G2 pass

Section 25 listed the holes. This round closed the ones that were reproducible in software. It does not finish every field of R8, and it does not pass G2.

ESPHome 2026.9.1 `ESP32PreferenceBackend::save` only appends to `s_pending_save` and returns true (`esphome/components/esp32/preferences.cpp`). Durable write is `ESP32Preferences::sync()` → `nvs_set_blob`. The same file says `nvs_commit` is a no-op on ESP-IDF. The host calls `sync()` and then readback. A failed sync does not publish.

| Item | Status | What changed | Test |
| --- | --- | --- | --- |
| A config transaction | done in software | `apply_ha_number` restores install, boundary, areas, and revision if persist fails. USB commit and HA write call `publish_hook` → `apply_to_radar` (install, polygon, enabled area points). Host YAML number/polygon actions check the bool and do not publish a failed input | `mwcp_af_test`: save failure keeps z and revision; success publishes once |
| B areas | partial | slot range, uniqueness, enabled type, empty enabled polygon rejected; disabled empty slot stored and read back | `mwcp_af_test` slot 99 and disabled slot. Area self-intersection is not checked |
| C commands | partial | `CONFIG_READ` pages all 8 keys with `cfg:` cursors. `UNSUBSCRIBE` removes only named streams. `WIFI_SCAN_RESULTS` returns the scan just completed, RSSI sorted | `mwcp_af_test` collects 8 keys once, unsubscribe logs keeps telemetry, two APs sorted. Scan result paging is still the first page only |
| D storage / Wi-Fi | partial | cache/sync/readback split. Sync failure does not publish. Commit refuses `recovery_required` and uint64 max | `mwcp_af_test` sync failure. uint64-max and full commit-ring failure were not executed this round. Live radio remains not_run |
| E telemetry / logs | partial | subscribe echoes accepted streams and reads `max_rate_hz`. Byte budget drops an oversized telemetry emit. Breath, heart, and distance observers fire even if the HA sensor pointer is null. Logger callback redacts `password` and counts drops | rate/budget and stale-target cases were not added as failing tests this round |
| F false pass | fixed for the cited case | triangle validate now requires `mwcp_dispatch_request` to return true after the previous control frame is pumped | `mwcp_r_test` and `static/test/mwcp-production.test.js` passed |

Commands this round: `g++ -Wall -Wextra -Werror` `mwcp_r_test` and `mwcp_af_test`, both exit 0. `node --test static/test/mwcp-production.test.js` with `MWCP_GPP` passed. `esphome==2026.9.1` compiled `tests/r60abd1-esp32c3-host.yaml` and `tests/r60abd1-esp32c3.yaml`, both exit 0.

Host OTA SHA-256 `41FD3AC4AF25F77273229A3F13AA6909DC27BF1554F73D2D07115B2EE163B3F3`. Factory `7B56A98B6E5343692E21FD8EB43189EDDC90BAB17CFFAADF755EA0025D9FE35A`. RAM 154992/321296, flash 893778/1835008. `git_sha` is `git rev-parse HEAD` at codegen. The tree is dirty, so that SHA is not a byte-for-byte source snapshot.

Still not done, and not “hardware only”: area polygon self-intersection, scan-result pages after the first, uint64-max and full-ring failure tests, stale target quality, full JSON escaping of log lines, HA area-text entities in `_areas.yaml` (they still write globals). G2-01–G2-07 remain `not_run`. Nothing was flashed or committed.

## 27. AF-1–AF-6 software fixes. Not a G2 pass

| Item | Status | Fix | Test |
| --- | --- | --- | --- |
| AF-1 | done in software | Same-value check compares `boundary_set_`, count, and all vertices before skipping persist. A different polygon with the same count bumps revision and is what cold start loads. `_areas.yaml` calls `radar.try_commit_area`; old profiles still use globals when no host is attached | `mwcp_af_test`: `[[1,1]...]` then `[[100,100]...]` keeps 100 after `load_storage` |
| AF-2 | partial | Area self-intersection, duplicate points, and zero area are rejected. `CONFIG_READ` emits stored points and JSON-escapes names. Overflow returns an error instead of a truncated success | Self-intersection assertion passed. A 64-point plus 3-area byte-for-byte round trip was not executed |
| AF-3 | partial | Scan cursor is parsed; page 2 is not page 1. SSID is escaped | 3-AP test: cursor `"2"` returns the third AP and `next_cursor:null`. Live auth mapping and `save_wifi_sta` failure visibility remain limited by ESPHome's void `save_wifi_sta` |
| AF-4 | partial | `password=MARKER_SECRET` becomes `password=<redacted>` before the log event. Quotes and newlines are escaped | `mwcp_af_test` asserts the marker is absent and `<redacted>` is present. Emoji and log-flood priority were not tested |
| AF-5 | partial | Position quality is `stale` at 6000 ms. No presence does not keep a valid target. Budget counts header, CRC, and COBS overhead | Not covered by a dedicated rate/budget assertion this round |
| AF-6 | partial | A failed commit restores the previous ring slot and `commit_next_`, not just `used=false` | `mwcp_af_test` fills 4 commits, fails the 5th, and still finds the oldest `op_id`. uint64-max was not executed. `mwcp_af_test` now runs inside `static/test/mwcp-production.test.js` |

`mwcp_r_test` and `mwcp_af_test` exited 0. `esphome==2026.9.1` compiled host and the old R60 profile, both exit 0. Host OTA SHA-256 `9268EFE03DFACBDA9D93E465123B3363694CD9EEA4B5ADA486E5F97827379D4D`. Factory `20FDB61F9E4F3AD3FF04DB606CAC4F412CCB4F635527CBBE0D1FC34490125D78`. RAM 155184/321296, flash 897774/1835008. The tree is dirty, so the build `git_sha` is not a full source snapshot. G2 hardware stays `not_run`. Nothing was flashed or committed.

## 28. AF close-out recheck. Software is not finished. G2 was not run

| Item | Status | What changed | What was actually run | Still open |
| --- | --- | --- | --- | --- |
| AF-4 | software fix tested | `redact_secrets(in, out, cap)` writes a bounded copy. Quoted values, including spaces and escapes, are replaced with `<redacted>`. If the replacement does not fit, the copy stops before the key. The log path calls this function, then `json_escape`, then `emit_event` | `mwcp_close_test`: 160-byte buffer with a canary, quoted `MARKER_SECRET` through `push_log_at` / `next_event`, empty and multiple secrets, emoji truncation. The emitted log frame was decoded by `validateEvent` | MinGW g++ 13.3.0 has no `-lasan` / `-lubsan`. ASan/UBSan was not run. That is not a pass |
| AF-1 | software fix compiled | Shared `tests/common/_areas.yaml` is back to the old global + script path. Only `tests/common/_areas_host.yaml`, included by the host profile, calls `id(host_link).commit_area_text`. No empty methods were added to other radars. `Service::apply_area_text` builds the full area array without a leading comma and keeps other slots' names, enabled flags, and vertices | Empty config slots 1 and 2, sparse slots, custom name, clear, invalid input, persist failure with no publish, cold start. Compile matrix below | HA entity state was not executed on a device. The yaml assigns the global only when commit returns true |
| AF-2 | partial | Self-intersection rejection kept. 64-point boundary and 3 max areas commit and survive `load_storage` field by field, including `门口`, `a"b`, and `c\d`. A page that cannot be encoded returns `PAYLOAD_TOO_LARGE` instead of silence or a truncated success | Boundary page request id matched and the JS schema check passed. The following areas page returned `PAYLOAD_TOO_LARGE` | Frozen `JSON_MAX_DEPTH=8` cannot carry `areas.definitions` inside the response envelope (root/result/items/item/value/slot/points/point/number is depth 9). The checker was not weakened. Area `CONFIG_READ` is therefore not done |
| AF-3 | partial, not complete | Scan auth is `open` or `unknown`. It is not guessed as `wpa2_psk`. `persist_credentials` returns true only after write, sync, and readback match. Production `persist_wifi` calls that function and does not treat `save_wifi_sta()` as success. Unchanged scan results are held until the fingerprint changes or 15 s elapses | Adapter fault injection: write fail, sync fail, readback fail, success, stale fingerprint | ESPHome 2026.9.1 `WiFiScanResult` only exposes `get_with_auth()`. WPA2 vs WPA3 vs enterprise cannot be known without changing ESPHome or the contract. Live NVS was not executed |
| AF-5 | software tests passed, not a hardware pass | Telemetry `metrics` include `distance.cm`, `breath_rate`, and `heart_rate` with their own `sample_ms`. Position is `stale` at 6000 ms. No presence does not keep a target. Each stream keeps its own accepted rate. Logs use `encode_frame` wire bytes against `event_budget_bps` and cannot be emitted while a control frame is queued | Same-millisecond 100-log flood dropped. 20 Hz logs stopped inside a 1000-byte window. `validateEvent` plus `telemetryIssue` passed on the captured telemetry frame | `motion.state`, `body.movement`, `sleep.state`, and `areas.occupancy` stay `unknown` because this observer does not have those samples. `speed.cm_s` is `unsupported` |
| AF-6 | regression wired, WP-2 not closed | uint64 max loaded from a CRC'd blob. USB and HA writes return failure, do not wrap, and do not change storage. `static/test/mwcp-production.test.js` compiles `mwcp_close_test` and schema-checks every `WIRE` line. Missing `g++` throws. `.github/workflows/web.yml` now includes `components/mmwave_host/**` | `node --test static/test/mwcp-production.test.js` exit 0 (`# pass 1`, `# fail 0`) | G2-01–G2-07 remain `not_run`. This section is not a WP-2 close-out |

Commands and exit codes:

- `g++ -std=c++14 -Wall -Wextra -Werror` `protocol/cpp/mwcp_close_test.cpp`: exit 0, `mwcp close test passed`.
- Same flags for `mwcp_af_test`: exit 0.
- `node --test --test-timeout=120000 static/test/mwcp-production.test.js` with `MWCP_GPP`: `# pass 1`, `# fail 0`.
- `g++ -fsanitize=address,undefined`: link failed, `cannot find -lasan` and `-lubsan`. Not run.
- `esphome==2026.9.1` compile, all exit 0: `tests/r60abd1-esp32c3-host.yaml`, `tests/r60abd1-esp32c3.yaml`, `tests/ld2450-esp32c3.yaml`, `tests/ld2451-esp32c3.yaml`, `tests/ld2452-esp32c3.yaml`, `tests/ld2453-esp32c3.yaml`, `tests/ld2454-esp32c3.yaml`.

Host OTA SHA-256 `1D84EFB62F853C2A68E8DA230DB7106694120A8B4FFDBFD95B3EA62AE699CED7`. Factory `0B3BB77AEA959440A0A80971E174393CBC5F727601712988AA08D750EE661E5A`. This compile did not reprint the RAM/flash line. `git_sha` is still `git rev-parse HEAD` on a dirty tree, so it is not a byte-for-byte source snapshot. Nothing was flashed or committed.

## 29. Second AF recheck. Not a WP-2 close-out. G2 not run

| Item | Status | Change | Evidence | Still open |
| --- | --- | --- | --- | --- |
| AF-5 | software fix tested | Production loop no longer uses a 768-byte buffer. `MwcpHost::loop` and the test call the same `mwcp_forward_events`. Event slots and that buffer are `kMaxEventJson` (2048). An event that cannot be encoded is counted in `unsent_events` and removed, so it cannot sit at the head forever | `mwcp_close_test` forwards a Service telemetry event through `MwcpHostLink` and the TX pump, including a 1-byte short write and a zero write. The decoded payload is longer than 768 and contains distance, breath, and heart. JS `validateEvent` passed on that wire. A log queued behind it was forwarded after the telemetry frame | Not a hardware rate measurement |
| AF-4 | software fix tested | Redaction now treats `wifi_password`, `ota_password`, `ap_password`, `sta_password`, `api_key`, `password`, `passwd`, and `psk`, including a JSON key quote before `:` and single-quoted values. A key that cannot be bounded drops the whole log | The three reproduced lines go through `push_log_at`, `mwcp_forward_events`, and wire decode. `MARKER` and `SECRET` are absent. Prior canary, expansion, and emoji cases still pass | ASan/UBSan still cannot link: MinGW g++ 13.3.0 has no `-lasan` or `-lubsan`. Not a pass |
| AF-1 | software fix compiled | Host area text is `optimistic: false`. ESPHome `TemplateText::control` therefore does not publish the input. The yaml publishes only the canonical text after commit succeeds. Boot no longer applies old globals onto the radar. USB publish uses `commit_area_view` and `export_area_text` | Failed `commit_area_view` leaves the previous HA and global strings. A successful slot-1 write publishes `0,0;100,0;50,80` to both. Host, old R60, and LD2450–2454 compiled | HA entity state was not executed on a device. The entity test calls the same function the host uses, not a live `TemplateText` |
| AF-2 | pending contract decision | No schema, JS checker, or golden-vector change | A single triangle is enough. C++ `json_check` returns `depth` for `{"ok":true,"result":{"revision":"1","items":[{"key":"areas.definitions","value":[{"slot":0,"enabled":true,"name":"a","points_cm":[[0,0],[1,0],[0,1]]}]}],"next_cursor":null}}`. Root is depth 1; the point number is depth 9. `JSON_MAX_DEPTH` is 8 in `docs/protocol/README.md`, `protocol/cpp/mwcp_json.cpp`, and `static/src/protocol/json.js`. The schema does not encode that depth. Paging cannot shrink one area item. Current device returns `PAYLOAD_TOO_LARGE` instead of a silent drop. That is not a pass | Proposed decision, not applied: raise `JSON_MAX_DEPTH` from 8 to 10. The parser is iterative, so the RAM cost is the existing depth counter, not a new stack. `JSON_MAX_KEYS`, `JSON_MAX_ITEMS`, and `max_payload` stay 64, 256, and 4096. Old clients that reject depth above 8 would reject area pages; new clients would accept them. Affected assets: both JSON checkers, README/README_CN, and any test that treats depth 9 as corrupt. Do not implement until a maintainer confirms |
| AF-3 | partial, not complete | Completion is a `WIFI_EVENT_SCAN_DONE` generation, not a 15 s fingerprint timeout. Timeout, start failure, and non-zero event status return failure and do not copy the previous AP list. A completed scan with the same or empty result copies the current list. Persist failure writes the previous credentials back | `collect_scan` tests: timeout copies 0 times; start failure and radio failure copy 0 times; a new generation copies once. Sync failure restores `old` / `old-pass-1` | `scanItem.auth` is an unconstrained string, so `unknown` validates. `WIFI_PROVISION` still accepts only `open` and `wpa2_psk`. Copying `unknown` into provision is rejected. That is compatible without a contract edit, but the console must ask the user for `open` or `wpa2_psk`. ESPHome still cannot name the real auth mode. Live NVS and a live scan were not run |
| AF-6 | regression wired, WP-2 not closed | uint64 max, request id matching, and production wire checks remain. `npm` unit entry compiles `mwcp_close_test` and fails if `g++` is missing | `mwcp_close_test` exit 0. `mwcp_af_test` exit 0. `node --test static/test/mwcp-production.test.js` `# pass 1`, `# fail 0`. Host compile exit 0. Old R60 and LD2450–2454 compile exit 0 | G2-01–G2-07 remain `not_run`. AF-2 is waiting on a maintainer. This is not a G2 pass |

Host OTA SHA-256 `292E78578C0A721C0AEF9E574937B4F77C9A849CD18FEFE9956EA0A5B358DC3E`. Factory `79E69CC85A5B72F04836EA413EEE880356DD3EFCBB053429762E3C85FAD7F0FA`. RAM 178600/321296, flash 902698/1835008. The tree is dirty, so `git_sha` is not a byte-for-byte source snapshot. Nothing was flashed or committed.

## 30. Approved contract changes applied. AF-2 areas page round-trips. G2 still not run

The maintainer approved three things: raise `JSON_MAX_DEPTH` from 8 to 10, allow `scanItem.auth` to be `unknown`, and retry the sanitizer build with the updated MinGW64. All three were executed this round.

| Item | Change | Evidence | Still open |
| --- | --- | --- | --- |
| Depth 10 | `protocol/cpp/mwcp_json.cpp` now rejects only `depth > 10`. `static/src/protocol/limits.js` sets `JSON_MAX_DEPTH = 10`. `docs/protocol/README.md` and `README_CN.md` record 10 and why. The schema never encoded depth and is unchanged by this item. `JSON_MAX_KEYS`, `JSON_MAX_ITEMS`, and the payload caps are untouched | `static/test/protocol-codec.test.js` now asserts an 8-wrapper document (number at depth 10) passes and a 9-wrapper document fails with `depth`. `mwcp_close_test` asserts a depth-9 area page passes `mwcp::json_check` and a depth-11 document is rejected with error code `depth` | Old clients that reject depth above 8 would reject area pages; the frozen-contract risk is now accepted by the maintainer |
| Areas page | With depth 10 the `CONFIG_READ` builder accepts the `areas.definitions` item through the same `json_check` gate. The close test no longer asserts `PAYLOAD_TOO_LARGE` for the areas page — that assertion was replaced: after the max config commit, the response either merges boundary and areas into one page (`next_cursor: null`) or continues on a follow-up page, and the test asserts `"ok":true`, the `门口` area name, and the absence of `PAYLOAD_TOO_LARGE` in both shapes. It now follows the cursor and sends the follow-up request with a fresh request id when one is present | Close test compiled and run: `mwcp close test passed`, exit 0 | Not a live radio verification |
| scan auth unknown | `scanItem.auth` in `mwcp-v1.schema.json` changed from an unconstrained string to `wifiAuth` or `"unknown"`. `WIFI_PROVISION` still accepts only `open` and `wpa2_psk`; the regression test now asserts `unknown` validates inside a scan item and is rejected inside a provision request | `npm run test:unit` 107/107 | The device firmware still names only `open` / `unknown` (ESPHome `get_with_auth()`); the console must still ask the user, and `unknown` must not be copied into `WIFI_PROVISION` |

Commands this round (Windows, Node, esphome 2026.9.1 / ESP-IDF 5.5.5):

- `D:\Build\w64devkit\bin\g++.exe` 14.2.0, `-std=c++14 -fno-exceptions -fno-rtti -Wall -Wextra -Werror`: `mwcp_close_test` exit 0 (`mwcp close test passed`), `mwcp_af_test` exit 0.
- `node --test` of `protocol-codec.test.js`, `protocol-schema.test.js`, `protocol-regression.test.js`, `mwcp-production.test.js`: 30 pass, 0 fail.
- `MWCP_GPP=<w64devkit g++> npm run test:unit`: 107 pass, 0 fail. Without `MWCP_GPP` the two compiler-entry tests fail closed (that is the designed behavior, not a regression).
- `npm run test:browser`: 2 pass, 0 fail. `npm run build`: exit 0 (Vite).
- `esphome compile`, all exit 0: `tests/r60abd1-esp32c3-host.yaml` (RAM 178600/321296, flash 902698/1835008), `tests/r60abd1-esp32c3.yaml` (RAM 107704/321296, flash 940512/1835008), `tests/ld2450-esp32c3.yaml`, `tests/ld2451-esp32c3.yaml`, `tests/ld2452-esp32c3.yaml`, `tests/ld2453-esp32c3.yaml`, `tests/ld2454-esp32c3.yaml`, `tests/r60abd1-esp32c3.factory.yaml`.
- `python -m unittest tests.unit.test_mwcp_sources -v` (workspace): 2 tests OK.

ASan/UBSan now run. History: the first retry used the then-current `D:\Build\w64devkit` GCC 14.2.0 and still failed to link (`cannot find -lasan`, `-lubsan`), and no other compiler existed on the machine at that time. The maintainer then replaced the toolchain with `D:\msys64\clang64\bin` (clang 23.1.3, MSYS2) — which removed `D:\Build\w64devkit` — and requested a new retry. A seeded heap-overflow probe (write past a `new int[3]`, exit 1 with a genuine `heap-buffer-overflow` report) confirmed the runtime actually detects faults on this toolchain. Then, with `clang++ -std=c++14 -fno-exceptions -fno-rtti -Wall -Wextra -Werror -fsanitize=address,undefined`:

- `mwcp_close_test` (+ `mwcp_wifi_adapter`): exit 0, `mwcp close test passed`, no sanitizer report, no leak report
- `mwcp_af_test`: exit 0
- `mwcp_host_test` (golden vectors): exit 0

One portability fix was required: `protocol/cpp/mwcp_close_test.cpp` now includes `<cmath>` because clang's libc++ does not expose `std::cos`/`std::sin` through `<math.h>`. Test-only; production code is unchanged, so the firmware hashes above remain current. Both touched `protocol/cpp` files are clang-format clean under the repo-standard `clang-format==22.1.8` (a newer local clang-format 23 printed extra violations that are version skew; they were not applied). The JS suites were re-run with `MWCP_GPP` pointed at `clang++`: the four protocol test files 30/30 and full `npm run test:unit` 107/107; `npm run test:browser` (2/2) and `npm run build` were already green this round and do not depend on the compiler. G2-01–G2-07 remain `not_run`. Nothing was flashed or committed.

New firmware hashes: Host OTA SHA-256 `766E65435D09FE79ABF1FAA9252B98E8C862AE0C573A557B65D27A0905A0B146`. Factory `E8C82DD843501094818592A57F9198014B35421C6D4771FA50B1DE4158687D77`. Both changed from section 29 because the depth constant compiles into the firmware. The tree is dirty, so `git_sha` is not a byte-for-byte source snapshot. G2-01–G2-07 remain `not_run`. Nothing was flashed or committed.

## 31. Scan results bound to completion. Start failures bounded. G2 still not run

AF-3 is now implemented in the production path, not just in the test seam. `ScanBridge` treats the raw `WIFI_EVENT_SCAN_DONE` as the completion gate and the ESPHome `WiFiScanResultsListener` as the "result list has been replaced" signal. A successful non-empty scan finishes only after both facts have been observed for the current request; the listener copies the list exactly once. A failure fails the job without publishing; a zero-AP completion finishes with an empty snapshot, so the previous scan's records cannot leak. `start()` clears the event slot before asking the platform to start and arms capture only after the start call returns, so a completion queued before the request is not attributed to it. A timeout with no event enters a bounded 31 s drain (`kDrainMs`), during which a new scan is refused; a late event is consumed by the drain and cannot complete a retry. A timeout where the raw success was already seen but the listener is late goes directly to idle: the driver has finished, so no quarantine is needed. `poll()` returns `-1` while draining, which lets the service's radar-timeout branch run instead of reporting a false `VERIFY_FAILED`. `tick(now)` runs before `service_.poll(now)` in the host loop, so quarantine advances even when the caller has abandoned the job.

The component wiring is complete. `mmwave_host.cpp` registers the raw event handler and a `ScanResultsListener`, and fails the build through `#error` if `USE_WIFI_SCAN_RESULTS_LISTENERS` is not defined. `__init__.py` calls both `wifi.request_wifi_scan_results_listener()` and `wifi.request_wifi_scan_results()`: the first makes ESPHome compile the listener interface, the second makes the driver return the full scan list instead of only configured networks. The host profile compiles with the new code. The start precondition checks are explicit: missing registration, a null Wi-Fi component, `is_disabled()`, and `is_roaming_scan_active()` fail the job before a start is issued.

The regression lives in `protocol/cpp/mwcp_scan_test.cpp`. It drives the real `Service` and `ScanBridge` through `WifiPort` and covers: raw completion before ESPHome updates the list (old AP is not served, the job stays `running`, `WIFI_SCAN_RESULTS` returns `BUSY`); the listener completing that scan once with the new AP only; zero AP while the old list is still non-empty (empty list, no copy); identical results; same-count different results; start refusal; registration refusal; radio failure; timeout without a copy plus a refused retry during drain and a late event that must not complete it; a fresh scan after the late event returning its own data; consecutive scans never reusing the previous snapshot; and release after the drain deadline. The legacy baseline printed `legacy poll n=1 ssid=OLD_AP` and `LEGACY BUG REPRODUCED: scan-done generation advanced before ESPHome updated the results list; old AP delivered`; the new test asserts the opposite (`old list was not copied`, `new AP is published after the list update`).

One bring-up defect was found and fixed before the test passed. The first listener implementation rejected a valid completion when the listener arrived before `poll()` had consumed the stored raw event, because it checked `raw_success_` without draining the slot. `ScanBridge::on_results` now drains the slot first, then handles `status != 0` (idle, no copy), `number == 0` (complete with an empty snapshot), and the successful non-empty case (`raw_success_`, copy on the listener), and `poll()` uses the same event handling. The test also spans more than the 15 s session TTL and would exceed the 8-job table, so it re-HELLOs with fresh nonces and continues on a fresh `Service`; that is test harness plumbing, not production behavior.

Start failure is still partly outside the public ESPHome API. `WiFiComponent::start_scanning()` (`wifi_component.cpp:1349`) discards the `bool` returned by `wifi_scan_start_()` and unconditionally sets `WIFI_COMPONENT_STATE_STA_SCANNING`; a driver-level refusal is therefore indistinguishable from a slow scan. The service reports `RADAR_TIMEOUT` at its 15 s scan deadline, and the bridge may then quarantine the radio for up to 31 s, refusing an immediate retry. The component reports `RADAR_UNAVAILABLE` only for the preconditions it can see; it never publishes a stale list. A direct `esp_wifi_scan_start()` probe was evaluated and rejected: it bypasses `WIFI_COMPONENT_STATE_STA_SCANNING`, so ESPHome's post-connect roaming can adopt our `SCAN_DONE` and act on our results. Closing the gap needs a small, source-compatible upstream change: make `start_scanning()` return the `wifi_scan_start_()` result and set `WIFI_COMPONENT_STATE_STA_SCANNING` only on success (`wifi_component.h` declaration plus `wifi_component.cpp`; all four platform `wifi_scan_start_()` implementations already return `bool`, and the three in-tree callers ignore the result). No vendor file was patched this round, so this remains an adaptation item, not a completed fix.

Verification this round (Windows, Node, esphome 2026.9.1 / ESP-IDF 5.5.5, `MWCP_GPP=D:\msys64\clang64\bin\clang++.exe`):

- `mwcp_scan_test` built with `-std=c++14 -fno-exceptions -fno-rtti -Wall -Wextra -Werror`: `mwcp scan test passed`, exit 0.
- Same test with `-fsanitize=address,undefined -fno-sanitize-recover=all`: `mwcp scan test passed`, exit 0. `mwcp_close_test` and `mwcp_af_test` were rebuilt against the current sources and also passed under ASan/UBSan, exit 0.
- `npm run test:unit`: 107 pass, 0 fail. The two compiler-entry tests require `MWCP_GPP`; without it they fail closed by design.
- `python -m unittest tests.unit.test_mwcp_sources -v` (workspace): 2 tests OK.
- `esphome compile tests/r60abd1-esp32c3-host.yaml`: success, RAM 181708/321296, flash 904352/1835008. The other seven profiles were compiled in the previous round; only the host profile contains `mmwave_host`, and it was rebuilt after the final formatting/comment changes.
- `clang-format==22.1.8`: the new `mwcp_scan_test.cpp`, the rewritten adapter, and the changed `mmwave_host` regions are clean (`--dry-run --Werror`, exit 0). The pre-existing `mwcp_service.cpp` and other untouched code still contain ESPHome-style single-line `if` statements that the checked-in `.clang-format` (which disables them) would reflow; they were not reformatted wholesale to keep the review diff focused.

New firmware hashes from this R1-only build (superseded by section 32): Host OTA SHA-256 `A49F5E4C6B0FCFA03E14F6F4AEB7BC7C8692DEE819F037EAF6411F278818E65A` (904704 bytes). Host factory `315618B9C5180B3979557B633FDC69BE43EE1D978AF610897F2D9B64889D88E1` (970240 bytes). The tree is dirty, so `git_sha` is not a byte-for-byte source snapshot.

Still not verified: no real Wi-Fi scan, NVS write, or HA entity test was run; G2-01–G2-07 remain `not_run`. Three scan-side residual risks stay open. (1) On a dual-core ESP32 the raw event handler and the main-loop listener run on different tasks; if the listener is delivered before the event-task handler stores the completion, the notification is ignored and the job fails closed on timeout rather than publishing stale data. (2) When disconnected, ESPHome may start its own retry scan; the public API cannot attribute or cancel it, and `scan_id` is a `uint8_t`, so it cannot identify a scan. (3) A driver-level start refusal is not observable through `start_scanning()`; it fails as `RADAR_TIMEOUT` after 15 s and can block the next scan for up to 31 s. Auth remains `open`/`unknown` because `get_with_auth()` is a boolean. The former `JOB_GET` failure-reason risk is closed in section 32. Nothing was flashed or committed.

## 32. JOB_CHANGED and JOB_GET share one complete job object. G2 still not run

R2 and R3 are now implemented in `components/mmwave_host/mwcp_service.cpp`. `Service::write_job()` is the single serializer for `JOB_CHANGED` (0x8004) and `JOB_GET` (0x0042). Running events and terminal events both carry `job_id`, `op_id`, `action_id`, `state`, `stage`, `progress`, `started_ms`, `finished_ms`, `result`, and `error`. A failed job publishes `result:null` and a structured `error:{code,message}`. A succeeded non-verifying job publishes `result:{"verified":false,"verification":"none"}` and `error:null`. Running and unknown jobs publish null result/error. The fixed messages are `Radar is unavailable`, `Radar operation timed out`, `Verification failed`, `Storage operation failed`, `Job resource is busy`, and `Internal job error`, with `Job failed` as the fallback. `finish_job()` explicitly terminates `error_code`; the event buffer and the `JOB_GET` buffer are both 512 bytes. No schema was loosened and no field was removed.

`protocol/cpp/mwcp_job_test.cpp` covers a successful scan (running and succeeded), start refusal (`RADAR_UNAVAILABLE`), radio failure (`VERIFY_FAILED`), scan timeout (`RADAR_TIMEOUT`), successful and failed reset, provisioning storage failure (`STORAGE_FAILED`), and an unknown job. It prints `JOBPAIR <event-wire> <response-wire>` for every pair. `static/test/mwcp-production.test.js` compiles the production service and adapter, decodes both frames, validates `JOB_CHANGED` and `JOB_GET` against the schema, and compares all ten job fields between the event and the `JOB_GET` result.

Verification this round (Windows, Node, esphome 2026.9.1 / ESP-IDF 5.5.5, `MWCP_GPP=D:\msys64\clang64\bin\clang++.exe`):

- `mwcp_job_test` with `-std=c++14 -fno-exceptions -fno-rtti -Wall -Wextra -Werror`: `mwcp job test passed`, exit 0.
- Same test with `-fsanitize=address,undefined -fno-sanitize-recover=all`: `mwcp job test passed`, exit 0. `mwcp_scan_test` also stayed green under ASan/UBSan.
- `node --test --test-timeout=120000 static/test/mwcp-production.test.js`: 1 pass, 0 fail; the scan, adapter, close, and job executables all compiled and ran.
- `npm run test:unit`: 107 pass, 0 fail.
- `esphome compile tests/r60abd1-esp32c3-host.yaml`: success, RAM 181708/321296, flash 905056/1835008.
- `clang-format==22.1.8`: the new `mwcp_job_test.cpp` and the new `write_job`/`job_error_message` regions are clean. The rest of `mwcp_service.cpp` retains the pre-existing single-line `if` style and was not reformatted wholesale.

Host OTA SHA-256 `EE29C62A9DD2B60EDDCED86E65C8059E6F5961B8E21CE6F9C0F8AC6CC146B7D0` (905408 bytes). Host factory `97DE59E4D5990B13B179C0BFA998A4FD88011F3FDC37C1E2B7A40F617192C1F2` (970944 bytes). The tree is dirty, so `git_sha` is not a byte-for-byte source snapshot. R1 remains a partial adaptation item as described in section 31. No real scan, NVS write, or HA entity test was run; G2-01–G2-07 remain `not_run`. Nothing was flashed or committed.

## 33. R1 closed on a pinned ESPHome patch. Scan ownership is exact. G2 still not run

R1 is now implemented against a repo-pinned ESPHome patch instead of an unobservable stock API. `patches/esphome-2026.9.1-wifi-scan-ownership.patch` (5 files: four modified files and the added `wifi_scan_ownership.h`; +222/−3) adds `WiFiComponent::start_scan_for_component(uint32_t *generation)` with an explicit start result, a completion listener called with the raw `(status, number)`, and roaming-suppression accessors. `scripts/apply_esphome_patch.py` pins `2026.9.1`, verifies the pristine and patched SHA-256 values (including the added header), applies with `git -c core.autocrlf=false apply -p1` only after `--check`, and is idempotent; CI has a `patch` job. The host profile builds from the patched tree; every other model profile stays on stock ESPHome. `components/mmwave_host/__init__.py` requests the completion listener only when the patched API exists and then defines `MWCP_WIFI_SCAN_OWNERSHIP`; on stock the code compiles the refusal path and `WIFI_SCAN` returns `UNSUPPORTED`. Section 31's `ScanBridge` description and its 31 s drain are superseded by this design.

`components/mmwave_host/mwcp_wifi_adapter.cpp` implements exclusive ownership. `acquire_owned_scan()` rejects a missing or disabled radio, an active connection-state-machine scan/connect, a roaming scan/roam, a pending earlier request, or a driver refusal before starting; a station connection is not required, so an unprovisioned device can list networks for first-time setup. It maps the dependency result to `ScanStart::{kStarted,kUnsupported,kBusy,kRefused}`. `ScanOwner` has four phases (`IDLE`, `WAIT`, `COMPLETE`, `FAILED`); `start()` refuses with `kBusy` while `WAIT`, drops an unpolled earlier completion, and only arms the request after the platform accepted it, recording the generation. `on_completion(generation, status, number, copy)` ignores any completion whose generation is not the active one, copies the list exactly once on success, maps a driver failure or an announced-but-unretrievable list to `FAILED`, and treats an announced zero-AP completion as a successful empty snapshot. `poll()` returns `-1` while waiting, the copied list once (`COMPLETE`, then resets), and `-2` on `FAILED`. `tick()` stops counting a `WAIT` after `kHoldBoundMs = 60000` and releases the suppression hold, but it does **not** release the dependency-owned radio: the ownership gate stays closed until the real completion event arrives, and a completion after the job finished is counted as ignored rather than published. There is deliberately no time-based ownership release.

The service maps those facts immediately: `kUnsupported` → `UNSUPPORTED` (`Unsupported operation`), `kBusy`/`kRefused` → `RADAR_UNAVAILABLE` (`Radar is unavailable`), retryable once the radio is idle. The scan deadline (`now + 15000`) is compared wrap-safely via `static_cast<int32_t>(now_ms - scan_deadline_ms_) >= 0` (`mwcp_service.cpp:1574`). An accepted scan whose dependency status fails → `VERIFY_FAILED`; no completion by the deadline → `RADAR_TIMEOUT`. The device never publishes a previous scan's records: while a scan job is pending, `WIFI_SCAN_RESULTS` returns `BUSY`; after a failed or timed-out scan the same page returns `items: []`; a refused start leaves no accepted job, so `WIFI_SCAN_RESULTS` for that `job_id` returns `INVALID_ARGUMENT`. If the completion event itself is lost, the ownership gate stays closed and later scans return `RADAR_UNAVAILABLE` until a completion arrives or the device reboots; the job deadline still reports `RADAR_TIMEOUT`.

The scan regression was rewritten around those counterexamples. It drives the real `Service` and the real `ScanOwner` through `WifiPort`, injects the fake platform via `acquire_owned_scan()`, and covers: (1) R1-A: A's completion is queued when A times out; the hold bound releases suppression only, the gate stays closed, a retry is refused, and processing A's late event copies nothing and reopens the gate, after which B returns only its own records; (2) a completion with no request is a background scan; (3) roaming and a busy connection-state-machine scan are refused before touching the radio; (4) driver refusal and disabled Wi-Fi fail with structured `RADAR_UNAVAILABLE`, while a disconnected station is not a refusal; (5) A times out, a retry is refused by the orphaned completion, and A's late event releases the gate for C; (6) an ultra-late completion cannot complete an immediate retry, and a fresh accepted scan returns its own data; (7) empty vs identical vs same-count-different lists; (8) failure never emits an old list, and OOM after announced records is not a successful empty result; (9) consecutive scans never reuse a previous snapshot; (10) the deadline comparison is correct across the uint32 wrap, including hold release after the wrap; (11) stock ESPHome fails with `UNSUPPORTED`; (12) an offline, never-provisioned device scans, provisions, reports `connecting`, persists the credentials, and reaches `connected` on the same job, without echoing the password.

The job regression also corrected section 32's coverage claim. `radar.reset_module` completes synchronously inside the request handler, so its running and terminal events share the same millisecond and the terminal event is always coalesced by the 20 Hz jobs stream at any legal subscription rate. The old test guarded the successful-reset capture with `if (capture_event(...))`, so it silently skipped the succeeded event and its pair: section 32's "successful reset" pair never existed. `mwcp_job_test.cpp` now asserts the running event at 20100 ms, exactly one coalesced terminal event via `svc.unsent_events()` increasing by one, and the `JOB_GET` succeeded result with `{"verified":false,"verification":"none"}` and `error:null`; reset success is covered through `JOB_GET`, not through a fabricated event. It also adds the `UNSUPPORTED` admission case and expects every capture instead of skipping it. It prints five `JOBPAIR` lines (running scan, succeeded scan, radio failure, scan timeout, storage failure).

Verification this round (Windows, Node, esphome 2026.9.1 / ESP-IDF 5.5.5, `MWCP_GPP=D:\msys64\clang64\bin\clang++.exe`):

- `mwcp_r_test`, `mwcp_af_test`, `mwcp_service_test`, `mwcp_close_test`, `mwcp_scan_test`, `mwcp_scan_gate_test`, and `mwcp_job_test` with `-std=c++14 -fno-exceptions -fno-rtti -Wall -Wextra -Werror`: all seven printed their `passed` line, exit 0.
- The same seven under `-fsanitize=address,undefined -fno-sanitize-recover=all`: all passed, exit 0.
- `npm run test:unit` with `MWCP_GPP`: 107 pass, 0 fail. The JS test recompiles r/af/close/scan/gate/job, validates event and response schemas, and checks all ten job fields in the `JOBPAIR` lines.
- `python -m unittest tests.unit.test_mwcp_sources -v` from the workspace root: 2 tests OK.
- `esphome compile tests/r60abd1-esp32c3-host.yaml` against the patched tree on `PYTHONPATH`: success. The generated `defines.h` contains `MWCP_WIFI_SCAN_OWNERSHIP`, `USE_WIFI_SCAN_COMPLETION_LISTENERS`, `ESPHOME_WIFI_SCAN_COMPLETION_LISTENERS 1`, and `USE_WIFI_RUNTIME_ROAMING_SUPPRESSION`. RAM 181656/321296, flash 904590/1835008 (section 34 supersedes this build).
- The first host build of this round failed on a real integration bug the host tests cannot see: `mmwave_host.h/.cpp` used unqualified `ScanStart` while the type lives in `mwcp_host`. It was fixed with the namespace qualification and the profile then compiled; this is why the ESPHome build stays in the verification list even though it is slow.
- `clang-format==22.1.8` with the checked-in `.clang-format`: `--dry-run --Werror` is clean for every changed/added file (`components/mmwave_host`, the six test files). Unlike sections 31–32, the changed component files are formatted, not only the new regions.

Final hashes of this R1 build (section 34 supersedes these with the corrected patch and host build): Host OTA SHA-256 `FE47A7B398DA197ED798FF517B3EB2743991AA48E650696382448F0E3C04F572` (905072 bytes). Host factory `710E0B30CB379D27DEFABE554040116BD950C01ECCE6DFF264EEB57B73637276` (970608 bytes). The tree is dirty, so `git_sha` is not a byte-for-byte source snapshot; ESP-IDF embeds build metadata, so a rebuild of identical sources is not byte-identical.

Still not verified: no real Wi-Fi scan, NVS write, or HA entity test was run; G2-01–G2-07 remain `not_run`. Residual risks: (1) the completion listener runs from the WiFi component's main-loop event processing (`wifi_loop_` → `wifi_process_event_`), not the Wi-Fi event task; the adapter copies the list there, and real dual-core timing is unmeasured. (2) A scan accepted but whose completion event is lost keeps the ownership gate closed permanently; later scans fail with `RADAR_UNAVAILABLE` until a completion arrives or the device reboots. This is a deliberate fail-closed choice, not a driver guarantee. (3) The ESP-IDF driver's "idle before the completion event is enqueued" ordering is not publicly provable; the exclusive lifecycle avoids relying on it, but hardware evidence is still absent. (4) Scan `auth` remains `open`/`unknown` because the API is a boolean. (5) The pinned patch must be revalidated on every ESPHome upgrade; the script refuses any other version. Nothing was flashed or committed.

Hardware authorization remains required from the user: specific board model, native USB Serial/JTAG path, R60ABD1 wiring and power, port VID/PID, test authorization, and confirmation that full chip erase remains forbidden. No hardware was opened, flashed, erased, or rebooted.

## 34. R1-A closed with an exclusive gate; offline first-time setup and the patched host build are exercised. G2 still not run

Section 33 overstated the first R1 patch. It released scan ownership after a 60 s stamp window and the completion handler used the *current* generation, so a stale event could be stamped with a newer request's generation. The red/green reproducer (temporary, outside the repository) makes the defect explicit:

```text
legacy stamping with 60 s release:
  t=0     A start -> generation 1
  t=0     A SCAN_DONE queued, not processed
  t=61000 B start -> accepted=1 generation 2 (A released by time)
  legacy: completion of OLD_AP (generation 1) attributed to generation 2
  t=62000 A completion processed; B believes its request is done
legacy result: misattributed=1 (B published A's APs)

exclusive gate:
  t=0     A start -> accepted=1 generation 1
  t=0     A SCAN_DONE queued, not processed
  t=61000 B start -> accepted=0 (pending completion blocks it)
  gate: completion of OLD_AP delivered as generation 1
  t=62000 A completion processed
  t=62000 B retry -> accepted=1 generation 2
  gate: completion of NEW_AP delivered as generation 2
gate result: A delivered as 1, B as 2, backgrounds=0
```

The patch now contains five files (four modified plus `wifi_scan_ownership.h`; +222/−3). The real host build also exposed a second integration defect that the native fakes could not see: the patch declared `notify_scan_completion_listeners_()` and iterated `scan_completion_listeners_`, but never added the public `add_scan_completion_listener()` method or the listener vector. `components/mmwave_host/mmwave_host.cpp` called that method, so the first full compile failed. Both were added to `wifi_component.h`, the patch was regenerated, and all hashes were updated.

Ownership rules after the correction:

- `start_scan_for_component()` has no station-connected precondition. It refuses only when Wi-Fi is disabled, the connection state machine is scanning or connecting, a roaming scan or roam is in progress, an earlier component request is still pending, or the driver refuses the start. A never-provisioned device can therefore scan, list access points, provision, and reach `connected` in one flow.
- `ScanOwnership::begin()` returns false while one request is pending; `take()` consumes it exactly once; `cancel()` is generation-checked so a stale cancellation cannot release a newer request. There is no time-based release.
- The ESPHome completion handler takes the gate and passes the generation that was issued at start time. A background completion with no pending request is dropped and never attributed.
- `ScanOwner::tick()` only releases the 60 s roaming-suppression hold and stops waiting. The dependency keeps the radio; a late completion is ignored by the owner and reopens the gate. A retry before that completion remains refused. If the event is lost, the device stays fail-closed until a completion arrives or it reboots; it never publishes an older scan's records.

The regression coverage now includes a dedicated `mwcp_scan_gate_test.cpp` (begin/take once, second-request refusal, stale cancel, null arguments, generation wrap) and the scan scenario that previously failed: A times out while its completion is queued; the hold bound releases suppression but not the gate; a retry is refused; A's late event copies nothing and reopens the gate; B then returns only `NEW_AP`, never `OLD_AP`. A separate offline scenario scans with no connection, provisions `HOME`, reports `connecting`, persists, and reaches `connected`, without echoing the password. A connected-station scan now also has to preserve `connected` instead of forcing `disconnected`, and a new scan clears the previous scan's `truncated` flag before it starts. The 60 s provisioning deadline is checked across the uint32 wrap, so a deadline that falls just before the wrap fires immediately after it rather than waiting for the next 49-day cycle. The JS test extracts the added header from the patch itself, compiles the gate regression, and runs it in the standard `npm run test:unit` entry point.

`scripts/build_host_profile.py` makes the patched and stock builds repeatable. Patched mode applies the pinned patch, compiles `tests/r60abd1-esp32c3-host.yaml`, asserts `MWCP_WIFI_SCAN_OWNERSHIP`, `USE_WIFI_SCAN_COMPLETION_LISTENERS`, and `USE_WIFI_RUNTIME_ROAMING_SUPPRESSION` in the generated `defines.h`, and prints firmware hashes. Stock mode compiles the same profile and asserts that the ownership defines are absent. CI now has a `patch-build` job that runs patched mode after the hash-only `patch` job; the stock matrix builds the same host profile with `version: "2026.9.1"` pinned in `esphome/build-action@v7`. `apply_esphome_patch.py` now also verifies the added header after applying, not only the four modified files.

Verification actually run this round (Windows, esphome 2026.9.1 / ESP-IDF 5.5.5, `MWCP_GPP=D:\msys64\clang64\bin\clang++.exe`):

- `python scripts/build_host_profile.py --mode patched` on a fresh pristine copy: success. Defines as above; RAM 181656/321296, flash 904648/1835008. `firmware.factory.bin` SHA-256 `75F633C36042D6002093C9B91FDF407FCA677A4B33DA4B9FC2B5998CF25AF531` (970544 bytes); `firmware.ota.bin` / app SHA-256 `F2CE960D11CF80761983F472DE24182C20468E394E08006268EBF52B2FF79EE2` (905008 bytes).
- `python scripts/build_host_profile.py --mode stock` on pristine esphome: success, with the ownership defines absent and `USE_WIFI_RUNTIME_ROAMING_SUPPRESSION` present; RAM 181624/321296, flash 903550/1835008. `firmware.factory.bin` SHA-256 `83A5EB5AFFF811311BD8A251EB1F59521011A653E2369E62CE9C70ABFA293C0D` (969440 bytes); OTA SHA-256 `BDB996F3C97A81DEDA29A89CDC67284E632722FC3D340303529BD39E7A0A1DFD` (903904 bytes).
- `python -m esphome compile tests/r60abd1-esp32c3.yaml` (the old R60 profile) on the patched tree: success, RAM 107704/321296, flash 940514/1835008.
- `npm run test:unit` with `MWCP_GPP`: 107 pass, 0 fail.
- `mwcp_scan_test` and `mwcp_scan_gate_test` with the standard flags and under `-fsanitize=address,undefined -fno-sanitize-recover=all`: passed, exit 0.
- `python -m unittest tests.unit.test_mwcp_sources -v`: 2 tests OK.
- `clang-format==22.1.8 --dry-run --Werror` on the changed/added component and test files: clean.
- `apply_esphome_patch.py --check` on pristine, then apply, then second apply: clean, patched, already patched.

Still not verified: no real Wi-Fi scan, NVS write, HA entity, driver-refusal, reconnect, or roaming test was run; G2-01–G2-07 remain `not_run`. Nothing was flashed or committed.

## 35. WP-2 closes the all-scan ownership hole: every scan entry shares one coordinator. G2 still not run

The §34 patch only made `start_scan_for_component()` reserve the ownership gate. `start_scanning()` (initial connection, captive portal, retry/restart phases) and `check_roaming_()` still called `wifi_scan_start_()` directly, so a background scan could run outside the gate. The failure ordering is: background A starts and leaves its completion event queued; ESPHome's scan state machine times out into cooldown; component B starts under the component-only gate; A's `SCAN_DONE` arrives and is treated as B's completion, so B publishes `OLD_BACKGROUND_AP`. The §34 reproducer only started A through the component path, so it never covered this bypass; the component-only gate did not close R1-A, it moved the bypass to the background entries.

This section supersedes §34 and the earlier §35 patch size, post-image hashes, and build numbers; §34 remains as history.

This round audited every scan entry on 2026.9.1:

- Background entries: `start_scanning()` for the initial connection, captive portal, retry phase/restarting adapter, and the `improv_serial` caller; the roaming scan in `check_roaming_()`.
- Component entry: `start_scan_for_component()`.
- Every entry ends at `WiFiComponent::wifi_scan_start_platform_()`, which is called only from `start_owned_scan()`; the four platform implementations (ESP-IDF, ESP8266, LibreTiny, Pico W) only contain the driver call. A non-host stock build keeps its original `#else` direct call, but there MWCP does not report `wifi.scan`, so no component attribution exists.
- `scripts/check_scan_ownership_sources.py` statically checks those call sites, the single driver choke point, listener registration and defines. On the old tree it reports 23 errors and exits 1.

Ownership and completion classification:

- `ScanOwnership` has only two states, in flight or idle. `begin()` reserves for a component scan and issues a non-zero generation that skips zero on wrap; `begin_background()` reserves for a background scan; any outstanding scan makes the next start return busy. `take()` returns `kNone`/`kBackground`/`kComponent`, and only `kComponent` carries a generation. `cancel()` checks the generation, and a background driver refusal uses `cancel_background()`.
- The header contains no clock, timeout, or state-machine hook. A scan timeout, cooldown, reconnect, or enable/disable transition never releases ownership. If `SCAN_DONE` is lost, the gate stays closed and later starts fail closed until the completion arrives or the device reboots.
- `ScanCoordinator` is the lifecycle shared by connection/retry/roaming and component scans: `start_background()`, `start_component()`, `take_completion()`. `notify_scan_completion_listeners_()` takes the completion first; background, duplicate, or unreserved events never reach a listener and are never rewritten just because a component request exists.
- A component scan still does not require a connected station. The offline first-scan → list APs → provision → `connected` path is preserved; unconnected scans were not forbidden again.

Executable evidence (`protocol/cpp/mwcp_scan_lifecycle_test.cpp`):

- The legacy half models the removed behaviour: background A starts without a reservation, its completion stays queued, component B is admitted, and B then publishes `OLD_BACKGROUND_AP`. This proves the test can catch the defect.
- The current half uses the patch's `ScanCoordinator`/`ScanOwner` directly: A remains `in_flight()` after the timeout; B's start returns busy, the driver is not called and no component reservation is created; A's completion returns `kBackground` and yields no result; only then can B start and return `COMPONENT_B_AP`, never `OLD_BACKGROUND_AP`.
- Recovery paths: a connect-failure retry is busy while A is outstanding and starts after A completes; disable/enable does not clear the gate; a failed roam is refused before the driver and recovers when the roam ends; a component completion is still `kComponent`.
- Scenario 12 in `mwcp_scan_test.cpp` re-checks the same ordering through the real host adapter; the existing component A→B timeout isolation, duplicate completion, driver refusal, empty result, same result, same-count-different result, uint32 wrap, and offline provisioning without password echo all still pass. `mwcp_scan_gate_test.cpp` covers background/component ownership in both directions, duplicate completion, cancellation, and generation wrap.
- The tests do not inject generations into callbacks; the generation is produced only by the coordinator under test, and `take_completion()` decides the classification. The JS test extracts the added header from the patch itself and then compiles these tests.

Verification for this round (Windows, esphome 2026.9.1 / ESP-IDF 5.5.5, `MWCP_GPP=D:\msys64\clang64\bin\clang++.exe`):

- `npm --prefix static run test:unit`: 107 passed, 0 failed, exit 0.
- The three scan tests under `-fsanitize=address,undefined -fno-sanitize-recover=all`: `mwcp scan test passed`, `mwcp scan gate test passed`, `mwcp scan lifecycle test passed`, all exit 0.
- Workspace root `python -m unittest tests.unit.test_mwcp_sources -v`: 2 tests OK, exit 0.
- Patched host profile (`.venv-esphome`, `scripts/build_host_profile.py --mode patched --venv .venv-esphome`): exit 0; defines `MWCP_WIFI_SCAN_OWNERSHIP`, `USE_WIFI_SCAN_COMPLETION_LISTENERS`, `USE_WIFI_RUNTIME_ROAMING_SUPPRESSION`; RAM 181664/321296, flash 904906/1835008; `firmware.factory.bin` SHA-256 `98f841059438afca81482f3e3af453ed6264e817b9664c7b98a131ee3ba2de12` (970800 bytes); `firmware.ota.bin` SHA-256 `7e09cdf1f2f03a5b44420eda76e128c2aee6504d9c68cba541cd405ea74fb010` (905264 bytes).
- Stock host profile (fresh pristine venv, `--mode stock --data-dir .esphome-host-stock`): exit 0; ownership defines absent, `USE_WIFI_RUNTIME_ROAMING_SUPPRESSION` present; RAM 181624/321296, flash 903550/1835008; factory SHA-256 `8a0703223c01a3e081aa851301298f746c07a28ff61dee9416145c950e716e97` (969440 bytes); OTA SHA-256 `ba99c564345476c357f72cce5fba37a1fa22214402620e95d88f3163eb9b2ce5` (903904 bytes).
- The old R60 profile `tests/r60abd1-esp32c3.yaml` on the patched tree: exit 0; RAM 107704/321296, flash 940514/1835008; factory SHA-256 `2a699f8d093ed15baf3cfeb1b84fdf3b5602f417e31bc9c602f05e233c0e4ab7` (1006416 bytes); OTA SHA-256 `488857701b765958a2b75858b501f58d82e07e6a650027ff7ad07934f70940a6` (940880 bytes).
- Patch: 8 files, +487/−10, 31,749 bytes; added `wifi_scan_ownership.h` SHA-256 `6b028c2477444b81e216f97aeafffa6de7e7154666ec3e9d1365ad8d78de9a3d`. `PRISTINE_SHA256`, `PATCHED_SHA256`, and `PATCHED_ADDED_SHA256` all match the files on disk. Pristine `--check` exits 0; applying to a pristine copy exits 0, and a second apply prints `already patched` and exits 0. `check_scan_ownership_sources.py` prints `2 background entries, 1 component entry, 1 driver choke point, 4 platform implementations`, exit 0.
- `clang-format==22.1.8 --dry-run --Werror`: the three test files and the added header are clean. The patched upstream `wifi_component.cpp` still shows the `WiFiScanResult` constructor wrapping that is also present in pristine ESPHome; that upstream region was not reformatted.
- Build environment fix: ESP-IDF `idf.py` prints a warning and exits 0 without running `main()` when `MSYSTEM` is present, so a build reports success with no firmware. `build_host_profile.py` now removes `MSYSTEM` from the child environment; `.gitignore` ignores `.esphome-host/` and `.esphome-host-stock/`. This is a local Windows/Git Bash reproducibility fix and does not change the Linux CI path.
- CI triggers: `web.yml` lists `patches/**` and `protocol/**` in `paths`, so a patch-only change still runs `npm run test:unit`; `ci.yml` is not excluded for patches and runs the patch check, `patch-build`, and the new scan-entry audit.

Boundaries and not verified:

- The above is software proof and compile verification. No real serial port was connected, nothing was flashed, and no real Wi-Fi scan/NVS/HA entity/driver refusal/reconnect/roaming test was run; nothing was committed or pushed; G2-01–G2-07 remain `not_run`.
- The conclusion covers starts that pass through the single choke point: the patch guarantees at most one outstanding scan and classifies its completion by reservation. It does not prove that any external driver/ESP-IDF version can never emit an ownerless event. If a completion is lost, the system stays fail-closed by design instead of guessing.
