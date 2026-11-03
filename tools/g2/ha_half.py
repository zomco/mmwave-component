#!/usr/bin/env python3
"""G2-04 HA-half external write entry chain (round 5).

Chain: HA REST writes Mount X -> device submit_number() -> MWCP config
revision changes -> USB CONFIG_READ reads the value back -> USB writes a
new value -> HA entity state follows. Secrets read from the gitignored
esphome-config/secrets.yaml; evidence records only ha_url and redacted
tokens.
"""

import json
import re
import sys
import time
import urllib.request
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import mwcp  # noqa: E402

SECRETS = Path(__file__).resolve().parents[4] / "esphome-config" / "secrets.yaml"
EVIDENCE = Path(__file__).resolve().parents[2] / "tmp" / "mwcp-g2" / "evidence"
HA_ENTITY = "number.r60abd1_test_device_mount_x"  # legacy test-device entity name
IP = "192.168.5.236"


def load_secrets() -> dict:
    values = {}
    for line in SECRETS.read_text(encoding="utf-8").splitlines():
        match = re.match(r"^(ha_url|ha_token):\s*[\"'](.+?)[\"']\s*$", line)
        if match:
            values[match.group(1)] = match.group(2)
    return values


def secrets_for_redaction(values: dict) -> list[str]:
    return [v for k, v in values.items() if k == "ha_token" and v]


def api(base: str, token: str, path: str, method: str = "GET", body: dict | None = None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(base.rstrip("/") + path, headers={"Authorization": f"Bearer {token}",
                                                                  "Content-Type": "application/json"},
                                 method=method, data=data)
    with urllib.request.urlopen(req, timeout=15) as resp:
        text = resp.read().decode()
        return resp.status, json.loads(text) if text else None


def web_number(name: str = "Mount%20X") -> float:
    with urllib.request.urlopen(f"http://{IP}/number/{name}", timeout=10) as resp:
        return float(json.loads(resp.read())["value"])


def main() -> int:
    secrets = load_secrets()
    base, token = secrets["ha_url"], secrets["ha_token"]
    stamp = time.strftime("%Y%m%d-%H%M%S")
    ev = mwcp.EvidenceWriter(EVIDENCE / f"g2-04-ha-half-{stamp}.jsonl",
                             mwcp.Redactor(secrets=secrets_for_redaction(secrets)))
    red = mwcp.Redactor()
    checks: list[tuple[bool, str, str]] = []

    def check(name: str, ok: bool, detail: str):
        checks.append((ok, name, detail))
        ev.note({"dir": "note", "event": name, "ok": ok, "detail": str(detail)[:200]})

    def ha_state(entity: str):
        _, states = api(base, token, "/api/states")
        found = [s for s in states if s["entity_id"] == entity]
        return found[0] if found else None

    def ha_set(entity: str, value: float):
        status, resp = api(base, token, "/api/services/number/set_value", "POST",
                           {"entity_id": entity, "value": value})
        return status == 200 or status == 201, status

    ev.note({"dir": "note", "event": "session_start", "ha_url": base,
             "ha_entity": HA_ENTITY, "device_ip": IP})

    import subprocess
    py = sys.executable
    holder = {"client": None}

    def reset_device():
        subprocess.run([py, "-m", "esptool", "--port", "COM9", "run"], capture_output=True, timeout=45)
        time.sleep(8)

    def open_client():
        holder["client"] = mwcp.Client("COM9", ev, allow_write=True)
        holder["client"].hello(timeout_ms=8000)

    def usb_call(name, payload=None, **kw):
        """USB RPC with the bench-standard wedge recovery: on timeout,
        esptool-reset the device and retry the same request on a fresh
        session (the protocol's replay cache makes this safe)."""
        for attempt in range(3):
            try:
                if holder["client"] is None:
                    open_client()
                return holder["client"].call(name, payload, **kw)
            except (TimeoutError, Exception) as error:  # noqa: BLE001
                # Non-timeout errors and a final attempt always propagate:
                # recovery is only for the recorded timeout pattern, and a
                # retried request keeps its payload (same op_id inside).
                if attempt == 2 or "no response" not in str(error):
                    raise
                ev.note({"dir": "note", "event": "usb_wedge_recover", "request": name,
                         "attempt": attempt})
                try:
                    holder["client"].close()
                except Exception:  # noqa: BLE001
                    pass
                holder["client"] = None
                reset_device()

    # baseline
    _, states = api(base, token, "/api/states")
    st0 = ha_state(HA_ENTITY)
    check("ha_token_and_entity_live", st0 is not None, f"state={st0.get('state') if st0 else None}")
    ha0 = float(st0["state"])
    web0 = web_number()
    check("ha_matches_web_baseline", ha0 == web0, f"ha={ha0} web={web0}")

    try:
        rev0 = usb_call("STATUS_GET")["result"]["config_revision"]
        check("usb_session_ok", True, f"rev={rev0}")

        # 1. HA writes a NEW value (odd number, not used elsewhere)
        new1 = 155.0
        ok, status = ha_set(HA_ENTITY, new1)
        check("ha_set_155_accepted", ok and status in (200, 201), f"status={status}")
        time.sleep(3.0)
        st1 = ha_state(HA_ENTITY)
        web1 = web_number()
        check("ha_state_follows_write", abs(float(st1["state"]) - new1) < 0.01,
              f"ha={st1['state']} (target {new1})")
        check("web_view_follows_ha_write", abs(web1 - new1) < 0.01, f"web={web1}")

        # 2. USB reads the HA-written value back through MWCP
        cursor, values, rev1 = None, {}, None
        while True:
            r = usb_call("CONFIG_READ", {"cursor": cursor})
            res = r["result"]
            rev1 = res.get("revision")
            for item in res.get("items", []):
                values[item["key"]] = item["value"]
            cursor = res.get("next_cursor")
            if cursor is None:
                break
        check("usb_reads_ha_written_value", float(values.get("install.x_cm", -1)) == new1,
              f"x={values.get('install.x_cm')} rev {rev0}->{rev1}")

        # 3. USB writes a new value; HA entity must follow
        new2 = 140.0
        c = usb_call("CONFIG_COMMIT", {"base_revision": rev1, "op_id": str(uuid.uuid4()),
                                       "changes": {"install.x_cm": new2}}, timeout_ms=15000)
        check("usb_commit_accepted", c.get("ok") is True and c.get("result", {}).get("persisted") is True,
              f"rev->{c.get('result', {}).get('revision')}")
        # The template number re-evaluates its lambda (radar calibration) on
        # the default 60 s update cycle; the USB commit path does not push an
        # explicit publish, so poll until HA and the device web view converge.
        ha2 = web2 = None
        deadline = time.time() + 80
        while time.time() < deadline:
            time.sleep(5.0)
            ha2 = float(ha_state(HA_ENTITY)["state"])
            web2 = web_number()
            if abs(ha2 - new2) < 0.01 and abs(web2 - new2) < 0.01:
                break
        check("ha_state_follows_usb_commit", ha2 is not None and abs(ha2 - new2) < 0.01,
              f"ha={ha2} (target {new2}, 60s template cycle)")
        check("web_view_follows_usb_commit", web2 is not None and abs(web2 - new2) < 0.01, f"web={web2}")

        # restore baseline (web writes are the ordinary user path)
        ok, _ = ha_set(HA_ENTITY, ha0)
        time.sleep(3.0)
        st3 = ha_state(HA_ENTITY)
        check("restore_baseline", abs(float(st3["state"]) - ha0) < 0.01, f"ha={st3['state']}")

        usb_call("SESSION_CLOSE")
    finally:
        if holder["client"] is not None:
            try:
                holder["client"].close()
            except Exception:  # noqa: BLE001
                pass
        summary = ev.close()

    passed = sum(1 for ok, _, _ in checks if ok)
    print(f"HA-half: {passed}/{len(checks)} checks pass")
    for ok, name, detail in checks:
        print(f"  [{'PASS' if ok else 'FAIL'}] {name} :: {detail}")
    print(f"evidence: {summary.get('file')}")
    return 0 if passed == len(checks) else 1


if __name__ == "__main__":
    sys.exit(main())
