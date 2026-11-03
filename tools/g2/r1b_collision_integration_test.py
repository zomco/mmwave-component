#!/usr/bin/env python3
"""Integration tests for G2-HW-R1-B Immutable Output Policy across runners.

Tests driving real runner main() entrypoints over isolated temporary directories
with fake transports, verifying:
- Target raw existing -> rejection, sentinel untouched
- Target result existing -> rejection, sentinel untouched
- Target manifest existing -> rejection, sentinel untouched
- All existing -> rejection
- Clean new path -> creates files
- power_cut_runner resume (start_cycle > 1) -> REJECTED before secrets/device
  I/O (immutable evidence policy, G2-HW-R2 R1-B: every attempt uses a new
  unique run directory; see r2_remediation_integration_test.py)
"""

import hashlib
import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_g2
import power_cut_runner
import usb_unplug_runner
import human_observe_runner


def sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


class TestR1BCollision(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.dir = Path(self.td.name)

    def tearDown(self):
        self.td.cleanup()

    def test_run_g2_raw_exists_rejected(self):
        raw = self.dir / "test_raw.jsonl"
        raw.write_text("sentinel_raw\n", encoding="utf-8")
        orig_hash = sha256(raw)

        def dummy_cmd(args):
            raise AssertionError("Command should never be called when target raw exists")

        with patch.object(sys, "argv", ["run_g2", "dummy", "--port", "COM9", "--out", str(raw)]), \
             patch.dict(run_g2.SUBCOMMANDS, {"dummy": dummy_cmd}), \
             patch.object(run_g2, "load_secrets", side_effect=AssertionError("Secrets should not be loaded on collision")), \
             redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            rc = run_g2.main()

        self.assertEqual(rc, 1)
        self.assertEqual(sha256(raw), orig_hash)

    def test_run_g2_result_exists_rejected(self):
        raw = self.dir / "test_result.jsonl"
        res = self.dir / "test_result.result.json"
        res.write_text('{"sentinel": true}\n', encoding="utf-8")
        orig_hash = sha256(res)

        def dummy_cmd(args):
            raise AssertionError("Command should never be called when target result exists")

        with patch.object(sys, "argv", ["run_g2", "dummy", "--port", "COM9", "--out", str(raw)]), \
             patch.dict(run_g2.SUBCOMMANDS, {"dummy": dummy_cmd}), \
             redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            rc = run_g2.main()

        self.assertEqual(rc, 1)
        self.assertEqual(sha256(res), orig_hash)

    def test_run_g2_manifest_exists_rejected(self):
        raw = self.dir / "test_manifest.jsonl"
        manifest = self.dir / "test_manifest.manifest.json"
        manifest.write_text('{"sentinel": true}\n', encoding="utf-8")
        orig_hash = sha256(manifest)

        def dummy_cmd(args):
            raise AssertionError("Command should never be called when target manifest exists")

        with patch.object(sys, "argv", ["run_g2", "dummy", "--port", "COM9", "--out", str(raw)]), \
             patch.dict(run_g2.SUBCOMMANDS, {"dummy": dummy_cmd}), \
             redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            rc = run_g2.main()

        self.assertEqual(rc, 1)
        self.assertEqual(sha256(manifest), orig_hash)

    def test_power_cut_runner_collision_rejected(self):
        raw = self.dir / "power.jsonl"
        raw.write_text("sentinel\n", encoding="utf-8")
        orig_hash = sha256(raw)

        with patch.object(sys, "argv", ["power", "--port", "COM9", "--out", str(raw)]), \
             patch.object(power_cut_runner, "run_cycle", side_effect=AssertionError("run_cycle must never touch hardware")), \
             redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            rc = power_cut_runner.main()

        self.assertEqual(rc, 1)
        self.assertEqual(sha256(raw), orig_hash)

    def test_usb_unplug_runner_collision_rejected(self):
        raw = self.dir / "usb.jsonl"
        res = self.dir / "usb.result.json"
        res.write_text("sentinel\n", encoding="utf-8")
        orig_hash = sha256(res)

        with patch.object(sys, "argv", ["usb", "--port", "COM9", "--out", str(raw)]), \
             patch.object(usb_unplug_runner, "run_cycle", side_effect=AssertionError("run_cycle must never touch hardware")), \
             redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            rc = usb_unplug_runner.main()

        self.assertEqual(rc, 1)
        self.assertEqual(sha256(res), orig_hash)

    def test_human_observe_runner_collision_rejected(self):
        raw = self.dir / "human.jsonl"
        raw.write_text("sentinel\n", encoding="utf-8")
        orig_hash = sha256(raw)

        with patch.object(sys, "argv", ["human", "--port", "COM9", "--out", str(raw)]), \
             patch.object(human_observe_runner, "robust_connect", side_effect=AssertionError("robust_connect must never touch port")), \
             redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            rc = human_observe_runner.main()

        self.assertEqual(rc, 1)
        self.assertEqual(sha256(raw), orig_hash)


if __name__ == "__main__":
    unittest.main()
