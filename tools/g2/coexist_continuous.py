#!/usr/bin/env python3
"""Continuous coexistence x10: ten WIFI_SCAN rounds in ONE session, ONE
boot, no resets between rounds (2026-10-26 r2 review: the per-item driver
reset each round, so the old bank never proved continuous coexistence).

Success per round: link connected before the scan, the job succeeded, the
results page ok:true, and the link still connected after the scan. A failed
scan with the link kept is recorded as recovery data, not a success.
"""

import json
import math
import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import mwcp  # noqa: E402

PORT = sys.argv[1] if len(sys.argv) > 1 else "COM9"


def main() -> int:
    stamp = time.strftime("%Y%m%d-%H%M%S")
    ev = mwcp.EvidenceWriter(EVIDENCE_DIR() / f"g2-06-coexist-continuous-{stamp}.jsonl", mwcp.Redactor())
    client = mwcp.Client(PORT, ev, allow_write=True)
    rounds_ok = 0
    recoveries = 0
    failures = 0
    try:
        client.hello(timeout_ms=15000)
        boot0 = client.boot_id
        # wait out the post-reset Wi-Fi association before judging the
        # coexistence precondition (a fresh boot needs a few seconds)
        for _ in range(15):
            st = client.call("WIFI_STATUS").get("result", {})
            if st.get("state") == "connected":
                break
            time.sleep(2.0)
        for i in range(10):
            st0 = client.call("WIFI_STATUS").get("result", {})
            connected_before = st0.get("state") == "connected"
            if not connected_before:
                failures += 1
                print(f"round{i}: precondition unmet (not connected)", flush=True)
                continue
            r = client.call("WIFI_SCAN", {"op_id": str(uuid.uuid4())})
            if not r.get("ok"):
                failures += 1
                print(f"round{i}: scan refused {json.dumps(r)[:80]}", flush=True)
                continue
            job = r["result"]["job_id"]
            term = None
            deadline = time.time() + 30
            while time.time() < deadline:
                term = client.call("JOB_GET", {"job_id": job}).get("result", {})
                if term and term.get("state") in ("succeeded", "failed"):
                    break
                time.sleep(1.0)
            page = client.call("WIFI_SCAN_RESULTS", {"job_id": job, "cursor": None})
            st1 = client.call("WIFI_STATUS").get("result", {})
            state = term.get("state") if term else None
            page_ok = page.get("ok") is True
            still = st1.get("state") == "connected"
            if state == "succeeded" and page_ok and still:
                rounds_ok += 1
                print(f"round{i}: succeeded page_ok=True wifi=connected job={job}", flush=True)
            elif state == "failed" and still:
                recoveries += 1
                print(f"round{i}: RECOVERY_ONLY failed page_ok={page.get('ok')} wifi=connected", flush=True)
            else:
                failures += 1
                print(f"round{i}: {state} page_ok={page.get('ok')} wifi={st1.get('state')}", flush=True)
            # The 8 job slots hold terminal jobs for their 300s retention
            # window; after 8 rounds within one window a new WIFI_SCAN is
            # correctly refused with BUSY/Job capacity. Wait out the oldest
            # job's retention instead of resetting - the refusal is contract
            # behavior, not a defect. The session must stay served during
            # the wait: ping every 8s keeps the 15s TTL alive and drains RX.
            if i < 9:
                waited = 0.0
                while waited < 45.0:
                    client.ping()
                    time.sleep(8.0)
                    waited += 8.0
        boot_ok = client.boot_id == boot0
        print(f"CONTINUOUS COEXIST: success={rounds_ok}/10 recoveries={recoveries} "
              f"failures={failures} single_boot={boot_ok}")
        return 0 if rounds_ok == 10 and boot_ok else 1
    finally:
        client.close()
        ev.close()


def EVIDENCE_DIR():
    return Path(__file__).resolve().parents[2].parents[1] / "tmp" / "mwcp-g2" / "evidence"


if __name__ == "__main__":
    sys.exit(main())
