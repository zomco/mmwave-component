#!/usr/bin/env python3
"""Unified pure verification contract for MWCP G2 flash evidence (H3).

Used consistently across:
- run_g2.py (cmd_soak, load_flash_evidence)
- build_evidence_index.py (batch_for_run)
- leg_driver2.py (environment_fingerprint)
- bank and regression test suites

Enforces:
1. Strict schema for flash record:
   - status == 'success'
   - verify is string in ('ok', 'verified')
   - valid 64-hex image_sha256 (not all zeros)
   - matching device_id/board_id
   - ISO-8601 timestamp with timezone, not in future relative to run_started
2. Mandatory source object:
   - Missing source -> unverified / unknown
   - source.ref must exist on disk
   - sha256(source.ref) must match source.sha256
3. Source file content parsing:
   - All lines/entries must be valid structured JSON records (no plain text, no swallowed syntax errors).
4. Explicit semantic match:
   - The source file MUST contain a matching success event for the claimed device and image,
     with normalized timestamp and seq/event_id matching the claim, on or before run start.
5. Full run-window lifecycle replay:
   - From the flash event to run_ended (or run_started), replay all records for this device.
   - Any subsequent failed/aborted/erased/partial/unknown event, missing status, or different
     image supersedes or invalidates the flash claim.
   - Events after run_ended or for other devices do not invalidate.
6. Bank history consistency:
   - Shared validation of order anchors, duplicate sequence conflicts, sequence/timestamp contradictions,
     and replay to latest valid state as of a given timestamp.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


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


def evaluate_flash_event(ev: dict) -> tuple[str, str | None, str | None, str]:
    """Evaluate a single flash event record.
    Returns (status_kind, normalized_image_sha256, verify_val, diagnostic_reason).
    status_kind is one of:
      - 'success': valid success with verify in ('ok', 'verified') and valid 64-hex image
      - 'unverified_success': success status but verify != ok/verified or invalid image
      - 'failed', 'aborted', 'erased', 'partial', 'unknown': recognized terminal/invalidation states
      - 'invalid': missing or non-string status
      - 'unrecognized': unrecognized status string
    """
    if not isinstance(ev, dict):
        return "invalid", None, None, "record is not a dictionary"
    raw_status = ev.get("status")
    if not isinstance(raw_status, str) or not raw_status.strip():
        return "invalid", None, None, f"missing status or non-string status: {raw_status!r}"
    status = raw_status.strip()

    if status in ("failed", "aborted", "erased", "partial", "unknown"):
        return status, None, None, f"status={status!r}"

    if status == "success":
        raw_img = ev.get("image_sha256")
        is_valid_image = (
            isinstance(raw_img, str)
            and len(raw_img) == 64
            and all(c in "0123456789abcdef" for c in raw_img.lower())
            and raw_img.lower() != "0" * 64
        )
        img_norm = raw_img.lower() if is_valid_image else None
        raw_verify = ev.get("verify")
        is_verify_ok = isinstance(raw_verify, str) and raw_verify.lower() in ("ok", "verified")
        if is_valid_image and is_verify_ok:
            return "success", img_norm, "ok", "ok"
        else:
            if not is_valid_image:
                diag = f"invalid image_sha256: {raw_img!r}"
            else:
                diag = f"verify={raw_verify!r} (expected 'ok' or 'verified')"
            return "unverified_success", img_norm, raw_verify if isinstance(raw_verify, str) else None, diag

    return "unrecognized", None, None, f"unrecognized status: {status!r}"


def parse_flash_log(source_input: str | Path) -> tuple[list[dict], int]:
    """Parse flash log file (JSON Lines, JSON object, or JSON array of objects).
    Returns (records: list[dict], unparsable_count: int)."""
    p = Path(source_input) if isinstance(source_input, (str, Path)) else None
    if p is None or not p.is_file():
        return [], 0
    try:
        content = p.read_text(encoding="utf-8")
    except Exception:
        return [], 1

    trimmed = content.strip()
    if not trimmed:
        return [], 0

    # 1. Try parsing as a whole JSON document first (supports single object or JSON array, compact or indented)
    try:
        whole = json.loads(trimmed)
        if isinstance(whole, dict):
            return [whole], 0
        elif isinstance(whole, list):
            valid = [x for x in whole if isinstance(x, dict)]
            unparsable = len(whole) - len(valid)
            return valid, unparsable
        else:
            return [], 1
    except Exception:
        pass

    # 2. Not a single valid JSON document; parse as JSON Lines
    raw_lines = [l.strip() for l in content.splitlines() if l.strip()]
    if not raw_lines:
        return [], 0

    records = []
    unparsable = 0
    for line in raw_lines:
        try:
            rec = json.loads(line)
            if isinstance(rec, dict):
                records.append(rec)
            else:
                unparsable += 1
        except Exception:
            unparsable += 1

    return records, unparsable


def validate_board_history(board_records: list[dict], as_of_time: datetime | None = None) -> tuple[bool, str]:
    """Validate consistency, sequencing, and absence of conflicts in a board's flash history records."""
    if not board_records:
        return False, "no flash record for this board"

    # 1. Ordering anchors & timestamps
    for r in board_records:
        if not isinstance(r, dict):
            return False, "flash records carry non-dict record"
        seq = r.get("seq")
        has_seq = isinstance(seq, int) and not isinstance(seq, bool)
        ts_str = r.get("timestamp")
        ts_dt = _parse_iso8601(ts_str) if isinstance(ts_str, str) else None
        if not has_seq and ts_dt is None:
            return False, "flash records carry unorderable record (missing seq and timestamp)"
        if as_of_time is not None and ts_dt is not None and ts_dt > as_of_time:
            return False, "flash records carry future timestamp (flash cannot be in the future)"

    has_all_ts = all(
        isinstance(r.get("timestamp"), str) and _parse_iso8601(r.get("timestamp")) is not None
        for r in board_records
    )
    has_all_seq = all(
        isinstance(r.get("seq"), int) and not isinstance(r.get("seq"), bool)
        for r in board_records
    )
    if not has_all_ts and not has_all_seq:
        return False, "flash records carry unorderable records (missing common order anchor between timestamp and seq)"

    # 2. Check duplicate sequence conflict
    seq_map = {}
    for rec in board_records:
        s = rec.get("seq")
        if isinstance(s, int) and not isinstance(s, bool):
            ts_str = rec.get("timestamp")
            t_parsed = _parse_iso8601(ts_str) if isinstance(ts_str, str) else None
            t_key = t_parsed.isoformat() if t_parsed is not None else None
            ev_kind, img_norm, v_val, _ = evaluate_flash_event(rec)
            sig = (ev_kind, img_norm, v_val, t_key)
            if s in seq_map:
                if seq_map[s] != sig:
                    return False, "flash records carry duplicate sequence conflict"
            else:
                seq_map[s] = sig

    # 3. Check sequence and timestamp contradiction
    for i in range(len(board_records)):
        r1 = board_records[i]
        s1 = r1.get("seq")
        ts1_str = r1.get("timestamp")
        t1 = _parse_iso8601(ts1_str) if isinstance(ts1_str, str) else None
        if not (isinstance(s1, int) and not isinstance(s1, bool)) or t1 is None:
            continue
        for j in range(i + 1, len(board_records)):
            r2 = board_records[j]
            s2 = r2.get("seq")
            ts2_str = r2.get("timestamp")
            t2 = _parse_iso8601(ts2_str) if isinstance(ts2_str, str) else None
            if not (isinstance(s2, int) and not isinstance(s2, bool)) or t2 is None:
                continue
            if (s1 < s2 and t1 > t2) or (s1 > s2 and t1 < t2):
                return False, "flash records carry sequence and timestamp contradiction"

    # 4. Check conflicting events at the same timestamp without sequence order (H3-L2)
    for i in range(len(board_records)):
        r1 = board_records[i]
        ts1 = _parse_iso8601(r1.get("timestamp")) if isinstance(r1.get("timestamp"), str) else None
        s1 = r1.get("seq")
        has_s1 = isinstance(s1, int) and not isinstance(s1, bool)
        if ts1 is None:
            continue
        for j in range(i + 1, len(board_records)):
            r2 = board_records[j]
            ts2 = _parse_iso8601(r2.get("timestamp")) if isinstance(r2.get("timestamp"), str) else None
            s2 = r2.get("seq")
            has_s2 = isinstance(s2, int) and not isinstance(s2, bool)
            if ts2 is None:
                continue
            if ts1 == ts2:
                # If they do not have distinct valid sequence numbers to determine unambiguous order
                if not (has_s1 and has_s2 and s1 != s2):
                    kind1, img1, v1, _ = evaluate_flash_event(r1)
                    kind2, img2, v2, _ = evaluate_flash_event(r2)
                    if (kind1, img1, v1) != (kind2, img2, v2):
                        return False, "flash records carry conflicting events at same timestamp without sequence order (unorderable)"

    return True, "ok"


def _sort_board_records(board_records: list[dict]) -> list[dict]:
    has_all_seq = all(
        isinstance(r.get("seq"), int) and not isinstance(r.get("seq"), bool)
        for r in board_records
    )
    def _sort_key(r):
        ts_str = r.get("timestamp")
        t = _parse_iso8601(ts_str) if isinstance(ts_str, str) else None
        t_val = t.timestamp() if t is not None else 0.0
        s = r.get("seq")
        s_val = s if (isinstance(s, int) and not isinstance(s, bool)) else 0
        if has_all_seq:
            return (s_val, t_val)
        else:
            return (t_val, s_val)
    return sorted(board_records, key=_sort_key)


def replay_board_history_to_latest(
    board_records: list[dict],
    as_of_time: datetime | None = None,
    expected_image_sha256: str | None = None,
) -> tuple[bool, str | None, str]:
    """Replay board history to find the latest valid flash state as of as_of_time.
    Used by bank (leg_driver2.environment_fingerprint).
    Returns (flashed_evidence: bool, flashed_image_sha256: str | None, reason: str)."""
    valid, reason = validate_board_history(board_records, as_of_time=as_of_time)
    if not valid:
        return False, None, reason

    sorted_records = _sort_board_records(board_records)
    last = None
    for rec in sorted_records:
        ts_str = rec.get("timestamp")
        t = _parse_iso8601(ts_str) if isinstance(ts_str, str) else None
        if as_of_time is not None and t is not None and t > as_of_time:
            continue
        kind, img_norm, v_val, diag = evaluate_flash_event(rec)
        if kind == "success":
            last = {"status": "success", "image_sha256": img_norm, "verify": "ok"}
        elif kind == "unverified_success":
            last = {"status": "unverified_success", "image_sha256": img_norm, "verify": v_val, "diag": diag}
        elif kind in ("failed", "aborted", "erased", "partial"):
            last = {"status": kind, "image_sha256": None, "verify": None, "diag": diag}
        else:
            last = {"status": "unknown", "image_sha256": None, "verify": None, "diag": diag}

    if last is None:
        return False, None, "no flash record for this board"
    if last["status"] == "unknown":
        return False, None, "board's latest flash was 'unknown'"
    if last["status"] == "unverified_success":
        return False, None, f"latest flash was not verify-ok ({last.get('diag')})"
    if last["status"] != "success":
        return False, None, f"board's latest flash was {last['status']!r}"
    if expected_image_sha256 and last["image_sha256"] != expected_image_sha256.lower():
        return False, None, "board's latest flash is a DIFFERENT image (supersedes the historical match)"
    if last.get("verify") != "ok":
        return False, None, f"latest flash was not verify-ok ({last.get('diag')})"

    return True, last["image_sha256"], "latest flash for this board matches this image"


def verify_flash_record(
    flash_input: dict | str | Path | None,
    run_started: str | None = None,
    run_ended: str | None = None,
    target_device_id: str | None = None,
) -> tuple[str, dict | None, list[str]]:
    """Validate a flash evidence input (file path or dict) against run constraints.

    Returns:
        (flashed_image_sha256, verified_flash_record, notes)
        On failure, returns ("unverified", rec, [reasons...]).
    """
    notes = []
    if flash_input is None:
        notes.append("flash evidence input is empty or missing")
        return "unverified", None, notes

    rec = None
    input_file_path = None
    if isinstance(flash_input, dict):
        rec = dict(flash_input)
    elif isinstance(flash_input, (str, Path)):
        p = Path(flash_input)
        if not p.is_file():
            notes.append(f"flash evidence file not found: {p}")
            return "unverified", None, notes
        input_file_path = p.resolve()
        try:
            parsed = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(parsed, dict):
                rec = parsed
            else:
                notes.append("flash evidence file does not contain a JSON object")
                return "unverified", None, notes
        except Exception as err:
            notes.append(f"flash evidence JSON parse error: {err}")
            return "unverified", None, notes
    else:
        notes.append("flash evidence input is of invalid type")
        return "unverified", None, notes

    # 1. Basic schema checks on the flash record (type-safe before any string methods)
    raw_status = rec.get("status")
    if not isinstance(raw_status, str) or raw_status != "success":
        notes.append(f"flash evidence status is {raw_status!r} (expected 'success')")
        return "unverified", rec, notes

    raw_verify = rec.get("verify")
    if not isinstance(raw_verify, str) or raw_verify.lower() not in ("ok", "verified"):
        notes.append(f"flash evidence verify is {raw_verify!r} (expected 'ok' or 'verified')")
        return "unverified", rec, notes

    raw_img = rec.get("image_sha256")
    if not (
        isinstance(raw_img, str)
        and len(raw_img) == 64
        and all(c in "0123456789abcdef" for c in raw_img.lower())
        and raw_img != "0" * 64
    ):
        notes.append("flash evidence invalid image_sha256")
        return "unverified", rec, notes
    img = raw_img.lower()

    rec_dev = rec.get("device_id")
    rec_board = rec.get("board_id")
    if rec_dev is not None and not isinstance(rec_dev, str):
        notes.append("flash evidence device_id is not a string")
        return "unverified", rec, notes
    if rec_board is not None and not isinstance(rec_board, str):
        notes.append("flash evidence board_id is not a string")
        return "unverified", rec, notes
    if rec_dev and rec_board and rec_dev != rec_board:
        notes.append("flash evidence has conflicting device_id and board_id")
        return "unverified", rec, notes
    flash_dev = rec_dev or rec_board
    if not flash_dev or not flash_dev.strip():
        notes.append("flash evidence missing device_id/board_id")
        return "unverified", rec, notes

    if target_device_id and flash_dev != target_device_id:
        notes.append(f"flash evidence device mismatch: {flash_dev!r} != {target_device_id!r}")
        return "unverified", rec, notes

    ts_str = rec.get("timestamp")
    if not isinstance(ts_str, str) or not ts_str.strip():
        notes.append("flash evidence missing mandatory timestamp")
        return "unverified", rec, notes
    flash_ts = _parse_iso8601(ts_str)
    if flash_ts is None:
        notes.append(f"flash evidence unparsable timestamp: {ts_str!r}")
        return "unverified", rec, notes

    if run_started:
        run_start_ts = _parse_iso8601(run_started)
        if run_start_ts and flash_ts > run_start_ts:
            notes.append(f"flash evidence timestamp {ts_str} is after run start {run_started}")
            return "unverified", rec, notes

    # 2. Mandatory source object
    source = rec.get("source")
    if source is None and input_file_path is not None:
        source = {
            "ref": str(input_file_path),
            "sha256": hashlib.sha256(input_file_path.read_bytes()).hexdigest(),
        }
        rec["source"] = source

    if source is None:
        notes.append("flash record missing mandatory source object (unverified without verifiable source)")
        return "unverified", rec, notes

    if not isinstance(source, dict):
        notes.append("flash record source must be a structured dictionary")
        return "unverified", rec, notes

    ref = source.get("ref")
    src_sha = source.get("sha256")
    if not isinstance(ref, str) or not isinstance(src_sha, str) or not ref or not src_sha:
        notes.append("flash record source missing ref or sha256")
        return "unverified", rec, notes

    ref_p = Path(ref)
    if not ref_p.is_file():
        notes.append(f"flash record source file not found: {ref}")
        return "unverified", rec, notes

    try:
        actual_src_sha = hashlib.sha256(ref_p.read_bytes()).hexdigest()
        if actual_src_sha.lower() != src_sha.lower():
            notes.append(f"flash record source sha256 mismatch: {actual_src_sha} != {src_sha}")
            return "unverified", rec, notes
    except Exception as err:
        notes.append(f"cannot read flash record source file {ref}: {err}")
        return "unverified", rec, notes

    # 3. Source content parsing and strict validation (no swallowed errors, no plain text)
    log_records, unparsable = parse_flash_log(ref_p)
    if unparsable > 0:
        notes.append(f"flash record source file contains {unparsable} unparsable non-JSON lines or items")
        return "unverified", rec, notes
    if not log_records:
        notes.append("flash record source contains no structured records")
        return "unverified", rec, notes

    # Filter records for the target device
    board_records = [r for r in log_records if (r.get("device_id") or r.get("board_id")) == flash_dev]
    if not board_records:
        notes.append(f"flash record source contains no records for device {flash_dev}")
        return "unverified", rec, notes

    # Validate board history consistency (unorderable, duplicate seq, seq/timestamp contradiction)
    valid_hist, hist_reason = validate_board_history(board_records)
    if not valid_hist:
        notes.append(hist_reason)
        return "unverified", rec, notes

    sorted_records = _sort_board_records(board_records)

    # 4. Explicit semantic match in source records (binding the same authentic source event)
    claim_seq = rec.get("seq")
    claim_event_id = rec.get("event_id")
    run_start_ts = _parse_iso8601(run_started) if run_started else None

    matching_events = []
    for r in sorted_records:
        r_dev = r.get("device_id") or r.get("board_id")
        r_ts_str = r.get("timestamp")
        r_ts = _parse_iso8601(r_ts_str) if isinstance(r_ts_str, str) else None
        r_seq = r.get("seq")
        r_event_id = r.get("event_id")

        if r_dev != flash_dev:
            continue
        kind, r_img, _, _ = evaluate_flash_event(r)
        if kind != "success":
            continue
        if r_img != img:
            continue
        if r_ts is None or r_ts != flash_ts:
            continue
        if claim_seq is not None and r_seq != claim_seq:
            continue
        if claim_event_id is not None and r_event_id != claim_event_id:
            continue
        # A flash event strictly after run start cannot establish the run's firmware
        if run_start_ts is not None and r_ts > run_start_ts:
            continue
        matching_events.append(r)

    if len(matching_events) == 0:
        notes.append(
            f"flash record source contains no matching success event with matching timestamp/seq "
            f"for device {flash_dev} and image {img} on or before run start"
        )
        return "unverified", rec, notes

    if len(matching_events) > 1:
        notes.append("flash record source contains ambiguous duplicate matching success events")
        return "unverified", rec, notes

    r_match = matching_events[0]
    match_idx = sorted_records.index(r_match)

    # 5. Full run-window lifecycle replay: from r_match forward to run_ended (or run_started)
    eval_window_end = _parse_iso8601(run_ended) if run_ended else (_parse_iso8601(run_started) if run_started else None)

    for ev in sorted_records[match_idx + 1:]:
        ev_ts_str = ev.get("timestamp")
        ev_ts = _parse_iso8601(ev_ts_str) if isinstance(ev_ts_str, str) else None

        # Check if strictly after evaluation window (post-run events do not invalidate past run facts)
        if eval_window_end is not None and ev_ts is not None and ev_ts > eval_window_end:
            continue

        kind, img_norm, v_val, diag = evaluate_flash_event(ev)
        if kind == "invalid":
            notes.append(
                f"flash lifecycle record missing status or non-string status before or during run: {diag}"
            )
            return "unverified", rec, notes
        elif kind in ("failed", "aborted", "erased", "partial", "unknown"):
            notes.append(
                f"flash lifecycle replay indicates image superseded, erased, or invalidated before or during run "
                f"({diag}, event_t={ev_ts_str})"
            )
            return "unverified", rec, notes
        elif kind == "unverified_success":
            notes.append(
                f"flash lifecycle record indicates subsequent flash was not verify-ok "
                f"({diag}, event_t={ev_ts_str})"
            )
            return "unverified", rec, notes
        elif kind == "unrecognized":
            notes.append(
                f"flash lifecycle record has unrecognized status before or during run: {diag}"
            )
            return "unverified", rec, notes
        elif kind == "success":
            if img_norm != img:
                notes.append(
                    f"flash lifecycle replay indicates image superseded by different image before or during run"
                )
                return "unverified", rec, notes
            # Valid reflash of the same image with verify=ok; remains verified

    return img, rec, notes
