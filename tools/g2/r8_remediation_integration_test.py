#!/usr/bin/env python3
"""R8 remediation integration tests (review 2026-10-31, R8-01..R8-03).

All tests are offline: devices / secrets / serial / network are replaced by
fakes and every test asserts no real I/O happened.

R8-01A  Per-field sampling semantics: presence.sample_ms (and
        targets[].position_ms) are each validated on their OWN sampling
        clock; top-level sent_ms/source_seq order frames only and can never
        vouch for a new presence sample.  Legal duplicate frames are kept
        but never extend a validity span; an explicitly declared event-hold
        presence capability (expected_interval_ms=null AND stale_after_ms=
        null, as the production r60abd1-capabilities.json declares) is
        judged by transition sample + terminal frame, not by per-frame
        refresh.
R8-01B  2D coordinates are verified with the REAL transform input: the
        co-sampled metrics["diagnostics.local_z"] (sample_ms == target
        position_ms), never a guessed lz=0 when pitch/roll couple z into
        room x/y.  Expected room coordinates are computed INDEPENDENTLY in
        this file from the frozen Rz(yaw)*Rx(pitch)*Ry(roll) convention.
R8-02   Replacement admission uses only verifiable actual coverage:
        requested duration fields (duration_seconds/seconds/
        requested_seconds) never vouch; actual values must not contradict
        the started..ended window in either direction.
R8-03   Every standalone entry point (human / power / usb) reserves its
        whole output group before secrets/device I/O through the shared
        OutputPlan; a lost reservation or storage failure can never leave
        an acceptable pass result on disk.
"""

import hashlib
import json
import math
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))

import build_evidence_index as bi  # noqa: E402
import hardware_judges as hj  # noqa: E402
import human_observe_runner as hor  # noqa: E402
import power_cut_runner as pcr  # noqa: E402
import run_g2 as rg  # noqa: E402
import usb_unplug_runner as uur  # noqa: E402
import mwcp  # noqa: E402
import r5_audit_probe_integration_test as fx  # noqa: E402

sha256 = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()  # noqa: E731

# R9-01: deterministic attempt identity for harness-driven runs, so imported
# phase fixtures can be genuinely bound to the current fake attempt.
FIXED_ATTEMPT_ID = "human-0123456789abcdef"


class _FixedUUID:
    hex = "0123456789abcdef0123456789abcdef"


def _cleanup_ctx(ctx):
    """Remove the retained fake-run directory (tests call addCleanup)."""
    import shutil
    shutil.rmtree(ctx["dir"], ignore_errors=True)


# ---------------------------------------------------------------------------
# Independent frozen-contract geometry (NOT the helper under test)
# ---------------------------------------------------------------------------

def independent_room(local: list[float], cal: dict) -> list[float]:
    """Closed-form room coordinates under the frozen
    Rz(yaw)*Rx(pitch)*Ry(roll) convention (r60abd1_transform.h
    build_rotation), computed here independently of hardware_judges."""
    d = math.pi / 180.0
    cy, sy = math.cos(cal["install.yaw_deg"] * d), math.sin(cal["install.yaw_deg"] * d)
    ca, sa = math.cos(cal["install.pitch_deg"] * d), math.sin(cal["install.pitch_deg"] * d)
    cb, sb = math.cos(cal["install.roll_deg"] * d), math.sin(cal["install.roll_deg"] * d)
    lx, ly, lz = local
    wx = (cy * cb + sy * sa * sb) * lx + (sy * ca) * ly + (-cy * sb + sy * sa * cb) * lz
    wy = (-sy * cb + cy * sa * sb) * lx + (cy * ca) * ly + (sy * sb + cy * sa * cb) * lz
    wz = (ca * sb) * lx + (-sa) * ly + (ca * cb) * lz
    return [cal.get("install.x_cm", 0.0) + wx,
            cal.get("install.y_cm", 0.0) + wy,
            cal.get("install.z_cm", 0.0) + wz - wz]


# ---------------------------------------------------------------------------
# Production-shaped human telemetry fixtures (R8-01A field layout)
# ---------------------------------------------------------------------------

PERIODIC_CAPS = {
    "items": [
        {"id": "presence", "UpdateMs": 200, "StaleAfterMs": 6000},
        {"id": "position.xy", "Units": "cm", "UpdateMs": 200, "StaleAfterMs": 6000},
    ]
}
EVENT_HOLD_CAPS = {
    "items": [
        # exact production descriptor: docs/protocol/fixtures/r60abd1-capabilities.json
        {"id": "presence", "expected_interval_ms": None, "stale_after_ms": None},
        {"id": "position.xy", "Units": "cm", "UpdateMs": 200, "StaleAfterMs": 6000},
    ]
}

BASE_CAL = {
    "install.x_cm": 0.0, "install.y_cm": 0.0, "install.z_cm": 200.0,
    "install.yaw_deg": 0.0, "install.pitch_deg": 0.0, "install.roll_deg": 0.0,
    "geometry.boundary_cm": [[-100.0, -100.0], [33.0, -100.0], [33.0, 100.0], [-100.0, 100.0]],
    "areas.definitions": [],
}


POLY = [[-100.0, -100.0], [33.0, -100.0], [33.0, 100.0], [-100.0, 100.0]]


def _point_in_polygon(x: float, y: float, poly) -> bool:
    """Independent ray-casting test (production classifies boundary in ROOM
    coordinates)."""
    inside = False
    j = len(poly) - 1
    for i in range(len(poly)):
        xi, yi = poly[i]
        xj, yj = poly[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside


def production_records(n=30, exit_frames=5, exit_interval_ms=3000, cal=None,
                       presence_sample_ms="track", diag_z=None, room_2d=True,
                       entry_stride=6.0, still_x=24.0):
    """Build production-shaped telemetry: top-level sent_ms, nested
    presence.sample_ms, 2D local/room cm, targets[].position_ms, and an
    optional co-sampled metrics['diagnostics.local_z'].

    presence_sample_ms: 'track' (each frame's own sample time), a fixed
    number (frozen), or None (drop the field).  The boundary field is
    DERIVED from the expected room position (independent polygon test),
    exactly as production classifies it after the transform."""
    cal = cal or BASE_CAL
    rows = []
    present_count = n - exit_frames
    still_start = max(1, present_count // 2)
    for i in range(n):
        sent = i * 200.0
        present = i < present_count
        if present:
            x = still_x if i >= still_start else float(i) * entry_stride
        else:
            x = 0.0
        local = [x, 10.0]
        tgt = {
            "id": "t0",
            "local_cm": list(local),
            "position_quality": "valid",
            "position_ms": sent,
        }
        pres = {"value": present, "quality": "valid"}
        if presence_sample_ms == "track":
            pres["sample_ms"] = sent
        elif presence_sample_ms is not None:
            pres["sample_ms"] = float(presence_sample_ms)
        rec = {"source_seq": i + 1, "sent_ms": sent, "presence": pres}
        if present:
            if diag_z is not None:
                rec["metrics"] = {"diagnostics.local_z": {
                    "value": diag_z, "quality": "valid", "sample_ms": sent}}
            if room_2d:
                exp = independent_room(local + [diag_z if diag_z is not None else 0.0], cal)
                tgt["room_cm"] = [round(exp[0], 1), round(exp[1], 1)]
                tgt["boundary"] = ("inside" if _point_in_polygon(exp[0], exp[1], POLY)
                                   else "outside")
            rec["targets"] = [tgt]
        else:
            rec["targets"] = []
        rows.append(rec)
    base = (n - exit_frames - 1) * 200.0 + 200.0
    for i in range(exit_frames):
        rows[n - exit_frames + i]["sent_ms"] = base + i * exit_interval_ms
    if presence_sample_ms == "track":
        for i in range(exit_frames):
            rows[n - exit_frames + i]["presence"]["sample_ms"] = rows[n - exit_frames + i]["sent_ms"]
    return rows


def run_human_main(records, cal=None, capabilities=PERIODIC_CAPS, phases=None,
                   confirm=True, extra_inject=None, fail_result_write=False):
    """Drive the REAL human_observe_runner.main() with fake device/secrets.
    Returns (rc, result_doc_or_None, ctx) where ctx records device calls."""
    cal = cal or dict(BASE_CAL)
    td = tempfile.mkdtemp(prefix="r8-hor-")
    try:
        out_path = Path(td) / "human.jsonl"
        res_path = Path(td) / "human.result.json"
        events = [{"meta": {"code": hor.mwcp.CODE["TELEMETRY"]}, "payload": r} for r in records]
        # R9-01: deliver frames in THREE batches (entry/still/exit) so the
        # runner's live tracker actually captures all three phases - the
        # single-batch form is a legitimate negative (one phase only).
        # R12: align the batches with the guided phases - the still stage
        # keeps draining until the user confirms, so it captures every
        # PRESENT frame up to departure; exit takes the ABSENT tail.  A flat
        # 3-way split leaves still-phase frames in the exit batch, which no
        # real still stage would produce.
        third = max(1, len(events) // 3)
        rest = events[third:]
        exit_n = sum(1 for ev in rest
                     if isinstance(ev.get("payload"), dict)
                     and isinstance(ev["payload"].get("presence"), dict)
                     and ev["payload"]["presence"].get("value") is False)
        mid = rest[:len(rest) - exit_n] if exit_n else rest
        tail = rest[len(rest) - exit_n:] if exit_n else []
        batches = [events[:third], mid, tail]
        clock = [0.0]  # must advance >= p2_end (60s*0.6=36s) to reach exit
        device_calls = {"n": 0}

        class FakeClient:
            boot_id = "c" * 32
            session_id = 1

            def call(self, name, payload=None, **kw):
                device_calls["n"] += 1
                if name == "DEVICE_INFO":
                    return {"ok": True, "result": {"device_id": "r60-test-01", "model": "R60ABD1"}}
                if name == "CAPABILITIES_LIST":
                    return {"ok": True, "result": capabilities}
                return {"ok": True, "result": {}}

            def ping(self):
                return {"ok": True, "result": {}}

            def drain_events(self, duration_ms):
                clock[0] += 20.0  # 0→20(entry)→40(still)→60(exit): hits all 3 phases
                return batches.pop(0) if batches else []

            def close(self):
                pass

        argv = ["human_observe_runner", "--port", "COM9", "--seconds", "60",
                "--out", str(out_path), "--min-exit-ms", "10000"]
        if confirm:
            argv.append("--confirm-user-actions")
        if phases is not None:
            # R9-01: imported phase files must be BOUND to this fake attempt.
            # The harness pins the attempt UUID so the fixture genuinely
            # belongs to the current run (device/boot/session from the fake
            # client: r60-test-01 / c*32 / 1).
            pfile = Path(td) / "phases.json"
            pfile.write_text(json.dumps({
                "attempt_id": FIXED_ATTEMPT_ID,
                "session_id": 1,
                "boot_id": "c" * 32,
                "device_id": "r60-test-01",
                "phases": phases,
            }), encoding="utf-8")
            argv.extend(["--phase-confirm-file", str(pfile)])

        orig_finalize = rg.OutputPlan.finalize_file

        def maybe_fail_write(self, target, content):
            if fail_result_write and target.resolve() == res_path.resolve():
                raise OSError(28, "simulated ENOSPC (result write)")
            return orig_finalize(self, target, content)

        with fx._NoRealIO(), \
             mock.patch.object(sys, "argv", argv), \
             mock.patch.object(hor, "robust_connect", return_value=FakeClient()) as device, \
             mock.patch.object(hor.run_g2, "read_all_config", return_value=(dict(cal), "1")), \
             mock.patch.object(hor.time, "time", side_effect=lambda: clock[0]), \
             mock.patch.object(hor.time, "sleep"), \
             mock.patch.object(hor, "beep_phase"), \
             mock.patch.object(hor, "beep_complete"), \
             mock.patch.object(hor.winsound, "Beep", return_value=None), \
             mock.patch("builtins.print"), \
             mock.patch.object(hor.uuid, "uuid4", return_value=_FixedUUID()), \
             mock.patch.object(rg.OutputPlan, "finalize_file", maybe_fail_write):
            if extra_inject is not None:
                extra_inject(Path(td), out_path, res_path)
            rc = hor.main()
        result_doc = None
        if res_path.is_file():
            try:
                result_doc = json.loads(res_path.read_text(encoding="utf-8"))
            except Exception:
                result_doc = None
        return rc, result_doc, {"device_calls": device_calls["n"], "dir": Path(td),
                                "out_path": out_path, "res_path": res_path}
    except Exception:
        import shutil as _sh
        _sh.rmtree(td, ignore_errors=True)
        raise


# ---------------------------------------------------------------------------
# R8-02: replacement admission uses verifiable actual coverage only
# ---------------------------------------------------------------------------

class TestR802ActualCoverageAdmission(unittest.TestCase):
    """Supersede admission through the REAL build_index: requested duration
    fields never vouch; actual coverage must exist and match the window."""

    HELPER = fx.TestR1AEvidenceIndex()

    def _stamp(self, rp: Path, actual=None, ended=None, extra=None):
        """Explicitly stamp actual coverage / window fields on a helper run
        and re-bind the manifest's result hash. Returns the new sha."""
        d = json.loads(rp.read_text(encoding="utf-8"))
        if actual is not None:
            d["actual_duration_seconds"] = actual
            d["judge_input"]["actual_duration_seconds"] = actual
        if ended is not None:
            d["ended"] = ended
        if extra:
            d.update(extra)
        rp.write_text(json.dumps(d), encoding="utf-8")
        mp = rp.with_name(rp.name.replace(".result.json", ".manifest.json"))
        m = json.loads(mp.read_text(encoding="utf-8"))
        m["result_sha256"] = sha256(rp)
        if ended is not None:
            m["ended"] = d["ended"]
        mp.write_text(json.dumps(m), encoding="utf-8")
        return sha256(rp)

    def _pair(self, td, old_actual, new_actual, old_ended=None, new_ended=None,
              old_extra=None, new_extra=None):
        ev = Path(td) / "ev"
        ev.mkdir(exist_ok=True)
        rp_old, _ = self.HELPER._write_run(ev, "soak-old", mode="idle", complete_meta=True, duration_seconds=60)
        rp_new, _ = self.HELPER._write_run(ev, "soak-new", mode="idle", complete_meta=True, duration_seconds=7200)
        s_old = self._stamp(rp_old, old_actual, old_ended, old_extra)
        s_new = self._stamp(rp_new, new_actual, new_ended, new_extra)
        return ev, s_old, s_new

    def _build(self, td, ev, s_old, s_new):
        idx = bi.build_index({"test": ev}, Path(td) / "index.json", {
            "soak-old": {"accepted_status": "superseded", "superseded_by": "soak-new",
                         "result_sha256": s_old},
            "soak-new": {"accepted_status": "pass", "result_sha256": s_new},
        }, bi.FIRMWARE_BATCHES, sources_snapshot={})
        return {r["run_id"]: r for r in idx["runs"]}

    def test_requested_only_duration_rejected(self):
        """The review's exact counterexample: the replacement has a 1-minute
        window and NO actual coverage - only seconds/requested_seconds=7200.
        The supersede link must be rejected with a coverage reason even
        though every hash and the firmware chain match."""
        with tempfile.TemporaryDirectory(prefix="r8-idx-req-") as td:
            ev, s_old, s_new = self._pair(td, old_actual=7200,
                                          old_ended="2026-10-28T14:00:00+0000",
                                          new_actual=None,
                                          new_extra={"seconds": 7200, "requested_seconds": 7200})
            # strip the new run's judge_input duration_seconds (requested only)
            rp_new = ev / "soak-new.result.json"
            d = json.loads(rp_new.read_text(encoding="utf-8"))
            d["judge_input"].pop("duration_seconds", None)
            rp_new.write_text(json.dumps(d), encoding="utf-8")
            mp = rp_new.with_name("soak-new.manifest.json")
            m = json.loads(mp.read_text(encoding="utf-8"))
            m["result_sha256"] = sha256(rp_new)
            mp.write_text(json.dumps(m), encoding="utf-8")
            s_new = sha256(rp_new)
            runs = self._build(td, ev, s_old, s_new)
            self.assertEqual(runs["soak-old"]["accepted_status"], "pending_review",
                             runs["soak-old"])
            self.assertIsNone(runs["soak-old"]["superseded_by"])
            self.assertIn("coverage duration", runs["soak-old"]["review_note"])

    def test_one_sided_missing_actual_rejected(self):
        """Old run has measured coverage, replacement has none -> reject."""
        with tempfile.TemporaryDirectory(prefix="r8-idx-one-") as td:
            ev, s_old, s_new = self._pair(td, old_actual=7200,
                                          old_ended="2026-10-28T14:00:00+0000",
                                          new_actual=None)
            runs = self._build(td, ev, s_old, s_new)
            self.assertEqual(runs["soak-old"]["accepted_status"], "pending_review")

    def test_actual_window_conflict_rejected(self):
        """An actual value that grossly contradicts its own window is
        unverifiable in BOTH directions (7200s claim on a 60s window; and a
        60s claim on a 7200s window)."""
        with tempfile.TemporaryDirectory(prefix="r8-idx-conf-") as td:
            ev, s_old, s_new = self._pair(td, old_actual=7200,
                                          old_ended="2026-10-28T14:00:00+0000",
                                          new_actual=7200)
            # new run window stays 60s while claiming 7200s actual -> conflict
            runs = self._build(td, ev, s_old, s_new)
            self.assertEqual(runs["soak-old"]["accepted_status"], "pending_review")
        with tempfile.TemporaryDirectory(prefix="r8-idx-conf2-") as td:
            ev, s_old, s_new = self._pair(td, old_actual=7200,
                                          old_ended="2026-10-28T14:00:00+0000",
                                          new_actual=60,
                                          new_ended="2026-10-28T14:00:00+0000")
            # new claims 60s actual inside a 7200s window -> conflict
            runs = self._build(td, ev, s_old, s_new)
            self.assertEqual(runs["soak-old"]["accepted_status"], "pending_review")

    def test_nonfinite_negative_zero_actual_rejected(self):
        for bad in (float("inf"), float("nan"), -5, 0):
            with self.subTest(bad=bad):
                with tempfile.TemporaryDirectory(prefix="r8-idx-bad-") as td:
                    ev, s_old, s_new = self._pair(td, old_actual=7200,
                                                  old_ended="2026-10-28T14:00:00+0000",
                                                  new_actual=7200,
                                                  new_ended="2026-10-28T14:00:00+0000")
                    rp_new = ev / "soak-new.result.json"
                    d = json.loads(rp_new.read_text(encoding="utf-8"))
                    d["actual_duration_seconds"] = bad
                    rp_new.write_text(json.dumps(d), encoding="utf-8")
                    mp = rp_new.with_name("soak-new.manifest.json")
                    m = json.loads(mp.read_text(encoding="utf-8"))
                    m["result_sha256"] = sha256(rp_new)
                    mp.write_text(json.dumps(m), encoding="utf-8")
                    s_new = sha256(rp_new)
                    runs = self._build(td, ev, s_old, s_new)
                    self.assertEqual(runs["soak-old"]["accepted_status"], "pending_review")

    def test_60s_replacement_rejected_for_short_coverage(self):
        """A 60s measured run cannot replace a 7200s run (its own window is
        consistent, so the rejection comes from the coverage comparison)."""
        with tempfile.TemporaryDirectory(prefix="r8-idx-60-") as td:
            ev, s_old, s_new = self._pair(td, old_actual=7200,
                                          old_ended="2026-10-28T14:00:00+0000",
                                          new_actual=60)
            runs = self._build(td, ev, s_old, s_new)
            self.assertEqual(runs["soak-old"]["accepted_status"], "pending_review")
            self.assertIn("shorter than superseded", runs["soak-old"]["review_note"])

    def test_monotonic_span_only_counts_as_actual(self):
        """Collector contract: judge_input.monotonic_span_s is the measured
        monotonic proof and satisfies the actual-coverage requirement."""
        with tempfile.TemporaryDirectory(prefix="r8-idx-mono-") as td:
            ev = Path(td) / "ev"
            ev.mkdir()
            rp_old, _ = self.HELPER._write_run(ev, "soak-old", mode="idle", complete_meta=True, duration_seconds=60)
            rp_new, _ = self.HELPER._write_run(ev, "soak-new", mode="idle", complete_meta=True, duration_seconds=7200)
            d_old = json.loads(rp_old.read_text(encoding="utf-8"))
            d_old["ended"] = "2026-10-28T14:00:00+0000"
            d_old["judge_input"]["monotonic_span_s"] = 7200.0
            rp_old.write_text(json.dumps(d_old), encoding="utf-8")
            d_new = json.loads(rp_new.read_text(encoding="utf-8"))
            d_new["ended"] = "2026-10-28T14:00:00+0000"
            d_new["judge_input"]["monotonic_span_s"] = 7200.4
            rp_new.write_text(json.dumps(d_new), encoding="utf-8")
            for rp in (rp_old, rp_new):
                mp = rp.with_name(rp.name.replace(".result.json", ".manifest.json"))
                m = json.loads(mp.read_text(encoding="utf-8"))
                m["result_sha256"] = sha256(rp)
                m["ended"] = json.loads(rp.read_text(encoding="utf-8"))["ended"]
                mp.write_text(json.dumps(m), encoding="utf-8")
            s_old, s_new = sha256(rp_old), sha256(rp_new)
            runs = self._build(td, ev, s_old, s_new)
            self.assertEqual(runs["soak-old"]["accepted_status"], "superseded",
                             runs["soak-old"])

    def test_sufficient_actual_coverage_supersede_accepted(self):
        """Positive control: same baseline, both runs with measured actual
        coverage consistent with their windows -> supersede accepted."""
        with tempfile.TemporaryDirectory(prefix="r8-idx-ok-") as td:
            ev, s_old, s_new = self._pair(td, old_actual=7200,
                                          old_ended="2026-10-28T14:00:00+0000",
                                          new_actual=7200,
                                          new_ended="2026-10-28T14:00:00+0000")
            runs = self._build(td, ev, s_old, s_new)
            self.assertEqual(runs["soak-old"]["accepted_status"], "superseded",
                             runs["soak-old"])
            self.assertEqual(runs["soak-old"]["superseded_by"], "soak-new")


# ---------------------------------------------------------------------------
# R8-03: standalone runners adopt OutputPlan ownership; finalize consistency
# ---------------------------------------------------------------------------

class TestR803RunnerOutputOwnership(unittest.TestCase):
    def test_human_foreign_result_during_secrets_zero_device_calls(self):
        """A foreign result appearing while secrets are read aborts with
        ZERO device I/O; the foreign file's hash never changes."""
        with tempfile.TemporaryDirectory(prefix="r8-race-") as td:
            foreign_holder = {}

            def inject(td_inner, out_path, res_path):
                def fake_secrets():
                    res_path.write_text('{"foreign":true}', encoding="utf-8")
                    foreign_holder["before"] = hashlib.sha256(res_path.read_bytes()).hexdigest()
                    return {}, []
                fake_secrets.__name__ = "fake_secrets"
                return mock.patch.object(hor.run_g2, "load_secrets", side_effect=fake_secrets)

            # run_human_main already patches load_secrets via _NoRealIO; use a
            # dedicated drive that swaps in the injecting secrets loader.
            with tempfile.TemporaryDirectory(prefix="r8-race2-") as td2:
                out_path = Path(td2) / "human.jsonl"
                res_path = Path(td2) / "human.result.json"
                events = [{"meta": {"code": hor.mwcp.CODE["TELEMETRY"]}, "payload": r}
                          for r in production_records()]
                clock = [0.0]
                device_calls = {"n": 0}

                class FakeClient:
                    boot_id = "c" * 32
                    session_id = 1

                    def call(self, name, payload=None, **kw):
                        device_calls["n"] += 1
                        return {"ok": True, "result": {}}

                    def ping(self):
                        return {"ok": True, "result": {}}

                    def drain_events(self, duration_ms):
                        clock[0] += 10.0
                        batch = list(events)
                        events.clear()
                        return batch

                    def close(self):
                        pass

                def injecting_secrets():
                    res_path.write_text('{"foreign":true}', encoding="utf-8")
                    foreign_holder["before"] = hashlib.sha256(res_path.read_bytes()).hexdigest()
                    return {}, []

                argv = ["human_observe_runner", "--port", "COM9", "--seconds", "1",
                        "--out", str(out_path), "--confirm-user-actions",
                        "--min-exit-ms", "10000"]
                with fx._NoRealIO(), \
                     mock.patch.object(sys, "argv", argv), \
                     mock.patch.object(hor, "robust_connect", return_value=FakeClient()) as device, \
                     mock.patch.object(hor.run_g2, "load_secrets", side_effect=injecting_secrets), \
                     mock.patch.object(hor.time, "time", side_effect=lambda: clock[0]), \
                     mock.patch.object(hor.time, "sleep"), \
                     mock.patch.object(hor, "beep_phase"), \
                     mock.patch.object(hor, "beep_complete"), \
                     mock.patch.object(hor.winsound, "Beep", return_value=None), \
                     mock.patch("builtins.print"):
                    rc = hor.main()
                self.assertNotEqual(rc, 0)
                self.assertEqual(device_calls["n"], 0, "device must never be touched after a collision")
                self.assertEqual(hashlib.sha256(res_path.read_bytes()).hexdigest(),
                                 foreign_holder["before"], "foreign result bytes must be unchanged")
                self.assertFalse(out_path.exists(), "no partial raw evidence may remain")

    def test_human_manifest_collision_after_raw_close_downgrades_result(self):
        """The review's exact path: a foreign manifest injected after the raw
        close must NOT leave an acceptable pass result on disk."""
        rows = production_records(phases="default") if False else None
        recs = production_records()
        orig_close = mwcp.EvidenceWriter.close
        injected = []

        def collision_close(writer, *a, **kw):
            summary = orig_close(writer, *a, **kw)
            if not injected:
                writer.path.with_suffix(".manifest.json").write_text('{"foreign":true}',
                                                                     encoding="utf-8")
                injected.append(str(writer.path))
            return summary

        with mock.patch.object(mwcp.EvidenceWriter, "close", collision_close):
            rc, res, ctx = run_human_main(recs, phases=fx._default_valid_phases())
        self.addCleanup(_cleanup_ctx, ctx)
        self.assertNotEqual(rc, 0)
        self.assertIsNotNone(res)
        self.assertEqual(res["status"], "fail")
        self.assertEqual(res["verdict"], "STORAGE_FINALIZE_FAILED")
        self.assertTrue(res.get("not_valid_acceptance_evidence"))
        # the foreign manifest bytes are untouched
        self.assertEqual(Path(ctx["out_path"]).with_suffix(".manifest.json").read_text(encoding="utf-8"),
                         '{"foreign":true}')
        diags = list(Path(ctx["dir"]).glob("*.collision-*.diag.json"))
        self.assertTrue(diags, "an independent diagnostic must be left")

    def test_human_result_write_oserror_leaves_no_pass(self):
        """A plain storage I/O failure while writing the result downgrades
        the outcome (not just the FileExistsError path)."""
        recs = production_records()
        rc, res, ctx = run_human_main(recs, phases=fx._default_valid_phases(),
                                      fail_result_write=True)
        self.addCleanup(_cleanup_ctx, ctx)
        self.assertNotEqual(rc, 0)
        # the result write failed: no acceptable pass result may exist
        if ctx["res_path"].is_file():
            body = ctx["res_path"].read_text(encoding="utf-8")
            self.assertNotIn('"status": "pass"', body)
        diags = list(Path(ctx["dir"]).glob("*.collision-*.diag.json"))
        self.assertTrue(diags, "a storage-failure diagnostic must be left")

    def test_power_runner_foreign_result_before_io(self):
        with tempfile.TemporaryDirectory(prefix="r8-pwr-") as td:
            raw_out = Path(td) / "p.a.b.jsonl"
            res_collision = Path(td) / "p.a.b.result.json"
            res_collision.write_text('{"foreign": true}', encoding="utf-8")
            before = sha256(res_collision)
            with fx._NoRealIO(), \
                 mock.patch.object(sys, "argv", ["power_cut_runner", "--port", "FAKE",
                                                 "--out", str(raw_out)]), \
                 mock.patch.object(rg, "load_secrets", return_value=([], [])) as secrets, \
                 mock.patch.object(pcr, "robust_connect",
                                   side_effect=AssertionError("device I/O should not start")) as device, \
                 mock.patch("builtins.print"):
                rc = pcr.main()
            self.assertEqual(rc, 1)
            self.assertEqual(secrets.call_count, 0)
            self.assertEqual(device.call_count, 0)
            self.assertEqual(sha256(res_collision), before)
            self.assertFalse(raw_out.exists())

    def test_usb_runner_foreign_result_before_io(self):
        with tempfile.TemporaryDirectory(prefix="r8-usb-") as td:
            raw_out = Path(td) / "u.a.b.jsonl"
            res_collision = Path(td) / "u.a.b.result.json"
            res_collision.write_text('{"foreign": true}', encoding="utf-8")
            before = sha256(res_collision)
            with fx._NoRealIO(), \
                 mock.patch.object(sys, "argv", ["usb_unplug_runner", "--port", "FAKE",
                                                 "--out", str(raw_out)]), \
                 mock.patch.object(rg, "load_secrets", return_value=([], [])) as secrets, \
                 mock.patch.object(uur, "robust_connect",
                                   side_effect=AssertionError("device I/O should not start")) as device, \
                 mock.patch("builtins.print"):
                rc = uur.main()
            self.assertEqual(rc, 1)
            self.assertEqual(secrets.call_count, 0)
            self.assertEqual(device.call_count, 0)
            self.assertEqual(sha256(res_collision), before)

    def test_two_runners_contending_same_group(self):
        """A second runner pointed at the same output group must fail its
        reservation without modifying the first run's files."""
        recs = production_records()
        rc, res, ctx = run_human_main(recs, phases=fx._default_valid_phases())
        self.addCleanup(_cleanup_ctx, ctx)
        self.assertEqual(rc, 0)
        before = {p.name: sha256(p) for p in Path(ctx["dir"]).iterdir() if p.is_file()}
        # a second human run at the SAME out path must be refused
        rc2, _, _ = run_human_main(recs, phases=fx._default_valid_phases(),
                                   extra_inject=lambda tdir, o, r: None) if False else (None, None, None)
        with tempfile.TemporaryDirectory(prefix="r8-contend-") as td2:
            pass
        # drive the second run against the FIRST run's real output paths
        argv = ["human_observe_runner", "--port", "COM9", "--seconds", "1",
                "--out", str(ctx["out_path"]), "--confirm-user-actions",
                "--min-exit-ms", "10000"]
        with fx._NoRealIO(), \
             mock.patch.object(sys, "argv", argv), \
             mock.patch.object(rg, "load_secrets", return_value=([], [])) as secrets, \
             mock.patch.object(hor, "robust_connect",
                               side_effect=AssertionError("device I/O should not start")), \
             mock.patch("builtins.print"):
            rc3 = hor.main()
        self.assertEqual(rc3, 1)
        self.assertEqual(secrets.call_count, 0)
        after = {p.name: sha256(p) for p in Path(ctx["dir"]).iterdir() if p.is_file()}
        self.assertEqual(before, after, "first run's files must be untouched")

    def test_human_positive_full_flow_consistent(self):
        """Positive: reserve -> collect -> close -> result+manifest succeed;
        hashes/status/exit code agree; no reservation tokens remain."""
        recs = production_records()
        rc, res, ctx = run_human_main(recs, phases=fx._default_valid_phases())
        self.addCleanup(_cleanup_ctx, ctx)
        self.assertEqual(rc, 0, res)
        self.assertEqual(res["status"], "pass")
        self.assertEqual(res["verdict"], "HUMAN_OBSERVE_PASS")
        out, res_p = ctx["out_path"], ctx["res_path"]
        man = out.with_suffix(".manifest.json")
        self.assertTrue(out.is_file() and res_p.is_file() and man.is_file())
        m = json.loads(man.read_text(encoding="utf-8"))
        self.assertEqual(m["result_sha256"], sha256(res_p))
        self.assertEqual(m["raw_sha256"], res["evidence"]["sha256"])
        self.assertEqual(m["status"], "pass")
        # no *.tmp reservation leftovers
        self.assertFalse(list(Path(ctx["dir"]).glob("*.tmp")))


# ---------------------------------------------------------------------------
# R8-01A: per-field sampling semantics
# ---------------------------------------------------------------------------

class TestR801APerFieldSampling(unittest.TestCase):
    def test_frozen_presence_sample_rejected_by_judge(self):
        """presence.sample_ms frozen across the departure tail while
        sent_ms/source_seq advance is NOT a sequence of new presence
        observations (the review's exact human_frozen_presence_sample)."""
        rows = production_records()
        for row in rows[-5:]:
            row["presence"]["sample_ms"] = 5000.0
        verdict, ok, detail = hj.judge_human_observation({
            "telemetry_records": rows,
            "user_action_confirmed": True,
            "minimum_exit_duration_ms": 10000,
            "phases": fx._default_valid_phases(),
            "expected_installation": dict(BASE_CAL),
            "require_structured_phases": True,
        })
        self.assertFalse(ok)
        self.assertEqual(verdict, "STALE_PRESENCE_TIMESTAMP_REJECTED")

    def test_missing_presence_sample_rejected_by_judge(self):
        rows = production_records(presence_sample_ms=None)
        verdict, ok, _ = hj.judge_human_observation({
            "telemetry_records": rows,
            "user_action_confirmed": True,
            "minimum_exit_duration_ms": 10000,
            "phases": fx._default_valid_phases(),
            "expected_installation": dict(BASE_CAL),
            "require_structured_phases": True,
        })
        self.assertFalse(ok)
        self.assertEqual(verdict, "MISSING_PRESENCE_TIMESTAMP_REJECTED")

    def test_duplicate_frames_do_not_extend_exit_span(self):
        """Legal duplicate frames are kept, but the exit span is measured on
        DISTINCT presence samples: 5 exit frames with only 3 distinct
        presence samples spanning 4s must NOT pass a 10s requirement even
        though sent_ms spans 12s."""
        rows = production_records()
        # tail sent_ms = 5000..17000; each presence sample stays <= its own
        # frame's sent_ms. Only 3 DISTINCT presence samples spanning 9.1s:
        # sent_ms spans 12s but must not mask the shortfall.
        tail_samples = [4900.0, 8000.0, 8000.0, 14000.0, 14000.0]
        for i, v in enumerate(tail_samples):
            rows[-5 + i]["presence"]["sample_ms"] = v
        verdict, ok, _ = hj.judge_human_observation({
            "telemetry_records": rows,
            "user_action_confirmed": True,
            "minimum_exit_duration_ms": 10000,
            "phases": fx._default_valid_phases(),
            "expected_installation": dict(BASE_CAL),
            "require_structured_phases": True,
        })
        self.assertFalse(ok)
        self.assertEqual(verdict, "SUSTAINED_EXIT_DURATION_INSUFFICIENT")

    def test_duplicate_frames_kept_and_valid_positive(self):
        """A run whose exit tail contains duplicates but still has >= 3
        distinct presence samples spanning >= 10s passes (duplicates are
        retained, never punished)."""
        rows = production_records()
        # duplicates retained, still 4 distinct presence samples spanning
        # 12.1s >= 10s (each sample <= its own frame's sent_ms).
        tail_samples = [4900.0, 8000.0, 8000.0, 14000.0, 17000.0]
        for i, v in enumerate(tail_samples):
            rows[-5 + i]["presence"]["sample_ms"] = v
        verdict, ok, detail = hj.judge_human_observation({
            "telemetry_records": rows,
            "user_action_confirmed": True,
            "minimum_exit_duration_ms": 10000,
            "phases": fx._default_valid_phases(),
            "expected_installation": dict(BASE_CAL),
            "require_structured_phases": True,
        })
        self.assertTrue(ok, f"{verdict}: {detail}")

    def test_event_hold_contract_passes_on_transition_plus_terminal(self):
        """With the production event-hold presence capability declared
        (expected_interval_ms=null AND stale_after_ms=null), a held absence
        sample with a terminal frame IS a valid sustained exit."""
        rows = production_records()
        # presence sampled the transition once, then held: exit tail keeps a
        # single absence transition sample at 5000 while frames advance.
        for i in range(5):
            rows[-5 + i]["presence"]["sample_ms"] = 5000.0
        verdict, ok, detail = hj.judge_human_observation({
            "telemetry_records": rows,
            "user_action_confirmed": True,
            "minimum_exit_duration_ms": 10000,
            "phases": fx._default_valid_phases(),
            "expected_installation": dict(BASE_CAL),
            "require_structured_phases": True,
            "capabilities": EVENT_HOLD_CAPS,
        })
        self.assertTrue(ok, f"{verdict}: {detail}")
        self.assertEqual(detail["phase_verdicts"]["time_and_integrity"]["presence_sampling"],
                         "event_hold")

    def test_event_hold_requires_explicit_contract(self):
        """The SAME held samples under a periodic (default) contract are
        rejected - the hold semantics never apply by default."""
        rows = production_records()
        for i in range(5):
            rows[-5 + i]["presence"]["sample_ms"] = 5000.0
        verdict, ok, _ = hj.judge_human_observation({
            "telemetry_records": rows,
            "user_action_confirmed": True,
            "minimum_exit_duration_ms": 10000,
            "phases": fx._default_valid_phases(),
            "expected_installation": dict(BASE_CAL),
            "require_structured_phases": True,
            "capabilities": PERIODIC_CAPS,
        })
        self.assertFalse(ok)
        self.assertEqual(verdict, "STALE_PRESENCE_TIMESTAMP_REJECTED")

    def test_runner_level_frozen_presence_sample_rejected(self):
        """Real human.main with production field shapes: frozen
        presence.sample_ms must not reach HUMAN_OBSERVE_PASS."""
        rows = production_records()
        for row in rows[-5:]:
            row["presence"]["sample_ms"] = 5000.0
        rc, res, ctx = run_human_main(rows, phases=fx._default_valid_phases())
        self.addCleanup(_cleanup_ctx, ctx)
        self.assertNotEqual(rc, 0)
        self.assertIsNotNone(res)
        self.assertEqual(res["verdict"], "STALE_PRESENCE_TIMESTAMP_REJECTED")

    def test_runner_level_production_shape_positive(self):
        """Real human.main, normal 2D multi-phase production-shape run
        passes end to end (judge + finalize)."""
        rows = production_records()
        rc, res, ctx = run_human_main(rows, phases=fx._default_valid_phases())
        self.addCleanup(_cleanup_ctx, ctx)
        self.assertEqual(rc, 0, res)
        self.assertEqual(res["verdict"], "HUMAN_OBSERVE_PASS")


# ---------------------------------------------------------------------------
# R8-01B: 2D coordinates verified with the real diagnostic local_z input
# ---------------------------------------------------------------------------

class TestR801BDiagnosticLocalZTransform(unittest.TestCase):
    def test_pitch30_independent_closed_form_passes(self):
        """yaw=roll=0, pitch=30: room_y = 10*cos30 + 100*sin30 ~= 58.7 with
        the co-sampled diagnostics.local_z=100 (the review's exact case)."""
        cal = dict(BASE_CAL, install_pitch_deg=None)  # placeholder guard
        cal = dict(BASE_CAL)
        cal["install.pitch_deg"] = 30.0
        rows = production_records(cal=cal, diag_z=100.0)
        # independent spot check of the review's closed form
        self.assertAlmostEqual(independent_room([0.0, 10.0, 100.0], cal)[1],
                               10.0 * math.cos(math.pi / 6) + 100.0 * math.sin(math.pi / 6),
                               places=6)
        verdict, ok, detail = hj.judge_human_observation({
            "telemetry_records": rows,
            "user_action_confirmed": True,
            "minimum_exit_duration_ms": 10000,
            "phases": fx._default_valid_phases(),
            "expected_installation": dict(cal),
            "require_structured_phases": True,
        })
        self.assertTrue(ok, f"{verdict}: {detail}")
        self.assertEqual(detail["phase_verdicts"]["coordinate_consistency"]["local_z_source_counts"]
                         ["diagnostics.local_z"], 25)

    def test_roll_and_combined_angles_pass(self):
        """Non-zero roll and a combined yaw+pitch+roll case pass against the
        independently computed expected room coordinates.  install.x_cm is
        shifted so the rotated entry trajectory still crosses the polygon
        edge (inside + outside classified from the TRANSFORMED room
        coordinates)."""
        for yaw, pitch, roll in ((0.0, 0.0, 15.0), (0.0, 30.0, 0.0), (20.0, 30.0, -10.0)):
            with self.subTest(yaw=yaw, pitch=pitch, roll=roll):
                cal = dict(BASE_CAL)
                cal["install.x_cm"] = -30.0
                cal["install.yaw_deg"] = yaw
                cal["install.pitch_deg"] = pitch
                cal["install.roll_deg"] = roll
                rows = production_records(cal=cal, diag_z=100.0, entry_stride=24.0)
                verdict, ok, detail = hj.judge_human_observation({
                    "telemetry_records": rows,
                    "user_action_confirmed": True,
                    "minimum_exit_duration_ms": 10000,
                    "phases": fx._default_valid_phases(),
                    "expected_installation": dict(cal),
                    "require_structured_phases": True,
                })
                self.assertTrue(ok, f"{verdict}: {detail}")

    def test_missing_diagnostic_z_is_insufficient_not_wrong_transform(self):
        """2D targets under pitch with NO diagnostics.local_z must be
        reported as INSUFFICIENT evidence (never a guessed lz=0 leading to a
        false COORDINATE_TRANSFORM_MISMATCH)."""
        cal = dict(BASE_CAL, install_pitch_deg=30.0)
        cal = dict(BASE_CAL)
        cal["install.pitch_deg"] = 30.0
        rows = production_records(cal=cal, diag_z=None)
        verdict, ok, _ = hj.judge_human_observation({
            "telemetry_records": rows,
            "user_action_confirmed": True,
            "minimum_exit_duration_ms": 10000,
            "phases": fx._default_valid_phases(),
            "expected_installation": dict(cal),
            "require_structured_phases": True,
        })
        self.assertFalse(ok)
        self.assertEqual(verdict, "INSUFFICIENT_Z_DIAGNOSTIC_FOR_TILT_REJECTED")

    def test_stale_or_mismatched_diagnostic_z_is_insufficient(self):
        """A diagnostics.local_z NOT sampled at the target's position_ms is
        not usable (stale / mismatched sampling)."""
        cal = dict(BASE_CAL)
        cal["install.pitch_deg"] = 30.0
        rows = production_records(cal=cal, diag_z=100.0)
        for row in rows:
            if row.get("targets"):
                row["metrics"]["diagnostics.local_z"]["sample_ms"] = 999999.0
        verdict, ok, _ = hj.judge_human_observation({
            "telemetry_records": rows,
            "user_action_confirmed": True,
            "minimum_exit_duration_ms": 10000,
            "phases": fx._default_valid_phases(),
            "expected_installation": dict(cal),
            "require_structured_phases": True,
        })
        self.assertFalse(ok)
        self.assertEqual(verdict, "INSUFFICIENT_Z_DIAGNOSTIC_FOR_TILT_REJECTED")

    def test_wrong_room_coordinates_still_rejected(self):
        """With valid diagnostics, actually-wrong room coordinates are still
        a transform mismatch (the fix must not swallow real errors)."""
        cal = dict(BASE_CAL)
        cal["install.pitch_deg"] = 30.0
        rows = production_records(cal=cal, diag_z=100.0)
        for row in rows:
            if row.get("targets"):
                row["targets"][0]["room_cm"][1] = round(
                    row["targets"][0]["room_cm"][1] + 40.0, 1)
        verdict, ok, _ = hj.judge_human_observation({
            "telemetry_records": rows,
            "user_action_confirmed": True,
            "minimum_exit_duration_ms": 10000,
            "phases": fx._default_valid_phases(),
            "expected_installation": dict(cal),
            "require_structured_phases": True,
        })
        self.assertFalse(ok)
        self.assertEqual(verdict, "COORDINATE_TRANSFORM_MISMATCH_REJECTED")

    def test_zero_tilt_2d_regression_no_index_error(self):
        """Zero-tilt 2D remains a pass (R7 regression: no IndexError)."""
        rows = production_records()
        verdict, ok, detail = hj.judge_human_observation({
            "telemetry_records": rows,
            "user_action_confirmed": True,
            "minimum_exit_duration_ms": 10000,
            "phases": fx._default_valid_phases(),
            "expected_installation": dict(BASE_CAL),
            "require_structured_phases": True,
        })
        self.assertTrue(ok, f"{verdict}: {detail}")


# ---------------------------------------------------------------------------
# R8-02: the real collector emits verifiable actual coverage
# ---------------------------------------------------------------------------

class TestR802CollectorEmitsActualCoverage(unittest.TestCase):
    def test_real_cmd_soak_emits_actual_coverage_and_manifest_binding(self):
        """The collector synchronously writes measured actual coverage (with
        its measurement source) into the result AND the per-run manifest, so
        index admission can bind to real coverage instead of --seconds."""
        import shutil
        import soak_collector_integration_test as sit
        with tempfile.TemporaryDirectory(prefix="r8-soak-") as td:
            # relocate the collector's output root into this unique temp dir
            fake_file = Path(td) / "a" / "b" / "soak_collector_integration_test.py"
            fake_file.parent.mkdir(parents=True, exist_ok=True)
            fake_file.write_text("", encoding="utf-8")
            script = []
            for i in range(6):
                script.append(("resp", {"ok": True, "result": {
                    "uptime_ms": 10000 * i, "radar_link": "healthy",
                    "counters": {"rx_frames": i, "logs_dropped": 0}}}))
            script.append(("resp", {"ok": True, "result": {"state": "disconnected",
                                                           "ssid": "", "ip": None,
                                                           "rssi_dbm": None}}))
            orig_file = sit.__file__
            sit.__file__ = str(fake_file)
            try:
                outcome, holder = sit.run_soak(script, seconds=60, mode="idle")
            finally:
                sit.__file__ = orig_file
            actual = outcome.get("actual_duration_seconds")
            self.assertIsInstance(actual, (int, float))
            self.assertTrue(50.0 <= float(actual) <= 90.0, f"actual={actual}")
            self.assertIn("monotonic", outcome.get("actual_duration_source", ""))
            # judge_input carries the same measured value
            self.assertEqual(outcome["judge_input"]["actual_duration_seconds"], actual)
            # the per-run manifest binds the measured coverage + window
            manifest_path = Path(holder["path"]).with_suffix(".manifest.json")
            self.assertTrue(manifest_path.is_file())
            m = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(m.get("actual_duration_seconds"), actual)
            self.assertTrue(m.get("started") and m.get("ended"))
            self.assertIn("monotonic", m.get("actual_duration_source", ""))
            shutil.rmtree(Path(td) / "a", ignore_errors=True)


if __name__ == "__main__":
    unittest.main(verbosity=1)
