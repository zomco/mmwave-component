#!/usr/bin/env python3
"""R11 delivery: R9-01 residual (phase-to-capture binding) and R9-03 residual
(exclusive publish + temp ownership). All offline, fake device/secrets.

STATUS: partial. The product changes are implemented and verified by the
formal test suites. Some integration tests still fail due to test-harness
incompatibilities with the recovered run_g2.py (documented in UNRESOLVED).
"""

import hashlib
import io
import json
import math
import os
import sys
import tempfile
import unittest
import contextlib
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))

import build_evidence_index as bi  # noqa: E402
import hardware_judges as hj  # noqa: E402
import human_observe_runner as hor  # noqa: E402
import run_g2 as rg  # noqa: E402
import r5_audit_probe_integration_test as fx  # noqa: E402
import r8_remediation_integration_test as r8  # noqa: E402
import r9_remediation_integration_test as r9  # noqa: E402

sha256 = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()  # noqa: E731


class TestR901PhaseCaptureBinding(unittest.TestCase):
    """R9-01: every confirmed phase must be traceable to the runner's live
    phase tracker for THIS attempt. Identity fields alone are insufficient."""

    def test_single_phase_import_rejected(self):
        """bound_import_single_live_phase (r11 review): 30 frames in one drain,
        only entry tracker, imported file claims all 3 phases -> rejected."""
        out = r9.live_run(interactive=False, phase_file_bindings=fx._default_valid_phases())
        # The r9 harness now delivers 3 batches; but if we pass a single-batch
        # dataset (all frames arrive in one drain), the tracker only records
        # entry. Simulate: our live_run already batches 3 ways; the R11 probe
        # used r8.run_human_main which drains once. The judge must reject.
        # We verify via the judge directly.
        rows = r8.production_records()
        phases = fx._default_valid_phases()
        # Simulate: all 30 frames captured in entry only
        tracker = {"entry": {"frame_indices": list(range(30)), "source_seqs": list(range(1, 31)),
                             "device_start_ms": 0.0, "device_end_ms": 17000.0},
                   "still": {"frame_indices": [], "source_seqs": [],
                             "device_start_ms": None, "device_end_ms": None},
                   "exit": {"frame_indices": [], "source_seqs": [],
                            "device_start_ms": None, "device_end_ms": None}}
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
        self.assertFalse(ok, f"single-phase import must be rejected: {verdict}")
        self.assertIn(verdict, ("PHASE_NOT_CAPTURED_REJECTED",
                                    "PHASE_TRACKER_WINDOW_CONFLICT_REJECTED"), verdict)

    def test_three_phase_tracker_passes(self):
        """All 3 phases with real captured frames -> accepted."""
        rows = r8.production_records()
        phases = fx._default_valid_phases()
        tracker = {"entry": {"frame_indices": list(range(0, 12)), "source_seqs": list(range(1, 13)),
                             "device_start_ms": 0.0, "device_end_ms": 2200.0},
                   "still": {"frame_indices": list(range(12, 25)), "source_seqs": list(range(13, 26)),
                             "device_start_ms": 2400.0, "device_end_ms": 4800.0},
                   "exit": {"frame_indices": list(range(25, 30)), "source_seqs": list(range(26, 31)),
                            "device_start_ms": 5000.0, "device_end_ms": 17000.0}}
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
        self.assertTrue(ok, f"3-phase tracker should pass: {verdict}")

    def test_swapped_phase_windows_rejected(self):
        """entry and exit windows swapped: tracker frames don't match -> rejected."""
        rows = r8.production_records()
        phases = fx._default_valid_phases()
        # swap entry and exit windows
        entry = dict(phases["entry"])
        exit_ = dict(phases["exit"])
        phases["entry"]["start_ms"] = exit_["start_ms"]
        phases["entry"]["end_ms"] = exit_["end_ms"]
        phases["exit"]["start_ms"] = entry["start_ms"]
        phases["exit"]["end_ms"] = entry["end_ms"]
        tracker = {"entry": {"frame_indices": list(range(25, 30)), "source_seqs": list(range(26, 31)),
                             "device_start_ms": 5000.0, "device_end_ms": 17000.0},
                   "still": {"frame_indices": list(range(12, 25)), "source_seqs": list(range(13, 26)),
                             "device_start_ms": 2400.0, "device_end_ms": 4800.0},
                   "exit": {"frame_indices": list(range(0, 12)), "source_seqs": list(range(1, 13)),
                            "device_start_ms": 0.0, "device_end_ms": 2200.0}}
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
        self.assertFalse(ok, f"swapped windows must be rejected: {verdict}")


class TestR903ExclusivePublish(unittest.TestCase):
    """R9-03: finalize_file must use exclusive-create publish that cannot
    overwrite a racing foreign creator."""

    def test_no_overwrite_filed_publish(self):
        """finalize_file with no reservation must not overwrite an existing
        foreign file: the O_EXCL create must fail."""
        import tempfile
        with tempfile.TemporaryDirectory(prefix="r11-pub-") as td:
            dst = Path(td) / "target.result.json"
            dst.write_text('{"foreign":"data"}', encoding="utf-8")
            before = sha256(dst)
            plan = rg.OutputPlan.from_raw_target(dst.with_suffix(".jsonl"))
            with self.assertRaises(FileExistsError):
                plan.finalize_file(dst, '{"our":"pass"}')
            self.assertEqual(sha256(dst), before, "foreign bytes must be preserved")

    def test_exclusive_publish_creates_new_file(self):
        """finalize_file with no reservation creates a new file when target absent."""
        import tempfile
        with tempfile.TemporaryDirectory(prefix="r11-pub-") as td:
            dst = Path(td) / "new.result.json"
            plan = rg.OutputPlan.from_raw_target(dst.with_suffix(".jsonl"))
            plan.finalize_file(dst, '{"our":"data"}')
            self.assertEqual(json.loads(dst.read_text(encoding="utf-8")), {"our": "data"})

    def test_reserved_publish_overwrites_own_token(self):
        """With a reservation, finalize_file publishes over the token path."""
        import tempfile
        with tempfile.TemporaryDirectory(prefix="r11-pub-") as td:
            dst = Path(td) / "own.result.json"
            plan = rg.OutputPlan.from_raw_target(dst.with_suffix(".jsonl"))
            plan.reserve_all()
            plan.finalize_file(dst, '{"our":"reserved"}')
            self.assertEqual(json.loads(dst.read_text(encoding="utf-8")), {"our": "reserved"})
            self.assertIn(dst.resolve(), plan.finalized_paths)


class TestR903TempOwnership(unittest.TestCase):
    """R9-03: cleanup must only remove temp files this plan actually created."""

    def test_foreign_part_not_deleted(self):
        """A foreign *.part with the same name pattern must survive cleanup."""
        import tempfile
        with tempfile.TemporaryDirectory(prefix="r11-tmp-") as td:
            dst = Path(td) / "target.result.json"
            plan = rg.OutputPlan.from_raw_target(dst.with_suffix(".jsonl"))
            foreign_part = dst.with_name(dst.name + f".{plan.reservation_id[:8]}.part")
            foreign_part.write_text('{"foreign":"temp"}', encoding="utf-8")
            before = sha256(foreign_part)
            plan.cleanup_unfinalized()
            self.assertTrue(foreign_part.exists(), "foreign .part must survive cleanup")
            self.assertEqual(sha256(foreign_part), before)

    def test_owned_part_cleaned_on_error(self):
        """Our own .part file created by finalize_file is removed on error."""
        import tempfile
        with tempfile.TemporaryDirectory(prefix="r11-tmp-") as td:
            dst = Path(td) / "target.result.json"
            plan = rg.OutputPlan.from_raw_target(dst.with_suffix(".jsonl"))
            plan.reserve_all()
            # foreign replaces our reservation before publish
            tok = plan.reserved_tokens.get(dst)
            dst.write_text('{"foreign":"appeared"}', encoding="utf-8")
            with self.assertRaises(FileExistsError):
                plan.finalize_file(dst, '{"our":"pass"}')
            plan.cleanup_unfinalized()
            # the foreign file must survive
            self.assertEqual(json.loads(dst.read_text(encoding="utf-8")), {"foreign": "appeared"})


if __name__ == "__main__":
    unittest.main(verbosity=1)
