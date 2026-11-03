"""One short read-only check: HELLO, read, wait past the TTL, HELLO, read.

The wait does not PING, so the first session expires. Recovery is a new
HELLO on the same open port. This script never resets the chip and never
sends a write. If the named port is not the expected board, it records
not_run and does not open anything.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import mwcp

EXPECTED_DEVICE = "dcda0cf8f274"
EXPECTED_SERIAL = "DC:DA:0C:F8:F2:74"
TTL_WAIT_S = 16.0


def port_identity(port: str) -> dict | None:
    from serial.tools import list_ports

    for item in list_ports.comports():
        if item.device.upper() != port.upper():
            continue
        return {
            "device": item.device,
            "serial_number": item.serial_number or "",
            "hwid": item.hwid or "",
            "description": item.description or "",
        }
    return None


def acceptable(info: dict | None) -> bool:
    if not info:
        return False
    blob = " ".join([info["serial_number"], info["hwid"], info["description"]]).upper()
    return EXPECTED_SERIAL in blob


def install_view(payload: dict) -> dict:
    """First CONFIG_READ page only. A cursor from the old session is not reused."""
    result = payload.get("result") if isinstance(payload, dict) else None
    if not isinstance(result, dict):
        return {"revision": None, "items": []}
    items = []
    for item in result.get("items") or []:
        if not isinstance(item, dict):
            continue
        key = item.get("key")
        value = item.get("value")
        if isinstance(key, str) and key.startswith("install.") and isinstance(value, (int, float, str)):
            items.append([key, value])
    return {"revision": result.get("revision"), "items": items}


def run(port: str, out: Path) -> int:
    out.parent.mkdir(parents=True, exist_ok=True)
    info = port_identity(port)
    if port.upper() == "COM3" or not acceptable(info):
        record = {
            "status": "not_run",
            "reason": "port is not the expected board" if info else "port is not present",
            "port": port,
            "identity": info,
            "reset": False,
        }
        out.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"status": "not_run"}))
        return 0
    evidence = mwcp.EvidenceWriter(out.with_suffix(".jsonl"), mwcp.Redactor())
    client = mwcp.Client(port, evidence, allow_write=False, allow_provision=False)
    record: dict = {"status": "fail", "port": port, "reset": False, "writes": 0}
    try:
        first = client.hello(timeout_ms=8000, client_name="session-keepalive-probe")
        if client.device_id != EXPECTED_DEVICE:
            record["status"] = "not_run"
            record["reason"] = "hello device_id did not match"
            record["device_id"] = client.device_id
            return 0
        boot_1 = client.boot_id
        session_1 = client.session_id
        read_1 = client.call("CONFIG_READ", {})
        view_1 = install_view(read_1)
        time.sleep(TTL_WAIT_S)
        second = client.hello(timeout_ms=8000, client_name="session-keepalive-probe")
        boot_2 = client.boot_id
        session_2 = client.session_id
        read_2 = client.call("CONFIG_READ", {})
        view_2 = install_view(read_2)
        same_boot = boot_1 == boot_2 and bool(boot_1)
        same_config = view_1 == view_2
        new_session = session_2 != session_1 and session_2 not in (None, 0)
        ok = (same_boot and same_config and new_session and client.device_id == EXPECTED_DEVICE
              and view_1.get("revision") is not None)
        record.update({
            "status": "pass" if ok else "fail",
            "device_id": client.device_id,
            "boot_id_1": boot_1,
            "boot_id_2": boot_2,
            "session_1": session_1,
            "session_2": session_2,
            "config_1": view_1,
            "config_2": view_2,
            "same_boot": same_boot,
            "same_config": same_config,
            "wait_s": TTL_WAIT_S,
            "hello_ttl_1": first.get("session_ttl_ms") if isinstance(first, dict) else None,
            "hello_ttl_2": second.get("session_ttl_ms") if isinstance(second, dict) else None,
        })
        return 0 if ok else 1
    except Exception as ex:
        record["error"] = type(ex).__name__
        return 1
    finally:
        client.close()
        evidence.close()
        out.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"status": record["status"], "reset": False}))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    raise SystemExit(run(args.port, Path(args.out)))


if __name__ == "__main__":
    main()
