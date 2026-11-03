#!/usr/bin/env python3
"""Interactive 5 physical USB hot-unplug / replug runner for COM9 (G2-01 / G2-03 / B3).

Requirements from verification-plan / g2-hardware-next-stage-2026-10-29:
- Only operates on COM9 (never touches COM3).
- Fixed 5 cycles of physical USB cable unplug during active communication.
- Host detects port disappearance / disconnection error.
- Host detects USB re-enumeration upon cable reinsertion.
- Verifies new session establishment, boot_id rotation (power cycle confirmation),
  and RPC recovery with intact configuration.
- Writes full audit trail to tmp/g2-hardware-20261029-session-01/evidence/b3_usb_unplug.jsonl.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
import winsound
from pathlib import Path

import serial
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


def wait_for_port(port: str, present: bool, timeout_s: float = 60.0) -> bool:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        ports = [p.device.upper() for p in serial.tools.list_ports.comports()]
        if (port.upper() in ports) == present:
            return True
        time.sleep(0.3)
    return False


def robust_connect(port: str, evidence: mwcp.EvidenceWriter, max_tries: int = 5) -> mwcp.Client:
    """Connect to serial port with settling and retries for Windows usbser driver."""
    last_err = None
    for attempt in range(max_tries):
        client = None
        try:
            time.sleep(1.5)
            client = mwcp.Client(port, evidence, allow_write=False)
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


def run_cycle(port: str, cycle: int, evidence: mwcp.EvidenceWriter) -> dict:
    print(f"\n=======================================================", flush=True)
    print(f"=== [CYCLE {cycle:02d}/05] 物理 USB 拔插恢复测试 (COM9) ===", flush=True)
    print(f"=======================================================", flush=True)

    # 1. Connect and start active RPC session
    print(f"  [1/4] 连接串口 {port} 并建立活跃通信会话...", flush=True)
    client = robust_connect(port, evidence)
    boot0 = client.boot_id or ""
    session0 = client.session_id
    print(f"    -> 初始会话已建立: session_id={session0}, boot_id={boot0}", flush=True)

    # Perform active ping and baseline config read
    ping0 = client.ping()
    uptime0 = ping0.get("uptime_ms", 0) if isinstance(ping0, dict) else 0
    print(f"    -> 活跃 PING 正常: uptime_ms={uptime0}, RTT={round(client.last_rtt_ms or 0, 1)}ms", flush=True)
    dev0 = client.soft_call("DEVICE_INFO")
    dev_id0 = extract_device_id(dev0)
    cfg0, rev0 = {}, "1"
    try:
        cfg0, rev0 = run_g2.read_all_config(client)
    except Exception as cfg_err:
        pass

    # Pre-flight side-effect guard:
    if not dev_id0:
        print(f"  [ERROR] 目标设备身份读取失败: dev_info={dev0}. 停止后续拔插流程！", flush=True)
        return {
            "cycle": cycle, "port": port, "target_port": port,
            "disconnect_observed": False, "reconnect_observed": False,
            "boot_before": boot0, "boot_after": None,
            "session_before": session0, "session_after": None,
            "device_id_before": None, "device_id_after": None,
            "rev_before": rev0, "rev_after": None,
            "config_before": cfg0, "config_after": None,
            "ping_after": None,
            "passed": False,
            "verdict": "MISSING_IDENTITY_REJECTED",
            "detail": f"Target identity check failed: dev_info={dev0}"
        }
    if not hardware_judges.is_valid_revision_string(rev0):
        print(f"  [ERROR] 基线版本号非法: rev={rev0!r}. 停止后续流程！", flush=True)
        return {
            "cycle": cycle, "port": port, "target_port": port,
            "disconnect_observed": False, "reconnect_observed": False,
            "boot_before": boot0, "boot_after": None,
            "session_before": session0, "session_after": None,
            "device_id_before": dev_id0, "device_id_after": None,
            "rev_before": rev0, "rev_after": None,
            "config_before": cfg0, "config_after": None,
            "ping_after": None,
            "passed": False,
            "verdict": "INVALID_REVISION_FORMAT",
            "detail": f"Baseline revision format invalid: {rev0!r}"
        }
    if not hardware_judges.is_valid_complete_config(cfg0):
        print(f"  [ERROR] 基线配置不完整或字段非法: {cfg0}. 停止后续流程！", flush=True)
        return {
            "cycle": cycle, "port": port, "target_port": port,
            "disconnect_observed": False, "reconnect_observed": False,
            "boot_before": boot0, "boot_after": None,
            "session_before": session0, "session_after": None,
            "device_id_before": dev_id0, "device_id_after": None,
            "rev_before": rev0, "rev_after": None,
            "config_before": cfg0, "config_after": None,
            "ping_after": None,
            "passed": False,
            "verdict": "INCOMPLETE_CONFIG_REJECTED",
            "detail": "Baseline configuration snapshots missing required protocol fields"
        }

    # 2. Prompt user to physically unplug USB cable
    print(f"\n  [2/4] 保持活跃通信状态下，提示物理断开 USB 数据线...", flush=True)
    print(f"  ================================================================", flush=True)
    print(f"  >>> 请立即拔掉 {port} 的 USB 数据线！(UNPLUG USB CABLE NOW!) <<<", flush=True)
    print(f"  ================================================================", flush=True)
    beep_unplug()
    t_unplug_prompt = time.time()

    # Active communication loop until I/O failure or port disappearance
    io_error_caught = None
    t_disconnect = None
    try:
        # Send pings until error or 25 seconds
        for _ in range(50):
            time.sleep(0.3)
            try:
                client.ping()
            except Exception as ex:
                io_error_caught = str(ex)
                t_disconnect = time.time()
                print(f"  ✓ 成功捕获通信物理中断异常: {ex}", flush=True)
                break
    finally:
        client.close()

    # Ensure port is removed from Windows device list
    if not t_disconnect:
        t_disconnect = time.time()
    cut_ok = wait_for_port(port, present=False, timeout_s=30.0)
    if cut_ok:
        print(f"  ✓ 成功检测到系统设备已注销 {port}！", flush=True)
    else:
        print(f"  ! 端口 {port} 仍存在于系统列表中（可能插拔过快或未真正断开）", flush=True)

    # 3. Prompt user to re-plug USB cable
    print(f"\n  [3/4] ================================================================", flush=True)
    print(f"  >>> 请将 {port} 的 USB 数据线重新插回！(RECONNECT USB CABLE NOW!) <<<", flush=True)
    print(f"  ================================================================", flush=True)
    beep_plug()
    t_replug_prompt = time.time()

    re_enum = wait_for_port(port, present=True, timeout_s=60.0)
    t_re_enum = time.time()
    if not re_enum:
        raise RuntimeError(f"等待 {port} 重插枚举超时 (60s)")
    print(f"  ✓ 成功检测到 {port} 重新插入并完成 Windows CDC 枚举！(耗时 {round(t_re_enum - t_replug_prompt, 2)}s)", flush=True)

    # Allow ESP32 boot and CDC enumeration to stabilize
    time.sleep(3.5)

    # 4. Reconnect, establish new session, verify recovery
    print(f"\n  [4/4] 重新连接 {port} 并验证新会话建立与配置完好...", flush=True)
    client2 = robust_connect(port, evidence)
    try:
        boot1 = client2.boot_id or ""
        session1 = client2.session_id
        ping1 = client2.ping()
        cfg1, rev1 = run_g2.read_all_config(client2)
        dev_info = client2.call("DEVICE_INFO", {}, timeout_ms=3000)
    finally:
        client2.close()

    boot_changed = (boot1 != boot0)
    rtt_ms = getattr(client2, "last_rtt_ms", 0) or 0

    print(f"    -> 恢复后新会话: session_id={session1}, 新 Boot ID={boot1} (已轮转: {boot_changed})", flush=True)
    print(f"    -> 恢复后 PING: uptime_ms={ping1.get('uptime_ms') if isinstance(ping1, dict) else 'none'}, RTT={round(rtt_ms, 1)}ms", flush=True)
    print(f"    -> 恢复后配置版本: rev={rev1}, 字段数={len(cfg1) if isinstance(cfg1, dict) else 0}", flush=True)
    print(f"    -> 设备信息: model={dev_info.get('model') if isinstance(dev_info, dict) else 'none'}, fw_version={dev_info.get('fw_version') if isinstance(dev_info, dict) else 'none'}", flush=True)

    dev_id1 = extract_device_id(dev_info)
    judge_rec = {
        "target_port": port,
        "port": port,
        "disconnect_observed": cut_ok,
        "reconnect_observed": re_enum,
        "boot_before": boot0,
        "boot_after": boot1,
        "session_before": session0,
        "session_after": session1,
        "ping_after": ping1,
        "config_before": cfg0,
        "config_after": cfg1,
        "rev_before": rev0,
        "rev_after": rev1,
        "device_id_before": dev_id0,
        "device_id_after": dev_id1,
    }
    verdict, passed, detail = hardware_judges.judge_usb_unplug_cycle(judge_rec)

    result_entry = {
        **judge_rec,
        "cycle": cycle,
        "timestamp_unplug_prompt": t_unplug_prompt,
        "timestamp_disconnect": t_disconnect,
        "timestamp_replug_prompt": t_replug_prompt,
        "timestamp_re_enum": t_re_enum,
        "unplug_duration_s": round(t_re_enum - t_disconnect, 2) if (t_re_enum and t_disconnect) else None,
        "boot_changed": boot_changed,
        "rtt_ms": round(rtt_ms, 2),
        "io_error_caught": io_error_caught,
        "verdict": verdict,
        "detail": detail,
        "passed": passed,
    }

    evidence.note({
        "event": "usb_unplug_cycle",
        **result_entry
    })

    print(f"\n  >>> 判定结果: [{verdict}] ({'PASS' if passed else 'FAIL'})", flush=True)
    print(f"      {detail}\n", flush=True)

    if passed:
        beep_success()
    return result_entry


def main():
    parser = argparse.ArgumentParser(description="5 Physical USB Unplug/Replug Runner for G2-01 / B3")
    parser.add_argument("--port", required=True, help="Explicit target serial port (never defaulted)")
    parser.add_argument("--rounds", type=int, default=5, help="Number of USB unplug rounds (default 5)")
    parser.add_argument("--out", default=None, help="Evidence output path")
    args = parser.parse_args()

    session_dir = Path("tmp/g2-hardware-20261029-session-01/evidence")
    raw_target = Path(args.out) if args.out else session_dir / "b3_usb_unplug.jsonl"
    out_path, result_path, manifest_path = run_g2.resolve_output_triplet(raw_target)

    # R8-03: exclusively reserve raw/result/manifest BEFORE secrets or device
    # I/O via the shared OutputPlan (same rules as run_g2/human/power).
    plan = run_g2.OutputPlan.from_raw_target(raw_target)
    try:
        plan.reserve_all()
    except FileExistsError as exc:
        print(f"Error: {exc} Refusing to run (immutable evidence policy G2-HW-R1-B / R8-03).", file=sys.stderr)
        return 1

    def _manifest_builder(res_obj: dict, res_sha: str | None) -> dict:
        return {
            "run_id": "g2-01-usb-unplug",
            "status": res_obj.get("status"),
            "total_cycles_planned": res_obj.get("total_cycles_planned"),
            "total_cycles_completed": res_obj.get("total_cycles_completed"),
            "raw_file": str(out_path),
            "result_file": str(result_path),
            "result_sha256": res_sha,
        }

    if args.rounds <= 0:
        result_doc = {
            "run_id": "g2-01-usb-unplug",
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

    print(f"============================================================")
    print(f"  MMWave Web Console G2 · 5 次物理 USB 数据线拔插恢复测试")
    print(f"  目标端口: {args.port} | 执行轮次: 1 至 {args.rounds}")
    print(f"  证据输出: {out_path}")
    print(f"============================================================", flush=True)

    history = []
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
        suite_eval = hardware_judges.judge_usb_unplug_suite(history, required_rounds=args.rounds)
        if suite_eval.get("status") != "pass" or len(history) != args.rounds or not all(r.get("passed") for r in history):
            status = "fail"

        ev_summary = evidence.close()
        result_doc = {
            "run_id": "g2-01-usb-unplug",
            "status": status,
            "total_cycles_planned": args.rounds,
            "total_cycles_completed": len(history),
            "unplug_recovered_count": sum(1 for r in history if r.get("verdict") == "UNPLUG_RECOVERED_SAFE"),
            "failed_count": sum(1 for r in history if r.get("verdict") != "UNPLUG_RECOVERED_SAFE"),
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
            print(f"完成轮次: {len(history)}/{args.rounds} | 拔插安全恢复: {result_doc['unplug_recovered_count']} | 失败数: {result_doc['failed_count']}", flush=True)
            file_collision = False

    if file_collision:
        return 1
    return 0 if status == "pass" and len(history) == args.rounds else 1


if __name__ == "__main__":
    sys.exit(main())
