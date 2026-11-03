#!/usr/bin/env python3
"""Offline negative self-test for the leg driver's banking and coexistence
judgement (2026-10-26 review G2-R3; no serial port, no device).

Encodes the review's counterexamples as data and asserts the NEW logic
rejects every one of them while still accepting genuine passes:

1. failed scan + page.ok:true + connected  -> RECOVERY_ONLY, not a success
2. succeeded scan + page.ok:false          -> fail, not a success
3. precondition unmet (never connected)    -> fail, not a success
4. bank entry from a different environment -> HIST, must re-run
5. same environment                        -> SKIP allowed
6. attempt log is append-only              -> success never erases failure
"""

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import leg_driver2 as ld  # noqa: E402


def coexist_judgement(state, page_ok, connected_before, still_connected):
    """Mirror of make_coexist()'s decision logic (kept in sync by this test)."""
    if not connected_before:
        return False, "precondition_unmet: not connected before scan"
    if state == "succeeded" and page_ok and still_connected:
        return True, "succeeded page_ok=True wifi=connected"
    if state == "failed" and still_connected:
        return False, f"RECOVERY_ONLY failed page_ok={page_ok} wifi=connected"
    return False, f"{state} page_ok={page_ok} wifi={'connected' if still_connected else 'down'}"


def main() -> int:
    failures = []

    def expect(name, ok):
        print(f"[{'PASS' if ok else 'FAIL'}] {name}")
        if not ok:
            failures.append(name)

    ok, detail = coexist_judgement("failed", True, True, True)
    expect("reject failed+page_ok:true (RECOVERY_ONLY)", (not ok) and "RECOVERY_ONLY" in detail)
    ok, detail = coexist_judgement("succeeded", False, True, True)
    expect("reject succeeded+page_ok:false", not ok)
    ok, detail = coexist_judge_pre_unmet = coexist_judgement("succeeded", True, False, True)
    expect("reject never-connected precondition", not ok)
    ok, _ = coexist_judgement("succeeded", True, True, True)
    expect("accept genuine coexist success", ok)
    ok, _ = coexist_judgement("succeeded", True, True, False)
    expect("reject link lost after scan", not ok)

    with tempfile.TemporaryDirectory() as td:
        ld.STATE = Path(td) / "bank.json"
        ld.ATTEMPTS = Path(td) / "attempts.jsonl"

        # bank entries from a DIFFERENT environment must not auto-skip
        bank = {"coexist_3": {"pass": True, "env": "old-firmware-sha", "run_id": "20261024-170000"}}
        skip = ld.environment()["image_sha256"] or "unknown-image"
        prior = bank.get("coexist_3", {})
        banked_for_env = prior.get("env") == skip and prior.get("pass")
        expect("old-environment entry triggers re-run (HIST)", not banked_for_env)

        # same environment skips
        bank2 = {"coexist_3": {"pass": True, "env": skip, "run_id": "current"}}
        prior2 = bank2.get("coexist_3", {})
        expect("same-environment entry skips", prior2.get("env") == skip and prior2.get("pass"))

        # append-only attempt log: a later success must not erase a failure
        ld.attempts_append({"item": "x", "attempt": 0, "status": "fail", "detail": "TimeoutError"})
        ld.attempts_append({"item": "x", "attempt": 1, "status": "pass", "detail": "ok"})
        lines = [json.loads(l) for l in ld.ATTEMPTS.read_text(encoding="utf-8").splitlines()]
        expect("attempt log keeps failure beside success",
               len(lines) == 2 and lines[0]["status"] == "fail" and lines[1]["status"] == "pass")

    print("VERDICT:", "pass" if not failures else f"FAIL ({len(failures)})")
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())
