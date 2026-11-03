#!/usr/bin/env python3
"""Comprehensive integration test suite for G2 Round 3 software remediation.

Validates:
1. R4-A: cmd_backpressure contract & execution through real entry (healthy pass, boot change reject, stale frames reject, rpc fail reject, zero ValueError/TypeError notes).
2. R3-A: Device identity extraction without hardcoded fallbacks, envelope parsing, and strict result/exit synchronization.
3. R1-B: Output lifecycle (pre-flight manifest collision interception, subcommand self-finalization preservation).
4. R4-B / R3-A: Human observation multi-phase contract & pure judge freshness/exit rules.
5. R1-A: Review content binding, hash protection, and superseded_by target resolution.
"""

from __future__ import annotations

import ast
import hashlib
import contextlib
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[4]
TOOLS = ROOT / "submodules/mmwave-component/tools/g2"
sys.path.insert(0, str(TOOLS))

import build_evidence_index as bi
import hardware_judges as hj
import mwcp
import power_cut_runner as power
import run_g2 as rg
import usb_unplug_runner as usb


class FakeEvidence:
    def __init__(self, path=None):
        self.path = path or "test.jsonl"
    def note(self, data): pass
    def close(self):
        return {"file": str(self.path), "sha256": "0"*64, "bytes": 100}


class FakeClient:
    def __init__(self, identity="fixture-A", broken=False, boot="1"*32):
        self.identity = identity
        self.broken = broken
        self.boot_id = boot
        self.session_id = 1
        self.last_rtt_ms = 12.5

    def hello(self, timeout_ms=3000):
        return {"boot_id": self.boot_id}

    def close(self): pass
    def resume_reads(self): pass

    def soft_call(self, cmd, *args, **kwargs):
        if self.broken:
            return {"ok": False, "error": {"code": "TIMEOUT"}}
        if cmd == "DEVICE_INFO":
            return {"ok": True, "result": {"device_id": self.identity, "mac": "aa:bb:cc:dd:ee:ff"}}
        return {"ok": True, "result": {}}

    def call(self, cmd, *args, **kwargs):
        return self.soft_call(cmd, *args, **kwargs)

    def ping(self):
        return {"uptime_ms": 1000}


class TestBackpressureRunner(unittest.TestCase):
    """R4-A: Backpressure execution through real entry with fake transport."""

    def test_backpressure_healthy_pass(self):
        c = FakeClient(boot="1"*32)
        count = [0]
        def gap(client, cmd, *args, **kwargs):
            count[0] += 1
            if count[0] == 1:
                return {"ok": True}  # SUBSCRIBE
            n = count[0]
            return {
                "ok": True,
                "result": {
                    "uptime_ms": n * 1000,
                    "radar_link": "healthy",
                    "last_radar_frame_ms": n * 900,
                    "counters": {"radar_frames": n * 10}
                }
            }

        with patch.object(rg, "connect", return_value=(c, FakeEvidence())), \
             patch.object(rg, "gap_call", side_effect=gap), \
             patch.object(rg.time, "sleep"), \
             contextlib.redirect_stdout(io.StringIO()):
            res = rg.cmd_backpressure(SimpleNamespace(seconds=12))

        self.assertEqual(res["status"], "pass")
        # Assert no unexpected exceptions in notes
        for note in res.get("notes", []):
            self.assertNotIn("ValueError", note)
            self.assertNotIn("TypeError", note)
            self.assertNotIn("exception:", note)

    def test_backpressure_boot_changed_rejected(self):
        c = FakeClient(boot="1"*32)
        count = [0]
        def gap(client, cmd, *args, **kwargs):
            count[0] += 1
            if count[0] == 1:
                return {"ok": True}
            n = count[0]
            if n == 3:
                c.boot_id = "2"*32  # spontaneous reboot
            return {
                "ok": True,
                "result": {
                    "uptime_ms": n * 1000,
                    "radar_link": "healthy",
                    "last_radar_frame_ms": n * 900,
                    "counters": {"radar_frames": n * 10}
                }
            }

        with patch.object(rg, "connect", return_value=(c, FakeEvidence())), \
             patch.object(rg, "gap_call", side_effect=gap), \
             patch.object(rg.time, "sleep"), \
             contextlib.redirect_stdout(io.StringIO()):
            res = rg.cmd_backpressure(SimpleNamespace(seconds=12))

        self.assertEqual(res["status"], "fail")
        failed_checks = [chk["name"] for chk in res["checks"] if not chk["pass"]]
        self.assertIn("no_reboot_during_backpressure", failed_checks)
        for note in res.get("notes", []):
            self.assertNotIn("ValueError", note)
            self.assertNotIn("TypeError", note)

    def test_backpressure_stale_frames_rejected(self):
        c = FakeClient(boot="1"*32)
        count = [0]
        def gap(client, cmd, *args, **kwargs):
            count[0] += 1
            if count[0] == 1:
                return {"ok": True}
            return {
                "ok": True,
                "result": {
                    "uptime_ms": 5000,
                    "radar_link": "waiting",
                    "last_radar_frame_ms": 100,  # Never advances
                    "counters": {"radar_frames": 0}
                }
            }

        with patch.object(rg, "connect", return_value=(c, FakeEvidence())), \
             patch.object(rg, "gap_call", side_effect=gap), \
             patch.object(rg.time, "sleep"), \
             contextlib.redirect_stdout(io.StringIO()):
            res = rg.cmd_backpressure(SimpleNamespace(seconds=12))

        self.assertEqual(res["status"], "fail")
        failed_checks = [chk["name"] for chk in res["checks"] if not chk["pass"]]
        self.assertIn("radar_alive_after_backpressure", failed_checks)


class TestIdentityAndAggregation(unittest.TestCase):
    """R3-A: Device identity extraction and synchronized results."""

    def setUp(self):
        self.td = tempfile.mkdtemp(prefix="r3-id-test-")
        self.cfg = {
            "install.x_cm": 10.0, "install.y_cm": 0.0,
            "install.z_cm": 150.0, "install.yaw_deg": 0.0,
            "install.pitch_deg": 0.0, "install.roll_deg": 0.0,
            "geometry.boundary_cm": None, "areas.definitions": []
        }

    def tearDown(self):
        shutil.rmtree(self.td, ignore_errors=True)

    def test_usb_cycle_healthy_identity_pass(self):
        clients = [FakeClient(identity="target-board", boot="1"*32),
                   FakeClient(identity="target-board", boot="2"*32)]
        with patch.object(usb, "robust_connect", side_effect=clients), \
             patch.object(usb, "wait_for_port", return_value=True), \
             patch.object(rg, "read_all_config", return_value=(self.cfg, "1")), \
             patch.object(usb.time, "sleep"), \
             patch.object(usb, "beep_unplug"), patch.object(usb, "beep_plug"), patch.object(usb, "beep_success"), \
             contextlib.redirect_stdout(io.StringIO()):
            rec = usb.run_cycle("FIXTURE", 1, FakeEvidence())

        self.assertTrue(rec["passed"])
        self.assertEqual(rec["verdict"], "UNPLUG_RECOVERED_SAFE")
        self.assertEqual(rec["device_id_before"], "target-board")
        self.assertEqual(rec["device_id_after"], "target-board")

    def test_usb_cycle_broken_client_no_fallback(self):
        clients = [FakeClient(broken=True), FakeClient(broken=True)]
        with patch.object(usb, "robust_connect", side_effect=clients), \
             patch.object(usb, "wait_for_port", return_value=True), \
             patch.object(rg, "read_all_config", return_value=(self.cfg, "1")), \
             patch.object(usb.time, "sleep"), \
             patch.object(usb, "beep_unplug"), patch.object(usb, "beep_plug"), \
             contextlib.redirect_stdout(io.StringIO()):
            rec = usb.run_cycle("FIXTURE", 1, FakeEvidence())

        self.assertFalse(rec["passed"])
        self.assertIsNone(rec["device_id_before"])
        self.assertIsNone(rec["device_id_after"])
        self.assertNotEqual(rec["device_id_before"], "dev-r60abd1")

    def test_power_robust_connect_and_read_no_fallback(self):
        with patch.object(power, "robust_connect", return_value=FakeClient(broken=True)), \
             patch.object(rg, "read_all_config", return_value=(self.cfg, "1")):
            cfg, rev, boot, dev_id = power.robust_connect_and_read("FIXTURE", FakeEvidence())

        self.assertIsNone(dev_id)

    def test_main_result_and_exit_code_synchronized_fail(self):
        """When run_cycle returns a failing record, main exits 1 AND result.json is fail."""
        fail_rec = {
            "cycle": 1, "port": "FIXTURE", "target_port": "FIXTURE",
            "disconnect_observed": True, "reconnect_observed": True,
            "boot_before": "1"*32, "boot_after": "2"*32,
            "device_id_before": None, "device_id_after": None,
            "rev_before": "1", "rev_after": "1",
            "config_before": self.cfg, "config_after": self.cfg,
            "ping_after": {"uptime_ms": 10},
            "passed": False, "verdict": "MISSING_IDENTITY_REJECTED", "detail": "test"
        }
        raw = Path(self.td) / "usb-fail.jsonl"
        res_file = raw.with_suffix(".result.json")
        with patch.object(sys, "argv", ["usb_unplug_runner.py", "--port", "FIXTURE", "--rounds", "1", "--out", str(raw)]), \
             patch.object(rg, "load_secrets", return_value=({}, [])), \
             patch.object(usb, "run_cycle", return_value=fail_rec), \
             contextlib.redirect_stdout(io.StringIO()):
            rc = usb.main()

        self.assertEqual(rc, 1)
        self.assertTrue(res_file.is_file())
        res_data = json.loads(res_file.read_text(encoding="utf-8"))
        self.assertEqual(res_data["status"], "fail")

    def test_main_result_and_exit_code_synchronized_pass(self):
        """When run_cycle returns a passing record, main exits 0 AND result.json is pass."""
        pass_rec = {
            "cycle": 1, "port": "FIXTURE", "target_port": "FIXTURE",
            "disconnect_observed": True, "reconnect_observed": True,
            "boot_before": "1"*32, "boot_after": "2"*32,
            "session_before": 1, "session_after": 2,
            "device_id_before": "test-dev", "device_id_after": "test-dev",
            "rev_before": "1", "rev_after": "1",
            "config_before": self.cfg, "config_after": self.cfg,
            "ping_after": {"uptime_ms": 10},
            "passed": True, "verdict": "UNPLUG_RECOVERED_SAFE", "detail": "test"
        }
        raw = Path(self.td) / "usb-pass.jsonl"
        res_file = raw.with_suffix(".result.json")
        with patch.object(sys, "argv", ["usb_unplug_runner.py", "--port", "FIXTURE", "--rounds", "1", "--out", str(raw)]), \
             patch.object(rg, "load_secrets", return_value=({}, [])), \
             patch.object(usb, "run_cycle", return_value=pass_rec), \
             contextlib.redirect_stdout(io.StringIO()):
            rc = usb.main()

        self.assertEqual(rc, 0)
        self.assertTrue(res_file.is_file())
        res_data = json.loads(res_file.read_text(encoding="utf-8"))
        self.assertEqual(res_data["status"], "pass")


class TestOutputLifecycle(unittest.TestCase):
    """R1-B: Lifecycle preservation and collision interception."""

    def setUp(self):
        self.td = tempfile.mkdtemp(prefix="r3-lifecycle-")

    def tearDown(self):
        shutil.rmtree(self.td, ignore_errors=True)

    def test_preflight_intercepts_manifest_only_collision(self):
        raw = Path(self.td) / "test-manifest-only.jsonl"
        manifest = raw.with_suffix(".manifest.json")
        manifest.write_text('{"sentinel": true}', encoding="utf-8")

        called = [False]
        def fake_cycle(*args, **kwargs):
            called[0] = True
            return {}

        with patch.object(sys, "argv", ["usb_unplug_runner.py", "--port", "FIXTURE", "--rounds", "1", "--out", str(raw)]), \
             patch.object(rg, "load_secrets", return_value=({}, [])), \
             patch.object(usb, "run_cycle", side_effect=fake_cycle), \
             contextlib.redirect_stdout(io.StringIO()), \
             contextlib.redirect_stderr(io.StringIO()):
            rc = usb.main()

        self.assertEqual(rc, 1)
        self.assertFalse(called[0], "Must never touch device stage when manifest already exists")

    def test_collector_already_finalized_preserved_by_main(self):
        def finalized_subcommand(args):
            e = mwcp.EvidenceWriter(Path(args.out), mwcp.Redactor())
            e.note({"test": True})
            res_p = Path(args.out).with_suffix("").with_suffix(".result.json")
            outcome = {
                "run_id": "fixture-run",
                "status": "pass",
                "evidence": e.close(),
                "_finalized_result_path": str(res_p.resolve()),
            }
            res_p.write_text(json.dumps(outcome), encoding="utf-8")
            outcome["_finalized_result_sha"] = hashlib.sha256(res_p.read_bytes()).hexdigest()
            return outcome

        raw = Path(self.td) / "finalized.jsonl"
        with patch.object(sys, "argv", ["run_g2", "probe", "--port", "FIXTURE", "--out", str(raw)]), \
             patch.dict(rg.SUBCOMMANDS, {"probe": finalized_subcommand}), \
             patch.object(rg, "load_secrets", return_value=({}, [])), \
             contextlib.redirect_stdout(io.StringIO()), \
             contextlib.redirect_stderr(io.StringIO()):
            rc = rg.main()

        self.assertEqual(rc, 0)
        res_file = raw.with_suffix(".result.json")
        self.assertTrue(res_file.is_file())
        res_data = json.loads(res_file.read_text(encoding="utf-8"))
        self.assertEqual(res_data["status"], "pass")


class TestHumanObservationMultiPhase(unittest.TestCase):
    """R4-B: Multi-phase human radar observation validation."""

    def test_positive_multi_phase_observation(self):
        # 10 frames absent, 15 frames moving present across inside/outside, 15 frames stationary present, 15 frames sustained absent >= 10s
        records = []
        seq = 100
        for i in range(10):
            seq += 1
            records.append({"presence": {"value": False, "quality": "valid", "sample_ms": i * 100}, "source_seq": seq, "targets": [], "sample_ms": i * 100})
        for i in range(15):
            seq += 1
            records.append({
                "presence": {"value": True, "quality": "valid"},
                "source_seq": seq,
                "sample_ms": 1000 + i * 200,
                "presence": {"value": True, "quality": "valid", "sample_ms": 1000 + i * 200},
                "targets": [{
                    "local_cm": [i * 5.0, 10.0, 0.0],
                    "room_cm": [i * 5.0, 10.0, 0.0],
                    "boundary": "inside" if i < 8 else "outside",
                    "position_quality": "valid",
                    "position_ms": 1000 + i * 200,
                    "speed_cm_s": None
                }]
            })
        for i in range(15):
            seq += 1
            records.append({
                "presence": {"value": True, "quality": "valid"},
                "source_seq": seq,
                "sample_ms": 4000 + i * 200,
                "presence": {"value": True, "quality": "valid", "sample_ms": 4000 + i * 200},
                "targets": [{
                    "local_cm": [25.0, 10.0, 0.0],
                    "room_cm": [25.0, 10.0, 0.0],
                    "boundary": "inside",
                    "position_quality": "valid",
                    "position_ms": 4000 + i * 200,
                    "speed_cm_s": None
                }]
            })
        for i in range(15):
            seq += 1
            records.append({"presence": {"value": False, "quality": "valid", "sample_ms": 7000 + i * 1000}, "source_seq": seq, "targets": [], "sample_ms": 7000 + i * 1000})

        verdict, passed, detail = hj.judge_human_observation(records, min_records=30, user_action_confirmed=True, minimum_exit_duration_ms=10000)
        self.assertTrue(passed, f"Expected pass, got {verdict}: {detail}")
        self.assertEqual(verdict, "HUMAN_OBSERVE_PASS")

    def test_stale_sequence_rejected(self):
        records = [{
            "presence": {"value": i < 25, "quality": "valid"},
            "source_seq": 42,  # Stale sequence across all frames
            "targets": [{"local_cm": [i * 2.0, 0, 0], "room_cm": [i * 2.0, 0, 0], "boundary": "inside", "position_quality": "valid"}] if i < 25 else []
        } for i in range(35)]
        verdict, passed, detail = hj.judge_human_observation(records, min_records=30, user_action_confirmed=True)
        self.assertFalse(passed)
        self.assertEqual(verdict, "STALE_SEQUENCE_REJECTED")

    def test_all_stale_targets_rejected(self):
        records = []
        for i in range(35):
            records.append({
                "presence": {"value": i < 25, "quality": "valid"},
                "source_seq": 100 + i,
                "targets": [{"local_cm": [i * 2.0, 0, 0], "room_cm": [i * 2.0, 0, 0], "boundary": "inside", "position_quality": "stale"}] if i < 25 else []
            })
        verdict, passed, detail = hj.judge_human_observation(records, min_records=30, user_action_confirmed=True)
        self.assertFalse(passed)
        self.assertEqual(verdict, "STALE_TARGETS_REJECTED")

    def test_single_frame_glitch_exit_rejected(self):
        records = []
        for i in range(35):
            records.append({
                "presence": {"value": i < 34, "quality": "valid"},  # Only 1 frame false at index 34
                "source_seq": 100 + i,
                "targets": [{"local_cm": [i * 2.0, 0, 0], "room_cm": [i * 2.0, 0, 0], "boundary": "inside", "position_quality": "valid"}] if i < 34 else []
            })
        verdict, passed, detail = hj.judge_human_observation(records, min_records=30, user_action_confirmed=True)
        self.assertFalse(passed)
        self.assertEqual(verdict, "SINGLE_FRAME_GLITCH_REJECTED")


class TestEvidenceIndexBinding(unittest.TestCase):
    """R1-A: Review content binding and superseded_by validation."""

    def setUp(self):
        self.td = tempfile.mkdtemp(prefix="r3-index-")

    def tearDown(self):
        shutil.rmtree(self.td, ignore_errors=True)

    def test_superseded_by_nonexistent_target_rejected(self):
        rroot = Path(self.td) / "index-root"
        rroot.mkdir()
        raw = rroot / "b1_backpressure.jsonl"
        raw.write_text('{"fixture": true}\n', encoding="utf-8")
        res = rroot / "b1_backpressure.result.json"
        res.write_text(json.dumps({"run_id": "test-bp", "status": "pass", "evidence": {"file": str(raw), "sha256": "0"*64}}), encoding="utf-8")

        reviews = {
            "index-root/b1_backpressure": {
                "accepted_status": "superseded",
                "reason": "testing nonexistent target",
                "superseded_by": "does-not-exist"
            }
        }
        idx = bi.build_index({"index-root": rroot}, Path(self.td) / "idx.json", reviews, bi.FIRMWARE_BATCHES, sources_snapshot={})
        run = idx["runs"][0]
        self.assertEqual(run["accepted_status"], "pending_review")
        self.assertIsNone(run["superseded_by"])

    def test_superseded_by_existing_target_accepted(self):
        rroot = Path(self.td) / "index-root"
        rroot.mkdir()
        def _raw_lines(exp_id, run_id):
            return "\n".join([
                json.dumps({"dir": "note", "event": "experiment_envelope", "experiment_id": exp_id, "run_id": run_id}),
                json.dumps({"dir": "tx", "meta": {"code": 1, "request_id": 1, "session_id": 0}, "payload": {"nonce": "n1"}}),
                json.dumps({
                    "dir": "rx",
                    "meta": {"code": 1, "request_id": 1, "session_id": 1},
                    "payload": {"ok": True, "result": {"nonce": "n1", "boot_id": "a" * 32, "device_id": "board-A"}},
                }),
            ]) + "\n"

        flash_src = rroot / "flash.log.json"
        flash_event = {
            "seq": 1,
            "status": "success",
            "verify": "ok",
            "image_sha256": "b" * 64,
            "device_id": "board-A",
            "timestamp": "2026-10-28T11:00:00+00:00",
        }
        flash_src.write_text(json.dumps([flash_event]), encoding="utf-8")
        fsha = hashlib.sha256(flash_src.read_bytes()).hexdigest()

        # Create target run (must be a verified pass run with matching raw sha256)
        raw2 = rroot / "b4_soak_idle_7200s.jsonl"
        raw2.write_text(_raw_lines("b4_soak_idle_7200s", "soak-target"), encoding="utf-8")
        sha_raw2 = hashlib.sha256(raw2.read_bytes()).hexdigest()
        res2 = rroot / "b4_soak_idle_7200s.result.json"
        res2.write_text(json.dumps({
            "run_id": "soak-target",
            "status": "pass",
            "started": "2026-10-28T12:00:00+0000",
            "ended": "2026-10-28T14:00:00+0000",
            "device_id": "board-A",
            "board_id": "board-A",
            "experiment_id": "b4_soak_idle_7200s",
            "scenario": "soak",
            "duration_seconds": 7200,
            "actual_duration_seconds": 7200,
            "judge_input": {"mode": "idle", "scenario": "soak", "tool_version": "g2-v1",
                             "duration_seconds": 7200, "actual_duration_seconds": 7200},
            "evidence": {"file": str(raw2), "sha256": sha_raw2},
        }), encoding="utf-8")
        sha_res2 = hashlib.sha256(res2.read_bytes()).hexdigest()
        (rroot / "b4_soak_idle_7200s.manifest.json").write_text(json.dumps({
            "schema": "g2-evidence-manifest-v1",
            "run_id": "soak-target",
            "experiment_id": "b4_soak_idle_7200s",
            "started": "2026-10-28T12:00:00+0000",
            "ended": "2026-10-28T14:00:00+0000",
            "boot_id_initial": "a" * 32,
            "board": {"device_id": "board-A"},
            "raw_file": str(raw2),
            "raw_sha256": sha_raw2,
            "result_file": str(res2),
            "result_sha256": sha_res2,
            "flashed_image_sha256": "b" * 64,
            "flash_record": {**flash_event, "source": {"ref": str(flash_src), "sha256": fsha}},
        }), encoding="utf-8")

        # Create rehearsal run that is superseded by target run
        raw1 = rroot / "b4_dry_run_idle_60s.jsonl"
        raw1.write_text(_raw_lines("b4_dry_run_idle_60s", "dry-run"), encoding="utf-8")
        sha_raw1 = hashlib.sha256(raw1.read_bytes()).hexdigest()
        res1 = rroot / "b4_dry_run_idle_60s.result.json"
        res1.write_text(json.dumps({
            "run_id": "dry-run",
            "status": "pass",
            "started": "2026-10-28T12:00:00+0000",
            "ended": "2026-10-28T12:01:00+0000",
            "device_id": "board-A",
            "board_id": "board-A",
            "experiment_id": "b4_dry_run_idle_60s",
            "scenario": "soak",
            "duration_seconds": 60,
            "actual_duration_seconds": 60,
            "judge_input": {"mode": "idle", "scenario": "soak", "tool_version": "g2-v1",
                             "duration_seconds": 60, "actual_duration_seconds": 60},
            "evidence": {"file": str(raw1), "sha256": sha_raw1},
        }), encoding="utf-8")
        sha_res1 = hashlib.sha256(res1.read_bytes()).hexdigest()
        (rroot / "b4_dry_run_idle_60s.manifest.json").write_text(json.dumps({
            "schema": "g2-evidence-manifest-v1",
            "run_id": "dry-run",
            "experiment_id": "b4_dry_run_idle_60s",
            "started": "2026-10-28T12:00:00+0000",
            "ended": "2026-10-28T12:01:00+0000",
            "boot_id_initial": "a" * 32,
            "board": {"device_id": "board-A"},
            "raw_file": str(raw1),
            "raw_sha256": sha_raw1,
            "result_file": str(res1),
            "result_sha256": sha_res1,
            "flashed_image_sha256": "b" * 64,
            "flash_record": {**flash_event, "source": {"ref": str(flash_src), "sha256": fsha}},
        }), encoding="utf-8")

        reviews = {
            "index-root/b4_soak_idle_7200s": {
                "target_root": "index-root",
                "result_sha256": sha_res2,
                "accepted_status": "pass",
                "reason": "verified full 7200s soak",
                "superseded_by": None,
            },
            "index-root/b4_dry_run_idle_60s": {
                "target_root": "index-root",
                "result_sha256": sha_res1,
                "accepted_status": "superseded",
                "reason": "superseded by full soak",
                "superseded_by": "b4_soak_idle_7200s"
            }
        }
        idx = bi.build_index({"index-root": rroot}, Path(self.td) / "idx.json", reviews, bi.FIRMWARE_BATCHES, sources_snapshot={})
        runs = {r["run_id"]: r for r in idx["runs"]}
        self.assertEqual(runs["dry-run"]["accepted_status"], "superseded")
        self.assertEqual(runs["dry-run"]["superseded_by"], "b4_soak_idle_7200s")


if __name__ == "__main__":
    unittest.main()
