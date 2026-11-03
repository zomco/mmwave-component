#!/usr/bin/env python3
"""Interactive 60s live human observation runner for R60ABD1 on COM9 (G2-03 / B3).

Requirements from verification-plan / g2-hardware-next-stage-2026-10-29 & R6-01:
- Only operates on explicit target port (never defaults).
- Preflights all output paths (.jsonl, .result.json, .manifest.json) BEFORE reading secrets or opening serial I/O.
- Reads and records device identity (DEVICE_INFO), model capabilities (CAPABILITIES_LIST), and full 8-key installation/boundary configuration.
- Captures 3 guided human interaction phases with structured per-phase confirmation (interactive prompt, --phase-confirm-file, or PHASE_CONFIRMER hook):
    Phase 1 (entry): Human enters and walks across boundary -> movement & boundary traversal
    Phase 2 (still): Human sits down / stays still -> stationary presence retention
    Phase 3 (exit):  Human exits radar coverage -> sustained absence >= 10s
- Single boolean --confirm-user-actions alone is NOT sufficient to pass all phases without structured phase confirmation records.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
import uuid
import winsound
from pathlib import Path
from typing import Any, Callable

sys.path.insert(0, str(Path(__file__).resolve().parent))
import mwcp
import run_g2


# Optional testable hook: callable(phase_name: str, start_ms: float, end_ms: float) -> dict | bool
PHASE_CONFIRMER: Callable[[str, float, float], Any] | None = None


def beep_phase():
    try:
        winsound.Beep(1000, 250)
    except Exception:
        pass


def beep_complete():
    try:
        winsound.Beep(1500, 150)
        time.sleep(0.05)
        winsound.Beep(2000, 250)
    except Exception:
        pass


def robust_connect(port: str, evidence: mwcp.EvidenceWriter, max_tries: int = 5, allow_write: bool = False) -> mwcp.Client:
    last_err = None
    for attempt in range(max_tries):
        client = None
        try:
            time.sleep(1.0)
            client = mwcp.Client(port, evidence, allow_write=allow_write)
            time.sleep(0.5)
            client.hello(timeout_ms=10000)
            return client
        except Exception as ex:
            if client is not None:
                client.close()
            last_err = ex
            if attempt < max_tries - 1:
                print(f"    (端口 {port} 连接重试 {attempt + 1}/{max_tries}: {ex}，等待 3s 再次连接...)", flush=True)
                time.sleep(3.0)
            else:
                break
    raise RuntimeError(f"连接串口 {port} 握手失败: {last_err}")


def _confirm_single_phase(
    args: argparse.Namespace,
    phase_name: str,
    phase_label: str,
    tracker_entry: dict[str, Any],
    boot_id: str,
    session_id: int | None,
    device_id: str | None = None,
    attempt_id: str | None = None,
) -> dict[str, Any] | None:
    """Confirm a single phase at live phase completion using real observed timestamps."""
    s_ms = tracker_entry.get("device_start_ms")
    e_ms = tracker_entry.get("device_end_ms")
    if PHASE_CONFIRMER is not None:
        res = PHASE_CONFIRMER(
            phase_name,
            float(s_ms) if s_ms is not None else -1.0,
            float(e_ms) if e_ms is not None else -1.0,
        )
        if isinstance(res, dict):
            out = dict(res)
            out.setdefault("boot_id", boot_id)
            out.setdefault("session_id", session_id)
            out.setdefault("device_id", device_id)
            out.setdefault("attempt_id", attempt_id)
            return out
        if isinstance(res, bool):
            return {
                "confirmed": res,
                "start_ms": s_ms,
                "end_ms": e_ms,
                "confirmed_at_ms": e_ms,
                "host_start_ms": tracker_entry.get("host_start_ms"),
                "host_end_ms": tracker_entry.get("host_end_ms"),
                "host_confirmed_at_ms": int(time.time() * 1000),
                "boot_id": boot_id,
                "session_id": session_id,
                "device_id": device_id,
                "attempt_id": attempt_id,
                "frame_count": len(tracker_entry.get("frame_indices", [])),
                "method": "hook",
            }
        return None

    if getattr(args, "interactive_confirm", False):
        ans = input(f"请确认已完成【{phase_label}】(输入 yes 确认): ").strip().lower()
        confirmed = (ans == "yes")
        # R9-01: the interactive path is a REAL confirmation path and must
        # carry the SAME attempt binding as the hook path — a missing
        # attempt_id here made every genuine interactive run foreign.
        return {
            "confirmed": confirmed,
            "start_ms": s_ms,
            "end_ms": e_ms,
            "confirmed_at_ms": e_ms,
            "host_start_ms": tracker_entry.get("host_start_ms"),
            "host_end_ms": tracker_entry.get("host_end_ms"),
            "host_confirmed_at_ms": int(time.time() * 1000),
            "boot_id": boot_id,
            "session_id": session_id,
            "device_id": device_id,
            "attempt_id": attempt_id,
            "frame_count": len(tracker_entry.get("frame_indices", [])),
            "method": "interactive_prompt",
        }
    return None


# Binding fields every ACCEPTED confirmation path must carry (R9-01): the
# unique attempt identity plus the run's device/boot/session.  A phase
# record lacking them is historical/unbound evidence, never this run's
# human confirmation.
_PHASE_BINDING_FIELDS = ("attempt_id", "session_id", "boot_id", "device_id")


def _bind_imported_phases(
    data: dict,
    attempt_id: str,
    session_id: int | None,
    boot_id: str,
    device_id: str | None,
) -> tuple[dict[str, Any] | None, str | None]:
    """Validate and bind an IMPORTED phase-confirmation document (R9-01).

    Merge rules (wrapper + per-phase, no silent drops):
      - the wrapper top level must declare ``attempt_id`` and ``session_id``
        (the operator copies them from the runner's startup banner);
      - ``boot_id`` / ``device_id`` are required at top level or per phase;
      - a per-phase binding field overrides the wrapper value; if both are
        present and differ -> the whole import is REJECTED (conflict);
      - a phase missing a field inherits the wrapper value; after the merge
        EVERY phase carries all four binding fields matching THIS run;
      - ``method`` is normalised to ``imported_file`` so an imported record
        can never masquerade as a live hook/interactive confirmation (and
        stripping/altering method cannot bypass the binding contract).

    Returns (bound_phases, None) or (None, rejection_reason).
    """
    if not isinstance(data, dict):
        return None, "phase confirmation document is not an object"
    wrapper = {k: data.get(k) for k in _PHASE_BINDING_FIELDS}
    if not wrapper.get("attempt_id"):
        return None, ("imported phase file has no top-level attempt_id - "
                      "unbound historical confirmations are not this run's "
                      "evidence (insufficient)")
    if not wrapper.get("session_id"):
        return None, "imported phase file has no top-level session_id"
    expected = {"attempt_id": attempt_id,
                "session_id": session_id,
                "boot_id": boot_id,
                "device_id": device_id}
    for field, want in expected.items():
        got = wrapper.get(field)
        if got is None:
            return None, (f"imported phase file is missing binding field "
                          f"{field!r} at wrapper level")
        if want is not None and str(got) != str(want):
            return None, (f"imported phase file {field} {got!r} does not "
                          f"match this attempt ({want!r})")
    phases = data.get("phases")
    if not isinstance(phases, dict) or not phases:
        return None, "imported phase file carries no phases object"
    merged: dict[str, Any] = {}
    for name, ph in phases.items():
        if not isinstance(ph, dict):
            return None, f"imported phase {name!r} is not an object"
        out = dict(ph)
        for field, want in expected.items():
            got = out.get(field)
            if got is None:
                got = wrapper.get(field)
            elif want is not None and str(got) != str(want):
                return None, (f"imported phase {name!r} {field} {got!r} "
                              f"conflicts with this attempt ({want!r})")
            if got is None:
                return None, (f"imported phase {name!r} is missing binding "
                              f"field {field!r}")
            out[field] = got
        # method normalisation: bindings are enforced on imported records
        # regardless of method, so removing/altering method cannot bypass.
        out["method"] = "imported_file"
        merged[name] = out
    return merged, None


def _load_phase_confirmations(
    args: argparse.Namespace,
    live_confirmed_phases: dict[str, dict[str, Any]],
    attempt_id: str | None = None,
    session_id: int | None = None,
    boot_id: str | None = None,
    device_id: str | None = None,
) -> tuple[dict[str, Any] | None, str | None]:
    """Load phase confirmations; returns (phases, import_rejection_reason)."""
    if getattr(args, "phase_confirm_file", None):
        p = Path(args.phase_confirm_file)
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            # R9-01: an unreadable import is a precise rejection, never a
            # JUDGE_EXCEPTION and never a silent pass-through.
            return None, f"imported phase file unreadable/invalid JSON: {exc!r}"
        if isinstance(data, dict) and "phases" in data and isinstance(data["phases"], dict):
            # R9-01: imported confirmations must be BOUND to this attempt.
            merged, reason = _bind_imported_phases(
                data, attempt_id or "", session_id, boot_id or "", device_id)
            if merged is None:
                return None, reason
            for k in ("run_id", "host_device_time_mapping"):
                if k in data and k not in merged:
                    merged[k] = data[k]
            return merged, None
        if isinstance(data, dict):
            # legacy whole-document form: entry/still/exit at top level with
            # the binding fields alongside - same contract applies
            legacy = {name: data[name] for name in ("entry", "still", "exit")
                      if isinstance(data.get(name), dict)}
            if not legacy:
                return None, "imported phase file carries no phases object"
            merged, reason = _bind_imported_phases(
                {"phases": legacy, **{k: data.get(k) for k in _PHASE_BINDING_FIELDS
                                      if k in data}},
                attempt_id or "", session_id, boot_id or "", device_id)
            if merged is None:
                return None, reason
            for k in ("run_id", "host_device_time_mapping"):
                if k in data and k not in merged:
                    merged[k] = data[k]
            return merged, None
        return None, "phase confirmation document is not an object"

    if live_confirmed_phases:
        return live_confirmed_phases, None

    return None, None


def main():
    parser = argparse.ArgumentParser(description="60s Live Human Observation Runner for R60ABD1")
    parser.add_argument("--port", required=True, help="Explicit target serial port (never defaulted)")
    parser.add_argument("--seconds", type=int, default=60, help="Observation duration in seconds (default 60)")
    parser.add_argument("--out", default=None, help="Evidence output path")
    parser.add_argument("--reset-radar", action="store_true", default=False,
                        help="Explicitly send radar.reset_module action before observation (requires explicit authorization)")
    parser.add_argument("--confirm-user-actions", action="store_true", default=False,
                        help="Explicitly confirm that physical human walk/still/exit actions were executed")
    parser.add_argument("--phase-confirm-file", default=None,
                        help="Path to JSON file recording structured entry/still/exit phase confirmations and timestamps")
    parser.add_argument("--interactive-confirm", action="store_true", default=False,
                        help="Interactively confirm each phase (entry, still, exit) with timestamps")
    parser.add_argument("--min-exit-ms", type=int, default=10000,
                        help="Minimum sustained exit duration in milliseconds (default 10000)")
    args = parser.parse_args()

    session_dir = Path("tmp/g2-hardware-20261029-session-01/evidence")
    raw_target = Path(args.out) if args.out else session_dir / "b3_human_observe.jsonl"
    out_path, result_path, manifest_path = run_g2.resolve_output_triplet(raw_target)

    # R8-03: establish and EXCLUSIVELY reserve this run's raw/result/manifest
    # BEFORE reading secrets or touching the device. Reservation is exclusive
    # creation via the shared OutputPlan; a pre-existing or racing foreign
    # file aborts with ZERO device I/O and foreign bytes are never modified.
    plan = run_g2.OutputPlan.from_raw_target(raw_target)
    try:
        plan.reserve_all()
    except FileExistsError as exc:
        print(
            f"Error: {exc} Refusing to run (immutable evidence policy G2-HW-R1-B / R8-03).",
            file=sys.stderr,
        )
        return 1

    try:
        controlled, secrets = run_g2.load_secrets()
        # A foreign file may have appeared while secrets were read: re-verify
        # ownership before any device I/O (R8-03 race window).
        plan.verify_triplet_before_io(plan.primary_triplet)
        redactor = mwcp.Redactor(controlled_ssids=controlled, secrets=secrets)
        evidence = plan.open_raw_writer(out_path, redactor)
    except FileExistsError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except Exception:
        plan.cleanup_unfinalized()
        raise

    # R8-01A.5: a unique per-attempt identity (the scenario run_id is a
    # fixed type label and never substitutes for the attempt binding).
    attempt_id = f"human-{uuid.uuid4().hex[:16]}"

    print("============================================================")
    print("  MMWave Web Console G2 · 60 秒真人雷达走动/存在观测 (COM9)")
    print("  雷达型号: R60ABD1 (60GHz 跌倒/呼吸心率多功能人体存在雷达)")
    print(f"  目标端口: {args.port} | 观测时长: {args.seconds} 秒")
    print(f"  证据输出: {out_path}")
    print("============================================================", flush=True)

    print(f"\n[1/3] 连接串口 {args.port} 并初始化雷达模组...", flush=True)
    try:
        client = robust_connect(args.port, evidence, allow_write=bool(args.reset_radar))
    except Exception:
        evidence.close()
        # R9-03.5: one cleanup owner for every error exit (no scattered
        # branches): the plan releases whatever this run still holds.
        plan.cleanup_unfinalized()
        raise

    boot0 = client.boot_id or ""
    print(f"  -> 会话建立: session_id={client.session_id}, boot_id={boot0}", flush=True)

    device_info = {}
    capabilities = {}
    try:
        di_res = client.call("DEVICE_INFO", {}, timeout_ms=3000)
        if isinstance(di_res, dict) and di_res.get("ok") and isinstance(di_res.get("result"), dict):
            device_info = di_res["result"]
    except Exception:
        pass
    try:
        cap_res = client.call("CAPABILITIES_LIST", {}, timeout_ms=3000)
        if isinstance(cap_res, dict) and cap_res.get("ok") and isinstance(cap_res.get("result"), dict):
            capabilities = cap_res["result"]
    except Exception:
        pass
    # R9-01 residual: the operator MUST be able to obtain the current
    # attempt/session/device/boot bindings for an imported confirmation
    # file - print them once the session and device identity are known.
    print("  -> 本次尝试绑定信息（导入确认文件请在 wrapper 顶层原样填写以下字段）:",
          flush=True)
    print(f"     attempt_id={attempt_id}", flush=True)
    print(f"     session_id={client.session_id}", flush=True)
    print(f"     boot_id={boot0}", flush=True)
    print(f"     device_id={device_info.get('device_id')}", flush=True)

    expected_installation = None
    config_revision = None
    try:
        base_cfg, config_revision = run_g2.read_all_config(client)
        if isinstance(base_cfg, dict):
            expected_installation = dict(base_cfg)
    except Exception as cfg_ex:
        print(f"  (读取安装几何配置失败: {cfg_ex})", flush=True)

    # Initialize R60ABD1 module only if explicitly authorized (G2-HW-R3-A item 6)
    if args.reset_radar:
        init_res = client.call("ACTION_START", {
            "action_id": "radar.reset_module",
            "op_id": str(uuid.uuid4()),
            "confirm": "radar.reset_module",
            "params": {}
        }, timeout_ms=5000)
        print(f"  -> 雷达模组初始化指令下发: ok={init_res.get('ok')}", flush=True)
        time.sleep(2.0)
    else:
        print("  -> 跳过 radar.reset_module (观察脚本默认不触发模组复位，需显式 --reset-radar 授权)", flush=True)

    # Subscribe to telemetry & status streams
    sub = client.call("SUBSCRIBE", {
        "streams": [
            {"id": "telemetry", "max_rate_hz": 1},
            {"id": "status", "max_rate_hz": 0.2}
        ],
        "event_budget_bps": 8000
    }, timeout_ms=3000)
    print(f"  -> 订阅成功: ok={sub.get('ok')}", flush=True)

    telemetry_records = []
    presence_states = set()
    targets_seen_total = 0
    speeds_detected = []
    xs, ys, dists = [], [], []
    boot_end = boot0

    print(f"\n[2/3] 准备开始真人分段实时观测（共 {args.seconds} 秒）...", flush=True)
    print("  >>> 请就位！5 秒后开始【阶段 1/3：走动检测】...", flush=True)
    for i in range(5, 0, -1):
        print(f"    [准备倒计时] {i} 秒...", flush=True)
        try:
            winsound.Beep(800, 150)
        except Exception:
            pass
        time.sleep(1.0)
    beep_phase()
    import hardware_judges
    t_start = time.time()
    t_deadline = t_start + args.seconds
    last_phase = 0
    last_ping = time.time()
    p1_end_s = max(1.0, args.seconds * 0.25)
    p2_end_s = max(p1_end_s + 1.0, args.seconds * 0.60)
    phase_names = {1: "entry", 2: "still", 3: "exit"}
    phase_labels = {
        1: "阶段 1/3 进入与走动穿越边界",
        2: "阶段 2/3 静止保持存在",
        3: "阶段 3/3 离开探测区域并保持无人",
    }
    live_phase_tracker: dict[str, dict[str, Any]] = {
        name: {
            "host_start_ms": None,
            "host_end_ms": None,
            "device_start_ms": None,
            "device_end_ms": None,
            "frame_indices": [],
            "source_seqs": [],
        }
        for name in ("entry", "still", "exit")
    }
    live_confirmed_phases: dict[str, dict[str, Any]] = {}
    runner_exception: Exception | None = None
    # R9-01: precise reason when an imported phase file is rejected as
    # unbound/conflicting (never silently accepted, never a crash).
    result_note_import_reject: str | None = None

    try:
        while time.time() < t_deadline:
            now = time.time()
            elapsed_f = now - t_start
            elapsed = int(elapsed_f)

            # Keep session active inside 15s TTL
            if now - last_ping >= 6.0:
                try:
                    client.ping()
                except Exception:
                    pass
                last_ping = now

            # Phase transitions
            current_phase = 1 if elapsed_f < p1_end_s else (2 if elapsed_f < p2_end_s else 3)
            if current_phase != last_phase:
                if last_phase in phase_names:
                    prev_name = phase_names[last_phase]
                    live_phase_tracker[prev_name]["host_end_ms"] = int(now * 1000)
                    conf_rec = _confirm_single_phase(
                        args,
                        prev_name,
                        phase_labels[last_phase],
                        live_phase_tracker[prev_name],
                        client.boot_id or boot0,
                        client.session_id,
                        device_id=device_info.get("device_id"),
                        attempt_id=attempt_id,
                    )
                    if conf_rec is not None:
                        live_confirmed_phases[prev_name] = conf_rec
                last_phase = current_phase
                cur_name = phase_names[current_phase]
                if live_phase_tracker[cur_name]["host_start_ms"] is None:
                    live_phase_tracker[cur_name]["host_start_ms"] = int(now * 1000)
                beep_phase()
                if current_phase == 1:
                    print("\n  ================================================================", flush=True)
                    print("  >>> 【阶段 1/3：走动检测】请进入雷达前方 1~3m 走动！ <<<", flush=True)
                    print("  ================================================================", flush=True)
                elif current_phase == 2:
                    print("\n  ================================================================", flush=True)
                    print("  >>> 【阶段 2/3：静止存在】请坐下或静止站立（微动呼吸）！ <<<", flush=True)
                    print("  ================================================================", flush=True)
                elif current_phase == 3:
                    print("\n  ================================================================", flush=True)
                    print(f"  >>> 【阶段 3/3：离开检测】请离开雷达探测区域（无人）！ <<<", flush=True)
                    print("  ================================================================", flush=True)

            # Drain frames for 1.0 second
            events = client.drain_events(1000)
            for ev in events:
                if ev.get("meta", {}).get("code") == mwcp.CODE["TELEMETRY"]:
                    payload = ev.get("payload", {})
                    frame_idx = len(telemetry_records)
                    telemetry_records.append(payload)
                    cur_name = phase_names.get(last_phase, "entry")
                    tr = live_phase_tracker[cur_name]
                    f_ts = hardware_judges._frame_timestamp_ms(payload)
                    if f_ts is not None:
                        if tr["device_start_ms"] is None:
                            tr["device_start_ms"] = float(f_ts)
                        tr["device_end_ms"] = float(f_ts)
                    tr["frame_indices"].append(frame_idx)
                    if payload.get("source_seq") is not None:
                        tr["source_seqs"].append(payload.get("source_seq"))

                    presence_obj = payload.get("presence")
                    if isinstance(presence_obj, dict):
                        presence_val = presence_obj.get("value")
                        presence_qual = presence_obj.get("quality")
                        presence_repr = f"{presence_val}({presence_qual})"
                    else:
                        presence_val = presence_obj
                        presence_repr = str(presence_obj)
                    presence_states.add(presence_repr)

                    metrics = payload.get("metrics") or {}
                    dist_obj = metrics.get("distance.cm") or {}
                    dist_val = dist_obj.get("value") if isinstance(dist_obj, dict) else None
                    if dist_val is not None:
                        dists.append(dist_val)

                    motion_obj = metrics.get("motion.state") or {}
                    motion_val = motion_obj.get("value") if isinstance(motion_obj, dict) else None

                    br_obj = metrics.get("breath_rate") or {}
                    br_val = br_obj.get("value") if isinstance(br_obj, dict) else None

                    hr_obj = metrics.get("heart_rate") or {}
                    hr_val = hr_obj.get("value") if isinstance(hr_obj, dict) else None

                    speed_metric = metrics.get("speed.cm_s") or {}
                    if isinstance(speed_metric, dict) and speed_metric.get("value") is not None:
                        speeds_detected.append(speed_metric.get("value"))

                    targets = payload.get("targets") or []
                    targets_seen_total += len(targets)

                    target_str = "无人"
                    if targets:
                        t0 = targets[0]
                        loc = t0.get("local_cm")
                        if isinstance(loc, list) and len(loc) >= 2:
                            tx, ty = loc[0], loc[1]
                        else:
                            tx = t0.get("x_cm")
                            ty = t0.get("y_cm")
                        td = t0.get("distance_cm") or dist_val
                        spd = t0.get("speed_cm_s")
                        bnd = t0.get("boundary")
                        if spd is not None:
                            speeds_detected.append(spd)
                        if tx is not None:
                            xs.append(tx)
                        if ty is not None:
                            ys.append(ty)
                        if td is not None and td not in dists:
                            dists.append(td)
                        target_str = f"目标数={len(targets)} (x={tx}cm, y={ty}cm, dist={td}cm, 边界={bnd})"
                    elif dist_val is not None:
                        target_str = f"探测距离={dist_val}cm (状态={motion_val or '检测中'})"

                    signs_str = f"呼吸={br_val if br_val is not None else '-'}bpm, 心率={hr_val if hr_val is not None else '-'}bpm"

                    print(f"  [T+{elapsed:02d}s] presence={presence_repr:<16} | {target_str:<32} | {signs_str}", flush=True)

        if last_phase in phase_names:
            final_name = phase_names[last_phase]
            live_phase_tracker[final_name]["host_end_ms"] = int(time.time() * 1000)
            conf_rec = _confirm_single_phase(
                args,
                final_name,
                phase_labels[last_phase],
                live_phase_tracker[final_name],
                client.boot_id or boot0,
                client.session_id,
                device_id=device_info.get("device_id"),
                attempt_id=attempt_id,
            )
            if conf_rec is not None:
                live_confirmed_phases[final_name] = conf_rec

        # Unsubscribe cleanly
        print("\n[3/3] 观测结束，退订遥测流并断开连接...", flush=True)
        try:
            unsub = client.call("UNSUBSCRIBE", {"streams": ["telemetry", "status"]}, timeout_ms=3000)
            print(f"  -> 退订结果: ok={unsub.get('ok')}", flush=True)
        except Exception as ex:
            print(f"  (退订通知: {ex})", flush=True)
        boot_end = client.boot_id or boot0
    except Exception as exc:
        runner_exception = exc
    finally:
        client.close()

    t_end = time.time()
    beep_complete()

    try:
        sample_ts = [
            hardware_judges._frame_timestamp_ms(r)
            for r in telemetry_records
            if hardware_judges._frame_timestamp_ms(r) is not None
        ]
        t_dev_first = float(sample_ts[0]) if sample_ts else 0.0
        t_dev_last = float(sample_ts[-1]) if sample_ts else 0.0

        phases, import_reject_reason = _load_phase_confirmations(
            args, live_confirmed_phases,
            attempt_id=attempt_id,
            session_id=getattr(client, "session_id", None) if client is not None else None,
            boot_id=boot_end or boot0,
            device_id=device_info.get("device_id"))
        if import_reject_reason:
            # R9-01: an unbound/conflicting import is explicitly insufficient
            # evidence for THIS run - recorded, never silently accepted.
            result_note_import_reject = import_reject_reason
        else:
            result_note_import_reject = None
        user_action_confirmed = bool(getattr(args, "confirm_user_actions", False)) or (phases is not None)
        min_exit_ms = int(getattr(args, "min_exit_ms", 10000))

        boot_intact = bool(boot0) and (boot_end == boot0)
        speed_null_passed = (len(speeds_detected) == 0)
        seqs = [r.get("source_seq") for r in telemetry_records if r.get("source_seq") is not None]
        seq_monotonic = (len(set(seqs)) > 1) and all(b >= a for a, b in zip(seqs, seqs[1:])) if seqs else False

        host_device_time_mapping = {
            "host_start_epoch_ms": int(t_start * 1000),
            "host_end_epoch_ms": int(t_end * 1000),
            "device_first_sample_ms": t_dev_first if sample_ts else None,
            "device_last_sample_ms": t_dev_last if sample_ts else None,
            "estimated_offset_ms": (int(t_start * 1000) - t_dev_first) if sample_ts else None,
            "live_phase_tracker": live_phase_tracker,
        }

        # R9-01 residual: stamp the ACTUAL live-tracker evidence into every
        # confirmation (live or imported) so the judge can verify each phase
        # against what this run really captured - identity alone is not
        # stage-completion evidence.
        if phases:
            for _pname, _ph in phases.items():
                if not isinstance(_ph, dict):
                    continue
                _tr = live_phase_tracker.get(_pname) or {}
                _ph["tracker_frame_count"] = len(_tr.get("frame_indices") or [])
                _ph["tracker_source_seqs"] = list(_tr.get("source_seqs") or [])
                _ph["tracker_device_start_ms"] = _tr.get("device_start_ms")
                _ph["tracker_device_end_ms"] = _tr.get("device_end_ms")

        judge_input_doc = {
            "run_id": "g2-03-human-observe",
            "attempt_id": attempt_id,
            "session_id": client.session_id if client is not None else None,
            "telemetry_records": telemetry_records,
            "boot_before": boot0,
            "boot_after": boot_end,
            "user_action_confirmed": user_action_confirmed,
            "phases": phases,
            "require_structured_phases": True,
            "expected_installation": expected_installation if expected_installation is not None else {},
            "minimum_exit_duration_ms": min_exit_ms,
            "device_info": device_info,
            "capabilities": capabilities,
            "host_device_time_mapping": host_device_time_mapping,
        }

        if runner_exception is not None:
            verdict = "RUNNER_EXCEPTION_REJECTED"
            judge_ok = False
            judge_detail = {"detail": f"Collection interrupted by exception: {runner_exception}"}
        else:
            verdict, judge_ok, judge_detail = hardware_judges.judge_human_observation(
                judge_input_doc,
                min_records=30,
            )
    except Exception as exc:
        verdict = "JUDGE_EXCEPTION_REJECTED"
        judge_ok = False
        judge_detail = {"detail": f"Judge raised unexpected exception: {exc}"}
        boot_intact = bool(boot0) and (boot_end == boot0)
        speed_null_passed = (len(speeds_detected) == 0)
        seq_monotonic = False
        phases = None
        user_action_confirmed = False
        min_exit_ms = int(getattr(args, "min_exit_ms", 10000))
        host_device_time_mapping = {}
        result_note_import_reject = None

    passed = (
        runner_exception is None
        and len(telemetry_records) >= 30
        and boot_intact
        and speed_null_passed
        and seq_monotonic
        and bool(judge_ok)
    )

    try:
        evidence.note({
            "kind": "human_observation_summary",
            "verdict": verdict,
            "passed": passed,
            "phases": phases,
            "phase_verdicts": judge_detail.get("phase_verdicts") if isinstance(judge_detail, dict) else None,
            "host_device_time_mapping": host_device_time_mapping,
        })
    finally:
        evidence_summary = evidence.close()

    summary = {
        "run_id": "g2-03-human-observe",
        "attempt_id": attempt_id,
        "phase_import_rejected": result_note_import_reject,
        "status": "pass" if passed else "fail",
        "verdict": verdict,
        "judge_detail": judge_detail,
        "phase_verdicts": judge_detail.get("phase_verdicts") if isinstance(judge_detail, dict) else None,
        "phases": phases,
        "user_action_confirmed": user_action_confirmed,
        "device_id": device_info.get("device_id"),
        "firmware_sha256": device_info.get("firmware_sha256"),
        "device_info": device_info,
        "capabilities": capabilities,
        "config_revision": config_revision,
        "expected_installation": expected_installation,
        "host_device_time_mapping": host_device_time_mapping,
        "minimum_exit_duration_ms": min_exit_ms,
        "duration_seconds": args.seconds,
        "frames_received": len(telemetry_records),
        "presence_states_seen": sorted(list(presence_states)),
        "targets_total_seen": targets_seen_total,
        "x_range_cm": [min(xs), max(xs)] if xs else None,
        "y_range_cm": [min(ys), max(ys)] if ys else None,
        "dist_range_cm": [min(dists), max(dists)] if dists else None,
        "r60_speed_null_check": speed_null_passed,
        "source_seq_monotonic": seq_monotonic,
        "device_spontaneous_reset": not boot_intact,
    }
    result_doc = {
        **summary,
        "evidence": evidence_summary,
    }

    # R8-03: consistent multi-file finalisation through the shared
    # OutputPlan.  Both reservations are verified before anything is
    # written; any lost reservation or storage failure downgrades the
    # result to STORAGE_FINALIZE_FAILED (never a残留 pass), foreign files
    # are never touched, and a *.collision-*.diag.json diagnostic is left.
    def _manifest_builder(res_obj: dict, res_sha: str | None) -> dict:
        return {
            "run_id": "g2-03-human-observe",
            "status": res_obj.get("status"),
            "verdict": res_obj.get("verdict"),
            "raw_file": str(out_path),
            "raw_sha256": (evidence_summary or {}).get("sha256"),
            "result_file": str(result_path),
            "result_sha256": res_sha,
        }

    finalize_ok, result_doc, diag_path = plan.finalize_result_and_manifest(
        result_path, result_doc, manifest_path, _manifest_builder)
    if not finalize_ok:
        print(
            f"\n[ERROR] 存储 finalization 失败，本次结果不可作为验收证据: "
            f"{result_doc.get('storage_error')}"
            + (f" | 诊断: {diag_path}" if diag_path else ""),
            file=sys.stderr,
        )
        return 1

    print("\n============================================================")
    print("  真人雷达走动/存在观测完成报告")
    print(f"  总接收遥测帧: {len(telemetry_records)} | 捕获状态集合: {summary['presence_states_seen']}")
    if xs and ys:
        dist_info = f"[{min(dists)}, {max(dists)}] cm" if dists else "N/A"
        print(f"  坐标范围: X [{min(xs)}, {max(xs)}] cm, Y [{min(ys)}, {max(ys)}] cm, 距离 {dist_info}")
    print(f"  R60 占位速度为 null: {speed_null_passed} | 序列号单调: {seq_monotonic} | 无异常重启: {boot_intact}")
    print(f"  最终判定: [{'PASS' if passed else 'FAIL'}] ({verdict})")
    print(f"  证据文件: {out_path} (SHA-256: {evidence_summary.get('sha256')})")
    print("============================================================", flush=True)

    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
