#!/usr/bin/env python3
"""Pure functional evaluation engine for G2 hardware verification (G2-HW-R3 & G2-HW-R4).

Completely decoupled from serial I/O and real hardware devices:
- Power cut cycle evaluation: judge_power_cut_cycle
- USB unplug cycle evaluation: judge_usb_unplug_cycle
- Backpressure telemetry progression: judge_backpressure
- Human observation telemetry phases: judge_human_observation
- Exact protocol data comparison without lossy conversions
"""

from __future__ import annotations

import hashlib
import json
import math
from typing import Any


R60_REQUIRED_CONFIG_KEYS = {
    "install.x_cm", "install.y_cm", "install.z_cm",
    "install.yaw_deg", "install.pitch_deg", "install.roll_deg",
    "geometry.boundary_cm", "areas.definitions"
}
REQUIRED_CONFIG_KEYS = R60_REQUIRED_CONFIG_KEYS


def rotation_matrix(yaw_deg: float, pitch_deg: float, roll_deg: float) -> list[list[float]]:
    D = math.pi / 180.0
    y = yaw_deg * D
    p = pitch_deg * D
    r = roll_deg * D
    sy = math.sin(y)
    cy = math.cos(y)
    sp = math.sin(p)
    cp = math.cos(p)
    sr = math.sin(r)
    cr = math.cos(r)
    return [
        [cy * cr + sy * sp * sr, sy * cp, -cy * sr + sy * sp * cr],
        [-sy * cr + cy * sp * sr, cy * cp, sy * sr + cy * sp * cr],
        [cp * sr, -sp, cp * cr],
    ]


def expected_room_coords(lx: float, ly: float, lz: float, cal: dict) -> list[float]:
    rx = cal.get("install.x_cm", 0.0)
    ry = cal.get("install.y_cm", 0.0)
    rz = cal.get("install.z_cm", 0.0)
    yaw = cal.get("install.yaw_deg", 0.0)
    pitch = cal.get("install.pitch_deg", 0.0)
    roll = cal.get("install.roll_deg", 0.0)
    R = rotation_matrix(yaw, pitch, roll)
    wx = R[0][0] * lx + R[0][1] * ly + R[0][2] * lz
    wy = R[1][0] * lx + R[1][1] * ly + R[1][2] * lz
    wz = R[2][0] * lx + R[2][1] * ly + R[2][2] * lz
    return [rx + wx, ry + wy, rz - wz]


NUMERIC_RANGES = {
    "install.x_cm": (-2000.0, 2000.0),
    "install.y_cm": (-2000.0, 2000.0),
    "install.z_cm": (50.0, 600.0),
    "install.yaw_deg": (-180.0, 180.0),
    "install.pitch_deg": (-90.0, 90.0),
    "install.roll_deg": (-90.0, 90.0),
}

NUMERIC_STEPS = {
    "install.x_cm": 1.0,
    "install.y_cm": 1.0,
    "install.z_cm": 1.0,
    "install.yaw_deg": 0.1,
    "install.pitch_deg": 0.5,
    "install.roll_deg": 0.5,
}


def _is_finite_num(v: Any) -> bool:
    return not isinstance(v, bool) and isinstance(v, (int, float)) and math.isfinite(v)


def _on_step(val: float, step: float) -> bool:
    if not math.isfinite(val) or step <= 0:
        return False
    q = val / step
    return abs(q - round(q)) <= 1e-4


def _orient(ax: float, ay: float, bx: float, by: float, cx: float, cy: float) -> float:
    return (bx - ax) * (cy - ay) - (by - ay) * (cx - ax)


def _on_segment(ax: float, ay: float, bx: float, by: float, px: float, py: float) -> bool:
    return (
        min(ax, bx) - 1e-6 <= px <= max(ax, bx) + 1e-6
        and min(ay, by) - 1e-6 <= py <= max(ay, by) + 1e-6
    )


def _segments_intersect(
    a1: tuple[float, float], a2: tuple[float, float],
    b1: tuple[float, float], b2: tuple[float, float],
) -> bool:
    o1 = _orient(a1[0], a1[1], a2[0], a2[1], b1[0], b1[1])
    o2 = _orient(a1[0], a1[1], a2[0], a2[1], b2[0], b2[1])
    o3 = _orient(b1[0], b1[1], b2[0], b2[1], a1[0], a1[1])
    o4 = _orient(b1[0], b1[1], b2[0], b2[1], a2[0], a2[1])
    if (o1 > 1e-6 and o2 < -1e-6 or o1 < -1e-6 and o2 > 1e-6) and (
        o3 > 1e-6 and o4 < -1e-6 or o3 < -1e-6 and o4 > 1e-6
    ):
        return True
    if abs(o1) <= 1e-6 and _on_segment(a1[0], a1[1], a2[0], a2[1], b1[0], b1[1]):
        return True
    if abs(o2) <= 1e-6 and _on_segment(a1[0], a1[1], a2[0], a2[1], b2[0], b2[1]):
        return True
    if abs(o3) <= 1e-6 and _on_segment(b1[0], b1[1], b2[0], b2[1], a1[0], a1[1]):
        return True
    if abs(o4) <= 1e-6 and _on_segment(b1[0], b1[1], b2[0], b2[1], a2[0], a2[1]):
        return True
    return False


def is_valid_polygon_points(pts: Any, min_points: int = 3, max_points: int = 64) -> bool:
    """Validate 2D polygon against firmware mwcp_service.cpp rules:
    - list of [x, y] pairs with min_points <= len <= max_points
    - finite coordinates in [-2000.0, 2000.0]
    - no zero-length edges
    - non-zero polygon area (abs(area2) > 1e-3)
    - no self-intersecting non-adjacent edges
    """
    if not isinstance(pts, list):
        return False
    n = len(pts)
    if not (min_points <= n <= max_points):
        return False
    coords: list[tuple[float, float]] = []
    for pt in pts:
        if not isinstance(pt, (list, tuple)) or len(pt) != 2:
            return False
        x, y = pt[0], pt[1]
        if not _is_finite_num(x) or not _is_finite_num(y):
            return False
        if x < -2000.0 or x > 2000.0 or y < -2000.0 or y > 2000.0:
            return False
        coords.append((float(x), float(y)))

    area2 = 0.0
    for i in range(n):
        j = (i + 1) % n
        if abs(coords[i][0] - coords[j][0]) < 1e-4 and abs(coords[i][1] - coords[j][1]) < 1e-4:
            return False
        area2 += coords[i][0] * coords[j][1] - coords[j][0] * coords[i][1]
    if abs(area2) <= 1e-3:
        return False

    for i in range(n):
        i2 = (i + 1) % n
        for j in range(i + 1, n):
            j2 = (j + 1) % n
            if i == j or i2 == j or j2 == i:
                continue
            if _segments_intersect(coords[i], coords[i2], coords[j], coords[j2]):
                return False
    return True


def point_in_polygon(x: float, y: float, poly: list[list[float]] | list[tuple[float, float]]) -> bool:
    """Ray-casting / boundary-inclusive point-in-polygon matching firmware point_in_polygon_."""
    n = len(poly)
    if n < 3:
        return False
    inside = False
    j = n - 1
    for i in range(n):
        xi, yi = float(poly[i][0]), float(poly[i][1])
        xj, yj = float(poly[j][0]), float(poly[j][1])
        if abs(_orient(xj, yj, xi, yi, x, y)) <= 1e-4 and _on_segment(xj, yj, xi, yi, x, y):
            return True
        if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi) + xi):
            inside = not inside
        j = i
    return inside


def is_valid_complete_config(cfg: Any) -> bool:
    """Validate that configuration has exact R60 keys with firmware-compliant types, steps, ranges, and geometry."""
    if not isinstance(cfg, dict):
        return False
    if set(cfg.keys()) != R60_REQUIRED_CONFIG_KEYS:
        return False
    for k, (low, high) in NUMERIC_RANGES.items():
        v = cfg.get(k)
        if not _is_finite_num(v):
            return False
        if v < low or v > high:
            return False
        step = NUMERIC_STEPS.get(k)
        if step is not None and not _on_step(float(v), step):
            return False

    # Validate geometry.boundary_cm: Either None or valid polygon with 3..64 vertices (empty list [] is invalid!)
    boundary = cfg.get("geometry.boundary_cm")
    if boundary is not None:
        if not is_valid_polygon_points(boundary, min_points=3, max_points=64):
            return False

    # Validate areas.definitions
    areas = cfg.get("areas.definitions")
    if not isinstance(areas, list):
        return False
    if len(areas) > 3:
        return False
    seen_slots: set[int] = set()
    for item in areas:
        if not isinstance(item, dict):
            return False
        if set(item.keys()) != {"slot", "enabled", "name", "points_cm"}:
            return False
        slot = item.get("slot")
        if isinstance(slot, bool) or not isinstance(slot, int) or not (0 <= slot <= 2):
            return False
        if slot in seen_slots:
            return False
        seen_slots.add(slot)
        enabled = item.get("enabled")
        if not isinstance(enabled, bool):
            return False
        name = item.get("name")
        if not isinstance(name, str) or len(name.encode("utf-8")) > 32:
            return False
        if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in name):
            return False
        pts = item.get("points_cm")
        if not isinstance(pts, list):
            return False
        if enabled:
            if not is_valid_polygon_points(pts, min_points=3, max_points=12):
                return False
        else:
            if len(pts) != 0 and not is_valid_polygon_points(pts, min_points=3, max_points=12):
                return False

    return True


def is_valid_revision_string(rev: Any) -> bool:
    """Validate that revision is a non-empty ASCII decimal digits string <= 20 UTF-8 bytes."""
    if not isinstance(rev, str):
        return False
    if not rev:
        return False
    b = rev.encode("utf-8")
    if len(b) > 20:
        return False
    return all("0" <= ch <= "9" for ch in rev)


def configs_strictly_equal(c1: Any, c2: Any) -> bool:
    """Compare two configs or values strictly respecting protocol types.
    
    Booleans (bool) are NOT equal to integers (int), floats are NOT rounded.
    JSON numerical equality allows int and float of exact same value (e.g. 105 == 105.0).
    """
    if isinstance(c1, bool) or isinstance(c2, bool):
        if type(c1) is not type(c2):
            return False
        return c1 == c2
    if isinstance(c1, (int, float)) and isinstance(c2, (int, float)):
        return c1 == c2
    if type(c1) is not type(c2):
        return False
    if isinstance(c1, dict):
        if set(c1.keys()) != set(c2.keys()):
            return False
        return all(configs_strictly_equal(c1[k], c2[k]) for k in c1)
    if isinstance(c1, list):
        if len(c1) != len(c2):
            return False
        return all(configs_strictly_equal(x, y) for x, y in zip(c1, c2))
    return c1 == c2


def canonical_config_hash(cfg: dict) -> str:
    """Deterministic hash of config preserving types."""
    raw = json.dumps(cfg, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


# ==============================================================================
# G2-HW-R3: Physical Power Cut Cycle Judgment
# ==============================================================================

def judge_power_cut_cycle(record: dict) -> tuple[str, bool, str]:
    """Pure evaluation of one physical power cut attempt."""
    target_port = record.get("target_port")
    port = record.get("port")
    if target_port and port and str(port).upper() != str(target_port).upper():
        return "PORT_MISMATCH", False, f"Port mismatch: expected {target_port}, got {port}"

    # 1. Physical disconnect & reconnect confirmation (must be strict boolean True)
    disc = record.get("disconnect_observed")
    if not isinstance(disc, bool):
        return "INVALID_TYPE_REJECTED", False, f"disconnect_observed must be a boolean bool, got {type(disc).__name__}"
    if not disc:
        return "NO_DISCONNECT_REJECTED", False, "No physical disconnect/port disappearance observed"

    rec = record.get("reconnect_observed")
    if not isinstance(rec, bool):
        return "INVALID_TYPE_REJECTED", False, f"reconnect_observed must be a boolean bool, got {type(rec).__name__}"
    if not rec:
        return "NO_RECONNECT_REJECTED", False, "No re-enumeration/reconnect observed"

    # 2. Device identity check (must be non-empty strings and equal)
    dev_before = record.get("device_id_before")
    dev_after = record.get("device_id_after")
    if not dev_before or not dev_after or not isinstance(dev_before, str) or not isinstance(dev_after, str):
        return "MISSING_IDENTITY_REJECTED", False, "device_id_before and device_id_after must be non-empty strings"
    if dev_before != dev_after:
        return "IDENTITY_MISMATCH", False, f"Device identity changed: {dev_before} -> {dev_after}"

    # 3. Revision checks (cannot be missing / None)
    rev_before_raw = record.get("rev_before")
    rev_target_raw = record.get("rev_target")
    rev_recovered_raw = record.get("rev_recovered")
    if rev_before_raw is None or rev_target_raw is None or rev_recovered_raw is None:
        return "MISSING_REVISION_REJECTED", False, "Revisions cannot be missing"
    if not is_valid_revision_string(rev_before_raw) or not is_valid_revision_string(rev_target_raw) or not is_valid_revision_string(rev_recovered_raw):
        return "INVALID_REVISION_FORMAT", False, f"Revisions must be decimal strings: before={rev_before_raw!r}, target={rev_target_raw!r}, recovered={rev_recovered_raw!r}"

    rev_before = rev_before_raw
    rev_target = rev_target_raw
    rev_recovered = rev_recovered_raw

    # 4. Hardware reboot confirmation
    boot_before = record.get("boot_before")
    boot_after = record.get("boot_after")
    if not boot_before or not boot_after or boot_before == boot_after:
        return "NO_REBOOT_REJECTED", False, f"Boot ID unchanged or missing ({boot_before} == {boot_after})"

    # 5. Target must differ from before (cannot count identity no-op as atomic switch)
    cfg_before = record.get("config_before")
    cfg_target = record.get("config_target")
    cfg_recovered = record.get("config_recovered")

    if not isinstance(cfg_before, dict) or not isinstance(cfg_target, dict) or not isinstance(cfg_recovered, dict):
        return "CONFIG_MISSING", False, "Configuration snapshots missing or invalid type"
    if len(cfg_before) == 0 or len(cfg_target) == 0 or len(cfg_recovered) == 0:
        return "CONFIG_EMPTY_REJECTED", False, "Configuration snapshots must not be empty"
    if not (is_valid_complete_config(cfg_before) and is_valid_complete_config(cfg_target) and is_valid_complete_config(cfg_recovered)):
        return "INCOMPLETE_CONFIG_REJECTED", False, "Configuration snapshots missing or invalid required protocol fields"

    if configs_strictly_equal(cfg_before, cfg_target):
        return "IDENTICAL_TARGET_REJECTED", False, "Target configuration is identical to before (not an atomic mutation)"

    # 6. Check request op_id
    req_op_id = record.get("op_id")
    if not req_op_id or not isinstance(req_op_id, str):
        return "MISSING_REQUEST_OP_ID_REJECTED", False, "Cycle record missing required request op_id"

    # 7. Check commit_response ACK revision and op_id if ACK was received
    commit_res = record.get("commit_response")
    if isinstance(commit_res, dict) and commit_res.get("ok") is True:
        ack_res = commit_res.get("result")
        if not isinstance(ack_res, dict):
            return "INVALID_ACK_STRUCTURE_REJECTED", False, "CONFIG_COMMIT ACK result is not a dictionary"
        for req_field in ("op_id", "revision", "persisted", "restart_required"):
            if req_field not in ack_res:
                return "INVALID_ACK_STRUCTURE_REJECTED", False, f"CONFIG_COMMIT ACK missing required field '{req_field}'"
        if not isinstance(ack_res.get("persisted"), bool) or not isinstance(ack_res.get("restart_required"), bool):
            return "INVALID_ACK_STRUCTURE_REJECTED", False, "CONFIG_COMMIT ACK boolean fields have invalid types"
        ack_op_id = ack_res.get("op_id")
        if ack_op_id != req_op_id:
            return "OP_ID_MISMATCH_REJECTED", False, f"CONFIG_COMMIT ACK op_id mismatch: {ack_op_id} != {req_op_id}"
        ack_rev = ack_res.get("revision")
        if not is_valid_revision_string(ack_rev):
            return "INVALID_REVISION_FORMAT", False, f"CONFIG_COMMIT ACK revision is not valid decimal ASCII string: {ack_rev}"
        if str(ack_rev) != rev_target:
            return "ACK_REVISION_MISMATCH_REJECTED", False, f"CONFIG_COMMIT ACK revision {ack_rev} does not match rev_target {rev_target}"

    is_old = configs_strictly_equal(cfg_recovered, cfg_before)
    is_new = configs_strictly_equal(cfg_recovered, cfg_target)

    persisted_ack = isinstance(commit_res, dict) and commit_res.get("ok") is True and commit_res.get("result", {}).get("persisted") is True

    # 8. If COMMIT already acknowledged persisted=true, falling back to old state is a DATA LOSS FAILURE!
    if persisted_ack:
        if is_old:
            return "PERSISTENCE_LOST_FAIL", False, (
                f"CONFIG_COMMIT confirmed persisted=True (rev {rev_target}), "
                f"but reboot reverted to old config: persistence violation!"
            )
        if not is_new:
            return "CORRUPTED_FAIL", False, "Recovered config is neither clean old nor clean new snapshot"
        if rev_recovered != rev_target:
            return "REVISION_MISMATCH_FAIL", False, f"Recovered new config but revision mismatch ({rev_recovered} != {rev_target})"
        return "COMMITTED_NEW_SAFE", True, f"Cut power after write completed; clean target config intact (rev {rev_recovered})"

    # 9. Interrupted before / during write (commit not acknowledged as persisted)
    if is_old:
        if rev_recovered != rev_before:
            return "REVISION_MISMATCH_FAIL", False, f"Old config retained but revision changed ({rev_recovered} != {rev_before})"
        return "REVERTED_OLD_SAFE", True, f"Cut power before/during atomic commit; clean old config preserved (rev {rev_before})"

    if is_new:
        if rev_recovered != rev_target:
            return "REVISION_MISMATCH_FAIL", False, f"New config applied but revision mismatch ({rev_recovered} != {rev_target})"
        return "COMMITTED_NEW_SAFE", True, f"Cut power after write completed; clean target config intact (rev {rev_recovered})"

    return "CORRUPTED_FAIL", False, "Recovered configuration contains mixed, corrupted or partial fields"


def judge_power_cut_suite(cycles: list[dict], required_rounds: int = 20) -> dict:
    """Evaluate an entire suite of power cut cycles."""
    if required_rounds <= 0:
        return {
            "status": "fail",
            "reason": f"Invalid required_rounds: {required_rounds} (must be >= 1)",
            "rounds_passed": 0,
            "rounds_total": len(cycles),
            "history": []
        }
    if len(cycles) < required_rounds:
        return {
            "status": "fail",
            "reason": f"Insufficient rounds completed: {len(cycles)}/{required_rounds}",
            "rounds_passed": 0,
            "rounds_total": len(cycles),
            "history": []
        }
    cycle_nums = [c.get("cycle") for c in cycles]
    if len(set(cycle_nums)) != len(cycle_nums):
        return {
            "status": "fail",
            "reason": f"Duplicate cycle numbers detected in suite: {cycle_nums}",
            "rounds_passed": 0,
            "rounds_total": len(cycles),
            "history": []
        }
    passed_count = 0
    history = []
    for c in cycles:
        v, p, d = judge_power_cut_cycle(c)
        history.append({"cycle": c.get("cycle"), "verdict": v, "passed": p, "detail": d})
        if p:
            passed_count += 1
    all_ok = (passed_count == len(cycles) == required_rounds)
    return {
        "status": "pass" if all_ok else "fail",
        "rounds_passed": passed_count,
        "rounds_total": len(cycles),
        "history": history
    }


# ==============================================================================
# G2-HW-R3: Physical USB Unplug / Re-enumeration Judgment
# ==============================================================================

def judge_usb_unplug_cycle(record: dict) -> tuple[str, bool, str]:
    """Pure evaluation of one physical USB unplug/replug attempt."""
    target_port = record.get("target_port")
    port = record.get("port")
    if target_port and port and str(port).upper() != str(target_port).upper():
        return "PORT_MISMATCH", False, f"Port mismatch: expected {target_port}, got {port}"

    disc = record.get("disconnect_observed")
    if not isinstance(disc, bool):
        return "INVALID_TYPE_REJECTED", False, f"disconnect_observed must be a boolean bool, got {type(disc).__name__}"
    if not disc:
        return "NO_DISCONNECT_REJECTED", False, "No physical USB disconnection observed by host"

    rec = record.get("reconnect_observed")
    if not isinstance(rec, bool):
        return "INVALID_TYPE_REJECTED", False, f"reconnect_observed must be a boolean bool, got {type(rec).__name__}"
    if not rec:
        return "NO_RECONNECT_FAIL", False, "Port did not re-enumerate after replug"

    dev_before = record.get("device_id_before")
    dev_after = record.get("device_id_after")
    if not dev_before or not dev_after or not isinstance(dev_before, str) or not isinstance(dev_after, str):
        return "INCOMPLETE_INPUT_REJECTED", False, "device_id_before and device_id_after must be non-empty strings"
    if dev_before != dev_after:
        return "IDENTITY_MISMATCH", False, f"Device identity mismatch across unplug: {dev_before} != {dev_after}"

    boot_before = record.get("boot_before")
    boot_after = record.get("boot_after")
    if not boot_before or not boot_after or boot_before == boot_after:
        return "NO_REBOOT_REJECTED", False, f"Boot ID unchanged across USB unplug: {boot_before}"

    ping = record.get("ping_after")
    if not isinstance(ping, dict) or ping.get("uptime_ms") is None or ping.get("uptime_ms") < 0:
        return "PING_FAILED", False, f"PING check failed after re-enumeration: {ping}"

    rev_before = record.get("rev_before")
    rev_after = record.get("rev_after")
    if rev_before is None or rev_after is None or not isinstance(rev_before, str) or not isinstance(rev_after, str):
        return "INCOMPLETE_INPUT_REJECTED", False, "rev_before and rev_after must be non-empty strings"
    if not is_valid_revision_string(rev_before) or not is_valid_revision_string(rev_after):
        return "INVALID_REVISION_FORMAT", False, f"rev_before and rev_after must be decimal strings: {rev_before!r}, {rev_after!r}"
    if rev_before != rev_after:
        return "REVISION_MUTATED_FAIL", False, f"Config revision changed across unplug ({rev_before} != {rev_after})"

    cfg_before = record.get("config_before")
    cfg_after = record.get("config_after")
    if not isinstance(cfg_before, dict) or not isinstance(cfg_after, dict):
        return "INCOMPLETE_INPUT_REJECTED", False, "Configuration snapshots missing or invalid type"
    if len(cfg_before) == 0 or len(cfg_after) == 0:
        return "INCOMPLETE_INPUT_REJECTED", False, "Configuration snapshots must not be empty"

    # Strict full configuration equality (no len(cfg) >= 8 heuristic)
    if not configs_strictly_equal(cfg_before, cfg_after):
        return "CONFIG_MUTATED_FAIL", False, "Configuration changed after USB unplug/replug!"

    if not (is_valid_complete_config(cfg_before) and is_valid_complete_config(cfg_after)):
        return "INCOMPLETE_CONFIG_REJECTED", False, "Configuration snapshots missing or invalid required protocol fields"

    return "UNPLUG_RECOVERED_SAFE", True, f"Clean re-enumeration and full configuration intact (rev {rev_after})"


def judge_usb_unplug_suite(cycles: list[dict], required_rounds: int = 5) -> dict:
    if required_rounds <= 0:
        return {
            "status": "fail",
            "reason": f"Invalid required_rounds: {required_rounds} (must be >= 1)",
            "rounds_passed": 0,
            "rounds_total": len(cycles),
            "history": []
        }
    if len(cycles) < required_rounds:
        return {
            "status": "fail",
            "reason": f"Insufficient rounds completed: {len(cycles)}/{required_rounds}",
            "rounds_passed": 0,
            "rounds_total": len(cycles),
            "history": []
        }
    cycle_nums = [c.get("cycle") for c in cycles]
    if len(set(cycle_nums)) != len(cycle_nums):
        return {
            "status": "fail",
            "reason": f"Duplicate cycle numbers detected in suite: {cycle_nums}",
            "rounds_passed": 0,
            "rounds_total": len(cycles),
            "history": []
        }
    passed_count = 0
    history = []
    for c in cycles:
        v, p, d = judge_usb_unplug_cycle(c)
        history.append({"cycle": c.get("cycle"), "verdict": v, "passed": p, "detail": d})
        if p:
            passed_count += 1
    all_ok = (passed_count == len(cycles) == required_rounds)
    return {
        "status": "pass" if all_ok else "fail",
        "rounds_passed": passed_count,
        "rounds_total": len(cycles),
        "history": history
    }


# ==============================================================================
# G2-HW-R4: Backpressure Telemetry Progression Judgment
# ==============================================================================

def judge_backpressure(base_status: dict, after_status: dict, rpc_result: dict,
                       boot_before: str, boot_after: str) -> tuple[bool, list[dict]]:
    """Pure evaluation of backpressure test.

    Fail-closed input contract (G2-HW-R2 R4-A): missing/non-finite fields
    never crash and never pass — a value that is not a finite number is
    treated as missing, and a missing uptime/counters snapshot fails the
    corresponding check.  Uptime semantics: only a strictly increasing
    monotonic uptime inside ONE boot is provable; a decreased or reset
    uptime indicates a reboot/stale snapshot and fails (no wraparound is
    assumed without independent evidence)."""
    checks = []

    def _finite(v) -> bool:
        return (not isinstance(v, bool) and isinstance(v, (int, float))
                and math.isfinite(v))

    # 1. Boot stability
    boot_ok = bool(boot_before and boot_after and boot_before == boot_after)
    checks.append({
        "name": "no_reboot_during_backpressure",
        "pass": boot_ok,
        "detail": f"boot_before={boot_before}, boot_after={boot_after}"
    })

    # 2. RPC response
    rpc_ok = isinstance(rpc_result, dict) and rpc_result.get("ok") is True
    checks.append({
        "name": "rpc_after_backpressure",
        "pass": rpc_ok,
        "detail": str(rpc_result)
    })

    # 3. Uptime progression (missing/None/non-finite -> fail, never crash)
    u_base = base_status.get("uptime_ms") if isinstance(base_status, dict) else None
    u_after = after_status.get("uptime_ms") if isinstance(after_status, dict) else None
    uptime_ok = _finite(u_base) and _finite(u_after) and u_after > u_base
    checks.append({
        "name": "uptime_advanced",
        "pass": uptime_ok,
        "detail": f"{u_base} -> {u_after}"
        + ("" if _finite(u_base) and _finite(u_after) else
           " (missing or non-finite uptime snapshot: fail-closed)")
    })

    # 4. Radar continuous sampling progression (G2-HW-R4 fix)
    cnt_base = (base_status.get("counters", {}) or {}) if isinstance(base_status, dict) else {}
    cnt_after = (after_status.get("counters", {}) or {}) if isinstance(after_status, dict) else {}
    rf_base = cnt_base.get("radar_frames", 0)
    rf_after = cnt_after.get("radar_frames", 0)
    if not _finite(rf_base) or not _finite(rf_after):
        # counters snapshot incomplete: frame progression is unverifiable
        # through counters (fall through to the timestamp leg only)
        rf_base = rf_after = None

    t_base = base_status.get("last_radar_frame_ms") if isinstance(base_status, dict) else None
    t_after = after_status.get("last_radar_frame_ms") if isinstance(after_status, dict) else None
    link_after = after_status.get("radar_link") if isinstance(after_status, dict) else None

    counters_advanced = (rf_base is not None and rf_after is not None
                         and rf_after > rf_base)
    time_advanced = (_finite(t_base) and _finite(t_after) and t_after > t_base)
    frame_advancement = counters_advanced or time_advanced
    # Stale or zero frames is strictly invalid; a counters snapshot missing
    # BOTH legs of evidence (no counters delta AND no advancing frame
    # timestamp) is fail-closed.
    radar_alive = frame_advancement and (link_after in ("healthy", "waiting")) and (
        (rf_after or 0) > 0 or t_after is not None)
    checks.append({
        "name": "radar_alive_after_backpressure",
        "pass": bool(radar_alive),
        "detail": f"frames: {rf_base} -> {rf_after}, last_frame_ms: {t_base} -> {t_after}, link={link_after}"
        + ("" if (counters_advanced or time_advanced) else
           "; no provable new-sample progress (counters and frame timestamp) - fail-closed")
    })

    overall_pass = all(c["pass"] for c in checks)
    return overall_pass, checks


# ==============================================================================
# G2-HW-R4 / R6-01: Human Observation Telemetry Phase Judgment
# ==============================================================================

def _sent_timestamp_ms(frame: dict) -> float | None:
    """Transport (frame emission) timestamp only (R8-01A).

    Production MWCP telemetry carries the device send time in top-level
    ``sent_ms``; legacy fixtures used a top-level ``sample_ms``.  This value is
    used ONLY to order frames and to bind them to phase windows.  It is never a
    substitute for ``presence.sample_ms`` or ``targets[].position_ms``
    freshness.
    """
    if not isinstance(frame, dict):
        return None
    for k in ("sent_ms", "sample_ms"):
        v = frame.get(k)
        if _is_finite_num(v):
            return float(v)
    return None


# Backwards-compatible name: now strictly the transport timestamp, with NO
# fallback to presence.sample_ms (R8-01A: field-specific sampling semantics).
_frame_timestamp_ms = _sent_timestamp_ms


def _presence_sample_ms(frame: dict) -> tuple[str, float | None]:
    """Return (status, presence.sample_ms) for a frame's presence observation.

    status: 'not_valid' (presence missing/unknown quality -> not an
    observation), 'ok', 'missing' (valid presence without a finite,
    non-negative presence.sample_ms).  Never falls back to sent_ms/source_seq.
    """
    if not isinstance(frame, dict):
        return "not_valid", None
    p = frame.get("presence")
    if not isinstance(p, dict) or p.get("quality") != "valid":
        return "not_valid", None
    v = p.get("sample_ms")
    if not _is_finite_num(v) or float(v) < 0:
        return "missing", None
    return "ok", float(v)


def _diag_local_z_for_target(frame: dict, target: dict) -> float | None:
    """Return co-sampled diagnostics.local_z for a 2D target, else None (R8-01B).

    Production publishes ``metrics["diagnostics.local_z"] = {value, quality,
    sample_ms=position_ms}``.  It is usable only when valid, finite and sampled
    at exactly the target's ``position_ms``.
    """
    metrics = frame.get("metrics") if isinstance(frame, dict) else None
    if not isinstance(metrics, dict):
        return None
    dz = metrics.get("diagnostics.local_z")
    if not isinstance(dz, dict) or dz.get("quality") != "valid":
        return None
    if not _is_finite_num(dz.get("value")) or not _is_finite_num(dz.get("sample_ms")):
        return None
    pms = target.get("position_ms")
    if not _is_finite_num(pms) or abs(float(dz["sample_ms"]) - float(pms)) > 1e-6:
        return None
    return float(dz["value"])


def _validate_tracker_mapping(live_phase_tracker: dict, telemetry_records: list,
                              frame_ts: list, req_names: tuple) -> str | None:
    """R9-01 (R13): validate the live tracker's index<->seq mapping contract.

    Collector contract (human_observe_runner.live_phase_tracker): for each
    guided phase, ``frame_indices`` are the arrival positions in THIS run's
    telemetry and ``source_seqs`` the payload source_seq of exactly those
    frames - a 1:1 positional mapping (``telemetry_records[frame_indices[k]]
    ["source_seq"] == source_seqs[k]``).  device_start_ms/device_end_ms, when
    both finite, are the min/max device timestamps of the mapped frames.

    Every claim must be explainable by THIS telemetry:
      - containers must be lists; entries must be true integers (bool is an
        int subclass in Python and is rejected explicitly);
      - same length for indices and seqs; no repeated index within a phase;
      - every index inside [0, len(telemetry_records));
      - every mapped frame's own source_seq equals the claimed seq;
      - a frame index belongs to exactly one phase (no cross-phase overlap);
      - the device time envelope covers the mapped frames' timestamps.
    Any violation returns a precise reason (the caller rejects with
    PHASE_TRACKER_MALFORMED_REJECTED); invalid entries are never silently
    dropped so a claim can pass.  Repeated source_seq VALUES are not
    rejected here - sampling rules govern them elsewhere; only the mapping
    identity is checked.  Returns None when the tracker is consistent."""
    try:
        for name in req_names:
            tr = live_phase_tracker.get(name)
            if tr is None:
                continue  # absence is the capture check's business
            if not isinstance(tr, dict):
                return f"phase '{name}' tracker entry is not an object ({type(tr).__name__})"
            frames = tr.get("frame_indices")
            seqs = tr.get("source_seqs")
            if frames is None and seqs is None:
                continue
            if not isinstance(frames, list) or not isinstance(seqs, list):
                return (f"phase '{name}' frame_indices/source_seqs must be lists "
                        f"(got {type(frames).__name__}/{type(seqs).__name__})")
            if len(frames) != len(seqs):
                return (f"phase '{name}' frame_indices ({len(frames)}) and source_seqs "
                        f"({len(seqs)}) lengths differ - index/seq mapping is inconsistent")
            for x in list(frames) + list(seqs):
                if isinstance(x, bool) or not isinstance(x, int):
                    return (f"phase '{name}' tracker entry {x!r} is not an integer "
                            f"({type(x).__name__})")
            for idx in frames:
                if not 0 <= idx < len(telemetry_records):
                    return (f"phase '{name}' frame index {idx} does not exist in this "
                            f"run's telemetry ({len(telemetry_records)} frames)")
            if len(set(frames)) != len(frames):
                return f"phase '{name}' tracker repeats a frame index"
            for idx, sq in zip(frames, seqs):
                rec = telemetry_records[idx]
                if not isinstance(rec, dict) or not _is_finite_num(rec.get("source_seq")):
                    return f"phase '{name}' mapped frame {idx} has no usable source_seq"
                if float(rec["source_seq"]) != float(sq):
                    return (f"phase '{name}' frame index {idx} carries source_seq "
                            f"{rec['source_seq']!r} but the tracker claims {sq!r}")
            ds, de = tr.get("device_start_ms"), tr.get("device_end_ms")
            if _is_finite_num(ds) and _is_finite_num(de) and frames:
                ts = [frame_ts[i] for i in frames
                      if 0 <= i < len(frame_ts) and frame_ts[i] is not None]
                if ts and (min(ts) < float(ds) - 1e-6 or max(ts) > float(de) + 1e-6):
                    return (f"phase '{name}' device time envelope [{ds}, {de}] does not "
                            f"cover its mapped frames (timestamps span "
                            f"[{min(ts)}, {max(ts)}])")
        seen: dict[int, str] = {}
        for name in req_names:
            tr = live_phase_tracker.get(name)
            frames = tr.get("frame_indices") if isinstance(tr, dict) else None
            if not isinstance(frames, list):
                continue
            for idx in frames:
                if isinstance(idx, bool) or not isinstance(idx, int):
                    continue  # already reported above
                if idx in seen:
                    return (f"frame index {idx} is attributed to both '{seen[idx]}' and "
                            f"'{name}' - a captured frame belongs to exactly one phase")
                seen[idx] = name
        return None
    except (TypeError, ValueError, KeyError, IndexError, OverflowError) as err:
        return f"tracker mapping is not evaluable as evidence: {err!r}"


def _validate_structured_phases(
    phases: Any,
    t_first: float,
    t_last: float,
    t_exit_start: float,
    telemetry_records: list[dict] | None = None,
    frame_ts: list[float] | None = None,
    minimum_still_duration_ms: float = 2000.0,
    minimum_exit_duration_ms: float = 10000.0,
    expected_boot_id: str | None = None,
    expected_device_id: str | None = None,
    expected_run_id: str | None = None,
    presence_ts: list[float | None] | None = None,
    presence_hold: bool = False,
    expected_attempt_id: str | None = None,
    expected_session_id: Any = None,
    live_phase_tracker: dict | None = None,
) -> tuple[bool, str, dict]:
    """Validate structured phase confirmation record and phase-bound telemetry for entry, still, and exit."""
    if not isinstance(phases, dict):
        return False, "MISSING_STRUCTURED_PHASES_REJECTED", {
            "detail": "Structured phase confirmations (entry, still, exit) are required; single boolean flag is insufficient"
        }
    if expected_attempt_id and phases.get("attempt_id") is not None and str(phases.get("attempt_id")) != str(expected_attempt_id):
        return False, "FOREIGN_PHASE_CONFIRMATION_REJECTED", {
            "detail": f"Phase confirmation attempt_id {phases.get('attempt_id')!r} != {expected_attempt_id!r}"
        }
    if expected_device_id and phases.get("device_id") and str(phases.get("device_id")) != str(expected_device_id):
        return False, "FOREIGN_PHASE_CONFIRMATION_REJECTED", {
            "detail": f"Phase confirmation device_id {phases.get('device_id')!r} != {expected_device_id!r}"
        }
    if expected_boot_id and phases.get("boot_id") and str(phases.get("boot_id")) != str(expected_boot_id):
        return False, "FOREIGN_PHASE_CONFIRMATION_REJECTED", {
            "detail": f"Phase confirmation boot_id {phases.get('boot_id')!r} != {expected_boot_id!r}"
        }
    if expected_run_id and phases.get("run_id") and str(phases.get("run_id")) != str(expected_run_id):
        return False, "FOREIGN_PHASE_CONFIRMATION_REJECTED", {
            "detail": f"Phase confirmation run_id {phases.get('run_id')!r} != {expected_run_id!r}"
        }

    req_names = ("entry", "still", "exit")
    parsed: dict[str, dict] = {}
    prev_end: float | None = None
    capture_is_epoch = (t_last > 1e11)
    for name in req_names:
        ph = phases.get(name)
        if not isinstance(ph, dict):
            return False, "MISSING_STRUCTURED_PHASES_REJECTED", {
                "detail": f"Missing structured phase record for '{name}'"
            }
        if ph.get("confirmed") is not True:
            return False, "UNCONFIRMED_PHASE_REJECTED", {
                "detail": f"Phase '{name}' was not explicitly confirmed (confirmed={ph.get('confirmed')!r})"
            }
        if expected_device_id and ph.get("device_id") and str(ph.get("device_id")) != str(expected_device_id):
            return False, "FOREIGN_PHASE_CONFIRMATION_REJECTED", {
                "detail": f"Phase '{name}' device_id {ph.get('device_id')!r} != {expected_device_id!r}"
            }
        if expected_run_id and ph.get("run_id") and str(ph.get("run_id")) != str(expected_run_id):
            return False, "FOREIGN_PHASE_CONFIRMATION_REJECTED", {
                "detail": f"Phase '{name}' run_id {ph.get('run_id')!r} != {expected_run_id!r}"
            }
        if expected_boot_id and ph.get("boot_id") and str(ph.get("boot_id")) != str(expected_boot_id):
            return False, "BOOT_CHANGED_REJECTED", {
                "detail": f"Phase '{name}' boot_id {ph.get('boot_id')!r} != {expected_boot_id!r}"
            }
        # R8-01A: live (runner-tracked) confirmations must be bound to THIS
        # attempt / device / boot / session.  Any record carrying a binding
        # field must match it exactly.
        is_live = ph.get("method") in ("hook", "interactive_prompt", "live")
        bindings = (
            ("attempt_id", expected_attempt_id),
            ("session_id", expected_session_id),
            ("boot_id", expected_boot_id),
            ("device_id", expected_device_id),
        )
        for bkey, bexp in bindings:
            if bexp is None or bexp == "":
                continue
            bval = ph.get(bkey)
            if bval is None:
                if is_live:
                    return False, "FOREIGN_PHASE_CONFIRMATION_REJECTED", {
                        "detail": f"Live phase '{name}' is missing binding field {bkey!r}"
                    }
                continue
            if str(bval) != str(bexp):
                return False, "FOREIGN_PHASE_CONFIRMATION_REJECTED", {
                    "detail": f"Phase '{name}' {bkey} {bval!r} != {bexp!r}"
                }
        s_ms = ph.get("start_ms")
        e_ms = ph.get("end_ms")
        c_ms = ph.get("confirmed_at_ms")
        if not (_is_finite_num(s_ms) and _is_finite_num(e_ms) and _is_finite_num(c_ms)):
            return False, "INVALID_PHASE_TIMESTAMPS_REJECTED", {
                "detail": f"Phase '{name}' missing finite start_ms/end_ms/confirmed_at_ms"
            }
        s_f, e_f, c_f = float(s_ms), float(e_ms), float(c_ms)
        if s_f < 0 or e_f <= s_f or c_f < e_f:
            return False, "INVALID_PHASE_TIMESTAMPS_REJECTED", {
                "detail": f"Phase '{name}' has zero/negative duration or out-of-order timestamps: start={s_f}, end={e_f}, confirmed_at={c_f}"
            }
        if prev_end is not None and s_f < prev_end:
            return False, "INVALID_PHASE_TIMESTAMPS_REJECTED", {
                "detail": f"Phase '{name}' start_ms ({s_f}) precedes previous phase end_ms ({prev_end})"
            }
        if (c_f > 1e11) != (e_f > 1e11) or (s_f > 1e11) != (e_f > 1e11):
            return False, "CLOCK_DOMAIN_MISMATCH_REJECTED", {
                "detail": f"Phase '{name}' mixes host epoch and device monotonic clock domains: start={s_f}, end={e_f}, confirmed_at={c_f}"
            }
        if (s_f > 1e11) != capture_is_epoch and not isinstance(phases.get("host_device_time_mapping"), dict):
            return False, "CLOCK_DOMAIN_MISMATCH_REJECTED", {
                "detail": f"Phase '{name}' clock domain does not match telemetry timestamps [{t_first}, {t_last}] and lacks host_device_time_mapping"
            }
        if s_f < t_first - 500.0 or e_f > t_last + 500.0:
            return False, "PHASE_WINDOW_OUTSIDE_CAPTURE_REJECTED", {
                "detail": f"Phase '{name}' window [{s_f}, {e_f}] lies outside telemetry capture window [{t_first}, {t_last}]"
            }
        prev_end = e_f
        parsed[name] = {
            "status": "pass",
            "confirmed": True,
            "start_ms": s_f,
            "end_ms": e_f,
            "confirmed_at_ms": c_f,
            "method": ph.get("method", "structured"),
        }
        if isinstance(ph.get("source_seqs"), list):
            parsed[name]["_source_seqs"] = list(ph.get("source_seqs"))

    if telemetry_records is not None and frame_ts is not None and len(telemetry_records) == len(frame_ts):
        # 0a. R9-01 residual: every confirmed phase must be traceable to the
        # runner's ACTUAL live phase tracker for this attempt - identity
        # fields alone do not prove the stage was executed.  The tracker is
        # the runner's own per-phase record of captured frames/source_seqs.
        if isinstance(live_phase_tracker, dict) and live_phase_tracker:
            seq_to_frame_ts: dict[float, float] = {}
            for r_i, ts_i in zip(telemetry_records, frame_ts):
                if isinstance(r_i, dict) and _is_finite_num(r_i.get("source_seq")):
                    seq_to_frame_ts.setdefault(float(r_i["source_seq"]), ts_i)
            # R9-01 (R13): the index<->seq mapping must be validated as a
            # whole BEFORE any statistics: every claimed index/seq pair has
            # to identify the SAME captured frame of THIS run.  A tracker
            # that is present but inconsistent is rejected outright - bad
            # entries are never silently filtered away to let a claim pass.
            _malformed = _validate_tracker_mapping(
                live_phase_tracker, telemetry_records, frame_ts, req_names)
            if _malformed is not None:
                return False, "PHASE_TRACKER_MALFORMED_REJECTED", {"detail": _malformed}
            for name in req_names:
                tr = live_phase_tracker.get(name)
                tr_frames = (tr or {}).get("frame_indices") or []
                tr_seqs = (tr or {}).get("source_seqs") or []
                if not tr_frames or not tr_seqs:
                    return False, "PHASE_NOT_CAPTURED_REJECTED", {
                        "detail": (
                            f"Phase '{name}' is confirmed but the runner's live "
                            f"tracker recorded no captured frames for it "
                            f"(frame_indices={len(tr_frames)}, source_seqs={len(tr_seqs)}) - "
                            "the stage was not actually executed in this attempt"
                        )
                    }
                tr_ds = (tr or {}).get("device_start_ms")
                tr_de = (tr or {}).get("device_end_ms")
                ps, pe = parsed[name]["start_ms"], parsed[name]["end_ms"]
                if ps <= 1e11 and _is_finite_num(tr_ds) and _is_finite_num(tr_de):
                    # majority of the tracker's own frames for this phase must
                    # fall inside the confirmed window (catches swapped stages
                    # and windows pointing at another stage's frames)
                    in_window = sum(1 for sq in tr_seqs
                                    if _is_finite_num(sq)
                                    and float(sq) in seq_to_frame_ts
                                    and ps - 500.0 <= seq_to_frame_ts[float(sq)] <= pe + 500.0)
                    if in_window * 2 < len(tr_seqs):
                        return False, "PHASE_TRACKER_WINDOW_CONFLICT_REJECTED", {
                            "detail": (
                                f"Phase '{name}' window [{ps}, {pe}] does not cover the "
                                f"frames the runner actually captured for it "
                                f"({in_window}/{len(tr_seqs)} tracker frames in window)"
                            )
                        }
        # 0b. Live tracker binding: every source_seq the runner attributed to a
        seq_to_ts: dict[float, float] = {}
        for r_i, ts_i in zip(telemetry_records, frame_ts):
            if isinstance(r_i, dict) and _is_finite_num(r_i.get("source_seq")):
                seq_to_ts.setdefault(float(r_i["source_seq"]), ts_i)
        for name in req_names:
            seqs_claimed = parsed[name].pop("_source_seqs", None)
            if seqs_claimed is None:
                continue
            ps, pe = parsed[name]["start_ms"], parsed[name]["end_ms"]
            for sq in seqs_claimed:
                if not _is_finite_num(sq) or float(sq) not in seq_to_ts:
                    return False, "FOREIGN_PHASE_CONFIRMATION_REJECTED", {
                        "detail": f"Phase '{name}' tracker source_seq {sq!r} is not a captured telemetry frame"
                    }
                ts_q = seq_to_ts[float(sq)]
                if ts_q < ps - 500.0 or ts_q > pe + 500.0:
                    return False, "FOREIGN_PHASE_CONFIRMATION_REJECTED", {
                        "detail": f"Phase '{name}' tracker source_seq {sq!r} lies outside its window [{ps}, {pe}]"
                    }
        # 1. Verify entry phase window contains motion and inside/outside traversal
        # R9-01 residual: when live_phase_tracker is available, use ONLY the
        # frames the runner actually captured for this phase - not the whole
        # telemetry by time window.  This prevents cross-phase frame borrowing.
        es, ee = parsed["entry"]["start_ms"], parsed["entry"]["end_ms"]
        _entry_tracker = (live_phase_tracker or {}).get("entry") or {}
        _entry_frame_ids = _entry_tracker.get("frame_indices") or []
        if _entry_frame_ids and isinstance(live_phase_tracker, dict) and live_phase_tracker:
            # restrict to tracked frames only
            entry_idx = sorted(set(_entry_frame_ids))
            # also intersect with time-window overlap to catch window/frame mismatch
            entry_idx = [i for i in entry_idx if 0 <= i < len(frame_ts)
                         and frame_ts[i] is not None
                         and es - 500.0 <= frame_ts[i] <= ee + 500.0]
        else:
            entry_idx = [i for i, ts in enumerate(frame_ts) if es - 1e-6 <= ts <= ee + 1e-6]
        if len(entry_idx) < 2:
            return False, "PHASE_WINDOW_OUTSIDE_CAPTURE_REJECTED", {
                "detail": f"Entry phase window [{es}, {ee}] matched only {len(entry_idx)} telemetry frames"
            }
        entry_targets = []
        for i in entry_idx:
            r = telemetry_records[i]
            p_obj = r.get("presence") or {}
            if isinstance(p_obj, dict) and p_obj.get("value") is True and p_obj.get("quality") == "valid":
                for t in (r.get("targets") or []):
                    if isinstance(t, dict) and t.get("position_quality") == "valid":
                        entry_targets.append(t)
        if len(entry_targets) < 2:
            return False, "ENTRY_PHASE_MOTION_INSUFFICIENT", {
                "detail": "Entry phase window contains fewer than 2 fresh target samples"
            }
        ex = [float(t["local_cm"][0]) for t in entry_targets]
        ey = [float(t["local_cm"][1]) for t in entry_targets]
        if (max(ex) - min(ex)) < 5.0 and (max(ey) - min(ey)) < 5.0:
            return False, "ENTRY_PHASE_MOTION_INSUFFICIENT", {
                "detail": "Entry phase window lacks >= 5.0cm spatial movement"
            }
        eb = {str(t.get("boundary")) for t in entry_targets if t.get("boundary") is not None}
        if not {"inside", "outside"}.issubset(eb):
            return False, "BOUNDARY_TRAVERSAL_INCOMPLETE_REJECTED", {
                "detail": f"Entry phase window [{es}, {ee}] did not traverse both inside and outside (observed {sorted(eb)})"
            }
        parsed["entry"]["frame_count"] = len(entry_idx)

        # 2. Verify still phase window contains stationary presence retention
        # R9-01 residual: restrict to tracked frames when available.
        ss, se = parsed["still"]["start_ms"], parsed["still"]["end_ms"]
        _still_tracker = (live_phase_tracker or {}).get("still") or {}
        _still_frame_ids = _still_tracker.get("frame_indices") or []
        if _still_frame_ids and isinstance(live_phase_tracker, dict) and live_phase_tracker:
            still_idx = sorted(set(_still_frame_ids))
            still_idx = [i for i in still_idx if 0 <= i < len(frame_ts)
                         and frame_ts[i] is not None
                         and ss - 500.0 <= frame_ts[i] <= se + 500.0]
        else:
            still_idx = [i for i, ts in enumerate(frame_ts) if ss - 1e-6 <= ts <= se + 1e-6]
        if len(still_idx) < 3:
            return False, "PHASE_WINDOW_OUTSIDE_CAPTURE_REJECTED", {
                "detail": f"Still phase window [{ss}, {se}] matched only {len(still_idx)} telemetry frames"
            }
        ph_still_dur = 0.0
        ph_still_frames = 0
        c_anchor: list[float] | None = None
        c_start: float | None = None
        c_last: float | None = None
        c_cnt = 0
        for i in still_idx:
            r = telemetry_records[i]
            p_obj = r.get("presence") or {}
            tgts = [t for t in (r.get("targets") or []) if isinstance(t, dict) and t.get("position_quality") == "valid"]
            pms_ok = bool(tgts) and _is_finite_num(tgts[0].get("position_ms"))
            if isinstance(p_obj, dict) and p_obj.get("value") is True and p_obj.get("quality") == "valid" and pms_ok:
                # R8-01A: stationary span measured on target position_ms (the
                # position field's own sampling clock), never on sent_ms.
                pms = float(tgts[0]["position_ms"])
                loc = [float(tgts[0]["local_cm"][0]), float(tgts[0]["local_cm"][1])]
                if c_anchor is None:
                    c_anchor = loc
                    c_start = pms
                    c_last = pms
                    c_cnt = 1
                else:
                    if math.hypot(loc[0] - c_anchor[0], loc[1] - c_anchor[1]) <= 5.0:
                        if c_last is not None and pms > c_last:
                            c_cnt += 1
                            c_last = pms
                        d = pms - float(c_start)
                        if c_cnt >= 3 and d > ph_still_dur:
                            ph_still_dur = d
                            ph_still_frames = c_cnt
                    else:
                        c_anchor = loc
                        c_start = pms
                        c_last = pms
                        c_cnt = 1
            else:
                c_anchor = None
                c_start = None
                c_last = None
                c_cnt = 0
        if ph_still_frames < 3 or ph_still_dur < float(minimum_still_duration_ms):
            return False, "STILL_PHASE_INSUFFICIENT", {
                "detail": f"Still phase window [{ss}, {se}] stationary retention {ph_still_dur}ms ({ph_still_frames} frames) < {minimum_still_duration_ms}ms"
            }
        parsed["still"]["frame_count"] = len(still_idx)

        # 3. Verify exit phase window contains sustained absence
        # R9-01 residual: restrict to tracked frames when available.
        xs_ms, xe_ms = parsed["exit"]["start_ms"], parsed["exit"]["end_ms"]
        _exit_tracker = (live_phase_tracker or {}).get("exit") or {}
        _exit_frame_ids = _exit_tracker.get("frame_indices") or []
        if _exit_frame_ids and isinstance(live_phase_tracker, dict) and live_phase_tracker:
            exit_idx = sorted(set(_exit_frame_ids))
            exit_idx = [i for i in exit_idx if 0 <= i < len(frame_ts)
                        and frame_ts[i] is not None
                        and xs_ms - 500.0 <= frame_ts[i] <= xe_ms + 500.0]
        else:
            exit_idx = [i for i, ts in enumerate(frame_ts) if xs_ms - 500.0 <= ts <= xe_ms + 500.0]
        if len(exit_idx) < 3:
            return False, "PHASE_WINDOW_OUTSIDE_CAPTURE_REJECTED", {
                "detail": f"Exit phase window [{xs_ms}, {xe_ms}] matched only {len(exit_idx)} telemetry frames"
            }
        exit_absent_idx = []
        exit_absent_seqs = []
        for i in exit_idx:
            r = telemetry_records[i]
            p_obj = r.get("presence") or {}
            if isinstance(p_obj, dict) and p_obj.get("value") is False and p_obj.get("quality") == "valid":
                exit_absent_idx.append(i)
                exit_absent_seqs.append(float(r["source_seq"]))
        exit_ok = len(exit_absent_idx) >= 3 and len(set(exit_absent_seqs)) >= 3
        exit_span = 0.0
        if exit_ok and presence_ts is not None and len(presence_ts) == len(frame_ts):
            # R8-01A: absence span measured on presence.sample_ms, not sent_ms.
            p_vals = [presence_ts[i] for i in exit_absent_idx]
            if any(v is None for v in p_vals):
                exit_ok = False
            elif presence_hold:
                # Event-hold contract: a fresh absence transition sample, held
                # until a terminal frame whose transport time bounds the span.
                prior_true = [
                    presence_ts[j] for j in range(exit_absent_idx[0])
                    if presence_ts[j] is not None
                    and isinstance(telemetry_records[j].get("presence"), dict)
                    and telemetry_records[j]["presence"].get("value") is True
                ]
                transition = float(p_vals[0])
                if prior_true and transition <= float(prior_true[-1]):
                    exit_ok = False
                exit_span = frame_ts[exit_absent_idx[-1]] - transition
            else:
                if len(set(p_vals)) < 3:
                    exit_ok = False
                exit_span = float(max(p_vals)) - float(min(p_vals))
        elif exit_ok:
            exit_span = frame_ts[exit_absent_idx[-1]] - frame_ts[exit_absent_idx[0]]
        if not exit_ok or exit_span < float(minimum_exit_duration_ms):
            return False, "SUSTAINED_EXIT_DURATION_INSUFFICIENT", {
                "detail": f"Exit phase window [{xs_ms}, {xe_ms}] did not sustain valid absence >= {minimum_exit_duration_ms}ms"
            }
        parsed["exit"]["frame_count"] = len(exit_idx)

    return True, "OK", parsed


def judge_human_observation(records_or_doc: list[dict] | dict, min_records: int = 30, **kwargs) -> tuple[str, bool, dict]:
    """Pure evaluation of human radar observation with full multi-phase & 2D/3D coordinate validation.

    Evaluates and aggregates explicit per-phase verdicts:
      1. Explicit positive user action confirmation and valid minimum_exit_duration_ms >= 10000ms.
      2. Minimum telemetry volume, same boot_id, and non-stale monotonically non-decreasing source_seq.
      3. Confirmed presence phase (valid presence=True) and 2D [x, y] or 3D [x, y, z] coordinates per device capability.
      4. Fresh spatial motion (targets with position_quality='valid' and finite advancing position_ms within stale_after_ms must span >= 5cm).
      5. Coordinate transform consistency (X, Y, and when present Z against expected_room_coords within 2.0cm).
      6. Sustained departure phase (consecutive valid presence=False frames sustained >= 10s with advancing source_seq and timestamps).
      7. Boundary polygon classification consistency and inside/outside traversal.
      8. Stationary retention phase (continuous valid presence=True with stationary target >= minimum_still_duration_ms).
      9. Structured phase confirmation records (entry, still, exit) bound to telemetry capture window.
    """
    if isinstance(records_or_doc, dict):
        telemetry_records = records_or_doc.get("telemetry_records") or records_or_doc.get("records") or []
        boot_before = records_or_doc.get("boot_before")
        boot_after = records_or_doc.get("boot_after")
        user_action_confirmed = records_or_doc.get("user_action_confirmed")
        expected_installation = records_or_doc.get("expected_installation")
        minimum_exit_duration_ms = records_or_doc.get("minimum_exit_duration_ms", 10000)
        minimum_still_duration_ms = records_or_doc.get("minimum_still_duration_ms", 2000)
        phases = records_or_doc.get("phases")
        require_structured_phases = records_or_doc.get("require_structured_phases", False)
        device_info = records_or_doc.get("device_info")
        has_device_info = "device_info" in records_or_doc
        capabilities = records_or_doc.get("capabilities")
        has_capabilities = "capabilities" in records_or_doc
        run_id = records_or_doc.get("run_id")
        attempt_id = records_or_doc.get("attempt_id")
        session_id = records_or_doc.get("session_id")
        frame_host_rx_ms = records_or_doc.get("frame_host_rx_ms")
        _hdm = records_or_doc.get("host_device_time_mapping")
        live_phase_tracker = (_hdm or {}).get("live_phase_tracker") if isinstance(_hdm, dict) else None
    else:
        telemetry_records = records_or_doc or []
        boot_before = kwargs.get("boot_before")
        boot_after = kwargs.get("boot_after")
        user_action_confirmed = kwargs.get("user_action_confirmed")
        expected_installation = kwargs.get("expected_installation")
        minimum_exit_duration_ms = kwargs.get("minimum_exit_duration_ms", 10000)
        minimum_still_duration_ms = kwargs.get("minimum_still_duration_ms", 2000)
        phases = kwargs.get("phases")
        require_structured_phases = kwargs.get("require_structured_phases", False)
        device_info = kwargs.get("device_info")
        has_device_info = "device_info" in kwargs
        capabilities = kwargs.get("capabilities")
        has_capabilities = "capabilities" in kwargs
        run_id = kwargs.get("run_id")
        attempt_id = kwargs.get("attempt_id")
        session_id = kwargs.get("session_id")
        frame_host_rx_ms = kwargs.get("frame_host_rx_ms")
        live_phase_tracker = kwargs.get("live_phase_tracker")

    phase_verdicts: dict[str, dict[str, Any]] = {
        "time_and_integrity": {"status": "pending", "reason": "UNCHECKED"},
        "entry_motion": {"status": "pending", "reason": "UNCHECKED"},
        "still_retention": {"status": "pending", "reason": "UNCHECKED"},
        "departure_exit": {"status": "pending", "reason": "UNCHECKED"},
        "coordinate_consistency": {"status": "pending", "reason": "UNCHECKED"},
        "structured_action_confirmation": {"status": "pending", "reason": "UNCHECKED"},
    }

    if user_action_confirmed is not True:
        phase_verdicts["structured_action_confirmation"] = {
            "status": "unconfirmed",
            "reason": "UNCONFIRMED_USER_ACTION_REJECTED",
        }
        return "UNCONFIRMED_USER_ACTION_REJECTED", False, {
            "detail": "Human observation requires explicit positive user action confirmation",
            "phase_verdicts": phase_verdicts,
        }

    if not _is_finite_num(minimum_exit_duration_ms) or float(minimum_exit_duration_ms) < 10000.0:
        phase_verdicts["departure_exit"] = {"status": "fail", "reason": "INVALID_THRESHOLD_REJECTED"}
        return "INVALID_THRESHOLD_REJECTED", False, {
            "detail": f"minimum_exit_duration_ms must be >= 10000ms, got {minimum_exit_duration_ms!r}",
            "phase_verdicts": phase_verdicts,
        }

    if not isinstance(telemetry_records, list) or len(telemetry_records) < min_records:
        cnt = len(telemetry_records) if isinstance(telemetry_records, list) else 0
        phase_verdicts["time_and_integrity"] = {"status": "insufficient", "reason": "INSUFFICIENT_RECORDS_REJECTED"}
        return "INSUFFICIENT_RECORDS_REJECTED", False, {
            "detail": f"Observed {cnt} telemetry frames, minimum required is {min_records}",
            "phase_verdicts": phase_verdicts,
        }

    if boot_before and boot_after and boot_before != boot_after:
        phase_verdicts["time_and_integrity"] = {"status": "fail", "reason": "BOOT_CHANGED_REJECTED"}
        return "BOOT_CHANGED_REJECTED", False, {
            "detail": f"Spontaneous reboot during observation ({boot_before} != {boot_after})",
            "phase_verdicts": phase_verdicts,
        }

    frame_boots = {
        r.get("boot_id") for r in telemetry_records
        if isinstance(r, dict) and r.get("boot_id") is not None
    }
    if len(frame_boots) > 1 or (boot_before and frame_boots and frame_boots != {boot_before}):
        phase_verdicts["time_and_integrity"] = {"status": "fail", "reason": "BOOT_CHANGED_REJECTED"}
        return "BOOT_CHANGED_REJECTED", False, {
            "detail": f"Cross-boot frames detected in telemetry: {sorted(str(x) for x in frame_boots)}",
            "phase_verdicts": phase_verdicts,
        }

    if has_device_info:
        if not isinstance(device_info, dict) or not isinstance(device_info.get("device_id"), str) or not device_info["device_id"].strip():
            phase_verdicts["time_and_integrity"] = {"status": "fail", "reason": "MISSING_DEVICE_IDENTITY_REJECTED"}
            return "MISSING_DEVICE_IDENTITY_REJECTED", False, {
                "detail": "Valid device_info with non-empty device_id is required for human observation",
                "phase_verdicts": phase_verdicts,
            }

    stale_after_ms = 6000.0
    # R8-01A: presence sampling contract.  Periodic presence must stay fresh
    # relative to the frame's sent_ms; an event-driven presence capability
    # (explicit expected_interval_ms=null AND stale_after_ms=null, as the
    # production R60 descriptor declares) is "event hold": the value is held
    # until the next transition and its span is bounded by a fresh transition
    # sample plus a terminal frame — never by advancing sent_ms alone.
    presence_hold = False
    presence_stale_ms = 6000.0
    if has_capabilities:
        cap_items = capabilities.get("items") if isinstance(capabilities, dict) else None
        if not isinstance(cap_items, list) or not cap_items:
            phase_verdicts["time_and_integrity"] = {"status": "fail", "reason": "INCOMPLETE_CAPABILITIES_REJECTED"}
            return "INCOMPLETE_CAPABILITIES_REJECTED", False, {
                "detail": "Valid capabilities descriptor with non-empty items is required",
                "phase_verdicts": phase_verdicts,
            }
        cap_by_id = {it.get("id"): it for it in cap_items if isinstance(it, dict) and isinstance(it.get("id"), str)}
        if not {"presence", "position.xy"}.issubset(set(cap_by_id.keys())):
            phase_verdicts["time_and_integrity"] = {"status": "fail", "reason": "INCOMPLETE_CAPABILITIES_REJECTED"}
            return "INCOMPLETE_CAPABILITIES_REJECTED", False, {
                "detail": f"Capabilities missing required 'presence' or 'position.xy' items: {sorted(cap_by_id.keys())}",
                "phase_verdicts": phase_verdicts,
            }
        pos_cap = cap_by_id["position.xy"]
        for k in ("StaleAfterMs", "stale_after_ms"):
            if _is_finite_num(pos_cap.get(k)) and float(pos_cap[k]) > 0:
                stale_after_ms = float(pos_cap[k])
                break
        pres_cap = cap_by_id["presence"]
        if (
            "expected_interval_ms" in pres_cap and pres_cap.get("expected_interval_ms") is None
            and "stale_after_ms" in pres_cap and pres_cap.get("stale_after_ms") is None
        ):
            presence_hold = True
        else:
            for k in ("StaleAfterMs", "stale_after_ms"):
                if _is_finite_num(pres_cap.get(k)) and float(pres_cap[k]) > 0:
                    presence_stale_ms = float(pres_cap[k])
                    break

    seqs = [r.get("source_seq") for r in telemetry_records if isinstance(r, dict) and r.get("source_seq") is not None]
    if len(seqs) != len(telemetry_records):
        phase_verdicts["time_and_integrity"] = {"status": "fail", "reason": "MISSING_SEQUENCE_REJECTED"}
        return "MISSING_SEQUENCE_REJECTED", False, {
            "detail": "One or more telemetry frames are missing source_seq",
            "phase_verdicts": phase_verdicts,
        }
    if any(not _is_finite_num(s) for s in seqs):
        phase_verdicts["time_and_integrity"] = {"status": "fail", "reason": "INVALID_SEQUENCE_REJECTED"}
        return "INVALID_SEQUENCE_REJECTED", False, {
            "detail": "Non-numeric or non-finite source_seq encountered",
            "phase_verdicts": phase_verdicts,
        }
    if len(set(seqs)) <= 1:
        phase_verdicts["time_and_integrity"] = {"status": "fail", "reason": "STALE_SEQUENCE_REJECTED"}
        return "STALE_SEQUENCE_REJECTED", False, {
            "detail": "Source sequence numbers never progressed (all frames identical)",
            "seq_count": len(seqs), "unique_seqs": len(set(seqs)),
            "phase_verdicts": phase_verdicts,
        }
    if not all(b >= a for a, b in zip(seqs, seqs[1:])):
        phase_verdicts["time_and_integrity"] = {"status": "fail", "reason": "NON_MONOTONIC_SEQUENCE_REJECTED"}
        return "NON_MONOTONIC_SEQUENCE_REJECTED", False, {
            "detail": "Source sequence numbers are not monotonically non-decreasing",
            "phase_verdicts": phase_verdicts,
        }

    presence_history = []
    for idx, r in enumerate(telemetry_records):
        p_obj = r.get("presence") or {}
        p_val = p_obj.get("value") if isinstance(p_obj, dict) else None
        p_qual = p_obj.get("quality") if isinstance(p_obj, dict) else None
        s_ms = _frame_timestamp_ms(r)
        presence_history.append((idx, p_val, p_qual, s_ms))

    true_indices = [idx for idx, val, qual, _ in presence_history if val is True and qual == "valid"]
    if not true_indices:
        phase_verdicts["entry_motion"] = {"status": "fail", "reason": "NO_PRESENCE_DETECTED"}
        return "NO_PRESENCE_DETECTED", False, {
            "detail": "No valid presence=True phase detected",
            "phase_verdicts": phase_verdicts,
        }
    first_true_idx = min(true_indices)
    last_true_idx = max(true_indices)

    # Filter target samples with valid coordinates and position quality
    all_targets = []
    fresh_targets = []
    fresh_target_frames: list[tuple[int, dict]] = []
    for idx, r in enumerate(telemetry_records):
        tgts = r.get("targets") or []
        for t in tgts:
            if isinstance(t, dict):
                all_targets.append(t)
                if t.get("position_quality") == "valid":
                    fresh_targets.append(t)
                    fresh_target_frames.append((idx, t))

    def _valid_coord_vec(vec: Any) -> bool:
        return (
            isinstance(vec, list)
            and len(vec) in (2, 3)
            and all(_is_finite_num(c) for c in vec)
        )

    # 1. Parsing check (2D/3D local_cm and room_cm required)
    all_local = [t.get("local_cm") for t in all_targets if _valid_coord_vec(t.get("local_cm"))]
    all_room = [t.get("room_cm") for t in all_targets if _valid_coord_vec(t.get("room_cm"))]
    if not all_local or not all_room or len(all_local) != len(all_targets) or len(all_room) != len(all_targets):
        phase_verdicts["coordinate_consistency"] = {"status": "fail", "reason": "COORDINATES_MISSING"}
        return "COORDINATES_MISSING", False, {
            "detail": "Failed to parse target coordinates (local_cm or room_cm missing, invalid length, or non-finite)",
            "phase_verdicts": phase_verdicts,
        }

    # 2. Fresh targets check
    if not fresh_targets:
        phase_verdicts["entry_motion"] = {"status": "fail", "reason": "STALE_TARGETS_REJECTED"}
        return "STALE_TARGETS_REJECTED", False, {
            "detail": "All target coordinate frames marked stale with no fresh position quality",
            "phase_verdicts": phase_verdicts,
        }

    fresh_local = [t["local_cm"] for t in fresh_targets if _valid_coord_vec(t.get("local_cm"))]
    fresh_room = [t["room_cm"] for t in fresh_targets if _valid_coord_vec(t.get("room_cm"))]
    if not fresh_local or not fresh_room:
        phase_verdicts["coordinate_consistency"] = {"status": "fail", "reason": "COORDINATES_MISSING"}
        return "COORDINATES_MISSING", False, {
            "detail": "Failed to parse fresh target coordinates (local_cm or room_cm missing or invalid)",
            "phase_verdicts": phase_verdicts,
        }

    xs = [float(pt[0]) for pt in fresh_local]
    ys = [float(pt[1]) for pt in fresh_local]
    x_span = max(xs) - min(xs)
    y_span = max(ys) - min(ys)
    if x_span < 5.0 and y_span < 5.0:
        phase_verdicts["entry_motion"] = {"status": "insufficient", "reason": "ALL_PRESENT_STATIC_INSUFFICIENT"}
        return "ALL_PRESENT_STATIC_INSUFFICIENT", False, {
            "detail": "Target coordinates static with zero motion (x_span < 5cm and y_span < 5cm) on fresh samples",
            "x_span": x_span, "y_span": y_span,
            "phase_verdicts": phase_verdicts,
        }

    # 3. Target position_ms presence, finiteness, monotonicity & advancement check (R6-01 / R7-01)
    pos_ms_values: list[float] = []
    advancing_fresh_targets: list[dict] = []
    last_pos_ms: float | None = None
    last_adv_seq: float | None = None
    missing_pos_ms = False
    for idx, t in fresh_target_frames:
        pms = t.get("position_ms")
        if pms is None:
            missing_pos_ms = True
            continue
        if not _is_finite_num(pms):
            phase_verdicts["time_and_integrity"] = {"status": "fail", "reason": "INVALID_POSITION_TIMESTAMP_REJECTED"}
            return "INVALID_POSITION_TIMESTAMP_REJECTED", False, {
                "detail": f"Target position_ms is not a finite number: {pms!r}",
                "phase_verdicts": phase_verdicts,
            }
        pms_f = float(pms)
        if last_pos_ms is not None and pms_f < last_pos_ms:
            phase_verdicts["time_and_integrity"] = {"status": "fail", "reason": "TIMESTAMP_REGRESSION_REJECTED"}
            return "TIMESTAMP_REGRESSION_REJECTED", False, {
                "detail": f"Target position_ms regressed from {last_pos_ms} to {pms_f}",
                "phase_verdicts": phase_verdicts,
            }
        f_seq = float(telemetry_records[idx]["source_seq"])
        if (last_pos_ms is None or pms_f > last_pos_ms) and (last_adv_seq is None or f_seq > last_adv_seq):
            advancing_fresh_targets.append(t)
            last_adv_seq = f_seq
        last_pos_ms = pms_f
        pos_ms_values.append(pms_f)

    if pos_ms_values:
        if len(set(pos_ms_values)) <= 1 or len(advancing_fresh_targets) < 2:
            phase_verdicts["entry_motion"] = {"status": "fail", "reason": "STALE_POSITION_TIMESTAMP_REJECTED"}
            return "STALE_POSITION_TIMESTAMP_REJECTED", False, {
                "detail": "Target position_ms never advanced across fresh target samples",
                "unique_position_ms": sorted(list(set(pos_ms_values))),
                "phase_verdicts": phase_verdicts,
            }
        adv_xs = [float(t["local_cm"][0]) for t in advancing_fresh_targets]
        adv_ys = [float(t["local_cm"][1]) for t in advancing_fresh_targets]
        if (max(adv_xs) - min(adv_xs)) < 5.0 and (max(adv_ys) - min(adv_ys)) < 5.0:
            phase_verdicts["entry_motion"] = {"status": "fail", "reason": "STALE_POSITION_TIMESTAMP_REJECTED"}
            return "STALE_POSITION_TIMESTAMP_REJECTED", False, {
                "detail": "Targets with advancing position_ms exhibited insufficient spatial motion (< 5cm)",
                "phase_verdicts": phase_verdicts,
            }

    # 4. 2D/3D Coordinate transform consistency check (X, Y, and when present Z)
    rx = [float(pt[0]) for pt in fresh_room]
    ry = [float(pt[1]) for pt in fresh_room]
    rx_span = max(rx) - min(rx)
    ry_span = max(ry) - min(ry)
    if (x_span >= 5.0 or y_span >= 5.0) and (rx_span == 0.0 and ry_span == 0.0):
        phase_verdicts["coordinate_consistency"] = {"status": "fail", "reason": "BAD_COORDINATE_TRANSFORM"}
        return "BAD_COORDINATE_TRANSFORM", False, {
            "detail": "Coordinate transform broken: local coordinates moved but room coordinates remained static",
            "local_span": [x_span, y_span],
            "room_span": [rx_span, ry_span],
            "phase_verdicts": phase_verdicts,
        }

    if expected_installation is not None:
        if not isinstance(expected_installation, dict) or not all(
            k in expected_installation and _is_finite_num(expected_installation[k])
            and NUMERIC_RANGES[k][0] <= float(expected_installation[k]) <= NUMERIC_RANGES[k][1]
            and _on_step(float(expected_installation[k]), NUMERIC_STEPS[k])
            for k in NUMERIC_RANGES
        ):
            phase_verdicts["coordinate_consistency"] = {
                "status": "fail",
                "reason": "INVALID_INSTALLATION_GEOMETRY_REJECTED",
            }
            return "INVALID_INSTALLATION_GEOMETRY_REJECTED", False, {
                "detail": "Expected installation geometry missing, out-of-range, or off-step numeric fields",
                "phase_verdicts": phase_verdicts,
            }
        tilt_couples_z = (
            abs(float(expected_installation["install.pitch_deg"])) > 1e-6
            or abs(float(expected_installation["install.roll_deg"])) > 1e-6
        )
        z_source_counts = {"local_cm": 0, "diagnostics.local_z": 0, "not_required": 0}
        for f_idx, t in fresh_target_frames:
            loc = t["local_cm"]
            rm = t["room_cm"]
            if len(loc) != len(rm):
                phase_verdicts["coordinate_consistency"] = {
                    "status": "fail",
                    "reason": "COORDINATE_DIMENSION_MISMATCH_REJECTED",
                }
                return "COORDINATE_DIMENSION_MISMATCH_REJECTED", False, {
                    "detail": f"Target local_cm dimension ({len(loc)}) != room_cm dimension ({len(rm)})",
                    "phase_verdicts": phase_verdicts,
                }
            lx, ly = float(loc[0]), float(loc[1])
            if len(loc) >= 3:
                lz = float(loc[2])
                z_source_counts["local_cm"] += 1
            else:
                # R8-01B: production 2D telemetry serialises local_cm=[x,y]
                # while the transform input z is published as the co-sampled
                # metrics["diagnostics.local_z"].  Never guess lz=0 when pitch
                # or roll couples local z into room x/y.
                diag_z = _diag_local_z_for_target(telemetry_records[f_idx], t)
                if diag_z is not None:
                    lz = diag_z
                    z_source_counts["diagnostics.local_z"] += 1
                elif tilt_couples_z:
                    phase_verdicts["coordinate_consistency"] = {
                        "status": "insufficient",
                        "reason": "INSUFFICIENT_Z_DIAGNOSTIC_FOR_TILT_REJECTED",
                    }
                    return "INSUFFICIENT_Z_DIAGNOSTIC_FOR_TILT_REJECTED", False, {
                        "detail": (
                            "2D target under non-zero pitch/roll requires a valid diagnostics.local_z "
                            f"sampled at position_ms={t.get('position_ms')!r} (frame {f_idx}); "
                            "room x/y cannot be verified without the real local z"
                        ),
                        "frame_index": f_idx,
                        "phase_verdicts": phase_verdicts,
                    }
                else:
                    # yaw-only: R[0][2] == R[1][2] == 0, room x/y independent of z.
                    lz = 0.0
                    z_source_counts["not_required"] += 1
            exp_rm = expected_room_coords(lx, ly, lz, expected_installation)
            # Compare X, Y, and (only when 3D room_cm is present) Z within strict 2.0 cm tolerance
            z_mismatch = (len(rm) >= 3 and abs(float(rm[2]) - exp_rm[2]) > 2.0)
            if (
                abs(float(rm[0]) - exp_rm[0]) > 2.0
                or abs(float(rm[1]) - exp_rm[1]) > 2.0
                or z_mismatch
            ):
                phase_verdicts["coordinate_consistency"] = {
                    "status": "fail",
                    "reason": "COORDINATE_TRANSFORM_MISMATCH_REJECTED",
                }
                return "COORDINATE_TRANSFORM_MISMATCH_REJECTED", False, {
                    "detail": (
                        f"Observed room_cm {rm} contradicts expected "
                        f"[{exp_rm[0]:.1f}, {exp_rm[1]:.1f}"
                        + (f", {exp_rm[2]:.1f}]" if len(rm) >= 3 else "]")
                        + " under installation matrix"
                    ),
                    "observed": [float(c) for c in rm],
                    "expected": [round(exp_rm[0], 2), round(exp_rm[1], 2)]
                    + ([round(exp_rm[2], 2)] if len(rm) >= 3 else []),
                    "phase_verdicts": phase_verdicts,
                }
    else:
        for t in fresh_targets:
            loc = t["local_cm"]
            rm = t["room_cm"]
            if len(rm) >= 3:
                lz = float(loc[2]) if len(loc) >= 3 else 0.0
                if abs(float(rm[2]) - lz) > 600.0 or abs(float(rm[2])) > 2000.0:
                    phase_verdicts["coordinate_consistency"] = {
                        "status": "fail",
                        "reason": "COORDINATE_TRANSFORM_MISMATCH_REJECTED",
                    }
                    return "COORDINATE_TRANSFORM_MISMATCH_REJECTED", False, {
                        "detail": f"Observed room_cm Z ({rm[2]}) is inconsistent with local_cm Z ({lz})",
                        "observed": rm,
                        "phase_verdicts": phase_verdicts,
                    }
    is_2d = all(len(t["local_cm"]) == 2 and len(t["room_cm"]) == 2 for t in fresh_targets)
    phase_verdicts["coordinate_consistency"] = {
        "status": "pass",
        "reason": "2D_TRANSFORM_VERIFIED" if is_2d else "3D_TRANSFORM_VERIFIED",
        "dimension": 2 if is_2d else 3,
    }
    if expected_installation is not None:
        phase_verdicts["coordinate_consistency"]["local_z_source_counts"] = z_source_counts

    # 5. Sustained Departure Frame Count & Sequence Advancement Check
    if last_true_idx == len(telemetry_records) - 1:
        phase_verdicts["departure_exit"] = {"status": "fail", "reason": "UNCONFIRMED_DEPARTURE_REJECTED"}
        return "UNCONFIRMED_DEPARTURE_REJECTED", False, {
            "detail": "Final frame indicates presence; subject did not depart",
            "last_presence": presence_history[-1][1],
            "phase_verdicts": phase_verdicts,
        }

    tail_records = presence_history[last_true_idx + 1:]
    if len(tail_records) < 3:
        phase_verdicts["departure_exit"] = {"status": "insufficient", "reason": "SINGLE_FRAME_GLITCH_REJECTED"}
        return "SINGLE_FRAME_GLITCH_REJECTED", False, {
            "detail": f"Exit phase is not sustained (only {len(tail_records)} frames absent, required >= 3 consecutive frames)",
            "exit_frames": len(tail_records),
            "first_present_frame": first_true_idx,
            "last_present_frame": last_true_idx,
            "phase_verdicts": phase_verdicts,
        }

    for idx, val, qual, _ in tail_records:
        if val is not False or qual != "valid":
            phase_verdicts["departure_exit"] = {"status": "fail", "reason": "NO_SUSTAINED_EXIT_REJECTED"}
            return "NO_SUSTAINED_EXIT_REJECTED", False, {
                "detail": f"Departure phase interrupted or non-valid sample at frame {idx}",
                "presence": val, "quality": qual,
                "phase_verdicts": phase_verdicts,
            }

    last_present_seq = float(telemetry_records[last_true_idx]["source_seq"])
    tail_seqs = [float(telemetry_records[idx]["source_seq"]) for idx, _, _, _ in tail_records]
    if tail_seqs[0] <= last_present_seq or len(set(tail_seqs)) < 3:
        phase_verdicts["departure_exit"] = {"status": "fail", "reason": "STALE_EXIT_SEQUENCE_REJECTED"}
        return "STALE_EXIT_SEQUENCE_REJECTED", False, {
            "detail": (
                f"Departure frames did not advance source_seq (last_present_seq={last_present_seq}, "
                f"unique_exit_seqs={len(set(tail_seqs))})"
            ),
            "phase_verdicts": phase_verdicts,
        }

    if missing_pos_ms:
        phase_verdicts["time_and_integrity"] = {"status": "fail", "reason": "MISSING_POSITION_TIMESTAMP_REJECTED"}
        return "MISSING_POSITION_TIMESTAMP_REJECTED", False, {
            "detail": "One or more fresh target samples are missing finite position_ms timestamp",
            "phase_verdicts": phase_verdicts,
        }

    # 6. Mandatory Frame Timestamps, Monotonicity & Target position_ms Freshness Check (R6-01 / R7-01)
    frame_ts: list[float] = []
    for idx, _, _, s_ms in presence_history:
        if s_ms is None or not _is_finite_num(s_ms):
            phase_verdicts["time_and_integrity"] = {"status": "fail", "reason": "MISSING_TIMESTAMPS_REJECTED"}
            return "MISSING_TIMESTAMPS_REJECTED", False, {
                "detail": f"Telemetry frame {idx} is missing finite sample_ms/sent_ms timestamp",
                "frame_index": idx,
                "phase_verdicts": phase_verdicts,
            }
        if frame_ts and float(s_ms) < frame_ts[-1]:
            phase_verdicts["time_and_integrity"] = {"status": "fail", "reason": "TIMESTAMP_REGRESSION_REJECTED"}
            return "TIMESTAMP_REGRESSION_REJECTED", False, {
                "detail": f"Frame timestamp regressed at frame {idx}: {s_ms} < {frame_ts[-1]}",
                "frame_index": idx,
                "phase_verdicts": phase_verdicts,
            }
        frame_ts.append(float(s_ms))

    if frame_ts[-1] <= frame_ts[0]:
        phase_verdicts["time_and_integrity"] = {"status": "fail", "reason": "STALE_TIMESTAMPS_REJECTED"}
        return "STALE_TIMESTAMPS_REJECTED", False, {
            "detail": "Frame timestamps did not advance across observation window",
            "phase_verdicts": phase_verdicts,
        }

    for idx, t in fresh_target_frames:
        f_ts = frame_ts[idx]
        pms_f = float(t["position_ms"])
        if (f_ts - pms_f) > stale_after_ms or (pms_f - f_ts) > 1000.0:
            phase_verdicts["time_and_integrity"] = {"status": "fail", "reason": "STALE_POSITION_TIMESTAMP_REJECTED"}
            return "STALE_POSITION_TIMESTAMP_REJECTED", False, {
                "detail": (
                    f"Target position_ms ({pms_f}) at frame {idx} is stale or inconsistent relative to "
                    f"frame sample_ms ({f_ts}), max allowed age is {stale_after_ms}ms"
                ),
                "frame_index": idx,
                "frame_sample_ms": f_ts,
                "position_ms": pms_f,
                "stale_after_ms": stale_after_ms,
                "phase_verdicts": phase_verdicts,
            }

    # 6b. Presence field sampling semantics (R8-01A): every valid presence
    # observation needs its own finite presence.sample_ms; it must not regress,
    # must not be in the future of its frame's sent_ms, and (for a periodic
    # presence capability) must stay within the presence staleness budget.
    presence_ts: list[float | None] = [None] * len(telemetry_records)
    last_presence_ms: float | None = None
    for idx, r in enumerate(telemetry_records):
        p_status, p_val = _presence_sample_ms(r)
        if p_status == "not_valid":
            continue
        if p_status == "missing":
            phase_verdicts["time_and_integrity"] = {"status": "fail", "reason": "MISSING_PRESENCE_TIMESTAMP_REJECTED"}
            return "MISSING_PRESENCE_TIMESTAMP_REJECTED", False, {
                "detail": f"Valid presence observation at frame {idx} lacks a finite non-negative presence.sample_ms "
                          "(sent_ms/source_seq are never substituted)",
                "frame_index": idx,
                "phase_verdicts": phase_verdicts,
            }
        assert p_val is not None
        if last_presence_ms is not None and p_val < last_presence_ms:
            phase_verdicts["time_and_integrity"] = {"status": "fail", "reason": "TIMESTAMP_REGRESSION_REJECTED"}
            return "TIMESTAMP_REGRESSION_REJECTED", False, {
                "detail": f"presence.sample_ms regressed at frame {idx}: {p_val} < {last_presence_ms}",
                "frame_index": idx,
                "phase_verdicts": phase_verdicts,
            }
        if p_val > frame_ts[idx] + 1e-6:
            phase_verdicts["time_and_integrity"] = {"status": "fail", "reason": "FUTURE_SAMPLE_TIMESTAMP_REJECTED"}
            return "FUTURE_SAMPLE_TIMESTAMP_REJECTED", False, {
                "detail": f"presence.sample_ms ({p_val}) at frame {idx} is later than its frame sent_ms ({frame_ts[idx]})",
                "frame_index": idx,
                "phase_verdicts": phase_verdicts,
            }
        if not presence_hold and (frame_ts[idx] - p_val) > presence_stale_ms:
            phase_verdicts["time_and_integrity"] = {"status": "fail", "reason": "STALE_PRESENCE_TIMESTAMP_REJECTED"}
            return "STALE_PRESENCE_TIMESTAMP_REJECTED", False, {
                "detail": (
                    f"presence.sample_ms ({p_val}) at frame {idx} is {frame_ts[idx] - p_val}ms older than sent_ms "
                    f"({frame_ts[idx]}); periodic presence stale budget is {presence_stale_ms}ms and no "
                    "event-hold presence contract was declared"
                ),
                "frame_index": idx,
                "phase_verdicts": phase_verdicts,
            }
        presence_ts[idx] = p_val
        last_presence_ms = p_val

    # 6c. Host receive timestamps (when the collector recorded them) are a
    # separate clock: they must be finite and non-decreasing per frame.
    if frame_host_rx_ms is not None:
        if (
            not isinstance(frame_host_rx_ms, list)
            or len(frame_host_rx_ms) != len(telemetry_records)
            or any(not _is_finite_num(v) for v in frame_host_rx_ms)
            or any(b < a for a, b in zip(frame_host_rx_ms, frame_host_rx_ms[1:]))
        ):
            phase_verdicts["time_and_integrity"] = {"status": "fail", "reason": "INVALID_HOST_RECEIVE_TIMESTAMPS_REJECTED"}
            return "INVALID_HOST_RECEIVE_TIMESTAMPS_REJECTED", False, {
                "detail": "frame_host_rx_ms must be a finite non-decreasing list aligned 1:1 with telemetry frames",
                "phase_verdicts": phase_verdicts,
            }

    phase_verdicts["time_and_integrity"] = {
        "status": "pass",
        "reason": "TIMESTAMPS_AND_SEQ_VERIFIED",
        "presence_sampling": "event_hold" if presence_hold else "periodic",
    }

    # 7. Sustained exit duration on the presence field's own sampling clock.
    last_true_p = presence_ts[last_true_idx]
    tail_idx = [idx for idx, _, _, _ in tail_records]
    tail_p = [presence_ts[i] for i in tail_idx]
    t_exit_start = frame_ts[tail_idx[0]]
    distinct_tail_ts: list[float] = sorted({float(v) for v in tail_p if v is not None})
    if any(v is None for v in tail_p) or last_true_p is None or float(tail_p[0]) <= float(last_true_p):
        phase_verdicts["departure_exit"] = {
            "status": "fail",
            "reason": "STALE_PRESENCE_TIMESTAMP_REJECTED",
        }
        return "STALE_PRESENCE_TIMESTAMP_REJECTED", False, {
            "detail": (
                "Departure has no fresh absence transition sample: first absent presence.sample_ms "
                f"({tail_p[0]}) must be newer than the last present sample ({last_true_p})"
            ),
            "phase_verdicts": phase_verdicts,
        }
    if presence_hold:
        transition_ms = float(tail_p[0])
        terminal_ms = frame_ts[tail_idx[-1]]
        exit_dur_ms = terminal_ms - transition_ms
        exit_basis = "event_hold:terminal_sent_ms-transition_presence_sample_ms"
        exit_count = len({float(telemetry_records[i]["source_seq"]) for i in tail_idx})
    else:
        if len(distinct_tail_ts) < 3:
            phase_verdicts["departure_exit"] = {
                "status": "fail",
                "reason": "STALE_PRESENCE_TIMESTAMP_REJECTED",
                "distinct_presence_samples": len(distinct_tail_ts),
            }
            return "STALE_PRESENCE_TIMESTAMP_REJECTED", False, {
                "detail": (
                    f"Departure presence.sample_ms advanced only {len(distinct_tail_ts)} distinct times; "
                    "advancing sent_ms/source_seq do not count as new presence samples"
                ),
                "phase_verdicts": phase_verdicts,
            }
        exit_dur_ms = distinct_tail_ts[-1] - distinct_tail_ts[0]
        exit_basis = "periodic:presence_sample_ms_span"
        exit_count = len(distinct_tail_ts)
    if exit_count < 3 or exit_dur_ms < float(minimum_exit_duration_ms):
        phase_verdicts["departure_exit"] = {
            "status": "insufficient",
            "reason": "SUSTAINED_EXIT_DURATION_INSUFFICIENT",
            "exit_duration_ms": exit_dur_ms,
            "basis": exit_basis,
        }
        return "SUSTAINED_EXIT_DURATION_INSUFFICIENT", False, {
            "detail": f"Sustained exit duration {exit_dur_ms}ms < required {minimum_exit_duration_ms}ms",
            "exit_duration_ms": exit_dur_ms,
            "minimum_required_ms": minimum_exit_duration_ms,
            "phase_verdicts": phase_verdicts,
        }
    phase_verdicts["departure_exit"] = {
        "status": "pass",
        "reason": "SUSTAINED_ABSENCE_VERIFIED",
        "exit_duration_ms": exit_dur_ms,
        "exit_frames": exit_count,
        "basis": exit_basis,
    }

    # 8. Boundary polygon classification & inside/outside traversal check (R6-01 / R7-01)
    boundary_poly = None
    if isinstance(expected_installation, dict):
        b_cfg = expected_installation.get("geometry.boundary_cm")
        if b_cfg is not None:
            if not is_valid_polygon_points(b_cfg, min_points=3, max_points=64):
                phase_verdicts["entry_motion"] = {"status": "fail", "reason": "INVALID_BOUNDARY_POLYGON_REJECTED"}
                return "INVALID_BOUNDARY_POLYGON_REJECTED", False, {
                    "detail": "Configured geometry.boundary_cm is not a valid polygon",
                    "phase_verdicts": phase_verdicts,
                }
            boundary_poly = b_cfg
    if require_structured_phases and boundary_poly is None:
        phase_verdicts["entry_motion"] = {"status": "fail", "reason": "MISSING_BOUNDARY_POLYGON_REJECTED"}
        return "MISSING_BOUNDARY_POLYGON_REJECTED", False, {
            "detail": "Active geometry.boundary_cm polygon is required in expected_installation for boundary traversal verification",
            "phase_verdicts": phase_verdicts,
        }

    for t in fresh_targets:
        b_label = t.get("boundary")
        if b_label not in ("inside", "outside"):
            phase_verdicts["entry_motion"] = {"status": "fail", "reason": "INVALID_BOUNDARY_LABEL_REJECTED"}
            return "INVALID_BOUNDARY_LABEL_REJECTED", False, {
                "detail": f"Target boundary field must be 'inside' or 'outside', got {b_label!r}",
                "phase_verdicts": phase_verdicts,
            }
        if boundary_poly is not None:
            rm = t["room_cm"]
            exp_in = point_in_polygon(float(rm[0]), float(rm[1]), boundary_poly)
            exp_label = "inside" if exp_in else "outside"
            if b_label != exp_label:
                phase_verdicts["entry_motion"] = {
                    "status": "fail",
                    "reason": "BOUNDARY_CLASSIFICATION_MISMATCH_REJECTED",
                }
                return "BOUNDARY_CLASSIFICATION_MISMATCH_REJECTED", False, {
                    "detail": f"Target at room_cm={rm[:2]} has boundary={b_label!r}, expected {exp_label!r} from polygon",
                    "room_cm": rm[:2],
                    "observed_boundary": b_label,
                    "expected_boundary": exp_label,
                    "phase_verdicts": phase_verdicts,
                }

    boundaries = sorted(list({str(t.get("boundary")) for t in advancing_fresh_targets if t.get("boundary") is not None}))
    if not {"inside", "outside"}.issubset(set(boundaries)):
        phase_verdicts["entry_motion"] = {
            "status": "fail",
            "reason": "BOUNDARY_TRAVERSAL_INCOMPLETE_REJECTED",
            "boundaries_observed": boundaries,
        }
        return "BOUNDARY_TRAVERSAL_INCOMPLETE_REJECTED", False, {
            "detail": f"Observation must traverse both 'inside' and 'outside' boundary states; observed only {boundaries}",
            "boundaries_observed": boundaries,
            "phase_verdicts": phase_verdicts,
        }

    phase_verdicts["entry_motion"] = {
        "status": "pass",
        "reason": "ENTRY_MOTION_AND_BOUNDARY_VERIFIED",
        "x_span_cm": round(x_span, 2),
        "y_span_cm": round(y_span, 2),
        "boundaries_observed": boundaries,
    }

    # 9. Stationary retention phase check (R6-01 / R7-01: 2D/3D safe, continuous valid presence=True)
    max_still_dur_ms = 0.0
    max_still_frames = 0
    cur_start_ms: float | None = None
    cur_last_ms: float | None = None
    cur_anchor: list[float] | None = None
    cur_frames = 0
    for idx in range(first_true_idx, last_true_idx + 1):
        r = telemetry_records[idx]
        _, p_val, p_qual, _s = presence_history[idx]
        tgts = [t for t in (r.get("targets") or []) if isinstance(t, dict) and t.get("position_quality") == "valid"]
        if p_val is True and p_qual == "valid" and tgts and _is_finite_num(tgts[0].get("position_ms")):
            # R8-01A: stationary retention is measured on position_ms; frames
            # that repeat the same position sample do not extend the span.
            pms = float(tgts[0]["position_ms"])
            loc = [float(tgts[0]["local_cm"][0]), float(tgts[0]["local_cm"][1])]
            if cur_anchor is None:
                cur_anchor = loc
                cur_start_ms = pms
                cur_last_ms = pms
                cur_frames = 1
            else:
                dist = math.hypot(loc[0] - cur_anchor[0], loc[1] - cur_anchor[1])
                if dist <= 5.0:
                    if cur_last_ms is not None and pms > cur_last_ms:
                        cur_frames += 1
                        cur_last_ms = pms
                    dur = pms - float(cur_start_ms)
                    if cur_frames >= 3 and dur > max_still_dur_ms:
                        max_still_dur_ms = dur
                        max_still_frames = cur_frames
                else:
                    cur_anchor = loc
                    cur_start_ms = pms
                    cur_last_ms = pms
                    cur_frames = 1
        else:
            cur_anchor = None
            cur_start_ms = None
            cur_last_ms = None
            cur_frames = 0

    if max_still_frames < 3 or max_still_dur_ms < float(minimum_still_duration_ms):
        phase_verdicts["still_retention"] = {
            "status": "insufficient",
            "reason": "STILL_PHASE_INSUFFICIENT",
            "max_still_duration_ms": max_still_dur_ms,
            "max_still_frames": max_still_frames,
        }
        return "STILL_PHASE_INSUFFICIENT", False, {
            "detail": (
                f"Stationary presence retention insufficient: max stationary window {max_still_dur_ms}ms "
                f"({max_still_frames} frames), required >= {minimum_still_duration_ms}ms and >= 3 frames"
            ),
            "max_still_duration_ms": max_still_dur_ms,
            "minimum_still_duration_ms": minimum_still_duration_ms,
            "phase_verdicts": phase_verdicts,
        }

    phase_verdicts["still_retention"] = {
        "status": "pass",
        "reason": "STATIONARY_PRESENCE_VERIFIED",
        "still_duration_ms": max_still_dur_ms,
        "still_frames": max_still_frames,
    }

    # 10. Structured phase confirmations & phase-bound telemetry check (R6-01 / R7-01)
    if require_structured_phases or phases is not None:
        exp_dev_id = device_info.get("device_id") if isinstance(device_info, dict) else None
        ok_ph, ph_code, ph_detail = _validate_structured_phases(
            phases,
            frame_ts[0],
            frame_ts[-1],
            t_exit_start,
            telemetry_records=telemetry_records,
            frame_ts=frame_ts,
            minimum_still_duration_ms=float(minimum_still_duration_ms),
            minimum_exit_duration_ms=float(minimum_exit_duration_ms),
            expected_boot_id=boot_before,
            expected_device_id=exp_dev_id,
            expected_run_id=run_id,
            presence_ts=presence_ts,
            presence_hold=presence_hold,
            expected_attempt_id=attempt_id,
            expected_session_id=session_id,
            live_phase_tracker=live_phase_tracker,
        )
        if not ok_ph:
            phase_verdicts["structured_action_confirmation"] = {
                "status": "unconfirmed",
                "reason": ph_code,
                "detail": ph_detail.get("detail"),
            }
            return ph_code, False, {
                "detail": ph_detail.get("detail"),
                "phase_verdicts": phase_verdicts,
            }
        phase_verdicts["structured_action_confirmation"] = {
            "status": "pass",
            "reason": "ALL_PHASES_CONFIRMED",
            "phases": ph_detail,
        }
    else:
        phase_verdicts["structured_action_confirmation"] = {
            "status": "pass",
            "reason": "USER_ACTION_CONFIRMED",
        }

    summary = {
        "record_count": len(telemetry_records),
        "target_count": len(all_targets),
        "fresh_target_count": len(fresh_targets),
        "advancing_fresh_target_count": len(advancing_fresh_targets),
        "coordinate_dimension": 2 if is_2d else 3,
        "x_range": [round(min(xs), 1), round(max(xs), 1)],
        "y_range": [round(min(ys), 1), round(max(ys), 1)],
        "boundaries_observed": boundaries,
        "presence_transition": True,
        "spatial_motion": True,
        "still_retention_confirmed": True,
        "still_duration_ms": max_still_dur_ms,
        "exit_confirmed": True,
        "exit_duration_ms": exit_dur_ms,
        "sustained_exit_frames": len(distinct_tail_ts),
        "phase_verdicts": phase_verdicts,
    }
    return "HUMAN_OBSERVE_PASS", True, summary
