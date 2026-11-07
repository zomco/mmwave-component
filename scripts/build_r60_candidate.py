#!/usr/bin/env python3
"""Build the local R60ABD1 candidate on stock ESPHome 2026.9.1.

The committed factory file keeps version: dev so the publisher can stamp a
real Alpha later. This compiles a copy. It does not patch ESPHome, publish,
or write static/public/releases.json. wifi.scan stays unsupported.

Versions follow the release tool's own rules (scripts/releases.py): strict
vX.Y.Z-alpha.N for Alpha candidates or v0.0.0-local.YYYYMMDD for local
development. Candidate builds never produce Beta. Artifact directories are
append-only: an existing candidate output is refused, never deleted.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_VERSION = "v0.0.0-local.20261105"
PINNED = "2026.9.1"

# One identity rule set: the candidate builder reuses the release tool's
# version validation instead of keeping its own channel heuristics.
_spec = importlib.util.spec_from_file_location(
    "_mmwave_release_tool", Path(__file__).resolve().with_name("releases.py")
)
release_tool = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(release_tool)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def run(cmd, env, log: Path) -> str:
    print(" ".join(str(part) for part in cmd))
    proc = subprocess.run(cmd, cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    log.write_text(proc.stdout, encoding="utf-8")
    if proc.returncode != 0:
        raise SystemExit(f"error: command failed ({proc.returncode}); see {log}")
    return proc.stdout


def expect_failure(cmd, env, log: Path) -> int:
    proc = subprocess.run(cmd, cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    log.write_text(proc.stdout, encoding="utf-8")
    if proc.returncode == 0:
        raise SystemExit("error: invalid release_channel was accepted")
    print(f"invalid profile rejected ({proc.returncode})")
    return proc.returncode


def stamp(destination: Path, version: str) -> str:
    """Stamp a copy of the factory config for one candidate build.

    The version is validated with the release tool's candidate rules before
    anything is read or written, so an invalid value cannot create files or
    change existing ones.
    """
    channel_value = release_tool.candidate_channel(version)
    text = (ROOT / "tests/r60abd1-esp32c3.factory.yaml").read_text(encoding="utf-8")
    text = text.replace(
        "core: !include r60abd1-esp32c3.yaml",
        "core: !include ../../tests/r60abd1-esp32c3.yaml",
        1,
    )
    stamped, count = re.subn(r"version:\s*dev\b", f'version: "{version}"', text, count=1)
    if count != 1 or "version: dev" in stamped:
        raise ValueError("could not stamp exactly one project version")
    stamped, channel_count = re.subn(
        r"(?m)^(\s*release_channel:\s*)dev\b",
        lambda match: f"{match.group(1)}{channel_value}",
        stamped,
        count=1,
    )
    if channel_count != 1:
        raise ValueError("could not stamp exactly one release_channel placeholder")
    destination.write_text(
        "# Generated local compile input. Not a release and not the file CI publishes.\n" + stamped,
        encoding="utf-8",
    )
    return channel_value


def bad_copy(destination: Path) -> None:
    text = (ROOT / "tests/r60abd1-esp32c3.yaml").read_text(encoding="utf-8")
    text = text.replace("name: r60abd1", "name: r60bad", 1)
    text = text.replace("path: ../components", "path: ../../components", 1)
    text = text.replace("common/r60abd1_mwcp.yaml", "../../tests/common/r60abd1_mwcp.yaml", 1)
    text = text.replace("release_channel: development", "release_channel: nightly", 1)
    destination.write_text(text, encoding="utf-8")


def find_one(paths):
    found = list(paths)
    if len(found) != 1:
        raise SystemExit(f"error: expected one match, found {found}")
    return found[0]


def assert_text(label, text, required, forbidden):
    for item in required:
        if item not in text:
            raise SystemExit(f"error: {label} is missing {item}")
    for item in forbidden:
        if item in text:
            raise SystemExit(f"error: {label} unexpectedly contains {item}")


def resolve_candidate_target(output: Path, version: str) -> Path:
    """Resolve the artifact directory for one candidate version.

    The version is already validated, so it cannot carry path separators; this
    still resolves the real path to refuse symlink escapes out of the firmware
    root. Existing outputs are refused instead of deleted, so earlier
    candidates and historical evidence are never removed or overwritten.
    """
    firmware_root = (output / "firmware").resolve()
    target = firmware_root / version / "r60abd1-ESP32-C3"
    resolved_target = target.resolve()
    if resolved_target == firmware_root or not resolved_target.is_relative_to(firmware_root):
        raise ValueError(f"candidate target {target} resolves outside {firmware_root}")
    if target.exists() or target.is_symlink():
        raise ValueError(
            f"candidate output {target} already exists; use a new --output directory "
            "(existing outputs are never deleted)"
        )
    return target


def assert_build(data_dir: Path, version: str, channel: str):
    defines_path = find_one(data_dir.glob("build/*/src/esphome/core/defines.h"))
    defines = defines_path.read_text(encoding="utf-8")
    if f'#define ESPHOME_PROJECT_VERSION "{version}"' not in defines:
        raise SystemExit("error: defines.h missing the project version")
    cmake_path = find_one(data_dir.glob("build/*/CMakeLists.txt"))
    cmake = cmake_path.read_text(encoding="utf-8")
    for flag in (
        '-DMWCP_BUILD_PROFILE=\\"r60-daily\\"',
        f'-DMWCP_RELEASE_CHANNEL=\\"{channel}\\"',
        '-DMWCP_FIRMWARE_VERSION=\\"dev\\"',
    ):
        if flag not in cmake:
            raise SystemExit(f"error: build flags missing {flag}")
    if "MWCP_WIFI_SCAN_OWNERSHIP" in defines or "MWCP_WIFI_SCAN_OWNERSHIP" in cmake:
        raise SystemExit("error: stock candidate unexpectedly enables scan ownership")
    sdk_paths = [
        path for path in data_dir.glob("build/*/sdkconfig.*")
        if "esphomeinternal" not in path.name and "." not in path.name.removeprefix("sdkconfig.")
    ]
    sdk_path = find_one(sdk_paths)
    sdkconfig = sdk_path.read_text(encoding="utf-8")
    for item in ("CONFIG_ESP_CONSOLE_NONE=y", "CONFIG_ESP_MAIN_TASK_STACK_SIZE=8192"):
        if item not in sdkconfig:
            raise SystemExit(f"error: sdkconfig missing {item}")
    if re.search(r"^CONFIG_ESP_CONSOLE_USB_SERIAL_JTAG=y$", sdkconfig, re.M):
        raise SystemExit("error: USB console is still enabled")
    factory = find_one(data_dir.glob("build/*/build/*.factory.bin"))
    ota = find_one(data_dir.glob("build/*/build/*.ota.bin"))
    return {"defines": defines_path, "sdkconfig": sdk_path, "factory": factory, "ota": ota}


def flash_fit(log_text: str) -> str:
    match = re.search(r"Flash:\s+\[[^\]]+\]\s+([\d.]+)%\s+\(used\s+(\d+)\s+bytes\s+from\s+(\d+)\s+bytes\)", log_text)
    if not match:
        raise SystemExit("error: compile log has no flash-fit line")
    percent = float(match.group(1))
    if percent >= 100:
        raise SystemExit(f"error: firmware does not fit ({percent}%)")
    return f"{match.group(1)}% ({match.group(2)}/{match.group(3)} bytes)"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--python", type=Path, required=True)
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--version", default=DEFAULT_VERSION, help="Target version string (default: local candidate)")
    parser.add_argument("--skip-compile", action="store_true")
    args = parser.parse_args()
    version = args.version
    try:
        release_tool.candidate_channel(version)
    except ValueError as error:
        raise SystemExit(f"error: invalid --version {version!r}: {error}")
    subprocess.check_call([sys.executable, str(ROOT / "scripts/check_r60_usb_profile.py")])
    data = args.data_dir.resolve()
    data.mkdir(parents=True, exist_ok=True)
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    try:
        target = resolve_candidate_target(output, version)
    except ValueError as error:
        raise SystemExit(f"error: {error}")
    reported = subprocess.check_output([str(args.python), "-m", "esphome", "version"], text=True)
    match = re.search(r"(\d{4}\.\d+\.\d+)", reported)
    esphome_ver = match.group(1) if match else ""
    if esphome_ver != PINNED:
        raise SystemExit(f"error: esphome {esphome_ver}, expected {PINNED}")
    env = dict(os.environ)
    env.pop("MSYSTEM", None)
    env["ESPHOME_DATA_DIR"] = str(data)
    stamped = data / "r60abd1.factory.yaml"
    try:
        ch = stamp(stamped, version)
    except ValueError as error:
        raise SystemExit(f"error: {error}")
    shutil.copyfile(stamped, output / "compiled.factory.yaml")
    bad = data / "bad-channel.yaml"
    bad_copy(bad)
    rejected = expect_failure([str(args.python), "-m", "esphome", "config", str(bad)], env, output / "config-bad.log")
    r60_config = run([str(args.python), "-m", "esphome", "config", str(stamped)], env, output / "config-r60.log")
    assert_text(
        "r60 config",
        r60_config,
        ["baud_rate: 0", "mmwave_host:", "captive_portal:", "reboot_timeout: 0s", f"version: {version}", "firmware_version: dev"],
        ["improv_serial:", "hardware_uart: USB_SERIAL_JTAG", "MWCP_WIFI_SCAN_OWNERSHIP"],
    )
    other = run(
        [str(args.python), "-m", "esphome", "config", str(ROOT / "tests/ld2450-esp32c3.factory.yaml")],
        env,
        output / "config-ld2450.log",
    )
    assert_text("ld2450 config", other, ["improv_serial:"], ["mmwave_host:"])
    if args.skip_compile:
        print("config ok")
        return 0
    compile_log = run([str(args.python), "-m", "esphome", "compile", str(stamped)], env, output / "compile.log")
    built = assert_build(data, version, ch)
    fit = flash_fit(compile_log)
    # The target was resolved and checked before the build started; nothing
    # that appeared meanwhile is overwritten (mkdir without exist_ok).
    target.mkdir(parents=True)
    factory_name = "r60abd1.factory.bin"
    ota_name = "r60abd1.ota.bin"
    shutil.copyfile(built["factory"], target / factory_name)
    shutil.copyfile(built["ota"], target / ota_name)
    ota_bytes = (target / ota_name).read_bytes()
    factory_bytes = (target / factory_name).read_bytes()
    factory_hash = sha256(factory_bytes)
    ota_hash = sha256(ota_bytes)
    manifest = {
        "name": f"R60ABD1 {ch}" if ch != "development" else "R60ABD1 local candidate",
        "version": version,
        "new_install_prompt_erase": True,
        "builds": [{
            "chipFamily": "ESP32-C3",
            "parts": [{"path": factory_name, "offset": 0, "md5": hashlib.md5(factory_bytes).hexdigest(), "sha256": factory_hash}],
            "ota": {"path": ota_name, "md5": hashlib.md5(ota_bytes).hexdigest(), "sha256": ota_hash},
        }],
    }
    manifest_bytes = (json.dumps(manifest, indent=2) + "\n").encode()
    (target / "manifest.json").write_bytes(manifest_bytes)
    try:
        head_commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    except Exception:
        head_commit = ""
    try:
        git_dirty = bool(subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True).strip())
    except Exception:
        git_dirty = False
    summary = {
        "version": version,
        "channel": ch,
        "sourceCommit": head_commit,
        "dirtyWorktree": git_dirty,
        "esphome": esphome_ver,
        "patched": False,
        "scan": "UNSUPPORTED",
        "flashFit": fit,
        "invalidChannelExit": rejected,
        "factorySha256": factory_hash,
        "otaSha256": ota_hash,
        "manifestSha256": sha256(manifest_bytes),
        "factoryBytes": len(factory_bytes),
        "otaBytes": len(ota_bytes),
        "defines": str(built["defines"]),
        "sdkconfig": str(built["sdkconfig"]),
    }
    (output / "artifact-summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
