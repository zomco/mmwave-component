"""MWCP/1 serial client for G2 hardware verification.

Byte-level framing (COBS + CRC32C + 24-byte header) is implemented here in
Python and proven byte-exact against the shared golden vectors
(protocol/fixtures/protocol-vectors.json) at client construction time, so the
client cannot silently diverge from the frozen contract. Payload-level schema
validation happens in a separate Node pass (tools/g2/validate_frames.mjs) that
imports the real JS validators from static/src/protocol.

Safety model (G2 execution handoff, section C):
- The port must be named explicitly (--port COM9). No scanning, no opening of
  any other port.
- Default mode is read-only. Write/provisioning commands are rejected unless
  the caller passes allow_write / allow_provision.
- One reader, one writer. DTR/RTS are parked once right after open and never
  toggled afterwards.
- Sessions are kept alive with PING; request_id is strictly monotonic from 2;
  at most 1 RPC in flight; >=110 ms spacing (10 RPC/s device limit).
- Side-effecting requests are never auto-retried.
- Redaction is applied at capture time: provisioning TX records only metadata
  ("sensitive fields omitted"); scan SSIDs are aliased (controlled test AP ->
  stable alias, others -> AP-<hash8>); BSSIDs and passwords are never written.
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any

def _finite_stamp(value, *, nonneg: bool = False) -> bool:
    """A JSON-safe clock sample. Bool is not a number. Wall stamps may be negative."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    if value != value or value in (float("inf"), float("-inf")):
        return False
    return value >= 0 if nonneg else True


HEADER_LEN = 24
CRC_LEN = 4
MAX_PAYLOAD = 4096
MAX_DECODED = HEADER_LEN + MAX_PAYLOAD + CRC_LEN
MAX_COBS = MAX_DECODED + MAX_DECODED // 254 + 1
MAX_WIRE = MAX_COBS + 2
HALF_FRAME_MS = 2000

KIND_REQUEST = 1
KIND_RESPONSE = 2
KIND_EVENT = 3

CODE = {
    "HELLO": 0x0001,
    "PING": 0x0002,
    "SESSION_CLOSE": 0x0003,
    "DEVICE_INFO": 0x0010,
    "CAPABILITIES_LIST": 0x0011,
    "STATUS_GET": 0x0012,
    "CONFIG_READ": 0x0020,
    "CONFIG_VALIDATE": 0x0021,
    "CONFIG_COMMIT": 0x0022,
    "COMMIT_STATUS": 0x0023,
    "SUBSCRIBE": 0x0030,
    "UNSUBSCRIBE": 0x0031,
    "ACTIONS_LIST": 0x0040,
    "ACTION_START": 0x0041,
    "JOB_GET": 0x0042,
    "WIFI_STATUS": 0x0050,
    "WIFI_SCAN": 0x0051,
    "WIFI_PROVISION": 0x0052,
    "WIFI_SCAN_RESULTS": 0x0053,
    "TELEMETRY": 0x8001,
    "STATUS_CHANGED": 0x8002,
    "CONFIG_CHANGED": 0x8003,
    "JOB_CHANGED": 0x8004,
    "LOG": 0x8005,
}

# Commands that change device state beyond this session's subscriptions.
WRITE_COMMANDS = {
    CODE["CONFIG_COMMIT"],
    CODE["ACTION_START"],
    CODE["WIFI_SCAN"],
    CODE["WIFI_PROVISION"],
}
PROVISION_COMMANDS = {CODE["WIFI_PROVISION"]}


class ProtocolError(RuntimeError):
    pass


def crc32c(data: bytes) -> int:
    crc = 0xFFFFFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = (crc >> 1) ^ (0x82F63B78 if crc & 1 else 0)
    return crc ^ 0xFFFFFFFF


def cobs_encode(data: bytes) -> bytes:
    out = bytearray()
    block = 1
    block_start = 0
    for i, byte in enumerate(data):
        if byte == 0:
            out.append(block)
            out.extend(data[block_start:i])
            block = 1
            block_start = i + 1
        else:
            block += 1
            if block == 255:
                out.append(255)
                out.extend(data[block_start : i + 1])
                block = 1
                block_start = i + 1
    out.append(block)
    out.extend(data[block_start:])
    return bytes(out)


def cobs_decode(data: bytes) -> bytes | None:
    if not data:
        return None
    out = bytearray()
    i = 0
    while i < len(data):
        code = data[i]
        if code == 0 or i + code > len(data):
            return None
        i += 1
        out.extend(data[i : i + code - 1])
        i += code - 1
        if i < len(data) and code != 255:
            out.append(0)
    return bytes(out)


def encode_frame(kind: int, session_id: int, request_id: int, code: int, payload: bytes, wire_seq: int) -> bytes:
    if len(payload) > MAX_PAYLOAD:
        raise ProtocolError("payload too large")
    header = (
        b"MWCP"
        + bytes([1, 0, kind, 0])
        + session_id.to_bytes(4, "little")
        + request_id.to_bytes(4, "little")
        + code.to_bytes(2, "little")
        + len(payload).to_bytes(2, "little")
        + (wire_seq & 0xFFFFFFFF).to_bytes(4, "little")
    )
    decoded = header + payload
    decoded += crc32c(decoded).to_bytes(4, "little")
    return b"\x00" + cobs_encode(decoded) + b"\x00"


def decode_decoded(decoded: bytes) -> dict[str, Any] | None:
    if not (HEADER_LEN + CRC_LEN <= len(decoded) <= MAX_DECODED):
        return None
    if decoded[0:4] != b"MWCP":
        return None
    major, minor, kind, flags = decoded[4], decoded[5], decoded[6], decoded[7]
    if major != 1 or minor != 0 or kind not in (1, 2, 3) or flags != 0:
        return None
    session_id = int.from_bytes(decoded[8:12], "little")
    request_id = int.from_bytes(decoded[12:16], "little")
    code = int.from_bytes(decoded[16:18], "little")
    length = int.from_bytes(decoded[18:20], "little")
    wire_seq = int.from_bytes(decoded[20:24], "little")
    if HEADER_LEN + length + CRC_LEN != len(decoded):
        return None
    body = decoded[HEADER_LEN : HEADER_LEN + length]
    if crc32c(decoded[:-4]) != int.from_bytes(decoded[-4:], "little"):
        return None
    return {
        "kind": kind,
        "session_id": session_id,
        "request_id": request_id,
        "code": code,
        "wire_seq": wire_seq,
        "payload": body,
    }


def selftest(vectors_path: Path) -> list[str]:
    """Prove this module's codec against the shared golden vectors."""
    vectors = json.loads(vectors_path.read_text(encoding="utf-8"))
    assert crc32c(b"123456789") == 0xE3069283, "crc32c check string failed"
    checked = []
    for case in vectors["frames"]:
        payload = case["payload_text"].encode("utf-8")
        assert len(payload) == case["payload_utf8_length"]
        wire = encode_frame(
            case["kind"], case["session_id"], case["request_id"], case["code"],
            payload, case["wire_seq"],
        )
        assert wire.hex() == case["wire_hex"], f"wire mismatch for {case['id']}"
        # strip the two 0x00 delimiters and COBS-decode to compare decoded bytes
        decoded = cobs_decode(wire[1:-1])
        assert decoded is not None and decoded.hex() == case["decoded_hex"], f"decoded mismatch for {case['id']}"
        parsed = decode_decoded(decoded)
        assert parsed is not None and parsed["code"] == case["code"]
        checked.append(case["id"])
    for case in vectors["cobs_cases"]:
        decoded_hex, encoded_hex = case["decoded_hex"], case["encoded_hex"]
        if decoded_hex:
            assert cobs_encode(bytes.fromhex(decoded_hex)).hex() == encoded_hex, f"cobs encode {case['id']}"
            assert cobs_decode(bytes.fromhex(encoded_hex)) == bytes.fromhex(decoded_hex), f"cobs decode {case['id']}"
        else:
            assert cobs_decode(bytes.fromhex(encoded_hex)) == b"", f"cobs decode {case['id']}"
    return checked


class Redactor:
    """Capture-time redaction. Defined before any evidence is collected."""

    def __init__(self, controlled_ssids: dict[str, str] | None = None, secrets: list[str] | None = None):
        # controlled ssid -> stable alias (e.g. "TEST_AP")
        self.controlled = dict(controlled_ssids or {})
        # literal secret values that must never reach any evidence file
        self.secrets = [s for s in (secrets or []) if s]

    def alias_ssid(self, ssid: str | None) -> str | None:
        if ssid is None:
            return None
        if ssid in self.controlled:
            return self.controlled[ssid]
        return "AP-" + hashlib.sha256(ssid.encode("utf-8")).hexdigest()[:8]

    def scan_items(self, items: list[dict]) -> list[dict]:
        out = []
        for item in items:
            out.append({
                "ssid": self.alias_ssid(item.get("ssid")) if item.get("ssid") is not None else None,
                "rssi_dbm": item.get("rssi_dbm"),
                "auth": item.get("auth"),
                "hidden": item.get("hidden"),
            })
        return out

    def all_secrets(self) -> list[str]:
        return self.secrets + [k for k in self.controlled if k]

    def frame_payload(self, code: int, dir_tx: bool, payload: dict) -> tuple[dict, list[str]]:
        """Return (safe_payload, list_of_redacted_fields).

        Responses carry their body under "result"; redaction must descend into
        it. Earlier only top-level keys were aliased, so WIFI_STATUS.result.ssid
        and WIFI_SCAN_RESULTS.result.items[].ssid leaked raw SSIDs (harness
        defect H-3, 2026-10-24 provisioning run).
        """
        redacted: list[str] = []
        safe = json.loads(json.dumps(payload))  # deep copy
        result = safe.get("result")
        if code == CODE["WIFI_PROVISION"] and dir_tx:
            for field in ("password",):
                if field in safe:
                    safe[field] = "<omitted>"
                    redacted.append(field)
            if "ssid" in safe and safe["ssid"] is not None:
                safe["ssid"] = self.alias_ssid(str(safe["ssid"]))
                redacted.append("ssid->alias")
        elif code == CODE["WIFI_SCAN_RESULTS"] and not dir_tx and isinstance(result, dict):
            if isinstance(result.get("items"), list):
                result["items"] = self.scan_items(result["items"])
                redacted.append("ssid->alias")
        elif code == CODE["WIFI_STATUS"] and not dir_tx and isinstance(result, dict):
            if result.get("ssid"):
                result["ssid"] = self.alias_ssid(str(result["ssid"]))
                redacted.append("ssid->alias")
        elif code == CODE["WIFI_PROVISION"] and not dir_tx:
            # responses only carry job_id; nothing to redact
            pass
        return safe, redacted


class EvidenceWriter:
    """JSONL evidence with capture-time redaction and secret scan on close."""

    def __init__(self, path: Path, redactor: Redactor, append: bool = False):
        self.path = Path(path)
        self.redactor = redactor
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not append and self.path.exists():
            raise FileExistsError(f"Evidence file already exists: {self.path}")
        mode = "a" if append else "x"
        self._fh = self.path.open(mode, encoding="utf-8", newline="\n")
        self.t0 = time.time()
        # H19-02: attempt waits are measured on this clock, not time.time()-t0.
        self.t0_mono = time.monotonic()

    def frame(self, dir_tx: bool, meta: dict, payload: dict | None, redacted: list[str],
              arrival: dict | None = None) -> None:
        safe_payload, extra = (self.redactor.frame_payload(meta.get("code", 0), dir_tx, payload or {})) if payload is not None else ({}, [])
        rec = {
            "t": round(time.time() - self.t0, 3),
            # Record time. Not the receive time: a slow writer must not move it.
            "t_mono": round(time.monotonic() - self.t0_mono, 3),
            "wall": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "dir": "tx" if dir_tx else "rx",
            **{k: v for k, v in meta.items() if v is not None},
            "payload": safe_payload,
            "redacted": redacted + extra,
        }
        # R21-02: frozen at decode, already relative to this file. Absent means
        # the capture has no receive time; do not fill these from `t`.
        if isinstance(arrival, dict):
            if _finite_stamp(arrival.get("mono"), nonneg=True):
                rec["rx_mono"] = round(float(arrival["mono"]), 3)
            if _finite_stamp(arrival.get("wall")):
                rec["rx_wall"] = round(float(arrival["wall"]), 3)
        self._fh.write(json.dumps(rec, ensure_ascii=False, separators=(",", ":")) + "\n")
        self._fh.flush()

    def note(self, event: dict) -> None:
        rec = {"t": round(time.time() - self.t0, 3), "wall": time.strftime("%Y-%m-%dT%H:%M:%S"), "dir": "note", **event}
        self._fh.write(json.dumps(rec, ensure_ascii=False, separators=(",", ":")) + "\n")
        self._fh.flush()

    def close(self) -> dict:
        self._fh.close()
        # secret scan: never echo matched text, only location
        text = self.path.read_text(encoding="utf-8", errors="replace")
        hits = []
        for secret in self.redactor.all_secrets():
            if secret and secret in text:
                # report the line number only
                for i, line in enumerate(text.splitlines(), 1):
                    if secret in line:
                        hits.append({"line": i, "secret_len": len(secret)})
                        break
        return {"file": str(self.path), "sha256": hashlib.sha256(self.path.read_bytes()).hexdigest(), "secret_hits": hits}


class Stats:
    def __init__(self) -> None:
        self.rx_frames = 0
        self.rx_events = 0
        self.rx_responses = 0
        self.bad_crc = 0
        self.bad_cobs = 0
        self.oversize = 0
        self.timeouts = 0
        self.tx_frames = 0
        self.tx_dropped_resync = 0
        self.plaintext_noise = 0

    def as_dict(self) -> dict:
        return dict(self.__dict__)


class Client:
    """One serial session against one explicitly named port."""

    def __init__(self, port: str, evidence: EvidenceWriter, allow_write: bool = False, allow_provision: bool = False,
                 ser=None):
        self.evidence = evidence
        self.allow_write = allow_write
        self.allow_provision = allow_provision
        self.stats = Stats()
        if ser is None:
            import serial  # pyserial, from the esphome venv

            self.ser = serial.Serial(port=port, baudrate=115200, bytesize=8, parity="N", stopbits=1,
                                      timeout=0.05, write_timeout=5.0, dsrdtr=False, rtscts=False)
        else:
            # Tests pass an already-built port. Production still opens `port`.
            self.ser = ser
        # Control lines are left exactly as pyserial leaves them on open
        # (DTR/RTS asserted). Toggling them after open — including "parking"
        # them at False, which passes through DTR=0/RTS=1 — reliably stops the
        # device from answering subsequent RPCs on this bench (V1/V3 vs V2 in
        # the G2 bisect). Protocol 1.2: never toggle DTR/RTS arbitrarily.
        self.session_id = 0
        self._req = 0
        self._tx_seq = 0
        self._rx_buf = bytearray()
        self._last_partial = 0.0
        self._last_rpc_t = 0.0
        self._hello_gen = 0
        self.boot_id: str | None = None
        self.device_id: str | None = None
        self.last_rtt_ms: float | None = None

    # -- low level ---------------------------------------------------------

    def close(self) -> None:
        try:
            self.ser.close()
        except Exception:
            pass

    def _write_wire(self, wire: bytes, meta: dict, payload: dict | None, expect_invalid: bool = False,
                    chunk: int = 64, gap_ms: float = 3.0) -> None:
        """Write one wire frame, paced in fixed-size pieces by default: the
        device ingests USB RX at ~64 B per main-loop pass into a 1024 B ring,
        so a sub-second burst of a large frame can overflow the ring before
        the loop drains it (bench-verified: large single-write frames were
        the first to wedge the link). 64 B x 3 ms matches the device TX pump
        pacing and keeps every frame inside one ring capacity."""
        if chunk > 0:
            for i in range(0, len(wire), chunk):
                self.ser.write(wire[i:i + chunk])
                time.sleep(gap_ms / 1000.0)
        else:
            self.ser.write(wire)
        self.stats.tx_frames += 1
        if expect_invalid:
            meta = {**meta, "expect_invalid": True}
        self.evidence.frame(True, meta, payload, [])

    def _pump_rx(self, duration_ms: float, want_request_ids: set[int] | None = None) -> list[dict]:
        """Read bytes for up to duration_ms; return decoded frames (responses+events).

        Returns as soon as a response whose request_id is in want_request_ids
        has been decoded. Without that early exit every "RTT" was simply the
        configured timeout, and a 40 s pump outlived the 15 s session TTL, so
        follow-up requests were protocol-correctly ignored (G2 harness defect
        H-1, found while auditing the 2026-10-24 soak results).
        Bytes are drained via in_waiting so an already-buffered frame is
        decoded promptly instead of only at the deadline.
        """
        import time as _t
        frames: list[dict] = []
        deadline = _t.monotonic() + duration_ms / 1000.0
        while _t.monotonic() < deadline:
            now = _t.monotonic()
            waiting = self.ser.in_waiting
            if waiting:
                self._feed(self.ser.read(waiting), frames)
                if want_request_ids is not None and any(
                    f["kind"] == KIND_RESPONSE and f["request_id"] in want_request_ids for f in frames
                ):
                    return frames
                continue
            if self._rx_buf and (now - self._last_partial) * 1000 > HALF_FRAME_MS:
                # half-frame timeout: drop the partial, count it, resync on next 0x00
                self.stats.timeouts += 1
                self._rx_buf.clear()
            _t.sleep(0.002)
        return frames

    def _feed(self, data: bytes, frames: list[dict]) -> None:
        import time as _t
        now = _t.monotonic()
        now_wall = _t.time()
        for byte in data:
            if byte == 0:
                if self._rx_buf:
                    block = bytes(self._rx_buf)
                    self._rx_buf.clear()
                    decoded = cobs_decode(block)
                    if decoded is None:
                        self.stats.bad_cobs += 1
                        continue
                    if len(decoded) > MAX_DECODED:
                        self.stats.oversize += 1
                        continue
                    parsed = decode_decoded(decoded)
                    if parsed is None:
                        # magic/version/flags/length/crc failure counted at codec layer
                        self.stats.bad_crc += 1
                        self.evidence.note({"event": "rx_undecodable", "len": len(decoded),
                                            "head_hex": decoded[:32].hex()})
                        continue
                    self.stats.rx_frames += 1
                    if parsed["kind"] == KIND_EVENT:
                        self.stats.rx_events += 1
                    else:
                        self.stats.rx_responses += 1
                    # One decode instant for this read. Later scheduling does
                    # not get to call this the arrival time.
                    parsed["arrival"] = now
                    parsed["arrival_wall"] = now_wall
                    frames.append(parsed)
                # empty frames ignored
            else:
                if len(self._rx_buf) >= MAX_COBS + 2:
                    self.stats.oversize += 1
                    self._rx_buf.clear()
                    continue
                if not self._rx_buf:
                    self._last_partial = now
                self._rx_buf.append(byte)

    def _record_rx(self, frame: dict) -> dict | None:
        try:
            payload = json.loads(frame["payload"].decode("utf-8"))
        except Exception:
            payload = {"__raw__": frame["payload"].hex()[:64], "__note__": "undecodable payload"}
        arrival = self._relative_arrival(frame)
        frame["rx_mono"] = arrival.get("mono")
        frame["rx_wall"] = arrival.get("wall")
        self.evidence.frame(False, {
            "kind": frame["kind"], "code": frame["code"],
            "session_id": frame["session_id"], "request_id": frame["request_id"],
            "wire_seq": frame["wire_seq"],
            "boot_id": self.boot_id,
        }, payload, [], arrival or None)
        return payload

    def _relative_arrival(self, frame: dict) -> dict:
        """Receive stamps relative to evidence open. Missing stays missing."""
        out = {}
        mono0 = getattr(self.evidence, "t0_mono", None)
        wall0 = getattr(self.evidence, "t0", None)
        raw_mono = frame.get("arrival")
        raw_wall = frame.get("arrival_wall")
        if mono0 is not None and _finite_stamp(raw_mono):
            rel = raw_mono - mono0
            if _finite_stamp(rel, nonneg=True):
                out["mono"] = round(rel, 3)
        if wall0 is not None and _finite_stamp(raw_wall):
            out["wall"] = round(raw_wall - wall0, 3)
        return out

    # -- session / RPC -----------------------------------------------------

    def _space_rpc(self) -> None:
        import time as _t
        # Bench reality (G2 re-diagnosis 2026-10-24): sustained sub-second
        # request cadence (~0.3 s) wedges the USB data path after ~35 frames
        # on this host/device combination, across builds; at >=1 s cadence the
        # console is fully stable (RPC + telemetry events for hours). Keep
        # requests at least 0.4 s apart - still well under the protocol's
        # 10 RPC/s limit and its 5 s heartbeat floor.
        wait = 0.400 - (_t.monotonic() - self._last_rpc_t)
        if wait > 0:
            _t.sleep(wait)
        self._last_rpc_t = _t.monotonic()

    def _clock_pair(self) -> tuple[float, float]:
        """(monotonic seconds since evidence open, wall seconds since evidence open).

        Attempt waits use the monotonic value. The wall value is only the
        timeline coordinate shared with TX/RX `t`, sampled at the same instant.
        """
        mono0 = getattr(self.evidence, "t0_mono", None)
        if mono0 is None:
            mono0 = time.monotonic()
            try:
                self.evidence.t0_mono = mono0
            except Exception:
                mono0 = None
        wall0 = getattr(self.evidence, "t0", None)
        mono = time.monotonic()
        wall = time.time()
        mono_s = 0.0 if mono0 is None else mono - mono0
        wall_s = 0.0 if wall0 is None else wall - wall0
        return mono_s, wall_s

    def _note_attempt(self, rid: int, code: int, attempt: int, window_ms: int,
                      outcome: str, pump_start, pump_end, *, error: str | None = None,
                      rtt_ms: float | None = None, tx_recorded: bool = True,
                      attempts_total: int | None = None,
                      selected: dict | None = None) -> None:
        """Attempt note. v2 is the pump interval. v3 also names the response
        the client actually accepted, with the receive time frozen at decode.

        `t` on the frame line is when the writer flushed it. `selected_rx_*`
        is not that time. A matched note without a frozen receive time is
        incomplete; the collector does not invent one.
        """
        if pump_start is None or pump_end is None:
            started = ended = actual = t_start = t_end = None
        else:
            ms, ts = pump_start
            me, te = pump_end
            started = round(ms, 3)
            ended = round(me, 3)
            actual = round(me - ms, 3)
            t_start = round(ts, 3)
            t_end = round(te, 3)
        note = {
            "event": "rpc_attempt",
            "note_version": 2,
            "clock": "monotonic",
            "request_id": rid,
            "code": code,
            "session_id": self.session_id,
            "boot_id": self.boot_id,
            "attempt": attempt,
            "configured_window_s": round(window_ms / 1000.0, 3),
            "wait_started_s": started,
            "wait_ended_s": ended,
            "wait_actual_s": actual,
            "timeline_t_start": t_start,
            "timeline_t_end": t_end,
            "outcome": outcome,
            "tx_recorded": tx_recorded,
        }
        if outcome == "matched":
            # v3 even when the selection is empty, so a missing arrival cannot
            # fall through to the v2 "unique frame near the record time" rule.
            sel = selected or {}
            note["note_version"] = 3
            note["selected_wire_seq"] = sel.get("wire_seq")
            note["selected_rx_mono"] = sel.get("rx_mono")
            note["selected_rx_wall"] = sel.get("rx_wall")
        if rtt_ms is not None:
            note["rtt_ms"] = rtt_ms
        if error is not None:
            note["error"] = error[:120]
        if attempts_total is not None:
            note["attempts_total"] = attempts_total
        self.evidence.note(note)

    @staticmethod
    def _is_unwind(ex: BaseException) -> bool:
        """Cancel/interrupt types Exception does not catch. Never swallowed."""
        import asyncio
        return isinstance(ex, (KeyboardInterrupt, SystemExit, asyncio.CancelledError))

    def _request(self, name: str, payload: dict | None = None, timeout_ms: int = 40000,
                 retry_same: bool = True, expect_invalid: bool = False, chunk: int = 0) -> tuple[dict, dict]:
        """Send one request, wait for its response. Retries (at most once) only
        when retry_same is True and only with identical request_id and bytes.
        Default timeout is 40000 ms (not the protocol's 1000 ms client policy)
        so a genuinely slow device is not classified as lost; the pump returns
        as soon as the matching response arrives, so this ceiling does not
        inflate measured RTTs. Side-effecting requests are never retried by
        the caller passing retry_same=False."""
        code = CODE[name]
        if code in WRITE_COMMANDS and not self.allow_write:
            raise ProtocolError(f"{name} refused: write commands need allow_write")
        if code in PROVISION_COMMANDS and not self.allow_provision:
            raise ProtocolError(f"{name} refused: provisioning needs allow_provision")
        assert self.session_id != 0, "HELLO first"
        self._req += 1
        rid = self._req + 1  # request_id starts at 2 after HELLO consumes 1
        body = json.dumps(payload or {}, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        wire = encode_frame(KIND_REQUEST, self.session_id, rid, code, body, self._tx_seq)
        self._tx_seq = (self._tx_seq + 1) & 0xFFFFFFFF
        meta = {"kind": KIND_REQUEST, "code": code, "session_id": self.session_id, "request_id": rid, "wire_seq": (self._tx_seq - 1) & 0xFFFFFFFF, "boot_id": self.boot_id}
        # Bench reality (G2 re-diagnosis 2026-10-24): the device sometimes
        # leaves a delivered request unprocessed until a later identical
        # write arrives, then executes within ~30 ms and the replay cache
        # answers the retry. Short same-id retries bound the damage for
        # idempotent commands; side-effecting commands keep the protocol
        # minimum of one exact-bytes retry after the full timeout.
        if code in WRITE_COMMANDS or not retry_same:
            attempts, window_ms = 2, timeout_ms
        else:
            attempts, window_ms = 8, min(timeout_ms, 2500)
        for attempt in range(attempts):
            self._space_rpc()
            sent_at = time.monotonic()
            try:
                self._write_wire(wire, meta, payload or {}, expect_invalid=expect_invalid, chunk=chunk)
            except BaseException as ex:
                # The TX frame is written only after the serial write returns.
                # A failure or cancel before that stays in the denominator and
                # must not be recorded as a successful send. No retry.
                if self._is_unwind(ex):
                    self._note_attempt(
                        rid, code, attempt, window_ms, "cancelled", None, None,
                        error=type(ex).__name__, tx_recorded=False)
                    raise
                self._note_attempt(
                    rid, code, attempt, window_ms, "write_error", None, None,
                    error=repr(ex), tx_recorded=False)
                raise
            pump_start = self._clock_pair()
            try:
                frames = self._pump_rx(window_ms, {rid})
            except BaseException as ex:
                pump_end = self._clock_pair()
                # CancelledError and KeyboardInterrupt are not Exception.
                # Record the real pump interval, then re-raise. Do not retry.
                if self._is_unwind(ex) or type(ex).__name__ in ("CancelledError", "Cancelled"):
                    self._note_attempt(
                        rid, code, attempt, window_ms, "cancelled", pump_start, pump_end,
                        error=type(ex).__name__, tx_recorded=True)
                    raise
                self._note_attempt(
                    rid, code, attempt, window_ms, "read_error", pump_start, pump_end,
                    error=repr(ex), tx_recorded=True)
                raise
            pump_end = self._clock_pair()
            matched = None
            for frame in frames:
                payload_json = self._record_rx(frame)
                if matched is None and frame["kind"] == KIND_RESPONSE and frame["request_id"] == rid:
                    matched = (payload_json, frame)
            last = attempt + 1 >= attempts
            if matched is not None:
                payload_json, frame = matched
                self.last_rtt_ms = round((frame.get("arrival", time.monotonic()) - sent_at) * 1000, 1)
                self._note_attempt(
                    rid, code, attempt, window_ms, "matched", pump_start, pump_end,
                    rtt_ms=self.last_rtt_ms, tx_recorded=True,
                    selected={
                        "wire_seq": frame.get("wire_seq"),
                        "rx_mono": frame.get("rx_mono"),
                        "rx_wall": frame.get("rx_wall"),
                    })
                return payload_json, self._stats_meta(frame)
            outcome = "no_response" if last else "window_timeout"
            self._note_attempt(
                rid, code, attempt, window_ms, outcome, pump_start, pump_end,
                tx_recorded=True, attempts_total=attempts if last else None)
            if not last:
                self.evidence.note({"event": "retry_same_request_id", "request_id": rid, "code": code,
                                    "session_id": self.session_id,
                                    "boot_id": self.boot_id,
                                    "attempt": attempt})
        raise TimeoutError(f"{name} (request_id={rid}) no response after {attempts}x{window_ms}ms")

    def _stats_meta(self, frame: dict) -> dict:
        return {"wire_seq": frame["wire_seq"]}

    def _note_hello(self, nonce: str, generation: int, outcome: str, **fields) -> None:
        """Record what this hello() call actually did.

        This is the host-test capture contract, not an MWCP frame change.
        Collector writes exactly one `hello_call` note (hello_note_version 1)
        at the exit of this call. The call key is (nonce, generation). It is
        not an rpc_attempt and has no pump window. A legal same-nonce resend
        inside this call does not write a second note.

        Required: hello_note_version 1, nonce (non-empty str), generation
        (int >= 0), outcome in {matched, protocol_error, timeout, cancelled,
        read_error, write_error}. `phase` is "write" or "read" when this
        collector knows which side failed; older notes may omit it.
        `matched` also requires selected_wire_seq, selected_kind,
        selected_code, selected_request_id, and selected_session_id.
        `protocol_error` requires rejected_wire_seq. `error`, when present,
        is the exception type name, not the payload.

        Rebuild validates the whole note group before it binds a completion.
        An unknown version, a duplicate generation, or a note that cannot be
        tied to a request is not a success and is not treated as a file that
        simply has no note. A raw file with no hello_call note at all stays
        on the historical frame rule. That rule is not a fallback for a
        broken note.
        """
        note = {
            "event": "hello_call",
            "hello_note_version": 1,
            "nonce": nonce,
            "generation": generation,
            "outcome": outcome,
        }
        for key, value in fields.items():
            if value is not None:
                note[key] = value
        self.evidence.note(note)

    def hello(self, timeout_ms: int = 3000, client_name: str = "g2-runner") -> dict:
        import secrets as _secrets
        generation = getattr(self, "_hello_gen", 0)
        self._hello_gen = generation + 1
        nonce = _secrets.token_hex(16)
        body = {
            "client": {"name": client_name, "version": "0.1.0"},
            "nonce": nonce,
            "protocol": {"major": 1, "minor_max": 0},
            "max_payload": 4096,
        }
        payload = json.dumps(body, separators=(",", ":")).encode("utf-8")
        wire = encode_frame(KIND_REQUEST, 0, 1, CODE["HELLO"], payload, self._tx_seq)
        self._tx_seq = (self._tx_seq + 1) & 0xFFFFFFFF
        noted = False

        def finish(outcome: str, **fields) -> None:
            nonlocal noted
            if noted:
                return
            noted = True
            self._note_hello(nonce, generation, outcome, **fields)

        try:
            self._write_wire(wire, {"kind": KIND_REQUEST, "code": CODE["HELLO"], "session_id": 0, "request_id": 1, "wire_seq": (self._tx_seq - 1) & 0xFFFFFFFF}, body)
        except BaseException as ex:
            # The TX line is written only after every chunk returns. A failure
            # here did not send. Do not retry the handshake.
            if self._is_unwind(ex):
                finish("cancelled", error=type(ex).__name__, phase="write")
            else:
                finish("write_error", error=type(ex).__name__, phase="write")
            raise
        deadline = time.monotonic() + timeout_ms / 1000.0
        try:
            while time.monotonic() < deadline:
                try:
                    batch = self._pump_rx(200, {1})
                except BaseException as ex:
                    if self._is_unwind(ex):
                        finish("cancelled", error=type(ex).__name__, phase="read")
                    else:
                        finish("read_error", error=type(ex).__name__, phase="read")
                    raise
                # Record the whole batch first so a rejected call still keeps
                # the later frames. The first decisive HELLO response ends it.
                decoded = [(frame, self._record_rx(frame)) for frame in batch]
                for frame, payload_json in decoded:
                    if (frame.get("kind") != KIND_RESPONSE or frame.get("request_id") != 1
                            or frame.get("code") != CODE["HELLO"]):
                        continue
                    result = payload_json.get("result") if isinstance(payload_json, dict) else None
                    echoed = result.get("nonce") if isinstance(result, dict) else None
                    boot = result.get("boot_id") if isinstance(result, dict) else None
                    accepted = (isinstance(payload_json, dict) and payload_json.get("ok") is True
                                and frame.get("session_id") not in (None, 0)
                                and echoed == nonce and isinstance(boot, str) and bool(boot))
                    if not accepted:
                        finish("protocol_error", rejected_wire_seq=frame.get("wire_seq"),
                               error="ProtocolError", phase="read")
                        raise ProtocolError("HELLO rejected")
                    self.session_id = frame["session_id"]
                    self.boot_id = boot
                    identity = result.get("identity") if isinstance(result, dict) else None
                    device = identity.get("device_id") if isinstance(identity, dict) else None
                    self.device_id = device or result.get("device_id")
                    self._req = 0  # a fresh session restarts request_ids at 2
                    finish("matched", selected_wire_seq=frame.get("wire_seq"),
                           selected_kind=frame.get("kind"), selected_code=frame.get("code"),
                           selected_request_id=frame.get("request_id"),
                           selected_session_id=frame.get("session_id"), phase="read")
                    return result
            finish("timeout", phase="read")
            raise TimeoutError("HELLO no response")
        except BaseException:
            if not noted:
                finish("read_error", error="unnoted", phase="read")
            raise

    def ping(self) -> dict:
        """PING; tolerates RATE_LIMITED by waiting out the window once."""
        for attempt in range(2):
            resp, _ = self._request("PING", {})
            if resp.get("ok"):
                return resp["result"]
            if resp.get("error", {}).get("code") == "RATE_LIMITED" and attempt == 0:
                time.sleep(1.2)
                continue
            raise ProtocolError(f"PING failed: {resp}")
        raise ProtocolError("PING rate-limited twice")

    def soft_call(self, name: str, payload: dict | None = None, timeout_ms: int = 15000) -> dict:
        """Call a side-effect-free command, retrying once with a NEW request_id
        after RATE_LIMITED (bursts unblocked after a main-loop stall can hit
        the 10 RPC/s window even with client-side pacing). Never used for
        side-effecting commands."""
        if CODE[name] in WRITE_COMMANDS:
            raise ProtocolError("soft_call is for idempotent commands only")
        resp = self.call(name, payload, timeout_ms=timeout_ms)
        if resp.get("error", {}).get("code") == "RATE_LIMITED":
            time.sleep(1.2)
            resp = self.call(name, payload, timeout_ms=timeout_ms)
        return resp

    def call(self, name: str, payload: dict | None = None, timeout_ms: int = 40000, **kw) -> dict:
        resp, _ = self._request(name, payload, timeout_ms=timeout_ms, **kw)
        return resp

    def raw_request(self, rid: int, name: str, payload: dict | None = None, timeout_ms: int = 1000,
                    expect_invalid: bool = False) -> dict | None:
        """Send one request with an explicit request_id (no auto-increment,
        no retry). Returns the response payload dict, or None on silence."""
        code = CODE[name]
        if code in WRITE_COMMANDS and not self.allow_write:
            raise ProtocolError(f"{name} refused: write commands need allow_write")
        if code in PROVISION_COMMANDS and not self.allow_provision:
            raise ProtocolError(f"{name} refused: provisioning needs allow_provision")
        body = json.dumps(payload or {}, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        wire = encode_frame(KIND_REQUEST, self.session_id, rid, code, body, self._tx_seq)
        self._tx_seq = (self._tx_seq + 1) & 0xFFFFFFFF
        meta = {"kind": KIND_REQUEST, "code": code, "session_id": self.session_id, "request_id": rid,
                "wire_seq": (self._tx_seq - 1) & 0xFFFFFFFF}
        self._space_rpc()
        sent_at = time.monotonic()
        self._write_wire(wire, meta, payload or {}, expect_invalid=expect_invalid)
        frames = self._pump_rx(timeout_ms, {rid})
        matched = None
        for frame in frames:
            payload_json = self._record_rx(frame)
            if matched is None and frame["kind"] == KIND_RESPONSE and frame["request_id"] == rid:
                matched = (payload_json, frame)
        if matched is not None:
            payload_json, frame = matched
            self.last_rtt_ms = round((frame.get("arrival", time.monotonic()) - sent_at) * 1000, 1)
            return payload_json
        return None

    def raw_request_strict(self, rid: int, name: str, payload: dict | None = None,
                           timeout_ms: int = 1000, accept=None) -> dict | None:
        """One send, no retry. Accept only a RESPONSE with this session, code, and request_id.

        raw_request stays request_id-only for existing diagnostics. A frame that
        misses any of the four fields is not this call's response and does not
        end the wait. accept, when set, is a payload check after that match;
        a body it rejects also leaves the rest of this wait open.
        """
        code = CODE[name]
        self._strict_sent = False
        if code in WRITE_COMMANDS and not self.allow_write:
            raise ProtocolError(f"{name} refused: write commands need allow_write")
        if code in PROVISION_COMMANDS and not self.allow_provision:
            raise ProtocolError(f"{name} refused: provisioning needs allow_provision")
        body = json.dumps(payload or {}, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        wire = encode_frame(KIND_REQUEST, self.session_id, rid, code, body, self._tx_seq)
        self._tx_seq = (self._tx_seq + 1) & 0xFFFFFFFF
        meta = {"kind": KIND_REQUEST, "code": code, "session_id": self.session_id, "request_id": rid,
                "wire_seq": (self._tx_seq - 1) & 0xFFFFFFFF}
        self._space_rpc()
        sent_at = time.monotonic()
        self._write_wire(wire, meta, payload or {})
        self._strict_sent = True
        deadline = time.monotonic() + timeout_ms / 1000.0
        while True:
            remaining_ms = (deadline - time.monotonic()) * 1000.0
            if remaining_ms <= 0:
                return None
            frames = self._pump_rx(remaining_ms, {rid})
            matched = None
            saw_other = False
            for frame in frames:
                payload_json = self._record_rx(frame)
                same_call = (
                    frame["kind"] == KIND_RESPONSE
                    and frame["session_id"] == self.session_id
                    and frame["code"] == code
                    and frame["request_id"] == rid
                )
                if same_call and (accept is None or accept(payload_json)):
                    matched = (payload_json, frame)
                    break
                if frame["kind"] == KIND_RESPONSE and frame["request_id"] == rid:
                    saw_other = True
            if matched is not None:
                payload_json, frame = matched
                self.last_rtt_ms = round((frame.get("arrival", time.monotonic()) - sent_at) * 1000, 1)
                return payload_json
            if not saw_other:
                return None

    def write_raw(self, data: bytes, note: str) -> None:
        """Write raw non-protocol bytes (noise tests); recorded as a note only."""
        self.ser.write(data)
        self.evidence.note({"event": "raw_tx", "note": note, "hex_head": data[:40].hex(), "len": len(data)})

    def pause_reads(self) -> None:
        """Simulate a host that stops consuming IN data (no reads at all)."""
        self._reads_paused = True

    def resume_reads(self) -> None:
        self._reads_paused = False
        # Drain whatever the OS buffered while we were not reading.
        try:
            self.ser.reset_input_buffer()
        except Exception:
            pass

    def drain_events(self, duration_ms: float, keepalive_s: float = 8.0) -> list[dict]:
        """Collect events for duration_ms in short slices. Slices keep evidence
        timestamps close to arrival, and a PING every keepalive_s keeps the
        control session inside its 15 s TTL; without it a drain longer than
        the TTL made the following request protocol-correctly silent
        (harness defect H-2, 2026-10-24 observe run)."""
        import time as _t
        deadline = _t.monotonic() + duration_ms / 1000.0
        out: list[dict] = []
        last_keepalive = _t.monotonic()
        while _t.monotonic() < deadline:
            for frame in self._pump_rx(500):
                payload_json = self._record_rx(frame)
                out.append({"meta": {k: frame[k] for k in ("kind", "code", "session_id", "request_id", "wire_seq")},
                            "payload": payload_json})
            if keepalive_s and _t.monotonic() - last_keepalive >= keepalive_s:
                try:
                    self.ping()
                except (TimeoutError, ProtocolError):
                    pass
                last_keepalive = _t.monotonic()
        return out

    def keepalive_ping(self) -> None:
        try:
            self.ping()
        except (TimeoutError, ProtocolError):
            pass

    def session_close(self) -> dict:
        return self.call("SESSION_CLOSE", {}, timeout_ms=1000)
