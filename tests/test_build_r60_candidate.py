"""Candidate builder input and artifact-path safety (alpha review 2026-11-07 R1).

Offline: no ESPHome run, no compile, no serial, and no real deletion. The
shared release-tool validation, path resolution and CLI branches run for
real; build subprocesses and shutil.rmtree are replaced with observers.
"""
import hashlib
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import build_r60_candidate as builder  # noqa: E402
from scripts import releases as release_tool  # noqa: E402


class SharedCandidateChannelTests(unittest.TestCase):
    """The same rule set the formal publisher stamps with."""

    def test_accepts_strict_alpha_and_local_formats(self):
        self.assertEqual(release_tool.candidate_channel("v1.2.0-alpha.3"), "alpha")
        self.assertEqual(release_tool.candidate_channel(builder.DEFAULT_VERSION), "development")

    def test_rejects_beta_malformed_and_path_like_values(self):
        for value in (
            "v1.2.0-beta.1",          # Beta only promotes tested Alpha bytes
            "v1.2.0-alpha.bad",       # malformed Alpha
            "v1.2.0-alpha.",          # missing counter
            "v1.2.0-alpha.1 ",        # trailing space
            "v1.2.0-alpha.1\n",       # newline
            "../outside",             # parent directory
            "a/b",                    # forward slash
            "a\\b",                   # backslash
            "/absolute",              # absolute path
            "C:\\abs",                # windows drive
            "v1.2.0-alpha.1;echo",    # shell metacharacters
            "dev",                    # placeholder is not a release version
            "",                       # empty
            None,                     # not a string
        ):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    release_tool.candidate_channel(value)


class BuilderStampTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_alpha_stamp_writes_version_and_channel(self):
        destination = self.root / "candidate.yaml"
        channel = builder.stamp(destination, "v1.2.0-alpha.3")
        self.assertEqual(channel, "alpha")
        text = destination.read_text(encoding="utf-8")
        self.assertIn('version: "v1.2.0-alpha.3"', text)
        self.assertIn("release_channel: alpha", text)
        self.assertNotIn("release_channel: dev", text)

    def test_local_stamp_keeps_development_channel(self):
        destination = self.root / "candidate.yaml"
        channel = builder.stamp(destination, builder.DEFAULT_VERSION)
        self.assertEqual(channel, "development")
        text = destination.read_text(encoding="utf-8")
        self.assertIn(f'version: "{builder.DEFAULT_VERSION}"', text)
        self.assertIn("release_channel: development", text)
        self.assertNotIn("release_channel: alpha", text)

    def test_invalid_version_writes_nothing_and_keeps_existing_bytes(self):
        destination = self.root / "candidate.yaml"
        destination.write_text("ORIGINAL", encoding="utf-8")
        for value in ("v1.2.0-beta.1", "v1.2.0-alpha.bad", "../outside", "..\\outside",
                      "/absolute", "C:\\abs", "v1.2.0-alpha.1\n"):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    builder.stamp(destination, value)
                self.assertEqual(destination.read_text(encoding="utf-8"), "ORIGINAL")
        self.assertEqual(sorted(item.name for item in self.root.iterdir()), ["candidate.yaml"])


class BuilderMainTests(unittest.TestCase):
    """CLI level: real validation, path resolution and branches; build I/O observed."""

    VERSION = "v1.2.0-alpha.7"

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.data = self.root / "data"
        self.output = self.root / "output"
        self.subprocess_calls = []
        self.deletions = []

    def _fabricate_build_outputs(self, version):
        """Create the files assert_build() inspects after a real compile."""
        build = self.data / "build" / "r60abd1"
        (build / "src" / "esphome" / "core").mkdir(parents=True)
        (build / "build").mkdir()
        defines = build / "src" / "esphome" / "core" / "defines.h"
        defines.write_text(f'#define ESPHOME_PROJECT_VERSION "{version}"\n', encoding="utf-8")
        cmake = build / "CMakeLists.txt"
        cmake.write_text(
            '-DMWCP_BUILD_PROFILE=\\"r60-daily\\"\n'
            f'-DMWCP_RELEASE_CHANNEL=\\"alpha\\"\n'
            '-DMWCP_FIRMWARE_VERSION=\\"dev\\"\n',
            encoding="utf-8",
        )
        sdkconfig = build / "sdkconfig.r60abd1"
        sdkconfig.write_text("CONFIG_ESP_CONSOLE_NONE=y\nCONFIG_ESP_MAIN_TASK_STACK_SIZE=8192\n", encoding="utf-8")
        factory = build / "build" / "r60abd1.factory.bin"
        factory.write_bytes(b"factory-bytes")
        ota = build / "build" / "r60abd1.ota.bin"
        ota.write_bytes(b"ota-bytes")
        return {"factory": factory, "ota": ota}

    def _run_main(self, *extra_args):
        """Run builder.main() with subprocesses and deletion replaced by observers."""
        argv = [
            "build_r60_candidate.py",
            "--python", "unused-python",
            "--data-dir", str(self.data),
            "--output", str(self.output),
            *extra_args,
        ]
        stdout, stderr = StringIO(), StringIO()

        def fake_check_call(cmd, **kwargs):
            self.subprocess_calls.append(("check_call", list(map(str, cmd))))
            return 0

        def fake_check_output(cmd, **kwargs):
            self.subprocess_calls.append(("check_output", list(map(str, cmd))))
            text = " ".join(str(part) for part in cmd)
            if "-m esphome version" in text:
                return "Version: 2026.9.1\n"
            if "rev-parse" in text:
                return ("a" * 40) + "\n"
            if "status" in text:
                return ""
            raise AssertionError(f"unexpected check_output: {cmd}")

        def fake_run(cmd, env, log):
            self.subprocess_calls.append(("run", list(map(str, cmd))))
            action = cmd[3]
            if action == "config":
                if "ld2450" in str(cmd[-1]):
                    return "improv_serial:\n"
                return (
                    "baud_rate: 0\nmmwave_host:\ncaptive_portal:\nreboot_timeout: 0s\n"
                    f"version: {self._stamped_version}\nfirmware_version: dev\n"
                )
            if action == "compile":
                return (
                    "build output\n"
                    "Flash: [==================================================]  82.5% (used 1514176 bytes from 1835008 bytes)\n"
                )
            raise AssertionError(f"unexpected esphome action: {cmd}")

        def fake_expect_failure(cmd, env, log):
            self.subprocess_calls.append(("expect_failure", list(map(str, cmd))))
            return 2

        self._stamped_version = builder.DEFAULT_VERSION
        if "--version" in extra_args:
            self._stamped_version = extra_args[extra_args.index("--version") + 1]

        code, exit_message = 0, ""
        with patch.object(builder.sys, "argv", argv), \
             patch.object(builder.subprocess, "check_call", fake_check_call), \
             patch.object(builder.subprocess, "check_output", fake_check_output), \
             patch.object(builder, "run", fake_run), \
             patch.object(builder, "expect_failure", fake_expect_failure), \
             patch.object(builder.shutil, "rmtree", lambda *a, **k: self.deletions.append(a)), \
             redirect_stdout(stdout), redirect_stderr(stderr):
            try:
                code = builder.main()
            except SystemExit as stop:
                code = stop.code if isinstance(stop.code, int) else 1
                exit_message = str(stop.code)
        return code, stdout.getvalue(), exit_message

    def test_invalid_version_runs_nothing_and_creates_nothing(self):
        for value in ("v1.2.0-beta.1", "v1.2.0-alpha.bad", "../outside", "..\\outside", "/absolute"):
            with self.subTest(value=value):
                code, _, message = self._run_main("--version", value)
                self.assertEqual(code, 1)
                self.assertIn("invalid --version", message)
                self.assertEqual(self.subprocess_calls, [], "no subprocess may run for an invalid version")
                self.assertEqual(self.deletions, [])
                self.assertFalse(self.data.exists(), "data dir must not be created")
                self.assertFalse(self.output.exists(), "output dir must not be created")
                self.assertEqual(list(self.root.iterdir()), [], "no files may be created")

    def test_skip_compile_writes_stamped_config_only(self):
        code, _, _ = self._run_main("--version", self.VERSION, "--skip-compile")
        self.assertEqual(code, 0)
        stamped = self.data / "r60abd1.factory.yaml"
        text = stamped.read_text(encoding="utf-8")
        self.assertIn(f'version: "{self.VERSION}"', text)
        self.assertIn("release_channel: alpha", text)
        self.assertTrue((self.output / "compiled.factory.yaml").is_file())
        self.assertFalse((self.output / "firmware").exists(), "skip-compile must not create artifacts")
        self.assertEqual(self.deletions, [])

    def test_default_version_is_the_local_candidate(self):
        code, _, _ = self._run_main("--skip-compile")
        self.assertEqual(code, 0)
        text = (self.data / "r60abd1.factory.yaml").read_text(encoding="utf-8")
        self.assertIn(f'version: "{builder.DEFAULT_VERSION}"', text)
        self.assertIn("release_channel: development", text)

    def test_full_build_writes_candidate_inside_firmware_root(self):
        self._fabricate_build_outputs(self.VERSION)
        code, _, _ = self._run_main("--version", self.VERSION)
        self.assertEqual(code, 0)
        target = self.output / "firmware" / self.VERSION / "r60abd1-ESP32-C3"
        self.assertTrue((target / "r60abd1.factory.bin").is_file())
        self.assertTrue((target / "r60abd1.ota.bin").is_file())
        self.assertTrue((target / "manifest.json").is_file())
        self.assertEqual((target / "r60abd1.factory.bin").read_bytes(), b"factory-bytes")
        self.assertEqual(self.deletions, [], "no candidate output may ever be deleted")
        summary = (self.output / "artifact-summary.json").read_text(encoding="utf-8")
        import json
        data = json.loads(summary)
        self.assertEqual(data["version"], self.VERSION)
        self.assertEqual(data["channel"], "alpha")
        self.assertEqual(data["factorySha256"], hashlib.sha256(b"factory-bytes").hexdigest())

    def test_existing_target_is_refused_and_not_overwritten(self):
        self._fabricate_build_outputs(self.VERSION)
        target = self.output / "firmware" / self.VERSION / "r60abd1-ESP32-C3"
        target.mkdir(parents=True)
        sentinel = target / "keep.txt"
        sentinel.write_text("HISTORICAL", encoding="utf-8")
        code, _, message = self._run_main("--version", self.VERSION)
        self.assertEqual(code, 1)
        self.assertIn("already exists", message)
        self.assertEqual(self.deletions, [], "existing outputs must never be deleted")
        self.assertEqual(sentinel.read_text(encoding="utf-8"), "HISTORICAL")
        self.assertEqual(sorted(item.name for item in target.iterdir()), ["keep.txt"])

    def test_symlink_escape_is_refused(self):
        outside = self.root / "outside"
        outside.mkdir()
        firmware = self.output / "firmware"
        firmware.mkdir(parents=True)
        try:
            (firmware / self.VERSION).symlink_to(outside, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("symlinks are not permitted on this platform/account")
        code, _, message = self._run_main("--version", self.VERSION)
        self.assertEqual(code, 1)
        self.assertIn("resolves outside", message)
        self.assertEqual(self.deletions, [])
        self.assertEqual(list(outside.iterdir()), [], "nothing may be created outside the firmware root")


if __name__ == "__main__":
    unittest.main()
