#!/usr/bin/env python3
"""G2 Hardware Round 7 Remediation Integration Test Suite (R7-01..R7-04).

Covers all 12 independent audit probes from Round 7 plus positive and negative
integration tests across R7-01 (2D protocol telemetry, live phase runner,
timestamp/sequence/clock-domain/identity/boundary validation, exception cleanup),
R7-02 (8-key R60 config step & vertex rules across judge + power/usb runners),
R7-03 (strict superseded_by structured metadata & actual coverage duration),
and R7-04 (OutputPlan pre-I/O atomic reservation across multi-leg subcommands).
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

TOOLS_G2 = Path(__file__).resolve().parent
if str(TOOLS_G2) not in sys.path:
    sys.path.insert(0, str(TOOLS_G2))

import build_evidence_index as bi
import hardware_judges as hj
import human_observe_runner as hor
import mwcp
import power_cut_runner as pcr
import r5_audit_probe_integration_test as fx
import run_g2
import usb_unplug_runner as ucr


def _regular_polygon(n_vertices: int, radius_cm: float = 80.0, cx: float = 0.0, cy: float = 150.0) -> list[list[float]]:
    pts = []
    for k in range(n_vertices):
        ang = 2.0 * math.pi * k / n_vertices
        x = round(round((cx + radius_cm * math.cos(ang)) * 2.0) / 2.0, 1)
        y = round(round((cy + radius_cm * math.sin(ang)) * 2.0) / 2.0, 1)
        pts.append([x, y])
    return pts


class TestR701TwoDAndLivePhaseHumanObserve(unittest.TestCase):
    """R7-01: 2D protocol coordinate support, live phase windows, timestamp/seq
    checks, identity/capability/boundary requirements, and resource cleanup."""

    def test_audit_probe_human_control_3d_and_protocol_2d(self):
        """Probes 1 & 2 + two_d.py: both 3D control and 2D protocol [x, y] pass."""
        rows_3d = fx._base_human_records(n=30, exit_frames=5, exit_interval_ms=3000, full_phases=True)
        rc3, res3 = fx.TestR4BRealHumanRunner()._run_runner(
            rows_3d, confirm=True, phases=fx._default_valid_phases()
        )
        self.assertEqual(rc3, 0, res3)
        self.assertEqual(res3["status"], "pass")
        self.assertEqual(res3["verdict"], "HUMAN_OBSERVE_PASS")

        rows_2d = copy.deepcopy(rows_3d)
        for r in rows_2d:
            r["sent_ms"] = r["sample_ms"]
            r["presence"]["sample_ms"] = r["sample_ms"]
            for t in r.get("targets", []):
                t["id"] = 1
                t["local_cm"] = t["local_cm"][:2]
                t["room_cm"] = t["room_cm"][:2]
        rc2, res2 = fx.TestR4BRealHumanRunner()._run_runner(
            rows_2d, confirm=True, phases=fx._default_valid_phases()
        )
        self.assertEqual(rc2, 0, res2)
        self.assertEqual(res2["status"], "pass")
        self.assertEqual(res2["verdict"], "HUMAN_OBSERVE_PASS")
        self.assertEqual(
            res2["phase_verdicts"]["coordinate_consistency"]["dimension"], 2
        )

    def test_real_runner_live_interactive_three_phases_2d_positive(self):
        """Real human_observe_runner.main() with live PHASE_CONFIRMER across 3 phases
        and 2D [x, y] telemetry records non-fabricated observed_windows and passes."""
        with tempfile.TemporaryDirectory(prefix="r7-hor-live-") as td:
            out_path = Path(td) / "human_live_2d.jsonl"
            res_path = Path(td) / "human_live_2d.result.json"
            man_path = Path(td) / "human_live_2d.manifest.json"

            # Build 3 batches of 2D telemetry corresponding to entry (0..2200ms),
            # still (2400..4800ms), and exit (5000..17000ms)
            all_rows = fx._base_human_records(n=30, exit_frames=5, exit_interval_ms=3000, full_phases=True)
            for r in all_rows:
                r["sent_ms"] = r["sample_ms"]
                r["presence"]["sample_ms"] = r["sample_ms"]
                for t in r.get("targets", []):
                    t["id"] = 1
                    t["local_cm"] = t["local_cm"][:2]
                    t["room_cm"] = t["room_cm"][:2]

            entry_events = [
                {"meta": {"code": mwcp.CODE["TELEMETRY"]}, "payload": r}
                for r in all_rows[:12]
            ]
            still_events = [
                {"meta": {"code": mwcp.CODE["TELEMETRY"]}, "payload": r}
                for r in all_rows[12:25]
            ]
            exit_events = [
                {"meta": {"code": mwcp.CODE["TELEMETRY"]}, "payload": r}
                for r in all_rows[25:]
            ]
            batches = [entry_events, still_events, exit_events]
            clock = [1000.0]
            closed_flags = {"client": False}

            class LiveFakeClient:
                boot_id = "d" * 32
                session_id = 7

                def call(self, name, payload=None, **kw):
                    if name == "DEVICE_INFO":
                        return {"ok": True, "result": {"device_id": "r60-live-2d", "model": "R60ABD1"}}
                    if name == "CAPABILITIES_LIST":
                        return {
                            "ok": True,
                            "result": {
                                "items": [
                                    {"id": "presence", "UpdateMs": 200, "StaleAfterMs": 6000},
                                    {"id": "position.xy", "Units": "cm", "UpdateMs": 200, "StaleAfterMs": 6000},
                                ]
                            },
                        }
                    return {"ok": True, "result": {}}

                def ping(self):
                    return {"ok": True, "result": {}}

                def drain_events(self, duration_ms):
                    clock[0] += 20.0
                    if batches:
                        return batches.pop(0)
                    return []

                def close(self):
                    closed_flags["client"] = True

            confirmed_phases = []

            def fake_phase_confirmer(phase_name: str, s_ms: float, e_ms: float) -> bool:
                confirmed_phases.append((phase_name, s_ms, e_ms))
                return True

            argv = [
                "human_observe_runner",
                "--port", "COM9",
                "--seconds", "60",
                "--out", str(out_path),
                "--min-exit-ms", "10000",
            ]
            with fx._NoRealIO() as guard, \
                 mock.patch.object(sys, "argv", argv), \
                 mock.patch.object(hor, "robust_connect", return_value=LiveFakeClient()), \
                 mock.patch.object(hor.run_g2, "read_all_config", return_value=(dict(fx.TestR4BRealHumanRunner.INST), "1")), \
                 mock.patch.object(hor, "PHASE_CONFIRMER", side_effect=fake_phase_confirmer), \
                 mock.patch.object(hor, "beep_phase"), \
                 mock.patch.object(hor, "beep_complete"), \
                 mock.patch.object(hor.winsound, "Beep", return_value=None), \
                 mock.patch("builtins.print"), \
                 mock.patch.object(hor.time, "sleep", return_value=None), \
                 mock.patch.object(hor.time, "time", side_effect=lambda: clock[0]), \
                 mock.patch.object(hor.time, "monotonic", side_effect=lambda: clock[0]):
                rc = hor.main()

            self.assertEqual(guard.attempts, [])
            self.assertEqual(rc, 0)
            self.assertTrue(closed_flags["client"])
            self.assertEqual([p[0] for p in confirmed_phases], ["entry", "still", "exit"])
            res = json.loads(res_path.read_text(encoding="utf-8"))
            self.assertEqual(res["status"], "pass")
            self.assertEqual(res["verdict"], "HUMAN_OBSERVE_PASS")
            obs_win = res["phases"]
            self.assertEqual(obs_win["entry"]["start_ms"], 0.0)
            self.assertEqual(obs_win["entry"]["end_ms"], 2200.0)
            self.assertEqual(obs_win["still"]["start_ms"], 2400.0)
            self.assertEqual(obs_win["still"]["end_ms"], 4800.0)
            self.assertEqual(obs_win["exit"]["start_ms"], 5000.0)
            self.assertEqual(obs_win["exit"]["end_ms"], 17000.0)
            self.assertTrue(man_path.is_file())

    def test_audit_probes_phase_windows_and_timestamps_and_sequences(self):
        """Probes 3..7: outside capture, zero-length phases, missing position_ms,
        old advancing position_ms, and duplicate exit sequence are all rejected."""
        base_rows = fx._base_human_records(n=30, exit_frames=5, exit_interval_ms=3000, full_phases=True)

        # Probe 3: phase windows outside capture
        bad_outside = {
            "entry": {"confirmed": True, "start_ms": 900000.0, "end_ms": 901000.0, "confirmed_at_ms": 901000.0},
            "still": {"confirmed": True, "start_ms": 902000.0, "end_ms": 903000.0, "confirmed_at_ms": 903000.0},
            "exit": {"confirmed": True, "start_ms": 904000.0, "end_ms": 920000.0, "confirmed_at_ms": 920000.0},
        }
        rc, res = fx.TestR4BRealHumanRunner()._run_runner(base_rows, confirm=True, phases=bad_outside)
        self.assertNotEqual(rc, 0)
        self.assertEqual(res["status"], "fail")
        self.assertEqual(res["verdict"], "PHASE_WINDOW_OUTSIDE_CAPTURE_REJECTED")

        # Probe 4: zero-length phases and missing confirmed_at_ms
        bad_zero = {
            "entry": {"confirmed": True, "start_ms": 1000.0, "end_ms": 1000.0},
            "still": {"confirmed": True, "start_ms": 1000.0, "end_ms": 1000.0},
            "exit": {"confirmed": True, "start_ms": 1000.0, "end_ms": 1000.0},
        }
        rc, res = fx.TestR4BRealHumanRunner()._run_runner(base_rows, confirm=True, phases=bad_zero)
        self.assertNotEqual(rc, 0)
        self.assertEqual(res["status"], "fail")
        self.assertEqual(res["verdict"], "INVALID_PHASE_TIMESTAMPS_REJECTED")

        # Probe 5: missing position_ms
        rows_no_pms = copy.deepcopy(base_rows)
        for r in rows_no_pms:
            for t in r.get("targets", []):
                t.pop("position_ms", None)
        rc, res = fx.TestR4BRealHumanRunner()._run_runner(
            rows_no_pms, confirm=True, phases=fx._default_valid_phases()
        )
        self.assertNotEqual(rc, 0)
        self.assertEqual(res["status"], "fail")
        self.assertEqual(res["verdict"], "MISSING_POSITION_TIMESTAMP_REJECTED")

        # Probe 6: old advancing position_ms (lag > 6000ms)
        rows_old_pms = copy.deepcopy(base_rows)
        for idx, r in enumerate(rows_old_pms):
            r["sample_ms"] += 100000
            for t in r.get("targets", []):
                t["position_ms"] = idx + 1
        shifted_phases = {
            "entry": {"confirmed": True, "start_ms": 100000.0, "end_ms": 102000.0, "confirmed_at_ms": 102000.0},
            "still": {"confirmed": True, "start_ms": 102000.0, "end_ms": 104800.0, "confirmed_at_ms": 104800.0},
            "exit": {"confirmed": True, "start_ms": 105000.0, "end_ms": 117000.0, "confirmed_at_ms": 117000.0},
        }
        rc, res = fx.TestR4BRealHumanRunner()._run_runner(rows_old_pms, confirm=True, phases=shifted_phases)
        self.assertNotEqual(rc, 0)
        self.assertEqual(res["status"], "fail")
        self.assertEqual(res["verdict"], "STALE_POSITION_TIMESTAMP_REJECTED")

        # Probe 7: duplicate exit sequence
        rows_dup_exit = copy.deepcopy(base_rows)
        for r in rows_dup_exit[-5:]:
            r["source_seq"] = rows_dup_exit[-6]["source_seq"]
        rc, res = fx.TestR4BRealHumanRunner()._run_runner(
            rows_dup_exit, confirm=True, phases=fx._default_valid_phases()
        )
        self.assertNotEqual(rc, 0)
        self.assertEqual(res["status"], "fail")
        self.assertEqual(res["verdict"], "STALE_EXIT_SEQUENCE_REJECTED")

    def test_clock_domain_mismatch_and_wrong_phase_behavior_and_identity_and_cleanup(self):
        """Negative tests for mixed clock domains, wrong phase telemetry behavior,
        missing device_id/capabilities/boundary, foreign phase file, and exception cleanup."""
        base_rows = fx._base_human_records(n=30, exit_frames=5, exit_interval_ms=3000, full_phases=True)
        inst = dict(fx.TestR4BRealHumanRunner.INST)

        # 1. Mixed clock domain (epoch seconds in phases vs device sample_ms)
        epoch_phases = {
            "entry": {"confirmed": True, "start_ms": 1761800000000.0, "end_ms": 1761800002000.0, "confirmed_at_ms": 1761800002000.0, "clock_domain": "host_wall_ms"},
            "still": {"confirmed": True, "start_ms": 2000.0, "end_ms": 4800.0, "confirmed_at_ms": 4800.0, "clock_domain": "device_sample_ms"},
            "exit": {"confirmed": True, "start_ms": 5000.0, "end_ms": 17000.0, "confirmed_at_ms": 17000.0, "clock_domain": "device_sample_ms"},
        }
        v, ok, _ = hj.judge_human_observation(
            base_rows, user_action_confirmed=True, expected_installation=inst,
            phases=epoch_phases, require_structured_phases=True
        )
        self.assertFalse(ok)
        self.assertEqual(v, "CLOCK_DOMAIN_MISMATCH_REJECTED")

        # 2. Wrong phase segment: entry has zero motion while still has motion
        swapped_rows = copy.deepcopy(base_rows)
        for i in range(12):
            swapped_rows[i]["targets"][0]["local_cm"] = [10.0, 10.0]
            swapped_rows[i]["targets"][0]["room_cm"] = [10.0, 10.0]
            swapped_rows[i]["targets"][0]["boundary"] = "inside"
        for i in range(12, 25):
            x_move = float(i - 12) * 6.0
            swapped_rows[i]["targets"][0]["local_cm"] = [x_move, 10.0]
            swapped_rows[i]["targets"][0]["room_cm"] = [x_move, 10.0]
            swapped_rows[i]["targets"][0]["boundary"] = "inside" if i < 18 else "outside"
        v, ok, _ = hj.judge_human_observation(
            swapped_rows, user_action_confirmed=True, expected_installation=inst,
            phases=fx._default_valid_phases(), require_structured_phases=True
        )
        self.assertFalse(ok)
        self.assertEqual(v, "ENTRY_PHASE_MOTION_INSUFFICIENT")

        # 3. Missing device_id when device_info is provided
        v, ok, _ = hj.judge_human_observation({
            "telemetry_records": base_rows,
            "user_action_confirmed": True,
            "expected_installation": inst,
            "phases": fx._default_valid_phases(),
            "require_structured_phases": True,
            "device_info": {"device_id": ""},
        })
        self.assertFalse(ok)
        self.assertEqual(v, "MISSING_DEVICE_IDENTITY_REJECTED")

        # 4. Incomplete capabilities when capabilities provided without position.xy
        v, ok, _ = hj.judge_human_observation({
            "telemetry_records": base_rows,
            "user_action_confirmed": True,
            "expected_installation": inst,
            "phases": fx._default_valid_phases(),
            "require_structured_phases": True,
            "device_info": {"device_id": "r60-01"},
            "capabilities": {"items": [{"id": "presence"}]},
        })
        self.assertFalse(ok)
        self.assertEqual(v, "INCOMPLETE_CAPABILITIES_REJECTED")

        # 5. Foreign phase confirmation bound to another device_id
        foreign_phases = copy.deepcopy(fx._default_valid_phases())
        foreign_phases["entry"]["device_id"] = "other-board-99"
        v, ok, _ = hj.judge_human_observation({
            "telemetry_records": base_rows,
            "user_action_confirmed": True,
            "expected_installation": inst,
            "phases": foreign_phases,
            "require_structured_phases": True,
            "device_info": {"device_id": "r60-01"},
        })
        self.assertFalse(ok)
        self.assertEqual(v, "FOREIGN_PHASE_CONFIRMATION_REJECTED")

        # 6. Runner exception cleanup: if judge_human_observation raises RuntimeError,
        # human_observe_runner still closes evidence & client, writes fail result+manifest,
        # and TemporaryDirectory cleans up on Windows without WinError 32.
        with tempfile.TemporaryDirectory(prefix="r7-hor-exc-") as td:
            out_path = Path(td) / "exc.jsonl"
            res_path = Path(td) / "exc.result.json"
            man_path = Path(td) / "exc.manifest.json"
            closed = {"client": False}

            class ExcClient:
                boot_id = "e" * 32
                session_id = 2

                def call(self, name, payload=None, **kw):
                    if name == "DEVICE_INFO":
                        return {"ok": True, "result": {"device_id": "r60-exc", "model": "R60ABD1"}}
                    if name == "CAPABILITIES_LIST":
                        return {"ok": True, "result": {"items": [{"id": "presence"}, {"id": "position.xy"}]}}
                    return {"ok": True, "result": {}}

                def ping(self):
                    return {"ok": True, "result": {}}

                def drain_events(self, duration_ms):
                    return []

                def close(self):
                    closed["client"] = True

            clock = [0.0]
            def tick():
                clock[0] += 5.0
                return clock[0]

            argv = ["human_observe_runner", "--port", "COM9", "--seconds", "1", "--out", str(out_path)]
            with fx._NoRealIO(), \
                 mock.patch.object(sys, "argv", argv), \
                 mock.patch.object(hor, "robust_connect", return_value=ExcClient()), \
                 mock.patch.object(hor.run_g2, "read_all_config", return_value=(inst, "1")), \
                 mock.patch.object(hj, "judge_human_observation", side_effect=RuntimeError("boom")), \
                 mock.patch.object(hor, "beep_phase"), \
                 mock.patch.object(hor, "beep_complete"), \
                 mock.patch.object(hor.winsound, "Beep", return_value=None), \
                 mock.patch("builtins.print"), \
                 mock.patch.object(hor.time, "sleep", return_value=None), \
                 mock.patch.object(hor.time, "time", side_effect=tick), \
                 mock.patch.object(hor.time, "monotonic", side_effect=tick):
                rc = hor.main()

            self.assertEqual(rc, 1)
            self.assertTrue(closed["client"])
            self.assertTrue(res_path.is_file())
            self.assertTrue(man_path.is_file())
            res_data = json.loads(res_path.read_text(encoding="utf-8"))
            self.assertEqual(res_data["status"], "fail")
            self.assertEqual(res_data["verdict"], "JUDGE_EXCEPTION_REJECTED")
            # Explicitly unlink raw file to prove no open handle lock on Windows
            out_path.unlink()


class TestR702FirmwareAlignedConfigValidation(unittest.TestCase):
    """R7-02: install.yaw_deg 0.1 deg step, pitch/roll 0.5 deg step,
    areas.definitions max 12 vertices, geometry.boundary_cm max 64 vertices."""

    def test_audit_probes_yaw_0_1_and_area_13_vertices(self):
        """Probes 8 & 9: yaw_deg=0.1 passes; 13-vertex area fails."""
        rec_yaw = fx._base_power_record()
        rec_yaw["config_target"] = dict(rec_yaw["config_target"], **{"install.yaw_deg": 0.1})
        rec_yaw["config_recovered"] = dict(rec_yaw["config_target"])
        v, ok, _ = hj.judge_power_cut_cycle(rec_yaw)
        self.assertTrue(ok, v)
        self.assertEqual(v, "COMMITTED_NEW_SAFE")

        rec_area13 = fx._base_power_record()
        pts13 = _regular_polygon(13)
        area13 = [{"slot": 0, "name": "a13", "enabled": True, "points_cm": pts13}]
        rec_area13["config_target"] = dict(rec_area13["config_target"], **{"areas.definitions": area13})
        rec_area13["config_recovered"] = dict(rec_area13["config_target"])
        v13, ok13, _ = hj.judge_power_cut_cycle(rec_area13)
        self.assertFalse(ok13)
        self.assertEqual(v13, "INCOMPLETE_CONFIG_REJECTED")

    def test_angle_steps_and_polygon_vertex_limits(self):
        """Verify yaw 0.1 vs 0.15, pitch/roll 0.5 vs 0.1, area 12 vs 13 (enabled & disabled),
        and boundary 64 vs 65."""
        # yaw 0.15 rejected
        rec = fx._base_power_record()
        rec["config_target"] = dict(rec["config_target"], **{"install.yaw_deg": 0.15})
        rec["config_recovered"] = dict(rec["config_target"])
        v, ok, _ = hj.judge_power_cut_cycle(rec)
        self.assertFalse(ok)
        self.assertEqual(v, "INCOMPLETE_CONFIG_REJECTED")

        # pitch 0.1 rejected, 0.5 accepted
        rec_p = fx._base_power_record()
        rec_p["config_target"] = dict(rec_p["config_target"], **{"install.pitch_deg": 0.1})
        rec_p["config_recovered"] = dict(rec_p["config_target"])
        v, ok, _ = hj.judge_power_cut_cycle(rec_p)
        self.assertFalse(ok)

        rec_p["config_target"] = dict(rec_p["config_target"], **{"install.pitch_deg": 0.5})
        rec_p["config_recovered"] = dict(rec_p["config_target"])
        v, ok, _ = hj.judge_power_cut_cycle(rec_p)
        self.assertTrue(ok)

        # roll 0.1 rejected, 0.5 accepted
        rec_r = fx._base_power_record()
        rec_r["config_target"] = dict(rec_r["config_target"], **{"install.roll_deg": 0.1})
        rec_r["config_recovered"] = dict(rec_r["config_target"])
        v, ok, _ = hj.judge_power_cut_cycle(rec_r)
        self.assertFalse(ok)

        rec_r["config_target"] = dict(rec_r["config_target"], **{"install.roll_deg": 0.5})
        rec_r["config_recovered"] = dict(rec_r["config_target"])
        v, ok, _ = hj.judge_power_cut_cycle(rec_r)
        self.assertTrue(ok)

        # Area 12 vertices accepted
        rec_a12 = fx._base_power_record()
        pts12 = _regular_polygon(12)
        area12 = [{"slot": 0, "name": "a12", "enabled": True, "points_cm": pts12}]
        rec_a12["config_target"] = dict(rec_a12["config_target"], **{"areas.definitions": area12})
        rec_a12["config_recovered"] = dict(rec_a12["config_target"])
        v, ok, _ = hj.judge_power_cut_cycle(rec_a12)
        self.assertTrue(ok, v)

        # Disabled area with 13 vertices rejected; disabled area with [] accepted
        rec_dis13 = fx._base_power_record()
        area_dis13 = [{"slot": 0, "name": "d13", "enabled": False, "points_cm": _regular_polygon(13)}]
        rec_dis13["config_target"] = dict(rec_dis13["config_target"], **{"areas.definitions": area_dis13})
        rec_dis13["config_recovered"] = dict(rec_dis13["config_target"])
        v, ok, _ = hj.judge_power_cut_cycle(rec_dis13)
        self.assertFalse(ok)

        rec_dis0 = fx._base_power_record()
        area_dis0 = [{"slot": 0, "name": "d0", "enabled": False, "points_cm": []}]
        rec_dis0["config_target"] = dict(rec_dis0["config_target"], **{"areas.definitions": area_dis0})
        rec_dis0["config_recovered"] = dict(rec_dis0["config_target"])
        v, ok, _ = hj.judge_power_cut_cycle(rec_dis0)
        self.assertTrue(ok, v)

        # Boundary 64 vertices accepted, 65 vertices rejected
        rec_b64 = fx._base_power_record()
        pts64 = _regular_polygon(64, radius_cm=200.0)
        rec_b64["config_target"] = dict(rec_b64["config_target"], **{"geometry.boundary_cm": pts64})
        rec_b64["config_recovered"] = dict(rec_b64["config_target"])
        v, ok, _ = hj.judge_power_cut_cycle(rec_b64)
        self.assertTrue(ok, v)

        rec_b65 = fx._base_power_record()
        pts65 = _regular_polygon(65, radius_cm=200.0)
        rec_b65["config_target"] = dict(rec_b65["config_target"], **{"geometry.boundary_cm": pts65})
        rec_b65["config_recovered"] = dict(rec_b65["config_target"])
        v, ok, _ = hj.judge_power_cut_cycle(rec_b65)
        self.assertFalse(ok)
        self.assertEqual(v, "INCOMPLETE_CONFIG_REJECTED")

    def test_power_and_usb_runners_accept_yaw_0_1_and_12_vertex_area(self):
        """Both judge_power_cut_cycle and judge_usb_unplug_cycle accept
        yaw_deg=0.1 and a 12-vertex area in readback."""
        base_rec = fx._base_power_record()
        cfg = dict(base_rec["config_target"])
        cfg["install.yaw_deg"] = 0.1
        cfg["areas.definitions"] = [
            {"slot": 0, "name": "zone12", "enabled": True, "points_cm": _regular_polygon(12)}
        ]
        power_rec = fx._base_power_record(config_target=cfg, config_recovered=dict(cfg))
        v_p, ok_p, _ = hj.judge_power_cut_cycle(power_rec)
        self.assertTrue(ok_p, v_p)
        self.assertEqual(v_p, "COMMITTED_NEW_SAFE")

        usb_rec = {
            "target_port": "COM9",
            "port": "COM9",
            "disconnect_observed": True,
            "reconnect_observed": True,
            "device_id_before": "r60-aabbccdd",
            "device_id_after": "r60-aabbccdd",
            "boot_before": "a" * 32,
            "boot_after": "b" * 32,
            "ping_after": {"uptime_ms": 1500},
            "rev_before": "2",
            "rev_after": "2",
            "config_before": cfg,
            "config_after": dict(cfg),
        }
        v_u, ok_u, _ = hj.judge_usb_unplug_cycle(usb_rec)
        self.assertTrue(ok_u, v_u)
        self.assertEqual(v_u, "UNPLUG_RECOVERED_SAFE")


class TestR703SupersededStructuredMetadataAndDuration(unittest.TestCase):
    """R7-03: build_evidence_index.py requires complete structured metadata
    (device_id, firmware_verified, tool_version, scenario/mode, and positive
    actual duration coverage) on BOTH runs before admitting superseded."""

    def test_audit_probe_missing_identity_firmware_tool_duration_rejected(self):
        """Probe 10: minimal runs without device_id, firmware_verified, tool_version,
        or duration_seconds are rejected as pending_review."""
        with tempfile.TemporaryDirectory(prefix="r7-idx-probe10-") as td:
            ev = Path(td) / "ev"
            ev.mkdir()
            helper = fx.TestR1AEvidenceIndex()
            _, s_old = helper._write_run(ev, "g2-07-soak-idle-old", mode="idle")
            _, s_new = helper._write_run(ev, "g2-07-soak-idle-new", mode="idle")
            idx = bi.build_index(
                {"test": ev},
                Path(td) / "index.json",
                {
                    "g2-07-soak-idle-old": {
                        "accepted_status": "superseded",
                        "superseded_by": "g2-07-soak-idle-new",
                        "result_sha256": s_old,
                    },
                    "g2-07-soak-idle-new": {
                        "accepted_status": "pass",
                        "result_sha256": s_new,
                    },
                },
                bi.FIRMWARE_BATCHES,
                sources_snapshot={},
            )
            runs = {r["run_id"]: r for r in idx["runs"]}
            self.assertEqual(runs["g2-07-soak-idle-old"]["accepted_status"], "pending_review")
            self.assertIsNone(runs["g2-07-soak-idle-old"]["superseded_by"])

    def _stamp_actual(self, rp: Path, actual: float, ended: str | None = None) -> str:
        """R8-02: explicitly stamp measured coverage (+ consistent window) on
        a helper run and re-bind the manifest's result hash. Returns the new
        result sha. The shared helper never fabricates actual fields."""
        d = json.loads(rp.read_text(encoding="utf-8"))
        d["actual_duration_seconds"] = actual
        d["judge_input"]["actual_duration_seconds"] = actual
        if ended is not None:
            d["ended"] = ended
        rp.write_text(json.dumps(d), encoding="utf-8")
        mp = rp.with_name(rp.name.replace(".result.json", ".manifest.json"))
        m = json.loads(mp.read_text(encoding="utf-8"))
        m["result_sha256"] = hashlib.sha256(rp.read_bytes()).hexdigest()
        if ended is not None:
            m["ended"] = ended
        mp.write_text(json.dumps(m), encoding="utf-8")
        return hashlib.sha256(rp.read_bytes()).hexdigest()

    def test_single_missing_field_and_short_actual_duration_and_shuffled_order(self):
        """Missing any single required metadata field on either old or new run,
        or verifiable actual coverage below the superseded run (requested
        seconds never vouch - R8-02), must downgrade superseded to
        pending_review."""
        helper = fx.TestR1AEvidenceIndex()

        for missing_field in ("device_id", "firmware", "tool_version", "scenario", "duration"):
            with tempfile.TemporaryDirectory(prefix=f"r7-idx-{missing_field}-") as td:
                ev = Path(td) / "ev"
                ev.mkdir()
                rp_old, _ = helper._write_run(ev, "soak-old", mode="idle", complete_meta=True, duration_seconds=60)
                rp_new, _ = helper._write_run(ev, "soak-new", mode="idle", complete_meta=True, duration_seconds=7200)
                # R8-02 baseline: both runs carry measured actual coverage
                # consistent with their windows (60s window -> 60s actual;
                # new window widened to 7200s -> 7200s actual).
                s_old = self._stamp_actual(rp_old, 60)
                self._stamp_actual(rp_new, 7200, ended="2026-10-28T14:00:00+0000")

                # Mutate the new run to remove the tested field and re-bind manifest/review sha
                d_new = json.loads(rp_new.read_text(encoding="utf-8"))
                man_new_path = ev / "soak-new.manifest.json"
                man_new = json.loads(man_new_path.read_text(encoding="utf-8"))

                if missing_field == "device_id":
                    d_new.pop("device_id", None)
                    d_new.pop("board_id", None)
                elif missing_field == "firmware":
                    man_new["flashed_image_sha256"] = "unverified"
                elif missing_field == "tool_version":
                    d_new["judge_input"].pop("tool_version", None)
                elif missing_field == "scenario":
                    d_new.pop("scenario", None)
                    d_new["judge_input"].pop("scenario", None)
                    d_new["judge_input"].pop("mode", None)
                elif missing_field == "duration":
                    # R8-02: the verifiable fields are actual/observed values;
                    # removing them (requested seconds cannot vouch) must
                    # reject the replacement.
                    d_new.pop("actual_duration_seconds", None)
                    d_new["judge_input"].pop("actual_duration_seconds", None)
                    d_new.pop("monotonic_span_s", None)
                    d_new["judge_input"].pop("monotonic_span_s", None)

                rp_new.write_text(json.dumps(d_new), encoding="utf-8")
                s_new = hashlib.sha256(rp_new.read_bytes()).hexdigest()
                man_new["result_sha256"] = s_new
                man_new_path.write_text(json.dumps(man_new), encoding="utf-8")

                idx = bi.build_index(
                    {"test": ev},
                    Path(td) / "index.json",
                    {
                        "soak-old": {"accepted_status": "superseded", "superseded_by": "soak-new", "result_sha256": s_old},
                        "soak-new": {"accepted_status": "pass", "result_sha256": s_new},
                    },
                    bi.FIRMWARE_BATCHES,
                    sources_snapshot={},
                )
                runs = {r["run_id"]: r for r in idx["runs"]}
                self.assertEqual(
                    runs["soak-old"]["accepted_status"],
                    "pending_review",
                    f"Field {missing_field} missing on target should reject supersede: {runs['soak-old']}",
                )
                self.assertIsNone(runs["soak-old"]["superseded_by"])

        # requested_seconds=7200 with actual_duration_seconds=30 (< old 60s):
        # the replacement window is made consistent with its own (shorter)
        # actual coverage, so the rejection comes from the duration
        # comparison itself, not a window conflict.
        with tempfile.TemporaryDirectory(prefix="r7-idx-actual-dur-") as td:
            ev = Path(td) / "ev"
            ev.mkdir()
            rp_old, _ = helper._write_run(ev, "soak-old", mode="idle", complete_meta=True, duration_seconds=60)
            rp_new, _ = helper._write_run(ev, "soak-new", mode="idle", complete_meta=True, duration_seconds=7200)
            s_old = self._stamp_actual(rp_old, 60)
            self._stamp_actual(rp_new, 30, ended="2026-10-28T12:00:30+0000")
            d_new = json.loads(rp_new.read_text(encoding="utf-8"))
            d_new["requested_seconds"] = 7200
            rp_new.write_text(json.dumps(d_new), encoding="utf-8")
            s_new = hashlib.sha256(rp_new.read_bytes()).hexdigest()
            man_new_path = ev / "soak-new.manifest.json"
            man_new = json.loads(man_new_path.read_text(encoding="utf-8"))
            man_new["result_sha256"] = s_new
            man_new_path.write_text(json.dumps(man_new), encoding="utf-8")

            idx = bi.build_index(
                {"test": ev},
                Path(td) / "index.json",
                {
                    "soak-old": {"accepted_status": "superseded", "superseded_by": "soak-new", "result_sha256": s_old},
                    "soak-new": {"accepted_status": "pass", "result_sha256": s_new},
                },
                bi.FIRMWARE_BATCHES,
                sources_snapshot={},
            )
            runs = {r["run_id"]: r for r in idx["runs"]}
            self.assertEqual(runs["soak-old"]["accepted_status"], "pending_review")
            self.assertIn("is shorter than superseded run", runs["soak-old"]["review_note"])


class TestR704OutputPlanPreIOReservation(unittest.TestCase):
    """R7-04: OutputPlan preflights and atomically reserves all triplets
    (including second legs of connected, config, provision, jobs, combined)
    before secrets/serial I/O, and aborts on race before Client connect."""

    def test_audit_probe_connected_second_leg_collision(self):
        """Probe 11: pre-existing g2-connected-r2-FIXED.result.json aborts before secrets or serial."""
        with tempfile.TemporaryDirectory(prefix="r7-conn-r2-") as td:
            ev = Path(td)
            second = ev / "g2-connected-r2-FIXED.result.json"
            second.write_text('{"foreign": true}', encoding="utf-8")
            calls = {"secrets": 0, "client": 0}

            def bad_secrets(*a, **k):
                calls["secrets"] += 1
                raise AssertionError("secrets called before connected-r2 collision check")

            def bad_client(*a, **k):
                calls["client"] += 1
                raise AssertionError("Client called before connected-r2 collision check")

            with mock.patch.object(run_g2, "EVIDENCE_DIR", ev), \
                 mock.patch.object(run_g2.time, "strftime", return_value="FIXED"), \
                 mock.patch.object(run_g2, "load_secrets", side_effect=bad_secrets), \
                 mock.patch.object(run_g2.mwcp, "Client", side_effect=bad_client), \
                 mock.patch.object(sys, "argv", ["run_g2.py", "connected", "--port", "COM99", "--allow-write"]):
                rc = run_g2.main()

            self.assertNotEqual(rc, 0)
            self.assertEqual(calls, {"secrets": 0, "client": 0})
            self.assertEqual(second.read_text(encoding="utf-8"), '{"foreign": true}')

    def test_audit_probe_preflight_race_without_reservation(self):
        """Probe 12: if a foreign result file replaces the reservation during load_secrets,
        connect() detects the race BEFORE mwcp.Client is invoked."""
        with tempfile.TemporaryDirectory(prefix="r7-race-") as td:
            ev = Path(td)
            out = ev / "race.jsonl"
            res = ev / "race.result.json"
            calls = {"secrets": 0, "client": 0}

            def racing_secrets(*a, **k):
                calls["secrets"] += 1
                res.write_text('{"foreign_race": true}', encoding="utf-8")
                return {}, []

            def bad_client(*a, **k):
                calls["client"] += 1
                raise AssertionError("Client called despite result path not reserved before I/O")

            with mock.patch.object(run_g2, "EVIDENCE_DIR", ev), \
                 mock.patch.object(run_g2, "load_secrets", side_effect=racing_secrets), \
                 mock.patch.object(run_g2.mwcp, "Client", side_effect=bad_client), \
                 mock.patch.object(sys, "argv", ["run_g2.py", "probe", "--port", "COM99", "--out", str(out)]):
                rc = run_g2.main()

            self.assertNotEqual(rc, 0)
            self.assertEqual(calls["client"], 0)
            self.assertEqual(res.read_text(encoding="utf-8"), '{"foreign_race": true}')
            self.assertFalse(out.exists())

    def test_multi_leg_commands_and_multi_dot_out_collision_rejected_pre_io(self):
        """All multi-leg commands (connected, config, provision, jobs, combined)
        reject pre-existing leg-2 raw/result/manifest on both default and multi-dot --out paths."""
        cases = [
            ("connected", None, "g2-connected-r2-FIXED.manifest.json"),
            ("config", None, "g2-04-config-r2-FIXED.result.json"),
            ("provision", None, "g2-06-provision-r2-FIXED.jsonl"),
            ("jobs", None, "g2-05-jobs-r2-FIXED.result.json"),
            ("combined", None, "g2-combined-r2-FIXED.manifest.json"),
            ("connected", "my.multi.dot.jsonl", "my.multi.dot-r2.result.json"),
        ]
        for cmd, custom_out, conflict_name in cases:
            with tempfile.TemporaryDirectory(prefix=f"r7-mleg-{cmd}-") as td:
                ev = Path(td)
                conflict = ev / conflict_name
                conflict.write_text('{"keep": 1}', encoding="utf-8")
                calls = {"secrets": 0, "client": 0}

                argv = ["run_g2.py", cmd, "--port", "COM99"]
                if custom_out:
                    argv.extend(["--out", str(ev / custom_out)])

                with mock.patch.object(run_g2, "EVIDENCE_DIR", ev), \
                     mock.patch.object(run_g2.time, "strftime", return_value="FIXED"), \
                     mock.patch.object(run_g2, "load_secrets", side_effect=lambda *a, **k: (calls.__setitem__("secrets", calls["secrets"] + 1), ({}, []))[1]), \
                     mock.patch.object(run_g2.mwcp, "Client", side_effect=lambda *a, **k: calls.__setitem__("client", calls["client"] + 1)), \
                     mock.patch.object(sys, "argv", argv):
                    rc = run_g2.main()

                self.assertNotEqual(rc, 0, f"{cmd} ({conflict_name}) should fail pre-IO")
                self.assertEqual(calls, {"secrets": 0, "client": 0})
                self.assertEqual(conflict.read_text(encoding="utf-8"), '{"keep": 1}')


if __name__ == "__main__":
    unittest.main()
