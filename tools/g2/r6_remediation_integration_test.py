# -*- coding: utf-8 -*-
#!/usr/bin/env python3
"""Round 6 remediation integration test suite (R6-01 through R6-04).

Verifies all 11 probes from tmp/g2-review-20261031-r6/review.py plus positive
and negative contract coverage for:
- R6-01: Multi-phase human observation judge & real human_observe_runner.main()
- R6-02: Firmware-parity R60 config validation (steps, ranges, polygons, areas)
- R6-03: Evidence index mandatory raw reference & two-stage superseded_by graph
- R6-04: Preflight collision check before secrets/serial I/O on default & explicit paths
"""

from __future__ import annotations

import hashlib
import json
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
import r5_audit_probe_integration_test as fx  # noqa: E402
import run_g2 as rg  # noqa: E402
import usb_unplug_runner as uur  # noqa: E402


class TestR601HumanObservationPhases(unittest.TestCase):
    """R6-01: Full multi-phase human observation judgment & real runner entry."""

    def setUp(self):
        self.runner = fx.TestR4BRealHumanRunner()

    def test_probe_human_only_inside_no_phases_rejected(self):
        """R6 audit probe 1: only inside targets and no structured phases -> fail."""
        rows = fx._base_human_records(n=30, exit_frames=5, exit_interval_ms=3000)
        rc, result = self.runner._run_runner(rows, confirm=True)
        self.assertEqual(rc, 1)
        self.assertEqual(result["status"], "fail")
        self.assertEqual(result["verdict"], "BOUNDARY_TRAVERSAL_INCOMPLETE_REJECTED")
        self.assertEqual(result["phase_verdicts"]["entry_motion"]["status"], "fail")

    def test_probe_human_missing_timestamps_rejected(self):
        """R6 audit probe 2: missing sample_ms and sent_ms -> MISSING_TIMESTAMPS_REJECTED."""
        rows = fx._base_human_records(n=30, exit_frames=5, exit_interval_ms=3000)
        for r in rows:
            r.pop("sample_ms", None)
            r.pop("sent_ms", None)
        rc, result = self.runner._run_runner(rows, confirm=True)
        self.assertEqual(rc, 1)
        self.assertEqual(result["status"], "fail")
        self.assertEqual(result["verdict"], "MISSING_TIMESTAMPS_REJECTED")

    def test_probe_human_stale_position_timestamp_rejected(self):
        """R6 audit probe 3: frozen target position_ms=1 -> STALE_POSITION_TIMESTAMP_REJECTED."""
        rows = fx._base_human_records(n=30, exit_frames=5, exit_interval_ms=3000)
        for r in rows:
            for target in r.get("targets") or []:
                target["position_ms"] = 1
        rc, result = self.runner._run_runner(rows, confirm=True)
        self.assertEqual(rc, 1)
        self.assertEqual(result["status"], "fail")
        self.assertEqual(result["verdict"], "STALE_POSITION_TIMESTAMP_REJECTED")

    def test_probe_human_wrong_room_z_rejected(self):
        """R6 audit probe 4: corrupted room_cm[2]=9999 -> COORDINATE_TRANSFORM_MISMATCH_REJECTED."""
        rows = fx._base_human_records(n=30, exit_frames=5, exit_interval_ms=3000)
        for r in rows:
            for target in r.get("targets") or []:
                target["room_cm"][2] = 9999
        rc, result = self.runner._run_runner(rows, confirm=True)
        self.assertEqual(rc, 1)
        self.assertEqual(result["status"], "fail")
        self.assertEqual(result["verdict"], "COORDINATE_TRANSFORM_MISMATCH_REJECTED")

    def test_single_boolean_confirm_without_structured_phases_rejected(self):
        """--confirm-user-actions alone without structured phase confirmation is rejected."""
        rows = fx._base_human_records(
            n=30, exit_frames=5, exit_interval_ms=3000,
            x_motion=True, mirror_room=False, full_phases=True,
        )
        rc, result = self.runner._run_runner(rows, confirm=True, phases=None)
        self.assertEqual(rc, 1)
        self.assertEqual(result["status"], "fail")
        self.assertEqual(result["verdict"], "MISSING_STRUCTURED_PHASES_REJECTED")

    def test_boundary_polygon_classification_mismatch_rejected(self):
        """Target boundary label contradicting configured polygon is rejected."""
        rows = fx._base_human_records(
            n=30, exit_frames=5, exit_interval_ms=3000,
            x_motion=True, mirror_room=False, full_phases=True,
        )
        inst = dict(self.runner.INST)
        # Polygon covering x in [-100, 10], y in [-100, 100]: target at x=42 is outside, but labeled inside
        inst["geometry.boundary_cm"] = [[-100.0, -100.0], [10.0, -100.0], [10.0, 100.0], [-100.0, 100.0]]
        verdict, passed, detail = hj.judge_human_observation(
            rows,
            user_action_confirmed=True,
            expected_installation=inst,
            phases=fx._default_valid_phases(),
            require_structured_phases=True,
        )
        self.assertFalse(passed)
        self.assertEqual(verdict, "BOUNDARY_CLASSIFICATION_MISMATCH_REJECTED")

    def test_timestamp_regression_rejected(self):
        """Non-monotonic frame timestamps -> TIMESTAMP_REGRESSION_REJECTED."""
        rows = fx._base_human_records(
            n=30, exit_frames=5, exit_interval_ms=3000,
            x_motion=True, mirror_room=False, full_phases=True,
        )
        rows[5]["sample_ms"] = rows[4]["sample_ms"] - 10
        rc, result = self.runner._run_runner(rows, confirm=True, phases=fx._default_valid_phases())
        self.assertEqual(rc, 1)
        self.assertEqual(result["status"], "fail")
        self.assertEqual(result["verdict"], "TIMESTAMP_REGRESSION_REJECTED")

    def test_positive_full_multi_phase_runner_passes(self):
        """Full 3-phase telemetry + structured phase confirmations + 3D transform -> PASS."""
        rows = fx._base_human_records(
            n=30, exit_frames=5, exit_interval_ms=3000,
            x_motion=True, mirror_room=False, full_phases=True,
        )
        rc, result = self.runner._run_runner(rows, confirm=True, phases=fx._default_valid_phases())
        self.assertEqual(rc, 0, result)
        self.assertEqual(result["status"], "pass")
        self.assertEqual(result["verdict"], "HUMAN_OBSERVE_PASS")
        for phase_key in ("time_and_integrity", "entry_motion", "still_retention",
                          "departure_exit", "coordinate_consistency", "structured_action_confirmation"):
            self.assertEqual(result["phase_verdicts"][phase_key]["status"], "pass")


class TestR602ConfigValidationParity(unittest.TestCase):
    """R6-02: Firmware-parity R60 configuration validation across power cut & USB unplug."""

    def test_probe_power_empty_boundary_rejected(self):
        """R6 audit probe 5: geometry.boundary_cm=[] must be rejected."""
        rec = fx._base_power_record()
        rec["config_target"] = dict(rec["config_target"], **{"geometry.boundary_cm": []})
        rec["config_recovered"] = dict(rec["config_target"])
        verdict, passed, _ = hj.judge_power_cut_cycle(rec)
        self.assertFalse(passed)
        self.assertEqual(verdict, "INCOMPLETE_CONFIG_REJECTED")

    def test_probe_power_zero_area_boundary_rejected(self):
        """R6 audit probe 6: collinear zero-area boundary [[0,0],[1,1],[2,2]] must be rejected."""
        rec = fx._base_power_record()
        rec["config_target"] = dict(rec["config_target"], **{"geometry.boundary_cm": [[0, 0], [1, 1], [2, 2]]})
        rec["config_recovered"] = dict(rec["config_target"])
        verdict, passed, _ = hj.judge_power_cut_cycle(rec)
        self.assertFalse(passed)
        self.assertEqual(verdict, "INCOMPLETE_CONFIG_REJECTED")

    def test_probe_power_enabled_area_no_points_rejected(self):
        """R6 audit probe 7: enabled area with empty points_cm=[] must be rejected."""
        rec = fx._base_power_record()
        rec["config_target"] = dict(
            rec["config_target"],
            **{"areas.definitions": [{"slot": 0, "enabled": True, "name": "test", "points_cm": []}]},
        )
        rec["config_recovered"] = dict(rec["config_target"])
        verdict, passed, _ = hj.judge_power_cut_cycle(rec)
        self.assertFalse(passed)
        self.assertEqual(verdict, "INCOMPLETE_CONFIG_REJECTED")

    def test_self_intersecting_polygon_rejected(self):
        """Bowtie self-intersecting polygon must be rejected."""
        rec = fx._base_power_record()
        rec["config_target"] = dict(
            rec["config_target"],
            **{"geometry.boundary_cm": [[0, 0], [100, 100], [100, 0], [0, 100]]},
        )
        rec["config_recovered"] = dict(rec["config_target"])
        verdict, passed, _ = hj.judge_power_cut_cycle(rec)
        self.assertFalse(passed)
        self.assertEqual(verdict, "INCOMPLETE_CONFIG_REJECTED")

    def test_step_size_violation_and_unknown_key_rejected(self):
        """install.x_cm not on 1.0 step or install.yaw_deg not on 0.5 step or extra key -> rejected."""
        rec = fx._base_power_record()
        rec["config_target"] = dict(rec["config_target"], **{"install.x_cm": 10.3})
        rec["config_recovered"] = dict(rec["config_target"])
        v1, p1, _ = hj.judge_power_cut_cycle(rec)
        self.assertFalse(p1)
        self.assertEqual(v1, "INCOMPLETE_CONFIG_REJECTED")

        rec2 = fx._base_power_record()
        rec2["config_target"] = dict(rec2["config_target"], **{"unknown.extra_key": 1})
        rec2["config_recovered"] = dict(rec2["config_target"])
        v2, p2, _ = hj.judge_power_cut_cycle(rec2)
        self.assertFalse(p2)
        self.assertEqual(v2, "INCOMPLETE_CONFIG_REJECTED")

    def test_duplicate_area_slot_and_control_char_name_rejected(self):
        """Duplicate area slot or control character in area name -> rejected."""
        poly = [[0, 0], [100, 0], [100, 100]]
        rec = fx._base_power_record()
        rec["config_target"] = dict(
            rec["config_target"],
            **{"areas.definitions": [
                {"slot": 0, "enabled": True, "name": "a", "points_cm": poly},
                {"slot": 0, "enabled": True, "name": "b", "points_cm": poly},
            ]},
        )
        rec["config_recovered"] = dict(rec["config_target"])
        v1, p1, _ = hj.judge_power_cut_cycle(rec)
        self.assertFalse(p1)
        self.assertEqual(v1, "INCOMPLETE_CONFIG_REJECTED")

        rec2 = fx._base_power_record()
        rec2["config_target"] = dict(
            rec2["config_target"],
            **{"areas.definitions": [
                {"slot": 0, "enabled": True, "name": "bad\nname", "points_cm": poly},
            ]},
        )
        rec2["config_recovered"] = dict(rec2["config_target"])
        v2, p2, _ = hj.judge_power_cut_cycle(rec2)
        self.assertFalse(p2)
        self.assertEqual(v2, "INCOMPLETE_CONFIG_REJECTED")


class TestR603EvidenceIndexIntegrityAndSupersede(unittest.TestCase):
    """R6-03: Mandatory raw reference & two-stage superseded_by graph validation."""

    def setUp(self):
        self.idx_helper = fx.TestR1AEvidenceIndex()

    def test_probe_index_missing_entire_raw_reference_rejected(self):
        """R6 audit probe 8: result with 'evidence' key popped cannot be accepted as pass."""
        with tempfile.TemporaryDirectory(prefix="r6-idx-raw-") as td:
            root = Path(td)
            res_path, _ = self.idx_helper._write_run(root, "g2-03-human-no-raw")
            doc = json.loads(res_path.read_text(encoding="utf-8"))
            doc.pop("evidence", None)
            res_path.write_text(json.dumps(doc), encoding="utf-8")
            new_sha = hashlib.sha256(res_path.read_bytes()).hexdigest()
            reviews = {
                "g2-03-human-no-raw": {
                    "target_root": "s1",
                    "result_sha256": new_sha,
                    "accepted_status": "pass",
                    "reason": "probe missing entire evidence field",
                }
            }
            out = bi.build_index({"s1": root}, root / "index.json", reviews, {"b": {}}, {})
            run = out["runs"][0]
            self.assertEqual(run["accepted_status"], "pending_review")
            self.assertIn("missing required evidence reference", run["review_note"])

    def test_probe_index_unreviewed_target_rejected(self):
        """R6 audit probe 9: superseding by an unreviewed (pending_review) target is rejected."""
        with tempfile.TemporaryDirectory(prefix="r6-idx-unrev-") as td:
            root = Path(td)
            _, sha_old = self.idx_helper._write_run(root, "g2-07-soak-idle-old", mode="idle")
            self.idx_helper._write_run(root, "g2-07-soak-idle-new", mode="idle")
            reviews = {
                "g2-07-soak-idle-old": {
                    "target_root": "s1",
                    "result_sha256": sha_old,
                    "accepted_status": "superseded",
                    "superseded_by": "g2-07-soak-idle-new",
                    "reason": "probe unreviewed replacement target",
                }
            }
            out = bi.build_index({"s1": root}, root / "index.json", reviews, {"b": {}}, {})
            by_id = {r["run_id"]: r for r in out["runs"]}
            self.assertEqual(by_id["g2-07-soak-idle-old"]["accepted_status"], "pending_review")
            self.assertIsNone(by_id["g2-07-soak-idle-old"]["superseded_by"])

    def test_probe_index_shorter_other_device_firmware_rejected(self):
        """R6 audit probe 10: superseding 7200s board-A run by 60s board-B run is rejected."""
        with tempfile.TemporaryDirectory(prefix="r6-idx-short-") as td:
            root = Path(td)
            p_old, _ = self.idx_helper._write_run(root, "g2-07-soak-idle-7200s-old", mode="idle")
            p_new, _ = self.idx_helper._write_run(root, "g2-07-soak-idle-60s-new", mode="idle")
            for p, dev, fw, dur, tv in (
                (p_old, "board-A", "a" * 64, 7200, "v1"),
                (p_new, "board-B", "b" * 64, 60, "v2"),
            ):
                d = json.loads(p.read_text(encoding="utf-8"))
                d.update({
                    "device_id": dev,
                    "firmware_sha256": fw,
                    "duration_seconds": dur,
                    "judge_input": {"mode": "idle", "duration_seconds": dur, "tool_version": tv},
                })
                p.write_text(json.dumps(d), encoding="utf-8")
            sha_old = hashlib.sha256(p_old.read_bytes()).hexdigest()
            sha_new = hashlib.sha256(p_new.read_bytes()).hexdigest()
            reviews = {
                "g2-07-soak-idle-7200s-old": {
                    "target_root": "s1",
                    "result_sha256": sha_old,
                    "accepted_status": "superseded",
                    "superseded_by": "g2-07-soak-idle-60s-new",
                    "reason": "probe shorter other device/firmware",
                },
                "g2-07-soak-idle-60s-new": {
                    "target_root": "s1",
                    "result_sha256": sha_new,
                    "accepted_status": "pass",
                    "reason": "short pass on other board",
                },
            }
            out = bi.build_index({"s1": root}, root / "index.json", reviews, {"b": {}}, {})
            by_id = {r["run_id"]: r for r in out["runs"]}
            self.assertEqual(by_id["g2-07-soak-idle-7200s-old"]["accepted_status"], "pending_review")
            self.assertIsNone(by_id["g2-07-soak-idle-7200s-old"]["superseded_by"])

    def test_two_node_and_three_node_supersede_cycles_rejected(self):
        """A -> B -> A and A -> B -> C -> A cycles must downgrade all cycle participants."""
        with tempfile.TemporaryDirectory(prefix="r6-idx-cyc-") as td:
            root = Path(td)
            _, sha_a = self.idx_helper._write_run(root, "g2-07-soak-idle-a", mode="idle")
            _, sha_b = self.idx_helper._write_run(root, "g2-07-soak-idle-b", mode="idle")
            _, sha_c = self.idx_helper._write_run(root, "g2-07-soak-idle-c", mode="idle")
            reviews = {
                "g2-07-soak-idle-a": {
                    "target_root": "s1", "result_sha256": sha_a,
                    "accepted_status": "superseded", "superseded_by": "g2-07-soak-idle-b", "reason": "a->b",
                },
                "g2-07-soak-idle-b": {
                    "target_root": "s1", "result_sha256": sha_b,
                    "accepted_status": "superseded", "superseded_by": "g2-07-soak-idle-c", "reason": "b->c",
                },
                "g2-07-soak-idle-c": {
                    "target_root": "s1", "result_sha256": sha_c,
                    "accepted_status": "superseded", "superseded_by": "g2-07-soak-idle-a", "reason": "c->a",
                },
            }
            out = bi.build_index({"s1": root}, root / "index.json", reviews, {"b": {}}, {})
            for r in out["runs"]:
                self.assertEqual(r["accepted_status"], "pending_review")
                self.assertIsNone(r["superseded_by"])


class TestR604PreflightOutputCollisionBeforeIO(unittest.TestCase):
    """R6-04: Preflight output collision check before secrets or serial I/O."""

    def test_probe_default_result_collision_before_io(self):
        """R6 audit probe 11: default path collision must return 1 with 0 secrets/device calls."""
        with tempfile.TemporaryDirectory(prefix="r6-def-") as td:
            folder = Path(td)
            collided = folder / "g2-07-soak-idle-FIXED.result.json"
            collided.write_text('{"foreign": true}', encoding="utf-8")
            with fx._NoRealIO(), \
                 mock.patch.object(sys, "argv", ["run_g2", "soak", "--port", "FAKE"]), \
                 mock.patch.object(rg, "EVIDENCE_DIR", folder), \
                 mock.patch.object(rg.time, "strftime", return_value="FIXED"), \
                 mock.patch.object(rg, "load_secrets", return_value=([], [])) as secrets, \
                 mock.patch.object(rg.mwcp, "Client", side_effect=AssertionError("device I/O should not start")) as device, \
                 mock.patch("sys.stderr"):
                rc = rg.main()
            self.assertEqual(rc, 1)
            self.assertEqual(secrets.call_count, 0)
            self.assertEqual(device.call_count, 0)
            self.assertEqual(collided.read_text(encoding="utf-8"), '{"foreign": true}')
            self.assertFalse((folder / "g2-07-soak-idle-FIXED.jsonl").exists())

    def test_standalone_runners_preflight_before_secrets_and_io(self):
        """human_observe_runner, power_cut_runner, usb_unplug_runner preflight before load_secrets."""
        with tempfile.TemporaryDirectory(prefix="r6-runners-") as td:
            folder = Path(td)
            for mod, cmd_name, base_name in (
                (hor, "human_observe_runner", "h.a.b"),
                (pcr, "power_cut_runner", "p.a.b"),
                (uur, "usb_unplug_runner", "u.a.b"),
            ):
                raw_out = folder / f"{base_name}.jsonl"
                res_collision = folder / f"{base_name}.result.json"
                res_collision.write_text('{"foreign": true}', encoding="utf-8")
                with fx._NoRealIO(), \
                     mock.patch.object(sys, "argv", [cmd_name, "--port", "FAKE", "--out", str(raw_out)]), \
                     mock.patch.object(rg, "load_secrets", return_value=([], [])) as secrets, \
                     mock.patch("sys.stderr"):
                    rc = mod.main()
                self.assertEqual(rc, 1)
                self.assertEqual(secrets.call_count, 0)
                self.assertEqual(res_collision.read_text(encoding="utf-8"), '{"foreign": true}')


if __name__ == "__main__":
    unittest.main()
