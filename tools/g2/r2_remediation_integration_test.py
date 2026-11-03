#!/usr/bin/env python3
"""Round-2 (2026-10-30) remediation closure tests — G2-HW-R1-A/R1-B/R3-A/R4-A.

Formal coverage for the review's named scenarios that were not yet pinned in
the official suites.  Everything runs offline through the REAL entry points
with fake transports; asserts no real serial / secrets I/O.

R1-A  Review binding is content-bound (result_sha256) and root-scoped:
      same-name results in different batch roots never inherit each other's
      reviews; a review bound to one file's hash cannot claim another file
      with the same run_id.
R1-B  Resume-by-append is disabled: --start-cycle > 1 is rejected before any
      secret or device I/O (immutable evidence policy; every attempt gets a
      unique new run directory instead).
R3-A  Real runner mains with --rounds 0 exit non-zero, write a fail result,
      and never touch the device or secrets.
R4-A  The REAL cmd_backpressure entry uses the shared judge: RPC failure,
      non-advancing counters+time, uptime reset, and missing/None snapshot
      fields all fail closed without crashing.
"""

import io
import json
import hashlib
import sys
import tempfile
import unittest
import contextlib
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))

import build_evidence_index as bi  # noqa: E402
import hardware_judges as hj  # noqa: E402
import power_cut_runner as pcr  # noqa: E402
import run_g2 as rg  # noqa: E402
import usb_unplug_runner as uur  # noqa: E402
import r5_audit_probe_integration_test as fx  # noqa: E402

sha256 = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()  # noqa: E731


# ---------------------------------------------------------------------------
# R1-A: content-bound, root-scoped review binding
# ---------------------------------------------------------------------------

class TestR1AReviewBinding(unittest.TestCase):
    HELPER = fx.TestR1AEvidenceIndex()

    def _stamp_review_sha(self, rp: Path) -> str:
        """Re-bind a run's manifest result hash after an explicit edit."""
        mp = rp.with_name(rp.name.replace(".result.json", ".manifest.json"))
        m = json.loads(mp.read_text(encoding="utf-8"))
        m["result_sha256"] = sha256(rp)
        mp.write_text(json.dumps(m), encoding="utf-8")
        return sha256(rp)

    def test_cross_root_same_name_with_old_reject_isolated(self):
        """Two batch roots reuse the SAME result filename; an old 'rejected'
        review bound to root A's file must not touch root B's file."""
        with tempfile.TemporaryDirectory(prefix="r2-xroot-") as td:
            root_a = Path(td) / "session-01"; root_a.mkdir()
            root_b = Path(td) / "session-02"; root_b.mkdir()
            ra, _ = self.HELPER._write_run(root_a, "b1_backpressure", complete_meta=True)
            rb, _ = self.HELPER._write_run(root_b, "b1_backpressure", complete_meta=True)
            # old reject bound (content hash) to root A's file ONLY
            reviews = {
                "session-01/b1_backpressure": {
                    "accepted_status": "rejected",
                    "reason": "old raw unrecoverable; re-run required (session-01)",
                    "result_sha256": sha256(ra),
                    "target_root": "session-01",
                },
            }
            idx = bi.build_index({"session-01": root_a, "session-02": root_b},
                                 Path(td) / "idx.json", reviews,
                                 bi.FIRMWARE_BATCHES, sources_snapshot={})
            runs = {(r["directory_batch"], r["result_file"]): r for r in idx["runs"]}
            ra_entry = next(v for (root, k), v in runs.items()
                            if root == "session-01")
            rb_entry = next(v for (root, k), v in runs.items()
                            if root == "session-02")
            self.assertEqual(ra_entry["accepted_status"], "rejected",
                             ra_entry)
            self.assertNotEqual(rb_entry["accepted_status"], "rejected",
                                "old batch reject must not pollute the new batch")
            self.assertEqual(rb_entry["accepted_status"], "pending_review",
                             rb_entry)

    def test_same_run_id_different_hash_rejects_transfer(self):
        """A review bound to one file's content cannot be claimed by another
        file that reuses the same run_id but has different bytes: the id-keyed
        review stays valid for the file it was bound to, and the OTHER file
        (same run_id, different hash) cannot inherit it."""
        with tempfile.TemporaryDirectory(prefix="r2-sameid-") as td:
            root = Path(td) / "ev"; root.mkdir()
            r_old, _ = self.HELPER._write_run(root, "dup-run", complete_meta=True)
            r_new, _ = self.HELPER._write_run(root, "dup-run-copy", complete_meta=True)
            # make both carry the same run_id but different content
            d_new = json.loads(r_new.read_text(encoding="utf-8"))
            d_new["run_id"] = "dup-run"
            r_new.write_text(json.dumps(d_new), encoding="utf-8")
            self._stamp_review_sha(r_new)
            s_old = self._stamp_review_sha(r_old)
            # single id-keyed review bound to the ORIGINAL's content hash
            reviews = {
                "dup-run": {"accepted_status": "pass",
                            "reason": "precise review bound to the original bytes",
                            "result_sha256": s_old},
            }
            idx = bi.build_index({"ev": root}, Path(td) / "idx.json", reviews,
                                 bi.FIRMWARE_BATCHES, sources_snapshot={})
            runs = {r["result_file"]: r for r in idx["runs"]}
            e_old = next(v for k, v in runs.items() if k.endswith("dup-run.result.json"))
            e_new = next(v for k, v in runs.items() if k.endswith("dup-run-copy.result.json"))
            # the original keeps its own hash-bound review
            self.assertEqual(e_old["accepted_status"], "pass", e_old)
            # the copy (same run_id, DIFFERENT bytes) cannot inherit it
            self.assertNotEqual(e_new["accepted_status"], "pass", e_new)
            self.assertEqual(e_new["accepted_status"], "pending_review", e_new)
            self.assertIn("hash mismatch", (e_new["review_note"] or ""),
                          f"rejection must be the content binding: {e_new}")

    def test_legacy_review_without_hash_binding_stays_pending(self):
        """A review entry without result_sha256 can never upgrade a run
        (content binding is mandatory; no filename trust)."""
        with tempfile.TemporaryDirectory(prefix="r2-legacy-") as td:
            root = Path(td) / "ev"; root.mkdir()
            rp, _ = self.HELPER._write_run(root, "legacy-run", complete_meta=True)
            idx = bi.build_index({"ev": root}, Path(td) / "idx.json",
                                 {"legacy-run": {"accepted_status": "pass",
                                                 "reason": "no hash bound"}},
                                 bi.FIRMWARE_BATCHES, sources_snapshot={})
            e = next(r for r in idx["runs"] if "legacy-run" in r["result_file"])
            self.assertEqual(e["accepted_status"], "pending_review", e)
            self.assertIn("result_sha256", e["review_note"])


# ---------------------------------------------------------------------------
# R1-B: resume-by-append stays disabled
# ---------------------------------------------------------------------------

class TestR1BResumeDisabled(unittest.TestCase):
    def test_power_runner_start_cycle_resume_rejected(self):
        """--start-cycle > 1 (in-place append resume) is rejected before
        secrets or device I/O; attempts must use a NEW unique run."""
        with tempfile.TemporaryDirectory(prefix="r2-resume-") as td:
            raw = Path(td) / "p.jsonl"
            with fx._NoRealIO(), \
                 patch.object(sys, "argv", ["power", "--port", "FAKE",
                                            "--start-cycle", "2",
                                            "--out", str(raw)]), \
                 patch.object(rg, "load_secrets",
                              side_effect=AssertionError("secrets must not load")), \
                 patch.object(pcr, "run_cycle",
                              side_effect=AssertionError("device must not be touched")), \
                 contextlib.redirect_stdout(io.StringIO()), \
                 contextlib.redirect_stderr(io.StringIO()):
                rc = pcr.main()
            self.assertEqual(rc, 1)
            self.assertFalse(raw.exists())


# ---------------------------------------------------------------------------
# R3-A: real runner mains with --rounds 0
# ---------------------------------------------------------------------------

class TestR3ARoundsZeroRealMains(unittest.TestCase):
    def test_power_main_rounds_zero_fail_closed(self):
        with tempfile.TemporaryDirectory(prefix="r2-pzero-") as td:
            raw = Path(td) / "p0.jsonl"
            with fx._NoRealIO(), \
                 patch.object(sys, "argv", ["power", "--port", "FAKE",
                                            "--rounds", "0", "--out", str(raw)]), \
                 contextlib.redirect_stdout(io.StringIO()), \
                 contextlib.redirect_stderr(io.StringIO()):
                rc = pcr.main()
            self.assertEqual(rc, 1)
            res = json.loads(raw.with_suffix(".result.json").read_text(encoding="utf-8"))
            self.assertEqual(res["status"], "fail")
            self.assertIn("Invalid rounds", res.get("error", ""))

    def test_usb_main_rounds_zero_fail_closed(self):
        with tempfile.TemporaryDirectory(prefix="r2-uzero-") as td:
            raw = Path(td) / "u0.jsonl"
            with fx._NoRealIO(), \
                 patch.object(sys, "argv", ["usb", "--port", "FAKE",
                                            "--rounds", "0", "--out", str(raw)]), \
                 contextlib.redirect_stdout(io.StringIO()), \
                 contextlib.redirect_stderr(io.StringIO()):
                rc = uur.main()
            self.assertEqual(rc, 1)
            res = json.loads(raw.with_suffix(".result.json").read_text(encoding="utf-8"))
            self.assertEqual(res["status"], "fail")
            self.assertIn("Invalid rounds", res.get("error", ""))


# ---------------------------------------------------------------------------
# R4-A: real cmd_backpressure — fail-closed data contract
# ---------------------------------------------------------------------------

class _FakeClient:
    def __init__(self, boot="1" * 32):
        self.boot_id = boot

    def hello(self):
        return {"boot_id": self.boot_id}

    def close(self):
        pass

    def resume_reads(self):
        pass


class _FakeEvidence:
    def note(self, data):
        pass

    def close(self):
        return {}


def run_bp(gap_fn, boot="1" * 32):
    c = _FakeClient(boot=boot)
    with patch.object(rg, "connect", return_value=(c, _FakeEvidence())), \
         patch.object(rg, "gap_call", side_effect=gap_fn), \
         patch.object(rg.time, "sleep"), \
         contextlib.redirect_stdout(io.StringIO()):
        return rg.cmd_backpressure(__import__("types").SimpleNamespace(seconds=12))


class TestR4ABackpressureDataContract(unittest.TestCase):
    @staticmethod
    def _status(n, uptime=None, frames=None, frame_ms=None, link="healthy"):
        return {"ok": True,
                "result": {"uptime_ms": n * 1000 if uptime is None else uptime,
                           "radar_link": link,
                           "last_radar_frame_ms": n * 900 if frame_ms is None else frame_ms,
                           "counters": {"radar_frames": n * 10 if frames is None else frames}}}

    def test_rpc_failure_fail_closed(self):
        count = [0]

        def gap(client, cmd, *a, **kw):
            count[0] += 1
            if count[0] == 1:
                return {"ok": True}
            if count[0] == 2:
                return self._status(1)
            return {"ok": False, "error": {"code": "TIMEOUT", "message": "x"}}

        res = run_bp(gap)
        self.assertEqual(res["status"], "fail", res)
        self.assertIn("rpc_after_backpressure",
                      [c["name"] for c in res["checks"] if not c["pass"]])

    def test_counters_and_time_stuck_fail_closed(self):
        def gap(client, cmd, *a, **kw):
            count = getattr(gap, "n", 0) + 1
            gap.n = count
            if count == 1:
                return {"ok": True}
            return self._status(count, frames=5, frame_ms=100)

        res = run_bp(gap)
        self.assertEqual(res["status"], "fail")
        self.assertIn("radar_alive_after_backpressure",
                      [c["name"] for c in res["checks"] if not c["pass"]])

    def test_uptime_reset_fail_closed(self):
        def gap(client, cmd, *a, **kw):
            count = getattr(gap, "n", 0) + 1
            gap.n = count
            if count == 1:
                return {"ok": True}
            if count == 2:
                return self._status(1, uptime=5000)
            # uptime drops below the base snapshot: reboot/stale, unprovable
            return self._status(2, uptime=100)

        res = run_bp(gap)
        self.assertEqual(res["status"], "fail")
        self.assertIn("uptime_advanced",
                      [c["name"] for c in res["checks"] if not c["pass"]])

    def test_missing_snapshot_fields_fail_closed_without_crash(self):
        def gap(client, cmd, *a, **kw):
            count = getattr(gap, "n", 0) + 1
            gap.n = count
            if count == 1:
                return {"ok": True}
            if count == 2:
                return {"ok": True, "result": {"uptime_ms": 1000}}  # no counters/time
            return {"ok": True, "result": {"uptime_ms": None, "counters": None,
                                           "radar_link": "healthy"}}

        res = run_bp(gap)  # must not raise
        self.assertEqual(res["status"], "fail")
        self.assertIn("uptime_advanced",
                      [c["name"] for c in res["checks"] if not c["pass"]])

    def test_healthy_progression_passes(self):
        def gap(client, cmd, *a, **kw):
            count = getattr(gap, "n", 0) + 1
            gap.n = count
            if count == 1:
                return {"ok": True}
            return self._status(count)

        res = run_bp(gap)
        self.assertEqual(res["status"], "pass", res)


if __name__ == "__main__":
    unittest.main(verbosity=1)
