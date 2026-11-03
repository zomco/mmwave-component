#!/usr/bin/env python3
"""Apply the pinned Wi-Fi scan-ownership patch to an installed ESPHome.

`components/mmwave_host` starts Wi-Fi scans for the `wifi.scan` job only when
the WiFi component can prove which scan a completion belongs to. Stock ESPHome
offers no such API: `start_scanning()` returns nothing, scan completions carry
no request identity, and failures are indistinguishable from "someone else's
scan finished". The patch in `patches/esphome-2026.9.1-wifi-scan-ownership.patch`
adds `WiFiComponent::start_scan_for_component()` plus a
`WiFiScanCompletionListener`, and is pinned to ESPHome 2026.9.1.

This script refuses to touch anything but an unmodified 2026.9.1 tree: it
verifies the exact version and the SHA-256 of every file in the patch before
handing the patch to `git apply`. That keeps the promise that host builds run
on a stock release plus exactly one reviewed patch.

Usage:
    python scripts/apply_esphome_patch.py --esphome-package path/to/site-packages/esphome
    python scripts/apply_esphome_patch.py --esphome-package path/to/site-packages/esphome --check

`--check` verifies that the patch applies to the pristine tree and exits
without modifying it; CI uses it to prove the patch stays valid for the pinned
release. Applying twice is not an error: an already-patched tree is recognized
by its post-image hashes and reported as such.
"""

from __future__ import annotations

import argparse
import hashlib
import re
import subprocess
import sys
import tempfile
from pathlib import Path

PINNED_VERSION = "2026.9.1"
PATCH_PATH = Path(__file__).resolve().parents[1] / "patches" / f"esphome-{PINNED_VERSION}-wifi-scan-ownership.patch"
WIFI_DIR = "components/wifi"

# SHA-256 of the modified files in an unmodified esphome 2026.9.1 release.
# The platform files change only because the driver entry point is renamed to
# wifi_scan_start_platform_(), making the ownership choke point auditable.
PRISTINE_SHA256 = {
    f"{WIFI_DIR}/wifi_component.h": "a6e3273e16d461e73d954b20b2c780fe1f903feee567582c03486c55e532c969",
    f"{WIFI_DIR}/wifi_component.cpp": "eb702ee952d594372011a3371c41ba37aa44eccecff0d3b687f23d64303ce6ce",
    f"{WIFI_DIR}/wifi_component_esp_idf.cpp": "c6980e4ab5cccf46ab07ead1b8dbd830f21f35fa09a62779fed009dff1aa1433",
    f"{WIFI_DIR}/wifi_component_esp8266.cpp": "29e66662a9cd8c3725febb125f1bbf4bc386d3ee63153bc5076252bc8e1d2b6b",
    f"{WIFI_DIR}/wifi_component_libretiny.cpp": "76927ea50576025a75e65ddcc77fa453a031b5de187962228afaee451b70fabf",
    f"{WIFI_DIR}/wifi_component_pico_w.cpp": "a6c06a0e20d6fbb7bab752e342ae9b5326776035bfea7ad9ad2597b716872a9d",
    f"{WIFI_DIR}/__init__.py": "b730f2bd42696461159b3fa152cc031b1486875bbaf539dbaca920232b4884ee",
}

# SHA-256 of the same files after the patch, used to recognize an already
# patched tree instead of failing on the second run.
PATCHED_SHA256 = {
    f"{WIFI_DIR}/wifi_component.h": "f2621afaec6fc4cf59ca2d8e9e4f17003acf126b370e67e80b13cf3b41f0e5be",
    f"{WIFI_DIR}/wifi_component.cpp": "98d472a47edeb87445eb1b9f312f87ce3dd2ba52166c707d41c6f7b93f11e19f",
    f"{WIFI_DIR}/wifi_component_esp_idf.cpp": "8d1c926e09d1227050097099d019f88612e334c2a2c270bec1c9e8df4c6bc456",
    f"{WIFI_DIR}/wifi_component_esp8266.cpp": "5931a263f0b9603986d2745373ed34492bfbad6d9cc9e2b359df4b75540e2474",
    f"{WIFI_DIR}/wifi_component_libretiny.cpp": "fce80001fc7c9e3ab145e6d23378c8545a786835515e820b1f6e6723137a7edc",
    f"{WIFI_DIR}/wifi_component_pico_w.cpp": "1957fc6e4b67c7ce0b324f2ad6bcf4e147a0e5b43b42446d44d75216786391c5",
    f"{WIFI_DIR}/__init__.py": "0b9fd7add2a221de9587cf19fdf6656683d9c5f03684aa3dbf216e173b7aeb7f",
}

# Files the patch adds. They exist only in a patched tree and are what the
# host-side ownership tests extract and compile.
PATCHED_ADDED_SHA256 = {
    f"{WIFI_DIR}/wifi_scan_ownership.h": "6b028c2477444b81e216f97aeafffa6de7e7154666ec3e9d1365ad8d78de9a3d",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_version(package: Path) -> str:
    const_py = package / "const.py"
    match = re.search(r'^__version__ = "([^"]+)"', const_py.read_text(encoding="utf-8"), re.MULTILINE)
    if match is None:
        raise SystemExit(f"error: cannot read __version__ from {const_py}")
    return match.group(1)


def classify(package: Path) -> str:
    """Return 'pristine', 'patched', or fail with a per-file report."""
    pristine = 0
    patched = 0
    lines = []
    for rel, expected in PRISTINE_SHA256.items():
        path = package / rel
        if not path.is_file():
            lines.append(f"  missing: {rel}")
            continue
        actual = sha256(path)
        if actual == expected:
            pristine += 1
        elif actual == PATCHED_SHA256[rel]:
            patched += 1
        else:
            lines.append(f"  modified: {rel} (sha256 {actual})")
    added_present = True
    added_wrong = False
    for rel, expected in PATCHED_ADDED_SHA256.items():
        path = package / rel
        if not path.is_file():
            added_present = False
            continue
        actual = sha256(path)
        if actual != expected:
            added_wrong = True
            lines.append(f"  modified: {rel} (sha256 {actual})")
    total = len(PRISTINE_SHA256)
    if pristine == total and not added_present and not added_wrong:
        return "pristine"
    if patched == total and added_present and not added_wrong:
        return "patched"
    if patched == total and not added_present:
        lines.append(f"  missing: {', '.join(PATCHED_ADDED_SHA256)}")
    detail = "\n".join(lines) if lines else "  (unknown mix of pristine and patched files)"
    raise SystemExit(
        "error: esphome tree does not match the pinned release in either pristine or patched form:\n"
        f"{detail}\n"
        "Reinstall the pinned release with `pip install esphome==2026.9.1` and retry."
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--esphome-package",
        required=True,
        type=Path,
        help="path to the installed 'esphome' package directory (the one containing const.py)",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify the patch applies to the pristine tree without modifying it",
    )
    args = parser.parse_args()

    package: Path = args.esphome_package.resolve()
    if not (package / "const.py").is_file():
        raise SystemExit(f"error: {package} is not an esphome package directory (no const.py)")
    if not PATCH_PATH.is_file():
        raise SystemExit(f"error: patch not found: {PATCH_PATH}")

    version = read_version(package)
    if version != PINNED_VERSION:
        raise SystemExit(
            f"error: esphome {version} is installed, but this patch is pinned to {PINNED_VERSION}.\n"
            "The patch edits internal wifi sources and must be revalidated before use on another release."
        )

    state = classify(package)
    if state == "patched":
        print(f"already patched: esphome {version} at {package}")
        return 0

    # -c core.autocrlf=false keeps the applied bytes identical to the patch on
    # every OS; otherwise a Windows checkout with autocrlf=true would rewrite
    # line endings and the post-image hashes below would (correctly) refuse it.
    #
    # GIT_DIR points at an empty temporary directory so repository discovery
    # cannot escape into an enclosing checkout. A local virtualenv lives inside
    # this repository and is gitignored, and git apply silently skips every
    # hunk whose path is ignored. An isolated GIT_DIR applies the same bytes
    # in place, which is also what CI does with a system-wide install.
    with tempfile.TemporaryDirectory() as git_dir:
        command = [
            "git",
            "--git-dir",
            git_dir,
            "-c",
            "core.autocrlf=false",
            "apply",
            "-p1",
            *(["--check"] if args.check else []),
            str(PATCH_PATH),
        ]
        result = subprocess.run(command, cwd=package.parent, capture_output=True, text=True)
    if result.returncode != 0:
        raise SystemExit(f"error: {' '.join(command)}\n{result.stderr.strip()}")
    if result.stderr.strip():
        raise SystemExit(f"error: {' '.join(command)}\n{result.stderr.strip()}")
    if args.check:
        print(f"patch applies cleanly: {PATCH_PATH.name} -> esphome {version} at {package}")
        return 0

    mismatched = [rel for rel, expected in {**PATCHED_SHA256, **PATCHED_ADDED_SHA256}.items()
                  if sha256(package / rel) != expected]
    if mismatched:
        raise SystemExit(f"error: patched tree does not match the pinned post-image: {', '.join(mismatched)}")
    print(f"patched esphome {version} at {package}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
