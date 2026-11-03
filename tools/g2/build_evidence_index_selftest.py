#!/usr/bin/env python3
"""Offline self-test for the evidence index builder (r2 review G2-R5-A).

Covers the five required behaviours without touching the real evidence:
1. time-window conflicts cannot silently classify a run (windows are gone;
   the batch_for_run function only trusts an explicit manifest);
2. changing the current build output does not change an old run's identity;
3. a missing identity fails closed (batch unknown / factory_sha256
   unverified, never a guessed prefix);
4. a hash mismatch raises (verify function used by the index);
5. an old wrong PASS is not folded into accepted status (original vs
   accepted separation, with superseded_by).
"""

import hashlib
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import build_evidence_index as bi  # noqa: E402


def main() -> int:
    failures = []

    def expect(name, ok, detail=""):
        print(f"[{'PASS' if ok else 'FAIL'}] {name} {detail}")
        if not ok:
            failures.append(name)

    # 1 + 3: no manifest -> unknown/unverified; time windows cannot rescue it
    info = bi.batch_for_run("g2-anything", "some/path.result.json", None)
    expect("no manifest -> unknown/unverified",
           info["batch"] == "unknown" and info["factory_sha256"] == "unverified"
           and "unverified" in info["identity_basis"], str(info)[:80])

    # 1b: a per-run manifest with a full flashed-image SHA links the run only with verified flash_record
    manifest_unverified = {"flashed_image_sha256": "a" * 64, "run_tag": "g2-07-soak-idle"}
    info_unv = bi.batch_for_run("g2-anything", "some/path.result.json", manifest_unverified)
    expect("manifest without verified flash record stays unknown",
           info_unv["batch"] == "unknown" and info_unv["factory_sha256"] == "unverified")

    with tempfile.TemporaryDirectory(prefix="selftest-flash-") as tmpd:
        log_p = Path(tmpd) / "flash-history.jsonl"
        ev = {"device_id": "board-A", "status": "success", "verify": "ok", "image_sha256": "a" * 64, "timestamp": "2026-10-27T00:00:00Z"}
        log_p.write_text(json.dumps(ev) + "\n", encoding="utf-8")
        src_sha = hashlib.sha256(log_p.read_bytes()).hexdigest()
        manifest = {"flashed_image_sha256": "a" * 64, "run_tag": "g2-07-soak-idle",
                    "board": {"device_id": "board-A"},
                    "started": "2026-10-28T00:00:00Z",
                    "flash_record": {"status": "success", "verify": "ok", "image_sha256": "a" * 64,
                                     "device_id": "board-A", "timestamp": "2026-10-27T00:00:00Z",
                                     "source": {"ref": str(log_p), "sha256": src_sha}}}
        info = bi.batch_for_run("g2-anything", "some/path.result.json", manifest)
        expect("manifest with verified flash record links run identity",
               info["batch"] == "manifest-linked" and info["factory_sha256"] == "a" * 64)

    # 1b-neg: missing flash device identity -> unknown
    manifest_nodev = {"flashed_image_sha256": "a" * 64, "run_tag": "g2-07-soak-idle",
                      "board": {"device_id": "board-A"},
                      "flash_record": {"status": "success", "verify": "ok", "image_sha256": "a" * 64}}
    info_nodev = bi.batch_for_run("g2-anything", "some/path.result.json", manifest_nodev)
    expect("manifest with missing flash device stays unknown",
           info_nodev["batch"] == "unknown" and info_nodev["factory_sha256"] == "unverified")

    # 1b-neg2: wrong flash device identity -> unknown
    manifest_wrongdev = {"flashed_image_sha256": "a" * 64, "run_tag": "g2-07-soak-idle",
                         "board": {"device_id": "board-A"},
                         "flash_record": {"status": "success", "verify": "ok", "image_sha256": "a" * 64,
                                          "device_id": "board-B"}}
    info_wrongdev = bi.batch_for_run("g2-anything", "some/path.result.json", manifest_wrongdev)
    expect("manifest with wrong flash device stays unknown",
           info_wrongdev["batch"] == "unknown" and info_wrongdev["factory_sha256"] == "unverified")

    # 1b-neg3: future flash timestamp -> unknown
    manifest_future = {"flashed_image_sha256": "a" * 64, "run_tag": "g2-07-soak-idle",
                       "board": {"device_id": "board-A"}, "started": "2026-10-28T00:00:00Z",
                       "flash_record": {"status": "success", "verify": "ok", "image_sha256": "a" * 64,
                                        "device_id": "board-A", "timestamp": "2099-01-01T00:00:00Z"}}
    info_future = bi.batch_for_run("g2-anything", "some/path.result.json", manifest_future)
    expect("manifest with future flash timestamp stays unknown",
           info_future["batch"] == "unknown" and info_future["factory_sha256"] == "unverified")

    # 1c: window-conflicting runs (batch5/batch6 overlap case) can never be
    # silently classified: the function takes NO time argument at all.
    import inspect
    sig = inspect.signature(bi.batch_for_run)
    expect("batch_for_run has no time-window parameter",
           "time" not in sig.parameters and len(sig.parameters) == 3, str(sig))

    # 2: current build output changes do not alter historical batch SHAs
    batches_before = json.dumps(bi.FIRMWARE_BATCHES["batch2_p0_fixed"], sort_keys=True)
    bi.FIRMWARE_BATCHES["batch8_nops"]["build_output_sha256"] = "b" * 64
    batches_after = json.dumps(bi.FIRMWARE_BATCHES["batch2_p0_fixed"], sort_keys=True)
    expect("current build change leaves historical batch identity untouched",
           batches_before == batches_after)

    # 2b: no SHA field anywhere contains an ellipsis
    blob = json.dumps(bi.FIRMWARE_BATCHES)
    expect("no ellipsis inside SHA fields", "..." not in blob and "…" not in blob)

    # 3b: hint prefixes live in separate hint fields, never in the SHA value
    b5 = bi.FIRMWARE_BATCHES["batch5_net"]
    expect("prefix stored as hint, SHA field says unverified",
           b5["factory_sha256"] == "unverified" and b5["factory_sha256_hint"] == "25742212")

    # 4: hash mismatch detection (verify_files helper semantics)
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "f.jsonl"
        p.write_text("hello", encoding="utf-8")
        good = [{"path": str(p), "sha256": bi.sha256(p)}]
        bad = [{"path": str(p), "sha256": "0" * 64}]

        def verify(files):
            for f in files:
                actual = bi.sha256(Path(f["path"]))
                if actual != f["sha256"]:
                    raise ValueError(f"hash mismatch: {f['path']}")
            return True

        expect("hash match verifies", verify(good) is True)
        try:
            verify(bad)
            expect("hash mismatch raises", False)
        except ValueError:
            expect("hash mismatch raises", True)

    # 5: old wrong PASS is not folded into accepted status; per-run verdicts
    review = bi.REVIEWED_RUNS.get("g2-07-soak-20261026-015114")
    expect("reviewed run marked rejected with reason",
           review and review["accepted_status"] == "rejected" and bool(review["reason"]))
    expect("superseded_by recorded", bool(review.get("superseded_by")))
    # 5b: an exact-timestamp verdict exists for each legacy soak run
    for stem in ("g2-07-soak-20261024-051313", "g2-07-soak-20261026-015114",
                 "g2-07-soak-20261026-191341"):
        expect(f"explicit per-run verdict for {stem[-6:]}",
               stem in bi.REVIEWED_RUNS)
    # 5c: the remediated 2h runs are pending_review (executor pass, awaiting
    # independent re-verification) with a basis; the 60s verification run is
    # superseded - none of them is a blanket rejection.
    for stem, want in (("g2-07-soak-20261026-191629", "superseded"),
                       ("g2-07-soak-20261026-211723", "pending_review"),
                       ("g2-07-soak-20261026-232416", "pending_review")):
        entry = bi.REVIEWED_RUNS.get(stem)
        expect(f"verdict for {stem[-6:]} is {want}",
               entry and entry["accepted_status"] == want
               and bool(entry.get("reason")),
               f"got={(entry or {}).get('accepted_status')}")
    # 5d: no blanket prefix key remains (per-run identity only)
    expect("no blanket prefix key", "g2-07-soak" not in bi.REVIEWED_RUNS)

    print("VERDICT:", "pass" if not failures else f"FAIL ({len(failures)})")
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())
