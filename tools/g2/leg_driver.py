"""Micro-window leg driver: each leg starts from a fresh esptool reset so it
fits inside the bench's short responsive USB windows (see report section on
the sub-second wedge). Banks one result JSON per leg."""

import json
import math
import subprocess
import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import mwcp  # noqa: E402

COMPONENT = Path(__file__).resolve().parents[2]
EVIDENCE = COMPONENT.parents[1] / "tmp" / "mwcp-g2" / "evidence"
ESPTOOL = [str(COMPONENT / ".venv-esphome" / "Scripts" / "python.exe"), "-m", "esptool", "--port"]
PORT = sys.argv[1] if len(sys.argv) > 1 else "COM9"


def reset_device():
    subprocess.run(ESPTOOL + [PORT, "run"], capture_output=True, timeout=45)
    time.sleep(8)


def new_session(tag, allow_write=True):
    ev = mwcp.EvidenceWriter(EVIDENCE / f"{tag}-{time.strftime('%Y%m%d-%H%M%S')}.jsonl", mwcp.Redactor())
    cli = mwcp.Client(PORT, ev, allow_write=allow_write)
    cli.hello(timeout_ms=25000)
    return cli, ev


def poly(n, r=400):
    return [[round(r * math.cos(2 * math.pi * k / n), 2), round(r * math.sin(2 * math.pi * k / n), 2)] for k in range(n)]


def read_all_config(cli):
    values, cursor, rev = {}, None, None
    while True:
        r = cli.call("CONFIG_READ", {"cursor": cursor}, timeout_ms=9000)
        if not r.get("ok"):
            raise RuntimeError(f"read failed: {json.dumps(r)[:120]}")
        res = r["result"]
        rev = res.get("revision")
        for item in res.get("items", []):
            values[item["key"]] = item["value"]
        cursor = res.get("next_cursor")
        if cursor is None:
            return values, rev


def leg_config_validate(checks, notes):
    reset_device()
    cli, ev = new_session("leg-cfg-validate")
    try:
        base, rev0 = read_all_config(cli)
        checks.append(("config_read_8_keys", len(base) == 8, f"rev={rev0}"))
        big = {"base_revision": rev0, "changes": {
            "install.x_cm": 120.0, "install.y_cm": -80.0, "install.z_cm": 280.0,
            "install.yaw_deg": 15.0, "install.pitch_deg": -5.0, "install.roll_deg": 3.0,
            "geometry.boundary_cm": poly(64),
            "areas.definitions": [
                {"slot": 0, "enabled": True, "name": "g2-door", "points_cm": poly(12, 150)},
                {"slot": 1, "enabled": True, "name": "g2-desk", "points_cm": poly(12, 200)},
                {"slot": 2, "enabled": True, "name": "g2-sofa", "points_cm": poly(12, 300)}]}}
        r = cli.call("CONFIG_VALIDATE", big, timeout_ms=9000)
        checks.append(("validate_max_ok", r.get("ok") is True, json.dumps(r)[:100]))
        bad = cli.call("CONFIG_VALIDATE", {"base_revision": rev0, "changes": {"install.z_cm": 601}}, timeout_ms=9000)
        checks.append(("validate_rejects_601", bad.get("error", {}).get("code") == "OUT_OF_RANGE",
                       json.dumps(bad)[:100]))
        bad2 = cli.call("CONFIG_VALIDATE", {"base_revision": rev0,
                                            "changes": {"geometry.boundary_cm": [[0, 0], [100, 100], [100, 0], [0, 100]]}},
                        timeout_ms=9000)
        checks.append(("validate_rejects_self_intersect", bad2.get("ok") is False, json.dumps(bad2)[:100]))
    finally:
        cli.close()
        s = ev.close()
        notes.append(f"evidence={s['file'].split(chr(92))[-1]} sha={s['sha256'][:12]}")
    return checks


def leg_config_commit(checks, notes):
    reset_device()
    cli, ev = new_session("leg-cfg-commit")
    try:
        base, rev0 = read_all_config(cli)
        small = {"install.x_cm": 155.0, "geometry.boundary_cm": poly(5, 300)}
        op1 = str(uuid.uuid4())
        c = cli.call("CONFIG_COMMIT", {"base_revision": rev0, "op_id": op1, "changes": small}, timeout_ms=12000)
        rev1 = c.get("result", {}).get("revision")
        checks.append(("commit_persisted", c.get("ok") is True and c.get("result", {}).get("persisted") is True,
                       json.dumps(c)[:110]))
        replay = cli.call("CONFIG_COMMIT", {"base_revision": rev0, "op_id": op1, "changes": small}, timeout_ms=12000)
        checks.append(("op_id_replay_same_revision", replay.get("ok") is True
                       and replay.get("result", {}).get("revision") == rev1, ""))
        misuse = cli.call("CONFIG_COMMIT", {"base_revision": rev1, "op_id": op1,
                                            "changes": {"install.x_cm": 156.0}}, timeout_ms=12000)
        checks.append(("op_id_reuse_rejected", misuse.get("error", {}).get("code") == "OP_ID_REUSE",
                       json.dumps(misuse)[:100]))
        stale = cli.call("CONFIG_COMMIT", {"base_revision": rev0, "op_id": str(uuid.uuid4()),
                                           "changes": {"install.x_cm": 999.0}}, timeout_ms=12000)
        checks.append(("stale_base_conflict", stale.get("error", {}).get("code") == "REVISION_CONFLICT", ""))
        back, rev_now = read_all_config(cli)
        checks.append(("commit_readback", back.get("install.x_cm") == 155.0
                       and isinstance(back.get("geometry.boundary_cm"), list)
                       and len(back["geometry.boundary_cm"]) == 5,
                       f"x={back.get('install.x_cm')} pts={len(back.get('geometry.boundary_cm') or [])} rev={rev_now}"))
    finally:
        cli.close()
        s = ev.close()
        notes.append(f"evidence={s['file'].split(chr(92))[-1]} sha={s['sha256'][:12]}")
    return checks


def leg_web_entry(checks, notes):
    import urllib.request
    from urllib.parse import quote
    ip = "192.168.5.236"

    def getn():
        with urllib.request.urlopen(f"http://{ip}/number/{quote('Mount X')}", timeout=10) as resp:
            return json.loads(resp.read().decode())

    def setn(v):
        req = urllib.request.Request(f"http://{ip}/number/{quote('Mount X')}/set?value={v}", data=b"", method="POST")
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status

    reset_device()
    cli, ev = new_session("leg-web-entry")
    try:
        base, revA = read_all_config(cli)
        setn(123)
        time.sleep(2.5)
        w = getn()
        checks.append(("web_write_applied", w.get("value") == "123", json.dumps(w)[:90]))
        cas = cli.call("CONFIG_COMMIT", {"base_revision": revA, "op_id": str(uuid.uuid4()),
                                         "changes": {"install.x_cm": 111.0}}, timeout_ms=12000)
        checks.append(("web_write_causes_cas_conflict", cas.get("error", {}).get("code") == "REVISION_CONFLICT",
                       json.dumps(cas)[:110]))
        back, revB = read_all_config(cli)
        checks.append(("web_value_preserved", back.get("install.x_cm") == 123.0,
                       f"x={back.get('install.x_cm')} revA={revA} revB={revB}"))
        uc = cli.call("CONFIG_COMMIT", {"base_revision": revB, "op_id": str(uuid.uuid4()),
                                        "changes": {"install.x_cm": 140.0}}, timeout_ms=12000)
        checks.append(("usb_commit_after_web", uc.get("ok") is True, json.dumps(uc)[:100]))
    finally:
        cli.close()
        s = ev.close()
        notes.append(f"evidence={s['file'].split(chr(92))[-1]} sha={s['sha256'][:12]}")
    time.sleep(3)
    w2 = getn()
    checks.append(("web_reads_back_usb_write", w2.get("value") == "140", json.dumps(w2)[:90]))
    return checks


def leg_jobs(checks, notes):
    reset_device()
    cli, ev = new_session("leg-jobs")
    try:
        nc = cli.call("ACTION_START", {"action_id": "radar.reset_module", "op_id": str(uuid.uuid4()),
                                       "params": {}, "confirm": None}, timeout_ms=9000)
        checks.append(("reset_no_confirm_rejected", nc.get("error", {}).get("code") == "INVALID_ARGUMENT",
                       json.dumps(nc)[:90]))
        wc = cli.call("ACTION_START", {"action_id": "radar.reset_module", "op_id": str(uuid.uuid4()),
                                       "params": {}, "confirm": "device.restart"}, timeout_ms=9000)
        checks.append(("reset_wrong_confirm_rejected", wc.get("error", {}).get("code") == "INVALID_ARGUMENT", ""))
        op = str(uuid.uuid4())
        rs = cli.call("ACTION_START", {"action_id": "radar.reset_module", "op_id": op,
                                       "params": {}, "confirm": "radar.reset_module"}, timeout_ms=9000)
        job = rs.get("result", {}).get("job_id")
        term = None
        deadline = time.time() + 30
        while time.time() < deadline:
            j = cli.call("JOB_GET", {"job_id": job}, timeout_ms=9000).get("result", {})
            term = j
            if j.get("state") in ("succeeded", "failed"):
                break
            time.sleep(1)
        checks.append(("reset_terminal_unverified", term and term.get("state") == "succeeded"
                       and term.get("result") == {"verified": False, "verification": "none"},
                       json.dumps(term)[:130]))
        again = cli.call("ACTION_START", {"action_id": "radar.reset_module", "op_id": op,
                                          "params": {}, "confirm": "radar.reset_module"}, timeout_ms=9000)
        checks.append(("reset_op_id_idempotent", again.get("ok") is True
                       and again.get("result", {}).get("job_id") == job, ""))
        mis = cli.call("ACTION_START", {"action_id": "device.restart", "op_id": op,
                                        "params": {}, "confirm": "device.restart"}, timeout_ms=9000)
        checks.append(("op_id_cross_action_rejected", mis.get("error", {}).get("code") == "OP_ID_REUSE", ""))
    finally:
        cli.close()
        s = ev.close()
        notes.append(f"evidence={s['file'].split(chr(92))[-1]} sha={s['sha256'][:12]}")
    return checks


def leg_restart_persistence(checks, notes):
    reset_device()
    cli, ev = new_session("leg-restart")
    try:
        base, revA = read_all_config(cli)
        c = cli.call("CONFIG_COMMIT", {"base_revision": revA, "op_id": str(uuid.uuid4()),
                                       "changes": {"install.y_cm": -77.0}}, timeout_ms=12000)
        revB = c.get("result", {}).get("revision")
        checks.append(("pre_restart_commit", c.get("ok") is True, f"revA={revA} revB={revB}"))
        rj = cli.call("ACTION_START", {"action_id": "device.restart", "op_id": str(uuid.uuid4()),
                                       "params": {}, "confirm": "device.restart"}, timeout_ms=9000)
        checks.append(("restart_accepted", rj.get("ok") is True, ""))
        boot_before = cli.boot_id
    finally:
        cli.close()
        s = ev.close()
        notes.append(f"evidence1={s['file'].split(chr(92))[-1]} sha={s['sha256'][:12]}")
    time.sleep(12)
    cli2, ev2 = new_session("leg-restart-r2")
    try:
        checks.append(("boot_id_changed", cli2.boot_id != boot_before, f"{boot_before}->{cli2.boot_id}"))
        back, revC = read_all_config(cli2)
        checks.append(("config_survives_restart", back.get("install.y_cm") == -77.0 and revC == revB,
                       f"y={back.get('install.y_cm')} rev={revC}"))
        st = None
        for _ in range(12):
            st = cli2.call("WIFI_STATUS", timeout_ms=9000).get("result", {})
            if st.get("state") == "connected":
                break
            time.sleep(2)
        checks.append(("wifi_reconnects_after_restart", st.get("state") == "connected", json.dumps(st)[:90]))
    finally:
        cli2.close()
        s2 = ev2.close()
        notes.append(f"evidence2={s2['file'].split(chr(92))[-1]} sha={s2['sha256'][:12]}")
    return checks


def leg_telemetry(checks, notes):
    reset_device()
    cli, ev = new_session("leg-telemetry", allow_write=False)
    try:
        sub = cli.call("SUBSCRIBE", {"streams": [{"id": "telemetry", "max_rate_hz": 1}],
                                     "event_budget_bps": 8000}, timeout_ms=9000)
        checks.append(("subscribe_ok", sub.get("ok") is True, ""))
        events = cli.drain_events(60000)
        telem = [e for e in events if e["meta"]["code"] == mwcp.CODE["TELEMETRY"]]
        checks.append(("telemetry_received", len(telem) > 0, f"n={len(telem)}"))
        if telem:
            sample = telem[0]["payload"]
            fields_ok = all(k in sample for k in ("source_seq", "sent_ms", "presence", "targets_quality", "targets"))
            checks.append(("telemetry_fields", fields_ok, str(sorted(sample.keys()))[:140]))
            seqs = [e["payload"].get("source_seq") for e in telem]
            checks.append(("source_seq_nondecreasing", all(b >= a for a, b in zip(seqs, seqs[1:])), f"n={len(seqs)}"))
            speeds = [t.get("speed_cm_s") for e in telem for t in (e["payload"].get("targets") or [])]
            checks.append(("speed_null_for_r60", all(s is None for s in speeds), ""))
            notes.append(f"no_target={sum(1 for e in telem if e['payload'].get('targets') in ([], None))}/{len(telem)}")
    finally:
        cli.close()
        s = ev.close()
        notes.append(f"evidence={s['file'].split(chr(92))[-1]} sha={s['sha256'][:12]}")
    return checks


def leg_coexist(checks, notes, rounds=10):
    ok_rounds = 0
    for i in range(rounds):
        reset_device()
        cli, ev = new_session(f"leg-coexist-{i}")
        try:
            op = str(uuid.uuid4())
            r = cli.call("WIFI_SCAN", {"op_id": op}, timeout_ms=9000)
            if not r.get("ok"):
                notes.append(f"round {i}: refused")
                continue
            job = r["result"]["job_id"]
            term = None
            deadline = time.time() + 30
            while time.time() < deadline:
                j = cli.call("JOB_GET", {"job_id": job}, timeout_ms=9000).get("result", {})
                term = j
                if j.get("state") in ("succeeded", "failed"):
                    break
                time.sleep(1)
            page = cli.call("WIFI_SCAN_RESULTS", {"job_id": job, "cursor": None}, timeout_ms=9000)
            st = cli.call("WIFI_STATUS", timeout_ms=9000).get("result", {})
            if term and term.get("state") in ("succeeded", "failed") and page.get("ok") is not None \
                    and st.get("state") == "connected":
                ok_rounds += 1
                notes.append(f"round {i}: ok ({term.get('state')}, connected kept)")
        finally:
            cli.close()
            ev.close()
    checks.append(("coexist_rounds", ok_rounds == rounds, f"{ok_rounds}/{rounds}"))
    return checks


def run_leg(name, fn, report):
    print(f"=== leg {name} ===", flush=True)
    checks, notes = [], []
    try:
        fn(checks, notes)
    except Exception as error:  # noqa: BLE001
        notes.append(f"exception: {error!r}")
    passed = sum(1 for _, ok, _ in checks if ok)
    for cname, ok, detail in checks:
        print(f"  [{'PASS' if ok else 'FAIL'}] {cname} :: {detail[:100]}", flush=True)
    report.append({"leg": name, "checks": [{"name": n, "pass": ok, "detail": d} for n, ok, d in checks],
                   "passed": passed, "total": len(checks), "notes": notes})
    return passed == len(checks) and len(checks) > 0


def main():
    report = []
    all_ok = True
    all_ok &= run_leg("config_validate", leg_config_validate, report)
    all_ok &= run_leg("config_commit", leg_config_commit, report)
    all_ok &= run_leg("web_entry", leg_web_entry, report)
    all_ok &= run_leg("jobs", leg_jobs, report)
    all_ok &= run_leg("restart_persistence", leg_restart_persistence, report)
    all_ok &= run_leg("telemetry", leg_telemetry, report)
    all_ok &= run_leg("coexist", leg_coexist, report)
    out = EVIDENCE / f"g2-legs-{time.strftime('%Y%m%d-%H%M%S')}.result.json"
    out.write_text(json.dumps({"run_id": "g2-legs", "status": "pass" if all_ok else "fail",
                               "legs": report}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"=== legs overall: {'PASS' if all_ok else 'PARTIAL/FAIL'} -> {out} ===", flush=True)


if __name__ == "__main__":
    main()
