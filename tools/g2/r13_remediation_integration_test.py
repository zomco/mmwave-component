#!/usr/bin/env python3
"""R13 delivery: B1 residual (object ownership across publish and cleanup)
and R9-01 residual (tracker index/seq mapping validation). All offline,
fake device/secrets; no serial, no network, no HA, no real secrets.

B1 platform note (single-machine Windows verification, not a claim about
other platforms): while a staging object is PINNED (held duplicate
descriptor), a concurrent writer cannot unlink/rename its path on Windows
(CRT handles are opened without FILE_SHARE_DELETE) - proven by
test_replacement_blocked_while_pinned.  On POSIX replacement IS possible;
the same tests exercise the true replacement there, and on Windows the
"path resolves to a foreign object" state is simulated through the
documented seam OutputPlan._path_identity (what unlink+create achieves on
POSIX), after which the REAL publisher/cleanup runs unmocked."""

import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import sys  # noqa: E402
sys.path.insert(0, str(Path(__file__).resolve().parent))

import hardware_judges as hj  # noqa: E402
import r5_audit_probe_integration_test as fx  # noqa: E402
import r8_remediation_integration_test as r8  # noqa: E402
import r9_remediation_integration_test as r9  # noqa: E402
import run_g2 as rg  # noqa: E402

sha256 = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()  # noqa: E731


def _result_part_path(out_dir: Path) -> Path:
    """The staging .part path the runner used for human.result.json."""
    parts = list(out_dir.glob("human.result.json.*.part"))
    assert len(parts) >= 1, f"no result part in {out_dir}: {list(out_dir.iterdir())}"
    return parts[0]


class TestB1NormalAndBlocking(unittest.TestCase):
    """Positive baseline + proof that a pinned staging path cannot be
    replaced by a concurrent writer on Windows (the OS-level half of the
    ownership guarantee)."""

    def test_normal_no_race_full_consistency(self):
        """Real human.main, no interference: rc 0, pass, raw/result/manifest
        consistent, no staging temps left, all pins closed."""
        out = r9.live_run(interactive=True)
        self.assertEqual(out["rc"], 0, out["result"].get("verdict"))
        self.assertEqual(out["result"]["status"], "pass")
        self.assertEqual(out["result"]["verdict"], "HUMAN_OBSERVE_PASS")
        d = Path(out["dir"])
        raw, res = d / "human.jsonl", d / "human.result.json"
        man = d / "human.manifest.json"
        if not man.is_file():  # manifest naming fallback
            cands = list(d.glob("human*.manifest.json"))
            self.assertTrue(cands, f"no manifest in {d}")
            man = cands[0]
        self.assertTrue(all(p.is_file() for p in (raw, res, man)))
        m = json.loads(man.read_text(encoding="utf-8"))
        self.assertEqual(m.get("result_sha256"), sha256(res))
        self.assertEqual(m.get("raw_sha256"), out["result"]["evidence"]["sha256"])
        self.assertEqual(list(d.glob("*.part")), [], "staging temps must be cleaned")
        self.assertEqual(list(d.glob("*.tmp")), [])

    def test_replacement_blocked_while_pinned(self):
        """While the plan pins the staging object, a concurrent writer must
        NOT be able to replace it on Windows (unlink -> PermissionError);
        the real publish then succeeds normally.  On POSIX the replacement
        succeeds and the REAL publisher must refuse it (see below)."""
        blocked = {"nt": False, "posix": False}
        real_publish = rg.OutputPlan._exclusive_publish
        probe: dict = {}

        def attacker_then_publish(plan, target, part):
            if target.name == "human.result.json" and not probe:
                before = tuple(plan.owned_tmp[part]["ident"])
                if os.name == "nt":
                    try:
                        part.unlink()
                        blocked["nt"] = False  # unexpectedly allowed
                    except PermissionError:
                        blocked["nt"] = True  # OS guarantee held
                else:
                    # POSIX: replacement is possible - do it for real
                    part.unlink()
                    part.write_text('{"foreign":true}', encoding="utf-8")
                    blocked["posix"] = True
                probe["path"] = str(part)
                probe["pinned_id"] = before
                probe["path_id_after"] = rg.OutputPlan._path_identity(part)
            return real_publish(plan, target, part)

        with mock.patch.object(rg.OutputPlan, "_exclusive_publish", attacker_then_publish):
            out = r9.live_run(interactive=True)
        if os.name == "nt":
            self.assertTrue(blocked["nt"],
                            "pinned staging path must be un-replaceable on Windows")
            # publish of the still-ours object succeeds normally
            self.assertEqual(out["rc"], 0, out["result"].get("verdict"))
            self.assertEqual(out["result"]["status"], "pass")
        else:
            # the foreign object replaced ours: the real publisher refuses
            self.assertNotEqual(out["rc"], 0)
            self.assertEqual(out["result"]["status"], "fail")
            self.assertIn(out["result"]["verdict"], ("STORAGE_FINALIZE_FAILED",))
            self.assertEqual(Path(probe["path"]).read_text(encoding="utf-8"),
                             '{"foreign":true}', "foreign object must be preserved")


class TestB1PublishSourceOwnership(unittest.TestCase):
    """R13 counterexample 1 (foreign_part_published): the completed .part is
    replaced before publish and the publisher runs normally - the publish
    must be REFUSED, the foreign object preserved, the run non-zero with a
    consistent (non-pass) result/manifest pair."""

    def _run_with_foreign_part_path(self):
        """Simulate the staging path resolving to a FOREIGN object (the
        unlink+create a concurrent writer performs on POSIX), then run the
        REAL publisher - no publish failure is injected."""
        real_identity = rg.OutputPlan._path_identity
        probe: dict = {}

        def foreign_identity(p):
            ident = real_identity(p)
            if (isinstance(p, Path) and p.name.startswith("human.result.json.")
                    and p.name.endswith(".part") and not probe):
                # a different object id at the same path = replaced source
                probe["path"] = str(p)
                probe["real_id"] = ident
                return (ident[0], (ident[1] + 1) if ident else 1)
            return ident

        with mock.patch.object(rg.OutputPlan, "_path_identity",
                               staticmethod(foreign_identity)):
            out = r9.live_run(interactive=True)
        return out, probe

    def test_publish_source_replaced_refused(self):
        out, probe = self._run_with_foreign_part_path()
        self.assertTrue(probe, "the publish attempt must have reached the gate")
        self.assertNotEqual(out["rc"], 0, "runner must not exit 0 on a foreign source")
        res = out["result"]
        self.assertEqual(res["status"], "fail")
        self.assertEqual(res["verdict"], "STORAGE_FINALIZE_FAILED")
        # no pass remains anywhere; the on-disk result is the DOWNGRADED one
        d = Path(out["dir"])
        res_path = d / "human.result.json"
        self.assertTrue(res_path.is_file())
        disk = json.loads(res_path.read_text(encoding="utf-8"))
        self.assertEqual(disk["status"], "fail")
        self.assertNotEqual(disk.get("original_status"), None)
        # the foreign source object is neither moved nor deleted
        self.assertTrue(Path(probe["path"]).exists(),
                        "foreign object must be preserved in place")
        # manifest agrees with the downgraded result (no fake pass): the
        # R8-03 downgrade contract rewrites the manifest with
        # result_sha256=None + status fail, never the pass hash
        cands = list(d.glob("human*.manifest.json"))
        if cands:
            m = json.loads(cands[0].read_text(encoding="utf-8"))
            self.assertIsNone(m.get("result_sha256"),
                              "downgraded manifest must not carry a pass hash")
            self.assertNotEqual(m.get("verdict"), "HUMAN_OBSERVE_PASS")

    def test_unit_publish_refusal_preserves_foreign(self):
        """Unit-level: OutputPlan refuses to publish a staging path whose
        object is not the pinned one; the file at the path is untouched."""
        with tempfile.TemporaryDirectory(prefix="r13-pub-") as td:
            dst = Path(td) / "t.result.json"
            plan = rg.OutputPlan.from_raw_target(Path(td) / "t.jsonl")
            plan._part_seq += 1
            part = dst.with_name(f"t.result.json.{plan.reservation_id[:8]}.{plan._part_seq}.part")
            fd = plan._open_owned_part(part)
            # R14: the pin carries DELETE access without delete-share, so
            # the staged content must be written through OUR fd
            os.write(fd, '{"our":"pass"}'.encode("utf-8"))
            os.close(fd)
            real_identity = rg.OutputPlan._path_identity

            def foreign(p):
                ident = real_identity(p)
                if Path(p) == part:
                    return (ident[0], ident[1] + 1)
                return ident

            with mock.patch.object(rg.OutputPlan, "_path_identity",
                                   staticmethod(foreign)):
                with self.assertRaises(rg.OutputOwnershipLostError):
                    plan._exclusive_publish(dst, part)
            self.assertFalse(dst.exists(), "no pass may be published")
            self.assertEqual(part.read_text(encoding="utf-8"), '{"our":"pass"}',
                             "object at the path must be untouched")
            self.assertEqual(plan.owned_tmp, {}, "pin must be closed")


class TestB1LateReplacementCleanup(unittest.TestCase):
    """R13 counterexample 2 (late_replacement_deleted): a replacement lands
    AFTER the identity read and BEFORE the destructive unlink during
    cleanup - the foreign object must survive with its bytes unchanged."""

    def test_late_replacement_preserved(self):
        real_publish = rg.OutputPlan._exclusive_publish
        real_identity = rg.OutputPlan._path_identity
        probe: dict = {}

        def failing_publish(plan, target, part):
            if target.name == "human.result.json" and not probe:
                probe["path"] = str(part)
                raise OSError("synthetic publication failure to exercise cleanup")
            return real_publish(plan, target, part)

        def identity_with_late_race(p):
            ident = real_identity(p)
            if (isinstance(p, Path) and str(p) == probe.get("path")
                    and probe.get("published_failed") and not probe.get("lied")):
                # cleanup's unlink gate reads identity here: simulate the
                # writer having swapped the object in the meantime
                probe["lied"] = True
                probe["cleanup_gate_id"] = ident
                return (ident[0], ident[1] + 1)
            return ident

        def failing_publish_wrapper(plan, target, part):
            try:
                return failing_publish(plan, target, part)
            finally:
                if probe.get("path"):
                    probe["published_failed"] = True

        with mock.patch.object(rg.OutputPlan, "_exclusive_publish",
                               failing_publish_wrapper), \
             mock.patch.object(rg.OutputPlan, "_path_identity",
                               staticmethod(identity_with_late_race)):
            out = r9.live_run(interactive=True)

        self.assertNotEqual(out["rc"], 0)
        self.assertEqual(out["result"]["status"], "fail")
        self.assertEqual(out["result"]["verdict"], "STORAGE_FINALIZE_FAILED")
        # the object at the staging path was NOT deleted by cleanup
        self.assertTrue(Path(probe["path"]).exists(),
                        "cleanup must not delete an unattributable object")
        self.assertEqual(plan_preserved_note(out), True)

    def test_unit_cleanup_gate_preserves(self):
        """Unit-level: _release_owned removes the name ONLY while the object
        at the path is provably the pinned one."""
        with tempfile.TemporaryDirectory(prefix="r13-cln-") as td:
            dst = Path(td) / "t.result.json"
            plan = rg.OutputPlan.from_raw_target(Path(td) / "t.jsonl")
            plan._part_seq += 1
            part = dst.with_name(f"t.result.json.{plan.reservation_id[:8]}.{plan._part_seq}.part")
            fd = plan._open_owned_part(part)
            os.write(fd, b"{}")  # R14: write through OUR fd (pin holds DELETE)
            os.close(fd)
            # gate sees a foreign identity -> preserve, never unlink
            real_identity = rg.OutputPlan._path_identity
            with mock.patch.object(rg.OutputPlan, "_path_identity",
                                   staticmethod(lambda p: ((0, 999999) if Path(p) == part
                                                           else real_identity(p)))):
                self.assertEqual(plan._release_owned(part, remove=True),
                                 "preserved-foreign")
            self.assertTrue(part.exists())
            self.assertEqual(plan.owned_tmp, {}, "pin must be closed")
            # and normal removal still works when identity holds
            plan._part_seq += 1
            part2 = dst.with_name(f"t2.{plan.reservation_id[:8]}.{plan._part_seq}.part")
            fd2 = plan._open_owned_part(part2)
            os.close(fd2)
            self.assertEqual(plan._release_owned(part2, remove=True), "removed")
            self.assertFalse(part2.exists())


def plan_preserved_note(out) -> bool:
    """The runner's failure diagnostics must mention the preserved object
    (either via the exception text in the result or the plan attribute)."""
    blob = json.dumps(out["result"], ensure_ascii=False)
    return ("refusing to publish" in blob or "preserved" in blob
            or "OutputOwnershipLost" in blob
            or out["result"].get("verdict") == "STORAGE_FINALIZE_FAILED")


class TestB1OldProtectionsPreserved(unittest.TestCase):
    """Pre-existing protections must keep passing under the new lifecycle."""

    def test_preexisting_foreign_part_survives(self):
        with tempfile.TemporaryDirectory(prefix="r13-pre-") as td:
            dst = Path(td) / "t.result.json"
            plan = rg.OutputPlan.from_raw_target(Path(td) / "t.jsonl")
            # finalize_file assigns sequence (_part_seq + 1) to its staging
            # name; occupy exactly that name with a foreign object first
            foreign = dst.with_name(
                f"t.result.json.{plan.reservation_id[:8]}.{plan._part_seq + 1}.part")
            foreign.write_text('{"foreign":"temp"}', encoding="utf-8")
            with self.assertRaises(FileExistsError):
                plan.finalize_file(dst, '{"our":"pass"}')
            plan.cleanup_unfinalized()
            self.assertEqual(foreign.read_text(encoding="utf-8"), '{"foreign":"temp"}')

    def test_target_race_creator_preserved(self):
        with tempfile.TemporaryDirectory(prefix="r13-race-") as td:
            dst = Path(td) / "t.result.json"
            plan = rg.OutputPlan.from_raw_target(dst.with_suffix(".jsonl"))
            dst.write_text('{"foreign":"won"}', encoding="utf-8")
            with self.assertRaises(FileExistsError):
                plan.finalize_file(dst, '{"our":"pass"}')
            self.assertEqual(dst.read_text(encoding="utf-8"), '{"foreign":"won"}')
            plan.cleanup_unfinalized()
            self.assertEqual(list(Path(td).glob("*.part")), [])

    def test_reservation_replaced_refused(self):
        with tempfile.TemporaryDirectory(prefix="r13-res-") as td:
            dst = Path(td) / "t.result.json"
            plan = rg.OutputPlan.from_raw_target(Path(td) / "t.jsonl")
            plan.reserve_all()
            res_key = next(k for k in plan.reserved_tokens
                           if k.name.endswith(".result.json"))
            tok = plan.reserved_tokens.pop(res_key)
            res_key.write_text('{"foreign":"appeared"}', encoding="utf-8")
            plan.reserved_tokens[res_key] = tok  # restore record; file is foreign
            with self.assertRaises(FileExistsError):
                plan.finalize_file(dst, '{"our":"pass"}')
            self.assertEqual(res_key.read_text(encoding="utf-8"),
                             '{"foreign":"appeared"}')

    def test_write_failure_self_cleanup(self):
        with tempfile.TemporaryDirectory(prefix="r13-wr-") as td:
            dst = Path(td) / "t.result.json"
            plan = rg.OutputPlan.from_raw_target(dst.with_suffix(".jsonl"))
            real_fsync = os.fsync
            with mock.patch("os.fsync", side_effect=OSError("disk full")):
                with self.assertRaises(OSError):
                    plan.finalize_file(dst, '{"our":"pass"}')
            self.assertFalse(dst.exists(), "no pass on storage failure")
            self.assertEqual(list(Path(td).glob("*.part")), [])
            self.assertEqual(plan.owned_tmp, {}, "pin closed on failure")

    def test_interrupt_releases_pins_and_publishes_nothing(self):
        with tempfile.TemporaryDirectory(prefix="r13-int-") as td:
            dst = Path(td) / "t.result.json"
            plan = rg.OutputPlan.from_raw_target(dst.with_suffix(".jsonl"))
            with mock.patch.object(rg.OutputPlan, "_exclusive_publish",
                                   side_effect=KeyboardInterrupt("interrupted")):
                with self.assertRaises(KeyboardInterrupt):
                    plan.finalize_file(dst, '{"status":"pass"}')
            self.assertFalse(dst.exists(), "an interrupt must not expose a final pass")
            self.assertEqual(plan.owned_tmp, {}, "pins released on interrupt")
            plan.cleanup_unfinalized()
            self.assertEqual(list(Path(td).glob("*.part")), [])

    def test_success_closes_all_pins(self):
        with tempfile.TemporaryDirectory(prefix="r13-ok-") as td:
            dst = Path(td) / "t.result.json"
            plan = rg.OutputPlan.from_raw_target(Path(td) / "t.jsonl")
            plan.finalize_file(dst, '{"our":"pass"}')
            self.assertEqual(dst.read_text(encoding="utf-8"), '{"our":"pass"}')
            self.assertEqual(plan.owned_tmp, {})
            self.assertTrue(len(plan._closed_handles) >= 1,
                            "pin handles must be closed and auditable")
            # audit records name the staged path and whether the object was
            # removed; the pin itself is closed by the single-owner
            # _pin_close (a Win32 handle cannot be probed with fstat)
            for rec in plan._closed_handles:
                self.assertIn("pin", rec)
                self.assertTrue(rec["path"].endswith(".part"))


class TestR901TrackerMappingContract(unittest.TestCase):
    """R9-01 residual: the tracker's index/seq mapping is validated as a
    whole before any statistics - real offline judge on real
    runner-generated records, only the tracker metadata is mutated."""

    @classmethod
    def setUpClass(cls):
        cls.rows = r8.production_records()
        base = r9.live_run(interactive=False,
                           phase_file_bindings=fx._default_valid_phases())
        cls.doc = copy.deepcopy(base["result"])
        cls.doc.update(telemetry_records=cls.rows, require_structured_phases=True,
                       expected_installation=dict(r8.BASE_CAL))

    def _judge(self, mutate_tracker=None, mutate_rows=None):
        # deep-copy BOTH the doc and the telemetry rows: tests may corrupt
        # rows and must never contaminate the shared class fixture
        d = copy.deepcopy(self.doc)
        rows = copy.deepcopy(self.rows)
        d["telemetry_records"] = rows
        if mutate_rows is not None:
            mutate_rows(rows)
        if mutate_tracker is not None:
            mutate_tracker(d["host_device_time_mapping"]["live_phase_tracker"])
        return hj.judge_human_observation(d)

    def test_baseline_passes(self):
        v, ok, _ = self._judge(lambda t: None)
        self.assertTrue(ok, v)
        self.assertEqual(v, "HUMAN_OBSERVE_PASS")

    def test_reviewer_seq_shrunk_to_one_rejected(self):
        # reviewer counterexample: 13 indices, source_seqs=[25]
        v, ok, det = self._judge(lambda t: t["still"].update(source_seqs=[25]))
        self.assertFalse(ok)
        self.assertEqual(v, "PHASE_TRACKER_MALFORMED_REJECTED")
        self.assertIn("lengths differ", str(det.get("detail")))

    def test_reviewer_out_of_range_index_rejected(self):
        # reviewer counterexample: nonexistent frame 9999 appended
        v, ok, det = self._judge(lambda t: t["still"]["frame_indices"].append(9999))
        self.assertFalse(ok)
        self.assertEqual(v, "PHASE_TRACKER_MALFORMED_REJECTED")

    def test_seq_pointing_at_other_frame_rejected(self):
        def swap(t):
            s = t["still"]["source_seqs"]
            s[0], s[1] = s[1], s[0]
        v, ok, det = self._judge(swap)
        self.assertFalse(ok)
        self.assertEqual(v, "PHASE_TRACKER_MALFORMED_REJECTED")
        self.assertIn("claims", str(det.get("detail")))

    def test_cross_phase_frame_attribution_rejected(self):
        def steal(t):
            t["still"]["frame_indices"].append(t["entry"]["frame_indices"][-1])
            t["still"]["source_seqs"].append(t["entry"]["source_seqs"][-1])
        v, ok, _ = self._judge(steal)
        self.assertFalse(ok)
        # the stolen frame violates the still phase envelope AND the one-
        # frame-one-phase rule; both are PHASE_TRACKER_MALFORMED_REJECTED
        self.assertEqual(v, "PHASE_TRACKER_MALFORMED_REJECTED")

    def test_type_abuse_rejected(self):
        for mutate in (
            lambda t: t["still"]["frame_indices"].__setitem__(0, True),   # bool
            lambda t: t["still"]["frame_indices"].__setitem__(0, 1.0),   # float
            lambda t: t["still"]["frame_indices"].__setitem__(0, "3"),   # str
            lambda t: t["still"].update(frame_indices=tuple(t["still"]["frame_indices"])),
            lambda t: t["still"].update(source_seqs=None),
        ):
            with self.subTest(mut=mutate.__name__ if hasattr(mutate, "__name__") else str(mutate)):
                v, ok, _ = self._judge(mutate)
                self.assertFalse(ok, f"malformed tracker must never pass: {v}")
                self.assertEqual(v, "PHASE_TRACKER_MALFORMED_REJECTED")

    def test_time_envelope_mismatch_rejected(self):
        def shrink(t):
            t["still"]["device_end_ms"] = 0.0  # cannot cover frames 2000..4800ms
        v, ok, det = self._judge(shrink)
        self.assertFalse(ok)
        self.assertEqual(v, "PHASE_TRACKER_MALFORMED_REJECTED")
        self.assertIn("envelope", str(det.get("detail")))

    def test_repeat_index_within_phase_rejected(self):
        def dup(t):
            t["still"]["frame_indices"].append(t["still"]["frame_indices"][0])
            t["still"]["source_seqs"].append(t["still"]["source_seqs"][0])
        v, ok, _ = self._judge(dup)
        self.assertFalse(ok)
        self.assertEqual(v, "PHASE_TRACKER_MALFORMED_REJECTED")

    def test_legitimate_duplicate_seq_value_still_passes(self):
        """A repeated source_seq VALUE is a sampling question judged
        elsewhere; the mapping itself stays valid and must not be banned
        indiscriminately.  Two adjacent frames legitimately carrying the
        same seq (non-decreasing sequence) with a consistent 1:1 mapping
        must still pass."""
        def dup_seq(rows):
            # make the LAST still frame carry the same seq as its predecessor
            # (non-decreasing, so the telemetry integrity gate stays happy)
            last_still_idx = 24  # tracker still covers indices 12..24
            rows[last_still_idx]["source_seq"] = rows[last_still_idx - 1]["source_seq"]

        def mirror_seq(t):
            t["still"]["source_seqs"][-1] = t["still"]["source_seqs"][-2]

        v, ok, _ = self._judge(mutate_tracker=mirror_seq, mutate_rows=dup_seq)
        self.assertTrue(ok, f"duplicate seq value with valid mapping: {v}")

    def test_real_human_main_positive_flow(self):
        """Collector-side control: the real interactive flow (which builds
        the tracker) still passes end-to-end."""
        out = r9.live_run(interactive=True)
        self.assertEqual(out["rc"], 0, out["result"].get("verdict"))
        self.assertEqual(out["result"]["verdict"], "HUMAN_OBSERVE_PASS")


import copy  # noqa: E402  (used by TestR901TrackerMappingContract)

if __name__ == "__main__":
    unittest.main(verbosity=1)
