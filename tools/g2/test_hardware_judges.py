#!/usr/bin/env python3
"""Comprehensive test suite for G2 hardware evaluation judges (G2-HW-R3, G2-HW-R4).

Verifies rejection of all counterexamples from review.py and audit.json,
plus single-variable edge cases and valid positive controls.
"""

from __future__ import annotations

import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import hardware_judges as hj


class TestPowerCutJudge(unittest.TestCase):
    def setUp(self):
        self.base_cfg = {
            "install.x_cm": 10.0,
            "install.y_cm": 0.0,
            "install.z_cm": 150.0,
            "install.yaw_deg": 0.0,
            "install.pitch_deg": 0.0,
            "install.roll_deg": 0.0,
            "geometry.boundary_cm": [[-200, 0], [200, 0], [200, 500], [-200, 500]],
            "areas.definitions": []
        }
        self.target_cfg = {
            "install.x_cm": 50.0,
            "install.y_cm": 10.0,
            "install.z_cm": 150.0,
            "install.yaw_deg": 15.0,
            "install.pitch_deg": 0.0,
            "install.roll_deg": 0.0,
            "geometry.boundary_cm": [[-300, 0], [300, 0], [300, 600], [-300, 600]],
            "areas.definitions": []
        }
        self.device_id = "dev-r60abd1-test"
        self.op_id = "11111111-1111-4111-8111-111111111111"

    def test_review_counterexample_rejected(self):
        """Must reject review.py counterexample: power_no_disconnect_wrong_revision_after_persisted_success."""
        record = {
            "target_port": "COM9",
            "port": "COM9",
            "device_id_before": self.device_id,
            "device_id_after": self.device_id,
            "disconnect_observed": False,  # No disconnect!
            "reconnect_observed": True,
            "boot_before": "fixture-old",
            "boot_after": "fixture-new",
            "rev_before": "5",
            "rev_target": "6",
            "rev_recovered": "999",  # Wrong revision!
            "config_before": self.base_cfg,
            "config_target": self.target_cfg,
            "config_recovered": self.base_cfg,
            "op_id": self.op_id,
            "commit_response": {"ok": True, "result": {"op_id": self.op_id, "persisted": True, "revision": "6", "restart_required": False}},
        }
        verdict, passed, detail = hj.judge_power_cut_cycle(record)
        self.assertFalse(passed)
        self.assertEqual(verdict, "NO_DISCONNECT_REJECTED")

    def test_persisted_success_with_old_config_rejected(self):
        """Even with disconnect, if COMMIT confirmed persisted=True, reverting to old config is data loss!"""
        record = {
            "target_port": "COM9",
            "port": "COM9",
            "device_id_before": self.device_id,
            "device_id_after": self.device_id,
            "disconnect_observed": True,
            "reconnect_observed": True,
            "boot_before": "fixture-old",
            "boot_after": "fixture-new",
            "rev_before": "5",
            "rev_target": "6",
            "rev_recovered": "5",
            "config_before": self.base_cfg,
            "config_target": self.target_cfg,
            "config_recovered": self.base_cfg,
            "op_id": self.op_id,
            "commit_response": {"ok": True, "result": {"op_id": self.op_id, "persisted": True, "revision": "6", "restart_required": False}},
        }
        verdict, passed, detail = hj.judge_power_cut_cycle(record)
        self.assertFalse(passed)
        self.assertEqual(verdict, "PERSISTENCE_LOST_FAIL")

    def test_old_config_with_wrong_revision_rejected(self):
        """Interrupted commit: old config preserved, but revision changed -> reject!"""
        record = {
            "target_port": "COM9",
            "port": "COM9",
            "device_id_before": self.device_id,
            "device_id_after": self.device_id,
            "disconnect_observed": True,
            "reconnect_observed": True,
            "boot_before": "fixture-old",
            "boot_after": "fixture-new",
            "rev_before": "5",
            "rev_target": "6",
            "rev_recovered": "999",
            "config_before": self.base_cfg,
            "config_target": self.target_cfg,
            "config_recovered": self.base_cfg,
            "op_id": self.op_id,
            "commit_response": None,
        }
        verdict, passed, detail = hj.judge_power_cut_cycle(record)
        self.assertFalse(passed)
        self.assertEqual(verdict, "REVISION_MISMATCH_FAIL")

    def test_identical_target_rejected(self):
        """Target config identical to before does not test atomic switching."""
        record = {
            "target_port": "COM9",
            "port": "COM9",
            "device_id_before": self.device_id,
            "device_id_after": self.device_id,
            "disconnect_observed": True,
            "reconnect_observed": True,
            "boot_before": "fixture-old",
            "boot_after": "fixture-new",
            "rev_before": "5",
            "rev_target": "6",
            "rev_recovered": "6",
            "config_before": self.base_cfg,
            "config_target": self.base_cfg,  # Identical!
            "config_recovered": self.base_cfg,
            "op_id": self.op_id,
            "commit_response": None,
        }
        verdict, passed, detail = hj.judge_power_cut_cycle(record)
        self.assertFalse(passed)
        self.assertEqual(verdict, "IDENTICAL_TARGET_REJECTED")

    def test_no_reboot_rejected(self):
        """Boot ID unchanged -> reject."""
        record = {
            "target_port": "COM9",
            "port": "COM9",
            "device_id_before": self.device_id,
            "device_id_after": self.device_id,
            "disconnect_observed": True,
            "reconnect_observed": True,
            "boot_before": "fixture-same",
            "boot_after": "fixture-same",
            "rev_before": "5",
            "rev_target": "6",
            "rev_recovered": "6",
            "config_before": self.base_cfg,
            "config_target": self.target_cfg,
            "config_recovered": self.target_cfg,
            "op_id": self.op_id,
            "commit_response": None,
        }
        verdict, passed, detail = hj.judge_power_cut_cycle(record)
        self.assertFalse(passed)
        self.assertEqual(verdict, "NO_REBOOT_REJECTED")

    def test_corrupted_config_rejected(self):
        """Recovered config with corrupted or mixed fields -> reject."""
        corrupted_cfg = dict(self.base_cfg)
        corrupted_cfg["install.x_cm"] = 55.0
        record = {
            "target_port": "COM9",
            "port": "COM9",
            "device_id_before": self.device_id,
            "device_id_after": self.device_id,
            "disconnect_observed": True,
            "reconnect_observed": True,
            "boot_before": "fixture-old",
            "boot_after": "fixture-new",
            "rev_before": "5",
            "rev_target": "6",
            "rev_recovered": "6",
            "config_before": self.base_cfg,
            "config_target": self.target_cfg,
            "config_recovered": corrupted_cfg,
            "op_id": self.op_id,
            "commit_response": None,
        }
        verdict, passed, detail = hj.judge_power_cut_cycle(record)
        self.assertFalse(passed)
        self.assertEqual(verdict, "CORRUPTED_FAIL")

    def test_positive_rollback_safe(self):
        """Valid rollback when power cut interrupts write: old config and old revision intact."""
        record = {
            "target_port": "COM9",
            "port": "COM9",
            "device_id_before": self.device_id,
            "device_id_after": self.device_id,
            "disconnect_observed": True,
            "reconnect_observed": True,
            "boot_before": "fixture-old",
            "boot_after": "fixture-new",
            "rev_before": "5",
            "rev_target": "6",
            "rev_recovered": "5",
            "config_before": self.base_cfg,
            "config_target": self.target_cfg,
            "config_recovered": self.base_cfg,
            "op_id": self.op_id,
            "commit_response": None,  # interrupted
        }
        verdict, passed, detail = hj.judge_power_cut_cycle(record)
        self.assertTrue(passed)
        self.assertEqual(verdict, "REVERTED_OLD_SAFE")

    def test_positive_commit_safe(self):
        """Valid atomic commit when write completed before cut: new config and target revision intact."""
        record = {
            "target_port": "COM9",
            "port": "COM9",
            "device_id_before": self.device_id,
            "device_id_after": self.device_id,
            "disconnect_observed": True,
            "reconnect_observed": True,
            "boot_before": "fixture-old",
            "boot_after": "fixture-new",
            "rev_before": "5",
            "rev_target": "6",
            "rev_recovered": "6",
            "config_before": self.base_cfg,
            "config_target": self.target_cfg,
            "config_recovered": self.target_cfg,
            "op_id": self.op_id,
            "commit_response": {"ok": True, "result": {"op_id": self.op_id, "persisted": True, "revision": "6", "restart_required": False}},
        }
        verdict, passed, detail = hj.judge_power_cut_cycle(record)
        self.assertTrue(passed)
        self.assertEqual(verdict, "COMMITTED_NEW_SAFE")


class TestUsbUnplugJudge(unittest.TestCase):
    def setUp(self):
        self.device_id = 'dev-r60abd1-test'
        self.base_cfg = {
            "install.x_cm": 10.0,
            "install.y_cm": 0.0,
            "install.z_cm": 150.0,
            "install.yaw_deg": 0.0,
            "install.pitch_deg": 0.0,
            "install.roll_deg": 0.0,
            "geometry.boundary_cm": [[-200, 0], [200, 0], [200, 500], [-200, 500]],
            "areas.definitions": [],
        }

    def test_review_counterexample_rejected(self):
        """Must reject review.py counterexample: usb_no_disconnect_arbitrary_eight_fields."""
        record = {
            "target_port": "COM9",
            "port": "COM9",
            "device_id_before": self.device_id,
            "device_id_after": self.device_id,
            "disconnect_observed": False,  # No disconnect!
            "reconnect_observed": True,
            "boot_before": "fixture-old",
            "boot_after": "fixture-new",
            "session_before": 1,
            "session_after": 1,
            "ping_after": {"uptime_ms": 200},
            "config_before": self.base_cfg,
            "config_after": {f"junk{i}": i for i in range(8)},  # Arbitrary junk fields!
            "rev_before": "5",
            "rev_after": "999",  # Mutated revision!
        }
        verdict, passed, detail = hj.judge_usb_unplug_cycle(record)
        self.assertFalse(passed)
        self.assertEqual(verdict, "NO_DISCONNECT_REJECTED")

    def test_arbitrary_fields_rejected_even_with_disconnect(self):
        """Even if disconnect was detected, arbitrary junk fields must be rejected."""
        record = {
            "target_port": "COM9",
            "port": "COM9",
            "device_id_before": self.device_id,
            "device_id_after": self.device_id,
            "disconnect_observed": True,
            "reconnect_observed": True,
            "boot_before": "fixture-old",
            "boot_after": "fixture-new",
            "session_before": 1,
            "session_after": 2,
            "ping_after": {"uptime_ms": 200},
            "config_before": self.base_cfg,
            "config_after": {f"junk{i}": i for i in range(8)},
            "rev_before": "5",
            "rev_after": "5",
        }
        verdict, passed, detail = hj.judge_usb_unplug_cycle(record)
        self.assertFalse(passed)
        self.assertEqual(verdict, "CONFIG_MUTATED_FAIL")

    def test_device_identity_mismatch_rejected(self):
        """Different board plugged into the same port -> reject."""
        record = {
            "target_port": "COM9",
            "port": "COM9",
            "device_id_before": self.device_id,
            "device_id_after": self.device_id,
            "disconnect_observed": True,
            "reconnect_observed": True,
            "boot_before": "fixture-old",
            "boot_after": "fixture-new",
            "session_before": 1,
            "session_after": 2,
            "ping_after": {"uptime_ms": 200},
            "config_before": self.base_cfg,
            "config_after": self.base_cfg,
            "rev_before": "5",
            "rev_after": "5",
            "device_id_before": "board-A-mac1",
            "device_id_after": "board-B-mac2",
        }
        verdict, passed, detail = hj.judge_usb_unplug_cycle(record)
        self.assertFalse(passed)
        self.assertEqual(verdict, "IDENTITY_MISMATCH")

    def test_positive_unplug_recovered_safe(self):
        """Clean physical unplug, full configuration strictly equal, rev matches, valid PING."""
        record = {
            "target_port": "COM9",
            "port": "COM9",
            "device_id_before": self.device_id,
            "device_id_after": self.device_id,
            "disconnect_observed": True,
            "reconnect_observed": True,
            "boot_before": "fixture-old",
            "boot_after": "fixture-new",
            "session_before": 1,
            "session_after": 2,
            "ping_after": {"uptime_ms": 200},
            "config_before": self.base_cfg,
            "config_after": self.base_cfg,
            "rev_before": "5",
            "rev_after": "5",
        }
        verdict, passed, detail = hj.judge_usb_unplug_cycle(record)
        self.assertTrue(passed)
        self.assertEqual(verdict, "UNPLUG_RECOVERED_SAFE")


class TestBackpressureJudge(unittest.TestCase):
    def test_review_counterexample_rejected(self):
        """Must reject review.py counterexample: backpressure_no_radar_frames_stale."""
        base = {"uptime_ms": 100, "last_radar_frame_ms": None, "radar_link": "stale",
                "counters": {"radar_frames": 0}}
        after = {"uptime_ms": 200, "last_radar_frame_ms": None, "radar_link": "stale",
                 "counters": {"radar_frames": 0}}
        rpc = {"ok": True}
        passed, checks = hj.judge_backpressure(base, after, rpc, "boot1", "boot1")
        self.assertFalse(passed)
        radar_check = next(c for c in checks if c["name"] == "radar_alive_after_backpressure")
        self.assertFalse(radar_check["pass"])

    def test_zero_frames_waiting_rejected(self):
        """Zero frames and waiting link -> reject."""
        base = {"uptime_ms": 100, "last_radar_frame_ms": None, "radar_link": "waiting",
                "counters": {"radar_frames": 0}}
        after = {"uptime_ms": 200, "last_radar_frame_ms": None, "radar_link": "waiting",
                 "counters": {"radar_frames": 0}}
        rpc = {"ok": True}
        passed, checks = hj.judge_backpressure(base, after, rpc, "boot1", "boot1")
        self.assertFalse(passed)

    def test_frozen_timestamp_rejected(self):
        """Timestamp did not advance -> reject."""
        base = {"uptime_ms": 100, "last_radar_frame_ms": 1000, "radar_link": "healthy",
                "counters": {"radar_frames": 5}}
        after = {"uptime_ms": 200, "last_radar_frame_ms": 1000, "radar_link": "healthy",
                 "counters": {"radar_frames": 5}}
        rpc = {"ok": True}
        passed, checks = hj.judge_backpressure(base, after, rpc, "boot1", "boot1")
        self.assertFalse(passed)

    def test_reboot_during_backpressure_rejected(self):
        """Boot ID changed during backpressure -> reject."""
        base = {"uptime_ms": 100, "last_radar_frame_ms": 1000, "radar_link": "healthy",
                "counters": {"radar_frames": 5}}
        after = {"uptime_ms": 50, "last_radar_frame_ms": 1500, "radar_link": "healthy",
                 "counters": {"radar_frames": 10}}
        rpc = {"ok": True}
        passed, checks = hj.judge_backpressure(base, after, rpc, "boot1", "boot2")
        self.assertFalse(passed)

    def test_positive_advancement_passed(self):
        """Valid continuous radar progression on same boot -> pass."""
        base = {"uptime_ms": 100, "last_radar_frame_ms": 1000, "radar_link": "healthy",
                "counters": {"radar_frames": 5}}
        after = {"uptime_ms": 200, "last_radar_frame_ms": 2500, "radar_link": "healthy",
                 "counters": {"radar_frames": 20}}
        rpc = {"ok": True}
        passed, checks = hj.judge_backpressure(base, after, rpc, "boot1", "boot1")
        self.assertTrue(passed)


class TestHumanObservationJudge(unittest.TestCase):
    def test_review_counterexample_rejected(self):
        """Must reject review.py counterexample: human_all_present_no_motion_or_exit."""
        # 60 frames all presence=True, identical static coordinates, no motion
        static_frame = {
            "presence": {"value": True, "quality": "valid", "sample_ms": 100},
            "targets": [{
                "id": 1,
                "local_cm": [50.0, 120.0, 0.0],
                "room_cm": [50.0, 120.0, 0.0],
                "boundary": "inside",
                "position_ms": 100,
                "position_quality": "valid",
                "speed_cm_s": None
            }],
            "source_seq": 1
        }
        records = [dict(static_frame, source_seq=i) for i in range(1, 65)]
        verdict, passed, summary = hj.judge_human_observation(records, user_action_confirmed=True)
        self.assertFalse(passed)
        self.assertEqual(verdict, "ALL_PRESENT_STATIC_INSUFFICIENT")

    def test_unparsed_coordinates_rejected(self):
        """Targets missing local_cm/room_cm -> reject."""
        bad_frame = {
            "presence": {"value": True, "quality": "valid"},
            "targets": [{"id": 1, "x_cm": 50.0, "y_cm": 120.0}],  # Wrong schema fields!
            "source_seq": 1
        }
        records = [dict(bad_frame, source_seq=i) for i in range(1, 65)]
        verdict, passed, summary = hj.judge_human_observation(records, user_action_confirmed=True)
        self.assertFalse(passed)
        self.assertEqual(verdict, "COORDINATES_MISSING")

    def test_positive_motion_and_presence_passed(self):
        """Multi-phase scenario: entry, spatial movement, boundary traversal, stationary retention, exit."""
        records = []
        # Phase 0: Empty room (no target, presence=False)
        for i in range(1, 10):
            records.append({
                "presence": {"value": False, "quality": "valid", "sample_ms": i * 200},
                "targets": [],
                "source_seq": i,
                "sample_ms": i * 200,
            })
        # Phase 1: Human enters and moves across boundary (coordinates shift from 30cm to 150cm)
        for i in range(10, 30):
            x = 30.0 + float(i - 10) * 6.0
            y = 100.0 + float(i - 10) * 2.0
            records.append({
                "presence": {"value": True, "quality": "valid", "sample_ms": i * 200},
                "targets": [{
                    "id": 1,
                    "local_cm": [x, y, 0.0],
                    "room_cm": [x + 5.0, y - 10.0, 200.0],
                    "boundary": "inside" if x < 90.0 else "outside",
                    "position_ms": i * 200,
                    "position_quality": "valid",
                    "speed_cm_s": None
                }],
                "source_seq": i,
                "sample_ms": i * 200,
            })
        # Phase 2: Stationary retention (>= 2000ms)
        for i in range(30, 45):
            records.append({
                "presence": {"value": True, "quality": "valid", "sample_ms": i * 200},
                "targets": [{
                    "id": 1,
                    "local_cm": [60.0, 120.0, 0.0],
                    "room_cm": [65.0, 110.0, 200.0],
                    "boundary": "inside",
                    "position_ms": i * 200,
                    "position_quality": "valid",
                    "speed_cm_s": None
                }],
                "source_seq": i,
                "sample_ms": i * 200,
            })
        # Phase 3: Human exits (presence=False) with sustained duration >= 10s
        for i in range(45, 70):
            t_ms = 9000 + (i - 45) * 500
            records.append({
                "presence": {"value": False, "quality": "valid", "sample_ms": t_ms},
                "targets": [],
                "source_seq": i,
                "sample_ms": t_ms,
            })
        exp_inst = {
            "install.x_cm": 5.0, "install.y_cm": -10.0, "install.z_cm": 200.0,
            "install.yaw_deg": 0.0, "install.pitch_deg": 0.0, "install.roll_deg": 0.0,
            "geometry.boundary_cm": [[0.0, 0.0], [94.0, 0.0], [94.0, 300.0], [0.0, 300.0]],
            "areas.definitions": [],
        }
        phases = {
            "entry": {"confirmed": True, "start_ms": 2000, "end_ms": 5800, "confirmed_at_ms": 5800},
            "still": {"confirmed": True, "start_ms": 6000, "end_ms": 8800, "confirmed_at_ms": 8800},
            "exit": {"confirmed": True, "start_ms": 9000, "end_ms": 21000, "confirmed_at_ms": 21000},
        }
        verdict, passed, summary = hj.judge_human_observation(
            records,
            user_action_confirmed=True,
            minimum_exit_duration_ms=10000,
            expected_installation=exp_inst,
            phases=phases,
            require_structured_phases=True,
        )
        self.assertTrue(passed, f"Expected pass, got {verdict}: {summary}")
        self.assertEqual(verdict, "HUMAN_OBSERVE_PASS")
        self.assertTrue(summary["presence_transition"])
        self.assertTrue(summary["spatial_motion"])


if __name__ == "__main__":
    unittest.main()
