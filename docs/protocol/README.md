# MWCP/1 Millimeter-Wave Device Console Protocol Specification (Self-Contained Component Normative Baseline)

- **Document Status**: **G1 Remediation Candidate, Pending Independent Re-review** (`DD-01`..`DD-15` closed, including user-approved & applied `DD-07` C2 and `DD-08` C2, plus G1-R1..G1-R5 acceptance remediations)
- **Protocol Version**: `major = 1`, `minor = 0` (Wire Magic `MWCP`)
- **Chinese Mirror**: [docs/protocol/README_CN.md](./README_CN.md)
- **Design Differences & Disposition Register**: [docs/protocol/design-differences.md](./design-differences.md) ([Chinese](./design-differences_CN.md))
- **G0 Hardware Verification Evidence Index**: [docs/reviews/web-console/g0-evidence-index.json](../reviews/web-console/g0-evidence-index.json)
- **Phase Acceptance Report**: [docs/reviews/web-console/wp0-wp1-phase-report.md](../reviews/web-console/wp0-wp1-phase-report.md) ([Chinese](../reviews/web-console/wp0-wp1-phase-report_CN.md))
- **Master Planning Source**: Workspace `docs/plans/mmwave-web-console/protocol-v1.md`

---

## 0. Normative Priority & Contract Assets

When wording differences arise between planning documents, phase reports, and executable code, the **authoritative source-of-truth priority order (from highest to lowest)** for MWCP/1 is:

1. **Executable Machine Contract & Golden Vectors (Highest Priority, Byte-for-Byte Dual-Stack Verified)**:
   - Shared Golden Vectors & Fixtures:
     - [`protocol/fixtures/protocol-vectors.json`](../../protocol/fixtures/protocol-vectors.json) (byte-for-byte SHA-256 identical to workspace `docs/plans/mmwave-web-console/protocol-vectors.json`, enforced by workspace `tests/unit/test_mwcp_sources.py`);
     - [`protocol/fixtures/json-cases.json`](../../protocol/fixtures/json-cases.json) and [`protocol/fixtures/double-overflow-threshold.txt`](../../protocol/fixtures/double-overflow-threshold.txt) (shared JS & C++14 JSON boundary cases and binary64 round-to-even overflow threshold);
     - [`docs/protocol/fixtures/coordinate-vectors.json`](./fixtures/coordinate-vectors.json) (shared 3D rotation matrix, 1D `+Y` projection, and ray-casting polygon boundary vectors).
   - Machine-Verifiable JSON Schema: [`docs/protocol/schema/mwcp-v1.schema.json`](./schema/mwcp-v1.schema.json) (covering all `19` commands' `request`/`result`, `5` `event` payloads, the unified `errorEnvelope`, and `x-configSchemas` structured config definitions `polygon.xy.v1`, `range.window.v1`, and `r60.areas.v1`).
   - R60ABD1 Capability & Configuration Descriptor Single Source of Truth: [`docs/protocol/fixtures/r60abd1-capabilities.json`](./fixtures/r60abd1-capabilities.json) (`19` items total: `11` observation features/metrics + `8` host writable config keys; plus `2` supported actions and `4` explicit `unsupported` declarations).
   - Reference Implementations:
     - JavaScript: [`static/src/protocol/limits.js`](../../static/src/protocol/limits.js), [`static/src/protocol/codec.js`](../../static/src/protocol/codec.js), [`static/src/protocol/json.js`](../../static/src/protocol/json.js), [`static/src/protocol/schema.js`](../../static/src/protocol/schema.js), [`static/src/protocol/geometry.js`](../../static/src/protocol/geometry.js), [`static/src/protocol/transform.js`](../../static/src/protocol/transform.js), [`static/src/protocol/contract.js`](../../static/src/protocol/contract.js), [`static/src/protocol/client.js`](../../static/src/protocol/client.js), [`static/src/protocol/simulator.js`](../../static/src/protocol/simulator.js), [`static/src/protocol/flash-handoff.js`](../../static/src/protocol/flash-handoff.js).
     - C++14 (`-fno-exceptions`, `-fno-rtti`): [`protocol/cpp/mwcp_codec.h`](../../protocol/cpp/mwcp_codec.h), [`protocol/cpp/mwcp_codec.cpp`](../../protocol/cpp/mwcp_codec.cpp), [`protocol/cpp/mwcp_json.h`](../../protocol/cpp/mwcp_json.h), [`protocol/cpp/mwcp_json.cpp`](../../protocol/cpp/mwcp_json.cpp), and coordinate transform header [`components/r60abd1/r60abd1_transform.h`](../../components/r60abd1/r60abd1_transform.h).
2. **This Self-Contained Component Normative Specification**: `docs/protocol/README.md` and `docs/protocol/README_CN.md`.
3. **Design Differences & Disposition Register**: `docs/protocol/design-differences.md` (`DD-01`..`DD-15`).
4. **Workspace Planning Archive**: `docs/plans/mmwave-web-console/protocol-v1.md`.

---

## 1. Scope, Layering & Non-Goals

### 1.1 Protocol Layering
1. **Byte Transport Layer**: Browser Web Serial API ↔ ESP32-C3 native `USB Serial/JTAG` (or verified USB-UART bridge) for host console communication; does not alter the radar module's internal UART wire protocol (ESP32-C3 communicates with R60ABD1 independently over `UART1` `GPIO21 TX / GPIO20 RX` at `115200 8N1`).
2. **Framing & Integrity Layer**: `0x00 | COBS(decoded_frame) | 0x00`, combining a 24-byte fixed header, a UTF-8 JSON payload (`<= 4096 B`), and a 4-byte trailing `CRC32C (Castagnoli)`; handles packet fragmentation, sticky packets, boot/crash noise isolation, and half-frame timeout recovery.
3. **Session & Reliability Layer**: `HELLO` handshake, `session_id` / `request_id` / `nonce` / `boot_id` correlation, 4-slot recent response replay cache (`ID_REUSE` / `REQUEST_EXPIRED`), and timeout management.
4. **Application Semantics Layer**: Device identity, paginated capability discovery (`CAPABILITIES_LIST`), live telemetry and log subscriptions (`SUBSCRIBE` / `UNSUBSCRIBE`), atomic host configuration transactions (`CONFIG_READ` / `VALIDATE` / `COMMIT` / `COMMIT_STATUS`), asynchronous jobs (`ACTIONS_LIST` / `ACTION_START` / `JOB_GET`), and USB Wi-Fi provisioning (`WIFI_*`).

### 1.2 Serial Port Parameters & Single-Owner Constraint
- **Browser `port.open()` Default Parameters**: `baudRate: 115200`, 8N1, no hardware flow control, `bufferSize: 16384` (see `DD-12`: existing `esp-web-tools 10.4.0` installer opens with `8192`; the standalone console opens with the normative `16384`). Do not toggle `DTR/RTS` arbitrarily to avoid resetting the board.
- **Single Runtime Owner (`DD-03`, Verified on G0 Hardware)**:
  - Only one runtime consumer may own the USB serial port at a time. An MWCP-enabled host profile (such as [`docs/reviews/web-console/g0/host.yaml`](../reviews/web-console/g0/host.yaml)) must remove stock `improv_serial`, set `CONFIG_ESP_CONSOLE_NONE: y` and `CONFIG_ESP_CONSOLE_USB_SERIAL_JTAG: n`, set `logger` to `hardware_uart: UART0, baud_rate: 0` (disabling interleaved plaintext serial logs), and set `wifi.reboot_timeout: 0s` and `api.reboot_timeout: 0s`.
  - **G0 Hardware Boundary**: On LuatOS ESP32C3-CORE (`USB\VID_303A&PID_1001`) native `USB Serial/JTAG`, if the host stops reading IN URBs while the firmware performs blocking writes to `USB_SERIAL_JTAG`, the 64-byte hardware TX FIFO fills and blocks `loop()`. Therefore, `HostLink` TX writes **MUST** use a 64-byte non-blocking pump (abandoning after `250 ms` of consecutive zero writes and marking a leading `0x00` resync before the next frame).

### 1.3 v1 Non-Goals
- **No BLE**: Does not allocate GATT UUIDs or specify BLE MTU fragmentation, pairing, or advertising.
- **No Raw Vendor UART Passthrough**: Does not expose arbitrary raw vendor UART transmission (`raw_uart_tx`) or `inject_mock_data` in production firmware.
- **Not a 3D Point-Cloud Product**: Scoped to 1D/2D radars; R60ABD1's raw Z coordinate is exposed solely as diagnostic feature `diagnostics.local_z`.

---

## 2. Frame Format, CRC32C & JSON Constraints (Normative)

### 2.1 Wire Encapsulation & COBS Rules
- **Wire Byte Stream Format**: `0x00 | COBS(decoded_frame) | 0x00`.
  - Every transmitted frame begins with `0x00` and ends with `0x00`; consecutive `0x00` bytes (empty frames) are ignored.
  - COBS uses standard `0xFF` block segmentation (not COBS/R).
  - All multi-byte integers are **Little-Endian**.

### 2.2 Decoded Frame Layout (`decoded_frame`)

| `decoded` Byte Offset | Length (Bytes) | Field Name | v1 Normative Value & Semantics |
| :--- | :--- | :--- | :--- |
| `0..3` | 4 | `magic` | Fixed ASCII `"MWCP"` (`4d 57 43 50`) |
| `4` | 1 | `major` | Major protocol version, fixed at `1` |
| `5` | 1 | `minor` | Minor protocol version, fixed at `0` |
| `6` | 1 | `kind` | Frame kind: `1` = `request`, `2` = `response`, `3` = `event` |
| `7` | 1 | `flags` | Frame flags, fixed at `0` in v1 (all other bits reserved and **MUST** be `0`; non-zero rejected as `bad_flags`) |
| `8..11` | 4 (`uint32 LE`) | `session_id` | Session ID: `0` for `HELLO` request; non-zero device-assigned `uint32` for established sessions |
| `12..15` | 4 (`uint32 LE`) | `request_id` | Request/response correlation ID; `0` for `event` frames; `0` is invalid on requests |
| `16..17` | 2 (`uint16 LE`) | `code` | Command or event code (see Section 4 registry) |
| `18..19` | 2 (`uint16 LE`) | `payload_length` | UTF-8 byte length of JSON payload (`0 <= N <= 4096`, byte count not character count) |
| `20..23` | 4 (`uint32 LE`) | `wire_seq` | Per-direction frame counter, wraps modulo $2^{32}$; diagnostic only, not used for RPC deduplication |
| `24 .. 24+N-1` | `N` | `payload` | UTF-8 encoded JSON object bytes (`N <= 4096`) |
| `24+N .. 27+N` | 4 (`uint32 LE`) | `crc32c` | CRC32C checksum covering `decoded[0 .. 24+N-1]` (24-byte header + `payload`) |

### 2.3 Hard Length Limits & CRC32C Algorithm
- **Constants (`static/src/protocol/limits.js` / `protocol/cpp/mwcp_codec.h`)**:
  - `HEADER_LEN = 24`, `CRC_LEN = 4`, minimum valid `decoded` length = **`28` bytes**.
  - `MAX_PAYLOAD = 4096` bytes.
  - `MAX_DECODED = 24 + 4096 + 4 = 4124` bytes.
  - `MAX_COBS = 4124 + floor(4124 / 254) + 1 = 4141` bytes.
  - `MAX_WIRE = MAX_COBS + 2 = 4143` bytes (including leading and trailing `0x00`).
  - `HALF_FRAME_MS = 2000` ms (if a partial non-empty frame receives no new bytes for `2000 ms`, the parser discards the buffer until the next `0x00` delimiter and increments `stats.timeouts`).
- **CRC32C (Castagnoli) Parameters**:
  - Reflected polynomial: `0x82F63B78`, initial value `0xFFFFFFFF`, final XOR `0xFFFFFFFF`.
  - Standard check string ASCII `"123456789"` yields **`0xE3069283`**, serialized on wire in Little-Endian as **`83 92 06 e3`**. IEEE 802.3 CRC32 must not be used.
- **Strict Parse Order & Silent-Drop Boundary (`DD-09` Closed)**:
  1. `0x00` delimiter framing and `MAX_COBS (4141 B)` accumulator cap check (overflow immediately enters `discarding` mode until the next `0x00` and increments `oversize`);
  2. COBS decode (failure increments `bad_cobs`);
  3. `decoded` length bounds (`28 .. 4124 B`) and `magic` (`"MWCP"`), `major (1)` / `minor (0)`, `kind (1..3)`, `flags (0)` checks;
  4. `payload_length <= 4096` and exact `decoded.length === 24 + payload_length + 4` match (no trailing bytes allowed);
  5. `CRC32C` verification (failure increments `bad_crc`);
  6. Strict UTF-8 check (`bad_utf8`) and baseline JSON syntax / depth / key count / duplicate key / safe integer check (`bad_json`).
  - **Normative Rule**: Any failure in steps 1–6 is a **codec-layer corruption**: the receiver increments its diagnostic counter, **does not execute the command, and generates no application response frame** (preventing noise amplification). Only when steps 1–6 succeed (valid envelope + valid JSON object) and the command code is unsupported or schema/business validation fails does the receiver reply with `{"ok":false,"error":{...}}`.

### 2.4 JSON Syntax & Safety Constraints (`DD-10`, `DD-13`, `DD-14`, `DD-15` Closed)
1. **Structural Limits**: Root must be a JSON Object (`{...}`), without UTF-8 BOM; maximum nesting depth `JSON_MAX_DEPTH = 10` (root object is depth 1; raised from 8 so a `CONFIG_READ` envelope can carry `areas.definitions` without exceeding the checker); at most `JSON_MAX_KEYS = 64` keys per object; at most `JSON_MAX_ITEMS = 256` items per array.
2. **No Equivalent Duplicate Keys (`DD-13`)**: Both `static/src/protocol/json.js` and `protocol/cpp/mwcp_json.cpp` compare object keys after unescaping (`\uXXXX`, etc.); literal or escape-equivalent duplicate keys (e.g., `{"a":1,"\u0061":2}`) are rejected as `duplicate_key`.
3. **Safe Integer Bounds & binary64 Overflow Threshold (`DD-14`)**: Every integer-valued JSON number (including plain integers and numbers written with exponents or `.0` fractional parts whose mathematical value is an integer, such as `9007199254740993e0` or `9007199254740993.0`) must lie within `±(2^53 - 1)` (`MAX_SAFE_INT = 9007199254740991`); out-of-range integers are rejected as `unsafe_integer`. Non-integers are checked against the exact IEEE 754 binary64 round-to-even midpoint `2^1024 - 2^970` (`protocol/fixtures/double-overflow-threshold.txt`). 64-bit persistent `revision` values are encoded as decimal digit strings (`^[0-9]+$`, `x-maxUtf8Bytes: 20`).
4. **UTF-8 Byte Length Limits (`DD-10`)**: The schema uses custom keyword `x-maxUtf8Bytes` to enforce UTF-8 byte length (e.g., multibyte CJK SSIDs are measured in UTF-8 bytes `<= 32`, not UTF-16 code units).
5. **Forward-Compatible Field Policy (`DD-15`)**: Request objects strictly forbid unknown properties (returning `UNKNOWN_FIELD`); response and event objects are annotated with `x-open-object: true` in `mwcp-v1.schema.json`, allowing future minor versions to add optional fields without breaking existing clients.

---

## 3. Session Lifecycle, Request Deduplication & Timeouts

### 3.1 `HELLO (0x0001)` Handshake
After opening the port, the client sends `session_id = 0`, `request_id = 1`, `code = 0x0001 (HELLO)`:
```json
{
  "client": { "name": "mmwave-web-console", "version": "0.1.0" },
  "nonce": "0123456789abcdef0123456789abcdef",
  "protocol": { "major": 1, "minor_max": 0 },
  "max_payload": 4096
}
```
The device assigns a non-zero `session_id` in the response header and replies:
```json
{
  "ok": true,
  "result": {
    "nonce": "0123456789abcdef0123456789abcdef",
    "protocol": { "major": 1, "minor": 0 },
    "boot_id": "fedcba9876543210fedcba9876543210",
    "session_ttl_ms": 15000,
    "limits": {
      "max_payload": 4096,
      "rpc_inflight": 1,
      "max_targets": 8,
      "event_budget_bps": 8000
    },
    "identity": {
      "device_id": "local-device-id",
      "configured_model": "r60abd1",
      "dimension": "2D",
      "firmware_version": "0.1.0-alpha.1"
    },
    "cap_revision": "r60-cap-1"
  }
}
```
- Both `nonce` and `boot_id` are 32-character lowercase hex strings (`^[0-9a-f]{32}$`) representing 16 random bytes. The client accepts a `HELLO` response only when both `request_id` and `nonce` match.
- If client `max_payload < 4096`, the device returns `LIMIT_UNSUPPORTED`; if no compatible major version exists, it returns `VERSION_UNSUPPORTED` with `session_id = 0`.
- Retransmitting `HELLO` with the same `nonce` returns the current session; a new `nonce` replaces the previous session and clears old subscriptions and `request_id` replay state without cancelling already-accepted persistent writes.

### 3.2 Strictly Monotonic `request_id` & 4-Slot Response Replay Cache
- Once a session is established, client `request_id` increments strictly starting from `2` (`0` is reserved for `event` frames). At most `1` normal RPC may be in flight (`rpc_inflight = 1`); long-running commands (`ACTION_START`, `WIFI_SCAN`, `WIFI_PROVISION`) release the RPC slot immediately after returning `job_id`.
- **Transport Deduplication (4-Slot Cache)**:
  - The device caches the last `4` completed `(request_id, code, payload_sha256, response)` entries per session.
  - A duplicate request with identical `request_id`, `code`, and `payload` bytes replays the cached response without re-execution.
  - A request with a cached `request_id` but different `code` or `payload` returns `ID_REUSE`.
  - A request with `request_id <= max_seen_request_id` that has been evicted from the 4-slot cache returns `REQUEST_EXPIRED` and is never re-executed.
- **Operation Idempotency (`op_id`)**:
  - Side-effecting commands (`CONFIG_COMMIT`, `ACTION_START`, `WIFI_SCAN`, `WIFI_PROVISION`) carry a UUID `op_id`.
  - `CONFIG_COMMIT` persists the last `4` host commits `(op_id, request_sha256, revision)`. Repeating a known `op_id` with identical digest returns the original result (checked before `base_revision`); repeating an `op_id` with a different digest returns `OP_ID_REUSE`.

### 3.3 Timeouts & Keep-Alive Parameters
- **Client Timeouts**:
  - `HELLO` handshake: `3,000 ms`;
  - Normal read/query RPC: `1,000 ms` (may retry once automatically using the **exact same `request_id` and payload bytes**);
  - `CONFIG_COMMIT`: `2,000 ms` (on timeout, mark outcome unknown and query via `COMMIT_STATUS` + `CONFIG_READ`; never auto-retry with a new `op_id`);
  - `ACTION_START` / `WIFI_PROVISION` acceptance: `1,000 ms` (do not auto-retry with a new ID; query via `JOB_GET` / `WIFI_STATUS`).
- **Session TTL & Heartbeat**: Client sends `PING (0x0002)` every `5,000 ms`; a session expires after `15,000 ms` (`session_ttl_ms`) without a valid client request (device-emitted `event` frames do not renew session TTL).

### 3.4 Unified Response & Error Envelope Format
- **Success Response (`kind = 2`)**: `{"ok": true, "result": { ... }}` (`header.code` echoes request `code`, `header.request_id` echoes `request_id`).
- **Error Response (`kind = 2`)**:
```json
{
  "ok": false,
  "error": {
    "code": "REVISION_CONFLICT",
    "message": "Configuration changed",
    "field": "base_revision",
    "details": { "current_revision": "43" }
  }
}
```

#### Standard Error Codes (`18` Machine Codes, `limits.js` `ERROR`)

| Error Code (`error.code`) | Trigger Condition & Client Handling |
| :--- | :--- |
| `VERSION_UNSUPPORTED` | `HELLO` major version mismatch; halt operations and prompt for compatible version |
| `LIMIT_UNSUPPORTED` | `HELLO` `max_payload < 4096`; refuse session |
| `UNSUPPORTED` | Command, capability, or config key is unsupported by this model; disable/hide in UI |
| `INVALID_ARGUMENT` | Invalid parameter type, format, enum, confirmation string (`confirm`), or polygon geometry |
| `UNKNOWN_FIELD` | Request body or config `changes` contains an undeclared field |
| `OUT_OF_RANGE` | Numeric value falls outside descriptor `[minimum, maximum]` bounds |
| `PAYLOAD_TOO_LARGE` | Frame payload exceeds `4096 B` or record exceeds page budget; never silently truncate or split |
| `ID_REUSE` | Same `request_id` reused with different `code` or payload bytes |
| `OP_ID_REUSE` | Same `op_id` reused with different payload bytes on a write/action |
| `REQUEST_EXPIRED` | Retried `request_id` has aged out of the device's 4-slot replay window |
| `REVISION_CONFLICT` | `base_revision` does not match current `revision`, or `revision` changed mid-pagination |
| `BUSY` | Resource lock (`wifi` / `radar` / `restart`) is held by an active job; returns `details.resource` and `job_id` |
| `RADAR_UNAVAILABLE` | Radar UART link is offline/unavailable, or a Wi-Fi scan cannot start because the radio is disabled, the connection state machine is scanning/connecting, a roaming scan/roam is active, an earlier component-owned scan is still pending, or the driver refused (the USB host link remains online) |
| `RADAR_TIMEOUT` | Radar module timed out waiting for a response, or an accepted Wi-Fi scan reported no completion within 15 s |
| `VERIFY_FAILED` | Readback verification after parameter write failed |
| `STORAGE_FAILED` | NVS storage slot corruption or write failure |
| `RATE_LIMITED` | Exceeded RPC rate limit (10 RPC/s) or persistent write token bucket (`details.retry_after_ms`) |
| `INTERNAL_ERROR` | Unexpected internal error; treat outcome as unknown and re-read authoritative state |

---

## 4. Complete Command & Event Registry (19 Commands + 5 Events)

Requests and responses share the same `code` in the frame header (`kind = 1` for request, `kind = 2` for response); events use `kind = 3` and `request_id = 0`. Level `M` denotes mandatory for v1; `C` denotes conditional on declared capabilities.

### 4.1 Request/Response Commands (`0x0001` .. `0x0053`)

| `code` (Hex / Dec) | Command Name | Level | Request Payload (`request`) | Success Result (`result`) |
| :--- | :--- | :--- | :--- | :--- |
| `0x0001` (`1`) | `HELLO` | M | `{client:{name,version}, nonce, protocol:{major,minor_max}, max_payload}` | `{nonce, protocol:{major,minor}, boot_id, session_ttl_ms, limits, identity, cap_revision}` |
| `0x0002` (`2`) | `PING` | M | `{}` | `{uptime_ms}` |
| `0x0003` (`3`) | `SESSION_CLOSE` | M | `{}` | `{closed: true}` (closes session after draining response; does not reboot device) |
| `0x0010` (`16`) | `DEVICE_INFO` | M | `{}` | `{device_id, boot_id, configured_model, dimension, firmware_version, git_sha, release_channel, build_profile, host_protocol, radar_identity}` |
| `0x0011` (`17`) | `CAPABILITIES_LIST` | M | `{cursor: null \| string}` | `{revision, items: CapabilityItem[], next_cursor}` |
| `0x0012` (`18`) | `STATUS_GET` | M | `{}` | `{uptime_ms, radar_link, last_radar_frame_ms, config_revision, config_storage, active_jobs, counters}` |
| `0x0020` (`32`) | `CONFIG_READ` | M | `{cursor: null \| string}` | `{revision, items: [{key, value}, ...], next_cursor}` |
| `0x0021` (`33`) | `CONFIG_VALIDATE` | M | `{base_revision, changes}` | `{valid: true, base_revision, restart_required: false}` (side-effect free) |
| `0x0022` (`34`) | `CONFIG_COMMIT` | M | `{base_revision, op_id, changes}` | `{op_id, revision, persisted: true, restart_required: false}` |
| `0x0023` (`35`) | `COMMIT_STATUS` | M | `{op_id}` | `{found: boolean, revision: string \| null, current_revision: string}` |
| `0x0030` (`48`) | `SUBSCRIBE` | M | `{streams: [{id, max_rate_hz}], event_budget_bps}` | `{streams: [{id, max_rate_hz}], event_budget_bps}` |
| `0x0031` (`49`) | `UNSUBSCRIBE` | M | `{streams: [id, ...]}` | `{removed: [id, ...]}` |
| `0x0040` (`64`) | `ACTIONS_LIST` | M | `{cursor: null \| string}` | `{revision, items: ActionDescriptor[], next_cursor}` |
| `0x0041` (`65`) | `ACTION_START` | C | `{action_id, op_id, params, confirm: string \| null}` | `{job_id}` |
| `0x0042` (`66`) | `JOB_GET` | M | `{job_id}` or `{op_id}` (mutually exclusive) | `Job` object (returns `state: "unknown"` summary if queried by unknown `op_id`) |
| `0x0050` (`80`) | `WIFI_STATUS` | M | `{}` | `{state, ssid, ip, rssi_dbm, last_error}` (**never returns password**) |
| `0x0051` (`81`) | `WIFI_SCAN` | M | `{op_id}` | `{job_id}` |
| `0x0052` (`82`) | `WIFI_PROVISION` | M | `{op_id, ssid, auth, password}` | `{job_id}` |
| `0x0053` (`83`) | `WIFI_SCAN_RESULTS` | M | `{job_id, cursor: null \| string}` | `{items: [{ssid, rssi_dbm, auth, hidden}], next_cursor, truncated}` |

### 4.2 Asynchronous Events (`0x8001` .. `0x8005`)

| `code` (Hex / Dec) | Event Name | Subscription Stream `id` | Event Payload (`event`) |
| :--- | :--- | :--- | :--- |
| `0x8001` (`32769`) | `TELEMETRY` | `telemetry` | `{source_seq, sent_ms, origin, presence, targets_quality, targets_ms, targets, metrics}` |
| `0x8002` (`32770`) | `STATUS_CHANGED` | `status` | Identical schema to `STATUS_GET` `result` |
| `0x8003` (`32771`) | `CONFIG_CHANGED` | `config` | `{revision, changed_keys, origin: "host"\|"ha"\|"web"\|"boot", op_id: string\|null}` |
| `0x8004` (`32772`) | `JOB_CHANGED` | `jobs` | `Job` object: `{job_id, op_id, action_id, state, stage, progress, started_ms, finished_ms, result, error}` |
| `0x8005` (`32773`) | `LOG` | `logs` | `{sample_ms, level: "error"\|"warn"\|"info"\|"debug", source, message, dropped_before}` |

---

## 5. Core Domain Contract Rules

### 5.1 Identity, Capability Discovery & Pagination Consistency
- **Pagination Rules (`CAPABILITIES_LIST`, `CONFIG_READ`, `ACTIONS_LIST`, `WIFI_SCAN_RESULTS`)**:
  - Start with `cursor: null`; `next_cursor: null` indicates the final page; every page envelope is `<= 4096 B` without truncating individual items.
  - If the underlying `revision` changes between pages, subsequent page requests return `REVISION_CONFLICT` and the client restarts from page 1.
- **R60ABD1 Baseline Capabilities, Config & Actions Contract (Single Source of Truth: [`docs/protocol/fixtures/r60abd1-capabilities.json`](./fixtures/r60abd1-capabilities.json))**:
  - **Observation Features & Metrics (11 items)**: `presence`, `distance.cm`, `position.xy` (`max_targets: 1`, `target_id_stable: false`, `expected_interval_ms: 2000`, `stale_after_ms: 6000`, per `DD-07` C2), `diagnostics.local_z`, `speed.cm_s` (`supported: false`, see `DD-06`), `motion.state`, `body.movement`, `breath_rate` (`medical: false`), `heart_rate` (`medical: false`), `sleep.state`, `areas.occupancy`.
  - **R60ABD1 Host Writable Config Descriptors (Exact 8 items, matching `r60abd1-capabilities.json` and `simulator.js` `r60` model)**:
    1. `install.x_cm` (`number`, `-2000 .. 2000`, step `1`, `cm`, `domain: "host"`, `restart_required: false`)
    2. `install.y_cm` (`number`, `-2000 .. 2000`, step `1`, `cm`, `domain: "host"`, `restart_required: false`)
    3. `install.z_cm` (`number`, `50 .. 600`, step `1`, `cm`, `domain: "host"`, `restart_required: false`; per user-approved `DD-08` Option C2, synchronized across `r60abd1-capabilities.json`, `simulator.js`, and `tests/common/r60abd1.yaml` `num_radar_z` to `50..600 cm`)
    4. `install.yaw_deg` (`number`, `-180 .. 180`, step `0.1`, `deg`, `domain: "host"`, `restart_required: false`)
    5. `install.pitch_deg` (`number`, `-90 .. 90`, step `0.5`, `deg`, `domain: "host"`, `restart_required: false`)
    6. `install.roll_deg` (`number`, `-90 .. 90`, step `0.5`, `deg`, `domain: "host"`, `restart_required: false`)
    7. `geometry.boundary_cm` (`array | null`, `unit: "cm"`, `schema_id: "polygon.xy.v1"`, `min_items: 3`, `max_items: 64`, `domain: "host"`, `restart_required: false`; `null` disables boundary filtering, otherwise a `3..64` vertex `[x, y]` 2D polygon within `[-2000, 2000] cm`, strictly rejecting out-of-range coordinates, duplicate adjacent vertices, an explicit duplicate closing vertex, zero area, collinear overlap, or self-intersecting edges; see `DD-04`/`DD-05`)
    8. `areas.definitions` (`array`, `unit: "cm"`, `schema_id: "r60.areas.v1"`, `min_items: 0`, `max_items: 3`, `domain: "host"`, `restart_required: false`; elements are area slot objects `{slot, enabled, name, points_cm}`: `slot` is an integer `0..2` with no duplicate `slot` within the array, `enabled` is a boolean, `name` is a string of `<= 32` UTF-8 bytes, and unknown properties are forbidden; when `enabled: true`, `points_cm` must be a valid non-self-intersecting, non-zero-area `3..12` vertex `[x, y]` 2D polygon within `[-2000, 2000] cm`; when `enabled: false`, `points_cm` may only be the empty array `[]` or a valid `3..12` vertex polygon)
  - **1D-Only Config Key (NOT part of R60ABD1)**:
    - `range.window_cm` (`schema_id: "range.window.v1"`, `{min: 0..600, max: 0..600}` with `min <= max` and no additional properties) applies only to 1D range-gated models (the `range1d` profile in `simulator.js`). In `r60abd1-capabilities.json`, `range.window_cm` is explicitly listed under `unsupported` (`["range.window_cm", "inject_mock_data", "raw_uart_tx", "speed.cm_s"]`), and submitting `range.window_cm` to an R60 instance is rejected (`UNSUPPORTED`).
  - **R60ABD1 Supported Actions (Exact 2 items)**:
    - `device.restart` (`confirm: true`, `verification: "none"`, `resource: "restart"`, `deadline_ms: 8000`)
    - `radar.reset_module` (`confirm: true`, `verification: "none"`, `resource: "radar"`, `deadline_ms: 2000`)

### 5.2 Telemetry Quality Semantics, Coordinate Transform & G0 Hardware Cadence Evidence
- **Quality Enum (`quality`)**: `valid | unknown | stale | invalid | unsupported`.
  - Whenever `quality` is `unknown`, `unsupported`, or `invalid`, the corresponding `value` **MUST** be `null` (enforced by `contract.js` `telemetryIssue`).
  - 1D targets use `range_cm`; 2D targets use `local_cm: [x, y]` and `room_cm: [x, y]`. Mixing 1D and 2D representations within `targets` is rejected (`mixed_representation`).
  - R60ABD1 does not report target speed; `speed_cm_s` is always `null` (`DD-06`).
- **Room Coordinate Transform & Boundary Predicate (`DD-11` Closed)**:
  - Uses the existing firmware and `mmwave-card` rotation convention: `Rz(yaw) * Rx(pitch) * Ry(roll)`, `yaw = 0` pointing to `+Y`, positive `yaw` clockwise, `room_z = radar_z - world_z`.
  - Ray-casting edge-point inclusion matches the existing firmware and card (`(50, 0)` and `(0, 0)` on square `[0..100, 0..100]` are `inside`, `(150, 10)` is `outside`), locked by [`static/test/protocol-coordinates.test.js`](../../static/test/protocol-coordinates.test.js), [`protocol/cpp/mwcp_host_test.cpp`](../../protocol/cpp/mwcp_host_test.cpp) (`test_transform`), and workspace `tests/unit/test_mwcp_sources.py`.
- **G0 Hardware Reporting Cadence & `DD-07` C2 Policy**:
  - Across the 2-hour standalone hardware endurance run (`7,198` samples), `R60ABD1` total valid control frames (`radar_frames`) averaged **`4.84 Hz` (`4..8 frames/s`)**, whereas `0x80/0x05` 2D coordinate frames (`radar_targets`) arrived strictly at **`0.50 Hz` (`1` frame every `2,000 ms`)**, and firmware `publish_position_()` applies a `1,000 ms` throttle. Per user-approved `DD-07` Option C2, `position.xy` is set to the hardware-measured `expected_interval_ms: 2000, stale_after_ms: 6000`, while unbucketed non-coordinate fields remain `null` with `quality` maintained by the device control-word state machine.

### 5.3 Configuration Transactions, Dual-Slot Persistence & Max R60 Config Proof (`C-13`)
- **Atomic Validation & Commit**:
  - `CONFIG_VALIDATE (0x0021)` and `CONFIG_COMMIT (0x0022)` enforce identical structural and semantic rules across Schema (`mwcp-v1.schema.json` `x-configSchemas`), contract (`contract.js` `validateConfigChanges`), and simulator/server: checking `base_revision`, field whitelist, numeric bounds/steps, `range.window.v1` (`min <= max`), `polygon.xy.v1` (`3..64` vertices in `[-2000, 2000] cm`, non-degenerate/non-self-intersecting), and `r60.areas.v1` (`0..3` slots, unique integer `slot 0..2`, no unknown properties, valid `3..12` vertex polygons). `CONFIG_VALIDATE` is strictly side-effect free.
  - `CONFIG_COMMIT (0x0022)` checks `op_id` idempotency and `base_revision`, atomically updates the snapshot, increments the decimal string `revision`, and emits `CONFIG_CHANGED (0x8003)`.
  - **Maximum Valid R60 Configuration Capacity Proof (`C-13`)**: A `CONFIG_COMMIT` request carrying all 8 R60 host configuration keys (including `install.z_cm = 600`, a geometrically valid 64-vertex convex polygon `geometry.boundary_cm`, and 3 enabled 12-vertex convex polygon `areas.definitions` slots) encodes well below `MAX_PAYLOAD = 4096 B`; the exact `4096 B` payload boundary is accepted and `4097 B` is rejected with `payload_too_large`.

### 5.4 Asynchronous Jobs & USB Wi-Fi Provisioning Security
- **Action Confirmation & Resource Locks (`A-01`..`A-03`, Hardened in G1-R1 / G1-R2)**:
  - In `mwcp-v1.schema.json`, `ACTION_START (0x0041)` restricts `confirm` to `["string", "null"]` (booleans `true` / `false` are rejected at schema validation). Actions with `confirm: true` require `confirm === action_id` (e.g., `"device.restart"` or `"radar.reset_module"`), otherwise returning `INVALID_ARGUMENT`.
  - **Task Admission Control, Reservation Invariant & Completed Record Protection (G1-R2-A Final)**:
    1. **Capacity Reservation Invariant**: Device task storage is strictly bounded. At all times, the system must satisfy:
       $$\text{protected\_completed\_jobs} + \text{active\_jobs\_reservation} \le 8$$
       Because every admitted active job will eventually transition into a completed history entry upon finishing, the device MUST reserve a future completed history slot before admitting any active task, preventing scenarios where a task runs only to later violate the 5-minute minimum retention rule or exceed bounded RAM.
    2. **Side-Effect-Free Admission Check Sequence**:
       - **Step 1: Idempotency Verification**: If the incoming `op_id` already exists in active or completed jobs, identical payload digests return the existing `job_id` (consuming no new slot and not re-executing, even when capacity is full); altered payload returns `OP_ID_REUSE` immediately prior to any side-effects.
       - **Step 2: Resource Mutex Check**: If the target resource (`wifi`, `radar`, `restart`) is currently locked by an active task, returns `BUSY` (with `details.resource` and active `job_id`).
       - **Step 3: Capacity Admission Check**: First reclaim completed entries with `elapsed >= 300,000 ms`; if afterwards `(completedJobs.length + activeJobs.size) >= 8` (i.e. every remaining completed entry still has `elapsed < 300,000 ms` and is protected), the new task MUST be immediately rejected with `ERROR.BUSY` (`details: { reason: "capacity", retry_after_ms: 1000 }`). Upon rejection, **NO** task is created, no lock is acquired, no events are emitted, and Wi-Fi state/SSID remain completely untouched.
       - **Step 4: State Transition & Admission**: Only after passing all preceding checks does the device mutate state, instantiate the task, acquire the resource lock, and return the new `job_id`.
    3. **Completed History FIFO by Completion Order & 5-Minute (300,000 ms) Minimum Retention Window**:
       - Completed tasks record `finished_ms` and enter the completed queue ordered by completion timestamp.
       - Let `elapsed = now_ms - finished_ms` (monotonic clock within the same boot).
       - **Strict Protection Within 5 Minutes**: Entries with `elapsed < 300,000 ms` are strictly protected and NEVER evicted to admit new tasks.
       - **Natural Expiration Only**: An entry may be pruned only when `elapsed >= 300,000 ms` (i.e. reaches or exceeds `300,000 ms`; reboots clear the table separately), thereby freeing capacity for new task admission. Exact boundary: `299,999 ms` is still protected; `300,000 ms` and `300,001 ms` are both reclaimable.
       - **Active Jobs Never Evicted**: Active jobs (`queued`/`running`) never participate in completed queue eviction, and their locks remain active until completion or reboot.
    4. **`unknown` State Semantics**: Jobs that reached or exceeded the 5-minute window (`elapsed >= 300,000 ms`) and were naturally reclaimed, or were lost across a reboot, return `state: "unknown"`. **Clients MUST understand that `unknown` indicates the device retains no record of this job, and NEVER guarantees that the job was never accepted or executed**; automatic blind retries of stateful actions returning `unknown` are strictly forbidden.
  - **Device Reboot Lifecycle & Bounded Volatile Memory (G1-R2-B)**:
    1. Device reboots mirror real hardware behavior: volatile RAM containing active jobs, completed history, sessions, subscriptions, and transient resource locks is atomically cleared, ensuring device task memory is strictly bounded (never exceeding 8 total active plus completed records under any condition, consistent with `protected_completed + active_reservation <= 8`); consecutive reboots generate a unique random 32-character hexadecimal `boot_id` each time.
    2. Queries for `job_id` or `op_id` from a previous boot return `state: "unknown"`, preventing stale state leaks across reboots.
    3. Reboots do not alter NVS persistent state: configuration snapshots, `revision`, and the last 4 atomic `CONFIG_COMMIT` records strictly survive reboots.
    4. Ordinary session disconnects or timeouts are not reboots and must not cancel or discard accepted tasks.
  - **Unverified Actions & Reboot Semantics (G1-R2)**: Non-rebooting actions with `verification: "none"` (such as `radar.reset_module`) complete with `Job.result = {"verified": false, "verification": "none"}` (never `verified: true`), and the UI must display "sent, unverified" without claiming hardware verification succeeded; `device.restart` remains `queued` / `running` prior to reboot (never marked `succeeded` before reboot); after reboot, `boot_id` changes, old `job_id` queries return `state: "unknown"`, and the client confirms reboot via the new `boot_id`.
- **Wi-Fi Scan & Zero Password Echo (`W-01`..`W-04`)**:
  - `WIFI_SCAN (0x0051)` starts an owned scan job; `WIFI_SCAN_RESULTS (0x0053)` paginates AP entries sorted by `rssi_dbm` descending, capping at 64 entries with `truncated: true` if exceeded.
  - The firmware build pins an ESPHome patch that serializes every scan start. Connection/retry scans reserve the radio through a background token; component scans reserve it with a generation. No scan can start while another is in flight, and every completion consumes exactly one reservation. Only component completions carry a generation; background completions are never attributed. On a build without that API, `WIFI_SCAN` fails immediately with `UNSUPPORTED`; the device never guesses which scan finished.
  - Start outcomes are immediate: the radio is disabled, any connection/retry/roaming scan is already in flight, a component scan is pending, or the driver refuses → `RADAR_UNAVAILABLE` (`Radar is unavailable`), retryable once the radio is idle. A station connection is not required: a never-provisioned device can scan, list access points, and provision. An accepted scan that the driver later reports as failed, or whose announced records cannot be retrieved, fails with `VERIFY_FAILED`. An accepted scan with no completion within 15 s fails with `RADAR_TIMEOUT`; a late completion cannot complete a retry, and ownership reopens only when that completion event is processed. If the completion event is lost, ownership stays closed and later scans return `RADAR_UNAVAILABLE` until a completion arrives or the device reboots; there is no time-based release.
  - While a scan job is pending, `WIFI_SCAN_RESULTS` returns `BUSY`. After a failed or timed-out scan the same page returns `items: []` (never a previous scan's records); after a refused start no job was accepted, so `WIFI_SCAN_RESULTS` for that `job_id` returns `INVALID_ARGUMENT`.
  - `WIFI_PROVISION (0x0052)` validates `auth` (`open` requires an empty password; `wpa2_psk` requires an `8..63` UTF-8 byte passphrase or 64-char hex PSK).
  - Scan item `auth` is `open`, `wpa2_psk`, or `unknown`. `unknown` means the radio did not report a suite; it must not be copied into `WIFI_PROVISION`.
  - **Invariant**: **No response (`WIFI_STATUS`, `JOB_GET`), event (`JOB_CHANGED`, `LOG`), or error detail may ever echo `password`**.

---

## 6. Verification Matrix & Directly Executable Local Commands

All commands below match the repository's real directory layout and can be copied and executed directly:

### 6.1 Frontend & Protocol JS Unit Tests, CDP Browser Tests & Production Build
Working directory: `submodules/mmwave-component/static`

```bash
# Linux / WSL2 / macOS (bash)
cd submodules/mmwave-component/static
MWCP_GPP=g++ npm run test:unit
npm run test:browser
npm run build
```

```powershell
# Windows (PowerShell)
cd submodules/mmwave-component/static
$env:MWCP_GPP = "D:\Build\mingw64\bin\g++.exe"
npm run test:unit
npm run test:browser
npm run build
```
- Notes: `npm run test:unit` runs all unit test suites (`static/test/*.test.js`, covering R1..R5 regression suites with 100% pass rate); `npm run test:browser` uses the repository's zero-dependency Chrome DevTools Protocol (CDP) runner (`static/test/browser-harness.js` + `static/test/browser/protocol-browser.test.js`) against headless Chrome/Chromium (2 tests).

### 6.2 C++14 Host Tests (Including `P-14` 100,000-Mutation Fuzz Campaign with ASan/UBSan)
Working directory: `submodules/mmwave-component`

```bash
# Linux / WSL2 (bash) — with AddressSanitizer + UndefinedBehaviorSanitizer
cd submodules/mmwave-component

g++ -std=c++14 -O1 -g -fsanitize=address,undefined -fno-omit-frame-pointer -Wall -Wextra -Werror \
  -I protocol/cpp -I components/r60abd1 \
  protocol/cpp/mwcp_codec.cpp protocol/cpp/mwcp_json.cpp protocol/cpp/mwcp_host_test.cpp \
  -o /tmp/mwcp_host_test_asan && /tmp/mwcp_host_test_asan protocol/fixtures/protocol-vectors.json

g++ -std=c++14 -Wall -Wextra -Werror -static \
  -I docs/reviews/web-console/g0/components/mmwave_host -I protocol/cpp -I components/r60abd1 \
  protocol/cpp/g0_session_test.cpp protocol/cpp/mwcp_codec.cpp protocol/cpp/mwcp_json.cpp \
  -o /tmp/g0_session_test && /tmp/g0_session_test

g++ -std=c++14 -Wall -Wextra -Werror -static \
  -I components/r60abd1 -I docs/reviews/web-console/g0/components/mmwave_host \
  protocol/cpp/r60_probe_stats_test.cpp \
  -o /tmp/r60_probe_stats_test && /tmp/r60_probe_stats_test
```

```powershell
# Windows (PowerShell)
cd submodules/mmwave-component

D:\Build\mingw64\bin\g++.exe -std=c++14 -fno-exceptions -fno-rtti -static -Wall -Wextra -Werror `
  -I protocol/cpp -I components/r60abd1 `
  protocol/cpp/mwcp_codec.cpp protocol/cpp/mwcp_json.cpp protocol/cpp/mwcp_host_test.cpp `
  -o "$env:TEMP\mwcp_host_test.exe"
& "$env:TEMP\mwcp_host_test.exe" protocol/fixtures/protocol-vectors.json

D:\Build\mingw64\bin\g++.exe -std=c++14 -static -Wall -Wextra -Werror `
  -I docs/reviews/web-console/g0/components/mmwave_host -I protocol/cpp -I components/r60abd1 `
  protocol/cpp/g0_session_test.cpp protocol/cpp/mwcp_codec.cpp protocol/cpp/mwcp_json.cpp `
  -o "$env:TEMP\g0_session_test.exe"
& "$env:TEMP\g0_session_test.exe"

D:\Build\mingw64\bin\g++.exe -std=c++14 -static -Wall -Wextra -Werror `
  -I components/r60abd1 -I docs/reviews/web-console/g0/components/mmwave_host `
  protocol/cpp/r60_probe_stats_test.cpp `
  -o "$env:TEMP\r60_probe_stats_test.exe"
& "$env:TEMP\r60_probe_stats_test.exe"
```

### 6.3 Python Release Validation & Golden Vector / Card Transform Source Alignment Tests

```bash
# 1. Run from component root (submodules/mmwave-component): 20/20 passed
cd submodules/mmwave-component
python -m unittest discover -s tests -p test_releases.py -v

# 2. Run from workspace root (mmwave-workspace): 2/2 passed (verifies golden vector dual-source identity & mmwave-card transform parity)
cd ../..
python -m unittest tests/unit/test_mwcp_sources.py -v
```
