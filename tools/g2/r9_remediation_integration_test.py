#!/usr/bin/env python3
"""R9 remediation closure tests (review 2026-10-31-r9, R9-01..R9-03).

All offline: devices/secrets/network are faked and every test asserts no
real I/O.  Original reviewer probes: tmp/g2-review-20261031-r9/review.py
(each scenario cites its probe).

R9-01  Interactive human confirmations carry the SAME attempt binding as
       the hook path (three real input() yes passes end-to-end); imported
       phase files must be bound to THIS attempt (wrapper + per-phase merge
       with conflict rejection); stripping/altering method cannot bypass;
       unbound imports are insufficient, never a pass.
R9-02  ALL declared actual-coverage copies (top-level and judge_input,
       actual/observed/monotonic) must be valid and mutually consistent -
       a contradictory copy rejects the replacement with a coverage reason;
       the manifest's declared coverage must agree with the result's.
R9-03  Entries that bypass run_g2.connect (reconnect50, p0repro) run the
       full OutputPlan lifecycle (zero device constructors on collision,
       foreign bytes untouched, own reservations cleaned, normal path
       works); a close/flush OSError after a complete result write leaves
       NO acceptable pass on disk (downgraded + diagnostic), and normal
       runs publish consistent raw/result/manifest.
"""

import hashlib
import io
import json
import os
import sys
import tempfile
import unittest
import contextlib
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))

import build_evidence_index as bi  # noqa: E402
import human_observe_runner as hor  # noqa: E402
import mwcp  # noqa: E402
import run_g2 as rg  # noqa: E402
import serial  # noqa: E402
import r5_audit_probe_integration_test as fx  # noqa: E402
import r8_remediation_integration_test as r8  # noqa: E402

sha256 = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()  # noqa: E731


# ---------------------------------------------------------------------------
# R9-01: interactive + imported confirmation binding
# ---------------------------------------------------------------------------

def live_run(interactive=True, hook=False, phase_file_bindings=None,
             strip_method=False, records=None, phase_overrides=None,
             wrapper_attempt=None, wrapper_bindings=True):
    """Drive the REAL human main with live confirmations (no
    PHASE_CONFIRMER when interactive), replicating the reviewer's
    live_hook_control / live_interactive probes.  phase_overrides lets a
    test plant WRONG binding values; wrapper_attempt overrides the file's
    top-level attempt_id to create a wrapper/per-phase conflict;
    wrapper_bindings=False writes a COMPLETELY unbound file (the reviewer's
    unbound_imported_phases scenario)."""
    td = tempfile.mkdtemp(prefix="r9-live-")
    outdir = Path(td)
    path = outdir / "human.jsonl"
    rows = records if records is not None else r8.production_records()
    clock = [1000.0]
    batches = [rows[:12], rows[12:25], rows[25:]]
    closed = []

    class Client:
        boot_id = "d" * 32
        session_id = 7

        def call(self, name, *args, **kwargs):
            if name == "DEVICE_INFO":
                return {"ok": True, "result": {"device_id": "r60-review", "model": "R60ABD1"}}
            if name == "CAPABILITIES_LIST":
                return {"ok": True, "result": r8.PERIODIC_CAPS}
            return {"ok": True, "result": {}}

        def ping(self):
            return {"ok": True, "result": {}}

        def close(self):
            closed.append(True)

        def drain_events(self, duration_ms):
            clock[0] += 20.0
            return [{"meta": {"code": mwcp.CODE["TELEMETRY"]}, "payload": r}
                    for r in (batches.pop(0) if batches else [])]

    argv = ["human", "--port", "FAKE", "--seconds", "60", "--out", str(path)]
    if interactive:
        argv += ["--interactive-confirm"]
    if phase_file_bindings is not None:
        attempt = wrapper_attempt or r8.FIXED_ATTEMPT_ID
        doc = {"phases": phase_file_bindings}
        if wrapper_bindings:
            doc.update({"attempt_id": attempt, "session_id": 7,
                        "boot_id": "d" * 32, "device_id": "r60-review"})
        if phase_overrides:
            for ph in doc["phases"].values():
                ph.update(phase_overrides)
        if strip_method:
            for ph in doc["phases"].values():
                ph.pop("method", None)
        pfile = outdir / "phases.json"
        pfile.write_text(json.dumps(doc), encoding="utf-8")
        argv += ["--phase-confirm-file", str(pfile)]
        interactive = False  # file import path
    with fx._NoRealIO() as guard, \
         mock.patch.object(sys, "argv", argv), \
         mock.patch.object(hor, "robust_connect", return_value=Client()), \
         mock.patch.object(rg, "read_all_config", return_value=(dict(r8.BASE_CAL), "1")), \
         mock.patch.object(hor, "PHASE_CONFIRMER", (lambda *args: True) if hook else None), \
         mock.patch("builtins.input", return_value="yes") as user_input, \
         mock.patch("builtins.print"), \
         mock.patch.object(hor, "beep_phase"), \
         mock.patch.object(hor, "beep_complete"), \
         mock.patch.object(hor.winsound, "Beep"), \
         mock.patch.object(hor.time, "sleep"), \
         mock.patch.object(hor.time, "time", side_effect=lambda: clock[0]), \
         mock.patch.object(hor.time, "monotonic", side_effect=lambda: clock[0]), \
         mock.patch.object(hor.uuid, "uuid4", return_value=r8._FixedUUID()):
        rc = hor.main()
    res = json.loads(path.with_suffix(".result.json").read_text(encoding="utf-8"))
    return {"rc": rc, "result": res, "input_calls": user_input.call_count,
            "client_closed": bool(closed), "dir": outdir}


class TestR901ConfirmationBinding(unittest.TestCase):
    def test_live_hook_control_passes(self):
        """Reviewer probe live_hook_control: hook True -> exit 0 PASS."""
        out = live_run(hook=True, interactive=False)
        self.assertEqual(out["rc"], 0, out["result"].get("verdict"))
        self.assertEqual(out["result"]["status"], "pass")
        self.assertEqual(out["result"]["verdict"], "HUMAN_OBSERVE_PASS")
        self.assertTrue(out["client_closed"])

    def test_live_interactive_three_yes_passes_with_bindings(self):
        """Reviewer probe live_interactive REPAIRED: --interactive-confirm
        with three real input() yes -> exit 0 PASS, and every phase carries
        the full attempt binding (attempt/session/boot/device)."""
        out = live_run(interactive=True)
        self.assertEqual(out["rc"], 0, out["result"].get("verdict"))
        self.assertEqual(out["result"]["verdict"], "HUMAN_OBSERVE_PASS")
        self.assertEqual(out["input_calls"], 3)
        self.assertTrue(out["client_closed"])
        phases = out["result"]["phases"]
        for name in ("entry", "still", "exit"):
            ph = phases[name]
            for field in ("attempt_id", "session_id", "boot_id", "device_id"):
                self.assertIn(field, ph, f"{name} missing {field}")
            self.assertEqual(ph["attempt_id"], out["result"]["attempt_id"])
            self.assertEqual(ph["session_id"], 7)
            self.assertEqual(ph["boot_id"], "d" * 32)
            self.assertEqual(ph["device_id"], "r60-review")

    def test_unbound_imported_phases_rejected(self):
        """Reviewer probe unbound_imported_phases REPAIRED: a phase file
        without ANY binding fields (wrapper or per-phase) is insufficient
        evidence for this run - it must not pass."""
        phases = fx._default_valid_phases()
        for ph in phases.values():
            for k in ("attempt_id", "session_id", "boot_id", "device_id"):
                ph.pop(k, None)
        out = live_run(interactive=False, phase_file_bindings=phases,
                       wrapper_bindings=False)
        self.assertNotEqual(out["rc"], 0, out["result"])
        self.assertNotEqual(out["result"]["verdict"], "HUMAN_OBSERVE_PASS")
        self.assertIsNotNone(out["result"].get("phase_import_rejected"),
                              "the import rejection reason must be recorded")

    def test_method_alteration_cannot_bypass(self):
        """A file claiming method=hook WITHOUT bindings is still rejected:
        method never bypasses the binding contract."""
        phases = fx._default_valid_phases()
        for ph in phases.values():
            ph["method"] = "hook"  # false live claim, zero bindings
        out = live_run(interactive=False, phase_file_bindings=phases,
                       wrapper_bindings=False)
        self.assertNotEqual(out["rc"], 0)
        self.assertNotEqual(out["result"]["verdict"], "HUMAN_OBSERVE_PASS")

    def test_bound_import_passes_and_survives_method_strip(self):
        """The legal import path: fully bound file passes; stripping the
        method does not change the verdict (bindings decide)."""
        phases = fx._default_valid_phases()
        out = live_run(interactive=False, phase_file_bindings=phases,
                       strip_method=True)
        self.assertEqual(out["rc"], 0, out["result"].get("verdict"))
        self.assertEqual(out["result"]["verdict"], "HUMAN_OBSERVE_PASS")
        for ph in out["result"]["phases"].values():
            self.assertEqual(ph["method"], "imported_file")
            self.assertEqual(ph["attempt_id"], out["result"]["attempt_id"])

    def test_wrong_attempt_binding_rejected(self):
        phases = fx._default_valid_phases()
        out = live_run(interactive=False, phase_file_bindings=phases,
                       phase_overrides={"attempt_id": "human-deadbeefdeadbeef"})
        self.assertNotEqual(out["rc"], 0)
        self.assertNotEqual(out["result"]["verdict"], "HUMAN_OBSERVE_PASS")

    def test_wrong_device_and_boot_and_session_rejected(self):
        for field, value in (("device_id", "other-device"),
                             ("boot_id", "e" * 32),
                             ("session_id", 9999)):
            with self.subTest(field=field):
                phases = fx._default_valid_phases()
                out = live_run(interactive=False, phase_file_bindings=phases,
                               phase_overrides={field: value})
                self.assertNotEqual(out["rc"], 0)
                self.assertNotEqual(out["result"]["verdict"], "HUMAN_OBSERVE_PASS")

    def test_per_phase_wrapper_conflict_rejected(self):
        """A per-phase binding that contradicts the wrapper rejects the whole
        import (no silent merge)."""
        phases = fx._default_valid_phases()
        phases["exit"]["attempt_id"] = "human-0000000000000000"
        out = live_run(interactive=False, phase_file_bindings=phases,
                       wrapper_attempt="human-0123456789abcdef")
        self.assertNotEqual(out["rc"], 0)
        self.assertNotEqual(out["result"]["verdict"], "HUMAN_OBSERVE_PASS")


# ---------------------------------------------------------------------------
# R9-02: contradictory actual-coverage copies reject replacement
# ---------------------------------------------------------------------------

class TestR902CoverageDeclarationConsistency(unittest.TestCase):
    HELPER = r8.TestR802ActualCoverageAdmission()

    def _pair_and_build(self, td, mutate_new):
        ev, s_old, s_new = self.HELPER._pair(
            td, old_actual=7200, old_ended="2026-10-28T14:00:00+0000",
            new_actual=7200, new_ended="2026-10-28T14:00:00+0000")
        rp = ev / "soak-new.result.json"
        d = json.loads(rp.read_text(encoding="utf-8"))
        mutate_new(d)
        rp.write_text(json.dumps(d), encoding="utf-8")
        mp = ev / "soak-new.manifest.json"
        m = json.loads(mp.read_text(encoding="utf-8"))
        m["result_sha256"] = sha256(rp)
        mp.write_text(json.dumps(m), encoding="utf-8")
        s_new = sha256(rp)
        idx = bi.build_index({"test": ev}, Path(td) / "index.json", {
            "soak-old": {"accepted_status": "superseded",
                         "superseded_by": "soak-new",
                         "result_sha256": s_old},
            "soak-new": {"accepted_status": "pass",
                         "result_sha256": s_new},
        }, bi.FIRMWARE_BATCHES, sources_snapshot={})
        return {r["run_id"]: r for r in idx["runs"]}

    def test_contradictory_actual_copies_rejected(self):
        """Reviewer probe index_contradictory_actual: top-level 7200 vs
        judge_input 60 -> replacement rejected with a coverage reason."""
        with tempfile.TemporaryDirectory(prefix="r9-idx-ca-") as td:
            def mutate(d):
                d["judge_input"]["actual_duration_seconds"] = 60
            runs = self._pair_and_build(td, mutate)
            self.assertEqual(runs["soak-old"]["accepted_status"], "pending_review")
            self.assertIsNone(runs["soak-old"]["superseded_by"])
            self.assertIn("conflict", runs["soak-old"]["review_note"])

    def test_contradictory_monotonic_copies_rejected(self):
        """Reviewer probe index_contradictory_monotonic: top-level 7200 vs
        judge_input 60 -> rejected."""
        with tempfile.TemporaryDirectory(prefix="r9-idx-cm-") as td:
            def mutate(d):
                d["monotonic_span_s"] = 7200
                d["judge_input"]["monotonic_span_s"] = 60
            runs = self._pair_and_build(td, mutate)
            self.assertEqual(runs["soak-old"]["accepted_status"], "pending_review")
            self.assertIn("conflict", runs["soak-old"]["review_note"])

    def test_swapped_precedence_still_rejected(self):
        """judge_input carries 7200 while top-level carries 60: the conflict
        is direction-independent (no level priority)."""
        with tempfile.TemporaryDirectory(prefix="r9-idx-sw-") as td:
            def mutate(d):
                d["actual_duration_seconds"] = 60
                d["judge_input"]["actual_duration_seconds"] = 7200
            runs = self._pair_and_build(td, mutate)
            self.assertEqual(runs["soak-old"]["accepted_status"], "pending_review")

    def test_invalid_second_copy_rejected(self):
        """A NaN/Inf/negative/bool copy in the SECOND position must not be
        masked by a valid first copy."""
        for bad in (float("nan"), float("inf"), -1, True, "7200"):
            with self.subTest(bad=bad):
                with tempfile.TemporaryDirectory(prefix="r9-idx-bad-") as td:
                    def mutate(d):
                        d["judge_input"]["actual_duration_seconds"] = bad
                    runs = self._pair_and_build(td, mutate)
                    self.assertEqual(runs["soak-old"]["accepted_status"],
                                     "pending_review", bad)

    def test_manifest_result_measurement_conflict_rejected(self):
        """A sidecar claiming a measured coverage that contradicts the
        result's own declarations invalidates the sidecar (identity unknown
        -> no supersede)."""
        with tempfile.TemporaryDirectory(prefix="r9-idx-man-") as td:
            ev, s_old, s_new = self.HELPER._pair(
                td, old_actual=7200, old_ended="2026-10-28T14:00:00+0000",
                new_actual=7200, new_ended="2026-10-28T14:00:00+0000")
            mp = ev / "soak-new.manifest.json"
            m = json.loads(mp.read_text(encoding="utf-8"))
            m["actual_duration_seconds"] = 60  # contradicts the result's 7200
            mp.write_text(json.dumps(m), encoding="utf-8")
            idx = bi.build_index({"test": ev}, Path(td) / "index.json", {
                "soak-old": {"accepted_status": "superseded",
                             "superseded_by": "soak-new",
                             "result_sha256": s_old},
                "soak-new": {"accepted_status": "pass",
                             "result_sha256": s_new},
            }, bi.FIRMWARE_BATCHES, sources_snapshot={})
            runs = {r["run_id"]: r for r in idx["runs"]}
            self.assertEqual(runs["soak-old"]["accepted_status"], "pending_review")

    def test_consistent_copies_still_supersede(self):
        """Positive control: all declared copies agree (7200 everywhere, both
        levels) with a matching window -> replacement accepted."""
        with tempfile.TemporaryDirectory(prefix="r9-idx-ok-") as td:
            def mutate(d):
                d["monotonic_span_s"] = 7200
                d["judge_input"]["monotonic_span_s"] = 7200
            runs = self._pair_and_build(td, mutate)
            self.assertEqual(runs["soak-old"]["accepted_status"], "superseded",
                             runs["soak-old"])


# ---------------------------------------------------------------------------
# R9-03A: bypass-connect entries adopt the OutputPlan lifecycle
# ---------------------------------------------------------------------------

class _SeqFakeClient:
    boot_id = "d" * 32
    session_id = 7

    def __init__(self, *args, **kwargs):
        _SeqFakeClient.constructed += 1

    def hello(self, timeout_ms=8000):
        return {"boot_id": self.boot_id}

    def ping(self):
        return {"uptime_ms": 1234}

    def close(self):
        pass


_SeqFakeClient.constructed = 0


def run_bypass_command(command, td, inject_result=False, inject_manifest=False):
    """Run the real rg.main for reconnect50 / p0repro with a fake device and
    fake secrets that inject a foreign file mid-race (reviewer probes
    bypass_reconnect / bypass_p0repro).  The injection OVERWRITES whatever
    is at the target path - exactly what a racing foreign writer would do to
    our freshly created reservation token."""
    raw = Path(td) / "capture.part.jsonl"
    foreign_res = raw.with_suffix(".result.json")
    foreign_man = raw.with_suffix(".manifest.json")
    _SeqFakeClient.constructed = 0
    serial_calls = []

    def secrets():
        if inject_result:
            foreign_res.write_text('{"foreign":true}', encoding="utf-8")
        if inject_manifest:
            foreign_man.write_text('{"foreign":true}', encoding="utf-8")
        return {}, []

    class DeviceBoundary(BaseException):
        pass

    def boundary(*args, **kwargs):
        _SeqFakeClient.constructed += 1
        raise DeviceBoundary("fake device boundary reached")

    def fake_serial(*args, **kwargs):
        serial_calls.append(1)
        raise DeviceBoundary("fake serial boundary reached")

    cli = "reconnect50" if command == "reconnect" else command
    argv = ["run_g2", cli, "--port", "FAKE", "--out", str(raw), "--repeat", "1"]
    with fx._NoRealIO() as guard, \
         mock.patch.object(sys, "argv", argv), \
         mock.patch.object(rg, "load_secrets", side_effect=secrets), \
         mock.patch.object(mwcp, "Client", _SeqFakeClient), \
         mock.patch.object(serial, "Serial", side_effect=fake_serial), \
         mock.patch.object(rg.time, "sleep"), \
         contextlib.redirect_stdout(io.StringIO()), \
         contextlib.redirect_stderr(io.StringIO()):
        rc = rg.main()
    return {
        "rc": rc,
        "device_calls": _SeqFakeClient.constructed,
        "serial_calls": len(serial_calls),
        "foreign_res_unchanged": (not foreign_res.exists())
                                 or foreign_res.read_text(encoding="utf-8") == '{"foreign":true}',
        "foreign_man_unchanged": (not foreign_man.exists())
                                 or foreign_man.read_text(encoding="utf-8") == '{"foreign":true}',
        "raw_exists": raw.exists(),
        "leftover_parts": list(Path(td).glob("*.part")),
    }


class TestR903BypassEntriesOutputPlan(unittest.TestCase):
    def test_reconnect_result_race_zero_device_calls(self):
        """Reviewer probe bypass_reconnect REPAIRED: a foreign result
        appearing during load_secrets stops the entry with ZERO device
        constructors and the foreign file untouched."""
        with tempfile.TemporaryDirectory(prefix="r9-bp-re-") as td:
            out = run_bypass_command("reconnect", td, inject_result=True)
            self.assertNotEqual(out["rc"], 0)
            self.assertEqual(out["device_calls"], 0, out)
            self.assertEqual(out["serial_calls"], 0)
            self.assertTrue(out["foreign_res_unchanged"])
            self.assertFalse(out["raw_exists"], "no partial raw may remain")
            self.assertEqual(out["leftover_parts"], [])

    def test_p0repro_result_race_zero_device_calls(self):
        """Reviewer probe bypass_p0repro REPAIRED: same contract for the
        destructive P0 entry (fake-only; never a real run)."""
        with tempfile.TemporaryDirectory(prefix="r9-bp-p0-") as td:
            out = run_bypass_command("p0repro", td, inject_result=True)
            self.assertNotEqual(out["rc"], 0)
            self.assertEqual(out["device_calls"], 0)
            self.assertEqual(out["serial_calls"], 0)
            self.assertTrue(out["foreign_res_unchanged"])
            self.assertFalse(out["raw_exists"])

    def test_reconnect_manifest_race_zero_device_calls(self):
        with tempfile.TemporaryDirectory(prefix="r9-bp-rm-") as td:
            out = run_bypass_command("reconnect", td, inject_manifest=True)
            self.assertNotEqual(out["rc"], 0)
            self.assertEqual(out["device_calls"], 0)
            self.assertTrue(out["foreign_man_unchanged"])

    def test_reconnect_normal_path_runs_real_collector(self):
        """The normal path must NOT be blocked by its own reservation: the
        real collection logic runs (one fake cycle), files finalize, and the
        result matches the exit code."""
        with tempfile.TemporaryDirectory(prefix="r9-bp-ok-") as td:
            raw = Path(td) / "capture.part.jsonl"
            argv = ["run_g2", "reconnect50", "--port", "FAKE",
                    "--out", str(raw), "--repeat", "1"]
            with fx._NoRealIO(), \
                 mock.patch.object(sys, "argv", argv), \
                 mock.patch.object(mwcp, "Client", _SeqFakeClient), \
                 mock.patch.object(rg.time, "sleep"), \
                 contextlib.redirect_stdout(io.StringIO()), \
                 contextlib.redirect_stderr(io.StringIO()):
                rc = rg.main()
            self.assertEqual(rc, 0)
            self.assertGreaterEqual(_SeqFakeClient.constructed, 1,
                                    "the real collection logic must have run")
            self.assertTrue(raw.is_file())
            res = json.loads(raw.with_suffix(".result.json").read_text(encoding="utf-8"))
            self.assertEqual(res["status"], "pass")

    def test_p0repro_fake_only_completes_and_finalizes(self):
        """p0repro stays a destructive tool: exercised ONLY through fakes; a
        full fake pass completes and finalizes the result deterministically
        (no real serial, ever)."""
        with tempfile.TemporaryDirectory(prefix="r9-bp-p0ok-") as td:
            raw = Path(td) / "p0.jsonl"

            class FakeSer:
                dtr = True
                rts = True

                def read(self, n):
                    return b""

                def write(self, data):
                    return len(data)

                def close(self):
                    pass

            argv = ["run_g2", "p0repro", "--port", "FAKE", "--out", str(raw)]
            clock = [1000.0]

            def fake_time():
                # advancing clock: p0repro's listen() loops on time.time(),
                # a constant stub would spin forever
                clock[0] += 2.0
                return clock[0]

            with fx._NoRealIO(), \
                 mock.patch.object(sys, "argv", argv), \
                 mock.patch.object(serial, "Serial", return_value=FakeSer()), \
                 mock.patch.object(rg.time, "sleep"), \
                 mock.patch.object(rg.time, "time", side_effect=fake_time), \
                 contextlib.redirect_stdout(io.StringIO()), \
                 contextlib.redirect_stderr(io.StringIO()):
                rc = rg.main()
            self.assertTrue(raw.is_file())
            res = json.loads(raw.with_suffix(".result.json").read_text(encoding="utf-8"))
            # fake serial answers nothing: F-phase check fails -> status fail
            self.assertEqual(res["status"], "fail")
            self.assertNotEqual(rc, 0)


# ---------------------------------------------------------------------------
# R9-03B: result close/flush failure after a COMPLETE write
# ---------------------------------------------------------------------------

_original_open = Path.open


class _FailingCloseFile:
    """Proxy that lets the real write/flush complete and raises OSError on
    close - the exact late-stage failure the reviewer injected."""

    def __init__(self, fh, failures):
        self._fh = fh
        self._failures = failures

    def write(self, *a, **kw):
        return self._fh.write(*a, **kw)

    def flush(self, *a, **kw):
        return self._fh.flush(*a, **kw)

    def fsync(self, *a, **kw):
        return os.fsync(self._fh.fileno())

    def fileno(self):
        return self._fh.fileno()

    def close(self):
        try:
            self._fh.close()
        finally:
            self._failures.append("simulated result close/flush failure")
            raise OSError(5, "simulated result close/flush failure")

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False


def run_human_with_result_close_failure():
    """Real human.main; ONLY the final result file's close fails once (the
    reviewer's result_close_failure probe, adapted to the R14 pinned-object
    lifecycle: the staging object is exclusive-created through
    OutputPlan._open_owned_part (Win32 CREATE_NEW on Windows, os.open on
    POSIX) and the stream wrapped via os.fdopen, so the failing handle is
    the result part's stream close - after the complete write, before
    publish)."""
    failures = []
    flagged = set()
    original_open_owned = rg.OutputPlan._open_owned_part
    original_fdopen = os.fdopen

    def fault_open_owned(plan, tmp):
        fd = original_open_owned(plan, tmp)
        if "human.result.json" in Path(str(tmp)).name and not failures:
            flagged.add(fd)
        return fd

    class _FailingCloseStream:
        """Delegates everything; the first close() REALLY closes the fd and
        then raises OSError - the exact late-stage failure the reviewer
        injected (fd closed first so the object-level cleanup can proceed)."""

        def __init__(self, f):
            self._f = f

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            self.close()
            return False

        def close(self):
            try:
                return self._f.close()
            finally:
                if not failures:
                    failures.append("simulated result close/flush failure")
                    raise OSError(5, "simulated result close/flush failure")

        def __getattr__(self, name):
            return getattr(self._f, name)

    def fault_fdopen(fd, *args, **kwargs):
        f = original_fdopen(fd, *args, **kwargs)
        if fd in flagged:
            flagged.discard(fd)
            return _FailingCloseStream(f)
        return f

    with mock.patch.object(rg.OutputPlan, "_open_owned_part", fault_open_owned), \
         mock.patch.object(os, "fdopen", fault_fdopen), \
         mock.patch.object(os, "fsync", lambda fd: None), \
         contextlib.redirect_stderr(io.StringIO()):
        rc, result, ctx = r8.run_human_main(r8.production_records(),
                                            phases=fx._default_valid_phases())
    return rc, result, ctx, failures


class TestR903ResultCloseFailure(unittest.TestCase):
    def test_result_close_failure_leaves_no_pass_on_disk(self):
        """Reviewer probe result_close_failure REPAIRED: one close OSError
        after a complete write -> exit non-zero, the on-disk result is NOT
        an acceptable pass (absent or explicitly downgraded), the manifest
        is failed, a diagnostic exists, and no *.part temp leaks."""
        rc, result, ctx, failures = run_human_with_result_close_failure()
        self.addCleanup(_cleanup, ctx)
        self.assertNotEqual(rc, 0)
        self.assertTrue(failures, "the fault injection must have fired")
        res_path = ctx["res_path"]
        if res_path.is_file():
            body = json.loads(res_path.read_text(encoding="utf-8"))
            # the on-disk result can NEVER be an acceptable pass
            self.assertNotEqual(body.get("verdict"), "HUMAN_OBSERVE_PASS",
                                json.dumps(body)[:200])
            self.assertNotEqual(body.get("status"), "pass")
        man = ctx["out_path"].with_suffix(".manifest.json")
        self.assertTrue(man.is_file())
        m = json.loads(man.read_text(encoding="utf-8"))
        self.assertEqual(m.get("status"), "fail")
        self.assertEqual(m.get("verdict"), "STORAGE_FINALIZE_FAILED")
        diags = list(Path(ctx["dir"]).glob("*.collision-*.diag.json"))
        self.assertTrue(diags, "an independent diagnostic must be left")
        self.assertEqual(list(Path(ctx["dir"]).glob("*.part")), [],
                         "no temp file may leak")

    def test_normal_finalize_consistent_no_temp_leak(self):
        """Positive control (already covered in r8, repeated here against the
        atomic publisher): raw/result/manifest hashes and status agree with
        the exit code and no temp files remain."""
        rc, result, ctx = r8.run_human_main(r8.production_records(),
                                            phases=fx._default_valid_phases())
        _cleanup = lambda c: None  # noqa: E731  (dir retained for asserts)
        try:
            self.assertEqual(rc, 0)
            self.assertEqual(result["status"], "pass")
            out, res_p = ctx["out_path"], ctx["res_path"]
            man = out.with_suffix(".manifest.json")
            self.assertTrue(all(f.is_file() for f in (out, res_p, man)))
            m = json.loads(man.read_text(encoding="utf-8"))
            self.assertEqual(m["result_sha256"], sha256(res_p))
            self.assertEqual(m["raw_sha256"], result["evidence"]["sha256"])
            self.assertEqual(list(Path(ctx["dir"]).glob("*.part")), [])
        finally:
            import shutil
            shutil.rmtree(ctx["dir"], ignore_errors=True)


def _cleanup(ctx):
    import shutil
    shutil.rmtree(ctx["dir"], ignore_errors=True)


if __name__ == "__main__":
    unittest.main(verbosity=1)
