#!/usr/bin/env python3
"""R12 delivery: A1 (soak protocol lifecycle + soak_mode), A2 (single result
path / single diagnostic), R9-01 residual (phase-specific frames, no
cross-phase borrowing), B1 (temp object ownership), B2 (exclusive atomic
publish). All offline, fake device/secrets; no serial, no network, no HA."""

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))

import hardware_judges as hj  # noqa: E402
import mwcp  # noqa: E402
import r5_audit_probe_integration_test as fx  # noqa: E402
import r8_remediation_integration_test as r8  # noqa: E402
import run_g2 as rg  # noqa: E402


# --------------------------------------------------------------------------
# A1: strict fake client - the REAL mwcp.Client starts at session_id=0 and
# _request asserts HELLO first (mwcp.py:499).  This fake enforces the same
# rule, so cmd_soak can only complete when hello() is truly the first
# protocol exchange after connect().
# --------------------------------------------------------------------------
class _StrictSoakClient:
    def __init__(self, evidence, device_id="esp32c3-luatos-core"):
        self.evidence = evidence
        self.session_id = 0
        self.boot_id = None
        self.device_id = device_id
        self.calls: list[str] = []
        self._rid = 1
        self._nonce = "a" * 32

    def _require_hello(self, what: str) -> None:
        if self.session_id == 0:
            raise AssertionError(
                f"{what} before HELLO - real Client asserts HELLO first")

    def _frame(self, is_tx: bool, code: int, payload, rid: int) -> None:
        self.evidence.frame(
            is_tx,
            {"kind": 1 if is_tx else 2, "code": code, "request_id": rid,
             "wire_seq": rid, "boot_id": self.boot_id or "B1",
             "session_id": self.session_id if not is_tx else 0},
            payload, [])

    def hello(self, timeout_ms=8000):
        self.calls.append("HELLO")
        rid = self._rid
        self._rid += 1
        # TX on session 0, RX on the NEW session (real handshake shape)
        self.evidence.frame(
            True, {"kind": 1, "code": 1, "session_id": 0, "request_id": rid,
                   "wire_seq": rid, "boot_id": "B1"},
            {"client": {"name": "g2-runner", "version": "0.1.0"},
             "nonce": self._nonce, "protocol": {"major": 1, "minor_max": 0},
             "max_payload": 4096}, [])
        self.session_id = 4096
        self.boot_id = "B1"
        res = {"nonce": self._nonce, "session_ttl_ms": 15000,
               "boot_id": self.boot_id, "device_id": self.device_id,
               "identity": {"device_id": self.device_id}}
        self.evidence.frame(
            False, {"kind": 2, "code": 1, "session_id": self.session_id,
                    "request_id": rid, "wire_seq": rid + 100,
                    "boot_id": self.boot_id},
            {"ok": True, "result": res}, [])
        return {"ok": True, "result": res}

    def ping(self):
        return self.call("PING")

    def call(self, name, payload=None, timeout_ms=9000, **kw):
        self._require_hello(name)
        self.calls.append(name)
        rid = self._rid
        self._rid += 1
        self._frame(True, mwcp.CODE.get(name, 0), payload or {}, rid)
        if name == "DEVICE_INFO":
            resp = {"ok": True, "result": {"device_id": self.device_id,
                                           "board": "esp32c3-luatos-core",
                                           "identity": {"device_id": self.device_id}}}
        elif name == "WIFI_STATUS":
            resp = {"ok": True, "result": {"state": "disconnected", "ssid": "",
                                           "ip": None, "rssi_dbm": None}}
        elif name == "STATUS_GET":
            resp = {"ok": True, "result": {"uptime_ms": 60000,
                                           "radar_link": "healthy",
                                           "counters": {"rx_frames": 99,
                                                        "logs_dropped": 0}}}
        else:
            resp = {"ok": True, "result": {}}
        self._frame(False, mwcp.CODE.get(name, 0), resp, rid)
        return resp

    def drain_events(self, duration_ms, keepalive_s=8.0):
        return []

    def close(self):
        pass


class TestA1SoakProtocolLifecycle(unittest.TestCase):
    """A1: real cmd_soak must establish HELLO as the first protocol exchange
    and must never produce a "soak-None" run tag."""

    def _run_soak(self):
        import argparse
        import time as _time
        with tempfile.TemporaryDirectory(prefix="r12-a1-") as td:
            out_dir = Path(td)
            args = argparse.Namespace(port="FAKE", out=None, allow_write=False,
                                      allow_provision=False, seconds=1,
                                      repeat=None, soak_mode=None,
                                      offline_evidence=None)
            real_connect = rg.connect

            def fake_connect(a, tag, allow_write=False, allow_provision=False):
                controlled, secrets = rg.load_secrets()
                redactor = mwcp.Redactor(controlled_ssids=list(controlled),
                                         secrets=list(secrets))
                evidence = mwcp.EvidenceWriter(out_dir / f"{tag}.jsonl", redactor)
                return _StrictSoakClient(evidence), evidence

            rg.connect = fake_connect
            try:
                with fx._NoRealIO():
                    outcome = rg.cmd_soak(args)
            finally:
                rg.connect = real_connect
            return outcome, out_dir

    def test_hello_is_first_protocol_exchange(self):
        outcome, out_dir = self._run_soak()
        # cmd_soak completed without AssertionError -> the strict guard was
        # never tripped: no call/ping happened before hello()
        self.assertIn("run_id", outcome)
        self.assertNotIn("soak-None", outcome.get("run_id", ""))
        # A1 residual: soak_mode=None with allow_write=False -> idle tag
        self.assertTrue(outcome.get("run_id", "").startswith("g2-07-soak-idle-"),
                        f"run_id={outcome.get('run_id')}")

    def test_strict_guard_proves_order(self):
        # Direct evidence of the order: replay the same fake and record calls.
        import argparse
        with tempfile.TemporaryDirectory(prefix="r12-a1o-") as td:
            evidence_holder = {}

            class _RecClient(_StrictSoakClient):
                pass

            def fake_connect(a, tag, allow_write=False, allow_provision=False):
                evidence_holder["client"] = _RecClient(
                    mock.Mock(), device_id="esp32c3-luatos-core")
                # evidence must support note/frame/close/path for cmd_soak
                return evidence_holder["client"], evidence_holder["evidence"]

            # use a real EvidenceWriter so rebuild works, but keep the client
            real_connect = rg.connect
            args = argparse.Namespace(port="FAKE", out=None, allow_write=False,
                                      allow_provision=False, seconds=1,
                                      repeat=None, soak_mode=None,
                                      offline_evidence=None)
            try:
                with fx._NoRealIO():
                    controlled, secrets = rg.load_secrets()
                    redactor = mwcp.Redactor(controlled_ssids=list(controlled),
                                             secrets=list(secrets))
                    evidence = mwcp.EvidenceWriter(Path(td) / "order.jsonl", redactor)
                    client = _StrictSoakClient(evidence)
                    evidence_holder["evidence"] = evidence
                    evidence_holder["client"] = client
                    rg.connect = lambda a, tag, allow_write=False, allow_provision=False: (client, evidence)
                    rg.cmd_soak(args)
            finally:
                rg.connect = real_connect
            calls = client.calls
            self.assertGreaterEqual(len(calls), 3)
            self.assertEqual(calls[0], "HELLO",
                             f"first exchange must be HELLO, got {calls}")
            self.assertNotIn("SUBSCRIBE", calls[:1])
            self.assertLess(calls.index("HELLO"), calls.index("WIFI_STATUS"))
            self.assertLess(calls.index("HELLO"), calls.index("PING"))
            self.assertLess(calls.index("HELLO"), calls.index("DEVICE_INFO"))
            self.assertEqual(client.session_id, 4096)
            self.assertEqual(client.boot_id, "B1")


class TestA2SingleResultPath(unittest.TestCase):
    """A2: main() must never write a second result; exactly one diagnostic."""

    def test_main_single_diag_no_second_result(self):
        with tempfile.TemporaryDirectory(prefix="r12-a2-") as td:
            td_path = Path(td)
            evdir = td_path / "evidence-default"
            evdir.mkdir()
            intended = td_path / "intended.result.json"
            intended.write_text('{"foreign":"raced-in"}', encoding="utf-8")
            outcome = {"run_id": "g2-07-soak-idle-x", "status": "fail",
                       "checks": [], "notes": [],
                       "_intended_result_path": str(intended.resolve()),
                       "failures": ["result_write_failure: injected"],
                       "error": "result_write_failure: injected"}
            rc, _out, _err = fx._run_main(
                ["run_g2", "soak", "--port", "FAKE"], "soak",
                lambda args: outcome, evdir)
            self.assertEqual(rc, 1)
            self.assertEqual(list(evdir.glob("*.result.json")), [],
                             "main wrote a second result elsewhere")
            diags = list(td_path.rglob("*.collision-*.diag.json"))
            self.assertEqual(len(diags), 1,
                             f"exactly one diagnostic expected, got {diags}")
            self.assertEqual(intended.read_text(encoding="utf-8"),
                             '{"foreign":"raced-in"}',
                             "foreign file must be preserved")


class TestR901PhaseFrameBinding(unittest.TestCase):
    """R9-01 residual: phase counts/durations must consume ONLY the frames
    the runner captured for that phase (live_phase_tracker), never frames
    borrowed from another phase's time window."""

    def test_one_still_frame_rejected_no_borrowing(self):
        # the review's exact counterexample: entry 24 frames, still 1 frame,
        # exit 5 frames; imported windows claim still = 2000..4800ms.
        rows = r8.production_records()
        phases = fx._default_valid_phases()
        tracker = {
            "entry": {"frame_indices": list(range(0, 24)),
                      "source_seqs": list(range(1, 25)),
                      "device_start_ms": 0.0, "device_end_ms": 4600.0},
            "still": {"frame_indices": [24], "source_seqs": [25],
                      "device_start_ms": 4800.0, "device_end_ms": 4800.0},
            "exit": {"frame_indices": list(range(25, 30)),
                     "source_seqs": list(range(26, 31)),
                     "device_start_ms": 5000.0, "device_end_ms": 17000.0},
        }
        hdm = {"live_phase_tracker": tracker}
        verdict, ok, detail = hj.judge_human_observation({
            "telemetry_records": rows,
            "user_action_confirmed": True,
            "minimum_exit_duration_ms": 10000,
            "phases": phases,
            "expected_installation": dict(r8.BASE_CAL),
            "require_structured_phases": True,
            "host_device_time_mapping": hdm,
        })
        self.assertFalse(ok, f"one-still-frame run must be rejected: {verdict}")
        self.assertEqual(verdict, "PHASE_WINDOW_OUTSIDE_CAPTURE_REJECTED")
        # the PHASE-scoped structured verdict must consume only the tracked
        # still frames (1 < 3), never the entry phase's frames
        structured = (detail.get("phase_verdicts", {}).get(
            "structured_action_confirmation", {}) if isinstance(detail, dict) else {})
        self.assertEqual(structured.get("reason"),
                         "PHASE_WINDOW_OUTSIDE_CAPTURE_REJECTED")
        self.assertIn("matched only 1", str(structured.get("detail", "")),
                      "still phase decision must use only its tracked frame")

    def test_aligned_three_phase_still_passes(self):
        # legitimate case: each phase's tracker covers its own window
        rows = r8.production_records()
        phases = fx._default_valid_phases()
        tracker = {
            "entry": {"frame_indices": list(range(0, 12)),
                      "source_seqs": list(range(1, 13)),
                      "device_start_ms": 0.0, "device_end_ms": 2200.0},
            "still": {"frame_indices": list(range(12, 25)),
                      "source_seqs": list(range(13, 26)),
                      "device_start_ms": 2400.0, "device_end_ms": 4800.0},
            "exit": {"frame_indices": list(range(25, 30)),
                     "source_seqs": list(range(26, 31)),
                     "device_start_ms": 5000.0, "device_end_ms": 17000.0},
        }
        hdm = {"live_phase_tracker": tracker}
        verdict, ok, _detail = hj.judge_human_observation({
            "telemetry_records": rows,
            "user_action_confirmed": True,
            "minimum_exit_duration_ms": 10000,
            "phases": phases,
            "expected_installation": dict(r8.BASE_CAL),
            "require_structured_phases": True,
            "host_device_time_mapping": hdm,
        })
        self.assertTrue(ok, f"aligned 3-phase run must pass: {verdict}")


class TestB1TempObjectOwnership(unittest.TestCase):
    """B1: owned_tmp tracks the OBJECT (st_dev, st_ino) this plan created;
    a foreign object that replaces our .part at the same path is never
    deleted by cleanup."""

    def test_replaced_part_not_deleted_at_publish_failure(self):
        # R13 note: on Windows the pinned staging handle makes a real
        # unlink+create replacement impossible (OS-level guarantee, proven
        # in r13); the replaced-path state is simulated on the documented
        # _path_identity seam and the REAL cleanup logic runs unmocked.
        with tempfile.TemporaryDirectory(prefix="r12-b1-") as td:
            dst = Path(td) / "target.result.json"
            plan = rg.OutputPlan.from_raw_target(dst.with_suffix(".jsonl"))
            seen: dict = {}

            def fail_publish(self_plan, target_path, part_path):
                seen["part"] = Path(part_path)
                seen["failed"] = True
                raise OSError("injected storage failure at publish point")

            real_identity = rg.OutputPlan._path_identity

            def foreign_late(p):
                ident = real_identity(p)
                if Path(p) == seen.get("part") and seen.get("failed"):
                    return (ident[0], ident[1] + 1)  # a different object
                return ident

            with mock.patch.object(rg.OutputPlan, "_exclusive_publish",
                                   fail_publish), \
                 mock.patch.object(rg.OutputPlan, "_path_identity",
                                   staticmethod(foreign_late)):
                with self.assertRaises(OSError):
                    plan.finalize_file(dst, '{"our":"pass"}')
            plan.cleanup_unfinalized()
            self.assertFalse(dst.exists(), "no pass may be published")
            tmp = seen["part"]
            self.assertTrue(tmp.exists(),
                            "unattributable object must survive cleanup")
            self.assertEqual(tmp.read_text(encoding="utf-8"), '{"our":"pass"}')

    def test_own_part_removed_when_publish_fails(self):
        with tempfile.TemporaryDirectory(prefix="r12-b1f-") as td:
            dst = Path(td) / "target.result.json"
            plan = rg.OutputPlan.from_raw_target(dst.with_suffix(".jsonl"))
            with mock.patch.object(rg.OutputPlan, "_exclusive_publish",
                                   side_effect=OSError("injected")):
                with self.assertRaises(OSError):
                    plan.finalize_file(dst, '{"our":"pass"}')
            plan.cleanup_unfinalized()
            self.assertFalse(dst.exists())
            self.assertEqual(list(Path(td).glob("*.part")), [],
                             "our own failed .part must be self-cleaned")

    def test_preexisting_foreign_part_survives(self):
        with tempfile.TemporaryDirectory(prefix="r12-b1p-") as td:
            dst = Path(td) / "target.result.json"
            plan = rg.OutputPlan.from_raw_target(dst.with_suffix(".jsonl"))
            foreign_part = dst.with_name(
                dst.name + f".{plan.reservation_id[:8]}.part")
            foreign_part.write_text('{"foreign":"temp"}', encoding="utf-8")
            plan.cleanup_unfinalized()
            self.assertTrue(foreign_part.exists())
            self.assertEqual(foreign_part.read_text(encoding="utf-8"),
                             '{"foreign":"temp"}')

    def test_success_publishes_and_removes_own_part(self):
        with tempfile.TemporaryDirectory(prefix="r12-b1s-") as td:
            dst = Path(td) / "target.result.json"
            plan = rg.OutputPlan.from_raw_target(dst.with_suffix(".jsonl"))
            plan.finalize_file(dst, '{"our":"pass"}')
            self.assertEqual(dst.read_text(encoding="utf-8"), '{"our":"pass"}')
            self.assertEqual(list(Path(td).glob("*.part")), [])


class TestB2ExclusiveAtomicPublish(unittest.TestCase):
    """B2: the completed .part IS the published object.  The target either
    receives the full bytes in one atomic operation or never exists - no
    pass is visible at the final path before the publish."""

    @staticmethod
    def _spy_patcher(observed, real_ops):
        # R14: while the pin (DELETE access, no delete-share) is open, no
        # new handle can open the staging file for reading - so the spy
        # records only existence/timing at the publish call; the source
        # content is proven post-publish via the target bytes.
        def spy_rename(src, dst, *a, **kw):
            observed["dst_exists_at_publish"] = os.path.exists(dst)
            observed["src_recorded"] = str(src)
            return real_ops["rename"](src, dst, *a, **kw)

        def spy_link(src, dst, *a, **kw):
            observed["dst_exists_at_publish"] = os.path.exists(dst)
            observed["src_recorded"] = str(src)
            return real_ops["link"](src, dst, *a, **kw)

        return [mock.patch("os.rename", spy_rename),
                mock.patch("os.link", spy_link)]

    def test_target_never_holds_pass_before_publish(self):
        real_ops = {"rename": os.rename, "link": os.link}
        PASS = '{"status":"pass","verdict":"OK"}'
        for use_reservation in (False, True):
            with self.subTest(reserved=use_reservation):
                observed = {}
                with tempfile.TemporaryDirectory(prefix="r12-b2-") as td:
                    dst = Path(td) / "t.result.json"
                    plan = rg.OutputPlan.from_raw_target(Path(td) / "t.jsonl")
                    if use_reservation:
                        plan.reserve_all()
                    patches = self._spy_patcher(observed, real_ops)
                    for p in patches:
                        p.start()
                    try:
                        plan.finalize_file(dst, PASS)
                    finally:
                        for p in reversed(patches):
                            p.stop()
                    self.assertFalse(
                        observed["dst_exists_at_publish"],
                        "pass was visible at the final path BEFORE publish")
                    # the published object IS the completed .part: the target
                    # carries exactly the staged content after the publish
                    self.assertTrue(observed["src_recorded"].endswith(".part"))
                    self.assertEqual(dst.read_text(encoding="utf-8"), PASS)
                    plan.cleanup_unfinalized()

    def test_publish_failure_leaves_no_pass(self):
        # simulated execution interruption at the publish point: with
        # rename-publish there is no partially-written target to mistake
        # for completed evidence - the target simply never exists.
        with tempfile.TemporaryDirectory(prefix="r12-b2f-") as td:
            dst = Path(td) / "t.result.json"
            plan = rg.OutputPlan.from_raw_target(dst.with_suffix(".jsonl"))
            with mock.patch("os.rename", side_effect=OSError("interrupted")), \
                 mock.patch("os.link", side_effect=OSError("interrupted")):
                with self.assertRaises(OSError):
                    plan.finalize_file(dst, '{"status":"pass"}')
            self.assertFalse(dst.exists(), "no pass may remain at final path")
            plan.cleanup_unfinalized()
            self.assertEqual(list(Path(td).glob("*.part")), [])

    def test_foreign_target_not_overwritten(self):
        with tempfile.TemporaryDirectory(prefix="r12-b2x-") as td:
            dst = Path(td) / "t.result.json"
            dst.write_text('{"foreign":"data"}', encoding="utf-8")
            before = dst.read_bytes()
            plan = rg.OutputPlan.from_raw_target(dst.with_suffix(".jsonl"))
            with self.assertRaises(FileExistsError):
                plan.finalize_file(dst, '{"our":"pass"}')
            self.assertEqual(dst.read_bytes(), before,
                             "foreign bytes must be preserved")


if __name__ == "__main__":
    unittest.main(verbosity=1)
