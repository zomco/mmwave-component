#!/usr/bin/env python3
"""Read-only HA readiness probe for the G2-04 HA half.

Reads ha_url/ha_token from the gitignored esphome-config/secrets.yaml (the
values never reach argv, stdout, or evidence files) and verifies: token
validity, the bench device's entities and their live states. Read-only -
safe to run during a soak.
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


def api(base: str, token: str, path: str):
    req = urllib.request.Request(base.rstrip("/") + path, headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        return resp.status, json.loads(resp.read().decode())


def main() -> int:
    secrets = load_secrets()
    if "ha_url" not in secrets or "ha_token" not in secrets:
        print("MISSING: ha_url/ha_token not found in esphome-config/secrets.yaml")
        return 1
    _, root = api(secrets["ha_url"], secrets["ha_token"], "/api/")
    print("token_ok:", root.get("message") == "API running.")

    _, states = api(secrets["ha_url"], secrets["ha_token"], "/api/states")
    nops = [s for s in states if "nops" in s["entity_id"].lower()]
    print(f"bench_device_entities: {len(nops)}")
    for s in sorted(nops, key=lambda x: x["entity_id"])[:16]:
        print(f"  {s['entity_id']} = {s.get('state')}")
    mounts = [s["entity_id"] for s in states if "mount" in s["entity_id"].lower()]
    print("mount_entities:", mounts)
    return 0


if __name__ == "__main__":
    sys.exit(main())
