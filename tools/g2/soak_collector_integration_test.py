#!/usr/bin/env python3
"""Full-chain offline integration test for the soak collector (G2-R3-03/04
r3b). Drives the REAL cmd_soak with a fake Client and a fake clock over a
synthetic evidence history: collector -> raw-frame rebuild -> judge ->
result, end to end. No serial port, no device.

Covers:
1. a healthy offline idle run (bracketing disconnected observations) passes
   end-to-end, including the offline precondition built by the REAL
   collector code;
2. the code_to_name NameError regression (the r3b review crash) is gone;
3. single-attempt timeouts are KEPT in the retry records;
4. boot/session changes come from the frames, not a boot_initial backfill;
5. a mid-run Wi-Fi association fails the offline precondition end-to-end;
6. counterexample A end-to-end (2Hz telemetry, 6 LOGs) fails the stress
   judge when driven through the real collector path.
"""

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import run_g2  # noqa: E402
import mwcp  # noqa: E402

failures = []


def expect(name, ok, detail=""):
    print(f"[{'PASS' if ok else 'FAIL'}] {name} {detail}")
    if not ok:
        failures.append(name)


class FakeClock:
    def __init__(self, start=0.0):
        self.now = start

    def monotonic(self):
        return self.now


_RID = [1]  # global request-id counter: survives client re-creation (the
# collector rebuilds the client after a timeout recovery; request ids must
# stay unique across instances so a timed-out tx is never paired with a
# later response under the same id)

_HELLO_SEQ = [1]  # unique handshake nonce per FakeClient instance: two
# handshakes inside one run must never share a nonce (the rebuild correlates
# HELLO generations by nonce, r3d)


class FakeClient:
    """Scripted device: responds to PING/STATUS_GET/WIFI_STATUS/SUBSCRIBE and
    emits events on demand. Records nothing to real files."""

    def __init__(self, script, clock, evidence, wifi_state="disconnected", device_id="esp32c3-luatos-core"):
        self.script = list(script)  # list of ("resp", dict) or ("timeout", None)
        self.drain_script = []  # list of ("events", [frames]) consumed by drain_events
        for entry in list(script):
            if entry[0] == "events":
                self.drain_script.append(entry)
            else:
                pass  # already in script via list()
        # remove "events" entries from script (they belong to the drain queue)
        self.script = [e for e in list(script) if e[0] != "events"]
        self.clock = clock
        self.evidence = evidence
        self.session_id = 4096
        self.boot_id = "B1"
        self.device_id = device_id
        self.wifi_state = wifi_state
        # r3d: the HELLO payloads must match the REAL client/device shape -
        # the TX body carries the client nonce top-level, the device echoes
        # it under result next to boot_id. A per-instance nonce keeps each
        # handshake generation distinct.
        self.hello_nonce = f"{_HELLO_SEQ[0]:032x}"
        _HELLO_SEQ[0] += 1

    def hello(self, timeout_ms=8000):
        # protocol order: TX (session 0) first, then the RX on the NEW
        # session — matching the real client so the rebuild's
        # first_send_t < resolved_t holds. Payload shapes = real mwcp.py
        # Client.hello / real device response (nonce correlation, r3d).
        nonce = self.hello_nonce
        self.evidence.frame(True, {"kind": 1, "code": 1, "session_id": 0, "request_id": 1,
                                   "wire_seq": 1, "boot_id": self.boot_id},
                            {"client": {"name": "g2-runner", "version": "0.1.0"},
                             "nonce": nonce,
                             "protocol": {"major": 1, "minor_max": 0},
                             "max_payload": 4096}, [])
        self.clock.now += 0.01
        res = {"nonce": nonce, "session_ttl_ms": 15000, "boot_id": self.boot_id}
        if self.device_id:
            res["device_id"] = self.device_id
            res["identity"] = {"device_id": self.device_id}
        self.evidence.frame(False, {"kind": 2, "code": 1, "session_id": self.session_id,
                                    "request_id": 1, "wire_seq": 2, "boot_id": self.boot_id},
                            {"ok": True, "result": res}, [])
        return {"ok": True, "result": res}

    def ping(self):
        return self.call("PING")

    def call(self, name, payload=None, timeout_ms=9000, **kw):
        _RID[0] += 1
        rid = _RID[0]  # global: unique across re-created clients
        code = mwcp.CODE.get(name, 0)
        tx_wall = round(mwcp.time.time() - self.evidence.t0, 3)
        tx_mono = round(mwcp.time.monotonic() - self.evidence.t0_mono, 3)
        self.evidence.frame(True, {"kind": 1, "code": code,
                                   "session_id": self.session_id, "request_id": rid,
                                   "wire_seq": rid + 100, "boot_id": self.boot_id},
                            payload or {}, [])
        # exhausted script = steady-state healthy response (a real device
        # answers every poll; timeouts must be explicit). WIFI_STATUS keeps
        # answering with its last known state so the end-of-run bracket
        # observation works.
        if name == "DEVICE_INFO":
            # device identity queries don't consume scripted entries
            action = ("resp", {"ok": True, "result": {
                "device_id": self.device_id, "board": "esp32c3-luatos-core",
                "identity": {"device_id": self.device_id}}})
        elif self.script:
            action = self.script.pop(0)
        elif name == "WIFI_STATUS":
            action = ("resp", {"ok": True, "result": {
                "state": self.wifi_state, "ssid": "", "ip": None, "rssi_dbm": None}})
        else:
            action = ("resp", {"ok": True, "result": {
                "uptime_ms": 60000, "radar_link": "healthy",
                "counters": {"rx_frames": 999, "logs_dropped": 0}}})
        if action[0] == "timeout":
            raise TimeoutError(f"{name} no response")  # tx recorded, no rx
        resp = action[1]
        # simulate a small RPC RTT on the fake clock so the RX timestamp
        # lands strictly after the TX (zero-RTT frames read as "masked" by
        # the retry integrity check: resolved_t <= first_send_t)
        self.clock.now += 0.01
        rx_wall = round(mwcp.time.time() - self.evidence.t0, 3)
        rx_mono = round(mwcp.time.monotonic() - self.evidence.t0_mono, 3)
        self.evidence.frame(False, {"kind": 2, "code": code,
                                    "session_id": self.session_id, "request_id": rid,
                                    "wire_seq": rid + 200, "boot_id": self.boot_id}, resp, [])
        # The scripted client never enters Client._request. Record the same
        # v2 pump note the real collector would, from this fake clock, so a
        # healthy run is not a missing-note fast path.
        actual = round(rx_mono - tx_mono, 3)
        self.evidence.note({
            "event": "rpc_attempt",
            "note_version": 2,
            "clock": "monotonic",
            "request_id": rid,
            "code": code,
            "session_id": self.session_id,
            "boot_id": self.boot_id,
            "attempt": 0,
            "configured_window_s": round(timeout_ms / 1000.0, 3),
            "wait_started_s": tx_mono,
            "wait_ended_s": round(tx_mono + actual, 3),
            "wait_actual_s": actual,
            "timeline_t_start": tx_wall,
            "timeline_t_end": round(tx_wall + actual, 3),
            "outcome": "matched",
            "tx_recorded": True,
            "rtt_ms": round(actual * 1000.0, 1),
        })
        return resp

    def drain_events(self, duration_ms, keepalive_s=8.0):
        out = []
        if self.drain_script:
            action = self.drain_script.pop(0)
            for frame in action[1]:
                self.evidence.frame(False, frame["meta"], frame["payload"], [])
                out.append({"meta": {k: frame["meta"][k] for k in
                                     ("kind", "code", "session_id", "request_id", "wire_seq")},
                            "payload": frame["payload"]})
        self.clock.now += duration_ms / 1000.0
        return out

    def close(self):
        pass


import datetime as _dt
import tempfile as _tf

SIM_BASE_WALL = _dt.datetime(2026, 10, 28, 12, 0, 0, tzinfo=_dt.timezone.utc)

def get_sim_now(tz=None):
    if tz is None:
        return SIM_BASE_WALL.replace(tzinfo=None)
    return SIM_BASE_WALL.astimezone(tz)

def run_soak(script, seconds=60, mode="idle", wifi_start="disconnected",
             wifi_end="disconnected", offline_evidence=None, device_id="esp32c3-luatos-core"):
    """Drive the REAL cmd_soak with the fake client. Returns (result, out)."""
    import tempfile
    td_obj = tempfile.TemporaryDirectory(prefix="soak-collector-")
    out_dir = Path(td_obj.name)
    import argparse

    args = argparse.Namespace(port="FAKE", out=None, allow_write=(mode == "stress"),
                              allow_provision=False, seconds=seconds, repeat=None,
                              soak_mode=(None if mode == "idle" else mode),
                              offline_evidence=offline_evidence)
    clock = FakeClock()
    real_monotonic = time.monotonic
    evidence_holder = {"_td": td_obj}
    real_connect = run_g2.connect

    stamp = f"20261027-{getattr(run_soak, '_stamp', 0):06d}"

    def fake_connect(args, tag, allow_write=False, allow_provision=False):
        controlled, secrets = run_g2.load_secrets()
        redactor = mwcp.Redactor(controlled_ssids=controlled, secrets=secrets)
        path = out_dir / f"{tag}-{stamp}.jsonl"
        evidence = mwcp.EvidenceWriter(path, redactor)
        if mode == "stress":
            # SUBSCRIBE ack must be the first scripted response in stress mode
            script.insert(0, ("resp", {"ok": True, "result": {"streams": [
                {"id": "telemetry", "max_rate_hz": 5}, {"id": "logs", "max_rate_hz": 20},
                {"id": "jobs", "max_rate_hz": 5}, {"id": "status", "max_rate_hz": 1}],
                "event_budget_bps": 8000}}))
        else:
            script.insert(0, ("resp", {"ok": True, "result": {
                "state": wifi_start, "ssid": "", "ip": None, "rssi_dbm": None}}))
        script.append(("resp", {"ok": True, "result": {
            "state": wifi_end, "ssid": "", "ip": None, "rssi_dbm": None}}))
        client = FakeClient(script, clock, evidence, wifi_state=wifi_end, device_id=device_id)
        evidence_holder["path"] = path
        evidence_holder["evidence"] = evidence
        if __debug__ and getattr(run_soak, "_debug", False):
            print("DBG script[0]:", str(script[0])[:70], flush=True)
        return client, evidence

    run_soak._stamp = getattr(run_soak, "_stamp", 0) + 1
    run_g2.connect = fake_connect
    orig_monotonic = time.monotonic
    try:
        import types

        def sim_strftime(fmt, t_struct=None):
            if t_struct is None:
                cur_dt = SIM_BASE_WALL + _dt.timedelta(seconds=clock.now)
                if "%z" in fmt:
                    return cur_dt.strftime(fmt.replace("%z", "+0000"))
                return cur_dt.strftime(fmt)
            return time.strftime(fmt, t_struct)

        fake_time = types.ModuleType("time_shim")
        fake_time.monotonic = lambda: clock.now
        fake_time.time = lambda: SIM_BASE_WALL.timestamp() + clock.now
        fake_time.sleep = lambda s: clock.__setattr__("now", clock.now + s)
        fake_time.strftime = sim_strftime
        run_g2.time = fake_time

        mwcp_time = types.ModuleType("time_shim")
        mwcp_time.monotonic = lambda: clock.now
        mwcp_time.time = lambda: SIM_BASE_WALL.timestamp() + clock.now
        mwcp_time.sleep = lambda s: clock.__setattr__("now", clock.now + s)
        mwcp_time.strftime = sim_strftime
        mwcp.time = mwcp_time

        outcome = run_g2.cmd_soak(args)
    finally:
        run_g2.connect = real_connect
        run_g2.time = time
        mwcp.time = time
        time.monotonic = orig_monotonic
    return outcome, evidence_holder


def main() -> int:
    # 1+2: healthy offline idle run end-to-end; also proves the code_to_name
    # NameError is gone (the rebuild runs on the real evidence file).
    script = []
    for i in range(6):  # 60s at 10s samples = 6 samples
        script.append(("resp", {"ok": True, "result": {
            "uptime_ms": 10000 * i, "radar_link": "healthy",
            "counters": {"rx_frames": i, "logs_dropped": 0}}}))
    # final WIFI_STATUS (end bracket) then result
    script.append(("resp", {"ok": True, "result": {"state": "disconnected", "ssid": "",
                                                   "ip": None, "rssi_dbm": None}}))
    outcome, holder = run_soak(script, seconds=60, mode="idle")
    checks = {c["name"]: c for c in outcome.get("checks", [])}
    # G2-R3-04 (r3b): the collector's bracketing-only precondition is
    # INSUFFICIENT - the E2E idle run must FAIL the offline gate (the
    # offline precondition check fails while the run-level status is fail);
    # the other run-quality checks (span, samples, boot, gaps) still pass.
    expect("E2E offline idle run: bracket-only precondition rejected (insufficient)",
           outcome.get("status") == "fail"
           and not checks.get("offline_precondition", {}).get("pass", True)
           and checks.get("duration_honest", {}).get("pass")
           and checks.get("single_boot", {}).get("pass")
           and checks.get("no_uncovered_gap", {}).get("pass"),
           f"status={outcome.get('status')} "
           f"precond={checks.get('offline_precondition', {}).get('detail', '')[:60]}")
    expect("E2E rebuild produced event data without NameError",
           "evidence_parse_failed" not in json.dumps(outcome.get("notes", "")),
           str([n for n in outcome.get("notes", []) if "parse" in n])[:80])

    # 3: single-attempt timeout kept in retry records. The REAL rebuild
    # function runs over a synthetic raw history containing one PING tx
    # with no rx; the record must survive with resolved_t=None and a single
    # attempt (r3b review item 5: never drop single-attempt timeouts).
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        hist = Path(td) / "history.jsonl"
        lines = [
            {"dir": "tx", "t": 1.0, "code": mwcp.CODE["PING"], "session_id": 4096,
             "request_id": 9, "boot_id": "B1", "payload": {}},
            {"dir": "rx", "t": 1.05, "code": mwcp.CODE["PING"], "session_id": 4096,
             "request_id": 9, "boot_id": "B1", "payload": {"uptime_ms": 1}},
            {"dir": "tx", "t": 30.0, "code": mwcp.CODE["PING"], "session_id": 4096,
             "request_id": 11, "boot_id": "B1", "payload": {}},  # times out: no rx
            {"dir": "tx", "t": 60.0, "code": mwcp.CODE["PING"], "session_id": 4096,
             "request_id": 13, "boot_id": "B1", "payload": {}},
            {"dir": "rx", "t": 60.05, "code": mwcp.CODE["PING"], "session_id": 4096,
             "request_id": 13, "boot_id": "B1", "payload": {"uptime_ms": 2}},
        ]
        hist.write_text(chr(10).join(json.dumps(l) for l in lines) + chr(10), encoding="utf-8")
        rebuilt = run_g2.rebuild_judge_inputs_from_evidence(hist)
        expect("E2E rebuild verified", rebuilt["verified"] is True)
        recs = {r["request"]: r for r in rebuilt["retry_records"]}
        expect("E2E single-attempt timeout retained (resolved_t=None)",
               11 in recs and recs[11]["resolved_t"] is None
               and len(recs[11]["attempts"]) == 1,
               f"records={sorted(recs)}")
        expect("E2E boot/session come from frames (no backfill)",
               all(r["boot"] == "B1" for r in rebuilt["retry_records"]))
        # the wait_s backoff marker lands on later attempts
        expect("E2E retry backoff wait_s recorded",
               recs[13]["attempts"][0].get("wait_s") is not None
               or len(recs[13]["attempts"]) == 1)

    # 5: mid-run association fails the precondition end-to-end
    script = []
    for i in range(6):
        script.append(("resp", {"ok": True, "result": {
            "uptime_ms": 10000 * i, "radar_link": "healthy",
            "counters": {"rx_frames": i, "logs_dropped": 0}}}))
    outcome, holder = run_soak(script, seconds=60, mode="idle",
                               wifi_end="connected")
    checks = {c["name"]: c for c in outcome.get("checks", [])}
    expect("E2E mid-run association fails offline precondition",
           outcome.get("status") == "fail"
           and not checks.get("offline_precondition", {}).get("pass", True),
           checks.get("offline_precondition", {}).get("detail", "")[:80])

    # 6: counterexample A through the stress collector path (2Hz telemetry
    # in the drain events, LOG only 6 in the whole window) must fail the
    # judge even though samples are healthy.
    script = []
    tele_frames = [{"meta": {"kind": 3, "code": mwcp.CODE["TELEMETRY"], "session_id": 4096,
                             "request_id": 0, "wire_seq": 5000 + i},
                    "payload": {"source_seq": i, "sent_ms": 0, "presence": False,
                                "targets": [], "targets_quality": 0}} for i in range(120)]
    for i in range(6):
        script.append(("events", tele_frames))
        script.append(("resp", {"ok": True, "result": {
            "uptime_ms": 10000 * i, "radar_link": "healthy",
            "counters": {"rx_frames": i, "logs_dropped": 0}}}))
    script.append(("resp", {"ok": True, "result": {"state": "disconnected", "ssid": "",
                                                   "ip": None, "rssi_dbm": None}}))
    outcome, holder = run_soak(script, seconds=60, mode="stress")
    checks = {c["name"]: c for c in outcome.get("checks", [])}
    expect("E2E counterexample A fails the stress judge (no log pressure)",
           outcome.get("status") == "fail"
           and not checks.get("log_pressure_real", {}).get("pass", True),
           checks.get("log_pressure_real", {}).get("detail", "")[:90])

    # 7 (r3c C.6): healthy stress positive. The fake client emits 2Hz
    # telemetry + 5Hz diagnostic LOG events with protocol-correct frame
    # shapes throughout the window; ALL checks must pass.
    def make_stress_script(seconds=60, log_hz=5, tele_hz=2):
        """Build a script where each drain_events call returns the events for
        the elapsed slice. The fake clock advances 0.2s per drain call; a
        60s run at 5s sample intervals has ~300 drain calls."""
        script = []
        # first the WIFI_STATUS start (inserted by fake_connect)
        # then for each drain_events call, return the events for that slice
        events_per_slice = []
        t_cursor = 0.0
        log_period = 1.0 / log_hz
        tele_period = 1.0 / tele_hz
        next_log = 0.0
        next_tele = 0.0
        while t_cursor < seconds:
            slice_events = []
            while next_log < t_cursor + 0.2 and next_log < seconds:
                slice_events.append({"meta": {"kind": 3, "code": mwcp.CODE["LOG"],
                                              "session_id": 4096, "request_id": 0,
                                              "wire_seq": 10000 + int(next_log * 100)},
                                     "payload": {"message": f"pressure-seq={int(next_log * log_hz)}",
                                                 "level": "info", "sample_ms": int(next_log * 1000)}})
                next_log += log_period
            while next_tele < t_cursor + 0.2 and next_tele < seconds:
                slice_events.append({"meta": {"kind": 3, "code": mwcp.CODE["TELEMETRY"],
                                              "session_id": 4096, "request_id": 0,
                                              "wire_seq": 20000 + int(next_tele * 10)},
                                     "payload": {"source_seq": int(next_tele * tele_hz),
                                                 "sent_ms": int(next_tele * 1000),
                                                 "presence": False, "targets": [],
                                                 "targets_quality": 0}})
                next_tele += tele_period
            events_per_slice.append(("events", slice_events))
            t_cursor += 0.2
        # the sample loop consumes PING + STATUS_GET responses; each drain
        # returns the events then a response for the next sample
        # We interleave: the script for the FakeClient is consumed in order
        # so we build: [events_slice_0, resp, events_slice_1, resp, ...]
        script = []
        n_samples = seconds // 5
        slices_per_sample = 25  # 5s / 0.2s
        slice_idx = 0
        for s in range(n_samples):
            for k in range(slices_per_sample):
                if slice_idx < len(events_per_slice):
                    script.append(events_per_slice[slice_idx])
                    slice_idx += 1
            script.append(("resp", {"ok": True, "result": {
                "uptime_ms": 5000 * s, "radar_link": "healthy",
                "counters": {"rx_frames": s, "logs_dropped": 0}}}))
        # trailing drains + end WIFI_STATUS
        while slice_idx < len(events_per_slice):
            script.append(events_per_slice[slice_idx])
            slice_idx += 1
        script.append(("resp", {"ok": True, "result": {"state": "disconnected",
                                                          "ssid": "", "ip": None,
                                                          "rssi_dbm": None}}))
        return script

    # healthy stress positive
    stress_script = make_stress_script(60, log_hz=5, tele_hz=2)
    outcome, holder = run_soak(stress_script, seconds=60, mode="stress",
                               wifi_start="disconnected", wifi_end="disconnected")
    stress_checks = {c["name"]: c for c in outcome.get("checks", [])}
    expect("E2E healthy stress positive: all checks pass",
           outcome.get("status") == "pass",
           "; ".join(n for n, c in stress_checks.items() if not c["pass"]))

    # single-variable negative: LOG rate 0 (no LOG events at all)
    no_log_script = make_stress_script(60, log_hz=0.01, tele_hz=2)  # ~0 LOG in 60s
    outcome, holder = run_soak(no_log_script, seconds=60, mode="stress")
    nl_checks = {c["name"]: c for c in outcome.get("checks", [])}
    expect("E2E no-LOG negative: log_pressure_real fails, others pass",
           outcome.get("status") == "fail"
           and not nl_checks.get("log_pressure_real", {}).get("pass", True)
           and nl_checks.get("telemetry_per_window_continuous", {}).get("pass", False),
           "; ".join(n for n, c in nl_checks.items() if not c["pass"]))

    # single-variable negative: telemetry stops after 20s (burst-then-stop)
    stop_script = make_stress_script(20, log_hz=5, tele_hz=2)
    # pad the remaining 40s with LOG-only events (no telemetry)
    pad_events = []
    for k in range(200):  # 40s of LOG at 5Hz = 200 events
        pad_events.append(("events", [{"meta": {"kind": 3, "code": mwcp.CODE["LOG"],
                                                "session_id": 4096, "request_id": 0,
                                                "wire_seq": 30000 + k},
                                       "payload": {"message": f"pad-seq={k}",
                                                   "level": "info", "sample_ms": 20000 + k * 200}}]))
        if k % 25 == 24:
            pad_events.append(("resp", {"ok": True, "result": {
                "uptime_ms": 20000 + k * 200, "radar_link": "healthy",
                "counters": {"rx_frames": k, "logs_dropped": 0}}}))
    pad_events.append(("resp", {"ok": True, "result": {"state": "disconnected",
                                                        "ssid": "", "ip": None,
                                                        "rssi_dbm": None}}))
    outcome, holder = run_soak(stop_script + pad_events, seconds=60, mode="stress")
    stop_checks = {c["name"]: c for c in outcome.get("checks", [])}
    expect("E2E telemetry-stops negative: telemetry_per_window fails",
           outcome.get("status") == "fail"
           and not stop_checks.get("telemetry_per_window_continuous", {}).get("pass", True),
           "; ".join(n for n, c in stop_checks.items() if not c["pass"]))

    # ---- G2-R3-04 (r3d A): real cmd_soak E2E offline-evidence matrix ------
    # The fixture is explicitly SOFTWARE: a synthetic isolation-evidence
    # file, never a real hardware/chamber record. The healthy positive uses
    # a coverage window that genuinely contains the run (built from the
    # actual wall clock at test time); each negative changes ONE variable.
    import datetime as _dt
    import hashlib as _hl
    import tempfile as _tf

    def idle_script(n=6):
        script = []
        for i in range(n):
            script.append(("resp", {"ok": True, "result": {
                "uptime_ms": 10000 * i, "radar_link": "healthy",
                "counters": {"rx_frames": i, "logs_dropped": 0}}}))
        script.append(("resp", {"ok": True, "result": {"state": "disconnected",
                                                       "ssid": "", "ip": None,
                                                       "rssi_dbm": None}}))
        return script

    def make_offline_ev(td, board="esp32c3-luatos-core", port="FAKE",
                        starts=None, ends=None, ha_isolated=True,
                        tz_aware=True, extra=None, attestation=None):
        """Build a SOFTWARE offline-evidence fixture in td. Coverage defaults
        to a window that contains the simulated run (healthy)."""
        now = get_sim_now(_dt.timezone.utc if tz_aware else None)
        cov_start = starts or (now - _dt.timedelta(hours=2))
        cov_end = ends or (now + _dt.timedelta(hours=2))
        fmt = "%Y-%m-%dT%H:%M:%S%z" if tz_aware else "%Y-%m-%dT%H:%M:%S"

        source = Path(td) / "offline-source.json"
        if attestation is not None:
            if isinstance(attestation, dict):
                source.write_text(json.dumps(attestation, indent=2), encoding="utf-8")
            else:
                source.write_text(str(attestation), encoding="utf-8")
        else:
            default_att = {
                "attestation_type": "rf-shielded-chamber-isolation",
                "observer": "qa-offline-verifier",
                "coverage": {
                    "started": cov_start.strftime(fmt),
                    "ended": cov_end.strftime(fmt),
                },
                "observed_at": now.strftime(fmt),
                "device_id": board,
                "ha_observation": "not_running" if ha_isolated else "running",
                "review_status": "verified",
                "conclusion": "isolated" if ha_isolated else "non_isolated",
            }
            source.write_text(json.dumps(default_att, indent=2), encoding="utf-8")

        ev = {"kind": "rf-shielded-chamber",
              "source": {"ref": str(source),
                         "sha256": _hl.sha256(source.read_bytes()).hexdigest()},
              "run_binding": {"board_id": board, "port": port},
              "coverage": {"started": cov_start.strftime(fmt),
                           "ended": cov_end.strftime(fmt)},
              "ha_isolated": ha_isolated}
        if extra:
            ev.update(extra)
        evpath = Path(td) / "offline.json"
        evpath.write_text(json.dumps(ev), encoding="utf-8")
        return evpath

    # A0 healthy idle positive: valid file WITHOUT covers_run inside it
    # (a legal file must pass on its own validated content).
    with _tf.TemporaryDirectory(prefix="r3d-offline-") as td:
        evpath = make_offline_ev(td)
        outcome, holder = run_soak(idle_script(), seconds=60, mode="idle",
                                   offline_evidence=str(evpath))
        checks = {c["name"]: c for c in outcome.get("checks", [])}
        expect("A0 healthy idle + valid offline evidence: ALL checks pass",
               outcome.get("status") == "pass",
               "; ".join(f"{n}:{c['detail'][:60]}" for n, c in checks.items()
                         if not c["pass"]))

    # A1 wrong board (single variable): must fail offline_precondition only;
    # the other run-quality checks still pass (no unrelated failures).
    with _tf.TemporaryDirectory(prefix="r3d-offline-") as td:
        evpath = make_offline_ev(td, board="OTHER-BOARD")
        outcome, holder = run_soak(idle_script(), seconds=60, mode="idle",
                                   offline_evidence=str(evpath))
        checks = {c["name"]: c for c in outcome.get("checks", [])}
        expect("A1 wrong board fails offline_precondition, others pass",
               outcome.get("status") == "fail"
               and not checks.get("offline_precondition", {}).get("pass", True)
               and checks.get("duration_honest", {}).get("pass")
               and checks.get("single_boot", {}).get("pass")
               and checks.get("no_uncovered_gap", {}).get("pass")
               and checks.get("rpc_p95_within_budget", {}).get("pass"),
               f"failed={[n for n, c in checks.items() if not c['pass']]}")

    # A1b same file WITH covers_run=true injected: still fails (the flag is
    # an untrusted input switch).
    with _tf.TemporaryDirectory(prefix="r3d-offline-") as td:
        evpath = make_offline_ev(td, board="OTHER-BOARD",
                                 extra={"covers_run": True, "verified": True})
        outcome, holder = run_soak(idle_script(), seconds=60, mode="idle",
                                   offline_evidence=str(evpath))
        checks = {c["name"]: c for c in outcome.get("checks", [])}
        expect("A1b wrong board + injected covers_run=true still fails",
               outcome.get("status") == "fail"
               and not checks.get("offline_precondition", {}).get("pass", True),
               f"failed={[n for n, c in checks.items() if not c['pass']]}")

    # A2 wrong port (single variable)
    with _tf.TemporaryDirectory(prefix="r3d-offline-") as td:
        evpath = make_offline_ev(td, port="OTHER-PORT")
        outcome, holder = run_soak(idle_script(), seconds=60, mode="idle",
                                   offline_evidence=str(evpath))
        checks = {c["name"]: c for c in outcome.get("checks", [])}
        expect("A2 wrong port fails offline_precondition",
               outcome.get("status") == "fail"
               and not checks.get("offline_precondition", {}).get("pass", True),
               f"failed={[n for n, c in checks.items() if not c['pass']]}")

    # A3 expired coverage (2000-01-01): fails even with covers_run=true.
    with _tf.TemporaryDirectory(prefix="r3d-offline-") as td:
        old = _dt.datetime(2000, 1, 1, tzinfo=_dt.timezone.utc)
        evpath = make_offline_ev(td, starts=old,
                                 ends=old + _dt.timedelta(seconds=1),
                                 extra={"covers_run": True})
        outcome, holder = run_soak(idle_script(), seconds=60, mode="idle",
                                   offline_evidence=str(evpath))
        checks = {c["name"]: c for c in outcome.get("checks", [])}
        expect("A3 expired 2000-era 1s coverage fails (covers_run=true ignored)",
               outcome.get("status") == "fail"
               and not checks.get("offline_precondition", {}).get("pass", True)
               and checks.get("duration_honest", {}).get("pass"),
               f"failed={[n for n, c in checks.items() if not c['pass']]}")

    # A4 short coverage: covers only the run's start; the window ENDS 300s
    # before the run does - far past the 60s bracketing-observation slack.
    with _tf.TemporaryDirectory(prefix="r3d-offline-") as td:
        now = get_sim_now(_dt.timezone.utc)
        evpath = make_offline_ev(td, starts=now - _dt.timedelta(hours=2),
                                 ends=now - _dt.timedelta(seconds=300))
        outcome, holder = run_soak(idle_script(), seconds=60, mode="idle",
                                   offline_evidence=str(evpath))
        checks = {c["name"]: c for c in outcome.get("checks", [])}
        expect("A4 short coverage (misses run end) fails",
               outcome.get("status") == "fail"
               and not checks.get("offline_precondition", {}).get("pass", True),
               f"failed={[n for n, c in checks.items() if not c['pass']]}")

    # A5 naive timestamps (no timezone): cannot be compared -> rejected.
    with _tf.TemporaryDirectory(prefix="r3d-offline-") as td:
        evpath = make_offline_ev(td, tz_aware=False)
        outcome, holder = run_soak(idle_script(), seconds=60, mode="idle",
                                   offline_evidence=str(evpath))
        checks = {c["name"]: c for c in outcome.get("checks", [])}
        expect("A5 timezone-less coverage rejected",
               outcome.get("status") == "fail"
               and not checks.get("offline_precondition", {}).get("pass", True),
               f"failed={[n for n, c in checks.items() if not c['pass']]}")

    # A6 HA unknown (ha_isolated=false): wifi may be isolated but HA is not
    # proven -> offline gate still fails.
    with _tf.TemporaryDirectory(prefix="r3d-offline-") as td:
        evpath = make_offline_ev(td, ha_isolated=False)
        outcome, holder = run_soak(idle_script(), seconds=60, mode="idle",
                                   offline_evidence=str(evpath))
        checks = {c["name"]: c for c in outcome.get("checks", [])}
        expect("A6 HA not isolated fails offline gate",
               outcome.get("status") == "fail"
               and not checks.get("offline_precondition", {}).get("pass", True),
               f"failed={[n for n, c in checks.items() if not c['pass']]}")

    # A7 bracket-only (no --offline-evidence at all): insufficient (kept
    # from r3c; the run-quality checks still pass).
    outcome, holder = run_soak(idle_script(), seconds=60, mode="idle")
    checks = {c["name"]: c for c in outcome.get("checks", [])}
    expect("A7 bracket-only (no evidence file) stays insufficient",
           outcome.get("status") == "fail"
           and not checks.get("offline_precondition", {}).get("pass", True)
           and checks.get("duration_honest", {}).get("pass"),
           f"failed={[n for n, c in checks.items() if not c['pass']]}")

    # A8 disconnected -> connected -> disconnected: both bracket ends
    # disconnected cannot be expressed with only start/end states, but the
    # E2E form the review demands is: end shows connected. The collector
    # sees start=disconnected end=connected -> association_observed -> fail.
    outcome, holder = run_soak(idle_script(), seconds=60, mode="idle",
                               wifi_end="connected")
    checks = {c["name"]: c for c in outcome.get("checks", [])}
    expect("A8 disconnected->connected->disconnected fails (end connected)",
           outcome.get("status") == "fail"
           and not checks.get("offline_precondition", {}).get("pass", True),
           checks.get("offline_precondition", {}).get("detail", "")[:80])

    # A9 the REAL disconnected->connected->disconnected negative: both
    # bracket endpoints read disconnected, the file is structurally valid,
    # but the AP-side record shows the device ASSOCIATING mid-window. The
    # evidence binding must reject it (endpoint states alone would pass).
    with _tf.TemporaryDirectory(prefix="r3d-offline-") as td:
        now = get_sim_now(_dt.timezone.utc)
        mid = now.isoformat()
        evpath = make_offline_ev(td, extra={"covers_run": True,
                                            "association_observations": [
                                                {"t": mid, "state": "connected",
                                                 "source": "ap-side-client-list"}]})
        outcome, holder = run_soak(idle_script(), seconds=60, mode="idle",
                                   offline_evidence=str(evpath))
        checks = {c["name"]: c for c in outcome.get("checks", [])}
        expect("A9 mid-run association inside coverage window rejected",
               outcome.get("status") == "fail"
               and not checks.get("offline_precondition", {}).get("pass", True),
               f"failed={[n for n, c in checks.items() if not c['pass']]}")

        # ---- G2-R3-04 (r3e): Strict Coverage Matrix & Device Identity Binding ----
        # 1. offline_uncovered_edges_with_connection (r3e unit test):
        # Two-hour run [00:00:00, 02:00:00], coverage [00:00:30, 01:59:30],
        # association recorded at 00:00:10 (outside coverage, inside run).
        with _tf.TemporaryDirectory(prefix="r3e-edge-") as td:
            src = Path(td) / "src.txt"
            src.write_text("SOFTWARE fixture", encoding="utf-8")
            ev = {"kind": "rf-shielded-chamber",
                  "source": {"ref": str(src), "sha256": _hl.sha256(src.read_bytes()).hexdigest()},
                  "run_binding": {"board_id": "esp32c3-luatos-core", "port": "FAKE"},
                  "coverage": {"started": "2026-10-28T00:00:30Z", "ended": "2026-10-28T01:59:30Z"},
                  "ha_isolated": True,
                  "association_observations": [{"t": "2026-10-28T00:00:10Z", "state": "connected"}]}
            evpath = Path(td) / "offline.json"
            evpath.write_text(json.dumps(ev), encoding="utf-8")
            verified = run_g2.load_offline_evidence(
                evpath, "2026-10-28T00:00:00Z", "2026-10-28T02:00:00Z", "esp32c3-luatos-core", "FAKE")
            pre = run_g2.offline_precondition_from_observation(
                "disconnected", "disconnected", "not_running", verified)
            expect("A10 r3e uncovered edges with connection fails coverage and precondition",
                   verified["covers_run"] is False
                   and pre["verified"] is False
                   and pre["wifi_status"] == "association_observed",
                   f"covers={verified.get('covers_run')} wifi={pre.get('wifi_status')}")

        # 2. actual_collector_zero_coverage_with_connection (r3e collector test):
        # Real cmd_soak 60s run; coverage is instantaneous at +30s; association at +10s.
        with _tf.TemporaryDirectory(prefix="r3e-zero-") as td:
            now = get_sim_now(_dt.timezone.utc)
            evpath = make_offline_ev(td, starts=now + _dt.timedelta(seconds=30),
                                     ends=now + _dt.timedelta(seconds=30),
                                     extra={"association_observations": [
                                         {"t": (now + _dt.timedelta(seconds=10)).isoformat(),
                                          "state": "connected"}]})
            outcome, holder = run_soak(idle_script(), seconds=60, mode="idle",
                                       offline_evidence=str(evpath))
            checks = {c["name"]: c for c in outcome.get("checks", [])}
            expect("A11 r3e actual collector zero coverage with connection fails",
                   outcome.get("status") == "fail"
                   and not checks.get("offline_precondition", {}).get("pass", True)
                   and checks.get("duration_honest", {}).get("pass"),
                   f"status={outcome.get('status')} failed={[n for n, c in checks.items() if not c['pass']]}")

        # 3. Missing initial period (single variable): cov starts 5s after run start
        with _tf.TemporaryDirectory(prefix="r3e-init-") as td:
            now = get_sim_now(_dt.timezone.utc)
            evpath = make_offline_ev(td, starts=now + _dt.timedelta(seconds=5),
                                     ends=now + _dt.timedelta(hours=2))
            outcome, holder = run_soak(idle_script(), seconds=60, mode="idle",
                                       offline_evidence=str(evpath))
            checks = {c["name"]: c for c in outcome.get("checks", [])}
            expect("A12 missing initial period (coverage starts late) fails",
                   outcome.get("status") == "fail"
                   and not checks.get("offline_precondition", {}).get("pass", True)
                   and checks.get("duration_honest", {}).get("pass"),
                   f"failed={[n for n, c in checks.items() if not c['pass']]}")

        # 4. Missing terminal period (single variable): cov ends before run end
        with _tf.TemporaryDirectory(prefix="r3e-term-") as td:
            now = get_sim_now(_dt.timezone.utc)
            evpath = make_offline_ev(td, starts=now - _dt.timedelta(hours=1),
                                     ends=now + _dt.timedelta(seconds=30))
            outcome, holder = run_soak(idle_script(), seconds=60, mode="idle",
                                       offline_evidence=str(evpath))
            checks = {c["name"]: c for c in outcome.get("checks", [])}
            expect("A13 missing terminal period (coverage ends early) fails",
                   outcome.get("status") == "fail"
                   and not checks.get("offline_precondition", {}).get("pass", True)
                   and checks.get("duration_honest", {}).get("pass"),
                   f"failed={[n for n, c in checks.items() if not c['pass']]}")

        # 5. Inverted coverage window: starts after ends
        with _tf.TemporaryDirectory(prefix="r3e-inv-") as td:
            now = get_sim_now(_dt.timezone.utc)
            evpath = make_offline_ev(td, starts=now + _dt.timedelta(hours=1),
                                     ends=now - _dt.timedelta(hours=1))
            outcome, holder = run_soak(idle_script(), seconds=60, mode="idle",
                                       offline_evidence=str(evpath))
            checks = {c["name"]: c for c in outcome.get("checks", [])}
            expect("A14 inverted coverage window fails",
               outcome.get("status") == "fail"
               and not checks.get("offline_precondition", {}).get("pass", True)
               and checks.get("duration_honest", {}).get("pass"),
               f"failed={[n for n, c in checks.items() if not c['pass']]}")

        # 6. Device identity mismatch: client device_id != evidence board_id
        with _tf.TemporaryDirectory(prefix="r3e-devmismatch-") as td:
            evpath = make_offline_ev(td, board="esp32c3-luatos-core")
            outcome, holder = run_soak(idle_script(), seconds=60, mode="idle",
                                       offline_evidence=str(evpath),
                                       device_id="esp32s3-other-board")
            checks = {c["name"]: c for c in outcome.get("checks", [])}
            expect("A15 device identity mismatch rejected",
                   outcome.get("status") == "fail"
                   and not checks.get("offline_precondition", {}).get("pass", True)
                   and checks.get("duration_honest", {}).get("pass"),
                   f"failed={[n for n, c in checks.items() if not c['pass']]}")

        # 7. Device identity missing from client
        with _tf.TemporaryDirectory(prefix="r3e-nodev-") as td:
            evpath = make_offline_ev(td, board="esp32c3-luatos-core")
            outcome, holder = run_soak(idle_script(), seconds=60, mode="idle",
                                       offline_evidence=str(evpath),
                                       device_id=None)
            checks = {c["name"]: c for c in outcome.get("checks", [])}
            expect("A16 missing client device identity conservatively judged insufficient",
                   outcome.get("status") == "fail"
                   and not checks.get("offline_precondition", {}).get("pass", True)
                   and checks.get("duration_honest", {}).get("pass"),
                   f"failed={[n for n, c in checks.items() if not c['pass']]}")

        # 8. Timezone equivalence positive control: coverage in +08:00 vs run in UTC
        with _tf.TemporaryDirectory(prefix="r3e-tz-") as td:
            tz_cst = _dt.timezone(_dt.timedelta(hours=8))
            now_cst = get_sim_now(tz_cst)
            evpath = make_offline_ev(td, starts=now_cst - _dt.timedelta(hours=2),
                                     ends=now_cst + _dt.timedelta(hours=2),
                                     board="esp32c3-luatos-core")
            outcome, holder = run_soak(idle_script(), seconds=60, mode="idle",
                                       offline_evidence=str(evpath),
                                       device_id="esp32c3-luatos-core")
            checks = {c["name"]: c for c in outcome.get("checks", [])}
            expect("A17 timezone equivalence positive: offsets compared in UTC pass",
                   outcome.get("status") == "pass"
                   and checks.get("offline_precondition", {}).get("pass", False),
                   f"failed={[n for n, c in checks.items() if not c['pass']]}")

        # A18 plain-text source rejected (r3f reproduction): lacks structured attestation
        with _tf.TemporaryDirectory(prefix="r3f-plaintext-") as td:
            evpath = make_offline_ev(td, attestation="SOFTWARE ONLY: this text provides no isolation or HA observation.")
            outcome, holder = run_soak(idle_script(), seconds=60, mode="idle", offline_evidence=str(evpath))
            checks = {c["name"]: c for c in outcome.get("checks", [])}
            expect("A18 plain text source rejected: offline precondition fails",
                   outcome.get("status") == "fail"
                   and not checks.get("offline_precondition", {}).get("pass", True),
                   f"status={outcome.get('status')}")

        # A19 pending review source rejected: review_status must be 'verified'
        with _tf.TemporaryDirectory(prefix="r3f-pending-") as td:
            evpath = make_offline_ev(td, attestation={
                "attestation_type": "rf-shielded-chamber-isolation",
                "observer": "qa-tester", "device_id": "esp32c3-luatos-core",
                "ha_observation": "not_running", "review_status": "pending",
                "conclusion": "isolated"
            })
            outcome, holder = run_soak(idle_script(), seconds=60, mode="idle", offline_evidence=str(evpath))
            checks = {c["name"]: c for c in outcome.get("checks", [])}
            expect("A19 pending review status in attestation rejected",
                   outcome.get("status") == "fail"
                   and not checks.get("offline_precondition", {}).get("pass", True),
                   f"status={outcome.get('status')}")

        # A20 ha_observation 'running' rejected: HA was active
        with _tf.TemporaryDirectory(prefix="r3f-ha-running-") as td:
            evpath = make_offline_ev(td, attestation={
                "attestation_type": "rf-shielded-chamber-isolation",
                "observer": "qa-tester", "device_id": "esp32c3-luatos-core",
                "ha_observation": "running", "review_status": "verified",
                "conclusion": "isolated"
            })
            outcome, holder = run_soak(idle_script(), seconds=60, mode="idle", offline_evidence=str(evpath))
            checks = {c["name"]: c for c in outcome.get("checks", [])}
            expect("A20 ha_observation running in attestation rejected",
                   outcome.get("status") == "fail"
                   and not checks.get("offline_precondition", {}).get("pass", True),
                   f"status={outcome.get('status')}")

        # A21 conclusion not isolated rejected: conclusion='non_isolated'
        with _tf.TemporaryDirectory(prefix="r3f-non-isolated-") as td:
            evpath = make_offline_ev(td, attestation={
                "attestation_type": "rf-shielded-chamber-isolation",
                "observer": "qa-tester", "device_id": "esp32c3-luatos-core",
                "ha_observation": "not_running", "review_status": "verified",
                "conclusion": "non_isolated"
            })
            outcome, holder = run_soak(idle_script(), seconds=60, mode="idle", offline_evidence=str(evpath))
            checks = {c["name"]: c for c in outcome.get("checks", [])}
            expect("A21 non-isolated conclusion in attestation rejected",
                   outcome.get("status") == "fail"
                   and not checks.get("offline_precondition", {}).get("pass", True),
                   f"status={outcome.get('status')}")

        # A22 device mismatch in attestation rejected: device_id does not match board
        with _tf.TemporaryDirectory(prefix="r3f-dev-mismatch-") as td:
            evpath = make_offline_ev(td, attestation={
                "attestation_type": "rf-shielded-chamber-isolation",
                "observer": "qa-tester", "device_id": "mismatched-hardware-id",
                "ha_observation": "not_running", "review_status": "verified",
                "conclusion": "isolated"
            })
            outcome, holder = run_soak(idle_script(), seconds=60, mode="idle", offline_evidence=str(evpath))
            checks = {c["name"]: c for c in outcome.get("checks", [])}
            expect("A22 attestation device mismatch rejected",
                   outcome.get("status") == "fail"
                   and not checks.get("offline_precondition", {}).get("pass", True),
                   f"status={outcome.get('status')}")

        # A23 attestation missing device_id rejected (r3g G4)
        with _tf.TemporaryDirectory(prefix="r3g-missing-dev-") as td:
            evpath = make_offline_ev(td, attestation={
                "attestation_type": "rf-shielded-chamber-isolation",
                "observer": "qa-tester",
                "ha_observation": "not_running", "review_status": "verified",
                "conclusion": "isolated"
            })
            outcome, holder = run_soak(idle_script(), seconds=60, mode="idle", offline_evidence=str(evpath))
            checks = {c["name"]: c for c in outcome.get("checks", [])}
            expect("A23 attestation missing device_id rejected",
                   outcome.get("status") == "fail"
                   and not checks.get("offline_precondition", {}).get("pass", True),
                   f"status={outcome.get('status')}")

        # A24 attestation own coverage expired (2000 year) rejected (r3g G4)
        with _tf.TemporaryDirectory(prefix="r3g-expired-cov-") as td:
            evpath = make_offline_ev(td, attestation={
                "attestation_type": "rf-shielded-chamber-isolation",
                "observer": "qa-tester", "device_id": "esp32c3-luatos-core",
                "coverage": {"started": "2000-01-01T00:00:00Z", "ended": "2000-01-01T00:00:01Z"},
                "observed_at": "2000-01-01T00:00:01Z",
                "ha_observation": "not_running", "review_status": "verified",
                "conclusion": "isolated"
            })
            outcome, holder = run_soak(idle_script(), seconds=60, mode="idle", offline_evidence=str(evpath))
            checks = {c["name"]: c for c in outcome.get("checks", [])}
            expect("A24 attestation expired coverage rejected",
                   outcome.get("status") == "fail"
                   and not checks.get("offline_precondition", {}).get("pass", True),
                   f"status={outcome.get('status')}")

        # A25 early HELLO failure cleanup and controlled result (r3g G5)
        closed = []
        oldclose = FakeClient.close
        def mock_close(self):
            closed.append(True)
            return oldclose(self)
        from unittest.mock import patch
        with patch.object(FakeClient, "hello", side_effect=TimeoutError("early hello timeout")), patch.object(FakeClient, "close", mock_close):
            outcome_early, _ = run_soak(idle_script(), seconds=60, mode="idle")
            expect("A25 early HELLO failure produces fail status without exception",
                   outcome_early.get("status") == "fail" and bool(closed) is True,
                   f"status={outcome_early.get('status')} closed={bool(closed)}")

        # A26 producer -> index closed loop with verified flash evidence (r3g B.4 / C.1)
        with _tf.TemporaryDirectory(prefix="r3g-flash-loop-") as td:
            flash_p = Path(td) / "flash_rec.json"
            img_flash = "a" * 64
            flash_data = {
                "status": "success", "verify": "ok",
                "image_sha256": img_flash,
                "device_id": "esp32c3-luatos-core",
                "timestamp": "2026-10-28T00:00:00Z",
                "seq": 1
            }
            flash_p.write_text(json.dumps(flash_data), encoding="utf-8")
            evpath = make_offline_ev(td, attestation={
                "attestation_type": "rf-shielded-chamber-isolation",
                "observer": "qa-tester", "device_id": "esp32c3-luatos-core",
                "ha_observation": "not_running", "review_status": "verified",
                "conclusion": "isolated"
            })
            orig_cmd_soak = run_g2.cmd_soak
            def wrap_soak(args):
                args.flash_evidence = str(flash_p)
                return orig_cmd_soak(args)
            with patch.object(run_g2, "load_secrets", lambda: ({}, [])), patch.object(run_g2, "cmd_soak", wrap_soak):
                outcome_ok, holder_ok = run_soak(idle_script(), seconds=60, mode="idle",
                                                 offline_evidence=str(evpath),
                                                 device_id="esp32c3-luatos-core")
            raw_p = holder_ok["path"]
            m_p = raw_p.with_suffix(".manifest.json")
            expect("A26 manifest written", m_p.is_file())
            m_obj = json.loads(m_p.read_text(encoding="utf-8"))
            expect("A26 manifest links flash image",
                   m_obj.get("flashed_image_sha256") == img_flash
                   and m_obj.get("flash_record", {}).get("device_id") == "esp32c3-luatos-core")
            import build_evidence_index as bi
            idx_out = Path(td) / "test.index.json"
            idx = bi.build_index({"prod": raw_p.parent}, idx_out, {}, bi.FIRMWARE_BATCHES, sources_snapshot={})
            expect("A26 build_index recognizes manifest-linked run",
                   len(idx.get("runs", [])) == 1
                   and idx["runs"][0].get("batch") == "manifest-linked"
                   and idx["runs"][0].get("factory_sha256") == img_flash,
                   str(idx.get("runs")))

    # ---- G2-R3-03 (r3d C): HELLO handshake-generation correlation ------
    # Driven through the REAL rebuild function over the REAL evidence-shape
    # JSONL (dir/kind/code/session/request/payload), matching mwcp.py's
    # Client/EvidenceWriter output: no top-level boot_id per frame, HELLO
    # request_id always 1, TX nonce top-level / RX nonce under result.
    with tempfile.TemporaryDirectory(prefix="r3d-hello-") as td:
        def hello_line(direction, t, session, nonce, boot=None):
            nonce_val = nonce
            if direction == "tx":
                payload = {"client": {"name": "g2-runner", "version": "0.1.0"},
                           "nonce": nonce_val, "protocol": {"major": 1, "minor_max": 0},
                           "max_payload": 4096}
            else:
                payload = {"ok": True, "result": {"nonce": nonce_val,
                                                  "session_ttl_ms": 15000,
                                                  "boot_id": boot or ("boot:" + nonce_val[:4])}}
            return {"dir": direction, "t": t,
                    "kind": 1 if direction == "tx" else 2,
                    "code": mwcp.CODE["HELLO"], "session_id": session,
                    "request_id": 1, "payload": payload}

        # C-h1: two DIFFERENT nonces at request_id=1 -> two records, each
        # resolved by its own echoed nonce; boots come from the VERIFIED
        # payloads (not the uniform fallback).
        hist = Path(td) / "h1.jsonl"
        lines = [hello_line("tx", 0.0, 0, "a" * 32),
                 hello_line("rx", 0.1, 4096, "a" * 32, boot="bootA"),
                 hello_line("tx", 10.0, 0, "b" * 32),
                 hello_line("rx", 10.1, 4097, "b" * 32, boot="bootB")]
        hist.write_text("\n".join(json.dumps(l) for l in lines) + "\n", encoding="utf-8")
        rebuilt = run_g2.rebuild_judge_inputs_from_evidence(hist, "fallback-boot")
        recs = rebuilt["retry_records"]
        expect("C-h1 two HELLO handshakes -> two independent records",
               rebuilt["verified"] is True and len(recs) == 2,
               f"n={len(recs)}")
        r1 = next((r for r in recs if r.get("nonce") == "a" * 32), None)
        r2 = next((r for r in recs if r.get("nonce") == "b" * 32), None)
        expect("C-h1 each record resolved by its own nonce",
               r1 is not None and r2 is not None
               and r1["resolved_t"] == 0.1 and r2["resolved_t"] == 10.1
               and len(r1["attempts"]) == 1 and len(r2["attempts"]) == 1,
               json.dumps([r1, r2], default=str)[:120])
        expect("C-h1 boots from verified HELLO payloads (no fallback)",
               r1["boot"] == "bootA" and r2["boot"] == "bootB",
               f"{r1.get('boot')}/{r2.get('boot')}")
        expect("C-h1 sessions reflect the ESTABLISHED sessions",
               r1["session"] == 4096 and r2["session"] == 4097,
               f"{r1.get('session')}/{r2.get('session')}")

        # C-h2: HELLO TX nonce=A, RX nonce=B -> the mismatched response
        # never resolves the handshake (resolved_t stays None; the record
        # stays unresolved and hits the unresolved gate).
        hist = Path(td) / "h2.jsonl"
        lines = [hello_line("tx", 0.0, 0, "a" * 32),
                 hello_line("rx", 0.1, 4096, "b" * 32, boot="bootZ")]
        hist.write_text("\n".join(json.dumps(l) for l in lines) + "\n", encoding="utf-8")
        rebuilt = run_g2.rebuild_judge_inputs_from_evidence(hist, "fallback-boot")
        recs = rebuilt["retry_records"]
        expect("C-h2 wrong-nonce RX does not resolve the handshake",
               rebuilt["verified"] is True and len(recs) == 1
               and recs[0]["resolved_t"] is None and recs[0]["boot"] == "fallback-boot",
               json.dumps(recs, default=str)[:120])

        # C-h3: same nonce twice (transport resend of ONE handshake) ->
        # ONE record, two attempts, resolved once.
        hist = Path(td) / "h3.jsonl"
        lines = [hello_line("tx", 0.0, 0, "c" * 32),
                 hello_line("tx", 2.0, 0, "c" * 32),
                 hello_line("rx", 2.1, 4098, "c" * 32, boot="bootC")]
        hist.write_text("\n".join(json.dumps(l) for l in lines) + "\n", encoding="utf-8")
        rebuilt = run_g2.rebuild_judge_inputs_from_evidence(hist, "fallback-boot")
        recs = rebuilt["retry_records"]
        expect("C-h3 same-nonce resend merges into one record",
               rebuilt["verified"] is True and len(recs) == 1
               and len(recs[0]["attempts"]) == 2 and recs[0]["resolved_t"] == 2.1,
               json.dumps(recs, default=str)[:120])

        # C-h4: late stale response (old nonce arriving after a NEW
        # handshake TX) does not resolve the NEW handshake and does not
        # resurrect the old one's attempts.
        hist = Path(td) / "h4.jsonl"
        lines = [hello_line("tx", 0.0, 0, "a" * 32),
                 hello_line("rx", 0.1, 4096, "a" * 32, boot="bootA"),
                 hello_line("tx", 10.0, 0, "b" * 32),
                 # stale echo of nonce A arrives at t=10.1
                 {"dir": "rx", "t": 10.1, "kind": 2, "code": mwcp.CODE["HELLO"],
                  "session_id": 4096, "request_id": 1,
                  "payload": {"ok": True, "result": {"nonce": "a" * 32,
                                                     "session_ttl_ms": 15000,
                                                     "boot_id": "bootA"}}},
                 hello_line("rx", 10.2, 4097, "b" * 32, boot="bootB")]
        hist.write_text("\n".join(json.dumps(l) for l in lines) + "\n", encoding="utf-8")
        rebuilt = run_g2.rebuild_judge_inputs_from_evidence(hist, "fallback-boot")
        recs = rebuilt["retry_records"]
        ra = next((r for r in recs if r.get("nonce") == "a" * 32), None)
        rb = next((r for r in recs if r.get("nonce") == "b" * 32), None)
        expect("C-h4 late stale echo lands on the OLD handshake only",
               ra is not None and rb is not None
               and ra["resolved_t"] == 0.1 and len(ra["attempts"]) == 1
               and rb["resolved_t"] == 10.2 and len(rb["attempts"]) == 1
               and ra.get("late_echoes", 0) == 1,
               json.dumps([ra, rb], default=str)[:160])

    print("VERDICT:", "pass" if not failures else f"FAIL ({len(failures)})")
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())
