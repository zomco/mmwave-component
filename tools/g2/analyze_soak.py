#!/usr/bin/env python3
"""Summarize a soak result JSON or a raw evidence JSONL for the G2 report.

    python tools/g2/analyze_soak.py <soak.result.json|soak.jsonl>

The JSONL mode is authoritative when the result JSON was produced by an older
runner that crashed while summarizing all-timeout samples: it pairs PING
requests with responses by request_id and counts STATUS_GET, events and boots
directly from the captured wire timeline.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def pct(values: list[float], p: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[min(int(len(ordered) * p), len(ordered) - 1)]


def summarize_result(data: dict) -> dict:
    samples = data.get("samples", [])
    rtts = [s["rtt_ms"] for s in samples if s.get("rtt_ms") is not None]
    gaps = [s for s in samples if s.get("rtt_ms") is None]
    boots = sorted({s.get("boot_id") for s in samples if s.get("boot_id")})
    first = next((s.get("counters") for s in samples if s.get("counters")), None)
    last = next((s.get("counters") for s in reversed(samples) if s.get("counters")), None)
    return {
        "file": str(data.get("_path", "")),
        "run_id": data.get("run_id"),
        "status": data.get("status"),
        "wall_span_s": (samples[-1]["t"] - samples[0]["t"]) if len(samples) > 1 else 0,
        "samples_total": len(samples),
        "samples_with_ping_and_status": len(rtts),
        "samples_gaps": len(gaps),
        "sample_rtt_ms": {
            "min": min(rtts) if rtts else None,
            "p50": pct(rtts, 0.50),
            "p95": pct(rtts, 0.95),
            "max": max(rtts) if rtts else None,
            "over_250ms": sum(1 for r in rtts if r > 250),
            "over_500ms": sum(1 for r in rtts if r > 500),
            "over_5s": sum(1 for r in rtts if r > 5000),
        },
        "boot_ids_seen": boots,
        "boot_changes": len(boots) - 1 if boots else 0,
        "counters_first": first,
        "counters_last": last,
        "uptime_first_ms": next((s.get("uptime_ms") for s in samples if s.get("uptime_ms") is not None), None),
        "uptime_last_ms": next((s.get("uptime_ms") for s in reversed(samples) if s.get("uptime_ms") is not None), None),
        "checks": [{"name": c["name"], "pass": c["pass"]} for c in data.get("checks", [])],
        "notes": data.get("notes", []),
    }


def summarize_jsonl(path: Path) -> dict:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    pending: dict[int, float] = {}
    rtts: list[float] = []
    pings = status_tx = status_rx = events = hellos = 0
    boots: set[str] = set()
    for row in rows:
        direction = row.get("dir")
        code = row.get("code")
        if direction == "tx" and row.get("kind") == 1 and code == 2:
            pings += 1
            pending[row["request_id"]] = row["t"]
        elif direction == "rx" and row.get("kind") == 2 and code == 2:
            started = pending.pop(row.get("request_id"), None)
            if started is not None:
                rtts.append(round((row["t"] - started) * 1000, 1))
        elif code == 18 and direction in ("tx", "rx"):
            if direction == "tx":
                status_tx += 1
            else:
                status_rx += 1
        elif code == 1 and direction == "rx":
            hellos += 1
            result = (row.get("payload") or {}).get("result") or {}
            if result.get("boot_id"):
                boots.add(result["boot_id"])
        if row.get("kind") == 3:
            events += 1
    rtts.sort()
    span = (rows[-1]["t"] - rows[0]["t"]) if len(rows) > 1 else 0
    return {
        "file": str(path),
        "rows": len(rows),
        "wall_span_s": round(span, 1),
        "hello_responses": hellos,
        "pings_sent": pings,
        "pings_answered": len(rtts),
        "pings_unanswered": len(pending),
        "ping_rtt_ms": {
            "min": rtts[0] if rtts else None,
            "p50": pct(rtts, 0.50),
            "p95": pct(rtts, 0.95),
            "max": rtts[-1] if rtts else None,
            "over_250ms": sum(1 for r in rtts if r > 250),
            "over_500ms": sum(1 for r in rtts if r > 500),
            "over_5s": sum(1 for r in rtts if r > 5000),
        },
        "status_get": {"sent": status_tx, "answered": status_rx},
        "events": events,
        "boot_ids_seen": sorted(boots),
    }


def main() -> int:
    path = Path(sys.argv[1])
    if path.suffix == ".jsonl":
        summary = summarize_jsonl(path)
    else:
        data = json.loads(path.read_text(encoding="utf-8"))
        data["_path"] = str(path)
        summary = summarize_result(data)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
