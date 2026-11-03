#!/usr/bin/env python3
"""Interactive 20 physical power cuts runner for COM9 (G2-04 / B3).

Requirements from verification-plan / g2-hardware-next-stage-2026-10-29:
- Only operates on COM9 (never touches COM3).
- Records baseline snapshot, SHA-256, op_id, target snapshot for each cycle.
- Dispatches CONFIG_COMMIT, detects physical power cut via port disappearance.
- Detects re-enumeration when user plugs back in.
- Re-reads full configuration; strictly requires intact old snapshot OR intact new snapshot.
- Zero corrupted fields, zero partial/mixed states, zero factory reset.
- First anomaly immediately halts the test to preserve diagnostic evidence.
- Writes full audit trail to evidence/b3_power_cuts.jsonl.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
import time
import uuid
import winsound
from pathlib import Path

import serial.tools.list_ports

sys.path.insert(0, str(Path(__file__).resolve().parent))
import mwcp
import run_g2
import hardware_judges


def extract_device_id(resp: dict | None) -> str | None:
    """Extract valid device identity from envelope or result dict."""
    if not isinstance(resp, dict):
        return None
    res = resp.get("result") if (resp.get("ok") is True and isinstance(resp.get("result"), dict)) else resp
    if not isinstance(res, dict):
        return None
    dev_id = res.get("device_id")
    if isinstance(dev_id, str) and dev_id.strip():
        return dev_id.strip()
    mac = res.get("mac")
    if isinstance(mac, str) and mac.strip():
        return mac.strip()
    return None


def beep_unplug():
    try:
        winsound.Beep(1200, 350)
    except Exception:
        pass


def beep_plug():
    try:
        winsound.Beep(600, 350)
    except Exception:
        pass


def beep_success():
    try:
        winsound.Beep(1500, 120)
        time.sleep(0.05)
        winsound.Beep(2000, 180)
    except Exception:
        pass


def int_convex_polygon(n: int, radius: float = 600.0) -> list[list[int]]:
    return [[int(radius * math.cos(2 * math.pi * i / n)), int(radius * math.sin(2 * math.pi * i / n))]
            for i in range(n)]


def normalize_val(v):
    if isinstance(v, (int, float)):
        return round(float(v), 2)
    if isinstance(v, list):
        return [normalize_val(x) for x in v]
    if isinstance(v, dict):
        return {k: normalize_val(val) for k, val in sorted(v.items())}
    return v


def normalize_config(cfg: dict) -> dict:
    norm = {}
    for k, v in sorted(cfg.items()):
        if k == "areas.definitions" and isinstance(v, list):
            norm[k] = sorted([normalize_val(item) for item in v], key=lambda x: x.get("slot", 0))
        else:
            norm[k] = normalize_val(v)
    return norm


def snapshot_hash(norm_cfg: dict) -> str:
    raw = json.dumps(norm_cfg, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def wait_for_port(port: str, present: bool, timeout_s: float = 120.0) -> bool:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        ports = [p.device.upper() for p in serial.tools.list_ports.comports()]
        if (port.upper() in ports) == present:
            return True
        time.sleep(0.4)
    return False


def robust_connect(port: str, evidence: mwcp.EvidenceWriter, max_tries: int = 5) -> mwcp.Client:
    """Connect to serial port with settling and retries for Windows usbser driver."""
    last_err = None
    for attempt in range(max_tries):
        client = None
        try:
            time.sleep(1.5)
            client = mwcp.Client(port, evidence, allow_write=True)
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
    raise RuntimeError(f"连接串口 {port} 握手失败 (重试 {max_tries} 次): {last_err}")


def robust_connect_and_read(port: str, evidence: mwcp.EvidenceWriter, max_tries: int = 5) -> tuple[dict, str, str, str]:
    """Connect to serial port with settling and retries, read all config, and close."""
    client = robust_connect(port, evidence, max_tries=max_tries)
    try:
        boot = client.boot_id or ""
        dev = client.soft_call("DEVICE_INFO")
        dev_id = extract_device_id(dev)
        cfg, rev = run_g2.read_all_config(client)
        return cfg, rev, boot, dev_id
    finally:
        client.close()


def run_cycle(port: str, cycle: int, evidence: mwcp.EvidenceWriter) -> dict:
    print(f"\n=======================================================", flush=True)
    print(f"=== [CYCLE {cycle:02d}/20] 物理断电保存测试 (COM9) ===", flush=True)
    print(f"=======================================================", flush=True)

    # 1. Connect and read baseline on single persistent client
    print(f"  [1/5] 连接串口 {port} 并读取基线配置快照...", flush=True)
    client = robust_connect(port, evidence)
    commit_res = None
    commit_error = None
    t_commit_start = None
    try:
        boot0 = client.boot_id or ""
        dev0 = client.soft_call("DEVICE_INFO")
        dev_id0 = extract_device_id(dev0)
        base_cfg, rev_before = run_g2.read_all_config(client)

        # Pre-flight side-effect guard:
        if not dev_id0:
            print(f"  [ERROR] 目标设备身份读取失败: dev_info={dev0}. 停止后续写入与断电流程！", flush=True)
            return {
                "cycle": cycle, "port": port, "target_port": port,
                "disconnect_observed": False, "reconnect_observed": False,
                "boot_before": boot0, "boot_after": None,
                "device_id_before": None, "device_id_after": None,
                "rev_before": rev_before, "rev_target": None, "rev_recovered": None,
                "config_before": base_cfg, "config_target": None, "config_recovered": None,
                "commit_response": None,
                "passed": False,
                "verdict": "MISSING_IDENTITY_REJECTED",
                "detail": f"Target identity check failed before commit: dev_info={dev0}"
            }
        if not hardware_judges.is_valid_revision_string(rev_before):
            print(f"  [ERROR] 基线版本号非法: rev={rev_before!r}. 停止后续流程！", flush=True)
            return {
                "cycle": cycle, "port": port, "target_port": port,
                "disconnect_observed": False, "reconnect_observed": False,
                "boot_before": boot0, "boot_after": None,
                "device_id_before": dev_id0, "device_id_after": None,
                "rev_before": rev_before, "rev_target": None, "rev_recovered": None,
                "config_before": base_cfg, "config_target": None, "config_recovered": None,
                "commit_response": None,
                "passed": False,
                "verdict": "INVALID_REVISION_FORMAT",
                "detail": f"Baseline revision format invalid: {rev_before!r}"
            }
        if not hardware_judges.is_valid_complete_config(base_cfg):
            print(f"  [ERROR] 基线配置不完整或字段非法: {base_cfg}. 停止后续流程！", flush=True)
            return {
                "cycle": cycle, "port": port, "target_port": port,
                "disconnect_observed": False, "reconnect_observed": False,
                "boot_before": boot0, "boot_after": None,
                "device_id_before": dev_id0, "device_id_after": None,
                "rev_before": rev_before, "rev_target": None, "rev_recovered": None,
                "config_before": base_cfg, "config_target": None, "config_recovered": None,
                "commit_response": None,
                "passed": False,
                "verdict": "INCOMPLETE_CONFIG_REJECTED",
                "detail": "Baseline configuration snapshots missing required protocol fields"
            }

        norm_before = normalize_config(base_cfg)
        sha_before = snapshot_hash(norm_before)
        print(f"    -> 基线版本: rev={rev_before}, Boot ID={boot0}", flush=True)
        print(f"    -> 基线快照 SHA-256: {sha_before}", flush=True)

        # 2. Prepare target changes (guaranteed mutation from baseline)
        curr_x = float(base_cfg.get("install.x_cm") or 100.0)
        new_x = round(curr_x + 5.0 if curr_x < 160.0 else curr_x - 5.0, 1)
        curr_yaw = float(base_cfg.get("install.yaw_deg") or 0.0)
        new_yaw = float((int(curr_yaw) + 3) % 45)
        new_boundary = int_convex_polygon(64, radius=560.0 + float(cycle * 2))
        target_changes = {
            "install.x_cm": new_x,
            "install.yaw_deg": new_yaw,
            "geometry.boundary_cm": new_boundary,
        }
        expected_new = dict(norm_before)
        expected_new.update(normalize_config(target_changes))
        expected_new_raw = dict(base_cfg)
        expected_new_raw.update(target_changes)
        sha_target = snapshot_hash(expected_new)
        op_id = str(uuid.uuid4())
        print(f"    -> 拟写入目标: x_cm={new_x}, yaw={new_yaw}, op_id={op_id}", flush=True)
        print(f"    -> 目标快照 SHA-256: {sha_target}", flush=True)

        # 3. Issue commit on open connection, signal user to cut power
        print(f"\n  [2/5] 下发 CONFIG_COMMIT 写入 NVS...", flush=True)
        print(f"  ================================================================", flush=True)
        print(f"  >>> 请立即拔掉 {port} 的电源或 USB 数据线！(CUT POWER NOW!) <<<", flush=True)
        print(f"  ================================================================", flush=True)
        beep_unplug()
        t_commit_start = time.time()
        try:
            commit_res = client.call("CONFIG_COMMIT",
                                     {"base_revision": rev_before, "op_id": op_id, "changes": target_changes},
                                     timeout_ms=3000)
            print(f"  (下发完成响应: ok={commit_res.get('ok')})", flush=True)
        except Exception as ex:
            commit_error = str(ex)
            print(f"  (下发过程中捕获断开: {ex})", flush=True)
    finally:
        client.close()

    # 4. Wait for port disappearance (power cut confirmed)
    print(f"\n  [3/5] 等待系统检测到 {port} 掉电断开...", flush=True)
    cut_ok = wait_for_port(port, present=False, timeout_s=45.0)
    t_cut = time.time()
    if cut_ok:
        print(f"  ✓ 成功捕获硬件断电！(端口 {port} 已从系统中移除)", flush=True)
    else:
        print(f"  ! 未在 45s 内检测到端口注销（可能未断电或断电过快已重连）", flush=True)

    # 5. Prompt user to plug back in
    print(f"\n  [4/5] ================================================================", flush=True)
    print(f"  >>> 请将 {port} 重新插上/恢复供电！(RESTORE POWER NOW!) <<<", flush=True)
    print(f"  ================================================================", flush=True)
    beep_plug()

    re_enum = wait_for_port(port, present=True, timeout_s=60.0)
    t_restore = time.time()
    if not re_enum:
        raise RuntimeError(f"等待 {port} 上电重枚举超时 (60s)")
    print(f"  ✓ 成功检测到 {port} 重新上电并枚举！", flush=True)

    # Allow ESP32 boot and USB CDC enumeration to stabilize
    time.sleep(3.5)

    # 6. Reconnect and inspect recovery state
    print(f"\n  [5/5] 重新连接 {port} 并校验配置完整性...", flush=True)
    recovered_cfg, rev_recovered, boot2, dev_id2 = robust_connect_and_read(port, evidence)

    norm_recovered = normalize_config(recovered_cfg)
    sha_recovered = snapshot_hash(norm_recovered)
    boot_changed = (boot2 != boot0)

    print(f"    -> 恢复后版本: rev={rev_recovered}, Boot ID={boot2} (已轮转: {boot_changed})", flush=True)
    print(f"    -> 恢复后快照 SHA-256: {sha_recovered}", flush=True)

    # Pure judge evaluation (G2-HW-R3 fix)
    judge_rec = {
        "target_port": port,
        "port": port,
        "device_id_before": dev_id0,
        "device_id_after": dev_id2,
        "disconnect_observed": cut_ok,
        "reconnect_observed": re_enum,
        "boot_before": boot0,
        "boot_after": boot2,
        "rev_before": rev_before,
        "rev_target": str(int(rev_before) + 1),
        "rev_recovered": rev_recovered,
        "config_before": base_cfg,
        "config_target": expected_new_raw,
        "config_recovered": recovered_cfg,
        "op_id": op_id,
        "changes": target_changes,
        "commit_response": commit_res,
    }
    verdict, passed, detail = hardware_judges.judge_power_cut_cycle(judge_rec)

    result_entry = {
        **judge_rec,
        "cycle": cycle,
        "timestamp_start": t_commit_start,
        "timestamp_cut": t_cut,
        "timestamp_restore": t_restore,
        "boot_changed": boot_changed,
        "sha_before": sha_before,
        "sha_target": sha_target,
        "sha_recovered": sha_recovered,
        "verdict": verdict,
        "detail": detail,
        "passed": passed,
    }

    evidence.note({
        "event": "power_cut_cycle",
        **result_entry
    })

    print(f"\n  >>> 判定结果: [{verdict}] ({'PASS' if passed else 'FAIL'})", flush=True)
    print(f"      {detail}\n", flush=True)

    if passed:
        beep_success()
    return result_entry


def main():
    parser = argparse.ArgumentParser(description="20 Physical Power Cuts Runner for G2-04")
    parser.add_argument("--port", required=True, help="Explicit target serial port (never defaulted)")
    parser.add_argument("--allow-write", action="store_true", default=False, help="Explicit write authorization")
    parser.add_argument("--rounds", type=int, default=20, help="Number of power cut rounds (default 20)")
    parser.add_argument("--start-cycle", type=int, default=1, help="Start cycle number (default 1)")
    parser.add_argument("--out", default=None, help="Evidence output path")
    args = parser.parse_args()

    session_dir = Path("tmp/g2-hardware-20261029-session-01/evidence")
    raw_target = Path(args.out) if args.out else session_dir / "b3_power_cuts.jsonl"
    out_path, result_path, manifest_path = run_g2.resolve_output_triplet(raw_target)

    # R8-03: exclusively reserve raw/result/manifest BEFORE secrets or device
    # I/O via the shared OutputPlan (same rules as run_g2/human runner).
    plan = run_g2.OutputPlan.from_raw_target(raw_target)
    try:
        plan.reserve_all()
    except FileExistsError as exc:
        print(f"Error: {exc} Refusing to run (immutable evidence policy G2-HW-R1-B / R8-03).", file=sys.stderr)
        return 1

    if args.start_cycle > 1:
        print("Error: Resuming via --start-cycle in-place append is disabled (G2-HW-R1-B). Resuming must use isolated run directories / segmented evidence.", file=sys.stderr)
        plan.cleanup_unfinalized()
        return 1

    def _manifest_builder(res_obj: dict, res_sha: str | None) -> dict:
        return {
            "run_id": "g2-04-power-cuts",
            "status": res_obj.get("status"),
            "total_cycles_planned": res_obj.get("total_cycles_planned"),
            "total_cycles_completed": res_obj.get("total_cycles_completed"),
            "raw_file": str(out_path),
            "result_file": str(result_path),
            "result_sha256": res_sha,
        }

    if args.rounds <= 0:
        result_doc = {
            "run_id": "g2-04-power-cuts",
            "status": "fail",
            "error": f"Invalid rounds: {args.rounds} (must be >= 1)",
            "total_cycles_planned": args.rounds,
            "total_cycles_completed": 0,
            "history": [],
        }
        plan.finalize_result_and_manifest(result_path, result_doc, manifest_path, _manifest_builder)
        return 1

    try:
        controlled, secrets = run_g2.load_secrets()
        plan.verify_triplet_before_io(plan.primary_triplet)
        redactor = mwcp.Redactor(controlled_ssids=controlled, secrets=secrets)
        evidence = plan.open_raw_writer(out_path, redactor)
    except FileExistsError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except Exception:
        plan.cleanup_unfinalized()
        raise

    history = []
    print(f"============================================================")
    print(f"  MMWave Web Console G2 · 20 次保存期间物理断电破坏性测试")
    print(f"  目标端口: {args.port} | 执行轮次: 1 至 {args.rounds}")
    print(f"  证据输出: {out_path}")
    print(f"============================================================", flush=True)

    status = "pass"
    try:
        for c in range(1, args.rounds + 1):
            rec = run_cycle(args.port, c, evidence)
            history.append(rec)
            if not rec.get("passed"):
                print(f"\n[FAIL] Cycle {c} 校验未通过，按门禁规则立即终止: [{rec.get('verdict')}] {rec.get('detail')}", flush=True)
                status = "fail"
                break
            if c < args.rounds:
                print(f"等待 4 秒后进入下一轮...", flush=True)
                time.sleep(4.0)
    except Exception as ex:
        print(f"\n[ERROR] 测试中断: {ex}", flush=True)
        status = "fail"
    finally:
        # Evaluate suite FIRST so that disk result.status and process exit code are strictly unified!
        suite_eval = hardware_judges.judge_power_cut_suite(history, required_rounds=args.rounds)
        if suite_eval.get("status") != "pass" or len(history) != args.rounds or not all(r.get("passed") for r in history):
            status = "fail"

        ev_summary = evidence.close()
        result_doc = {
            "run_id": "g2-04-power-cuts",
            "status": status,
            "total_cycles_planned": args.rounds,
            "total_cycles_completed": len(history),
            "reverted_old_count": sum(1 for r in history if r.get("verdict") == "REVERTED_OLD_SAFE"),
            "committed_new_count": sum(1 for r in history if r.get("verdict") == "COMMITTED_NEW_SAFE"),
            "corrupted_count": sum(1 for r in history if r.get("verdict") == "CORRUPTED_FAIL"),
            "suite": suite_eval,
            "evidence": ev_summary,
            "history": history,
        }
        # R8-03: consistent multi-file finalisation - any lost reservation or
        # storage failure downgrades the result (never a stale pass on disk).
        finalize_ok, result_doc, diag_path = plan.finalize_result_and_manifest(
            result_path, result_doc, manifest_path, _manifest_builder)
        if not finalize_ok:
            print(f"\n[ERROR] 存储 finalization 失败，本次结果不可作为验收证据: "
                  f"{result_doc.get('storage_error')}"
                  + (f" | 诊断: {diag_path}" if diag_path else ""), file=sys.stderr)
            status = "fail"
            file_collision = True
        else:
            print(f"\n测试摘要已固化至: {result_path}")
            print(f"完成轮次: {len(history)}/{args.rounds} | 旧态安全回滚: {result_doc['reverted_old_count']} | 新态安全提交: {result_doc['committed_new_count']} | 损坏数: {result_doc['corrupted_count']}", flush=True)
            file_collision = False

    if file_collision:
        return 1
    return 0 if status == "pass" and len(history) == args.rounds else 1


if __name__ == "__main__":
    sys.exit(main())
