# WP-0 / WP-1 phase report

Date: 2026-10-18. Packages: WP-0 and WP-1. Committed or published: no. Protocol frozen: no. Ready for a G1 freeze review: **no.**

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
- `npm run test:unit` (with `MWCP_GPP=g++`, MinGW g++ 13.3.0 in PATH): **94/94 passed**, exit code 0 (was 78, Round 2 +11, Round 3 +5, total 94 suites).
- `node --test test/g0-diag.test.js`: **33/33 passed**, exit code 0.
- `node --test test/g0-hello.test.js`: **2/2 passed**, exit code 0.
- `npm run test:browser`: **2/2 passed**, exit code 0 (Chrome 155.0.8059.84).
- `npm run build`: **passed**, exit code 0 (Vite 8.3.1 production build).
- C++ host contract tests:
  - `mwcp_host_test` (`-std=c++14 -fno-exceptions -fno-rtti -static`): **passed**, exit code 0, 100% protocol vectors pass.
  - `g0_session_test` (`-std=c++14 -static-libgcc -static-libstdc++`): **passed**, exit code 0.
  - `r60_probe_stats_test` (`-std=c++14 -static`): **passed**, exit code 0.
- Python tests: `python -m unittest discover -s tests -p test_releases.py -v`: **20/20 passed**, exit code 0.

### Unexecuted items and limitations
- **Linux WSL / Remote CI**:
  - Local WSL environment encountered networking initialization failure (`CreateInstance/CreateVm/ConfigureNetworking/0x8007054f`) and missing Node binary in the WSL rootfs; Linux Node testing is explicitly marked **blocked / not_run**.
  - Strictly preserved constraints: did not push to remote or trigger remote GitHub Actions; did not substitute Windows results for Linux.
- **Physical hardware G0-01–G0-05**:
  - Maintained as **not_run**. Pending explicit board model, native USB path, wiring, port VID/PID, and test authorization. Strictly no serial ports opened, no flashing, no erase, and no reboot.

### Firmware hashes and source snapshot
Firmware C++ code and YAML profiles were untouched. Firmware hashes from section 20 remain valid:
- Host OTA: `DF0DA7283D78E899B478F6092C125528964FABCED6FB4EF49F7B5ACDD8674026`
- Host factory: `72C87C3DB3AAEF9A9C1968F2994365230D63FF33B3D0F50BE7B52A725CE56DD6`
- Baseline OTA: `7E0B7077A8D8A0594184C7F46924BC0A05969BC583F2777E96E0ADDA6CB4D1B8`
- Baseline factory: `EDD243713F65C6B86DDA7642AF140898A24EABAD804A23E54B17AF14186BB21D`

Workspace `468b4144a0653c5adde66351a2d8f7e94a0763c8`, component `f01ac84fa72dd5b3f479cb1e674572f5cea95c1b`, plus uncommitted changes.
Latest G0 source snapshot hash across 76 files (sorted `sha256 relative_path` manifest hashed with SHA-256):
**`242D8366DFA15E0A45AC0F4467AD24FFE7ED3649201CCB3758C353DB0675BAA2`**.

| Hardware item | Status |
| --- | --- |
| G0-01 | not_run |
| G0-02 | not_run |
| G0-03 | not_run |
| G0-04 | not_run |
| G0-05 | not_run |

Hardware authorization remains required from user: specific board model, native USB Serial/JTAG path, R60ABD1 wiring and power, port VID/PID, test authorization, and confirmation that full chip erase remains forbidden. No hardware was opened, flashed, erased, or rebooted.


