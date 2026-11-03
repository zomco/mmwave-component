
def _parse_iso8601(s):
    if not isinstance(s, str) or not s:
        return None
    try:
        raw = s.strip()
        if raw.endswith("Z") or raw.endswith("z"):
            raw = raw[:-1] + "+00:00"
        dt = datetime.fromisoformat(raw)
        if dt.tzinfo is None:
            return None
        return dt.astimezone(timezone.utc)
    except Exception:
        return None
from datetime import datetime, timedelta, timezone
"""Bank-one-at-a-time leg driver: every item gets its own fresh-boot USB
window (reset -> hello -> <=4 RPCs) and retries independently.

2026-10-26 r2 review (G2-R3-A/B) hardening:
- try_item returns True immediately on the first success (one execution,
  no extra reset); failures/exceptions append to the attempt log; a later
  success never erases a recorded failure.
- Side-effecting commits persist the op_id BEFORE sending
  (leg2-pending-ops.jsonl); a lost response is resolved by querying with
  the SAME op_id, and an unknown outcome stops with the op_id recorded -
  never a fresh-op_id blind retry.
- The stable environment key is the SHA-256 of a full manifest (image,
  sources, runner, client, profile, patch, board, preconditions); an
  incomplete identity forbids reuse; run_id is separate.
- Coexistence success requires: connected before the scan, the job
  succeeded, the results page ok:true, and the link still connected after
  the scan. failed-but-connected is RECOVERY_ONLY.
- The F-10 fresh-session commit in validate_max is a cold-start
  workaround EXPERIMENT, kept separate from the normal continuous chain
  (the R1 hardware gate). No chip/peripheral fault is claimed as proven.
"""

import hashlib
import json
import math
import os
import subprocess
import sys
import time
import urllib.request
import uuid
from pathlib import Path
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).resolve().parent))
import mwcp  # noqa: E402
import flash_verifier  # noqa: E402

COMPONENT = Path(__file__).resolve().parents[2]
EVIDENCE = COMPONENT.parents[1] / "tmp" / "mwcp-g2" / "evidence"
STATE = EVIDENCE / "leg2-bank.json"
ATTEMPTS = EVIDENCE / "leg2-attempts.jsonl"
RUN_ID = time.strftime("%Y%m%d-%H%M%S")
PORT = sys.argv[1] if len(sys.argv) > 1 else "COM9"
IP = "192.168.5.236"
VERBOSE = "-q" not in sys.argv


def _sha256(path):
    try:
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()
    except OSError:
        return None


TARGET_DEVICE_ID = os.environ.get("MWCP_TARGET_DEVICE_ID") or None


def environment_fingerprint(device_id: str | None = None, as_of_time: datetime | None = None):
    """Stable identity of the hardware/software under test.

    Fields: image (build-tree HINT), sources (incl. deferred_request.h),
    runner, client, profile, patch, board, preconditions. run_id is
    separate. `complete` requires every stable field to be a real hash AND
    a flashed/verify record (flashed_image_sha256 from flash-log) to exist
    - without flashed evidence the bank must not auto-skip (r3b review:
    the build output alone never proves the on-board image).
    """
    net_build = COMPONENT / ".esphome-host" / "build" / "r60abd1-host-nops" / "build"
    factory = net_build / "firmware.factory.bin"
    manifest_path = EVIDENCE / "leg2-env-manifest.json"
    effective_dev = device_id or TARGET_DEVICE_ID
    fp = {
        "image_sha256": _sha256(factory),  # build-tree hint
        "sources": {rel: _sha256(COMPONENT / rel) for rel in (
            "components/mmwave_host/mmwave_host.cpp", "components/mmwave_host/mmwave_host.h",
            "components/mmwave_host/deferred_request.h",
            "components/mmwave_host/mwcp_service.cpp", "components/mmwave_host/mwcp_service.h",
            "components/mmwave_host/mwcp_link.h", "components/mmwave_host/tx_pump.h",
            "protocol/cpp/mwcp_codec.h")},
        "runner": _sha256(Path(__file__)),
        "client": _sha256(COMPONENT / "tools" / "g2" / "mwcp.py"),
        "profile": _sha256(COMPONENT.parents[1] / "esphome-config" / "r60abd1-host-nops.yaml"),
        "patch": _sha256(COMPONENT / "patches" / "esphome-2026.9.1-wifi-scan-ownership.patch"),
        "board": {"port": PORT, "device": "esp32c3-luatos-core", "mac_hint": "dc:da:0c:f8:f2:74",
                  "device_id": effective_dev},
        "preconditions": {"wifi_profile": "static-ip-nops", "power_save": "none"},
        "run_id": RUN_ID,  # informational; excluded from the stable key
    }
    # identity completeness: every stable component must be a real hash
    missing = [k for k, v in fp.items()
               if k in ("image_sha256", "runner", "client", "profile", "patch")
               and not (isinstance(v, str) and len(v) == 64)]
    missing += [rel for rel, v in fp["sources"].items() if not (isinstance(v, str) and len(v) == 64)]
    if not effective_dev:
        missing.append("board.device_id (live device identity required)")
    # flashed evidence (r3d): a structured flash/verify RECORD must exist —
    # not a SHA substring in a text log. Records are REPLAYED in sequence
    # order (seq, then timestamp) and the board's LATEST valid state at this
    # run's point decides: a later successful flash of a DIFFERENT image
    # supersedes an older success, so a historical success for our image can
    # never survive it. The replay requires every record to carry its order
    # (seq or timestamp); without any ordering the log is unverifiable and
    # flashes evidence stays False. Fields per record: status, image_sha256,
    # board_id, seq, timestamp, optional verify ("ok"/"failed").
    flash_log = EVIDENCE / "flash-log-r2.txt"
    flashed_evidence = False
    flash_state_reason = "no flash log"
    if flash_log.is_file() and isinstance(fp["image_sha256"], str) and len(fp["image_sha256"]) == 64:
        records, unparsable = flash_verifier.parse_flash_log(flash_log)
        if unparsable > 0:
            flashed_evidence = False
            flash_state_reason = f"flash log contains {unparsable} unparsable non-JSON lines or non-object items"
        else:
            board_id = effective_dev or fp["board"].get("device_id") or fp["board"].get("mac_hint")
            board_records = [r for r in records if (r.get("device_id") or r.get("board_id")) == board_id]

            if not board_records:
                flash_state_reason = "no flash record for this board"
            else:
                now_utc = as_of_time if as_of_time is not None else datetime.now(timezone.utc)
                flashed_evidence, flashed_img, flash_state_reason = flash_verifier.replay_board_history_to_latest(
                    board_records, as_of_time=now_utc, expected_image_sha256=fp["image_sha256"]
                )
    if not effective_dev and flashed_evidence:
        flashed_evidence = False
        flash_state_reason = "missing verified live device identity"
    fp["flashed_evidence"] = flashed_evidence
    fp["flashed_evidence_reason"] = flash_state_reason
    if not flashed_evidence:
        missing.append(f"flashed_image_sha256 ({flash_state_reason})")
    fp["complete"] = not missing
    fp["missing"] = missing
    try:
        manifest_path.write_text(json.dumps(fp, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        pass
    return fp


# G2-R3-05: NO side effects at import time - importing this module must not
# write manifests or touch the filesystem beyond reads. The fingerprint is
# computed lazily on first real use (try_item), and the manifest write only
# happens when an item actually runs.
ENV = None


def environment(device_id: str | None = None):
    """Lazily computed environment fingerprint (import is side-effect free)."""
    global ENV
    effective_dev = device_id or TARGET_DEVICE_ID
    if ENV is None or (effective_dev and ENV.get("board", {}).get("device_id") != effective_dev):
        ENV = environment_fingerprint(device_id=effective_dev)
    return ENV


def environment_key(device_id: str | None = None):
    """Stable reuse key: the SHA-256 of the full manifest content. Incomplete
    identity returns None, and None never matches a banked entry."""
    env = environment(device_id=device_id)
    if not env.get("complete"):
        return None
    return hashlib.sha256(json.dumps(
        {k: v for k, v in env.items() if k not in ("run_id", "complete", "missing")},
        sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def poly(n, r=400):
    return [[round(r * math.cos(2 * math.pi * k / n), 2), round(r * math.sin(2 * math.pi * k / n), 2)] for k in range(n)]


def reset_device():
    subprocess.run([str(COMPONENT / ".venv-esphome" / "Scripts" / "python.exe"), "-m", "esptool",
                    "--port", PORT, "run"], capture_output=True, timeout=45)
    time.sleep(8)


PENDING_OPS = EVIDENCE / "leg2-pending-ops.jsonl"


class UnknownOutcome(Exception):
    """Raised when a side-effecting operation's outcome cannot be
    determined (G2-R3-02): try_item must stop the whole chain on this - no
    reset, no retry, no new op_id. The pending op_id stays recorded for
    explicit recovery."""


def _is_strict_bool(v):
    """True only for actual Python bools (not 0/1, not strings)."""
    return isinstance(v, bool)


def _is_valid_revision(v):
    """Protocol revision contract (G2-R3-02 r3d): a decimal-digit STRING
    (ASCII 0-9 only - str.isdigit() also accepts Arabic-Indic/fullwidth
    Unicode digits, which the schema's ^[0-9]+$ does not), 1-20 UTF-8
    bytes (x-maxUtf8Bytes: 20), and within the uint64 range (the protocol
    stores revision as a 64-bit counter: "18446744073709551615" is the
    max legal value; anything larger is out of contract even though the
    pattern alone would accept it)."""
    if not isinstance(v, str) or not 1 <= len(v.encode("utf-8")) <= 20:
        return False
    if not all(c in "0123456789" for c in v):
        return False
    return int(v) <= 18446744073709551615


def _validate_error_envelope(err):
    """Return True when err is a well-formed protocol error object
    ({code: non-empty string, message: string}), else False. Unknown
    extra fields are allowed per the open-object policy."""
    return (isinstance(err, dict)
            and isinstance(err.get("code"), str) and err.get("code")
            and isinstance(err.get("message"), str))


def _validate_commit_success(c, expected_op_id):
    """Validate a CONFIG_COMMIT success envelope against the current
    protocol contract. Returns (True, detail) or raises UnknownOutcome.

    Mandatory: ok is strict True; result is a dict with
      - op_id equal to the request's op_id (string),
      - revision matching the decimal contract,
      - persisted is strict True,
      - restart_required is strict False (the current schema pins
        const:false - a true value is NOT a valid success under the
        unmodified contract; accepting it pre-approves an unapproved
        protocol change. A future schema change must update this).
    Unknown extra fields are allowed. Anything failing this is UNKNOWN,
    not a known failure — the caller falls to COMMIT_STATUS."""
    if not isinstance(c, dict):
        raise UnknownOutcome(
            f"op_id={expected_op_id} recorded; CONFIG_COMMIT returned a "
            f"malformed response ({type(c).__name__}) - outcome unknown")
    if not _is_strict_bool(c.get("ok")):
        raise UnknownOutcome(
            f"op_id={expected_op_id} recorded; CONFIG_COMMIT ok is not a "
            f"strict boolean ({json.dumps(c, default=str)[:120]}) - "
            f"outcome unknown")
    if c["ok"] is not True:
        raise UnknownOutcome(
            f"op_id={expected_op_id} recorded; CONFIG_COMMIT ok=false "
            f"without usable error envelope - outcome unknown")
    res = c.get("result")
    if not isinstance(res, dict):
        raise UnknownOutcome(
            f"op_id={expected_op_id} recorded; CONFIG_COMMIT result "
            f"malformed ({type(res).__name__}) - outcome unknown")
    if res.get("op_id") != expected_op_id:
        raise UnknownOutcome(
            f"op_id={expected_op_id} recorded; CONFIG_COMMIT returned a "
            f"different op_id ({res.get('op_id')!r:.40}) - outcome unknown")
    if not _is_valid_revision(res.get("revision")):
        raise UnknownOutcome(
            f"op_id={expected_op_id} recorded; CONFIG_COMMIT revision "
            f"invalid ({res.get('revision')!r:.30}) - outcome unknown")
    if res.get("persisted") is not True:
        raise UnknownOutcome(
            f"op_id={expected_op_id} recorded; CONFIG_COMMIT persisted is "
            f"not strict true - outcome unknown")
    rr = res.get("restart_required")
    # G2-R3-02 (r3d): the CONFIG_COMMIT result schema pins
    # restart_required to const:false. A true (or non-false) value is a
    # contract violation -> UNKNOWN, not a tolerated future semantics.
    if rr is not False:
        raise UnknownOutcome(
            f"op_id={expected_op_id} recorded; CONFIG_COMMIT "
            f"restart_required violates the schema const:false "
            f"({rr!r}) - outcome unknown")
    return True, json.dumps(c)[:140]


def _validate_commit_error(c):
    """Validate an ok=false error envelope. Returns (False, detail) when
    well-formed; raises UnknownOutcome otherwise."""
    err = c.get("error")
    if not _validate_error_envelope(err):
        raise UnknownOutcome(
            f"op_id recorded; CONFIG_COMMIT ok=false with malformed error "
            f"envelope ({json.dumps(c, default=str)[:120]}) - outcome unknown")
    return False, json.dumps(c)[:140]


def record_op_id(op_id, item, changes):
    """Persist the op_id BEFORE the side-effecting request is sent (r2
    review G2-R3-A: after a lost response, the original op_id must be
    queryable without regenerating one)."""
    PENDING_OPS.open("a", encoding="utf-8").write(json.dumps(
        {"op_id": op_id, "item": item, "changes": changes,
         "wall": time.strftime("%Y-%m-%dT%H:%M:%S")}, ensure_ascii=False) + "\n")


def query_commit_status(session, op_id, timeout_ms):
    """Protocol COMMIT_STATUS query (0x0023) with the ORIGINAL op_id.

    Returns (ok, detail) or raises UnknownOutcome. Semantics per the
    protocol contract: found=true requires the protocol's mandatory fields
    (revision, current_revision) to be present - a found=true without them
    is not a usable confirmation. found=false is NOT "not executed" - the
    replay cache holds only the last kCommitRing entries, so an evicted
    op_id also reads found=false and stays UNKNOWN."""
    try:
        s = session.call("COMMIT_STATUS", {"op_id": op_id}, timeout_ms=timeout_ms)
    except Exception as query_error:  # noqa: BLE001
        raise UnknownOutcome(
            f"op_id={op_id} recorded in leg2-pending-ops.jsonl; COMMIT_STATUS "
            f"query failed ({repr(query_error)[:80]}) - outcome unknown")
    # G2-R3-02 (r3b/r3c): fail-closed response-shape validation via the
    # shared validators. None, lists, strings, non-boolean ok, unusable
    # result shapes, or invalid revisions are all UNKNOWN.
    if not isinstance(s, dict):
        raise UnknownOutcome(
            f"op_id={op_id} recorded; COMMIT_STATUS returned a malformed "
            f"response ({type(s).__name__}) - outcome unknown")
    if not _is_strict_bool(s.get("ok")):
        raise UnknownOutcome(
            f"op_id={op_id} recorded; COMMIT_STATUS ok is not a strict "
            f"boolean ({json.dumps(s, default=str)[:120]}) - outcome unknown")
    if s["ok"] is not True:
        raise UnknownOutcome(
            f"op_id={op_id} recorded; COMMIT_STATUS ok=false "
            f"({json.dumps(s, default=str)[:120]}) - outcome unknown")
    res = s.get("result")
    if not isinstance(res, dict):
        raise UnknownOutcome(
            f"op_id={op_id} recorded; COMMIT_STATUS result malformed "
            f"({type(res).__name__}) - outcome unknown")
    if res.get("found") is True:
        # found=true requires the protocol's mandatory fields (0x0023
        # contract) with VALID values and types - null, wrong types, or
        # non-contract revisions do not confirm a success.
        rev = res.get("revision")
        cur = res.get("current_revision")
        if not _is_valid_revision(rev) or not _is_valid_revision(cur):
            raise UnknownOutcome(
                f"op_id={op_id} recorded; COMMIT_STATUS found=true but "
                f"revision/current_revision invalid "
                f"({json.dumps(res, default=str)[:120]}) - outcome unknown")
        return True, (f"resolved-by-COMMIT_STATUS found=true "
                      f"revision={rev}")
    # found=false: never executed OR evicted from the replay cache - the
    # protocol says this does NOT prove the commit was not executed.
    raise UnknownOutcome(
        f"op_id={op_id} recorded; COMMIT_STATUS found=false (not executed OR "
        f"evicted from the replay cache) - outcome unknown")


def commit_with_query(session, item, base_revision, changes, timeout_ms=12000):
    """CONFIG_COMMIT with the lost-response contract. Returns
    (ok, detail); raises UnknownOutcome when the outcome cannot be
    determined - try_item must then stop the whole chain (no reset, no
    retry, no new op_id).

    G2-R3-02 (r3b): transport failures are NOT classified by matching the
    exception's text. Every exception that reaches us after the request
    left (or may have left) the host - timeouts, write stalls, serial
    disconnects, malformed responses, parse failures - is treated as
    "possibly executed": keep the op_id and query COMMIT_STATUS. Only an
    explicit protocol-level response (ok:false with an error code) is a
    known failure; everything unproven stays UNKNOWN and stops the chain."""
    op_id = str(uuid.uuid4())
    record_op_id(op_id, item, changes)
    transport_error = None
    try:
        c = session.call("CONFIG_COMMIT", {"base_revision": base_revision, "op_id": op_id,
                                           "changes": changes}, timeout_ms=timeout_ms)
    except Exception as error:  # noqa: BLE001
        # Any exception here happened while/after sending: write timeouts,
        # read disconnects, protocol timeouts, malformed frames. None of
        # them PROVE the request was not executed, so all of them fall to
        # the status query (never a blind re-send with this op_id, never a
        # new one).
        transport_error = error
    if transport_error is not None:
        # A failed COMMIT_STATUS query leaves the outcome unknown via
        # UnknownOutcome from query_commit_status.
        return query_commit_status(session, op_id, timeout_ms)
    # G2-R3-02 (r3c): unified fail-closed commit-response validation via
    # _validate_commit_success/_validate_commit_error. Only a complete
    # envelope with correct field types/semantics is a known outcome;
    # everything else is UNKNOWN (no new op_id, no retry, no reset) with a
    # COMMIT_STATUS query to decide if it can.
    if not isinstance(c, dict):
        raise UnknownOutcome(
            f"op_id={op_id} recorded; CONFIG_COMMIT returned a malformed "
            f"response ({type(c).__name__}) - outcome unknown")
    if not _is_strict_bool(c.get("ok")):
        raise UnknownOutcome(
            f"op_id={op_id} recorded; CONFIG_COMMIT ok is not a strict "
            f"boolean ({json.dumps(c, default=str)[:120]}) - outcome unknown")
    if c["ok"] is True:
        return _validate_commit_success(c, op_id)
    return _validate_commit_error(c)


class Session:
    def __init__(self, tag):
        self.ev = mwcp.EvidenceWriter(EVIDENCE / f"{tag}-{time.strftime('%Y%m%d-%H%M%S')}.jsonl", mwcp.Redactor())
        self.cli = mwcp.Client(PORT, self.ev, allow_write=True)
        self.cli.hello(timeout_ms=25000)

    def call(self, name, payload=None, timeout_ms=9000):
        return self.cli.call(name, payload, timeout_ms=timeout_ms)

    def read_all(self):
        values, cursor, rev = {}, None, None
        while True:
            r = self.call("CONFIG_READ", {"cursor": cursor})
            if not r.get("ok"):
                raise RuntimeError(f"read: {json.dumps(r)[:100]}")
            res = r["result"]
            rev = res.get("revision")
            for item in res.get("items", []):
                values[item["key"]] = item["value"]
            cursor = res.get("next_cursor")
            if cursor is None:
                return values, rev

    def close(self):
        try:
            self.cli.close()
        except Exception:
            pass
        try:
            return self.ev.close()
        except Exception:
            return {}


def getn(name="Mount X"):
    with urllib.request.urlopen(f"http://{IP}/number/{quote(name)}", timeout=10) as resp:
        return json.loads(resp.read().decode())


def setn(value, name="Mount X"):
    req = urllib.request.Request(f"http://{IP}/number/{quote(name)}/set?value={value}", data=b"", method="POST")
    with urllib.request.urlopen(req, timeout=10) as resp:
        return resp.status


def bank_load():
    if STATE.exists():
        return json.loads(STATE.read_text(encoding="utf-8"))
    return {}


def bank_save(bank):
    STATE.write_text(json.dumps(bank, ensure_ascii=False, indent=2), encoding="utf-8")


def attempts_append(record):
    """Append-only attempt log (2026-10-26 review: failures, recoveries and
    exceptions must survive; a later success never overwrites them)."""
    ATTEMPTS.open("a", encoding="utf-8").write(json.dumps(record, ensure_ascii=False) + "\n")


def try_item(bank, item_id, fn, attempts=5):
    env = environment()
    env_key = environment_key()
    prior = bank.get(item_id, {})
    if env_key is None:
        if VERBOSE:
            print(f"[STOP] {item_id}: environment identity incomplete "
                  f"({env.get('missing')}); reuse forbidden", flush=True)
        return False
    banked = prior.get("env") == env_key and prior.get("pass")
    if banked:
        if VERBOSE:
            print(f"[SKIP] {item_id} already banked for this environment", flush=True)
        return True
    if prior.get("pass") and prior.get("env") != env_key:
        if VERBOSE:
            print(f"[HIST] {item_id} pass recorded under different environment; re-running", flush=True)
    if prior.get("outcome") == "unknown":
        if VERBOSE:
            print(f"[HOLD] {item_id} outcome unknown from a previous run "
                  f"(op_id recorded); NOT re-issuing - explicit recovery first", flush=True)
        return False
    for attempt in range(attempts):
        record = {"item": item_id, "run_id": RUN_ID, "env_key": env_key,
                  "attempt": attempt, "wall": time.strftime("%Y-%m-%dT%H:%M:%S")}
        try:
            ok, detail = fn()
            record.update({"status": "pass" if ok else "fail", "detail": str(detail)[:300]})
            bank[item_id] = {"pass": bool(ok), "detail": str(detail)[:300],
                             "wall": record["wall"], "attempt": attempt, "env": env_key,
                             "run_id": RUN_ID}
            bank_save(bank)
            attempts_append(record)  # logged before any return (G2-R3-02)
            if VERBOSE:
                print(f"[{'PASS' if ok else 'FAIL'}] {item_id} :: {str(detail)[:110]} (attempt {attempt})", flush=True)
            if ok:
                return True
        except UnknownOutcome as error:
            # G2-R3-02: an undetermined side-effect outcome stops the whole
            # chain - no reset, no retry, no new op_id. The pending op_id
            # stays in leg2-pending-ops.jsonl for explicit recovery.
            record.update({"status": "unknown", "detail": repr(error)[:300]})
            bank[item_id] = {"pass": False, "outcome": "unknown",
                             "detail": repr(error)[:300], "wall": record["wall"],
                             "attempt": attempt, "env": env_key, "run_id": RUN_ID}
            bank_save(bank)
            attempts_append(record)
            if VERBOSE:
                print(f"[UNKNOWN] {item_id} :: {repr(error)[:110]} - chain stopped", flush=True)
            return False
        except Exception as error:  # noqa: BLE001
            record.update({"status": "exception", "detail": repr(error)[:300]})
            attempts_append(record)
            if VERBOSE:
                print(f"[..] {item_id} attempt {attempt}: {repr(error)[:90]}", flush=True)
        reset_device()
    return False


def main():
    bank = bank_load()

    def item_validate_max():
        # F-10 platform workaround (see tmp/usb-diag/README.md): the C3
        # usb_serial_jtag peripheral stops delivering RX after ~1KB per
        # session (both bench units, zero-MWCP echo firmware reproduces,
        # in-process heal is ineffective). Each >1KB operation therefore
        # runs in its own fresh session - port open resets the device, and
        # hello + STATUS_GET cost only ~70B, so the big frame is the first
        # large frame of a cold boot, which always passes.
        big = {"install.x_cm": 120.0, "install.y_cm": -80.0, "install.z_cm": 280.0,
               "install.yaw_deg": 15.0, "install.pitch_deg": -5.0, "install.roll_deg": 3.0,
               "geometry.boundary_cm": poly(64),
               "areas.definitions": [
                   {"slot": 0, "enabled": True, "name": "g2-door", "points_cm": poly(12, 150)},
                   {"slot": 1, "enabled": True, "name": "g2-desk", "points_cm": poly(12, 200)},
                   {"slot": 2, "enabled": True, "name": "g2-sofa", "points_cm": poly(12, 300)}]}
        op_id = str(uuid.uuid4())
        record_op_id(op_id, "validate_max", {"snapshot": "max-legal-config"})

        s = Session("l2-validate")
        try:
            rev = s.call("STATUS_GET")["result"]["config_revision"]
            r = s.call("CONFIG_VALIDATE", {"base_revision": rev, "changes": big})
            vok = r.get("ok") is True
            vdetail = json.dumps(r)[:110]
        finally:
            s.close()
        if not vok:
            return False, f"validate: {vdetail}"

        s = Session("l2-commit-max")
        try:
            rev = s.call("STATUS_GET")["result"]["config_revision"]
            # NOTE: this cold-start commit is the F-10 workaround experiment
            # (each >1KB op in its own fresh session). It is NOT the normal
            # continuous chain; that chain is the R1 hardware gate.
            cok, cdetail = commit_with_query(s, "validate_max", rev, big)
        finally:
            s.close()
        if not cok:
            return False, f"validate ok; commit: {cdetail}"

        s = Session("l2-readback-max")
        try:
            values, rev2 = s.read_all()

            def norm(v):
                if isinstance(v, float):
                    return round(v, 2)
                if isinstance(v, list):
                    return [norm(x) for x in v]
                if isinstance(v, dict):
                    return {k: norm(x) for k, x in sorted(v.items())}
                return v

            # 2026-10-26 review: a full normalized snapshot comparison - all
            # install params, all 64 coordinates, every area field - not a
            # point-count/X spot check.
            expect = norm({"install.x_cm": 120.0, "install.y_cm": -80.0, "install.z_cm": 280.0,
                           "install.yaw_deg": 15.0, "install.pitch_deg": -5.0, "install.roll_deg": 3.0,
                           "geometry.boundary_cm": poly(64),
                           "areas.definitions": [
                               {"slot": 0, "enabled": True, "name": "g2-door", "points_cm": poly(12, 150)},
                               {"slot": 1, "enabled": True, "name": "g2-desk", "points_cm": poly(12, 200)},
                               {"slot": 2, "enabled": True, "name": "g2-sofa", "points_cm": poly(12, 300)}]})
            actual = {k: norm(values.get(k)) for k in expect}
            rok = actual == expect
            diff = "" if rok else next((f"{k}: got={str(actual.get(k))[:60]} want={str(v)[:60]}"
                                        for k, v in expect.items() if actual.get(k) != v), "?")
        finally:
            s.close()
        return vok and cok and rok, (f"validate+commit+readback snapshot_ok={rok} rev->{rev2} "
                                     f"[F-10 fresh-session pattern, op_id={op_id[:8]}] {diff}")

    def item_validate_illegal():
        s = Session("l2-illegal")
        try:
            _, rev = s.read_all()
            bad1 = s.call("CONFIG_VALIDATE", {"base_revision": rev, "changes": {"install.z_cm": 601}})
            bad2 = s.call("CONFIG_VALIDATE", {"base_revision": rev,
                                              "changes": {"geometry.boundary_cm": [[0, 0], [100, 100], [100, 0], [0, 100]]}})
            ok = (bad1.get("error", {}).get("code") == "OUT_OF_RANGE"
                  and bad2.get("ok") is False and bad2.get("error", {}).get("code") in ("INVALID_ARGUMENT", "OUT_OF_RANGE"))
            return ok, f"601->{bad1.get('error', {}).get('code')} selfint->{bad2.get('error', {}).get('code')}"
        finally:
            s.close()

    def item_readback_after_commit():
        s = Session("l2-readback")
        try:
            back, rev = s.read_all()
            b = back.get("geometry.boundary_cm")
            ok = isinstance(b, list) and len(b) == 5 and back.get("install.x_cm") in (123.0, 140.0)
            return ok, f"x={back.get('install.x_cm')} pts={len(b) if isinstance(b, list) else None} rev={rev}"
        finally:
            s.close()

    def item_web_preserved():
        s = Session("l2-webkept")
        try:
            back, rev = s.read_all()
            return back.get("install.x_cm") == 123.0, f"x={back.get('install.x_cm')} rev={rev} (web value kept)"
        finally:
            s.close()

    def item_usb_commit_after_web():
        s = Session("l2-usbwrite")
        try:
            _, rev = s.read_all()
            ok, detail = commit_with_query(s, "usb_commit_after_web", rev,
                                           {"install.x_cm": 140.0})
            return ok, detail
        finally:
            s.close()

    def item_web_reads_usb():
        w = getn()
        return w.get("value") == "140", json.dumps(w)[:90]

    def item_restart_persist():
        created_job = None
        created_op = None
        s = Session("l2-restart1")
        try:
            _, revA = s.read_all()
            cok, cdetail = commit_with_query(s, "restart_persist", revA,
                                             {"install.y_cm": -77.0})
            created_op = None
            # recover the op_id the helper recorded (needed for post-restart query)
            for line in reversed(PENDING_OPS.read_text(encoding="utf-8").splitlines()):
                rec = json.loads(line)
                if rec.get("item") == "restart_persist":
                    created_op = rec["op_id"]
                    break
            if not cok:
                return False, f"commit failed {cdetail}"
            _, revB = s.read_all()
            rj = s.call("ACTION_START", {"action_id": "device.restart", "op_id": str(uuid.uuid4()),
                                         "params": {}, "confirm": "device.restart"})
            if not rj.get("ok"):
                return False, "restart not accepted"
            created_job = rj["result"]["job_id"]
            boot_before = s.cli.boot_id
        finally:
            s.close()
        time.sleep(14)
        s2 = Session("l2-restart2")
        try:
            new_boot = s2.cli.boot_id
            back, revC = s2.read_all()
            st = None
            for _ in range(10):
                st = s2.call("WIFI_STATUS").get("result", {})
                if st.get("state") == "connected":
                    break
                time.sleep(2)
            # 2026-10-26 review: query THIS run's job_id/op_id after restart;
            # a port-open reset is not an ACTION_START success.
            old_job = s2.call("JOB_GET", {"job_id": created_job}).get("result", {})
            old_ok = old_job.get("state") == "unknown"
            ok = (new_boot != boot_before and back.get("install.y_cm") == -77.0 and revC == revB
                  and st.get("state") == "connected" and old_ok)
            return ok, (f"boot_changed={new_boot != boot_before} y={back.get('install.y_cm')} "
                        f"rev={revB}->{revC} wifi={st.get('state')} "
                        f"job={created_job[:14]}..->{old_job.get('state')} op={created_op[:8]}")
        finally:
            s2.close()

    def item_old_job_unknown():
        # Semantic support check: an arbitrary never-issued id reads unknown.
        # The real cross-restart evidence lives in item_restart_persist(),
        # which queries the job_id/op_id it actually created.
        s = Session("l2-oldjob")
        try:
            j = s.call("JOB_GET", {"job_id": f"unknown-{uuid.uuid4()}"})
            return j.get("ok") and j.get("result", {}).get("state") == "unknown", json.dumps(j)[:120]
        finally:
            s.close()

    def item_telemetry():
        s = Session("l2-telemetry")
        try:
            sub = s.call("SUBSCRIBE", {"streams": [{"id": "telemetry", "max_rate_hz": 1}],
                                       "event_budget_bps": 8000})
            if not sub.get("ok"):
                return False, "subscribe failed"
            events = s.cli.drain_events(45000)
            telem = [e for e in events if e["meta"]["code"] == mwcp.CODE["TELEMETRY"]]
            if not telem:
                return False, "no telemetry in 45s"
            sample = telem[0]["payload"]
            fields = all(k in sample for k in ("source_seq", "sent_ms", "presence", "targets_quality", "targets"))
            seqs = [e["payload"].get("source_seq") for e in telem]
            mono = all(b >= a for a, b in zip(seqs, seqs[1:]))
            speeds = [t.get("speed_cm_s") for e in telem for t in (e["payload"].get("targets") or [])]
            no_speed = all(x is None for x in speeds)
            return fields and mono and no_speed, f"n={len(telem)} fields={fields} seq_mono={mono} speed_null={no_speed}"
        finally:
            s.close()

    def make_coexist(i):
        def item():
            s = Session(f"l2-coexist-{i}")
            try:
                # wait for the post-boot association before judging coexistence
                connected_before = False
                for _ in range(12):
                    st0 = s.call("WIFI_STATUS").get("result", {})
                    if st0.get("state") == "connected":
                        connected_before = True
                        break
                    time.sleep(2)
                if not connected_before:
                    return False, "precondition_unmet: not connected before scan"
                r = s.call("WIFI_SCAN", {"op_id": str(uuid.uuid4())})
                if not r.get("ok"):
                    return False, f"refused {json.dumps(r)[:70]}"
                job = r["result"]["job_id"]
                term = None
                deadline = time.time() + 30
                while time.time() < deadline:
                    term = s.call("JOB_GET", {"job_id": job}).get("result", {})
                    if term.get("state") in ("succeeded", "failed"):
                        break
                    time.sleep(1.2)
                page = s.call("WIFI_SCAN_RESULTS", {"job_id": job, "cursor": None})
                st = s.call("WIFI_STATUS").get("result", {})
                state = term.get("state") if term else None
                page_ok = page.get("ok") is True
                still_connected = st.get("state") == "connected"
                if state == "succeeded" and page_ok and still_connected:
                    # full success: scan completed, page delivered, link kept
                    return True, f"succeeded page_ok=True wifi=connected job={job}"
                if state == "failed" and still_connected:
                    # recovery data only (2026-10-26 review: a failed scan
                    # that keeps the link is NOT one of the ten successes)
                    return False, (f"RECOVERY_ONLY failed page_ok={page.get('ok')} "
                                   f"wifi=connected job={job}")
                return False, f"{state} page_ok={page.get('ok')} wifi={st.get('state')} job={job}"
            finally:
                s.close()
        return item

    results = {}
    for item_id, fn in [
        ("validate_max", item_validate_max),
        ("validate_illegal", item_validate_illegal),
        ("readback_after_commit", item_readback_after_commit),
        ("web_value_preserved", item_web_preserved),
        ("usb_commit_after_web", item_usb_commit_after_web),
        ("web_reads_back_usb", item_web_reads_usb),
        ("restart_persistence", item_restart_persist),  # multi-window item
        ("old_job_unknown", item_old_job_unknown),
        ("telemetry", item_telemetry),
    ]:
        results[item_id] = try_item(bank, item_id, fn)
    for i in range(10):
        results[f"coexist_{i}"] = try_item(bank, f"coexist_{i}", make_coexist(i), attempts=3)

    all_ok = all(v for v in results.values())
    out = {"run_id": "g2-legs2", "bank": bank, "summary_pass": all_ok,
           "file": str(STATE), "wall": time.strftime("%Y-%m-%dT%H:%M:%S")}
    (EVIDENCE / "g2-legs2.result.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"=== legs2 overall: {'PASS' if all_ok else 'PARTIAL'} ===", flush=True)
    for k, v in results.items():
        print(f"  {k}: {'ok' if v else 'MISSING'}", flush=True)


if __name__ == "__main__":
    main()
