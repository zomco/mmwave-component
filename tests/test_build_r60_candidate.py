"""Candidate builder input and artifact-path safety (alpha review 2026-11-07 R1).

Offline: no ESPHome run, no compile, no serial, and no real deletion. The
shared release-tool validation, path resolution and CLI branches run for
real; build subprocesses and shutil.rmtree are replaced with observers.
"""
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
import unittest
import contextlib
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
        channel = release_tool.candidate_channel(version)
        """Create the files assert_build() inspects after a real compile."""
        build = self.data / "build" / "r60abd1"
        (build / "src" / "esphome" / "core").mkdir(parents=True)
        (build / "build").mkdir()
        defines = build / "src" / "esphome" / "core" / "defines.h"
        defines.write_text(f'#define ESPHOME_PROJECT_VERSION "{version}"\n', encoding="utf-8")
        cmake = build / "CMakeLists.txt"
        cmake.write_text(
            r'-DMWCP_BUILD_PROFILE=\"r60-daily\"' + "\n" +
            rf'-DMWCP_RELEASE_CHANNEL=\"{channel}\"' + "\n" +
            r'-DMWCP_FIRMWARE_VERSION=\"dev\"' + "\n",
            encoding="utf-8",
        )
        sdkconfig = build / "sdkconfig.r60abd1"
        sdkconfig.write_text("CONFIG_ESP_CONSOLE_NONE=y\nCONFIG_ESP_MAIN_TASK_STACK_SIZE=8192\n", encoding="utf-8")
        factory = build / "build" / "r60abd1.factory.bin"
        factory.write_bytes(b"factory-bytes")
        ota = build / "build" / "r60abd1.ota.bin"
        ota.write_bytes(b"ota-bytes")
        return {"factory": factory, "ota": ota}

    def _run_main(self, *extra_args, git_fails=False, status_text="", diff_text="", fail_compile=False, root=None):
        """Run builder.main() with subprocesses and deletion replaced by observers.

        git_fails: every git invocation raises, exercising the unknown fallback.
        status_text: porcelain output returned for 'git status' (dirty-tree cases).
        diff_text: patch text returned for 'git diff HEAD -- <files>'.
        fail_compile: the mocked esphome compile writes its log then raises
            BuildStageError, exercising the failed-run summary path.
        root: patch builder.ROOT to this directory (fabricated mini-repo).
        """
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
            if git_fails and "-m esphome version" not in text:
                raise OSError("git is not available")
            if "-m esphome version" in text:
                return "Version: 2026.9.1\n"
            if "rev-parse" in text:
                return ("a" * 40) + "\n"
            if "diff" in text:
                return diff_text
            if "status" in text:
                return status_text
            raise AssertionError(f"unexpected check_output: {cmd}")

        def fake_run(cmd, env, log):
            self.subprocess_calls.append(("run", list(map(str, cmd))))
            log.write_text("simulated esphome output\n", encoding="utf-8")
            action = cmd[3]
            if action == "config":
                if "ld2450" in str(cmd[-1]):
                    return "improv_serial:\n"
                if getattr(self, "_on_config", None):
                    self._on_config()
                return (
                    "baud_rate: 0\nmmwave_host:\ncaptive_portal:\nreboot_timeout: 0s\n"
                    f"version: {self._stamped_version}\nfirmware_version: dev\n"
                )
            if action == "compile":
                if fail_compile:
                    log.write_text("partial compile output\n", encoding="utf-8")
                    raise builder.BuildStageError("compile_command", 2, "command failed (2); see log")
                if getattr(self, "_on_compile", None):
                    self._on_compile()
                return (
                    "build output\n"
                    "Flash: [==================================================]  82.5% (used 1514176 bytes from 1835008 bytes)\n"
                )
            raise AssertionError(f"unexpected esphome action: {cmd}")

        def fake_expect_failure(cmd, env, log):
            self.subprocess_calls.append(("expect_failure", list(map(str, cmd))))
            log.write_text("simulated rejection output\n", encoding="utf-8")
            return 2

        self._stamped_version = builder.DEFAULT_VERSION
        if "--version" in extra_args:
            self._stamped_version = extra_args[extra_args.index("--version") + 1]

        code, exit_message = 0, ""
        patches = [
            patch.object(builder.sys, "argv", argv),
            patch.object(builder.subprocess, "check_call", fake_check_call),
            patch.object(builder.subprocess, "check_output", fake_check_output),
            patch.object(builder, "run", fake_run),
            patch.object(builder, "expect_failure", fake_expect_failure),
            patch.object(builder.shutil, "rmtree", lambda *a, **k: self.deletions.append(a)),
        ]
        if root is not None:
            patches.append(patch.object(builder, "ROOT", root))
        with redirect_stdout(stdout), redirect_stderr(stderr):
            with contextlib.ExitStack() as stack:
                for item in patches:
                    stack.enter_context(item)
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



class CompileWindowTests(unittest.TestCase):
    """CO-R1: the identity verdict is computed after the real compile returns."""

    VERSION = "v1.2.0-alpha.7"

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.data = self.root / "data"
        self.output = self.root / "output"
        self.subprocess_calls = []
        self.deletions = []
        self.mini = self.root / "repo"
        for rel in builder.EXPLICIT_SOURCE_FILES:
            target = self.mini / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(builder.ROOT / rel, target)
        self.probe = self.mini / "components" / "r60abd1" / "probe.cpp"
        self.probe.parent.mkdir(parents=True, exist_ok=True)
        self.probe.write_text("// original input\n", encoding="utf-8")

    def _run(self, during_compile=None):
        BuilderMainTests._fabricate_build_outputs(self, self.VERSION)
        self._on_compile = during_compile
        return BuilderMainTests._run_main(self, "--version", self.VERSION, root=self.mini)

    def _summary(self):
        return json.loads((self.output / "artifact-summary.json").read_text(encoding="utf-8"))

    def test_unchanged_compile_stays_success_and_links_hashes(self):
        code, _, message = self._run()
        self.assertEqual(code, 0, message)
        summary = self._summary()
        self.assertEqual(summary["status"], "success")
        self.assertFalse(summary["sourceModifiedDuringBuild"])
        self.assertTrue(summary["stampedConfigMatchesConsumed"])
        state = json.loads((self.output / "source-state.json").read_text(encoding="utf-8"))
        self.assertEqual(
            summary["sourceStateSha256"],
            hashlib.sha256((self.output / "source-state.json").read_bytes()).hexdigest(),
        )
        archived = (self.output / "compiled.factory.yaml").read_bytes()
        consumed = (self.data / "r60abd1.factory.yaml").read_bytes()
        self.assertEqual(archived, consumed)
        self.assertEqual(summary["stampedConfigSha256"], hashlib.sha256(archived).hexdigest())
        self.assertIn("components/r60abd1/probe.cpp", state["sourceInputs"])
        self.assertEqual(summary["factorySha256"], hashlib.sha256(b"factory-bytes").hexdigest())

    def test_existing_source_edited_during_compile_is_uncertain(self):
        def edit():
            self.probe.write_text("// edited during compile\n", encoding="utf-8")

        code, _, _ = self._run(edit)
        self.assertEqual(code, 0)
        summary = self._summary()
        self.assertEqual(summary["status"], "uncertain")
        self.assertTrue(summary["sourceModifiedDuringBuild"])
        self.assertNotEqual(summary["status"], "success")
        joined = "\n".join(summary["modifiedInputsDuringBuild"])
        self.assertIn("components/r60abd1/probe.cpp", joined)
        self.assertTrue((self.output / "source-state.json").is_file())
        self.assertTrue((self.output / "compiled.factory.yaml").is_file())
        self.assertTrue((self.output / "compile.log").is_file())

    def test_source_added_and_removed_during_compile_is_uncertain(self):
        def change_set():
            (self.probe.parent / "added.cpp").write_text("// added during compile\n", encoding="utf-8")
            self.probe.unlink()

        code, _, _ = self._run(change_set)
        summary = self._summary()
        self.assertEqual(summary["status"], "uncertain")
        self.assertTrue(summary["sourceModifiedDuringBuild"])
        joined = "\n".join(summary["modifiedInputsDuringBuild"])
        self.assertIn("components/r60abd1/added.cpp", joined)
        self.assertIn("components/r60abd1/probe.cpp", joined)
        self.assertIn("added", joined)
        self.assertIn("removed", joined)

    def test_consumed_stamped_config_edited_during_compile_is_uncertain(self):
        archived_before = None

        def edit_stamp():
            nonlocal archived_before
            archived_before = (self.output / "compiled.factory.yaml").read_bytes()
            stamped = self.data / "r60abd1.factory.yaml"
            stamped.write_bytes(stamped.read_bytes().replace(b"release_channel: alpha", b"release_channel: development"))

        code, _, _ = self._run(edit_stamp)
        summary = self._summary()
        self.assertEqual(summary["status"], "uncertain")
        self.assertTrue(summary["sourceModifiedDuringBuild"])
        self.assertFalse(summary["stampedConfigMatchesConsumed"])
        self.assertEqual((self.output / "compiled.factory.yaml").read_bytes(), archived_before)
        self.assertNotEqual((self.data / "r60abd1.factory.yaml").read_bytes(), archived_before)
        joined = "\n".join(summary["modifiedInputsDuringBuild"])
        self.assertIn("consumed stamped config changed", joined)



class SourceStateTests(unittest.TestCase):
    """T1: source-state is recorded by the real entry before any build work."""

    VERSION = "v1.2.0-alpha.9"

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.data = self.root / "data"
        self.output = self.root / "output"
        self.subprocess_calls = []
        self.deletions = []

    def _run_main(self, *extra_args, git_fails=False, status_text="", diff_text="", fail_compile=False):
        return BuilderMainTests._run_main(self, *extra_args, git_fails=git_fails,
                                          status_text=status_text, diff_text=diff_text,
                                          fail_compile=fail_compile)

    def test_source_state_recorded_with_identity_and_inputs(self):
        code, _, _ = self._run_main("--version", self.VERSION, "--run-id", "rid-1", "--skip-compile")
        self.assertEqual(code, 0)
        state = json.loads((self.output / "source-state.json").read_text(encoding="utf-8"))
        self.assertEqual(state["schemaVersion"], 1)
        self.assertEqual(state["runId"], "rid-1")
        self.assertEqual(state["version"], self.VERSION)
        self.assertEqual(state["channel"], "alpha")
        self.assertEqual(state["buildProfile"], "r60-daily")
        self.assertEqual(state["esphomeVersion"], builder.PINNED)
        self.assertEqual(state["git"]["head"], "a" * 40)
        self.assertEqual(state["git"]["status"], "clean")
        self.assertIn("scripts/build_r60_candidate.py", state["sourceInputs"])
        self.assertIn("tests/r60abd1-esp32c3.factory.yaml", state["sourceInputs"])
        self.assertGreater(state["sourceInputCount"], 0)
        # recorded hashes match the real files
        for rel, digest in state["sourceInputs"].items():
            self.assertEqual(digest, hashlib.sha256((builder.ROOT / rel).read_bytes()).hexdigest(), rel)

    def test_summary_links_source_state_and_stamped_config(self):
        code, _, _ = self._run_main("--version", self.VERSION, "--skip-compile")
        self.assertEqual(code, 0)
        summary = json.loads((self.output / "artifact-summary.json").read_text(encoding="utf-8"))
        state_bytes = (self.output / "source-state.json").read_bytes()
        stamped_bytes = (self.output / "compiled.factory.yaml").read_bytes()
        self.assertEqual(summary["sourceStateSha256"], hashlib.sha256(state_bytes).hexdigest())
        self.assertEqual(summary["stampedConfigSha256"], hashlib.sha256(stamped_bytes).hexdigest())
        self.assertTrue((self.output / "compiled.factory.yaml").is_file())
        self.assertIn('version: "' + self.VERSION + '"', stamped_bytes.decode(encoding="utf-8"))

    def test_git_failure_is_recorded_as_unknown(self):
        code, _, _ = self._run_main("--version", self.VERSION, "--skip-compile", git_fails=True)
        self.assertEqual(code, 0)
        state = json.loads((self.output / "source-state.json").read_text(encoding="utf-8"))
        self.assertEqual(state["git"]["status"], "unknown")
        self.assertEqual(state["git"]["head"], "unknown")
        self.assertIn("error", state["git"])
        summary = json.loads((self.output / "artifact-summary.json").read_text(encoding="utf-8"))
        self.assertEqual(summary["gitStatus"], "unknown")

    def test_dirty_tree_captures_patch_and_scope(self):
        status = " M scripts/build_r60_candidate.py\n M components/mmwave_host/mmwave_host.cpp\n"
        patch_text = "diff --git a/scripts/build_r60_candidate.py b/scripts/build_r60_candidate.py\n..."
        code, _, _ = self._run_main("--version", self.VERSION, "--skip-compile",
                                    status_text=status, diff_text=patch_text)
        self.assertEqual(code, 0)
        state = json.loads((self.output / "source-state.json").read_text(encoding="utf-8"))
        self.assertEqual(state["git"]["status"], "dirty")
        self.assertEqual(state["git"]["patchFile"], "source-dirty.patch")
        self.assertTrue((self.output / "source-dirty.patch").is_file())
        self.assertEqual((self.output / "source-dirty.patch").read_text(encoding="utf-8"), patch_text)
        joined = "\n".join(state["git"]["dirtyScopeFiles"])
        self.assertIn("scripts/build_r60_candidate.py", joined)
        self.assertIn("components/mmwave_host/mmwave_host.cpp", joined)
        summary = json.loads((self.output / "artifact-summary.json").read_text(encoding="utf-8"))
        self.assertTrue(summary["dirtyWorktree"])
        self.assertEqual(summary["gitStatus"], "dirty")

    def test_inputs_changed_during_build_marked_uncertain(self):
        probe_file = builder.ROOT / "tests/common/r60abd1_mwcp.yaml"
        original_bytes = probe_file.read_bytes()
        def touch_input():
            # Simulate an input changing while the run is in progress.
            # Byte-level append/restore only: write_text would translate newlines
            # and leave the real tree with changed line endings after cleanup.
            probe_file.write_bytes(original_bytes + b"\n# transient probe\n")
        self.addCleanup(lambda: probe_file.write_bytes(original_bytes))
        self._on_config = touch_input
        try:
            code, _, _ = self._run_main("--version", self.VERSION, "--skip-compile")
        finally:
            self._on_config = None
        self.assertEqual(code, 0)
        summary = json.loads((self.output / "artifact-summary.json").read_text(encoding="utf-8"))
        self.assertEqual(summary["status"], "uncertain")
        self.assertIn("tests/common/r60abd1_mwcp.yaml", summary["modifiedInputsDuringBuild"][0])
        state = json.loads((self.output / "source-state.json").read_text(encoding="utf-8"))
        # source-state still holds the pre-build hash, so the pair is reconcilable
        self.assertNotEqual(
            state["sourceInputs"]["tests/common/r60abd1_mwcp.yaml"],
            hashlib.sha256((builder.ROOT / "tests/common/r60abd1_mwcp.yaml").read_bytes()).hexdigest(),
        )


class RunIsolationTests(unittest.TestCase):
    """T2: every run is independent; historical outputs are never overwritten."""

    VERSION = "v1.2.0-alpha.8"

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.data = self.root / "data"
        self.output = self.root / "output"
        self.subprocess_calls = []
        self.deletions = []

    def _run_main(self, *extra_args, fail_compile=False):
        return BuilderMainTests._run_main(self, *extra_args, fail_compile=fail_compile)

    def test_existing_root_artifacts_are_refused(self):
        self.output.mkdir(parents=True)
        for name in ("artifact-summary.json", "compiled.factory.yaml", "source-state.json",
                     "compile.log", "config-r60.log", "source-dirty.patch"):
            with self.subTest(protected=name):
                sentinel = self.output / name
                sentinel.write_text("HISTORICAL", encoding="utf-8")
                code, _, message = self._run_main("--version", self.VERSION, "--skip-compile")
                self.assertEqual(code, 1)
                self.assertIn("already contains previous run artifact", message)
                self.assertEqual(sentinel.read_text(encoding="utf-8"), "HISTORICAL")
                self.assertEqual(self.deletions, [])

    def test_failed_compile_keeps_logs_and_writes_failed_summary(self):
        code, _, message = self._run_main("--version", self.VERSION, fail_compile=True)
        self.assertEqual(code, 1)
        self.assertIn("command failed (2)", message)
        summary = json.loads((self.output / "artifact-summary.json").read_text(encoding="utf-8"))
        self.assertEqual(summary["status"], "failed")
        self.assertEqual(summary["stage"], "compile_command")
        self.assertEqual(summary["exitCode"], 2)
        self.assertEqual(summary["version"], self.VERSION)
        self.assertEqual(summary["channel"], "alpha")
        self.assertTrue(summary["runId"])
        # logs produced before the failure are still there
        self.assertTrue((self.output / "config-bad.log").is_file())
        self.assertTrue((self.output / "config-r60.log").is_file())
        self.assertTrue((self.output / "config-ld2450.log").is_file())
        self.assertTrue((self.output / "source-state.json").is_file())
        # and no success-only fields are present
        self.assertNotIn("factorySha256", summary)

    def test_explicit_run_id_is_used(self):
        code, _, _ = self._run_main("--version", self.VERSION, "--skip-compile", "--run-id", "my-run-42")
        self.assertEqual(code, 0)
        summary = json.loads((self.output / "artifact-summary.json").read_text(encoding="utf-8"))
        state = json.loads((self.output / "source-state.json").read_text(encoding="utf-8"))
        self.assertEqual(summary["runId"], "my-run-42")
        self.assertEqual(state["runId"], "my-run-42")

    def test_default_run_id_is_timestamped(self):
        code, _, _ = self._run_main("--version", self.VERSION, "--skip-compile")
        self.assertEqual(code, 0)
        summary = json.loads((self.output / "artifact-summary.json").read_text(encoding="utf-8"))
        self.assertRegex(summary["runId"], r"^run-\d{8}-\d{6}$")


class StampRelocationTests(unittest.TestCase):
    """T2: the generated include resolves from any run-directory depth."""

    def test_stamp_include_resolves_from_nested_directory(self):
        with tempfile.TemporaryDirectory() as temp:
            deep = Path(temp) / "runs" / "2026-11-08" / "alpha" / "data"
            deep.mkdir(parents=True)
            destination = deep / "r60abd1.factory.yaml"
            channel = builder.stamp(destination, "v1.2.0-alpha.2")
            self.assertEqual(channel, "alpha")
            text = destination.read_text(encoding="utf-8")
            self.assertIn('version: "v1.2.0-alpha.2"', text)
            match = re.search(r"core: !include (\S+)", text)
            self.assertIsNotNone(match)
            resolved = (destination.parent / match.group(1)).resolve()
            self.assertTrue(resolved.is_file(), f"include target must exist: {resolved}")
            self.assertEqual(resolved, (builder.ROOT / "tests/r60abd1-esp32c3.yaml").resolve())

    def test_bad_copy_include_resolves_from_nested_directory(self):
        with tempfile.TemporaryDirectory() as temp:
            deep = Path(temp) / "x" / "y" / "z"
            deep.mkdir(parents=True)
            destination = deep / "bad-channel.yaml"
            builder.bad_copy(destination)
            text = destination.read_text(encoding="utf-8")
            self.assertIn("r60bad", text)
            match = re.search(r"path: (\S+)", text)
            self.assertIsNotNone(match)
            resolved = (destination.parent / match.group(1)).resolve()
            self.assertTrue((resolved / "__init__.py").is_file() or resolved.is_dir(),
                            f"components include must resolve: {resolved}")


if __name__ == "__main__":
    unittest.main()
