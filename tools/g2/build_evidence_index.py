#!/usr/bin/env python3

"""Assemble docs/reviews/web-console/g2-evidence-index.json.



2026-10-26 r2 review (G2-R5-A) rewrite:

- Batch attribution is NOT guessed from wide time windows. A run's firmware

  identity comes from its own run manifest when one exists

  (leg2-env-manifest.json / soak metadata); when it cannot be recovered the

  batch is "unknown" with reason "unverified", never a prefix guess.

- SHA fields never contain ellipses: a full 64-hex SHA or the literal

  string "unverified" (in a separate field, never inside the SHA value).

- Raw result status is preserved as ``original_status``; the reviewed

  acceptance status lives in ``accepted_status`` with ``review`` notes

  naming superseded/rejected runs and their replacements.

- Both evidence roots and the HA-half files stay included; files are never

  moved.



An offline self-test (build_evidence_index_selftest.py) covers the r2

review's five index requirements.

"""



from __future__ import annotations



import hashlib

import json

import math

import sys

from datetime import date, datetime, timezone

from pathlib import Path





# MWCP protocol opcodes

MWCP_CODE_HELLO = 0x0001

MWCP_CODE_PING = 0x0002

MWCP_CODE_SESSION_CLOSE = 0x0003

MWCP_CODE_DEVICE_INFO = 0x0010





def _parse_iso8601(s):

    if not isinstance(s, str) or not s:

        return None

    try:

        raw = s.strip()

        if raw.endswith("Z") or raw.endswith("z"):

            raw = raw[:-1] + "+00:00"

        dt = datetime.fromisoformat(raw)

        if dt.tzinfo is None:

            return None

        return dt.astimezone(timezone.utc)

    except Exception:

        return None





COMPONENT = Path(__file__).resolve().parents[2]

WORKSPACE = COMPONENT.parents[1]

EVIDENCE_ROOTS = {

    "workspace": WORKSPACE / "tmp" / "mwcp-g2" / "evidence",

    "component": COMPONENT / "tmp" / "mwcp-g2" / "evidence",

    "session-01": WORKSPACE / "tmp" / "g2-hardware-20261029-session-01" / "evidence",
    "session-02": WORKSPACE / "tmp" / "g2-hardware-20261030-session-02" / "evidence",

    "usb-diag": COMPONENT / "tmp" / "usb-diag",

}

OUT = COMPONENT / "docs" / "reviews" / "web-console" / "g2-evidence-index.json"



SOURCE_SNAPSHOT_FILES = (

    "components/mmwave_host/mmwave_host.cpp", "components/mmwave_host/mmwave_host.h",

    "components/mmwave_host/mwcp_service.cpp", "components/mmwave_host/mwcp_service.h",

    "components/mmwave_host/mwcp_link.h", "components/mmwave_host/tx_pump.h",

    "components/mmwave_host/mwcp_wifi_adapter.cpp", "components/mmwave_host/mwcp_wifi_adapter.h",

    "protocol/cpp/mwcp_codec.h",

    "patches/esphome-2026.9.1-wifi-scan-ownership.patch",

    "scripts/apply_esphome_patch.py", "scripts/build_host_profile.py",

    "tools/g2/run_g2.py", "tools/g2/leg_driver2.py", "tools/g2/mwcp.py",

    "tools/g2/ha_half.py", "tools/g2/build_evidence_index.py",

)



# Batches whose image SHA is fully known (full 64-hex only; historical images

# recovered from build logs / flash records). Unknown stays "unverified".

FIRMWARE_BATCHES = {

    "batch1_prefix": {

        "factory_sha256": "98f841059438afca81482f3e3af453ed6264e817b9664c7b98a131ee3ba2de12",

        "ota_sha256": "7e09cdf1f2f03a5b44420eda76e128c2aee6504d9c68cba541cd405ea74fb010",

        "profile": "tests/r60abd1-esp32c3-host.yaml",

        "identity_basis": "flash-log + RUN.md round 1 (full image hashes recorded)",

    },

    "batch2_p0_fixed": {

        "factory_sha256": "8bfd435633cb904ceca830e88a7047f54c69b549d82c9520282663b7d1cd9df2",

        "ota_sha256": "33f4c89eb38314e5dd57fce088bf2a7d97036ff3d5c93ee48d866d0ff23fc85c",

        "profile": "tests/r60abd1-esp32c3-host.yaml",

        "identity_basis": "flash-log + report §0 (full image hashes recorded)",

    },

    "batch5_net": {

        "factory_sha256": "unverified",

        "factory_sha256_hint": "25742212",  # prefix only, kept in a hint field

        "profile": "esphome-config/r60abd1-host-net.yaml",

        "identity_basis": "unverified: no full image hash recorded in surviving artifacts",

        "superseded": True,

    },

    "batch6_f8": {

        "factory_sha256": "unverified",

        "factory_sha256_hint": "13713b09",

        "profile": "esphome-config/r60abd1-host-net.yaml",

        "identity_basis": "unverified: no full image hash recorded in surviving artifacts",

        "superseded": True,

    },

    "batch7_f9": {

        "factory_sha256": "66037d2f8dc24bd22889ef59bc44adaebed3366e138083363f3f2bd4bdd429f4",

        "profile": "esphome-config/r60abd1-host-net.yaml",

        "identity_basis": "flash-log 2026-10-25 + sha256sum of the surviving build output",

    },

    "batch8_nops": {

        # The bench image's SHA is only trustworthy when the image currently

        # on the bench is proven to be this file. The build output hash goes

        # to build_output_sha256 (it describes THIS tree's artifact), while

        # on_bench_sha256 records what a flash/verify log last confirmed.

        "profile": "esphome-config/r60abd1-host-nops.yaml",

        "identity_basis": "build output of the remediation tree; on-bench identity "

                          "requires the next flash/verify log (r2 review)",

    },

    "batch3_intermediate": {

        "factory_sha256": "unverified",

        "profile": "tests/r60abd1-esp32c3-host.yaml",

        "identity_basis": "unverified: transient build, image not preserved",

        "superseded": True,

    },

    "batch4_intermediate": {

        "factory_sha256": "unverified",

        "profile": "tests/r60abd1-esp32c3-host.yaml",

        "identity_basis": "unverified: transient build, image not preserved",

        "superseded": True,

    },

    "diag_usbecho": {

        "factory_sha256": "unverified",

        "profile": "tmp/usb-diag/usb-echo.yaml",

        "identity_basis": "diagnostic-only image; rebuilt between runs",

        "diagnostic": True,

    },

    "diag_nops_console": {

        "factory_sha256": "unverified",

        "profile": "esphome-config/r60abd1-host-diagc2.yaml",

        "identity_basis": "diagnostic-only image; rebuilt between runs",

        "diagnostic": True,

    },

    "batch9_nops_deferred": {

        "factory_sha256": "acb72caaa4be3657376dea83ca0213b0dc003c8487107fdbfd97f732c34c6c28",

        "profile": "esphome-config/r60abd1-host-nops.yaml",

        "identity_basis": "flash-log-r2.txt 2026-10-26 17:11 (full SHA recorded)",

        "changes": "batch 8 + deferred dispatch (F-10 fix)",

    },

    "batch9_nwf_deferred": {

        "factory_sha256": "d9215d68d52afbd982d71009b095c3ee58c0da1519fd058c17f37f809d7a20cc",

        "profile": "tests/r60abd1-esp32c3-host-nowifi.yaml",

        "identity_basis": "flash-log-r2.txt 2026-10-26 17:13 (full SHA recorded)",

        "changes": "offline image with the F-10 fix",

    },

    "diag_stress_source": {

        "factory_sha256": "87c2168ef0d9f14bdd37ba832bf2f88fb2a22968794da2ebfeeb5cc96af2de5b",

        "profile": "esphome-config/r60abd1-stress-diag.yaml",

        "identity_basis": "flash-log-r2.txt 2026-10-26 17:31 (full SHA recorded)",

        "changes": "batch 9 + controlled 5Hz diagnostic LOG source",

        "diagnostic": True,

    },

    "diag_usbecho_instrumented": {

        "factory_sha256": "d62e3051f41d603cb490282cedf6d466ca1594bf755a43ff6c6b2743787144e7",

        "profile": "tmp/usb-diag/usb-echo.yaml",

        "identity_basis": "build output sha256sum 2026-10-26 16:29 (build tree still holds the image)",

        "diagnostic": True,

    },

    "diag_usbecho_fullstack": {

        "factory_sha256": "082009c3824c4dc35373a17e90f1495afb3374c1ef0c117fe8cadacd054f81d7",

        "profile": "esphome-config/echo-fullstack.yaml",

        "identity_basis": "build output sha256sum 2026-10-26 16:46 (build tree still holds the image)",

        "diagnostic": True,

    },

    "batch10_ownership": {

        "factory_sha256": "6f95de60dcac2ff86f57106fd4b2f19ebf6df24403a104a26a47292ca37cf66a",

        "profile": "esphome-config/r60abd1-host-nops.yaml",

        "identity_basis": "build-log 2026-10-27 03:02 (full SHA recorded); built but "

                          "NOT flashed - awaiting bench authorization",

        "changes": "batch 9 + G2-R3-01 payload ownership (DeferredRequest)",

    },

    "diag_chunk4096": {

        "factory_sha256": "unverified",

        "factory_sha256_hint": "14d7ea81",

        "profile": "esphome-config/r60abd1-host-nops.yaml (diagnostic kChunk=4096 edit, reverted)",

        "identity_basis": "diagnostic bisect build; image overwritten by later builds",

        "diagnostic": True,

    },

    "diag_deferred_first": {

        "factory_sha256": "unverified",

        "factory_sha256_hint": "f8a334cb",

        "profile": "esphome-config/r60abd1-host-nops.yaml (first deferred-dispatch build)",

        "identity_basis": "diagnostic bisect build; image overwritten by batch 9",

        "diagnostic": True,

    },

}



# Reviewed acceptance status (r2 review G2-R5-A item 3): raw result status is

# preserved separately; runs the independent review rejected or superseded

# are recorded here with reasons and replacements.

# Per-run verdicts keyed by the exact result-file stem. Mappings verified

# against each result's own evidence reference and started/ended span

# (G2-R3-05: 191629=60s idle; 211723=2h stress; 232416=2h idle - the earlier

# swap is corrected). New runs stay "pending_review" until independently

# re-verified; a raw pass is never copied into acceptance automatically.

REVIEWED_RUNS = {

    # session-01 hardware delivery runs (2026-10-29 / 2026-10-30 review)

    # The 6 runs with result vs raw sha256 mismatch (original raw irrecoverable due to unversioned rerun overwrite):

    "b1_backpressure": {

        "target_root": "session-01",

        "result_sha256": "6340633bc54e2becae8dba2254866c14519dc689f62b20cf02e3fe99aeaff6f4",

        "accepted_status": "rejected",

        "reason": "result vs raw sha256 mismatch (original raw irrecoverable due to unversioned rerun overwrite; held as diagnostic); requires clean rerun in Batch 2",

        "superseded_by": None,

    },

    "b2_provision": {

        "target_root": "session-01",

        "result_sha256": "c6da3a946d3880efa1a55baca54eac1a0681e9aba82b557f7a9964f17c9e5b2a",

        "accepted_status": "rejected",

        "reason": "result vs raw sha256 mismatch (original raw irrecoverable due to unversioned rerun overwrite; held as diagnostic); requires clean rerun in Batch 2",

        "superseded_by": None,

    },

    "b2_scan_coexist": {

        "target_root": "session-01",

        "result_sha256": "d59826d7c9b3de94e00c0327ead2f3ac3ce8e5652c8559282c337f5306a639c4",

        "accepted_status": "rejected",

        "reason": "result vs raw sha256 mismatch (original raw irrecoverable due to unversioned rerun overwrite; held as diagnostic); requires clean rerun in Batch 2",

        "superseded_by": None,

    },

    "b2_wifi_scan": {

        "target_root": "session-01",

        "result_sha256": "21dea7b3e341d1549769e9f770b18feed04d3e6fe8f072a32af9d625d4ff878e",

        "accepted_status": "rejected",

        "reason": "result vs raw sha256 mismatch (original raw irrecoverable due to unversioned rerun overwrite; held as diagnostic); requires clean rerun in Batch 2",

        "superseded_by": None,

    },

    "b3_config": {

        "target_root": "session-01",

        "result_sha256": "60a588af243de995a90e00347abd18aba2f0cb69b82146a561ba96b3ae3f96ee",

        "accepted_status": "rejected",

        "reason": "result vs raw sha256 mismatch (original raw irrecoverable due to unversioned rerun overwrite; held as diagnostic); requires clean rerun in Batch 2",

        "superseded_by": None,

    },

    "b3_jobs": {

        "target_root": "session-01",

        "result_sha256": "d12ec3f7931215243c01951df5abc0b7e093e41bda754ae175c91aefce5438a4",

        "accepted_status": "rejected",

        "reason": "result vs raw sha256 mismatch (original raw irrecoverable due to unversioned rerun overwrite; held as diagnostic); requires clean rerun in Batch 2",

        "superseded_by": None,

    },

    # Physical power cut and USB unplug (historical runs evaluated under loose/unverified conditions):

    "b3_power_cuts": {

        "target_root": "session-01",

        "result_sha256": "74a204dc1c73532798de3b3c1658b8bec0c085b55edbf3fc7fefac1a4817fde6",

        "accepted_status": "rejected",

        "reason": "legacy run evaluated with unverified soft reset / no physical disconnect verification; refactored into hardware_judges.py, requires 20-round bench rerun in Batch 2",

        "superseded_by": None,

    },

    "b3_usb_unplug": {

        "target_root": "session-01",

        "result_sha256": "6a4a6472c940230a0abb155b4e6cf944e95aa0e4ba5f02723c35ed376199d8db",

        "accepted_status": "rejected",

        "reason": "legacy run evaluated with loose check (len(cfg)>=8); refactored into hardware_judges.py with strict config+revision check, requires 5-round bench rerun in Batch 2",

        "superseded_by": None,

    },

    "b3_human_observe": {

        "target_root": "session-01",

        "result_sha256": "cca53a8b85df5986bbb8d647703fff0b51682b141175ba700926f0d5cd89d690",

        "accepted_status": "rejected",

        "reason": "legacy runner checked nonexistent top-level x_cm/y_cm instead of local_cm/room_cm; refactored, requires multi-phase bench rerun in Batch 2",

        "superseded_by": None,

    },

    # Soak runs (both legitimately failed gate checks):

    "b4_soak_idle_7200s": {

        "target_root": "session-01",

        "result_sha256": "d348d3228594de7a125dead416ca16902b4944e78211798a9979a3c53c36e07e",

        "accepted_status": "rejected",

        "reason": "original status fail (offline_precondition failed due to Wi-Fi association); requires clean unassociated 7200s soak in Batch 2",

        "superseded_by": None,

    },

    "b4_soak_stress_7200s": {

        "target_root": "session-01",

        "result_sha256": "5ebab7aac1bf07210d4e91f72eb223c478d1eebcb3655d6edb9bf4c4616e162c",

        "accepted_status": "rejected",

        "reason": "original status fail (log_pressure_real failed due to zero LOG events in production profile); requires 5Hz diagnostic log firmware 7200s soak in Batch 2",

        "superseded_by": None,

    },

    "b4_dry_run_idle_60s": {

        "target_root": "session-01",

        "result_sha256": "7c2e2552966f6494658c28e80110982747e0861b0c505a9b5b17df1b8392f946",

        "accepted_status": "rejected",

        "reason": "60s idle rehearsal dry-run (not a 7200s soak); target 7200s soak failed gate checks, so rehearsal is not acceptance evidence",

        "superseded_by": None,

    },

    "b4_dry_run_stress_60s": {

        "target_root": "session-01",

        "result_sha256": "fd581a69547b50659c516a6672f114d1f2e971843327300b656702ba85f7742b",

        "accepted_status": "rejected",

        "reason": "60s stress rehearsal dry-run (not a 7200s soak); target 7200s soak failed gate checks, so rehearsal is not acceptance evidence",

        "superseded_by": None,

    },

    "b3_web_serial": {

        "target_root": "session-01",

        "result_sha256": "3884911bcbc0c16739ee9fa68dfd60e85d43cca43a6f7d10ec89e25103c0179c",

        "accepted_status": "pending_review",

        "reason": "manual WebSerial diagnostic log; awaiting independent review",

        "superseded_by": None,

    },

    "g2-07-soak-20261024-051313": {

        "accepted_status": "rejected",

        "reason": "batch-2-era soak: stress path measured an unsubscribed "

                  "window; idle path ran on a static-IP online profile "

                  "without offline proof (r2 review).",

        "superseded_by": "g2-07-soak-20261026-232416 (2h idle) / "

                         "g2-07-soak-20261026-211723 (2h stress)",

    },

    "g2-07-soak-20261024-072026": {

        "accepted_status": "rejected",

        "reason": "batch-2-era soak, same defects as 20261024-051313 (r2 review).",

        "superseded_by": "g2-07-soak-20261026-232416 (2h idle) / "

                         "g2-07-soak-20261026-211723 (2h stress)",

    },

    "g2-07-soak-20261026-015114": {

        "accepted_status": "rejected",

        "reason": "stress soak on batch 8: judge of that era accepted an "

                  "unsubscribed window (r2 review G2-R2-A).",

        "superseded_by": "g2-07-soak-20261026-211723 (2h stress, remediated judge)",

    },

    "g2-07-soak-20261026-131712": {

        "accepted_status": "rejected",

        "reason": "stress soak on batch 8 pre-remediation judge (same as "

                  "015114); superseded by the remediated-judge re-run.",

        "superseded_by": "g2-07-soak-20261026-211723 (2h stress, remediated judge)",

    },

    "g2-07-soak-20261026-191341": {

        "accepted_status": "rejected",

        "reason": "first 2h idle attempt on batch 9-nwf (19:13:41 result of "

                  "the 17:13-19:13 run): the run itself was clean (7200.5s "

                  "span, p95=33.6ms, zero gaps, single boot) but the "

                  "collector hardcoded verified=False for the offline "

                  "precondition, so the judge correctly failed it. Collector "

                  "fixed; superseded by the verified re-run.",

        "superseded_by": "g2-07-soak-20261026-232416 (2h idle re-run)",

    },

    "g2-07-soak-20261026-191629": {

        "accepted_status": "superseded",

        "reason": "60s idle collector-verification run (19:15:29-19:16:29, "

                  "raw g2-07-soak-idle-20261026-191529.jsonl) - proves the "

                  "offline-precondition collector fix; NOT a 2h soak.",

        "superseded_by": "g2-07-soak-20261026-232416 (the full 2h idle run)",

    },

    "g2-07-soak-20261026-211723": {

        "accepted_status": "pending_review",

        "reason": "2h PERSISTENT-STRESS soak (19:17:13-21:17:22, raw "

                  "g2-07-soak-stress-20261026-191713.jsonl) on the "

                  "stress-diag image 87c2168e... with the controlled 5Hz LOG "

                  "source: judge_stress_soak 14/14 PASS, span 7200.4s, "

                  "p95=240.4ms, single boot, zero gaps, subscription never "

                  "unsubscribed (raw RX: 22460 TELEMETRY / 34614 LOG; "

                  "uniform per window). Executor-accepted; awaiting "

                  "independent re-verification.",

        "basis": "flash-log-r2.txt; result checks 14/14; raw jsonl sha "

                 "d738462b5ef97af8a66111324d133c6de4fa37498356b0bfe6dd1854327a9a69",

    },

    "g2-07-soak-20261026-232416": {

        "accepted_status": "pending_review",

        "reason": "2h OFFLINE IDLE soak (21:24:15-23:24:16, raw "

                  "g2-07-soak-idle-20261026-212415.jsonl) on the batch-9-nwf "

                  "image d9215d68...: judge_idle_soak 7/7 PASS incl. "

                  "offline_precondition, span 7200.4s, p95=33.5ms, single "

                  "boot, zero gaps. Executor-accepted; awaiting independent "

                  "re-verification.",

        "basis": "flash-log-r2.txt; result checks 7/7; raw jsonl sha "

                 "1fc24f6b03f04bbb2cbf51b8f56a321dfa95799d91fe821e9de5f0b5f441f347",

    },

}





def sha256(path: Path) -> str:

    return hashlib.sha256(path.read_bytes()).hexdigest()





def _raw_jsonl_for(result_path: str, result_data: dict) -> Path | None:

    """Locate a run's raw jsonl through the result's OWN evidence reference

    first, then through the started timestamp (full date+time). No

    hhmmss-only fuzz (G2-R3-05)."""

    ev = result_data.get("evidence") or {}

    ref = ev.get("file") if isinstance(ev, dict) else None

    if ref:

        cand = Path(ref)

        if cand.is_file():

            return cand

    started = result_data.get("started") or ""

    stamp = started.replace("T", " ").replace(":", "").replace("-", "")

    if not stamp:

        return None

    parent = Path(result_path).parent

    for cand in parent.glob(f"*{stamp}*.jsonl"):

        if not cand.name.endswith(".manifest.json"):

            return cand

    return None





def _normalize_frame(rec: dict) -> dict | None:

    """Normalize frame fields from top-level and meta.

    If top-level and meta fields conflict, the frame is contradictory and cannot be trusted -> returns None.

    """

    if not isinstance(rec, dict):

        return None

    meta = rec.get("meta")

    if meta is not None and not isinstance(meta, dict):

        return None

    meta = meta or {}



    def get_field(name, expected_type):

        v1 = rec.get(name)

        v2 = meta.get(name)

        if v1 is not None and v2 is not None:

            if v1 != v2:

                return None, True

            val = v1

        elif v1 is not None:

            val = v1

        else:

            val = v2

        if val is not None:

            if expected_type is int and isinstance(val, bool):

                return None, True

            if not isinstance(val, expected_type):

                return None, True

        return val, False



    f_dir, conf = get_field("dir", str)

    if conf:

        return None

    f_kind, conf = get_field("kind", int)

    if conf:

        return None

    f_code, conf = get_field("code", int)

    if conf:

        return None

    f_rid, conf = get_field("request_id", int)

    if conf:

        return None

    f_sid, conf = get_field("session_id", int)

    if conf:

        return None



    # Direction and Kind consistency

    # kind: 1 = request (tx), 2 = response (rx), 3 = event (rx), 4 = note

    is_tx = False

    is_rx = False

    if f_dir == "tx" and f_kind == 1:

        is_tx = True

    elif f_dir == "tx" and f_kind is None:

        is_tx = True

    elif f_dir is None and f_kind == 1:

        is_tx = True

    elif (f_dir == "rx" or f_dir is None) and (f_kind == 2 or (f_kind is None and f_dir == "rx")):

        is_rx = True



    # Direction vs kind contradictions (e.g. dir=rx with kind=1, or dir=tx with kind in (2, 3))

    if (f_dir == "rx" and f_kind == 1) or (f_dir == "tx" and f_kind in (2, 3)):

        return None



    if f_sid is not None and not (0 <= f_sid <= 0xFFFFFFFF):

        return None

    if f_rid is not None and not (0 <= f_rid <= 0xFFFFFFFF):

        return None



    payload = rec.get("payload")

    if payload is not None and not isinstance(payload, dict):

        return None



    return {

        "is_tx": is_tx,

        "is_rx": is_rx,

        "dir": f_dir,

        "kind": f_kind,

        "code": f_code,

        "request_id": f_rid,

        "session_id": f_sid,

        "payload": payload or {},

        "raw": rec,

    }





def _raw_correlated_identities(jsonl: Path) -> tuple[set, set]:

    """Parse raw jsonl and extract verified (boot_ids, device_ids) strictly from

    successful RX responses that correlate with genuine TX requests.

    - Direction must be 'rx' (dir == 'rx' and kind != 1).

    - Code must be 1 (HELLO) or 16 (DEVICE_INFO).

    - payload.ok must be True.

    - For HELLO (code 1): the RX response must match a preceding TX request with matching

      request_id and nonce, session=0 on request, non-zero session allocated on response.

    - For DEVICE_INFO (code 16): the RX response must match a preceding TX request with

      matching request_id and active session.

    - For SESSION_CLOSE (code 3): closes the active session and clears pending requests;

      does NOT extract identity from response.

    """

    boots = set()

    devs = set()

    pending_hello = {}        # request_id -> (nonce, session_id)

    pending_device_info = {}  # request_id -> session_id

    pending_close = {}        # request_id -> session_id

    active_sessions = set()

    current_hello_nonce = None

    try:

        for line in jsonl.read_text(encoding="utf-8").splitlines():

            line = line.strip()

            if not line:

                continue

            try:

                rec = json.loads(line)

            except Exception:

                continue



            frame = _normalize_frame(rec)

            if frame is None:

                continue



            code = frame["code"]

            rid = frame["request_id"]

            sid = frame["session_id"]

            payload = frame["payload"]



            # Track TX requests for correlation

            if frame["is_tx"]:

                if rid is None or sid is None:

                    continue

                if code == MWCP_CODE_HELLO:

                    # HELLO request session_id MUST be 0

                    if sid != 0:

                        continue

                    n = payload.get("nonce") or frame["raw"].get("nonce")

                    if n and isinstance(n, str):

                        # Protocol §3.1: if a new nonce is issued, clear stale pending handshakes

                        if current_hello_nonce is None or str(n) != current_hello_nonce:

                            current_hello_nonce = str(n)

                            pending_hello = {r: v for r, v in pending_hello.items() if v[0] == str(n)}

                        pending_hello[rid] = (str(n), sid)

                elif code == MWCP_CODE_DEVICE_INFO:

                    # DEVICE_INFO request session_id MUST be in active_sessions

                    if sid == 0 or not active_sessions or sid not in active_sessions:

                        continue

                    pending_device_info[rid] = sid

                elif code == MWCP_CODE_SESSION_CLOSE:

                    # SESSION_CLOSE request session_id MUST be in active_sessions

                    if sid == 0 or not active_sessions or sid not in active_sessions:

                        continue

                    pending_close[rid] = sid

                continue



            # Genuine RX response required

            if frame["is_rx"]:

                if code not in (MWCP_CODE_HELLO, MWCP_CODE_DEVICE_INFO, MWCP_CODE_SESSION_CLOSE):

                    continue

                if rid is None or sid is None:

                    continue

                if payload.get("ok") is not True:

                    continue

                res = payload.get("result")

                if not isinstance(res, dict):

                    continue



                if code == MWCP_CODE_HELLO:

                    # HELLO response MUST allocate a non-zero session_id

                    if sid == 0:

                        continue

                    if rid not in pending_hello:

                        continue

                    tx_nonce, tx_sid = pending_hello[rid]

                    rx_nonce = res.get("nonce")

                    if not rx_nonce or not isinstance(rx_nonce, str) or rx_nonce != tx_nonce:

                        # Stale or mismatched nonce: do NOT pop pending_hello[rid]

                        continue



                    # Handshake matched: now consume pending request

                    pending_hello.pop(rid)



                    # Protocol §3.1: new nonce / session establishes current session and resets old session

                    active_sessions = {sid}

                    pending_device_info = {r: s for r, s in pending_device_info.items() if s == sid}

                    pending_close = {r: s for r, s in pending_close.items() if s == sid}



                    b = res.get("boot_id")

                    if isinstance(b, str) and b.strip():

                        boots.add(b.strip())

                    d = res.get("device_id")

                    if isinstance(d, str) and d.strip():

                        devs.add(d.strip())

                    ident = res.get("identity")

                    if isinstance(ident, dict):

                        d2 = ident.get("device_id")

                        if isinstance(d2, str) and d2.strip():

                            devs.add(d2.strip())

                        b2 = ident.get("boot_id")

                        if isinstance(b2, str) and b2.strip():

                            boots.add(b2.strip())



                elif code == MWCP_CODE_DEVICE_INFO:

                    if not active_sessions or sid not in active_sessions:

                        continue

                    if rid not in pending_device_info:

                        continue

                    tx_sid = pending_device_info[rid]

                    if tx_sid != sid:

                        continue



                    # Matched: consume pending request

                    pending_device_info.pop(rid)



                    d = res.get("device_id")

                    if isinstance(d, str) and d.strip():

                        devs.add(d.strip())

                    b = res.get("boot_id")

                    if isinstance(b, str) and b.strip():

                        boots.add(b.strip())

                    ident = res.get("identity")

                    if isinstance(ident, dict):

                        d2 = ident.get("device_id")

                        if isinstance(d2, str) and d2.strip():

                            devs.add(d2.strip())

                        b2 = ident.get("boot_id")

                        if isinstance(b2, str) and b2.strip():

                            boots.add(b2.strip())



                elif code == MWCP_CODE_SESSION_CLOSE:

                    if not active_sessions or sid not in active_sessions:

                        continue

                    if rid not in pending_close:

                        continue

                    tx_sid = pending_close[rid]

                    if tx_sid != sid:

                        continue



                    # Matched: consume pending request

                    pending_close.pop(rid)



                    # Close session: clear active session and its pending requests

                    active_sessions.discard(sid)

                    pending_device_info = {r: s for r, s in pending_device_info.items() if s != sid}

                    pending_close = {r: s for r, s in pending_close.items() if s != sid}

                    # IMPORTANT: SESSION_CLOSE does NOT extract identity, even if result contains device_id/boot_id

    except Exception:

        return set(), set()

    return boots, devs





def _coverage_declaration_conflict(manifest: dict, result_data: dict) -> str | None:
    """R9-02: cross-check the manifest's declared measured coverage against
    EVERY actual-coverage copy the result carries.  The manifest is written
    by the same collector run, so a disagreement (beyond the shared
    max(5 s, 5 %) tolerance) means one of the two files was edited/rebound -
    the sidecar cannot be trusted and the run stays unknown."""
    claimed = manifest.get("actual_duration_seconds") if isinstance(manifest, dict) else None
    if claimed is None:
        return None  # manifest makes no measured-coverage claim
    if isinstance(claimed, bool) or not isinstance(claimed, (int, float)) \
            or not math.isfinite(float(claimed)) or float(claimed) <= 0:
        return f"manifest actual_duration_seconds is not a positive finite number ({claimed!r})"
    claimed = float(claimed)
    ji = result_data.get("judge_input") if isinstance(result_data.get("judge_input"), dict) else {}
    copies = []
    for kind, getter in (
        ("actual_duration_seconds", lambda: result_data.get("actual_duration_seconds")),
        ("judge_input.actual_duration_seconds", lambda: ji.get("actual_duration_seconds")),
        ("observed_duration_seconds", lambda: result_data.get("observed_duration_seconds")),
        ("judge_input.observed_duration_seconds", lambda: ji.get("observed_duration_seconds")),
        ("monotonic_span_s", lambda: result_data.get("monotonic_span_s")),
        ("judge_input.monotonic_span_s", lambda: ji.get("monotonic_span_s")),
    ):
        v = getter()
        if v is None:
            continue
        if isinstance(v, bool) or not isinstance(v, (int, float)) \
                or not math.isfinite(float(v)) or float(v) <= 0:
            return f"result {kind} is not a positive finite number ({v!r})"
        copies.append((kind, float(v)))
    if not copies:
        return None  # result declares no measured coverage: nothing to contradict
    for kind, v in copies:
        tol = max(5.0, max(v, claimed) * 0.05)
        if abs(v - claimed) > tol:
            return (f"manifest actual_duration_seconds ({claimed}s) conflicts "
                    f"with result {kind} ({v}s)")
    return None





def _raw_boot_ids(jsonl: Path) -> set:

    """Boot IDs verified via correlated protocol responses."""

    boots, _ = _raw_correlated_identities(jsonl)

    return boots





def _raw_device_ids(jsonl: Path) -> set:

    """Device IDs verified via correlated protocol responses."""

    _, devs = _raw_correlated_identities(jsonl)

    return devs





def _raw_experiment_ids(jsonl: Path) -> set:

    """Every experiment_id / run_id recorded in raw frames or envelope notes."""

    exp_ids = set()

    try:

        for line in jsonl.read_text(encoding="utf-8").splitlines():

            line = line.strip()

            if not line:

                continue

            try:

                rec = json.loads(line)

            except Exception:

                continue

            if not isinstance(rec, dict):

                continue

            e = rec.get("experiment_id") or rec.get("run_id")

            if isinstance(e, str) and e:

                exp_ids.add(e)

            meta = rec.get("meta")

            if isinstance(meta, dict):

                e = meta.get("experiment_id") or meta.get("run_id")

                if isinstance(e, str) and e:

                    exp_ids.add(e)

            if rec.get("dir") == "note" or rec.get("event") == "experiment_envelope":

                e = rec.get("experiment_id") or rec.get("run_id")

                if isinstance(e, str) and e:

                    exp_ids.add(e)

                note_data = rec.get("note")

                if isinstance(note_data, dict):

                    e = note_data.get("experiment_id") or note_data.get("run_id")

                    if isinstance(e, str) and e:

                        exp_ids.add(e)

    except Exception:

        return set()

    return exp_ids





def run_manifest_for(result_path: str, result_data: dict) -> dict | None:

    """The PER-RUN manifest sidecar for this result, or None.



    G2-R3-05 (r3f): STRICT identity binding:

    - raw_sha256 must match raw file hash

    - result_sha256 must match result file hash (detects tampering/checks modification)

    - run_id / experiment_id must match exactly

    - started and ended must be valid timezone-aware ISO8601 and match exactly (no slack)

    - boot_id_initial must exist in verified raw_boots

    - device_id must be present on manifest, result, and raw_devs and match EXACTLY (no substring)

    - evidence.sha256 must match raw hash"""

    jsonl = _raw_jsonl_for(result_path, result_data)

    if jsonl is None or not jsonl.is_file():

        return None

    sidecar = jsonl.with_name(jsonl.stem + ".manifest.json")

    if not sidecar.is_file():

        return None

    try:

        mdata = json.loads(sidecar.read_text(encoding="utf-8"))

    except Exception:

        return None

    if not isinstance(mdata, dict):

        return None



    # Content binding: raw_sha256

    want_raw = mdata.get("raw_sha256")

    if not isinstance(want_raw, str) or len(want_raw) != 64 or not all(c in "0123456789abcdef" for c in want_raw.lower()) or want_raw == "0"*64:

        return None

    actual_raw_sha = sha256(jsonl)

    if actual_raw_sha.lower() != want_raw.lower():

        return None



    # Content binding: result_sha256 (must exist in manifest and match result file content)

    want_res = mdata.get("result_sha256")

    if not isinstance(want_res, str) or len(want_res) != 64 or not all(c in "0123456789abcdef" for c in want_res.lower()) or want_res == "0"*64:

        return None

    actual_res_sha = sha256(Path(result_path))

    if actual_res_sha.lower() != want_res.lower():

        return None



    # Check result evidence reference matches actual raw hash

    ev = result_data.get("evidence")

    if not isinstance(ev, dict):

        return None

    ev_ref_sha = ev.get("sha256")

    if not ev_ref_sha or ev_ref_sha.lower() != actual_raw_sha.lower():

        return None



    # Check result ref if declared

    want_ref = mdata.get("result_ref")

    if want_ref and Path(result_path).name != want_ref:

        return None



    # Check run ID consistency: run_id / experiment_id must match exactly

    res_exp = result_data.get("experiment_id")

    m_exp = mdata.get("experiment_id")

    res_run = result_data.get("run_id")

    m_run = mdata.get("run_id")



    # If both result and manifest declare experiment_id, they must match

    if res_exp and m_exp and res_exp != m_exp:

        return None

    # If both result and manifest declare run_id, they must match

    if res_run and m_run and res_run != m_run:

        return None



    canon_exp = res_exp or res_run

    m_canon_exp = m_exp or m_run

    if not canon_exp or not m_canon_exp or canon_exp != m_canon_exp:

        return None



    # Check raw experiment_ids: raw MUST carry experiment envelope, cannot be empty

    raw_exps = _raw_experiment_ids(jsonl)

    if not raw_exps:

        return None

    allowed_ids = {canon_exp, m_canon_exp}

    if res_exp:

        allowed_ids.add(res_exp)

    if m_exp:

        allowed_ids.add(m_exp)

    if res_run:

        allowed_ids.add(res_run)

    if m_run:

        allowed_ids.add(m_run)

    if any(r_exp not in allowed_ids for r_exp in raw_exps) or canon_exp not in raw_exps:

        return None



    m_tag = mdata.get("run_tag")

    if m_tag and not jsonl.stem.startswith(m_tag):

        return None



    # Check timestamps: result started/ended vs manifest started/ended (exact match in UTC)

    res_start = _parse_iso8601(result_data.get("started"))

    m_start = _parse_iso8601(mdata.get("started"))

    res_end = _parse_iso8601(result_data.get("ended"))

    m_end = _parse_iso8601(mdata.get("ended"))

    if res_start is None or m_start is None or res_end is None or m_end is None:

        return None

    if res_start != m_start or res_end != m_end:

        return None



    # Check boot identity: raw MUST carry boot IDs, claimed_boot must be non-empty and in raw_boots

    raw_boots = _raw_boot_ids(jsonl)

    if not raw_boots:

        return None

    claimed_boot = mdata.get("boot_id_initial")

    if not isinstance(claimed_boot, str) or not claimed_boot or claimed_boot not in raw_boots:

        return None



    # Check device identity: exact equality, no substring matching

    raw_devs = _raw_device_ids(jsonl)

    if not raw_devs:

        return None

    m_board = mdata.get("board")

    m_dev_id = None

    if isinstance(m_board, dict):

        m_dev_id = m_board.get("device_id")

    elif isinstance(m_board, str):

        m_dev_id = m_board

    if not isinstance(m_dev_id, str) or not m_dev_id:

        return None

    if m_dev_id not in raw_devs:

        return None



    res_board = result_data.get("board_id") or result_data.get("device_id")

    if not isinstance(res_board, str) or not res_board:

        return None

    if res_board != m_dev_id or res_board not in raw_devs:

        return None



    # Check flashed_image_sha256 format if provided

    img = mdata.get("flashed_image_sha256")

    if img and img != "unverified":

        if not (isinstance(img, str) and len(img) == 64 and all(c in "0123456789abcdef" for c in img.lower()) and img.lower() != "0"*64):

            return None



    # R9-02: the sidecar's declared measured coverage must agree with the

    # result's own declared copies (no rebinding one file past the other).

    conflict = _coverage_declaration_conflict(mdata, result_data)

    if conflict is not None:

        return None



    return mdata





def batch_for_run(run_id: str | None, result_path: str, manifest: dict | None) -> dict:

    """Firmware identity for a run: ONLY this run's own sidecar manifest with verified flash record.

    Missing flash record, non-hex, or zero SHA -> unverified/unknown."""

    if not manifest or not isinstance(manifest.get("flashed_image_sha256"), str):

        return {"batch": "unknown", "factory_sha256": "unverified",

                "identity_basis": "unverified: no verified flash record for this run"}



    img = manifest["flashed_image_sha256"].lower()

    if len(img) != 64 or not all(c in "0123456789abcdef" for c in img) or img == "0" * 64:

        return {"batch": "unknown", "factory_sha256": "unverified",

                "identity_basis": "unverified: no verified flash record for this run"}



    flash_rec = manifest.get("flash_record")

    if not isinstance(flash_rec, dict):

        return {"batch": "unknown", "factory_sha256": "unverified",

                "identity_basis": "unverified: no verified flash record for this run"}



    m_board = manifest.get("board")

    m_dev = m_board.get("device_id") if isinstance(m_board, dict) else (m_board if isinstance(m_board, str) else None)



    import flash_verifier

    verified_img, verified_rec, notes = flash_verifier.verify_flash_record(

        flash_rec,

        run_started=manifest.get("started"),

        run_ended=manifest.get("ended"),

        target_device_id=m_dev,

    )

    if verified_img == "unverified" or not verified_rec:

        reason = notes[0] if notes else "unverified: no verified flash record for this run"

        return {"batch": "unknown", "factory_sha256": "unverified", "identity_basis": reason}



    if verified_img != img:

        return {"batch": "unknown", "factory_sha256": "unverified",

                "identity_basis": "image sha mismatch between manifest and verified flash record"}



    return {

        "batch": "manifest-linked",

        "factory_sha256": img,

        "identity_basis": f"per-run manifest with verified flash record (run_tag={manifest.get('run_tag')}, "

                          f"profile={manifest.get('image_profile')})",

    }





def build_index(evidence_roots: dict, out_path: Path, reviewed: dict,

                batches: dict, sources_snapshot: dict | None = None) -> dict:

    """Assemble the index over the given roots (G2-R3-05: injectable so

    the integration test drives the REAL indexing path over sandbox

    roots)."""

    files = []

    runs = []

    seen_paths = set()

    for root_name, root in evidence_roots.items():

        if not root.is_dir():

            continue

        patterns = ("*.jsonl", "*.result.json") if root_name != "usb-diag"             else ("f10_*.jsonl", "validate_*.jsonl", "*reconnect_diag*.jsonl")

        for pattern in patterns:

            for path in sorted(root.glob(pattern)):

                rel = str(path)

                if rel in seen_paths:

                    continue

                seen_paths.add(rel)

                files.append({"path": rel, "root": root_name, "sha256": sha256(path),

                              "bytes": path.stat().st_size})

    all_runs_identifiers = []
    for p_str in seen_paths:
        if p_str.endswith(".result.json"):
            try:
                p_obj = Path(p_str)
                d = json.loads(p_obj.read_text(encoding="utf-8"))
                rid = d.get("run_id")
                st = p_obj.stem
                st_no = st[:-7] if st.endswith(".result") else st
                all_runs_identifiers.append((rid, st_no, str(p_obj.resolve())))
            except Exception:
                pass

    RAW_EXEMPT_RUN_IDS = {"g2-07-judge-selftest", "g2-07-soak-judge-selftest"}
    run_records_meta = []

    for path in sorted(seen_paths):

        if not path.endswith(".result.json"):

            continue

        try:

            data = json.loads(Path(path).read_text(encoding="utf-8"))

        except Exception:

            continue

        run_id = data.get("run_id")

        # r2 review: soak runs share one run_id, so the review verdicts key on

        # the result FILE NAME (immutable per run), falling back to run_id.

        stem = Path(path).stem

        stem_no_ext = stem[:-7] if stem.endswith(".result") else stem

        # Resolve evidence root for run to prevent cross-batch review pollution (G2-HW-R1-A)
        run_root = None
        for rname, rdir in evidence_roots.items():
            try:
                Path(path).resolve().relative_to(rdir.resolve())
                run_root = rname
                break
            except Exception:
                pass

        # Re-initialize output and review state cleanly on EVERY loop iteration (R1-A)
        accepted = "pending_review"
        review_note = None
        superseded_target = None
        review = None
        boundary = False

        file_sha = sha256(Path(path))
        candidates = [
            reviewed.get(f"{run_root}/{stem_no_ext}"),
            reviewed.get(f"{run_root}/{stem}"),
            reviewed.get(stem),
            reviewed.get(stem_no_ext),
            reviewed.get(run_id)
        ]
        for cand in candidates:
            if not cand or not isinstance(cand, dict):
                continue
            cand_root = cand.get("target_root") or cand.get("target_dir")
            if cand_root and run_root and cand_root != run_root:
                continue
            review = cand
            break

        manifest = run_manifest_for(path, data)
        batch_info = batch_for_run(run_id, path, manifest)

        jsonl_path = _raw_jsonl_for(path, data)
        if jsonl_path and jsonl_path.is_file():
            mfile = jsonl_path.with_name(jsonl_path.stem + ".manifest.json")
            if mfile.is_file():
                try:
                    mdata = json.loads(mfile.read_text(encoding="utf-8"))
                    boundary = bool(mdata.get("boundary_violation") or
                                    mdata.get("not_valid_acceptance_evidence"))
                except Exception:
                    pass
            try:
                last_line = jsonl_path.read_text(encoding="utf-8").splitlines()[-1]
                boundary = boundary or bool(json.loads(last_line).get("boundary_violation"))
            except Exception:
                pass

        # Always compute raw_integrity_ok for every run (R6-03)
        raw_integrity_ok = True
        raw_integrity_note = None
        is_raw_exempt = (run_id in RAW_EXEMPT_RUN_IDS or stem_no_ext in RAW_EXEMPT_RUN_IDS)
        if not is_raw_exempt:
            if "evidence" not in data or data.get("evidence") is None:
                raw_integrity_ok = False
                raw_integrity_note = "missing required evidence reference"
        for ev_k in ("evidence", "evidence_2"):
            if not raw_integrity_ok:
                break
            if ev_k in data:
                ref = data.get(ev_k)
                if ev_k == "evidence" and is_raw_exempt and ref is None:
                    continue
                if ev_k == "evidence_2" and ref is None:
                    continue
                if not isinstance(ref, dict):
                    raw_integrity_ok = False
                    raw_integrity_note = f"{ev_k} is not a valid dict"
                    break
                raw_file_str = ref.get("file")
                raw_expected_sha = ref.get("sha256")
                if not raw_file_str or not isinstance(raw_file_str, str):
                    raw_integrity_ok = False
                    raw_integrity_note = f"{ev_k} missing valid file path"
                    break
                if (
                    not raw_expected_sha
                    or not isinstance(raw_expected_sha, str)
                    or len(raw_expected_sha) != 64
                    or not all(c in "0123456789abcdef" for c in raw_expected_sha.lower())
                ):
                    raw_integrity_ok = False
                    raw_integrity_note = f"{ev_k} missing valid 64-hex sha256"
                    break
                raw_p = Path(raw_file_str)
                if not raw_p.is_absolute():
                    cand = Path(path).parent / raw_p
                    if cand.is_file():
                        raw_p = cand
                    else:
                        found_cands = []
                        seen_resolved = set()
                        for base_dir in (WORKSPACE, COMPONENT, *evidence_roots.values()):
                            cand_b = base_dir / raw_p
                            if cand_b.is_file():
                                res_b = str(cand_b.resolve())
                                if res_b not in seen_resolved:
                                    seen_resolved.add(res_b)
                                    found_cands.append(cand_b)
                        if len(found_cands) > 1:
                            raw_integrity_ok = False
                            raw_integrity_note = f"{ev_k} relative path '{raw_file_str}' is ambiguous across multiple roots"
                            break
                        if len(found_cands) == 1:
                            raw_p = found_cands[0]
                if not raw_p.is_file():
                    raw_integrity_ok = False
                    raw_integrity_note = f"{ev_k} raw file missing ({raw_file_str})"
                    break
                actual_sha = sha256(raw_p)
                if actual_sha != raw_expected_sha:
                    raw_integrity_ok = False
                    raw_integrity_note = f"{ev_k} raw file modified (expected {raw_expected_sha[:8]}, got {actual_sha[:8]})"
                    break

        if boundary:
            accepted = "invalid: boundary violation (no bench authorization)"
            review_note = "executed without bench authorization; recorded as a violation, not evidence"
            superseded_target = None
        else:
            if review:
                cand_res_sha = review.get("result_sha256")
                if not cand_res_sha:
                    accepted = "pending_review"
                    review_note = "unverified legacy review: missing result_sha256 content binding"
                    superseded_target = None
                elif cand_res_sha != file_sha:
                    accepted = "pending_review"
                    review_note = f"review hash mismatch: result content modified ({file_sha[:8]} != {cand_res_sha[:8]})"
                    superseded_target = None
                elif not raw_integrity_ok:
                    accepted = "pending_review"
                    review_note = f"evidence integrity check failed: {raw_integrity_note}"
                    superseded_target = None
                else:
                    accepted = review.get("accepted_status", "pending_review")
                    superseded_target = review.get("superseded_by")
                    review_note = review.get("reason")
            else:
                accepted = "pending_review"
                review_note = None
                superseded_target = None

        run_entry = {
            "run_id": run_id,
            "original_status": data.get("status"),
            "accepted_status": accepted,
            "review_note": review_note,
            "superseded_by": superseded_target,
            "started": data.get("started"),
            "ended": data.get("ended"),
            "batch": batch_info["batch"],
            "directory_batch": run_root or "unknown",
            "firmware_verified": (batch_info["batch"] == "manifest-linked" and batch_info["factory_sha256"] != "unverified"),
            "factory_sha256": batch_info["factory_sha256"],
            "identity_basis": batch_info["identity_basis"],
            "checks_total": len(data.get("checks", [])),
            "checks_passed": sum(1 for c in data.get("checks", []) if c.get("pass")),
            "failed_checks": [c["name"] for c in data.get("checks", []) if not c.get("pass")],
            "notes_head": (data.get("notes") or [])[:6],
            "result_file": path,
        }
        runs.append(run_entry)
        run_records_meta.append({
            "entry": run_entry,
            "run_id": run_id,
            "stem": stem,
            "stem_no_ext": stem_no_ext,
            "path": path,
            "data": data,
            "manifest": manifest,
            "batch_info": batch_info,
            "review": review,
            "raw_integrity_ok": raw_integrity_ok,
        })

    # Phase 2: Two-stage / graph-wide validation of superseded_by relationships (R6-03)
    def _match_target_metas(target_key: str, self_meta: dict) -> list[dict]:
        return [
            m for m in run_records_meta
            if m is not self_meta
            and (m["run_id"] == target_key or m["stem_no_ext"] == target_key or m["stem"] == target_key)
            and m["run_id"] != self_meta["run_id"]
            and m["stem_no_ext"] != self_meta["stem_no_ext"]
        ]

    def _extract_run_window_s(d: dict) -> float | None:
        """Compute the started..ended window in seconds (R8-02 cross-validation).

        Returns the window in seconds if both fields are valid ISO-8601
        timestamps, else None.
        """
        from datetime import datetime, timezone
        started = d.get("started")
        ended = d.get("ended")
        if not isinstance(started, str) or not isinstance(ended, str):
            return None
        try:
            # Accept both +0000 and +00:00 timezone formats
            s_str = started.replace("+0000", "+00:00").replace("+0800", "+08:00")
            e_str = ended.replace("+0000", "+00:00").replace("+0800", "+08:00")
            s_dt = datetime.fromisoformat(s_str)
            e_dt = datetime.fromisoformat(e_str)
            window = (e_dt - s_dt).total_seconds()
            return window if window > 0 else None
        except (ValueError, TypeError):
            return None

    def _extract_run_duration(d: dict) -> tuple[float | None, str | None]:
        """Extract verifiable ACTUAL run coverage across ALL declared copies
        (R9-02).

        Field-source semantics by result version — EVERY present copy is a
        declaration that must be checked, never just the first one:
          - ``actual_duration_seconds`` / ``observed_duration_seconds`` /
            ``monotonic_span_s``, each at result top level AND inside
            ``judge_input``.  A collector that emits a field at one level
            must not contradict itself at the other; if a version
            deprecates a field, its absence is simply not a declaration
            (no implicit value invention).
          - ``duration_seconds`` / ``seconds`` / ``requested_seconds`` are
            *requested/planned* values: never actual coverage, never a
            fallback (requested-only -> (None, "missing")).

        Validation of each declared copy: a bool, a non-number, a
        non-finite value, or a value <= 0 makes the coverage unverifiable
        — a bad copy is NOT masked by a good sibling (R9-02: no priority
        ordering between levels).

        Consistency: all declared copies must agree within
        max(5 s, 5 % of the largest); any contradiction -> (None, reason).
        The surviving value is then cross-checked against the
        started..ended window in BOTH directions (same tolerance): a gross
        mismatch means the measurement contradicts its own window.
        """
        import math
        ji = d.get("judge_input") if isinstance(d.get("judge_input"), dict) else {}
        declarations: list[tuple[str, float]] = []

        def _declare(kind: str, v) -> str | None:
            if v is None:
                return None  # not a declaration in this version
            if isinstance(v, bool) or not isinstance(v, (int, float)):
                return f"{kind} is {type(v).__name__}, not a number"
            fv = float(v)
            if not math.isfinite(fv):
                return f"{kind} is not finite ({v!r})"
            if fv <= 0.0:
                return f"{kind} is non-positive ({v!r})"
            declarations.append((kind, fv))
            return None

        for kind, getter in (
            ("actual_duration_seconds", lambda: d.get("actual_duration_seconds")),
            ("judge_input.actual_duration_seconds", lambda: ji.get("actual_duration_seconds")),
            ("observed_duration_seconds", lambda: d.get("observed_duration_seconds")),
            ("judge_input.observed_duration_seconds", lambda: ji.get("observed_duration_seconds")),
            ("monotonic_span_s", lambda: d.get("monotonic_span_s")),
            ("judge_input.monotonic_span_s", lambda: ji.get("monotonic_span_s")),
        ):
            err = _declare(kind, getter())
            if err is not None:
                return None, err
        if not declarations:
            return None, "no actual coverage declared (requested fields never vouch)"

        # All declared copies must agree (no priority ordering between
        # levels: contradictory copies make the coverage unverifiable).
        values = [v for _, v in declarations]
        ref = max(values)
        tolerance = max(5.0, ref * 0.05)
        lo, hi = min(values), max(values)
        if hi - lo > tolerance:
            kinds = ", ".join(f"{k}={v}" for k, v in declarations)
            return None, (f"coverage measurement copies conflict: {kinds} "
                          f"(spread {hi - lo:.1f}s > tolerance {tolerance:.1f}s)")

        dur = values[0]
        # Cross-validate the surviving value against the started..ended
        # window, both directions.
        window_s = _extract_run_window_s(d)
        if window_s is not None and window_s > 0.0:
            w_tol = max(5.0, window_s * 0.05)
            if dur > window_s + w_tol or dur < window_s - w_tol:
                return None, (f"actual coverage {dur}s contradicts its own "
                              f"started..ended window ({window_s}s)")
        return dur, None

    def _extract_run_device(d: dict, man: dict | None) -> str | None:
        for v in (
            d.get("device_id"),
            d.get("board_id"),
            (man or {}).get("board", {}).get("device_id") if isinstance((man or {}).get("board"), dict) else None,
        ):
            if isinstance(v, str) and v.strip() and v.strip().lower() not in ("unknown", "unverified"):
                return v.strip()
        return None

    def _extract_run_fw(d: dict, man: dict | None, binfo: dict) -> str | None:
        for v in (
            binfo.get("factory_sha256"),
            (man or {}).get("flashed_image_sha256") if isinstance(man, dict) else None,
            d.get("firmware_sha256"),
        ):
            if isinstance(v, str) and len(v.strip()) == 64 and all(c in "0123456789abcdef" for c in v.strip().lower()) and v.strip().lower() != "0" * 64:
                return v.strip().lower()
        return None

    def _extract_tool_version(d: dict, man: dict | None) -> str | None:
        ji = d.get("judge_input") if isinstance(d.get("judge_input"), dict) else {}
        col = (man or {}).get("collector") if isinstance((man or {}).get("collector"), dict) else {}
        for v in (d.get("tool_version"), ji.get("tool_version"), (man or {}).get("tool_version") if isinstance(man, dict) else None, col.get("tool_version")):
            if isinstance(v, str) and v.strip():
                return v.strip()
        return None

    def _extract_structured_scenario(d: dict, man: dict | None) -> str | None:
        ji = d.get("judge_input") if isinstance(d.get("judge_input"), dict) else {}
        for v in (
            d.get("scenario"),
            ji.get("scenario"),
            (man or {}).get("scenario") if isinstance(man, dict) else None,
            (man or {}).get("run_tag") if isinstance(man, dict) else None,
        ):
            if isinstance(v, str) and v.strip():
                s = v.strip().lower()
                for known in ("wifi", "soak", "backpressure", "reconnect", "human", "power", "usb", "job", "provision", "config", "combined", "connected"):
                    if known in s:
                        return known
                return s
        return None

    def _extract_structured_mode(d: dict, man: dict | None) -> str | None:
        ji = d.get("judge_input") if isinstance(d.get("judge_input"), dict) else {}
        for v in (
            ji.get("mode"),
            d.get("soak_mode"),
            d.get("mode"),
            (man or {}).get("mode") if isinstance(man, dict) else None,
        ):
            if isinstance(v, str) and v.strip():
                return v.strip().lower()
        return None

    # First detect any cycles in the superseded_by graph regardless of order
    cycle_members: set[int] = set()
    for idx_m, m in enumerate(run_records_meta):
        if m["entry"]["accepted_status"] != "superseded":
            continue
        visited_indices = [idx_m]
        curr_m = m
        while curr_m["entry"]["accepted_status"] == "superseded":
            t_key = curr_m["entry"]["superseded_by"]
            if not t_key or not isinstance(t_key, str):
                break
            t_matches = [
                (i, cand_m) for i, cand_m in enumerate(run_records_meta)
                if cand_m is not curr_m
                and (cand_m["run_id"] == t_key or cand_m["stem_no_ext"] == t_key or cand_m["stem"] == t_key)
            ]
            if len(t_matches) != 1:
                break
            next_idx, next_m = t_matches[0]
            if next_idx in visited_indices:
                for cyc_i in visited_indices[visited_indices.index(next_idx):]:
                    cycle_members.add(cyc_i)
                cycle_members.add(idx_m)
                break
            visited_indices.append(next_idx)
            curr_m = next_m

    for idx_m, m in enumerate(run_records_meta):
        entry = m["entry"]
        if entry["accepted_status"] != "superseded":
            continue
        superseded_target = entry["superseded_by"]
        run_id = m["run_id"]
        stem_no_ext = m["stem_no_ext"]
        stem = m["stem"]
        data = m["data"]

        if not superseded_target or not isinstance(superseded_target, str) or not superseded_target.strip():
            entry["accepted_status"] = "pending_review"
            entry["review_note"] = "invalid superseded_by: replacement target is missing or empty"
            entry["superseded_by"] = None
            continue

        if superseded_target in (run_id, stem_no_ext, stem):
            entry["accepted_status"] = "pending_review"
            entry["review_note"] = "invalid superseded_by: self-replacement"
            entry["superseded_by"] = None
            continue

        matches = _match_target_metas(superseded_target, m)
        if not matches:
            entry["accepted_status"] = "pending_review"
            entry["review_note"] = f"invalid superseded_by: replacement '{superseded_target}' not found in index"
            entry["superseded_by"] = None
            continue
        if len(matches) > 1:
            entry["accepted_status"] = "pending_review"
            entry["review_note"] = f"invalid superseded_by: replacement '{superseded_target}' is ambiguous ({len(matches)} matches)"
            entry["superseded_by"] = None
            continue

        t_meta = matches[0]
        t_entry = t_meta["entry"]
        t_data = t_meta["data"]
        target_id = t_meta["run_id"]
        target_stem = t_meta["stem_no_ext"]

        # Scenario & mode consistency check (checked before cycle/status so cross-mode reports mode mismatch)
        c_name = f"{run_id or ''} {stem_no_ext or ''}".lower()
        t_name = f"{target_id or ''} {target_stem or ''}".lower()
        scens = ("wifi", "soak", "backpressure", "reconnect", "human", "power", "usb", "job")
        c_scen = next((s for s in scens if s in c_name), None)
        t_scen = next((s for s in scens if s in t_name), None)

        c_mode = (data.get("judge_input") or {}).get("mode") or data.get("soak_mode")
        t_mode = (t_data.get("judge_input") or {}).get("mode") or t_data.get("soak_mode")
        c_mode_str = str(c_mode).lower() if c_mode else ("idle" if "idle" in c_name else ("stress" if "stress" in c_name else None))
        t_mode_str = str(t_mode).lower() if t_mode else ("idle" if "idle" in t_name else ("stress" if "stress" in t_name else None))

        if c_mode_str and t_mode_str and c_mode_str != t_mode_str:
            entry["accepted_status"] = "pending_review"
            entry["review_note"] = f"invalid superseded_by: mode mismatch ({c_mode_str} vs {t_mode_str})"
            entry["superseded_by"] = None
            continue
        if (c_scen is not None and t_scen is not None and c_scen != t_scen) or ("wifi" in t_name and "wifi" not in c_name):
            entry["accepted_status"] = "pending_review"
            entry["review_note"] = f"invalid superseded_by: incompatible replacement scenario ({target_id} vs {run_id})"
            entry["superseded_by"] = None
            continue

        if idx_m in cycle_members:
            entry["accepted_status"] = "pending_review"
            entry["review_note"] = f"invalid superseded_by: cyclic replacement detected involving '{superseded_target}'"
            entry["superseded_by"] = None
            continue

        # Target status check: target MUST be an accepted 'pass' run with valid raw evidence (R6-03)
        if t_entry["accepted_status"] != "pass" or not t_meta["raw_integrity_ok"] or t_entry["original_status"] != "pass":
            entry["accepted_status"] = "pending_review"
            entry["review_note"] = (
                f"invalid superseded_by: target '{superseded_target}' is not a verified pass run "
                f"(accepted_status={t_entry['accepted_status']!r}, raw_integrity_ok={t_meta['raw_integrity_ok']})"
            )
            entry["superseded_by"] = None
            continue

        # Mandatory metadata completeness & consistency check (R7-03: missing metadata NEVER defaults to pass)
        c_dev = _extract_run_device(data, m["manifest"])
        t_dev = _extract_run_device(t_data, t_meta["manifest"])
        if not c_dev or not t_dev:
            entry["accepted_status"] = "pending_review"
            entry["review_note"] = "invalid superseded_by: missing verified device_id on superseded or replacement run"
            entry["superseded_by"] = None
            continue
        if c_dev != t_dev:
            entry["accepted_status"] = "pending_review"
            entry["review_note"] = f"invalid superseded_by: device_id mismatch ({c_dev} vs {t_dev})"
            entry["superseded_by"] = None
            continue

        c_fw = _extract_run_fw(data, m["manifest"], m["batch_info"])
        t_fw = _extract_run_fw(t_data, t_meta["manifest"], t_meta["batch_info"])
        if not entry.get("firmware_verified") or not t_entry.get("firmware_verified") or not c_fw or not t_fw:
            entry["accepted_status"] = "pending_review"
            entry["review_note"] = "invalid superseded_by: missing verified firmware chain (firmware_verified must be True on both runs)"
            entry["superseded_by"] = None
            continue
        if c_fw != t_fw:
            entry["accepted_status"] = "pending_review"
            entry["review_note"] = f"invalid superseded_by: firmware_sha256 mismatch ({c_fw[:12]} vs {t_fw[:12]})"
            entry["superseded_by"] = None
            continue

        c_tv = _extract_tool_version(data, m["manifest"])
        t_tv = _extract_tool_version(t_data, t_meta["manifest"])
        if not c_tv or not t_tv:
            entry["accepted_status"] = "pending_review"
            entry["review_note"] = "invalid superseded_by: missing tool_version on superseded or replacement run"
            entry["superseded_by"] = None
            continue
        if c_tv != t_tv:
            entry["accepted_status"] = "pending_review"
            entry["review_note"] = f"invalid superseded_by: tool_version mismatch ({c_tv} vs {t_tv})"
            entry["superseded_by"] = None
            continue

        c_struct_scen = _extract_structured_scenario(data, m["manifest"])
        t_struct_scen = _extract_structured_scenario(t_data, t_meta["manifest"])
        if not c_struct_scen or not t_struct_scen:
            entry["accepted_status"] = "pending_review"
            entry["review_note"] = "invalid superseded_by: missing structured scenario on superseded or replacement run"
            entry["superseded_by"] = None
            continue
        if c_struct_scen != t_struct_scen:
            entry["accepted_status"] = "pending_review"
            entry["review_note"] = f"invalid superseded_by: structured scenario mismatch ({c_struct_scen} vs {t_struct_scen})"
            entry["superseded_by"] = None
            continue
        if c_struct_scen == "soak":
            c_sm = _extract_structured_mode(data, m["manifest"])
            t_sm = _extract_structured_mode(t_data, t_meta["manifest"])
            if not c_sm or not t_sm or c_sm != t_sm:
                entry["accepted_status"] = "pending_review"
                entry["review_note"] = f"invalid superseded_by: missing or mismatched structured soak mode ({c_sm!r} vs {t_sm!r})"
                entry["superseded_by"] = None
                continue

        c_dur, c_dur_reason = _extract_run_duration(data)
        t_dur, t_dur_reason = _extract_run_duration(t_data)
        if c_dur is None or t_dur is None:
            why = c_dur_reason if c_dur is None else t_dur_reason
            entry["accepted_status"] = "pending_review"
            entry["review_note"] = (f"invalid superseded_by: coverage duration unverifiable "
                                    f"({why or 'missing'}) on superseded or replacement run")
            entry["superseded_by"] = None
            continue
        if t_dur < c_dur:
            entry["accepted_status"] = "pending_review"
            entry["review_note"] = f"invalid superseded_by: target duration ({t_dur}s) is shorter than superseded run ({c_dur}s)"
            entry["superseded_by"] = None
            continue

    batches = json.loads(json.dumps(batches))  # deep copy: never mutate the caller's tables

    b8 = batches.get("batch8_nops")

    if b8 is not None:

        build_out = COMPONENT / ".esphome-host" / "build" / "r60abd1-host-nops" / "build" / "firmware.factory.bin"

        if build_out.is_file():

            b8["build_output_sha256"] = sha256(build_out)

        else:

            b8["build_output_sha256"] = "unverified"

        b8["on_bench_sha256"] = "unverified"  # only a flash/verify log may set this

    b9 = batches.get("batch9_nops_deferred")

    if b9 is not None:

        b9["factory_sha256"] = "unverified"  # superseded by batch 10; full SHA in flash-log

        b9["factory_sha256_hint"] = "acb72caa"

    b10 = batches.get("batch10_ownership")

    if b10 is not None:

        build_out10 = COMPONENT / ".esphome-host" / "build" / "r60abd1-host-nops" / "build" / "firmware.factory.bin"

        b10["build_output_sha256"] = sha256(build_out10) if build_out10.is_file() else "unverified"

        b10["on_bench_sha256"] = "unverified"  # not flashed; awaiting authorization



    sources = sources_snapshot

    if sources is None:

        sources = {rel: sha256(COMPONENT / rel) for rel in SOURCE_SNAPSHOT_FILES

                   if (COMPONENT / rel).is_file()}

    ha_note = "HA-half evidence: none found"

    for root_name, root in EVIDENCE_ROOTS.items():

        ha = sorted(root.glob("g2-04-ha-half-*.jsonl"))

        if ha:

            ha_note = f"HA-half evidence found under root '{root_name}': {[p.name for p in ha]}"

            break



    index = {

        "round": "G2 hardware verification (WP-2) + 2026-10-26/27 remediation",

        "generated": date.today().isoformat(),

        "bench": {

            "board": "LuatOS ESP32-C3-CORE (ESP32-C3 rev v0.4, native USB Serial/JTAG)",

            "usb": "USB\\VID_303A&PID_1001&MI_00", "port": "COM9",

            "sta_mac": "dc:da:0c:f8:f2:74",

            "board2": "LuatOS ESP32-C3-CORE, COM3, MAC 48:31:b7:36:09:0c (F-10 cross-check)",

            "radar": "R60ABD1 @ UART1 GPIO21/GPIO20 115200",

        },

        "firmware_batches": batches,

        "current_sources_snapshot": {

            "label": "remediation-round tree - NOT a historical batch",

            "files": sources,

        },

        "evidence_roots": {name: str(path) for name, path in evidence_roots.items()},

        "ha_half_note": ha_note,

        "evidence_files": files,

        "runs": runs,

    }

    # Graph cycle detection for superseded_by
    run_by_id = {}
    for r in runs:
        rid = r.get("run_id")
        if rid:
            run_by_id[rid] = r
        rf = r.get("result_file")
        if rf:
            p_rf = Path(rf)
            run_by_id[p_rf.name] = r
            run_by_id[p_rf.stem] = r
            if p_rf.name.endswith(".result.json"):
                run_by_id[p_rf.name[:-12]] = r

    for r in runs:
        if r.get("accepted_status") == "superseded" and r.get("superseded_by"):
            visited = [r]
            curr = r
            while curr and curr.get("superseded_by"):
                nxt_target = curr["superseded_by"]
                nxt_run = run_by_id.get(nxt_target)
                if not nxt_run or nxt_run is curr:
                    break
                if nxt_run in visited:
                    for node in visited:
                        node["accepted_status"] = "pending_review"
                        node["review_note"] = f"invalid superseded_by: cyclic replacement detected ({node.get('superseded_by')})"
                        node["superseded_by"] = None
                    break
                visited.append(nxt_run)
                curr = nxt_run

    out_path.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"wrote {out_path} with {len(files)} evidence files, {len(runs)} runs")

    return index





def main() -> int:

    build_index(EVIDENCE_ROOTS, OUT, REVIEWED_RUNS, FIRMWARE_BATCHES)

    return 0





if __name__ == "__main__":

    sys.exit(main())

