#!/usr/bin/env python3
"""R14 delivery: object-level staging deletion (B1 residual close->unlink
race). All offline, fake device/secrets; no serial, no network, no HA.

R13 residual fixed here: _release_owned closed the pin BEFORE the pathname
unlink, so a writer that swapped the path right after the real close could
have OUR unlink destroy the foreign object (reviewer probes
close_unlink_race_success/failure: foreign_exists_after=false).

R14 design: deletion is bound to the OBJECT, not the path.  On Windows the
pin is a Win32 handle carrying DELETE access (opened CREATE_NEW, share
read+write but NOT delete); removal marks the pinned object for deletion
via SetFileInformationByHandle(FileDispositionInfoEx, POSIX semantics) and
closes the pin - the removal completes with the handle, and there is NO
pathname unlink after (or before) the close, so the reviewer's interleave
(close returns -> writer swaps the path -> product unlinks) cannot occur:
at the moment the protection is gone the staging NAME is already removed.

What the formal tests below prove, per the remediation prompt:
  - at the tightest seam (real release returned => real pin closed), the
    staging name is already gone (swap unconstructable) on Windows, OR a
    swap that does land is never deleted by the product;
  - a foreign object occupying the freed staging name AFTER the release is
    never touched by the product (success AND failure paths, real main);
  - the blocking control (unlink while pinned -> PermissionError) holds;
  - the no-object-delete fallback (POSIX posture) preserves the staging
    file and NEVER pathname-unlinks (structural spy on os.unlink);
  - full write/flush/fsync/close -> publish, no-overwrite, interrupt and
    failure contracts stay intact.
Platform boundary: object-level delete verified on Windows only; POSIX is
the documented safe-preservation path, exercised via the
_delete_object_via_pin seam."""

import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import sys  # noqa: E402
sys.path.insert(0, str(Path(__file__).resolve().parent))

import r9_remediation_integration_test as r9  # noqa: E402
import run_g2 as rg  # noqa: E402

sha256 = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()  # noqa: E731

FOREIGN_BODY = "foreign-created-after-pin-close"


def _swap_at_release_seam(staging_filter, fail_publish=False):
    """Drive the REAL human.main.  The swap is attempted at the tightest
    seam: when the product's release for the result staging object RETURNS
    (pin really closed, protection gone).  Two outcomes are both valid and
    asserted separately:
      - "name already gone": the object-level removal completed with the
        close, so the writer cannot displace our object at all;
      - "swap landed": a foreign object occupies the staging name; the
        product must finish without deleting/moving it."""
    real_release = rg.OutputPlan._release_owned
    real_publish = rg.OutputPlan._exclusive_publish
    probe: dict = {}
    active: dict = {}

    def maybe_fail(plan, target, part):
        if fail_publish and target.name == "human.result.json" \
                and not probe.get("failed_once"):
            probe["failed_once"] = True
            raise OSError("synthetic publish failure for real cleanup path")
        return real_publish(plan, target, part)

    def watched_release(plan, path, *, remove):
        rec = plan.owned_tmp.get(path)
        watched = (rec is not None and remove and staging_filter(path)
                   and not probe.get("attempted"))
        if watched:
            active.update(path=Path(path), ident=rec["ident"])
            probe["attempted"] = True
        result = real_release(plan, path, remove=remove)
        if watched:
            p = active["path"]
            old_id = active["ident"]
            # real close has happened inside the release: protection gone
            if not p.exists():
                # our object was already removed by the handle disposition;
                # the reviewer's interleave cannot displace it
                probe["swap_unconstructable"] = True
                probe["old_id"] = list(old_id)
            else:
                # name still present after close (e.g. disposition failed):
                # plant the foreign object; the product must never delete it
                backup = p.with_name(p.name + ".own-displaced")
                os.rename(str(p), str(backup))
                with p.open("x", encoding="utf-8") as f:
                    f.write(FOREIGN_BODY)
                probe.update(swapped=True, path=str(p), old_id=list(old_id),
                             own_backup=str(backup),
                             foreign_id=list(rg.OutputPlan._path_identity(p)),
                             foreign_sha=sha256(p),
                             own_backup_sha=sha256(backup))
                assert tuple(probe["old_id"]) != tuple(probe["foreign_id"])
            active.clear()
        return result

    with mock.patch.object(rg.OutputPlan, "_release_owned", watched_release), \
         mock.patch.object(rg.OutputPlan, "_exclusive_publish", maybe_fail), \
         mock.patch("builtins.print"):
        out = r9.live_run(interactive=True)
    return out, probe


class TestR14CloseThenSwapRealMain(unittest.TestCase):
    """Real human.main -> judge -> finalize -> release/cleanup with the
    swap attempted exactly when the pin protection is gone."""

    @unittest.skipUnless(os.name == "nt", "object-level delete verified on Windows")
    def test_close_time_swap_success_path(self):
        out, probe = _swap_at_release_seam(
            lambda p: p.name.startswith("human.result.json."), fail_publish=False)
        d = Path(out["dir"])
        res = d / "human.result.json"
        man = d / "human.manifest.json"
        self.assertTrue(probe.get("attempted"), "release seam must be reached")
        self.assertEqual(out["rc"], 0, out["result"].get("verdict"))
        self.assertEqual(out["result"]["status"], "pass")
        # normal success contract intact
        self.assertTrue(man.is_file())
        m = json.loads(man.read_text(encoding="utf-8"))
        self.assertEqual(m.get("result_sha256"), sha256(res))
        self.assertEqual(m.get("raw_sha256"), out["result"]["evidence"]["sha256"])
        if probe.get("swapped"):
            # a swap DID land: the foreign object must survive untouched
            self.assertTrue(Path(probe["path"]).exists())
            self.assertEqual(Path(probe["path"]).read_text(encoding="utf-8"),
                             FOREIGN_BODY)
            self.assertTrue(Path(probe["own_backup"]).exists())
            self.assertNotEqual(probe["own_backup_sha"], probe["foreign_sha"])
        else:
            # the object-level removal completed with the close: the name
            # was already gone, the reviewer's interleave cannot occur
            self.assertTrue(probe.get("swap_unconstructable"),
                            f"probe={probe}")
            self.assertFalse(d.glob("human.result.json.*.part") and
                             any(p.name.endswith(".part") and
                                 p.read_text(encoding="utf-8") == FOREIGN_BODY
                                 for p in d.glob("human.result.json.*.part")))

    @unittest.skipUnless(os.name == "nt", "object-level delete verified on Windows")
    def test_close_time_swap_failure_path(self):
        out, probe = _swap_at_release_seam(
            lambda p: p.name.startswith("human.result.json."), fail_publish=True)
        d = Path(out["dir"])
        self.assertTrue(probe.get("attempted"))
        self.assertNotEqual(out["rc"], 0)
        self.assertEqual(out["result"]["status"], "fail")
        self.assertEqual(out["result"]["verdict"], "STORAGE_FINALIZE_FAILED")
        res = d / "human.result.json"
        self.assertTrue(res.is_file(), "downgraded result must be on disk")
        body = json.loads(res.read_text(encoding="utf-8"))
        self.assertNotEqual(body.get("status"), "pass")
        self.assertNotEqual(body.get("verdict"), "HUMAN_OBSERVE_PASS")
        man = d / "human.manifest.json"
        m = json.loads(man.read_text(encoding="utf-8"))
        self.assertNotEqual(m.get("verdict"), "HUMAN_OBSERVE_PASS")
        if probe.get("swapped"):
            self.assertTrue(Path(probe["path"]).exists())
            self.assertEqual(Path(probe["path"]).read_text(encoding="utf-8"),
                             FOREIGN_BODY)
            self.assertTrue(Path(probe["own_backup"]).exists())

    def test_foreign_object_at_freed_name_survives(self):
        """A foreign object occupying the freed staging name AFTER the
        release is never touched by the product (real main, both paths)."""
        for fail_publish in (False, True):
            with self.subTest(fail_publish=fail_publish):
                real_release = rg.OutputPlan._release_owned
                real_publish = rg.OutputPlan._exclusive_publish
                probe: dict = {}

                def maybe_fail(plan, target, part):
                    if fail_publish and target.name == "human.result.json" \
                            and not probe.get("failed_once"):
                        probe["failed_once"] = True
                        raise OSError("synthetic publish failure")
                    return real_publish(plan, target, part)

                def watched_release(plan, path, *, remove):
                    result = real_release(plan, path, remove=remove)
                    p = Path(path)
                    if (p.name.startswith("human.result.json.")
                            and p.name.endswith(".part")
                            and not p.exists() and not probe.get("planted")):
                        # the name is freed by the object-level removal:
                        # a late writer claims it
                        probe["planted"] = str(p)
                        with p.open("x", encoding="utf-8") as f:
                            f.write(FOREIGN_BODY)
                    return result

                with mock.patch.object(rg.OutputPlan, "_release_owned",
                                       watched_release), \
                     mock.patch.object(rg.OutputPlan, "_exclusive_publish",
                                       maybe_fail), \
                     mock.patch("builtins.print"):
                    out = r9.live_run(interactive=True)
                self.assertTrue(probe.get("planted"),
                                "the staging name must have been freed and re-claimed")
                self.assertTrue(Path(probe["planted"]).exists(),
                                "late foreign object must survive cleanup")
                self.assertEqual(Path(probe["planted"]).read_text(encoding="utf-8"),
                                 FOREIGN_BODY)
                if fail_publish:
                    self.assertNotEqual(out["rc"], 0)
                    self.assertEqual(out["result"]["verdict"],
                                     "STORAGE_FINALIZE_FAILED")
                else:
                    self.assertEqual(out["rc"], 0)
                    self.assertEqual(out["result"]["verdict"], "HUMAN_OBSERVE_PASS")


class TestR14DeferredCleanupBranch(unittest.TestCase):
    """No object-level delete available (the documented POSIX posture, via
    the _delete_object_via_pin seam): the staging file is PRESERVED and
    reported - never removed by a pathname unlink."""

    @staticmethod
    def _make_owned_part(td, name="t.result.json"):
        plan = rg.OutputPlan.from_raw_target(Path(td) / "t.jsonl")
        plan._part_seq += 1
        part = Path(td) / f"{name}.{plan.reservation_id[:8]}.{plan._part_seq}.part"
        fd = plan._open_owned_part(part)
        os.write(fd, b"{}")  # write through OUR fd: the pin forbids new handles
        os.close(fd)
        return plan, part

    def test_unit_deferred_cleanup_preserves_staging(self):
        with tempfile.TemporaryDirectory(prefix="r14-def-") as td:
            plan, part = self._make_owned_part(td)
            with mock.patch.object(rg.OutputPlan, "_delete_object_via_pin",
                                   return_value=False):
                self.assertEqual(plan._release_owned(part, remove=True),
                                 "cleanup-deferred")
            self.assertTrue(part.exists(), "deferred cleanup must preserve the file")
            self.assertTrue(any("cleanup deferred" in s for s in plan.preserved_foreign),
                            plan.preserved_foreign)
            self.assertEqual(plan.owned_tmp, {}, "pin must still be closed")

    def test_unit_no_pathname_unlink_after_close(self):
        """Structural guard for the exact R13 bug: when a delete request
        cannot be honored, NO pathname unlink may run from _release_owned."""
        with tempfile.TemporaryDirectory(prefix="r14-nol-") as td:
            plan, part = self._make_owned_part(td)
            unlink_calls = []
            real_unlink = os.unlink

            def spy_unlink(path, *a, **kw):
                unlink_calls.append(str(path))
                return real_unlink(path, *a, **kw)

            with mock.patch.object(rg.OutputPlan, "_delete_object_via_pin",
                                   return_value=False), \
                 mock.patch.object(os, "unlink", spy_unlink):
                plan._release_owned(part, remove=True)
            self.assertNotIn(str(part), unlink_calls,
                             "_release_owned must not pathname-unlink")
            self.assertTrue(part.exists())


class TestR14ObjectLevelDeleteProperties(unittest.TestCase):
    """Verified object-level removal properties on Windows."""

    @unittest.skipUnless(os.name == "nt", "Win32 disposition semantics")
    def test_disposition_keeps_hardlinked_target(self):
        with tempfile.TemporaryDirectory(prefix="r14-dis-") as td:
            dst = Path(td) / "t.result.json"
            plan = rg.OutputPlan.from_raw_target(Path(td) / "t.jsonl")
            plan.finalize_file(dst, '{"our":"pass"}')
            self.assertEqual(dst.read_text(encoding="utf-8"), '{"our":"pass"}')
            self.assertEqual(list(Path(td).glob("*.part")), [])
            self.assertEqual(plan.owned_tmp, {})
            removals = [r for r in plan._closed_handles if r.get("removed")]
            self.assertTrue(removals, "staging object must be removed by handle")
            self.assertTrue(all(r["path"].endswith(".part") for r in removals))

    def test_unlink_blocked_while_pinned_control(self):
        """Positive control: while the pin is held the path still cannot be
        unlinked/replaced on Windows (the OS-level half of the guarantee)."""
        with tempfile.TemporaryDirectory(prefix="r14-blk-") as td:
            plan = rg.OutputPlan.from_raw_target(Path(td) / "t.jsonl")
            plan._part_seq += 1
            part = Path(td) / f"t.result.json.{plan.reservation_id[:8]}.{plan._part_seq}.part"
            fd = plan._open_owned_part(part)
            os.close(fd)  # close the writable stream; the PIN stays open
            try:
                part.unlink()
                blocked = False
            except PermissionError:
                blocked = True
            self.assertTrue(blocked, "pinned path must be un-replaceable on Windows")
            self.assertEqual(plan._release_owned(part, remove=True), "removed")
            self.assertFalse(part.exists())
            self.assertEqual(plan.owned_tmp, {})

    def test_check_before_replacement_preserved(self):
        """Replacement BEFORE the identity check: preserve, never delete."""
        with tempfile.TemporaryDirectory(prefix="r14-pre-") as td:
            plan = rg.OutputPlan.from_raw_target(Path(td) / "t.jsonl")
            plan._part_seq += 1
            part = Path(td) / f"t.result.json.{plan.reservation_id[:8]}.{plan._part_seq}.part"
            fd = plan._open_owned_part(part)
            os.write(fd, b"{}")
            os.close(fd)
            real_identity = rg.OutputPlan._path_identity
            with mock.patch.object(rg.OutputPlan, "_path_identity",
                                   staticmethod(lambda p: ((0, 999999)
                                                           if Path(p) == part
                                                           else real_identity(p)))):
                self.assertEqual(plan._release_owned(part, remove=True),
                                 "preserved-foreign")
            self.assertTrue(part.exists())
            self.assertTrue(any("preserved unattributable" in s
                                for s in plan.preserved_foreign))


class TestR14NormalContractIntact(unittest.TestCase):
    """The full-write-then-publish, no-overwrite and exclusive properties
    must be unchanged by the R14 deletion redesign."""

    def test_normal_publish_full_chain(self):
        with tempfile.TemporaryDirectory(prefix="r14-ok-") as td:
            dst = Path(td) / "t.result.json"
            plan = rg.OutputPlan.from_raw_target(Path(td) / "t.jsonl")
            plan.finalize_file(dst, '{"our":"pass"}')
            self.assertEqual(dst.read_text(encoding="utf-8"), '{"our":"pass"}')
            self.assertEqual(list(Path(td).glob("*.part")), [])
            self.assertEqual(plan.owned_tmp, {})

    def test_target_race_creator_preserved(self):
        with tempfile.TemporaryDirectory(prefix="r14-race-") as td:
            dst = Path(td) / "t.result.json"
            plan = rg.OutputPlan.from_raw_target(Path(td) / "t.jsonl")
            dst.write_text('{"foreign":"won"}', encoding="utf-8")
            with self.assertRaises(FileExistsError):
                plan.finalize_file(dst, '{"our":"pass"}')
            self.assertEqual(dst.read_text(encoding="utf-8"), '{"foreign":"won"}')
            plan.cleanup_unfinalized()
            self.assertEqual(list(Path(td).glob("*.part")), [])

    def test_write_failure_self_cleanup(self):
        with tempfile.TemporaryDirectory(prefix="r14-wr-") as td:
            dst = Path(td) / "t.result.json"
            plan = rg.OutputPlan.from_raw_target(Path(td) / "t.jsonl")
            with mock.patch("os.fsync", side_effect=OSError("disk full")):
                with self.assertRaises(OSError):
                    plan.finalize_file(dst, '{"our":"pass"}')
            self.assertFalse(dst.exists())
            self.assertEqual(plan.owned_tmp, {})

    def test_interrupt_releases_pins_publishes_nothing(self):
        with tempfile.TemporaryDirectory(prefix="r14-int-") as td:
            dst = Path(td) / "t.result.json"
            plan = rg.OutputPlan.from_raw_target(Path(td) / "t.jsonl")
            with mock.patch.object(rg.OutputPlan, "_exclusive_publish",
                                   side_effect=KeyboardInterrupt("interrupted")):
                with self.assertRaises(KeyboardInterrupt):
                    plan.finalize_file(dst, '{"status":"pass"}')
            self.assertFalse(dst.exists())
            self.assertEqual(plan.owned_tmp, {}, "pins released on interrupt")

    def test_real_main_normal_contract(self):
        out = r9.live_run(interactive=True)
        self.assertEqual(out["rc"], 0, out["result"].get("verdict"))
        self.assertEqual(out["result"]["verdict"], "HUMAN_OBSERVE_PASS")
        d = Path(out["dir"])
        self.assertEqual(list(d.glob("*.part")), [], "no staging residue")


if __name__ == "__main__":
    unittest.main(verbosity=1)
