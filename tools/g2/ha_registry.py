#!/usr/bin/env python3
"""Read-only HA entity-registry lookup for the G2-04 HA half.

Checks whether the bench device's Mount numbers are registered (they may
lack a state until first publish, which hides them from /api/states).
Secrets handling identical to ha_probe.py.
"""

import json
import re
import sys
import urllib.request
from pathlib import Path

SECRETS = Path(__file__).resolve().parents[4] / "esphome-config" / "secrets.yaml"


def load_secrets() -> dict:
    values = {}
    for line in SECRETS.read_text(encoding="utf-8").splitlines():
        match = re.match(r"^(ha_url|ha_token):\s*[\"'](.+?)[\"']\s*$", line)
        if match:
            values[match.group(1)] = match.group(2)
    return values


def api(base: str, token: str, path: str, method: str = "GET"):
    req = urllib.request.Request(base.rstrip("/") + path, headers={"Authorization": f"Bearer {token}"}, method=method)
    with urllib.request.urlopen(req, timeout=10) as resp:
        body = resp.read().decode()
        return resp.status, json.loads(body) if body else None


def main() -> int:
    secrets = load_secrets()
    base, token = secrets["ha_url"], secrets["ha_token"]
    try:
        _, entries = api(base, token, "/api/config/entity_registry/list")
    except urllib.error.HTTPError as e:
        print("registry_list_unavailable:", e.code)
        return 1
    nops = [e for e in entries if "nops" in e.get("entity_id", "").lower()]
    print(f"registered_bench_entities: {len(nops)}")
    for e in sorted(nops, key=lambda x: x["entity_id"]):
        print(f"  {e['entity_id']}  unique_id={e.get('unique_id', '')[:40]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
