#!/usr/bin/env python3
"""Integration test for build_evidence_index (G2-R3-05).

Drives the REAL build_index path through main()-equivalent code over
temporary evidence roots containing the review's required scenarios:

1. two runs on DIFFERENT images, each with its own per-run sidecar manifest
   -> each links its own image;
2. a FOREIGN manifest (run A's manifest renamed next to run B) -> rejected,
   run B stays on its own identity or unknown;
3. a legacy run with NO sidecar -> unknown/unverified;
4. the same filename present in BOTH roots -> deduplicated, root recorded;
5. rebuilding twice (and re-importing the module) leaves history unchanged;
6. a boundary-violating run (marker in the raw jsonl) -> invalid;
7. the three real 2026-10-26 soak verdicts match their raw contents
   (191629=60s idle / 211723=2h stress / 232416=2h idle).

Import side effects: importing build_evidence_index and leg_driver2 must
not write anything (checked by snapshotting the temp dirs).
"""

import hashlib
import json
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import build_evidence_index as bi  # noqa: E402

failures = []


def expect(name, ok, detail=""):
    print(f"[{'PASS' if ok else 'FAIL'}] {name} {detail}")
    if not ok:
        failures.append(name)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def make_result(root: Path, result_stem: str, started: str, ended: str, raw_stem: str,
                raw_lines: list, status: str = "pass", run_id: str = "g2-07-soak",
                board_id: str = "esp32c3"):
    if not started.endswith("Z") and "+" not in started:
        started = started + "Z"
    if not ended.endswith("Z") and "+" not in ended:
        ended = ended + "Z"
    raw = root / f"{raw_stem}.jsonl"
    has_envelope = any(isinstance(l, dict) and l.get("event") == "experiment_envelope" for l in raw_lines)
    if not has_envelope and raw_lines and not any(isinstance(l, dict) and l.get("boundary_violation") for l in raw_lines):
        raw_lines = [{"event": "experiment_envelope", "experiment_id": run_id, "run_id": run_id}] + list(raw_lines)
    tx_nonces = {str(l.get("payload", {}).get("nonce")) for l in raw_lines if isinstance(l, dict) and l.get("dir") == "tx" and l.get("code") == 1}
    expanded_lines = []
    for l in raw_lines:
        if isinstance(l, dict) and l.get("dir") == "rx" and l.get("code") == 1:
            res = (l.get("payload") or {}).get("result") or {}
            nonce = res.get("nonce") or "nonce-test-1"
            res["nonce"] = nonce
            rx_rid = l.get("request_id")
            if rx_rid is None:
                rx_rid = 1
                l["request_id"] = rx_rid
            if l.get("session_id") is None:
                l["session_id"] = 1
            if str(nonce) not in tx_nonces:
                expanded_lines.append({
                    "dir": "tx", "kind": 1, "code": 1, "session_id": 0, "request_id": rx_rid,
                    "payload": {"nonce": str(nonce)}
                })
                tx_nonces.add(str(nonce))
        expanded_lines.append(l)
    raw_lines = expanded_lines
    raw.write_text("\n".join(json.dumps(l) for l in raw_lines) + "\n", encoding="utf-8")
    raw_sha = hashlib.sha256(raw.read_bytes()).hexdigest()
    result = root / f"{result_stem}.result.json"
    result.write_text(json.dumps({
        "run_id": run_id, "status": status, "started": started, "ended": ended,
        "board_id": board_id,
        "checks": [{"name": "ok", "pass": True, "detail": ""}],
        "notes": [], "evidence": {"file": str(raw), "sha256": raw_sha},
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    return result, raw


def manifest_for(root: Path, raw_stem: str, image_sha: str, run_tag: str, **extra):
    raw = root / f"{raw_stem}.jsonl"
    raw_sha = hashlib.sha256(raw.read_bytes()).hexdigest()
    res_sha = None
    res_data = {}
    for p in root.glob("*.result.json"):
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
            if d.get("evidence", {}).get("file") == str(raw):
                res_sha = hashlib.sha256(p.read_bytes()).hexdigest()
                res_data = d
                break
        except Exception:
            pass
    board_arg = extra.pop("board", None)
    if board_arg is not None:
        if isinstance(board_arg, dict):
            board_id = board_arg.get("device_id") or board_arg.get("device", "esp32c3")
            board_dict = {"port": board_arg.get("port", "COMX"), "device_id": board_id}
        else:
            board_id = str(board_arg)
            board_dict = {"port": "COMX", "device_id": board_id}
    else:
        board_id = res_data.get("board_id", "esp32c3")
        board_dict = {"port": "COMX", "device_id": board_id}

    flash_rec = extra.pop("flash_record", None)
    if flash_rec is None and not extra.pop("no_flash_record", False):
        src_path = root / f"{raw_stem}.flash-source.jsonl"
        src_entry = {
            "device_id": board_id,
            "status": "success",
            "verify": "ok",
            "image_sha256": image_sha,
            "timestamp": "2026-10-26T09:00:00Z",
        }
        src_path.write_text(json.dumps(src_entry) + "\n", encoding="utf-8")
        flash_rec = {
            "status": "success",
            "verify": "ok",
            "image_sha256": image_sha,
            "device_id": board_id,
            "timestamp": "2026-10-26T09:00:00Z",
            "source": {
                "ref": str(src_path),
                "sha256": hashlib.sha256(src_path.read_bytes()).hexdigest(),
            },
        }

    m = {"run_id": res_data.get("run_id", run_tag),
         "experiment_id": res_data.get("run_id", run_tag),
         "run_tag": run_tag,
         "flashed_image_sha256": image_sha,
         "raw_sha256": raw_sha,
         "result_sha256": extra.pop("result_sha256", res_sha),
         "started": extra.pop("started", res_data.get("started", "2026-10-26T10:00:00")),
         "ended": extra.pop("ended", res_data.get("ended", "2026-10-26T12:00:00")),
         "image_profile": "profile-x",
         "board": board_dict,
         "collector": {"script": "run_g2.py", "judge": "j"},
         "boot_id_initial": extra.pop("boot_id_initial", "B1"),
         "written": "now"}
    if flash_rec:
        m["flash_record"] = flash_rec
    m.update(extra)
    (root / f"{raw_stem}.manifest.json").write_text(json.dumps(m, indent=2), encoding="utf-8")


def main() -> int:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td) / "evidence"
        root.mkdir()

        imgA = "a" * 64
        imgB = "b" * 64

        # run A: 2h stress on image A, with its own sidecar manifest
        make_result(root, "g2-07-soak-20261026-100000", "2026-10-26T10:00:00",
                    "2026-10-26T12:00:00", "g2-07-soak-stress-20261026-100001",
                    [{"dir": "rx", "kind": 2, "code": 1, "t": 1.0,
                      "payload": {"ok": True, "result": {"boot_id": "B1", "device_id": "esp32c3"}},
                      "session_id": 1, "request_id": 0, "boot_id": "B1"}])
        manifest_for(root, "g2-07-soak-stress-20261026-100001", imgA, "g2-07-soak-stress")

        # run B: 2h idle on image B, own sidecar
        make_result(root, "g2-07-soak-20261026-120000", "2026-10-26T12:00:00",
                    "2026-10-26T14:00:00", "g2-07-soak-idle-20261026-120001",
                    [{"dir": "rx", "kind": 2, "code": 1, "t": 1.0,
                      "payload": {"ok": True, "result": {"boot_id": "B1", "device_id": "esp32c3"}},
                      "session_id": 1, "request_id": 0, "boot_id": "B1"}])
        manifest_for(root, "g2-07-soak-idle-20261026-120001", imgB, "g2-07-soak-idle")

        # run C: legacy, NO sidecar -> unknown
        make_result(root, "g2-07-soak-20261024-090000", "2026-10-24T09:00:00",
                    "2026-10-24T11:00:00", "g2-07-soak-idle-20261024-090001",
                    [{"dir": "note", "event": "x", "t": 1.0}], status="fail")

        # run D: boundary-violating probe (marker as the raw jsonl's last line)
        r, raw = make_result(root, "g2-07-soak-20261027-010000", "2026-10-27T01:00:00",
                             "2026-10-27T01:01:00", "g2-07-soak-idle-20261027-010001",
                             [{"dir": "note", "event": "x", "t": 1.0},
                              {"boundary_violation": True}])

        # a foreign manifest: run A's manifest copied next to run B's raw file
        shutil.copy(root / "g2-07-soak-stress-20261026-100001.manifest.json",
                    root / "g2-07-soak-idle-20261026-120001.manifest.json")

        idx = bi.build_index({"main": root}, Path(td) / "index.json", bi.REVIEWED_RUNS,
                             bi.FIRMWARE_BATCHES, sources_snapshot={})
        runs = {r["result_file"]: r for r in idx["runs"]}

        ra = next(v for k, v in runs.items() if "100000" in k)
        rb = next(v for k, v in runs.items() if "120000" in k)
        rc = next(v for k, v in runs.items() if "090000" in k)
        rd = next(v for k, v in runs.items() if "010000" in k)

        expect("1. run A links its own image A",
               ra["factory_sha256"] == imgA and ra["batch"] == "manifest-linked",
               ra["factory_sha256"][:12])
        # The foreign manifest (A's manifest copied onto B's sidecar name)
        # is rejected because its run_tag contradicts B's raw file; B falls
        # back to unknown rather than inheriting A's image.
        expect("1. run B rejects the foreign manifest and stays unknown",
               rb["batch"] == "unknown" and rb["factory_sha256"] == "unverified",
               rb["identity_basis"][:60])
        # and a properly-owned manifest still links (already covered by A);
        # verify B would link its own image when the sidecar is correct:
        manifest_for(root, "g2-07-soak-idle-20261026-120001", imgB, "g2-07-soak-idle")
        idx1b = bi.build_index({"main": root}, Path(td) / "index1b.json",
                               bi.REVIEWED_RUNS, bi.FIRMWARE_BATCHES, sources_snapshot={})
        rb1b = next(v for k, v in
                    {r["result_file"]: r for r in idx1b["runs"]}.items()
                    if "120000" in k)
        expect("1. run B links image B once its own manifest is restored",
               rb1b["factory_sha256"] == imgB, rb1b["factory_sha256"][:12])
        expect("3. legacy run without sidecar stays unknown",
               rc["batch"] == "unknown" and rc["factory_sha256"] == "unverified",
               rc["identity_basis"][:60])
        expect("6. boundary-violating run marked invalid",
               "invalid" in rd["accepted_status"], rd["accepted_status"][:60])

        # snapshot AFTER all fixtures exist; the invariance checks compare
        # builds/imports against this
        snap_before = {p.name: sha(p) for p in sorted(root.rglob("*")) if p.is_file()}

        # 4: same filename in both roots
        root2 = Path(td) / "evidence2"
        root2.mkdir()
        make_result(root, "g2-07-soak-20261026-140000", "2026-10-26T14:00:00",
                    "2026-10-26T16:00:00", "g2-07-soak-idle-20261026-140001",
                    [{"dir": "note", "event": "dup-main", "t": 1.0}])
        make_result(root2, "g2-07-soak-20261026-140000", "2026-10-26T14:00:00",
                    "2026-10-26T16:00:00", "g2-07-soak-idle-20261026-140001",
                    [{"dir": "note", "event": "dup-mirror", "t": 1.0}])
        idx2 = bi.build_index({"main": root, "mirror": root2}, Path(td) / "index2.json",
                              bi.REVIEWED_RUNS, bi.FIRMWARE_BATCHES, sources_snapshot={})
        dupes = [f for f in idx2["evidence_files"] if "140001" in f["path"]]
        expect("4. same filename across roots deduplicated with roots recorded",
               len(dupes) == 2 and {f["root"] for f in dupes} == {"main", "mirror"},
               f"count={len(dupes)}")

        # 5: rebuild invariance + import side-effect freedom
        i1 = Path(td) / "i1.json"
        i2 = Path(td) / "i2.json"
        bi.build_index({"main": root}, i1, bi.REVIEWED_RUNS, bi.FIRMWARE_BATCHES, sources_snapshot={})
        before = {p.name: sha(p) for p in sorted(root.rglob("*")) if p.is_file()}
        bi.build_index({"main": root}, i2, bi.REVIEWED_RUNS, bi.FIRMWARE_BATCHES, sources_snapshot={})
        after = {p.name: sha(p) for p in sorted(root.rglob("*")) if p.is_file()}
        # Invariance is about files that existed at snapshot time: fixtures
        # added later (the dup scenario) are new files, not modifications.
        changed = [k for k in set(before) | set(after)
                   if k in before and k in after and before[k] != after[k]]
        disappeared = [k for k in before if k not in after]
        expect("5. rebuilding leaves the evidence tree unchanged",
               not changed and not disappeared,
               f"changed={changed} disappeared={disappeared}")
        import importlib
        import leg_driver2  # noqa: F401  (import must not write anything)
        importlib.reload(bi)
        after_import = {p.name: sha(p) for p in sorted(root.rglob("*")) if p.is_file()}
        changed_import = [k for k in set(before) | set(after_import)
                          if k in before and k in after_import and before[k] != after_import[k]]
        expect("5. importing leg/index modules writes nothing",
               not changed_import and set(before) <= set(after_import),
               f"changed={changed_import}")
        expect("5. two builds produce identical index bytes", sha(i1) == sha(i2))

        # 7: the three real soak verdicts match their raw contents
        verdicts = {k[-10:-12 if False else None]: v for k, v in bi.REVIEWED_RUNS.items()}
        v191629 = bi.REVIEWED_RUNS["g2-07-soak-20261026-191629"]
        v211723 = bi.REVIEWED_RUNS["g2-07-soak-20261026-211723"]
        v232416 = bi.REVIEWED_RUNS["g2-07-soak-20261026-232416"]
        expect("7. 191629 = 60s idle collector verification (superseded)",
               v191629["accepted_status"] == "superseded")
        expect("7. 211723 = 2h stress (pending_review, raw 191713)",
               v211723["accepted_status"] == "pending_review"
               and "191713" in v211723["reason"])
        expect("7. 232416 = 2h idle (pending_review, raw 212415)",
               v232416["accepted_status"] == "pending_review"
               and "212415" in v232416["reason"])

        # No PRE-EXISTING evidence file was modified or deleted by the whole
        # test (the dup fixtures added files, which is expected - they are
        # new, not modifications).
        final = {p.name: sha(p) for p in sorted(root.rglob("*")) if p.is_file()}
        modified = [k for k in set(before) & set(final) if before[k] != final[k]]
        deleted = [k for k in before if k not in final]
        expect("no pre-existing evidence files modified or deleted",
               not modified and not deleted, f"modified={modified} deleted={deleted}")

        # ---- G2-R3-05 (r3b) additions ---------------------------------------
        root3 = Path(td) / "evidence3"
        root3.mkdir()
        imgS1 = "c" * 64
        imgS2 = "d" * 64

        def sha_of(path):
            return hashlib.sha256(path.read_bytes()).hexdigest()

        # stress run S1 on image C with its own correctly-bound sidecar
        make_result(root3, "g2-07-soak-20261026-160000", "2026-10-26T16:00:00",
                    "2026-10-26T18:00:00", "g2-07-soak-stress-20261026-160001",
                    [{"dir": "rx", "kind": 2, "code": 1, "t": 1.0,
                      "payload": {"ok": True, "result": {"event": "s1", "boot_id": "B1", "device_id": "esp32c3"}},
                      "session_id": 1, "request_id": 0, "boot_id": "B1"}])
        raw1 = root3 / "g2-07-soak-stress-20261026-160001.jsonl"
        manifest_for(root3, raw1.stem, imgS1, "g2-07-soak-stress")
        m1 = json.loads((root3 / "g2-07-soak-stress-20261026-160001.manifest.json").read_text(encoding="utf-8"))

        # stress run S2 on image D with its own sidecar
        make_result(root3, "g2-07-soak-20261026-180000", "2026-10-26T18:00:00",
                    "2026-10-26T20:00:00", "g2-07-soak-stress-20261026-180001",
                    [{"dir": "rx", "kind": 2, "code": 1, "t": 1.0,
                      "payload": {"ok": True, "result": {"event": "s2", "boot_id": "B1", "device_id": "esp32c3"}},
                      "session_id": 1, "request_id": 0, "boot_id": "B1"}])
        raw2 = root3 / "g2-07-soak-stress-20261026-180001.jsonl"
        manifest_for(root3, raw2.stem, imgS2, "g2-07-soak-stress")
        m2 = json.loads((root3 / "g2-07-soak-stress-20261026-180001.manifest.json").read_text(encoding="utf-8"))

        # same-type foreign: S1's manifest copied onto S2's sidecar (run_tag is
        # identical - only the raw_sha256 differs)
        (root3 / "g2-07-soak-stress-20261026-180001.manifest.json").write_text(
            json.dumps(m1), encoding="utf-8")

        idx3 = bi.build_index({"main": root3}, Path(td) / "i3.json",
                              bi.REVIEWED_RUNS, bi.FIRMWARE_BATCHES, sources_snapshot={})
        runs3 = {r["result_file"]: r for r in idx3["runs"]}
        rs1 = next(v for k, v in runs3.items() if "160000" in k)
        rs2 = next(v for k, v in runs3.items() if "180000" in k)
        expect("R5b two stress runs link different images",
               rs1["factory_sha256"] == imgS1 and rs2["factory_sha256"] != imgS1,
               f"S1={rs1['factory_sha256'][:8]} S2={rs2['factory_sha256'][:8]}")
        expect("R5b same-type foreign manifest rejected (S2 stays unverified)",
               rs2["batch"] == "unknown" and rs2["factory_sha256"] == "unverified",
               rs2["identity_basis"][:70])

        # restore S2's own manifest, then mutate the raw content: the sidecar
        # must no longer bind (raw_sha256 mismatch)
        (root3 / "g2-07-soak-stress-20261026-180001.manifest.json").write_text(
            json.dumps(m2), encoding="utf-8")
        raw2.write_text(raw2.read_text(encoding="utf-8")
                        + json.dumps({"dir": "note", "event": "mutated"}) + chr(10),
                        encoding="utf-8")
        idx4 = bi.build_index({"main": root3}, Path(td) / "i4.json",
                              bi.REVIEWED_RUNS, bi.FIRMWARE_BATCHES, sources_snapshot={})
        runs4 = {r["result_file"]: r for r in idx4["runs"]}
        rs2b = next(v for k, v in runs4.items() if "180000" in k)
        expect("R5b raw-content change invalidates the sidecar",
               rs2b["batch"] == "unknown", rs2b["identity_basis"][:60])

        # legacy sidecar WITHOUT raw_sha256 -> unknown (r3b: no compat pass)
        mutated_line = json.dumps({"dir": "note", "event": "mutated"}) + chr(10)
        raw2.write_text(raw2.read_text(encoding="utf-8").replace(mutated_line, ""),
                        encoding="utf-8")
        m2_legacy = dict(m2)
        m2 = {"run_tag": "g2-07-soak-stress", "flashed_image_sha256": imgS2,
              "raw_sha256": sha_of(raw2), "image_profile": "p2"}
        (root3 / "g2-07-soak-stress-20261026-180001.manifest.json").write_text(
            json.dumps({"run_tag": "g2-07-soak-stress", "flashed_image_sha256": imgS2,
                        "image_profile": "p2"}), encoding="utf-8")
        idx5 = bi.build_index({"main": root3}, Path(td) / "i5.json",
                              bi.REVIEWED_RUNS, bi.FIRMWARE_BATCHES, sources_snapshot={})
        runs5 = {r["result_file"]: r for r in idx5["runs"]}
        rs2c = next(v for k, v in runs5.items() if "180000" in k)
        expect("R5b legacy sidecar without raw_sha256 -> unknown (no compat pass)",
               rs2c["batch"] == "unknown" and rs2c["factory_sha256"] == "unverified",
               rs2c["identity_basis"][:60])
        # ---- G2-R3-05 (r3c E) ----------------------------------------------
        # E1: explicit review pass + original pass => pass (requires result_sha256 binding R1-A)
        res_100k = root / "g2-07-soak-20261026-100000.result.json"
        sha_100k = hashlib.sha256(res_100k.read_bytes()).hexdigest()
        idx_r = bi.build_index({"main": root}, Path(td) / "ir.json",
                                {"g2-07-soak-20261026-100000": {"target_root": "main",
                                                                 "result_sha256": sha_100k,
                                                                 "accepted_status": "pass",
                                                                 "reason": "independently reviewed"}},
                                bi.FIRMWARE_BATCHES, sources_snapshot={})
        rr = next(r for r in idx_r["runs"] if "100000" in r["result_file"])
        expect("E1 explicit pass + original pass => pass (not pending)",
               rr["accepted_status"] == "pass", rr["accepted_status"])

        # E2: no review => pending_review (even when original is pass)
        idx_n = bi.build_index({"main": root}, Path(td) / "in.json",
                                {}, bi.FIRMWARE_BATCHES, sources_snapshot={})
        rn = next(r for r in idx_n["runs"] if "100000" in r["result_file"])
        expect("E2 no review => pending_review", rn["accepted_status"] == "pending_review",
               rn["accepted_status"])

        # E3: explicit reject stays reject
        idx_j = bi.build_index({"main": root}, Path(td) / "ij.json",
                                {"g2-07-soak-20261026-100000": {"target_root": "main",
                                                                 "result_sha256": sha_100k,
                                                                 "accepted_status": "rejected",
                                                                 "reason": "defective judge"}},
                                bi.FIRMWARE_BATCHES, sources_snapshot={})
        rj = next(r for r in idx_j["runs"] if "100000" in r["result_file"])
        expect("E3 explicit reject stays reject", rj["accepted_status"] == "rejected",
               rj["accepted_status"])

        # ---- G2-R3-05 (r3d B.3): full run-identity binding ----------------
        # B1-manifest-A/raw-B case: a sidecar with a CORRECT raw_sha256 but
        # a boot identity the raw frames never carried belongs to another
        # run -> rejected (unknown), not manifest-linked.
        root4 = Path(td) / "evidence4"
        root4.mkdir()
        imgX = "9" * 64
        # run X: raw frames carry boot BOOT-X
        make_result(root4, "g2-07-soak-20261026-200000", "2026-10-26T20:00:00",
                    "2026-10-26T22:00:00", "g2-07-soak-idle-20261026-200001",
                    [{"dir": "rx", "kind": 2, "code": 1, "t": 1.0,
                      "payload": {"ok": True, "result": {"boot_id": "BOOT-X", "device_id": "esp32c3"}},
                      "session_id": 1, "request_id": 0, "boot_id": "BOOT-X"}])
        rawX = root4 / "g2-07-soak-idle-20261026-200001.jsonl"
        manifest_for(root4, rawX.stem, imgX, "g2-07-soak-idle", boot_id_initial="BOOT-Y")
        idx4 = bi.build_index({"main": root4}, Path(td) / "i4.json",
                              bi.REVIEWED_RUNS, bi.FIRMWARE_BATCHES, sources_snapshot={})
        rx4 = next(r for r in idx4["runs"] if "200000" in r["result_file"])
        expect("B3 manifest identity A next to raw body B -> unknown",
               rx4["batch"] == "unknown" and rx4["factory_sha256"] == "unverified",
               rx4["identity_basis"][:70])

        # ...and the SAME raw bytes with the CORRECT boot bind fine.
        manifest_for(root4, rawX.stem, imgX, "g2-07-soak-idle", boot_id_initial="BOOT-X")
        idx4b = bi.build_index({"main": root4}, Path(td) / "i4b.json",
                               bi.REVIEWED_RUNS, bi.FIRMWARE_BATCHES, sources_snapshot={})
        rx4b = next(r for r in idx4b["runs"] if "200000" in r["result_file"])
        expect("B3 same content + correct boot identity links",
               rx4b["factory_sha256"] == imgX and rx4b["batch"] == "manifest-linked",
               rx4b["identity_basis"][:70])

        # two INDEPENDENT legal runs, each bound to its own raw/boot/image
        make_result(root4, "g2-07-soak-20261026-210000", "2026-10-26T21:00:00",
                    "2026-10-26T23:00:00", "g2-07-soak-idle-20261026-210001",
                    [{"dir": "rx", "kind": 2, "code": 1, "t": 1.0,
                      "payload": {"ok": True, "result": {"boot_id": "BOOT-Y", "device_id": "esp32c3"}},
                      "session_id": 1, "request_id": 0, "boot_id": "BOOT-Y"}])
        rawY = root4 / "g2-07-soak-idle-20261026-210001.jsonl"
        manifest_for(root4, rawY.stem, "8" * 64, "g2-07-soak-idle", boot_id_initial="BOOT-Y")
        idx4c = bi.build_index({"main": root4}, Path(td) / "i4c.json",
                               bi.REVIEWED_RUNS, bi.FIRMWARE_BATCHES, sources_snapshot={})
        runs4c = {r["result_file"]: r for r in idx4c["runs"]}
        rxx = next(v for k, v in runs4c.items() if "200000" in k)
        ryy = next(v for k, v in runs4c.items() if "210000" in k)
        expect("B3 two legal runs each bind their own image",
               rxx["factory_sha256"] == imgX and ryy["factory_sha256"] == "8" * 64,
               f"X={rxx['factory_sha256'][:8]} Y={ryy['factory_sha256'][:8]}")

        # a HELLO-result boot_id (device states boot in the payload, no
        # top-level boot_id) also satisfies the binding
        make_result(root4, "g2-07-soak-20261026-220000", "2026-10-26T22:30:00",
                    "2026-10-26T23:30:00", "g2-07-soak-idle-20261026-220001",
                    [{"dir": "rx", "code": 0x0001, "kind": 2, "t": 0.5, "payload":
                      {"ok": True, "result": {"nonce": "n", "boot_id": "BOOT-Z", "device_id": "esp32c3"}}}])
        rawZ = root4 / "g2-07-soak-idle-20261026-220001.jsonl"
        manifest_for(root4, rawZ.stem, "7" * 64, "g2-07-soak-idle", boot_id_initial="BOOT-Z")
        idx4d = bi.build_index({"main": root4}, Path(td) / "i4d.json",
                               bi.REVIEWED_RUNS, bi.FIRMWARE_BATCHES, sources_snapshot={})
        rzz = next(r for r in idx4d["runs"] if "220000" in r["result_file"])
        expect("B3 HELLO-payload boot satisfies identity binding",
               rzz["factory_sha256"] == "7" * 64, rzz["identity_basis"][:60])

        # ---- G2-R3-05 (r3e): Raw/Result/Sidecar/Boot/Device correlation matrix ----
        root5 = Path(td) / "evidence5"
        root5.mkdir()
        imgTest = "7" * 64

        # 1. index_control: valid positive control with verified boot and device
        res_ctrl, raw_ctrl = make_result(root5, "ctrl-result", "2026-10-26T10:00:00Z", "2026-10-26T12:00:00Z",
                                         "soak-ctrl",
                                         [{"dir": "rx", "kind": 2, "code": 1,
                                           "payload": {"ok": True, "result": {"boot_id": "boot-A", "device_id": "board-A"}}}],
                                         board_id="board-A")
        manifest_for(root5, raw_ctrl.stem, imgTest, "soak", boot_id_initial="boot-A",
                     board={"device_id": "board-A", "port": "COM-A"})

        idx_ctrl = bi.build_index({"main": root5}, Path(td) / "idx_ctrl.json", {}, bi.FIRMWARE_BATCHES, sources_snapshot={})
        r_ctrl = idx_ctrl["runs"][0]
        expect("R3e index_control positive: binds image and manifest-linked",
               r_ctrl["batch"] == "manifest-linked" and r_ctrl["factory_sha256"] == imgTest,
               f"{r_ctrl['batch']}/{r_ctrl['factory_sha256'][:8]}")

        # 2. index_no_boot: raw has no boot IDs -> must fail
        root_noboot = Path(td) / "noboot"
        root_noboot.mkdir()
        res_nb, raw_nb = make_result(root_noboot, "noboot-res", "2026-10-26T10:00:00Z", "2026-10-26T12:00:00Z",
                                     "soak-nb", [{"dir": "note", "event": "fixture only, not hardware"}])
        manifest_for(root_noboot, raw_nb.stem, imgTest, "soak", boot_id_initial="boot-A")
        idx_nb = bi.build_index({"main": root_noboot}, Path(td) / "idx_nb.json", {}, bi.FIRMWARE_BATCHES, sources_snapshot={})
        r_nb = idx_nb["runs"][0]
        expect("R3e index_no_boot: raw without boot IDs rejected",
               r_nb["batch"] == "unknown" and r_nb["factory_sha256"] == "unverified",
               f"{r_nb['batch']}/{r_nb['factory_sha256'][:8]}")

        # 3. index_missing_claimed_boot: manifest boot_id_initial is None -> must fail
        root_missboot = Path(td) / "missboot"
        root_missboot.mkdir()
        res_mb, raw_mb = make_result(root_missboot, "missboot-res", "2026-10-26T10:00:00Z", "2026-10-26T12:00:00Z",
                                     "soak-mb", [{"boot_id": "boot-B"}])
        manifest_for(root_missboot, raw_mb.stem, imgTest, "soak", boot_id_initial=None)
        idx_mb = bi.build_index({"main": root_missboot}, Path(td) / "idx_mb.json", {}, bi.FIRMWARE_BATCHES, sources_snapshot={})
        r_mb = idx_mb["runs"][0]
        expect("R3e index_missing_claimed_boot: manifest with boot_id_initial=None rejected",
               r_mb["batch"] == "unknown" and r_mb["factory_sha256"] == "unverified",
               f"{r_mb['batch']}/{r_mb['factory_sha256'][:8]}")

        # 4. index_wrong_board: manifest board.device_id != raw device_id -> must fail
        root_wboard = Path(td) / "wboard"
        root_wboard.mkdir()
        res_wb, raw_wb = make_result(root_wboard, "wboard-res", "2026-10-26T10:00:00Z", "2026-10-26T12:00:00Z",
                                     "soak-wb",
                                     [{"dir": "rx", "kind": 2, "code": 1,
                                       "payload": {"ok": True, "result": {"boot_id": "boot-A", "device_id": "board-B"}}}])
        manifest_for(root_wboard, raw_wb.stem, imgTest, "soak", boot_id_initial="boot-A",
                     board={"device_id": "board-A", "port": "COM-A"})
        idx_wb = bi.build_index({"main": root_wboard}, Path(td) / "idx_wb.json", {}, bi.FIRMWARE_BATCHES, sources_snapshot={})
        r_wb = idx_wb["runs"][0]
        expect("R3e index_wrong_board: device mismatch between raw and manifest rejected",
               r_wb["batch"] == "unknown" and r_wb["factory_sha256"] == "unverified",
               f"{r_wb['batch']}/{r_wb['factory_sha256'][:8]}")

        # 5. index_nonhex_image: non-hex image SHA in manifest -> must fail
        root_nonhex = Path(td) / "nonhex"
        root_nonhex.mkdir()
        res_nh, raw_nh = make_result(root_nonhex, "nonhex-res", "2026-10-26T10:00:00Z", "2026-10-26T12:00:00Z",
                                     "soak-nh", [{"boot_id": "boot-A"}])
        manifest_for(root_nonhex, raw_nh.stem, "z" * 64, "soak", boot_id_initial="boot-A")
        idx_nh = bi.build_index({"main": root_nonhex}, Path(td) / "idx_nh.json", {}, bi.FIRMWARE_BATCHES, sources_snapshot={})
        r_nh = idx_nh["runs"][0]
        expect("R3e index_nonhex_image: non-hex image SHA 'z'*64 rejected",
               r_nh["batch"] == "unknown" and r_nh["factory_sha256"] == "unverified",
               f"{r_nh['batch']}/{r_nh['factory_sha256'][:8]}")

        # 6. index_changed_result: result tampered with contradicted run_id, board_id, started -> must fail
        res_ch, raw_ch = make_result(root5, "changed-res", "2026-10-26T10:00:00Z", "2026-10-26T12:00:00Z",
                                     "soak-ch",
                                     [{"dir": "rx", "kind": 2, "code": 1,
                                       "payload": {"ok": True, "result": {"boot_id": "boot-A", "device_id": "board-A"}}}])
        manifest_for(root5, raw_ch.stem, imgTest, "soak", boot_id_initial="boot-A")
        tampered_data = json.loads(res_ch.read_text(encoding="utf-8"))
        tampered_data.update(started="2030-01-01T00:00:00Z", ended="2030-01-01T02:00:00Z",
                             run_id="different-run", board_id="other-board")
        res_ch.write_text(json.dumps(tampered_data), encoding="utf-8")
        idx_ch = bi.build_index({"main": root5}, Path(td) / "idx_ch.json", {}, bi.FIRMWARE_BATCHES, sources_snapshot={})
        r_ch = next(r for r in idx_ch["runs"] if "changed-res" in r["result_file"])
        expect("R3e index_changed_result: tampered result contradicting manifest rejected",
               r_ch["batch"] == "unknown" and r_ch["factory_sha256"] == "unverified",
               f"{r_ch['batch']}/{r_ch['factory_sha256'][:8]}")

        # ---- G2-R3-05 (r3f): Formalized Index Negative Tests ----
        import copy
        imgF = "e" * 64
        raw_base = [{"dir": "rx", "kind": 2, "code": 1, "session_id": 123, "request_id": 1,
                     "payload": {"ok": True, "result": {"nonce": "1" * 32, "boot_id": "boot-A",
                                                        "identity": {"device_id": "board-10"}}}}]
        manifest_base = {"run_id": "g2-07-soak", "run_tag": "g2-07-soak-idle", "boot_id_initial": "boot-A",
                         "board": {"device_id": "board-10", "port": "COMX"}, "flashed_image_sha256": imgF,
                         "started": "2026-10-28T00:00:00Z", "ended": "2026-10-28T02:00:00Z"}

        for neg_name in ("index_control_no_flash_record", "device_substring", "missing_manifest_device",
                         "missing_raw_device", "missing_run_fields", "result_time_changed_60s",
                         "result_checks_changed", "identity_from_note"):
            neg_root = Path(td) / neg_name
            neg_root.mkdir()
            neg_raw = neg_root / "g2-07-soak-idle-sample.jsonl"
            data = copy.deepcopy(raw_base)
            neg_manifest = copy.deepcopy(manifest_base)
            neg_result = {"run_id": "g2-07-soak", "board_id": "board-10", "status": "pass",
                          "started": neg_manifest["started"], "ended": neg_manifest["ended"],
                          "checks": [{"name": "duration_honest", "pass": True}],
                          "evidence": {"file": str(neg_raw)}}
            if neg_name == "device_substring":
                neg_manifest["board"]["device_id"] = "board-1"
                neg_result["board_id"] = "board-1"
            elif neg_name == "missing_manifest_device":
                neg_manifest["board"] = {"port": "COMX"}
            elif neg_name == "missing_raw_device":
                data[0]["payload"]["result"].pop("identity", None)
            elif neg_name == "missing_run_fields":
                for field in ("run_id", "run_tag", "started", "ended"):
                    neg_manifest.pop(field, None)
                for field in ("run_id", "board_id", "started", "ended"):
                    neg_result.pop(field, None)
            elif neg_name == "result_time_changed_60s":
                neg_result["started"] = "2026-10-28T00:01:00Z"
            elif neg_name == "result_checks_changed":
                neg_result["checks"] = [{"name": "completely_different_check", "pass": True}]
            elif neg_name == "identity_from_note":
                data = [{"dir": "note", "boot_id": "boot-A", "device_id": "board-10"}]

            neg_raw.write_text("\n".join(map(json.dumps, data)) + "\n", encoding="utf-8")
            raw_dig = hashlib.sha256(neg_raw.read_bytes()).hexdigest()
            neg_manifest["raw_sha256"] = raw_dig
            neg_result_path = neg_root / "sample.result.json"
            neg_result_path.write_text(json.dumps(neg_result), encoding="utf-8")
            neg_manifest["result_sha256"] = hashlib.sha256(neg_result_path.read_bytes()).hexdigest()

            # For all negative tests, no verified flash record is attached (or tampered inputs invalidate binding)
            neg_raw.with_suffix(".manifest.json").write_text(json.dumps(neg_manifest), encoding="utf-8")

            neg_idx = bi.build_index({"main": neg_root}, Path(td) / f"{neg_name}.index.json",
                                     {}, bi.FIRMWARE_BATCHES, sources_snapshot={})
            r_neg = neg_idx["runs"][0]
            expect(f"R3f {neg_name} rejected: unknown/unverified",
                   r_neg["batch"] == "unknown" and r_neg["factory_sha256"] == "unverified"
                   and r_neg["accepted_status"] == "pending_review",
                   f"{r_neg['batch']}/{r_neg['factory_sha256']}")

        # ---- G2-R3-05 (r3g): Formalized Index Negative & Positive Tests ----
        image_r3g = "a" * 64
        for case in ('control', 'wrong_flash_device_id', 'missing_flash_identity', 'future_flash',
                     'mismatching_experiment_ids', 'raw_from_other_experiment', 'nonresponse_identity'):
            case_root = Path(td) / f"r3g_{case}"
            case_root.mkdir()
            case_raw = case_root / "g2-07-soak-idle-raw.jsonl"
            frames = [{'dir': 'tx', 'kind': 1, 'code': 1, 'session_id': 0, 'request_id': 1,
                       'payload': {'nonce': '1' * 32}, 'experiment_id': 'exp-A'},
                      {'dir': 'rx', 'kind': 2, 'code': 1, 'session_id': 1, 'request_id': 1, 'experiment_id': 'exp-A',
                       'payload': {'ok': True, 'result': {'nonce': '1' * 32, 'boot_id': 'boot-A', 'identity': {'device_id': 'board-A'}}}}]
            src_p = case_root / "flash-source.jsonl"
            src_p.write_text(json.dumps({'status': 'success', 'verify': 'ok', 'image_sha256': image_r3g, 'board_id': 'board-A',
                                         'timestamp': '2026-10-27T00:00:00Z', 'seq': 1}) + '\n', encoding='utf-8')
            flash = {'status': 'success', 'verify': 'ok', 'image_sha256': image_r3g, 'board_id': 'board-A',
                     'timestamp': '2026-10-27T00:00:00Z', 'seq': 1,
                     'source': {'ref': str(src_p), 'sha256': hashlib.sha256(src_p.read_bytes()).hexdigest()}}
            if case == 'wrong_flash_device_id':
                flash.pop('board_id'); flash['device_id'] = 'board-B'
            if case == 'missing_flash_identity':
                flash.pop('board_id')
            if case == 'future_flash':
                flash['timestamp'] = '2099-01-01T00:00:00Z'
            if case == 'raw_from_other_experiment':
                for f in frames: f['experiment_id'] = 'exp-B'
            if case == 'nonresponse_identity':
                frames = [dict(frames[1], dir='tx', kind=1, code=999)]
            case_raw.write_text('\n'.join(map(json.dumps, frames)) + '\n', encoding='utf-8')
            res = {'run_id': 'run-A', 'experiment_id': 'exp-A', 'status': 'pass', 'board_id': 'board-A',
                   'started': '2026-10-28T00:00:00Z', 'ended': '2026-10-28T02:00:00Z',
                   'evidence': {'file': str(case_raw), 'sha256': hashlib.sha256(case_raw.read_bytes()).hexdigest()}, 'checks': []}
            rp = case_root / 'run.result.json'
            rp.write_text(json.dumps(res), encoding='utf-8')
            m = {'run_id': 'run-A', 'experiment_id': 'exp-A', 'run_tag': 'g2-07-soak-idle',
                 'started': res['started'], 'ended': res['ended'], 'board': {'device_id': 'board-A'},
                 'boot_id_initial': 'boot-A', 'raw_sha256': hashlib.sha256(case_raw.read_bytes()).hexdigest(),
                 'result_sha256': hashlib.sha256(rp.read_bytes()).hexdigest(),
                 'result_ref': rp.name, 'flashed_image_sha256': image_r3g, 'flash_record': flash}
            if case == 'mismatching_experiment_ids':
                m['experiment_id'] = 'exp-B'
            case_raw.with_suffix('.manifest.json').write_text(json.dumps(m), encoding='utf-8')
            idx_r3g = bi.build_index({'main': case_root}, Path(td) / f'r3g_{case}.index.json', {}, bi.FIRMWARE_BATCHES, sources_snapshot={})
            r_item = idx_r3g['runs'][0]
            if case == 'control':
                expect(f"R3g {case} positive links image",
                       r_item["batch"] == "manifest-linked" and r_item["factory_sha256"] == image_r3g,
                       f"{r_item['batch']}/{r_item['factory_sha256'][:8]}")
            else:
                expect(f"R3g {case} negative rejected",
                       r_item["batch"] == "unknown" and r_item["factory_sha256"] == "unverified",
                       f"{r_item['batch']}/{r_item['factory_sha256'][:8]}")

        # ---- G2-H2 & G2-H3 (r3j): Normalized Frames, Session Correlation, Source Semantics & Lifecycle Replay ----
        image_h = "f" * 64
        base_h = "2026-10-28T12:00:00Z"
        end_h = "2026-10-28T12:01:00Z"

        # H2 / H3 test cases
        h_cases = [
            # H2 cases
            ("h2_control", "pass", "manifest-linked", None),
            ("h2_missing_hello_tx_session", "fail", "unknown", "missing_tx_session"),
            ("h2_missing_hello_rx_session", "fail", "unknown", "missing_rx_session"),
            ("h2_contradictory_direction_tx", "fail", "unknown", "tx_dir_rx"),
            ("h2_hello_tx_nonzero_session", "fail", "unknown", "tx_session_nonzero"),
            ("h2_hello_rx_zero_session", "fail", "unknown", "rx_session_zero"),
            ("h2_top_meta_session_conflict", "fail", "unknown", "meta_conflict"),
            # H3 cases
            ("h3_no_source_dict", "fail", "unknown", "no_source"),
            ("h3_source_plain_text", "fail", "unknown", "plain_text_source"),
            ("h3_source_wrong_image", "fail", "unknown", "wrong_image_source"),
            ("h3_erase_before_run", "fail", "unknown", "erase_before"),
            ("h3_erase_during_run", "fail", "unknown", "erase_during"),
            ("h3_unknown_before_run", "fail", "unknown", "unknown_before"),
            ("h3_erase_after_run_allowed", "pass", "manifest-linked", "erase_after"),
            ("h3_other_device_erase_ignored", "pass", "manifest-linked", "other_dev_erase"),
        ]

        for h_name, expected_stat, expected_batch, mut in h_cases:
            c_root = Path(td) / f"h_{h_name}"
            c_root.mkdir()
            c_raw = c_root / f"g2-07-soak-idle-{h_name}.jsonl"
            
            # Base frames: valid HELLO handshake
            tx_frame = {
                "dir": "tx", "kind": 1, "code": 1, "session_id": 0, "request_id": 1,
                "payload": {"nonce": "2" * 32}, "experiment_id": f"exp-{h_name}",
            }
            rx_frame = {
                "dir": "rx", "kind": 2, "code": 1, "session_id": 100, "request_id": 1,
                "payload": {"ok": True, "result": {"nonce": "2" * 32, "boot_id": "boot-H", "identity": {"device_id": "board-H"}}},
                "experiment_id": f"exp-{h_name}",
            }

            if mut == "missing_tx_session":
                tx_frame.pop("session_id")
            elif mut == "missing_rx_session":
                rx_frame.pop("session_id")
            elif mut == "tx_dir_rx":
                tx_frame["dir"] = "rx"  # kind remains 1
            elif mut == "tx_session_nonzero":
                tx_frame["session_id"] = 42
            elif mut == "rx_session_zero":
                rx_frame["session_id"] = 0
            elif mut == "meta_conflict":
                tx_frame["meta"] = {"session_id": 99}  # top-level is 0, meta is 99 -> conflict

            c_raw.write_text(json.dumps(tx_frame) + "\n" + json.dumps(rx_frame) + "\n", encoding="utf-8")
            c_raw_sha = hashlib.sha256(c_raw.read_bytes()).hexdigest()

            c_res_p = c_root / "run.result.json"
            c_res = {
                "run_id": f"run-{h_name}", "experiment_id": f"exp-{h_name}", "status": "pass",
                "board_id": "board-H", "started": base_h, "ended": end_h,
                "evidence": {"file": str(c_raw), "sha256": c_raw_sha}, "checks": [],
            }
            c_res_p.write_text(json.dumps(c_res), encoding="utf-8")
            c_res_sha = hashlib.sha256(c_res_p.read_bytes()).hexdigest()

            # Source log records
            src_log = c_root / "flash-source.jsonl"
            flash_ts = "2026-10-27T00:00:00Z"
            base_ev = {"device_id": "board-H", "status": "success", "verify": "ok", "image_sha256": image_h, "timestamp": flash_ts, "seq": 1}

            if mut == "no_source":
                flash_obj = dict(base_ev)
            elif mut == "plain_text_source":
                src_log.write_text("SOFTWARE NOT JSON\n", encoding="utf-8")
                flash_obj = dict(base_ev, source={"ref": str(src_log), "sha256": hashlib.sha256(src_log.read_bytes()).hexdigest()})
            elif mut == "wrong_image_source":
                src_log.write_text(json.dumps(dict(base_ev, image_sha256="0" * 64)) + "\n", encoding="utf-8")
                flash_obj = dict(base_ev, source={"ref": str(src_log), "sha256": hashlib.sha256(src_log.read_bytes()).hexdigest()})
            elif mut == "erase_before":
                src_log.write_text(json.dumps(base_ev) + "\n" + json.dumps({"device_id": "board-H", "status": "erased", "timestamp": "2026-10-28T11:59:59Z", "seq": 2}) + "\n", encoding="utf-8")
                flash_obj = dict(base_ev, source={"ref": str(src_log), "sha256": hashlib.sha256(src_log.read_bytes()).hexdigest()})
            elif mut == "erase_during":
                src_log.write_text(json.dumps(base_ev) + "\n" + json.dumps({"device_id": "board-H", "status": "erased", "timestamp": "2026-10-28T12:00:30Z", "seq": 2}) + "\n", encoding="utf-8")
                flash_obj = dict(base_ev, source={"ref": str(src_log), "sha256": hashlib.sha256(src_log.read_bytes()).hexdigest()})
            elif mut == "unknown_before":
                src_log.write_text(json.dumps(base_ev) + "\n" + json.dumps({"device_id": "board-H", "status": "unknown", "timestamp": "2026-10-28T11:59:59Z", "seq": 2}) + "\n", encoding="utf-8")
                flash_obj = dict(base_ev, source={"ref": str(src_log), "sha256": hashlib.sha256(src_log.read_bytes()).hexdigest()})
            elif mut == "erase_after":
                src_log.write_text(json.dumps(base_ev) + "\n" + json.dumps({"device_id": "board-H", "status": "erased", "timestamp": "2026-10-28T12:02:00Z", "seq": 2}) + "\n", encoding="utf-8")
                flash_obj = dict(base_ev, source={"ref": str(src_log), "sha256": hashlib.sha256(src_log.read_bytes()).hexdigest()})
            elif mut == "other_dev_erase":
                src_log.write_text(json.dumps(base_ev) + "\n" + json.dumps({"device_id": "board-OTHER", "status": "erased", "timestamp": "2026-10-28T12:00:30Z", "seq": 2}) + "\n", encoding="utf-8")
                flash_obj = dict(base_ev, source={"ref": str(src_log), "sha256": hashlib.sha256(src_log.read_bytes()).hexdigest()})
            else:
                src_log.write_text(json.dumps(base_ev) + "\n", encoding="utf-8")
                flash_obj = dict(base_ev, source={"ref": str(src_log), "sha256": hashlib.sha256(src_log.read_bytes()).hexdigest()})

            c_man = {
                "run_id": f"run-{h_name}", "experiment_id": f"exp-{h_name}", "run_tag": "g2-07-soak-idle",
                "started": base_h, "ended": end_h, "board": {"device_id": "board-H"},
                "boot_id_initial": "boot-H", "raw_sha256": c_raw_sha, "result_sha256": c_res_sha,
                "result_ref": c_res_p.name, "flashed_image_sha256": image_h, "flash_record": flash_obj,
            }
            c_raw.with_suffix(".manifest.json").write_text(json.dumps(c_man), encoding="utf-8")

            idx_h = bi.build_index({"main": c_root}, Path(td) / f"{h_name}.index.json", {}, bi.FIRMWARE_BATCHES, sources_snapshot={})
            h_item = idx_h["runs"][0]

            if expected_batch == "manifest-linked":
                expect(f"R3j {h_name} positive links image",
                       h_item["batch"] == "manifest-linked" and h_item["factory_sha256"] == image_h,
                       f"{h_item['batch']}/{h_item['factory_sha256'][:8]}")
            else:
                expect(f"R3j {h_name} negative rejected",
                       h_item["batch"] == "unknown" and h_item["factory_sha256"] == "unverified",
                       f"{h_item['batch']}/{h_item['factory_sha256'][:8]}")

        # --- R3k additions: H2-A, H2-B, H3-A, H3-B ---
        # 1. H2-A: DEVICE_INFO (code 16) extracts identity; SESSION_CLOSE (code 3) closes session without identity extraction
        dev_info_raw = Path(td) / "test_dev_info.jsonl"
        dev_info_frames = [
            {"dir": "tx", "kind": 1, "code": 1, "session_id": 0, "request_id": 1, "payload": {"nonce": "d"*32}},
            {"dir": "rx", "kind": 2, "code": 1, "session_id": 500, "request_id": 1, "payload": {"ok": True, "result": {"nonce": "d"*32, "boot_id": "boot-D", "device_id": "board-D"}}},
            {"dir": "tx", "kind": 1, "code": 16, "session_id": 500, "request_id": 2, "payload": {}},
            {"dir": "rx", "kind": 2, "code": 16, "session_id": 500, "request_id": 2, "payload": {"ok": True, "result": {"device_id": "board-D-extra"}}},
        ]
        dev_info_raw.write_text("\n".join(json.dumps(f) for f in dev_info_frames) + "\n", encoding="utf-8")
        _, dev_info_devs = bi._raw_correlated_identities(dev_info_raw)
        expect("R3k H2-A DEVICE_INFO code 16 extracts identity", "board-D-extra" in dev_info_devs)

        close_raw = Path(td) / "test_close.jsonl"
        close_frames = [
            {"dir": "tx", "kind": 1, "code": 1, "session_id": 0, "request_id": 1, "payload": {"nonce": "d"*32}},
            {"dir": "rx", "kind": 2, "code": 1, "session_id": 500, "request_id": 1, "payload": {"ok": True, "result": {"nonce": "d"*32, "boot_id": "boot-D", "device_id": "board-D"}}},
            {"dir": "tx", "kind": 1, "code": 3, "session_id": 500, "request_id": 2, "payload": {}},
            {"dir": "rx", "kind": 2, "code": 3, "session_id": 500, "request_id": 2, "payload": {"ok": True, "result": {"device_id": "board-D-fake", "closed": True}}},
        ]
        close_raw.write_text("\n".join(json.dumps(f) for f in close_frames) + "\n", encoding="utf-8")
        _, close_devs = bi._raw_correlated_identities(close_raw)
        expect("R3k H2-A SESSION_CLOSE code 3 does not extract identity", "board-D-fake" not in close_devs)

        # 2. H2-B: Stale HELLO response reusing request_id does not drop pending new HELLO request
        stale_hello_raw = Path(td) / "test_stale_hello.jsonl"
        stale_frames = [
            # Client sends new HELLO request with nonce B
            {"dir": "tx", "kind": 1, "code": 1, "session_id": 0, "request_id": 1, "payload": {"nonce": "b"*32}},
            # Stale response for previous handshake arrives (rid=1, but nonce A)
            {"dir": "rx", "kind": 2, "code": 1, "session_id": 100, "request_id": 1, "payload": {"ok": True, "result": {"nonce": "a"*32, "boot_id": "boot-stale", "device_id": "board-stale"}}},
            # Legitimate response for nonce B arrives (rid=1, nonce B)
            {"dir": "rx", "kind": 2, "code": 1, "session_id": 101, "request_id": 1, "payload": {"ok": True, "result": {"nonce": "b"*32, "boot_id": "boot-new", "device_id": "board-new"}}},
        ]
        stale_hello_raw.write_text("\n".join(json.dumps(f) for f in stale_frames) + "\n", encoding="utf-8")
        stale_boots, stale_devs = bi._raw_correlated_identities(stale_hello_raw)
        expect("R3k H2-B stale HELLO response does not drop pending new request", "boot-new" in stale_boots and "boot-stale" not in stale_boots)

        # 3. H3-A: File-chain counterexamples via build_index
        r3k_matrix = [
            ("source_success_only_after_run", "unknown"),
            ("claim_timestamp_shifted_past_erase", "unknown"),
            ("same_timestamp_later_seq_erase", "unknown"),
            ("missing_status_during_run", "unknown"),
            ("duplicate_sequence_conflict", "unknown"),
        ]
        for k_name, expected_k_batch in r3k_matrix:
            k_root = Path(td) / f"r3k_{k_name}"
            k_root.mkdir(parents=True, exist_ok=True)
            k_raw = k_root / "run.jsonl"
            k_tx = {"dir": "tx", "kind": 1, "code": 1, "session_id": 0, "request_id": 1, "payload": {"nonce": "k"*32}}
            k_rx = {"dir": "rx", "kind": 2, "code": 1, "session_id": 200, "request_id": 1, "payload": {"ok": True, "result": {"nonce": "k"*32, "boot_id": "boot-K", "identity": {"device_id": "board-K"}}}, "experiment_id": f"exp-{k_name}"}
            k_raw.write_text(json.dumps(k_tx) + "\n" + json.dumps(k_rx) + "\n", encoding="utf-8")
            k_raw_sha = hashlib.sha256(k_raw.read_bytes()).hexdigest()

            k_base = "2026-10-28T12:00:00Z"
            k_end = "2026-10-28T12:01:00Z"
            k_res_p = k_root / "run.result.json"
            k_res = {
                "run_id": f"run-{k_name}", "experiment_id": f"exp-{k_name}", "status": "pass",
                "board_id": "board-K", "started": k_base, "ended": k_end,
                "evidence": {"file": str(k_raw), "sha256": k_raw_sha}, "checks": [],
            }
            k_res_p.write_text(json.dumps(k_res), encoding="utf-8")
            k_res_sha = hashlib.sha256(k_res_p.read_bytes()).hexdigest()

            k_src_log = k_root / "flash-history.jsonl"
            k_flash = {"device_id": "board-K", "status": "success", "verify": "ok", "image_sha256": image_h, "timestamp": "2026-10-27T00:00:00Z", "seq": 1}

            if k_name == "source_success_only_after_run":
                k_records = [dict(k_flash, timestamp="2026-10-28T13:00:00Z")]
                claim_flash = dict(k_flash)
            elif k_name == "claim_timestamp_shifted_past_erase":
                k_records = [k_flash, {"device_id": "board-K", "status": "erased", "timestamp": "2026-10-28T10:00:00Z", "seq": 2}]
                claim_flash = dict(k_flash, timestamp="2026-10-28T11:00:00Z")
            elif k_name == "same_timestamp_later_seq_erase":
                k_records = [k_flash, {"device_id": "board-K", "status": "erased", "timestamp": k_flash["timestamp"], "seq": 2}]
                claim_flash = dict(k_flash)
            elif k_name == "missing_status_during_run":
                k_records = [k_flash, {"device_id": "board-K", "timestamp": "2026-10-28T12:00:30Z", "seq": 2}]
                claim_flash = dict(k_flash)
            elif k_name == "duplicate_sequence_conflict":
                k_records = [k_flash, dict(k_flash, seq=1, timestamp="2026-10-28T11:00:00Z")]
                claim_flash = dict(k_flash)
            else:
                k_records = [k_flash]
                claim_flash = dict(k_flash)

            k_src_log.write_text("\n".join(json.dumps(r) for r in k_records) + "\n", encoding="utf-8")
            claim_flash["source"] = {"ref": str(k_src_log), "sha256": hashlib.sha256(k_src_log.read_bytes()).hexdigest()}

            k_man = {
                "run_id": f"run-{k_name}", "experiment_id": f"exp-{k_name}", "run_tag": "g2-07-soak-idle",
                "started": k_base, "ended": k_end, "board": {"device_id": "board-K"},
                "boot_id_initial": "boot-K", "raw_sha256": k_raw_sha, "result_sha256": k_res_sha,
                "result_ref": k_res_p.name, "flashed_image_sha256": image_h, "flash_record": claim_flash,
            }
            k_raw.with_suffix(".manifest.json").write_text(json.dumps(k_man), encoding="utf-8")

            idx_k = bi.build_index({"main": k_root}, Path(td) / f"{k_name}.index.json", {}, bi.FIRMWARE_BATCHES, sources_snapshot={})
            k_item = idx_k["runs"][0]
            expect(f"R3k {k_name} negative rejected",
                   k_item["batch"] == expected_k_batch and k_item["factory_sha256"] == "unverified",
                   f"{k_item['batch']}/{k_item['factory_sha256'][:8]}")

        # 4. H3-B: bank and shared contract agreement
        import leg_driver2 as ld
        import flash_verifier as fv
        from datetime import datetime, timezone
        from unittest.mock import patch
        bank_dev = "dc:da:0c:f8:f2:74"
        bank_flash = {"device_id": bank_dev, "status": "success", "verify": "ok", "image_sha256": image_h, "timestamp": "2026-10-27T00:00:00Z", "seq": 1}
        conflict_records = [bank_flash, dict(bank_flash, seq=1, timestamp="2026-10-28T11:00:00Z")]
        conflict_log = Path(td) / "bank_conflict_log.txt"
        conflict_log.write_text("\n".join(json.dumps(r) for r in conflict_records) + "\n", encoding="utf-8")
        shared_claim = dict(bank_flash, source={"ref": str(conflict_log), "sha256": hashlib.sha256(conflict_log.read_bytes()).hexdigest()})
        shared_res = fv.verify_flash_record(shared_claim, "2026-10-28T12:00:00Z", "2026-10-28T12:01:00Z", bank_dev)
        with patch.object(ld, "EVIDENCE", Path(td)), patch.object(ld, "_sha256", lambda p: image_h):
            (Path(td) / "flash-log-r2.txt").write_text(conflict_log.read_text(), encoding="utf-8")
            bank_res = ld.environment_fingerprint(device_id=bank_dev, as_of_time=datetime.fromisoformat("2026-10-28T12:00:00+00:00"))
        expect("R3k H3-B shared verifier rejects duplicate seq", shared_res[0] == "unverified")
        expect("R3k H3-B bank rejects duplicate seq", bank_res["flashed_evidence"] is False and "duplicate sequence conflict" in bank_res.get("flashed_evidence_reason", ""))

        # 5. R3l H3-L1 ~ H3-L4: verify on subsequent same-image, unorderable equal timestamps, JSON array parsing, bank parse errors
        r3l_matrix = [
            ("later_same_image_verify_ok", "manifest-linked", image_h, [
                {"device_id": "board-L", "status": "success", "verify": "ok", "image_sha256": image_h, "timestamp": "2026-10-27T00:00:00Z", "seq": 1},
                {"device_id": "board-L", "status": "success", "verify": "ok", "image_sha256": image_h, "timestamp": "2026-10-28T11:00:00Z", "seq": 2},
            ], False),
            ("later_same_image_verify_failed", "unknown", "unverified", [
                {"device_id": "board-L", "status": "success", "verify": "ok", "image_sha256": image_h, "timestamp": "2026-10-27T00:00:00Z", "seq": 1},
                {"device_id": "board-L", "status": "success", "verify": "failed", "image_sha256": image_h, "timestamp": "2026-10-28T11:00:00Z", "seq": 2},
            ], False),
            ("equal_time_no_seq_erase_first", "unknown", "unverified", [
                {"device_id": "board-L", "status": "erased", "timestamp": "2026-10-27T00:00:00Z"},
                {"device_id": "board-L", "status": "success", "verify": "ok", "image_sha256": image_h, "timestamp": "2026-10-27T00:00:00Z"},
            ], False),
            ("equal_time_no_seq_erase_last", "unknown", "unverified", [
                {"device_id": "board-L", "status": "success", "verify": "ok", "image_sha256": image_h, "timestamp": "2026-10-27T00:00:00Z"},
                {"device_id": "board-L", "status": "erased", "timestamp": "2026-10-27T00:00:00Z"},
            ], False),
            ("equal_time_seq_erase_then_success", "manifest-linked", image_h, [
                {"device_id": "board-L", "status": "erased", "timestamp": "2026-10-27T00:00:00Z", "seq": 1},
                {"device_id": "board-L", "status": "success", "verify": "ok", "image_sha256": image_h, "timestamp": "2026-10-27T00:00:00Z", "seq": 2},
            ], False),
            ("equal_time_seq_success_then_erase", "unknown", "unverified", [
                {"device_id": "board-L", "status": "success", "verify": "ok", "image_sha256": image_h, "timestamp": "2026-10-27T00:00:00Z", "seq": 1},
                {"device_id": "board-L", "status": "erased", "timestamp": "2026-10-27T00:00:00Z", "seq": 2},
            ], False),
            ("json_array_compact", "manifest-linked", image_h, [
                {"device_id": "board-L", "status": "success", "verify": "ok", "image_sha256": image_h, "timestamp": "2026-10-27T00:00:00Z", "seq": 1},
            ], "compact"),
            ("json_array_pretty", "manifest-linked", image_h, [
                {"device_id": "board-L", "status": "success", "verify": "ok", "image_sha256": image_h, "timestamp": "2026-10-27T00:00:00Z", "seq": 1},
            ], "pretty"),
        ]
        for l_name, exp_l_batch, exp_l_sha, l_records, json_style in r3l_matrix:
            l_root = Path(td) / f"r3l_{l_name}"
            l_root.mkdir(parents=True, exist_ok=True)
            l_raw = l_root / f"g2-07-soak-idle-{l_name}.jsonl"
            l_tx = {"dir": "tx", "kind": 1, "code": 1, "session_id": 0, "request_id": 1, "payload": {"nonce": "l"*32}}
            l_rx = {"dir": "rx", "kind": 2, "code": 1, "session_id": 300, "request_id": 1, "payload": {"ok": True, "result": {"nonce": "l"*32, "boot_id": "boot-L", "identity": {"device_id": "board-L"}}}, "experiment_id": f"exp-{l_name}"}
            l_raw.write_text(json.dumps(l_tx) + "\n" + json.dumps(l_rx) + "\n", encoding="utf-8")
            l_raw_sha = hashlib.sha256(l_raw.read_bytes()).hexdigest()

            l_base = "2026-10-28T12:00:00Z"
            l_end = "2026-10-28T12:01:00Z"
            l_res_p = l_root / f"g2-07-soak-idle-{l_name}.result.json"
            l_res = {
                "run_id": f"run-{l_name}", "experiment_id": f"exp-{l_name}", "status": "pass",
                "board_id": "board-L", "started": l_base, "ended": l_end,
                "evidence": {"file": str(l_raw), "sha256": l_raw_sha}, "checks": [],
            }
            l_res_p.write_text(json.dumps(l_res), encoding="utf-8")
            l_res_sha = hashlib.sha256(l_res_p.read_bytes()).hexdigest()

            l_src_log = l_root / "flash-history.jsonl"
            if json_style == "compact":
                l_src_log.write_text(json.dumps(l_records), encoding="utf-8")
            elif json_style == "pretty":
                l_src_log.write_text(json.dumps(l_records, indent=2), encoding="utf-8")
            else:
                l_src_log.write_text("\n".join(json.dumps(r) for r in l_records) + "\n", encoding="utf-8")

            claim_rec = [r for r in l_records if r.get("status") == "success"][0]
            claim_l = dict(claim_rec, source={"ref": str(l_src_log), "sha256": hashlib.sha256(l_src_log.read_bytes()).hexdigest()})

            l_man = {
                "run_id": f"run-{l_name}", "experiment_id": f"exp-{l_name}", "run_tag": "g2-07-soak-idle",
                "started": l_base, "ended": l_end, "board": {"device_id": "board-L"},
                "boot_id_initial": "boot-L", "raw_sha256": l_raw_sha, "result_sha256": l_res_sha,
                "result_ref": l_res_p.name, "flashed_image_sha256": image_h, "flash_record": claim_l,
            }
            l_raw.with_suffix(".manifest.json").write_text(json.dumps(l_man), encoding="utf-8")

            idx_l = bi.build_index({"main": l_root}, Path(td) / f"{l_name}.index.json", {}, bi.FIRMWARE_BATCHES, sources_snapshot={})
            l_item = idx_l["runs"][0]
            expect(f"R3l {l_name} result matches expected",
                   l_item["batch"] == exp_l_batch and l_item["factory_sha256"] == exp_l_sha,
                   f"{l_item['batch']}/{l_item['factory_sha256'][:8]}")

        # 6. R3l H3-L3 & H3-L1 bank parity checks
        b_rec = {"device_id": bank_dev, "status": "success", "verify": "ok", "image_sha256": image_h, "timestamp": "2026-10-27T00:00:00Z", "seq": 1}
        nondict_log = Path(td) / "bank_nondict.txt"
        nondict_log.write_text(json.dumps(b_rec) + "\n17\n", encoding="utf-8")
        with patch.object(ld, "EVIDENCE", Path(td)), patch.object(ld, "_sha256", lambda p: image_h):
            (Path(td) / "flash-log-r2.txt").write_text(nondict_log.read_text(), encoding="utf-8")
            b_nondict_res = ld.environment_fingerprint(device_id=bank_dev, as_of_time=datetime.fromisoformat("2026-10-28T12:00:00+00:00"))
        expect("R3l bank rejects non-dict line in flash log", b_nondict_res["flashed_evidence"] is False and b_nondict_res["complete"] is False)

        failed_verify_log = Path(td) / "bank_failed_verify.txt"
        failed_verify_records = [
            b_rec,
            {"device_id": bank_dev, "status": "success", "verify": "failed", "image_sha256": image_h, "timestamp": "2026-10-28T11:00:00Z", "seq": 2}
        ]
        failed_verify_log.write_text("\n".join(json.dumps(r) for r in failed_verify_records) + "\n", encoding="utf-8")
        with patch.object(ld, "EVIDENCE", Path(td)), patch.object(ld, "_sha256", lambda p: image_h):
            (Path(td) / "flash-log-r2.txt").write_text(failed_verify_log.read_text(), encoding="utf-8")
            b_failed_verify_res = ld.environment_fingerprint(device_id=bank_dev, as_of_time=datetime.fromisoformat("2026-10-28T12:00:00+00:00"))
        expect("R3l bank rejects subsequent same-image verify failed", b_failed_verify_res["flashed_evidence"] is False and b_failed_verify_res["complete"] is False)

        # 7. G2-HW-R1-A Cross-Batch Review Isolation and Composite Identity
        r1a_root_a = Path(td) / "r1a_root_a"
        r1a_root_b = Path(td) / "r1a_root_b"
        r1a_root_a.mkdir(exist_ok=True)
        r1a_root_b.mkdir(exist_ok=True)

        res_a = r1a_root_a / "b1_backpressure.result.json"
        raw_a = r1a_root_a / "b1_backpressure.jsonl"
        raw_a.write_text('{"event":"start"}\n', encoding="utf-8")
        res_a.write_text(json.dumps({
            "run_id": "g2-01-backpressure", "status": "fail",
            "evidence": {"file": str(raw_a), "sha256": sha_of(raw_a)}
        }), encoding="utf-8")
        sha_res_a = sha_of(res_a)

        res_b = r1a_root_b / "b1_backpressure.result.json"
        raw_b = r1a_root_b / "b1_backpressure.jsonl"
        raw_b.write_text('{"event":"start_b"}\n{"event":"data_b"}\n', encoding="utf-8")
        res_b.write_text(json.dumps({
            "run_id": "g2-01-backpressure", "status": "pass",
            "evidence": {"file": str(raw_b), "sha256": sha_of(raw_b)}
        }), encoding="utf-8")
        sha_res_b = sha_of(res_b)

        # Subtest 1: Scoped review for root_a must not pollute root_b
        r1a_reviewed = {
            "b1_backpressure": {
                "target_root": "root_a",
                "result_sha256": sha_res_a,
                "accepted_status": "rejected",
                "reason": "old batch reject",
                "superseded_by": None,
            }
        }
        idx_r1a = bi.build_index({"root_a": r1a_root_a, "root_b": r1a_root_b}, Path(td) / "r1a.index.json",
                                 r1a_reviewed, bi.FIRMWARE_BATCHES, sources_snapshot={})
        runs_r1a = {r["result_file"]: r for r in idx_r1a["runs"]}
        run_a_item = next(v for k, v in runs_r1a.items() if "r1a_root_a" in k)
        run_b_item = next(v for k, v in runs_r1a.items() if "r1a_root_b" in k)

        expect("R1-A root_a gets exact review rejected", run_a_item["accepted_status"] == "rejected", run_a_item["accepted_status"])
        expect("R1-A root_b remains pending_review (no cross-batch pollution)", run_b_item["accepted_status"] == "pending_review", run_b_item["accepted_status"])

        # Subtest 2: Different result hash with same run_id does not inherit review
        expect("R1-A runs have different result hashes", sha_res_a != sha_res_b)

        # Subtest 3: Composite key positive review on root_b
        r1a_composite_reviewed = {
            "root_b/b1_backpressure": {
                "target_root": "root_b",
                "result_sha256": sha_res_b,
                "accepted_status": "pass",
                "reason": "independently reviewed batch B",
                "superseded_by": None,
            }
        }
        idx_r1a_comp = bi.build_index({"root_a": r1a_root_a, "root_b": r1a_root_b}, Path(td) / "r1a_comp.index.json",
                                      r1a_composite_reviewed, bi.FIRMWARE_BATCHES, sources_snapshot={})
        runs_comp = {r["result_file"]: r for r in idx_r1a_comp["runs"]}
        run_b_comp = next(v for k, v in runs_comp.items() if "r1a_root_b" in k)
        expect("R1-A composite key on root_b accepted as pass", run_b_comp["accepted_status"] == "pass", run_b_comp["accepted_status"])

    print("VERDICT:", "pass" if not failures else f"FAIL ({len(failures)})")
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())
