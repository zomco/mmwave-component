#!/usr/bin/env python3
"""Build the host-enabled firmware on pinned ESPHome, patched or stock.

The patched mode proves the real delivery path: it applies the reviewed
Wi-Fi scan-ownership patch to esphome 2026.9.1, compiles
``tests/r60abd1-esp32c3-host.yaml``, and asserts that the expected compile
defines reached the generated ``defines.h``. Stock mode proves the fallback:
the same configuration compiles without the patch and without the ownership
defines, so ``wifi.scan`` reports UNSUPPORTED instead of guessing.

Usage:
    python scripts/build_host_profile.py --mode patched
    python scripts/build_host_profile.py --mode stock

Use ``--venv PATH`` to create and populate an isolated environment with the
pinned ESPHome. Without it, the current interpreter must already have esphome
2026.9.1 installed.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import subprocess
import sys
from pathlib import Path

from apply_esphome_patch import PINNED_VERSION, classify, read_version

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_YAML = ROOT / "tests" / "r60abd1-esp32c3-host.yaml"
HOST_DEFINES = ("MWCP_WIFI_SCAN_OWNERSHIP", "USE_WIFI_SCAN_COMPLETION_LISTENERS")
SHARED_DEFINES = ("USE_WIFI_RUNTIME_ROAMING_SUPPRESSION",)


def venv_python(venv: Path) -> Path:
    return venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def ensure_venv(venv: Path) -> Path:
    python = venv_python(venv)
    if not python.exists():
        print(f"creating {venv}")
        subprocess.check_call([sys.executable, "-m", "venv", str(venv)])
        subprocess.check_call([str(python), "-m", "pip", "install", "--quiet", f"esphome=={PINNED_VERSION}"])
    return python


def esphome_package(python: Path) -> Path:
    code = "import esphome, os; print(os.path.dirname(esphome.__file__))"
    return Path(subprocess.check_output([str(python), "-c", code], text=True).strip())


def find_defines(data_dir: Path) -> Path:
    candidates = sorted(
        data_dir.glob("build/*/src/esphome/core/defines.h"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    if not candidates:
        raise SystemExit(f"error: no generated defines.h under {data_dir}")
    return candidates[0]


def assert_defines(defines: Path, present: tuple[str, ...], absent: tuple[str, ...] = ()) -> None:
    text = defines.read_text(encoding="utf-8")
    for macro in present:
        if not re.search(rf"^#define {macro}(?:\s|$)", text, re.MULTILINE):
            raise SystemExit(f"error: {defines} is missing '#define {macro}'")
    for macro in absent:
        if re.search(rf"^#define {macro}(?:\s|$)", text, re.MULTILINE):
            raise SystemExit(f"error: {defines} unexpectedly defines {macro}")
    print(f"defines ok: {defines}")
    for macro in present:
        print(f"  wants #define {macro}")


def firmware_hashes(data_dir: Path) -> None:
    bins = sorted(data_dir.glob("build/*/build/*.bin"))
    if not bins:
        raise SystemExit(f"error: no firmware binaries under {data_dir}")
    for path in bins:
        print(f"firmware {path.name} sha256={hashlib.sha256(path.read_bytes()).hexdigest()}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--mode", choices=("patched", "stock"), required=True)
    parser.add_argument("--yaml", type=Path, default=DEFAULT_YAML)
    parser.add_argument("--data-dir", type=Path, default=ROOT / ".esphome-host")
    parser.add_argument("--venv", type=Path)
    parser.add_argument("--skip-compile", action="store_true")
    args = parser.parse_args()

    yaml = args.yaml.resolve()
    if not yaml.is_file():
        raise SystemExit(f"error: config not found: {yaml}")
    data_dir = args.data_dir.resolve()
    data_dir.mkdir(parents=True, exist_ok=True)

    python = ensure_venv(args.venv.resolve()) if args.venv else Path(sys.executable)
    package = esphome_package(python)
    version = read_version(package)
    if version != PINNED_VERSION:
        raise SystemExit(f"error: esphome at {package} is {version}, expected {PINNED_VERSION}")

    state = classify(package)
    if args.mode == "patched":
        subprocess.check_call(
            [str(python), str(ROOT / "scripts" / "apply_esphome_patch.py"), "--esphome-package", str(package)]
        )
    elif state != "pristine":
        raise SystemExit("error: stock mode needs a pristine esphome install; use a fresh --venv or data dir")

    if not args.skip_compile:
        env = dict(os.environ)
        env["ESPHOME_DATA_DIR"] = str(data_dir)
        # ESP-IDF's idf.py prints a warning and exits 0 without building when
        # MSYSTEM is set, so a Git Bash parent would silently produce no
        # firmware. The native ESP-IDF toolchain must run outside MSYS.
        env.pop("MSYSTEM", None)
        subprocess.check_call([str(python), "-m", "esphome", "compile", str(yaml)], cwd=ROOT, env=env)

    if args.skip_compile:
        print(f"{args.mode} setup ok")
        return 0
    defines = find_defines(data_dir)
    if args.mode == "patched":
        assert_defines(defines, HOST_DEFINES + SHARED_DEFINES)
    else:
        assert_defines(defines, SHARED_DEFINES, HOST_DEFINES)
    firmware_hashes(data_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
