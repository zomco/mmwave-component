#!/usr/bin/env python3
"""Audit that every Wi-Fi scan start shares the ownership coordinator.

The patch is only safe if one rule holds: no scan reaches a platform driver
without a reservation in `ScanOwnership`, and no completion reaches a
component listener unless the event consumed a component reservation. This
script statically checks the patched ESPHome tree for the call-site structure
that enforces it, so a new scan entry cannot quietly bypass the gate:

* `start_scanning()` and `check_roaming_()` start background scans through
  `ScanCoordinator::start_background()`; app-initiated, captive-portal, retry
  and improv scans all funnel through `start_scanning()`.
* `start_scan_for_component()` starts component scans through
  `ScanCoordinator::start_component()`.
* `notify_scan_completion_listeners_()` delivers only a `kComponent` event.
* The platform entry point `wifi_scan_start_platform_()` is called only from
  `scan_driver_start_()` and from the two `#else` branches that compile when
  the listener API is absent (no component scan exists there, so there is
  nothing to misattribute).
* Each platform implementation still contains exactly one definition and the
  underlying driver call stays inside it.

Usage:
    python scripts/check_scan_ownership_sources.py --esphome-package PATH
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

WIFI = "components/wifi"
DRIVER_ENTRY = "wifi_scan_start_platform_"
PLATFORM_FILES = (
    "wifi_component_esp_idf.cpp",
    "wifi_component_esp8266.cpp",
    "wifi_component_libretiny.cpp",
    "wifi_component_pico_w.cpp",
)
DRIVER_CALLS = {
    "wifi_component_esp_idf.cpp": "esp_wifi_scan_start(",
    "wifi_component_esp8266.cpp": "wifi_station_scan(",
    "wifi_component_libretiny.cpp": "WiFi.scanNetworks(",
    "wifi_component_pico_w.cpp": "cyw43_wifi_scan(",
}


def function_body(text: str, signature: str) -> str | None:
    """Return the brace-balanced body of the first function with signature."""
    start = text.find(signature)
    if start < 0:
        return None
    brace = text.find("{", start + len(signature))
    if brace < 0:
        return None
    depth = 0
    for index in range(brace, len(text)):
        char = text[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[brace : index + 1]
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--esphome-package",
        required=True,
        type=Path,
        help="patched esphome package directory (the one containing const.py)",
    )
    args = parser.parse_args()

    package: Path = args.esphome_package.resolve()
    wifi = package / WIFI
    if not (package / "const.py").is_file() or not wifi.is_dir():
        raise SystemExit(f"error: {package} is not an esphome package directory")

    errors: list[str] = []

    def require(condition: bool, message: str) -> None:
        if not condition:
            errors.append(message)

    component = (wifi / "wifi_component.cpp").read_text(encoding="utf-8")
    header = (wifi / "wifi_component.h").read_text(encoding="utf-8")
    ownership = (wifi / "wifi_scan_ownership.h").read_text(encoding="utf-8")
    init_py = (wifi / "__init__.py").read_text(encoding="utf-8")

    start_scanning = function_body(component, "void WiFiComponent::start_scanning()")
    roaming = function_body(component, "void WiFiComponent::check_roaming_(uint32_t now)")
    component_start = function_body(component, "bool WiFiComponent::start_scan_for_component(uint32_t *generation)")
    completion = function_body(component, "void WiFiComponent::notify_scan_completion_listeners_(uint32_t status, uint16_t number)")
    driver = function_body(component, "bool WiFiComponent::scan_driver_start_(void *self, bool passive)")

    require(start_scanning is not None, "wifi_component.cpp: start_scanning() not found")
    require(roaming is not None, "wifi_component.cpp: check_roaming_() not found")
    require(component_start is not None, "wifi_component.cpp: start_scan_for_component() not found")
    require(completion is not None, "wifi_component.cpp: notify_scan_completion_listeners_() not found")
    require(driver is not None, "wifi_component.cpp: scan_driver_start_() not found")

    if start_scanning:
        require(
            "scan_coordinator_.start_background(" in start_scanning,
            "start_scanning() does not start through scan_coordinator_.start_background()",
        )
    if roaming:
        require(
            "scan_coordinator_.start_background(" in roaming,
            "check_roaming_() does not start through scan_coordinator_.start_background()",
        )
    if component_start:
        require(
            "scan_coordinator_.start_component(" in component_start,
            "start_scan_for_component() does not start through scan_coordinator_.start_component()",
        )
    if completion:
        require(
            "scan_coordinator_.take_completion(" in completion,
            "notify_scan_completion_listeners_() does not classify events with take_completion()",
        )
        require(
            "ScanOwner::kComponent" in completion,
            "notify_scan_completion_listeners_() does not require a kComponent event",
        )
    if driver:
        require(
            f"{DRIVER_ENTRY}(" in driver,
            "scan_driver_start_() does not call the platform entry point",
        )

    entry_calls = [match.start() for match in re.finditer(rf"{DRIVER_ENTRY}\(", component)]
    require(len(entry_calls) == 3, f"wifi_component.cpp: expected 3 {DRIVER_ENTRY} calls, found {len(entry_calls)}")
    if driver:
        driver_span = (component.find(driver), component.find(driver) + len(driver))
        in_driver = sum(1 for pos in entry_calls if driver_span[0] <= pos < driver_span[1])
        require(in_driver == 1, f"the choke point must contain exactly one {DRIVER_ENTRY} call, found {in_driver}")
        fallback_calls = [pos for pos in entry_calls if not driver_span[0] <= pos < driver_span[1]]
        for pos in fallback_calls:
            window = component[max(0, pos - 240) : pos]
            require("#else" in window, f"{DRIVER_ENTRY} call at offset {pos} is not in a listener-disabled branch")
            require("#endif" in component[pos : pos + 240], f"{DRIVER_ENTRY} fallback call at offset {pos} is not closed")

    require(
        not re.search(r"\bwifi_scan_start_\(", component),
        "wifi_component.cpp: the old direct wifi_scan_start_() entry still exists",
    )

    for name, driver_call in DRIVER_CALLS.items():
        path = wifi / name
        text = path.read_text(encoding="utf-8")
        definition = function_body(text, f"bool WiFiComponent::{DRIVER_ENTRY}(bool passive)")
        require(definition is not None, f"{name}: missing the {DRIVER_ENTRY}() definition")
        require(
            text.count(f"WiFiComponent::{DRIVER_ENTRY}") == 1,
            f"{name}: expected exactly one {DRIVER_ENTRY}() definition",
        )
        if definition is not None:
            require(driver_call in definition, f"{name}: driver call {driver_call} moved out of {DRIVER_ENTRY}()")
        require(
            text.count(driver_call) == definition.count(driver_call) if definition else False,
            f"{name}: {driver_call} is called outside {DRIVER_ENTRY}()",
        )

    require(
        "ScanCoordinator scan_coordinator_" in header,
        "wifi_component.h: the component does not own a ScanCoordinator",
    )
    require(
        ownership.count("start_owned_scan(") == 3,
        "wifi_scan_ownership.h: expected the choke point definition and two callers",
    )
    require("start_owned_scan(" in ownership and "gate.owns(ticket.generation)" in ownership,
           "wifi_scan_ownership.h: component starts do not verify their reservation")
    require(
        "millis(" not in ownership and "now_ms" not in ownership,
        "wifi_scan_ownership.h: ownership must not depend on a clock",
    )

    require(
        "request_wifi_scan_completion_listener" in init_py,
        "__init__.py: missing request_wifi_scan_completion_listener()",
    )
    require(
        "USE_WIFI_SCAN_COMPLETION_LISTENERS" in init_py,
        "__init__.py: missing the listener define",
    )

    idf = (wifi / "wifi_component_esp_idf.cpp").read_text(encoding="utf-8")
    require(
        "notify_scan_completion_listeners_(it.status, it.number)" in idf,
        "wifi_component_esp_idf.cpp: SCAN_DONE does not dispatch to the ownership coordinator",
    )

    if errors:
        for message in errors:
            print(f"error: {message}", file=sys.stderr)
        return 1
    print(
        "scan ownership sources ok: 2 background entries, 1 component entry, "
        f"1 driver choke point, {len(PLATFORM_FILES)} platform implementations"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
