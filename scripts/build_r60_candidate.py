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
from datetime import datetime, timezone
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

# Explicit source input scope for source-state recording
EXPLICIT_SOURCE_FILES = [
    "tests/r60abd1-esp32c3.factory.yaml",
    "tests/r60abd1-esp32c3.yaml",
    "tests/common/r60abd1_mwcp.yaml",
    "tests/common/_device.yaml",
    "tests/common/_areas_host.yaml",
    "scripts/build_r60_candidate.py",
    "scripts/releases.py",
    "scripts/check_r60_usb_profile.py",
]

EXPLICIT_SOURCE_DIRS = [
    "components/mmwave_host",
    "components/r60abd1",
    "protocol/cpp",
]


class BuildStageError(Exception):
    def __init__(self, stage: str, exit_code: int, message: str):
        super().__init__(message)
        self.stage = stage
        self.exit_code = exit_code


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def collect_source_files(root: Path = ROOT) -> list[str]:
    files = set()
    for rel in EXPLICIT_SOURCE_FILES:
        p = root / rel
        if p.is_file():
            files.add(rel)
    for rel_dir in EXPLICIT_SOURCE_DIRS:
        d = root / rel_dir
        if d.is_dir():
            for p in d.rglob("*"):
                if p.is_file() and not p.name.endswith(".pyc") and not p.name.startswith("."):
                    files.add(p.relative_to(root).as_posix())
    return sorted(files)


def hash_source_files(rel_files: list[str], root: Path = ROOT) -> dict[str, str]:
    res = {}
    for rel in rel_files:
        p = root / rel
        if p.is_file():
            res[rel] = sha256(p.read_bytes())
        else:
            res[rel] = "missing"
    return res


def capture_git_state(rel_files: list[str], root: Path = ROOT) -> dict:
    try:
        head = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=root, text=True, stderr=subprocess.PIPE
        ).strip()
    except Exception as e:
        return {
            "head": "unknown",
            "status": "unknown",
            "error": str(e),
            "dirtyScopeFiles": [],
            "patch": "",
        }
    try:
        porcelain = subprocess.check_output(
            ["git", "status", "--porcelain"], cwd=root, text=True, stderr=subprocess.PIPE
        ).rstrip("\r\n")
        is_dirty = bool(porcelain)
        dirty_scope = []
        if porcelain:
            # Keep the leading status column: git porcelain lines are "XY <path>",
            # so only trailing newlines may be stripped, never the line head.
            for line in porcelain.rstrip("\r\n").splitlines():
                path_part = line[3:].strip()
                if " -> " in path_part:  # rename entries: track the new path
                    path_part = path_part.split(" -> ", 1)[1]
                path_part = path_part.replace("\\", "/")
                for rf in rel_files:
                    if path_part == rf or path_part.startswith(rf):
                        dirty_scope.append(line)
                        break
        diff = ""
        if is_dirty:
            try:
                diff = subprocess.check_output(
                    ["git", "diff", "HEAD", "--"] + list(rel_files),
                    cwd=root,
                    text=True,
                    stderr=subprocess.PIPE,
                )
            except Exception:
                diff = ""
        return {
            "head": head,
            "status": "dirty" if is_dirty else "clean",
            "dirtyScopeFiles": dirty_scope,
            "patch": diff,
        }
    except Exception as e:
        return {
            "head": head,
            "status": "unknown",
            "error": str(e),
            "dirtyScopeFiles": [],
            "patch": "",
        }


def record_source_state(
    output: Path,
    version: str,
    channel: str,
    esphome_ver: str,
    run_id: str,
    root: Path = ROOT,
) -> tuple[dict, dict[str, str]]:
    rel_files = collect_source_files(root)
    source_inputs = hash_source_files(rel_files, root)
    git_info = capture_git_state(rel_files, root)

    patch_rel = None
    if git_info.get("patch"):
        patch_path = output / "source-dirty.patch"
        patch_path.write_text(git_info["patch"], encoding="utf-8")
        patch_rel = patch_path.name

    source_state = {
        "schemaVersion": 1,
        "runId": run_id,
        "recordedAt": datetime.now(timezone.utc).isoformat(),
        "version": version,
        "channel": channel,
        "buildProfile": "r60-daily",
        "esphomeVersion": esphome_ver,
        "git": {
            "head": git_info["head"],
            "status": git_info["status"],
            "dirtyScopeFiles": git_info["dirtyScopeFiles"],
            "patchFile": patch_rel,
        },
        "sourceInputs": source_inputs,
        "sourceInputCount": len(source_inputs),
    }
    if "error" in git_info:
        source_state["git"]["error"] = git_info["error"]

    state_path = output / "source-state.json"
    state_path.write_text(json.dumps(source_state, indent=2) + "\n", encoding="utf-8")
    return source_state, source_inputs


def verify_source_inputs(
    initial_inputs: dict[str, str], root: Path = ROOT
) -> tuple[bool, list[str]]:
    """Re-collect the declared source set and compare it with the start snapshot.

    Re-hashing only the original keys would miss a file added inside the
    declared directories while the compiler ran. Deletions stay visible because
    the original paths are hashed as "missing" when they disappear.
    """
    current = hash_source_files(collect_source_files(root), root)
    changes = []
    for rel in sorted(set(initial_inputs) | set(current)):
        before = initial_inputs.get(rel)
        after = current.get(rel)
        if before == after:
            continue
        if before is None:
            changes.append(f"{rel} (added, now {after[:8]})")
        elif after is None or after == "missing":
            changes.append(f"{rel} (removed, was {before[:8]})")
        else:
            changes.append(f"{rel} (was {before[:8]}, now {after[:8]})")
    return len(changes) == 0, changes


def stamped_config_unchanged(
    stamped: Path, archived: Path, baseline: bytes
) -> tuple[bool, list[str]]:
    """The file ESPHome consumed must still match the bytes stamped at start.

    Re-hashing the file after it changed and calling that the archive hash
    would hide the edit. The comparison is against the bytes captured when the
    stamp was written.
    """
    reasons = []
    try:
        consumed = stamped.read_bytes()
    except OSError as error:
        return False, [f"stamped config unreadable after compile: {error}"]
    try:
        copy = archived.read_bytes()
    except OSError as error:
        return False, [f"archived compiled.factory.yaml unreadable: {error}"]
    if consumed != baseline:
        reasons.append("consumed stamped config changed after it was handed to ESPHome")
    if copy != baseline:
        reasons.append("archived compiled.factory.yaml no longer matches the start snapshot")
    if consumed != copy:
        reasons.append("consumed stamped config and archived copy differ")
    return len(reasons) == 0, reasons


def run(cmd, env, log: Path) -> str:
    print(" ".join(str(part) for part in cmd))
    proc = subprocess.run(
        cmd, cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
    )
    log.write_text(proc.stdout, encoding="utf-8")
    if proc.returncode != 0:
        raise BuildStageError(
            "compile_command", proc.returncode, f"command failed ({proc.returncode}); see {log}"
        )
    return proc.stdout


def expect_failure(cmd, env, log: Path) -> int:
    proc = subprocess.run(
        cmd, cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
    )
    log.write_text(proc.stdout, encoding="utf-8")
    if proc.returncode == 0:
        raise BuildStageError(
            "bad_channel_validation", 1, "error: invalid release_channel was accepted"
        )
    print(f"invalid profile rejected ({proc.returncode})")
    return proc.returncode


def stamp(destination: Path, version: str) -> str:
    """Stamp a copy of the factory config for one candidate build.

    The version is validated with the release tool's candidate rules before
    anything is read or written, so an invalid value cannot create files or
    change existing ones.
    The relative path to r60abd1-esp32c3.yaml is computed dynamically relative
    to the destination directory so deep or shallow run directories work.
    """
    channel_value = release_tool.candidate_channel(version)
    destination = destination.resolve()
    try:
        rel_core = os.path.relpath(ROOT / "tests/r60abd1-esp32c3.yaml", destination.parent).replace(
            "\\", "/"
        )
    except ValueError:
        rel_core = (ROOT / "tests/r60abd1-esp32c3.yaml").as_posix()
    text = (ROOT / "tests/r60abd1-esp32c3.factory.yaml").read_text(encoding="utf-8")
    text = text.replace(
        "core: !include r60abd1-esp32c3.yaml",
        f"core: !include {rel_core}",
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
        "# Generated local compile input. Not a release and not the file CI publishes.\n"
        + stamped,
        encoding="utf-8",
    )
    return channel_value


def bad_copy(destination: Path) -> None:
    destination = destination.resolve()
    try:
        rel_components = os.path.relpath(ROOT / "components", destination.parent).replace("\\", "/")
    except ValueError:
        rel_components = (ROOT / "components").as_posix()
    try:
        rel_mwcp = os.path.relpath(ROOT / "tests/common/r60abd1_mwcp.yaml", destination.parent).replace(
            "\\", "/"
        )
    except ValueError:
        rel_mwcp = (ROOT / "tests/common/r60abd1_mwcp.yaml").as_posix()
    text = (ROOT / "tests/r60abd1-esp32c3.yaml").read_text(encoding="utf-8")
    text = text.replace("name: r60abd1", "name: r60bad", 1)
    text = text.replace("path: ../components", f"path: {rel_components}", 1)
    text = text.replace("common/r60abd1_mwcp.yaml", rel_mwcp, 1)
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
            raise BuildStageError(
                f"assert_text_{label}", 1, f"error: {label} is missing {item}"
            )
    for item in forbidden:
        if item in text:
            raise BuildStageError(
                f"assert_text_{label}", 1, f"error: {label} unexpectedly contains {item}"
            )


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


def check_output_clean(output: Path, version: str) -> Path:
    """Ensure output directory does not silently overwrite existing run artifacts."""
    target = resolve_candidate_target(output, version)
    for protected in (
        "artifact-summary.json",
        "compiled.factory.yaml",
        "source-state.json",
        "compile.log",
        "config-bad.log",
        "config-r60.log",
        "config-ld2450.log",
        "source-dirty.patch",
    ):
        if (output / protected).exists():
            raise ValueError(
                f"output directory {output} already contains previous run artifact ({protected}); "
                "use a new --output directory to protect historical outputs"
            )
    return target


def write_failure_summary(
    output: Path,
    stage: str,
    exit_code: int,
    error_msg: str,
    version: str,
    channel: str,
    run_id: str,
) -> None:
    fail_summary = {
        "status": "failed",
        "stage": stage,
        "exitCode": exit_code,
        "error": str(error_msg),
        "version": version,
        "channel": channel,
        "runId": run_id,
        "recordedAt": datetime.now(timezone.utc).isoformat(),
    }
    try:
        (output / "artifact-summary.json").write_text(
            json.dumps(fail_summary, indent=2) + "\n", encoding="utf-8"
        )
    except Exception:
        pass


def assert_build(data_dir: Path, version: str, channel: str):
    defines_path = find_one(data_dir.glob("build/*/src/esphome/core/defines.h"))
    defines = defines_path.read_text(encoding="utf-8")
    if f'#define ESPHOME_PROJECT_VERSION "{version}"' not in defines:
        raise BuildStageError("assert_build", 1, "error: defines.h missing the project version")
    cmake_path = find_one(data_dir.glob("build/*/CMakeLists.txt"))
    cmake = cmake_path.read_text(encoding="utf-8")
    for flag in (
        '-DMWCP_BUILD_PROFILE=\\"r60-daily\\"',
        f'-DMWCP_RELEASE_CHANNEL=\\"{channel}\\"',
        '-DMWCP_FIRMWARE_VERSION=\\"dev\\"',
    ):
        if flag not in cmake:
            raise BuildStageError("assert_build", 1, f"error: build flags missing {flag}")
    if "MWCP_WIFI_SCAN_OWNERSHIP" in defines or "MWCP_WIFI_SCAN_OWNERSHIP" in cmake:
        raise BuildStageError(
            "assert_build", 1, "error: stock candidate unexpectedly enables scan ownership"
        )
    sdk_paths = [
        path
        for path in data_dir.glob("build/*/sdkconfig.*")
        if "esphomeinternal" not in path.name and "." not in path.name.removeprefix("sdkconfig.")
    ]
    sdk_path = find_one(sdk_paths)
    sdkconfig = sdk_path.read_text(encoding="utf-8")
    for item in ("CONFIG_ESP_CONSOLE_NONE=y", "CONFIG_ESP_MAIN_TASK_STACK_SIZE=8192"):
        if item not in sdkconfig:
            raise BuildStageError("assert_build", 1, f"error: sdkconfig missing {item}")
    if re.search(r"^CONFIG_ESP_CONSOLE_USB_SERIAL_JTAG=y$", sdkconfig, re.M):
        raise BuildStageError("assert_build", 1, "error: USB console is still enabled")
    factory = find_one(data_dir.glob("build/*/build/*.factory.bin"))
    ota = find_one(data_dir.glob("build/*/build/*.ota.bin"))
    return {"defines": defines_path, "sdkconfig": sdk_path, "factory": factory, "ota": ota}


def flash_fit(log_text: str) -> str:
    match = re.search(
        r"Flash:\s+\[[^\]]+\]\s+([\d.]+)%\s+\(used\s+(\d+)\s+bytes\s+from\s+(\d+)\s+bytes\)",
        log_text,
    )
    if not match:
        raise BuildStageError("flash_fit", 1, "error: compile log has no flash-fit line")
    percent = float(match.group(1))
    if percent >= 100:
        raise BuildStageError("flash_fit", 1, f"error: firmware does not fit ({percent}%)")
    return f"{match.group(1)}% ({match.group(2)}/{match.group(3)} bytes)"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--python", type=Path, required=True)
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--version", default=DEFAULT_VERSION, help="Target version string (default: local candidate)"
    )
    parser.add_argument(
        "--run-id", default=None, help="Explicit run ID (default: generated timestamp ID)"
    )
    parser.add_argument("--skip-compile", action="store_true")
    args = parser.parse_args()
    version = args.version

    # Strict version validation before ANY filesystem modification or child process execution
    try:
        ch = release_tool.candidate_channel(version)
    except ValueError as error:
        raise SystemExit(f"error: invalid --version {version!r}: {error}")

    run_id = (
        args.run_id
        if args.run_id
        else f"run-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"
    )

    data = args.data_dir.resolve()
    output = args.output.resolve()

    # Pre-execution check: output must not exist or overwrite previous run artifacts
    try:
        target = check_output_clean(output, version)
    except ValueError as error:
        raise SystemExit(f"error: {error}")

    data.mkdir(parents=True, exist_ok=True)
    output.mkdir(parents=True, exist_ok=True)

    try:
        # Record source state before modifying configs or compiling
        source_state, initial_inputs = record_source_state(
            output, version, ch, PINNED, run_id, ROOT
        )

        subprocess.check_call([sys.executable, str(ROOT / "scripts/check_r60_usb_profile.py")])

        reported = subprocess.check_output(
            [str(args.python), "-m", "esphome", "version"], text=True
        )
        match = re.search(r"(\d{4}\.\d+\.\d+)", reported)
        esphome_ver = match.group(1) if match else ""
        if esphome_ver != PINNED:
            raise BuildStageError(
                "esphome_version", 1, f"error: esphome {esphome_ver}, expected {PINNED}"
            )

        env = dict(os.environ)
        env.pop("MSYSTEM", None)
        env["ESPHOME_DATA_DIR"] = str(data)

        stamped = data / "r60abd1.factory.yaml"
        try:
            ch = stamp(stamped, version)
        except ValueError as error:
            raise BuildStageError("stamp", 1, f"error: {error}")

        shutil.copyfile(stamped, output / "compiled.factory.yaml")
        stamped_baseline = stamped.read_bytes()

        bad = data / "bad-channel.yaml"
        bad_copy(bad)
        rejected = expect_failure(
            [str(args.python), "-m", "esphome", "config", str(bad)],
            env,
            output / "config-bad.log",
        )

        r60_config = run(
            [str(args.python), "-m", "esphome", "config", str(stamped)],
            env,
            output / "config-r60.log",
        )
        assert_text(
            "r60 config",
            r60_config,
            [
                "baud_rate: 0",
                "mmwave_host:",
                "captive_portal:",
                "reboot_timeout: 0s",
                f"version: {version}",
                "firmware_version: dev",
            ],
            ["improv_serial:", "hardware_uart: USB_SERIAL_JTAG", "MWCP_WIFI_SCAN_OWNERSHIP"],
        )

        other = run(
            [str(args.python), "-m", "esphome", "config", str(ROOT / "tests/ld2450-esp32c3.factory.yaml")],
            env,
            output / "config-ld2450.log",
        )
        assert_text("ld2450 config", other, ["improv_serial:"], ["mmwave_host:"])

        # Config-stage check only. A later compile must not reuse this result:
        # the trustworthy association is decided after compile returns.
        sources_intact, modified_files = verify_source_inputs(initial_inputs, ROOT)
        if not sources_intact:
            print(f"warning: source inputs changed during config: {modified_files}")

        if args.skip_compile:
            summary = {
                "status": "success" if sources_intact else "uncertain",
                "runId": run_id,
                "version": version,
                "channel": ch,
                "buildProfile": "r60-daily",
                "sourceCommit": source_state["git"]["head"],
                "gitStatus": source_state["git"]["status"],
                "dirtyWorktree": source_state["git"]["status"] == "dirty",
                "sourceState": "source-state.json",
                "sourceStateSha256": sha256((output / "source-state.json").read_bytes()),
                "stampedConfig": "compiled.factory.yaml",
                "stampedConfigSha256": sha256((output / "compiled.factory.yaml").read_bytes()),
                "esphome": esphome_ver,
                "patched": False,
                "scan": "UNSUPPORTED",
                "invalidChannelExit": rejected,
                "compileSkipped": True,
            }
            if not sources_intact:
                summary["identityNote"] = (
                    "source inputs changed during the run; artifacts may not match the recorded source-state"
                )
                summary["modifiedInputsDuringBuild"] = modified_files
            (output / "artifact-summary.json").write_text(
                json.dumps(summary, indent=2) + "\n", encoding="utf-8"
            )
            print(json.dumps(summary, indent=2))
            print("config ok")
            return 0

        compile_log = run(
            [str(args.python), "-m", "esphome", "compile", str(stamped)],
            env,
            output / "compile.log",
        )
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
            "builds": [
                {
                    "chipFamily": "ESP32-C3",
                    "parts": [
                        {
                            "path": factory_name,
                            "offset": 0,
                            "md5": hashlib.md5(factory_bytes).hexdigest(),
                            "sha256": factory_hash,
                        }
                    ],
                    "ota": {
                        "path": ota_name,
                        "md5": hashlib.md5(ota_bytes).hexdigest(),
                        "sha256": ota_hash,
                    },
                }
            ],
        }
        manifest_bytes = (json.dumps(manifest, indent=2) + "\n").encode("utf-8")
        (target / "manifest.json").write_bytes(manifest_bytes)

        # Final check after compile returns. Do not reuse the pre-compile result.
        final_intact, final_changes = verify_source_inputs(initial_inputs, ROOT)
        config_intact, config_reasons = stamped_config_unchanged(
            stamped, output / "compiled.factory.yaml", stamped_baseline
        )
        reasons = list(final_changes)
        reasons.extend(config_reasons)
        trustworthy = final_intact and config_intact

        summary = {
            "status": "success" if trustworthy else "uncertain",
            "runId": run_id,
            "version": version,
            "channel": ch,
            "buildProfile": "r60-daily",
            "sourceCommit": source_state["git"]["head"],
            "gitStatus": source_state["git"]["status"],
            "dirtyWorktree": source_state["git"]["status"] == "dirty",
            "sourceState": "source-state.json",
            "sourceStateSha256": sha256((output / "source-state.json").read_bytes()),
            "stampedConfig": "compiled.factory.yaml",
            "stampedConfigSha256": sha256(stamped_baseline),
            "stampedConfigMatchesConsumed": config_intact,
            "sourceModifiedDuringBuild": not trustworthy,
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
        if not trustworthy:
            summary["identityNote"] = (
                "inputs changed during compile; artifacts are not a trustworthy candidate"
            )
            summary["modifiedInputsDuringBuild"] = reasons
            print(f"warning: candidate identity uncertain after compile: {reasons}")

        (output / "artifact-summary.json").write_text(
            json.dumps(summary, indent=2) + "\n", encoding="utf-8"
        )
        print(json.dumps(summary, indent=2))
        return 0

    except BuildStageError as bse:
        write_failure_summary(output, bse.stage, bse.exit_code, str(bse), version, ch, run_id)
        raise SystemExit(str(bse))
    except Exception as exc:
        write_failure_summary(output, "unexpected_error", 1, str(exc), version, ch, run_id)
        raise


if __name__ == "__main__":
    sys.exit(main())
