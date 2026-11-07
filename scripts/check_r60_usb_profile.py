#!/usr/bin/env python3
"""Check that the R60ABD1 candidate owns USB and other models keep Improv.

Text-level on purpose: it runs in CI before the firmware matrix. The
expanded config and the compiled sdkconfig are checked by
scripts/build_r60_candidate.py. ``--self-test`` proves the failure path
without touching the tree.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def key_present(text, key):
    return any(line.split("#", 1)[0].strip() == key for line in text.splitlines())


def candidate_errors(base, factory, mwcp):
    errors = []
    required = (
        "components: [r60abd1, mmwave_host]",
        "CONFIG_ESP_CONSOLE_NONE: y",
        "CONFIG_ESP_CONSOLE_USB_SERIAL_JTAG: n",
        "CONFIG_ESP_MAIN_TASK_STACK_SIZE: \"8192\"",
        "baud_rate: 0",
        "hardware_uart: UART0",
        "reboot_timeout: 0s",
        "captive_portal:",
        "common/r60abd1_mwcp.yaml",
        "build_profile: r60-daily",
        "release_channel: development",
    )
    for item in required:
        if item not in base:
            errors.append(f"base is missing {item}")
    if base.count("reboot_timeout: 0s") < 2:
        errors.append("base must disable both API and Wi-Fi reboot loops")
    if key_present(base, "improv_serial:") or key_present(factory, "improv_serial:"):
        errors.append("R60 candidate still declares improv_serial")
    if "hardware_uart: USB_SERIAL_JTAG" in base or "networks:" in base:
        errors.append("base moves logs to USB or pins a Wi-Fi network")
    for item in ("esp32_improv:", "platform: http_request", "dashboard_import:", "r60abd1-esp32c3.yaml"):
        if item not in factory:
            errors.append(f"factory is missing {item}")
    if "version: dev" not in factory:
        errors.append("factory must keep the version: dev placeholder for the publisher")
    if "release_channel: dev" not in factory:
        errors.append("factory must keep the release_channel: dev placeholder for the publisher")
    if "_device.yaml" not in mwcp or "_areas_host.yaml" not in mwcp:
        errors.append("MWCP core must include diagnostics and host-bound areas")
    if "_standard_device.yaml" in mwcp or key_present(mwcp, "improv_serial:"):
        errors.append("MWCP core pulls serial Improv back in")
    return errors


def tree_errors():
    errors = []
    base = (ROOT / "tests/r60abd1-esp32c3.yaml").read_text(encoding="utf-8")
    factory = (ROOT / "tests/r60abd1-esp32c3.factory.yaml").read_text(encoding="utf-8")
    mwcp = (ROOT / "tests/common/r60abd1_mwcp.yaml").read_text(encoding="utf-8")
    errors.extend(candidate_errors(base, factory, mwcp))
    standard = (ROOT / "tests/common/_standard_device.yaml").read_text(encoding="utf-8")
    if "_device.yaml" not in standard or "_improv_serial.yaml" not in standard:
        errors.append("ordinary device package must compose diagnostics and serial Improv")
    device = (ROOT / "tests/common/_device.yaml").read_text(encoding="utf-8")
    if key_present(device, "improv_serial:"):
        errors.append("_device.yaml must not itself declare improv_serial")
    for name in ("ld2450.yaml", "r60abd1.yaml"):
        text = (ROOT / "tests/common" / name).read_text(encoding="utf-8")
        if "_standard_device.yaml" not in text:
            errors.append(f"{name} lost serial Improv")
    return errors


def self_test():
    good = """
components: [r60abd1, mmwave_host]
CONFIG_ESP_CONSOLE_NONE: y
CONFIG_ESP_CONSOLE_USB_SERIAL_JTAG: n
CONFIG_ESP_MAIN_TASK_STACK_SIZE: "8192"
baud_rate: 0
hardware_uart: UART0
api:
  reboot_timeout: 0s
wifi:
  reboot_timeout: 0s
captive_portal:
common/r60abd1_mwcp.yaml
build_profile: r60-daily
release_channel: development
"""
    factory = """
core: !include r60abd1-esp32c3.yaml
version: dev
release_channel: dev
dashboard_import:
esp32_improv:
ota:
  - platform: http_request
# mentions improv_serial in a comment only
"""
    mwcp = "packages:\n  device: !include _device.yaml\n  areas: !include _areas_host.yaml\n"
    if candidate_errors(good, factory, mwcp):
        raise SystemExit("self-test: the good sample was rejected")
    bad = good + "\nimprov_serial:\n"
    if not candidate_errors(bad, factory, mwcp):
        raise SystemExit("self-test: a candidate with serial Improv was accepted")
    print("self-test ok")


def main():
    self_test()
    if "--self-test" in sys.argv:
        return 0
    errors = tree_errors()
    if errors:
        for error in errors:
            print(f"error: {error}", file=sys.stderr)
        return 1
    print("r60 usb profile ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
