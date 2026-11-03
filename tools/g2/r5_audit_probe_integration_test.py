# -*- coding: utf-8 -*-
#!/usr/bin/env python3
"""R5 audit probe integration test - covers every probe from
tmp/g2-review-20261030-r5/audit.json through real entry paths.

Each test asserts a specific rejection reason or positive outcome,
never just "all inputs fail". Tests use fake transport/clock and
never access real serial ports, secrets, or network.

Probes covered:
  R3-A: config_out_of_range, config_invalid_polygon, config_invalid_areas,
        revision_unicode, revision_overlength, missing_request_op_id,
        actual_power_wrong_transaction
  R4-B: human_unconfirmed_mirrored_3ms_exit, human_explicit_unconfirmed_rejected
  R1-B: foreign_same_run_status, real_soak_racing_files
  R1-A: index_cross_mode_cycle, index_missing_raw_hash,
        index_missing_exact_path_uses_basename
"""

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))

import hardware_judges as hj  # noqa: E402
import build_evidence_index as bi  # noqa: E402

# R9-01: deterministic attempt identity shared by runner harnesses so
# imported phase fixtures are genuinely bound to the current fake attempt.
FIXED_ATTEMPT_ID = "human-0123456789abcdef"


class _FixedUUID:
    hex = "0123456789abcdef0123456789abcdef"


def _base_power_record(**overrides):
    """Build a valid power cut cycle record, allowing selective overrides."""
    rec = {
        "target_port": "COM9",
        "port": "COM9",
        "disconnect_observed": True,
        "reconnect_observed": True,
        "boot_before": "a" * 32,
        "boot_after": "b" * 32,
        "rev_before": "1",
        "rev_target": "2",
        "rev_recovered": "2",
        "config_before": {
            "install.x_cm": 0.0, "install.y_cm": 0.0, "install.z_cm": 200.0,
            "install.yaw_deg": 0.0, "install.pitch_deg": 0.0, "install.roll_deg": 0.0,
            "geometry.boundary_cm": None, "areas.definitions": [],
        },
        "config_target": {
            "install.x_cm": 100.0, "install.y_cm": 0.0, "install.z_cm": 200.0,
            "install.yaw_deg": 0.0, "install.pitch_deg": 0.0, "install.roll_deg": 0.0,
            "geometry.boundary_cm": None, "areas.definitions": [],
        },
        "config_recovered": {
            "install.x_cm": 100.0, "install.y_cm": 0.0, "install.z_cm": 200.0,
            "install.yaw_deg": 0.0, "install.pitch_deg": 0.0, "install.roll_deg": 0.0,
            "geometry.boundary_cm": None, "areas.definitions": [],
        },
        "commit_response": {
            "ok": True,
            "result": {
                "op_id": "test-op-123",
                "revision": "2",
                "persisted": True,
                "restart_required": False,
            }
        },
        "device_id_before": "r60-aabbccdd",
        "device_id_after": "r60-aabbccdd",
        "op_id": "test-op-123",
    }
    rec.update(overrides)
    return rec


def _default_valid_phases():
    return {
        "entry": {"confirmed": True, "start_ms": 0.0, "end_ms": 2000.0, "confirmed_at_ms": 2000.0},
        "still": {"confirmed": True, "start_ms": 2000.0, "end_ms": 4800.0, "confirmed_at_ms": 4800.0},
        "exit": {"confirmed": True, "start_ms": 5000.0, "end_ms": 17000.0, "confirmed_at_ms": 17000.0},
    }


def _base_human_records(n=30, exit_frames=5, exit_interval_ms=3000,
                        x_motion=True, mirror_room=False, full_phases=False):
    """Build telemetry records for human observation testing."""
    records = []
    present_count = n - exit_frames
    still_start = max(1, present_count // 2)
    for i in range(n):
        if i < present_count:
            presence_val = True
            if full_phases and i >= still_start:
                x_val = 24.0 if x_motion else 0.0
            else:
                x_val = (float(i) * 6.0 if full_phases else float(i)) if x_motion else 0.0
        else:
            presence_val = False
            x_val = 0.0

        local_cm = [x_val, 10.0, 100.0]
        if mirror_room:
            room_cm = [-x_val, -10.0, 100.0]
        else:
            room_cm = [x_val, 10.0, 100.0]

        if full_phases:
            bnd = "inside" if (i >= still_start or i < still_start // 2) else "outside"
        else:
            bnd = "inside"

        rec = {
            "source_seq": i + 1,
            "sample_ms": i * 200,
            "presence": {"value": presence_val, "quality": "valid"},
            "targets": [{
                "local_cm": local_cm,
                "room_cm": room_cm,
                "position_quality": "valid",
                "position_ms": i * 200,
                "boundary": bnd,
            }] if presence_val else [],
        }
        records.append(rec)
    base_ms = (n - exit_frames - 1) * 200 + 200
    for i in range(exit_frames):
        records[n - exit_frames + i]["sample_ms"] = base_ms + i * exit_interval_ms
    # R8-01A: the presence field carries its own sampling clock (production
    # mwcp_service emits presence.sample_ms); periodic fixture samples it
    # together with each frame.
    for rec in records:
        rec["presence"]["sample_ms"] = rec["sample_ms"]
    return records


class TestR3APowerCutConfigValidation(unittest.TestCase):
    """R3-A probes: config_out_of_range, config_invalid_polygon,
    config_invalid_areas, revision_unicode, revision_overlength,
    missing_request_op_id, actual_power_wrong_transaction."""

    def test_positive_baseline(self):
        """Baseline: a valid record with correct op_id passes."""
        rec = _base_power_record()
        verdict, passed, detail = hj.judge_power_cut_cycle(rec)
        self.assertTrue(passed, f"Expected pass, got {verdict}: {detail}")
        self.assertEqual(verdict, "COMMITTED_NEW_SAFE")

    def test_config_out_of_range_pitch_999(self):
        """config_out_of_range: pitch=999 exceeds [-90, 90]."""
        cfg_bad = {
            "install.x_cm": 0.0, "install.y_cm": 0.0, "install.z_cm": 200.0,
            "install.yaw_deg": 0.0, "install.pitch_deg": 999.0, "install.roll_deg": 0.0,
            "geometry.boundary_cm": None, "areas.definitions": [],
        }
        rec = _base_power_record(config_target=cfg_bad, config_recovered=cfg_bad)
        verdict, passed, detail = hj.judge_power_cut_cycle(rec)
        self.assertFalse(passed, f"pitch=999 must reject but got {verdict}")
        self.assertEqual(verdict, "INCOMPLETE_CONFIG_REJECTED")

    def test_config_invalid_polygon(self):
        """config_invalid_polygon: boundary=["bad"] must be rejected."""
        cfg_bad = {
            "install.x_cm": 0.0, "install.y_cm": 0.0, "install.z_cm": 200.0,
            "install.yaw_deg": 0.0, "install.pitch_deg": 0.0, "install.roll_deg": 0.0,
            "geometry.boundary_cm": ["bad"],
            "areas.definitions": [],
        }
        rec = _base_power_record(config_target=cfg_bad, config_recovered=cfg_bad)
        verdict, passed, detail = hj.judge_power_cut_cycle(rec)
        self.assertFalse(passed, f"boundary=['bad'] must reject but got {verdict}")
        self.assertEqual(verdict, "INCOMPLETE_CONFIG_REJECTED")

    def test_config_invalid_areas(self):
        """config_invalid_areas: areas=[null] must be rejected."""
        cfg_bad = {
            "install.x_cm": 0.0, "install.y_cm": 0.0, "install.z_cm": 200.0,
            "install.yaw_deg": 0.0, "install.pitch_deg": 0.0, "install.roll_deg": 0.0,
            "geometry.boundary_cm": None,
            "areas.definitions": [None],
        }
        rec = _base_power_record(config_target=cfg_bad, config_recovered=cfg_bad)
        verdict, passed, detail = hj.judge_power_cut_cycle(rec)
        self.assertFalse(passed, f"areas=[null] must reject but got {verdict}")
        self.assertEqual(verdict, "INCOMPLETE_CONFIG_REJECTED")

    def test_revision_unicode_arabic(self):
        """revision_unicode: Arabic digits must be rejected."""
        rec = _base_power_record(rev_target="\u0661\u0662", rev_recovered="\u0661\u0662")
        rec["commit_response"]["result"]["revision"] = "\u0661\u0662"
        verdict, passed, detail = hj.judge_power_cut_cycle(rec)
        self.assertFalse(passed, f"Arabic digits must reject but got {verdict}")
        self.assertEqual(verdict, "INVALID_REVISION_FORMAT")

    def test_revision_overlength_21_digits(self):
        """revision_overlength: 21-digit revision exceeds <=20 UTF-8 byte limit."""
        long_rev = "1" * 21
        rec = _base_power_record(rev_target=long_rev, rev_recovered=long_rev)
        rec["commit_response"]["result"]["revision"] = long_rev
        verdict, passed, detail = hj.judge_power_cut_cycle(rec)
        self.assertFalse(passed, f"21-digit rev must reject but got {verdict}")
        self.assertEqual(verdict, "INVALID_REVISION_FORMAT")

    def test_revision_20_digits_accepted(self):
        """Positive: 20-digit revision is exactly at the limit and should pass."""
        rev20 = "1" * 20
        rec = _base_power_record(rev_before="1", rev_target=rev20, rev_recovered=rev20)
        rec["commit_response"]["result"]["revision"] = rev20
        verdict, passed, detail = hj.judge_power_cut_cycle(rec)
        self.assertTrue(passed, f"20-digit rev should pass but got {verdict}: {detail}")

    def test_missing_request_op_id(self):
        """missing_request_op_id: no op_id in cycle record."""
        rec = _base_power_record()
        del rec["op_id"]
        verdict, passed, detail = hj.judge_power_cut_cycle(rec)
        self.assertFalse(passed, f"Missing op_id must reject but got {verdict}")
        self.assertEqual(verdict, "MISSING_REQUEST_OP_ID_REJECTED")

    def test_actual_power_wrong_transaction(self):
        """actual_power_wrong_transaction: ACK op_id != request op_id."""
        rec = _base_power_record()
        rec["op_id"] = "request-op-001"
        rec["commit_response"]["result"]["op_id"] = "different-op-999"
        verdict, passed, detail = hj.judge_power_cut_cycle(rec)
        self.assertFalse(passed, f"op_id mismatch must reject but got {verdict}")
        self.assertEqual(verdict, "OP_ID_MISMATCH_REJECTED")
        self.assertIn("different-op-999", detail)


class TestR4BHumanObservation(unittest.TestCase):
    """R4-B probes: human_unconfirmed_mirrored_3ms_exit,
    human_explicit_unconfirmed_rejected."""

    def test_positive_human_observation(self):
        """Full positive: confirmed, 10s+ exit, correct transform passes."""
        records = _base_human_records(
            n=30, exit_frames=5, exit_interval_ms=3000,
            x_motion=True, mirror_room=False, full_phases=True,
        )
        verdict, passed, summary = hj.judge_human_observation(
            records, user_action_confirmed=True, minimum_exit_duration_ms=10000,
            expected_installation=dict(TestR4BRealHumanRunner.INST),
            phases=_default_valid_phases(), require_structured_phases=True,
        )
        self.assertTrue(passed, f"Positive case should pass but got {verdict}: {summary}")
        self.assertEqual(verdict, "HUMAN_OBSERVE_PASS")

    def test_unconfirmed_defaults_to_rejected(self):
        """Missing user_action_confirmed defaults to None, rejected."""
        records = _base_human_records(n=30, exit_frames=5, exit_interval_ms=3000)
        verdict, passed, summary = hj.judge_human_observation(records)
        self.assertFalse(passed)
        self.assertEqual(verdict, "UNCONFIRMED_USER_ACTION_REJECTED")

    def test_explicit_false_confirmation_rejected(self):
        """human_explicit_unconfirmed_rejected: user_action_confirmed=False rejected."""
        records = _base_human_records(n=30, exit_frames=5, exit_interval_ms=3000)
        verdict, passed, summary = hj.judge_human_observation(
            records, user_action_confirmed=False, minimum_exit_duration_ms=10000,
        )
        self.assertFalse(passed)
        self.assertEqual(verdict, "UNCONFIRMED_USER_ACTION_REJECTED")

    def test_3ms_exit_duration_rejected(self):
        """Exit duration 3ms < 10000ms minimum."""
        records = _base_human_records(
            n=30, exit_frames=3, exit_interval_ms=1,
            x_motion=True, mirror_room=False,
        )
        verdict, passed, summary = hj.judge_human_observation(
            records, user_action_confirmed=True, minimum_exit_duration_ms=10000,
        )
        self.assertFalse(passed, f"3ms exit should fail but got {verdict}: {summary}")
        self.assertEqual(verdict, "SUSTAINED_EXIT_DURATION_INSUFFICIENT")

    def test_mirrored_room_coords_with_expected_installation(self):
        """Mirrored room coordinates contradict expected_installation."""
        records = _base_human_records(
            n=30, exit_frames=5, exit_interval_ms=3000,
            x_motion=True, mirror_room=True,
        )
        expected_inst = {
            "install.x_cm": 0.0, "install.y_cm": 0.0, "install.z_cm": 200.0,
            "install.yaw_deg": 0.0, "install.pitch_deg": 0.0, "install.roll_deg": 0.0,
        }
        verdict, passed, summary = hj.judge_human_observation(
            records, user_action_confirmed=True, minimum_exit_duration_ms=10000,
            expected_installation=expected_inst,
        )
        self.assertFalse(passed, f"Mirrored coords should fail but got {verdict}: {summary}")
        self.assertEqual(verdict, "COORDINATE_TRANSFORM_MISMATCH_REJECTED")

    def test_dict_input_with_confirmation(self):
        """Test dict input form with user_action_confirmed inside doc."""
        records = _base_human_records(
            n=30, exit_frames=5, exit_interval_ms=3000,
            x_motion=True, mirror_room=False, full_phases=True,
        )
        doc = {
            "telemetry_records": records,
            "user_action_confirmed": True,
            "minimum_exit_duration_ms": 10000,
            "phases": _default_valid_phases(),
            "expected_installation": dict(TestR4BRealHumanRunner.INST),
            "require_structured_phases": True,
        }
        verdict, passed, summary = hj.judge_human_observation(doc)
        self.assertTrue(passed, f"Dict positive should pass but got {verdict}: {summary}")
        self.assertEqual(verdict, "HUMAN_OBSERVE_PASS")

    def test_dict_input_without_confirmation_rejected(self):
        """Dict input with missing confirmation defaults to None, rejected."""
        records = _base_human_records(n=30, exit_frames=5, exit_interval_ms=3000)
        doc = {
            "telemetry_records": records,
            "minimum_exit_duration_ms": 10000,
        }
        verdict, passed, summary = hj.judge_human_observation(doc)
        self.assertFalse(passed)
        self.assertEqual(verdict, "UNCONFIRMED_USER_ACTION_REJECTED")


class TestR4BRealHumanRunner(unittest.TestCase):
    """R4-B through the REAL human_observe_runner.main()."""

    INST = {
        "install.x_cm": 0.0, "install.y_cm": 0.0, "install.z_cm": 200.0,
        "install.yaw_deg": 0.0, "install.pitch_deg": 0.0, "install.roll_deg": 0.0,
        "geometry.boundary_cm": [[-100.0, -100.0], [33.0, -100.0], [33.0, 100.0], [-100.0, 100.0]],
        "areas.definitions": [],
    }

    def _run_runner(self, records, confirm=True, min_exit_ms=10000, phases=None):
        import human_observe_runner as hor
        with tempfile.TemporaryDirectory(prefix="r5-hor-") as td:
            out_path = Path(td) / "human.jsonl"
            res_path = Path(td) / "human.result.json"
            events = [
                {"meta": {"code": hor.mwcp.CODE["TELEMETRY"]}, "payload": r}
                for r in records
            ]
            clock = [0.0]

            class FakeClient:
                boot_id = "c" * 32
                session_id = 1

                def call(self, name, payload=None, **kw):
                    if name == "DEVICE_INFO":
                        return {"ok": True, "result": {"device_id": "r60-test-01", "model": "R60ABD1"}}
                    if name == "CAPABILITIES_LIST":
                        return {
                            "ok": True,
                            "result": {
                                "items": [
                                    {"id": "presence", "UpdateMs": 200, "StaleAfterMs": 6000},
                                    {"id": "position.xy", "Units": "cm", "UpdateMs": 200, "StaleAfterMs": 6000},
                                ]
                            },
                        }
                    return {"ok": True, "result": {}}

                def ping(self):
                    return {"ok": True, "result": {}}

                def drain_events(self, duration_ms):
                    clock[0] += 20.0
                    # R9-01/R12 harness realism: the guided runner keeps
                    # draining inside a phase until the user confirms it, so
                    # a real still stage captures every frame up to
                    # departure.  Align the fake batches with the three
                    # guided phases: entry takes the first 10 frames, exit
                    # takes all remaining ABSENT frames, still keeps
                    # everything in between.
                    if not getattr(self, "_batches", None):
                        if not events:
                            return []
                        head = events[:10]
                        rest = events[10:]
                        exit_n = sum(
                            1 for ev in rest
                            if isinstance(ev.get("payload"), dict)
                            and isinstance(ev["payload"].get("presence"), dict)
                            and ev["payload"]["presence"].get("value") is False
                        )
                        mid = rest[:len(rest) - exit_n] if exit_n else rest
                        tail = rest[len(rest) - exit_n:] if exit_n else []
                        self._batches = [head, mid, tail]
                        del events[:]
                    return self._batches.pop(0) if self._batches else []

                def close(self):
                    pass

            argv = ["human_observe_runner", "--port", "COM9", "--seconds", "60",
                    "--out", str(out_path), "--min-exit-ms", str(min_exit_ms)]
            if confirm:
                argv.append("--confirm-user-actions")
            if phases is not None:
                # R9-01: imported phase files must be BOUND to this fake
                # attempt (device/boot/session from the fake client:
                # r60-test-01 / c*32 / 1; attempt UUID pinned below).
                pfile = Path(td) / "phases.json"
                pfile.write_text(json.dumps({
                    "attempt_id": FIXED_ATTEMPT_ID,
                    "session_id": 1,
                    "boot_id": "c" * 32,
                    "device_id": "r60-test-01",
                    "phases": phases,
                }), encoding="utf-8")
                argv.extend(["--phase-confirm-file", str(pfile)])

            with _NoRealIO(), \
                 mock.patch.object(sys, "argv", argv), \
                 mock.patch.object(hor, "robust_connect", return_value=FakeClient()), \
                 mock.patch.object(hor.run_g2, "read_all_config", return_value=(dict(self.INST), "1")), \
                 mock.patch.object(hor.time, "time", side_effect=lambda: clock[0]), \
                 mock.patch.object(hor.time, "sleep"), \
                 mock.patch.object(hor, "beep_phase"), \
                 mock.patch.object(hor, "beep_complete"), \
                 mock.patch.object(hor.winsound, "Beep", return_value=None), \
                 mock.patch.object(hor.uuid, "uuid4", return_value=_FixedUUID()), \
                 mock.patch("builtins.print"):
                rc = hor.main()
            res = json.loads(res_path.read_text(encoding="utf-8"))
            return rc, res

    def test_runner_positive_confirmed_passes(self):
        records = _base_human_records(n=30, exit_frames=5, exit_interval_ms=3000,
                                      x_motion=True, mirror_room=False, full_phases=True)
        rc, res = self._run_runner(records, confirm=True, phases=_default_valid_phases())
        self.assertEqual(rc, 0, res)
        self.assertEqual(res["status"], "pass")
        self.assertEqual(res["verdict"], "HUMAN_OBSERVE_PASS")
        self.assertTrue(res["user_action_confirmed"])

    def test_runner_unconfirmed_rejected(self):
        records = _base_human_records(n=30, exit_frames=5, exit_interval_ms=3000,
                                      x_motion=True, mirror_room=False)
        rc, res = self._run_runner(records, confirm=False)
        self.assertEqual(rc, 1)
        self.assertEqual(res["status"], "fail")
        self.assertEqual(res["verdict"], "UNCONFIRMED_USER_ACTION_REJECTED")

    def test_runner_mirrored_transform_rejected(self):
        records = _base_human_records(n=30, exit_frames=5, exit_interval_ms=3000,
                                      x_motion=True, mirror_room=True)
        rc, res = self._run_runner(records, confirm=True)
        self.assertEqual(rc, 1)
        self.assertEqual(res["status"], "fail")
        self.assertEqual(res["verdict"], "COORDINATE_TRANSFORM_MISMATCH_REJECTED")

    def test_runner_3ms_exit_rejected(self):
        records = _base_human_records(n=30, exit_frames=3, exit_interval_ms=1,
                                      x_motion=True, mirror_room=False)
        rc, res = self._run_runner(records, confirm=True)
        self.assertEqual(rc, 1)
        self.assertEqual(res["status"], "fail")
        self.assertEqual(res["verdict"], "SUSTAINED_EXIT_DURATION_INSUFFICIENT")


class TestR1AEvidenceIndex(unittest.TestCase):
    """R1-A probes driven through the REAL bi.build_index with content-bound
    reviews (result_sha256), exactly like the reviewer's probe: a review that
    says 'pass' must still be downgraded when the raw binding is broken."""

    def _write_run(self, root, name, mode=None, evidence="valid", raw_dir=None,
                   complete_meta: bool = False, duration_seconds: int = 7200):
        raw_dir = raw_dir or root
        raw = raw_dir / f"{name}.jsonl"
        if complete_meta:
            raw_lines = [
                json.dumps({"dir": "note", "event": "experiment_envelope", "experiment_id": name, "run_id": name}),
                json.dumps({
                    "dir": "tx",
                    "meta": {"code": 1, "request_id": 1, "session_id": 0},
                    "payload": {"nonce": "n1"},
                }),
                json.dumps({
                    "dir": "rx",
                    "meta": {"code": 1, "request_id": 1, "session_id": 1},
                    "payload": {
                        "ok": True,
                        "result": {"nonce": "n1", "boot_id": "a" * 32, "device_id": "board-A"},
                    },
                }),
            ]
            raw.write_text("\n".join(raw_lines) + "\n", encoding="utf-8")
        else:
            raw.write_text(json.dumps({"code": 1, "run": name}) + "\n")
        data = {
            "run_id": name, "status": "pass",
            "started": "2026-10-28T12:00:00+0000",
            "ended": "2026-10-28T12:01:00+0000",
            "judge_input": {"mode": mode} if mode else {},
        }
        if complete_meta:
            # Complete metadata (R7-03): device / scenario / tool / requested
            # duration.  NOTE (R8-02): this helper deliberately does NOT add
            # actual-coverage fields and does NOT derive `ended` from
            # `duration_seconds` -- requested values are not verifiable
            # coverage, and tests that exercise supersede admission must set
            # actual_duration_seconds / window fields EXPLICITLY.
            data["device_id"] = "board-A"
            data["board_id"] = "board-A"
            data["experiment_id"] = name
            data["scenario"] = "soak"
            data["duration_seconds"] = duration_seconds
            data["judge_input"] = {
                "mode": mode or "idle",
                "scenario": "soak",
                "tool_version": "g2-v1",
                "duration_seconds": duration_seconds,
            }
        if evidence == "valid":
            data["evidence"] = {"file": str(raw),
                                "sha256": hashlib.sha256(raw.read_bytes()).hexdigest()}
        elif evidence == "no_sha":
            data["evidence"] = {"file": str(raw)}
        elif isinstance(evidence, dict):
            data["evidence"] = evidence
        rp = root / f"{name}.result.json"
        rp.write_text(json.dumps(data))
        rsha = hashlib.sha256(rp.read_bytes()).hexdigest()
        if complete_meta and evidence == "valid":
            flash_src = root / f"{name}-flash.log.json"
            flash_event = {
                "seq": 1,
                "status": "success",
                "verify": "ok",
                "image_sha256": "b" * 64,
                "device_id": "board-A",
                "timestamp": "2026-10-28T11:00:00+00:00",
            }
            flash_src.write_text(json.dumps([flash_event]), encoding="utf-8")
            fsha = hashlib.sha256(flash_src.read_bytes()).hexdigest()
            manifest = {
                "schema": "g2-evidence-manifest-v1",
                "run_id": name,
                "experiment_id": name,
                "started": "2026-10-28T12:00:00+0000",
                "ended": "2026-10-28T12:01:00+0000",
                "boot_id_initial": "a" * 32,
                "board": {"device_id": "board-A"},
                "raw_file": str(raw),
                "raw_sha256": data["evidence"]["sha256"],
                "result_file": str(rp),
                "result_sha256": rsha,
                "flashed_image_sha256": "b" * 64,
                "flash_record": {
                    **flash_event,
                    "source": {"ref": str(flash_src), "sha256": fsha},
                },
            }
            (root / f"{name}.manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        return rp, rsha

    def _build(self, td, root, reviewed):
        idx = bi.build_index({"test": root}, Path(td) / "idx.json", reviewed,
                             bi.FIRMWARE_BATCHES, sources_snapshot={})
        return {r["run_id"]: r for r in idx["runs"]}

    def test_evidence_with_valid_hash_passes(self):
        """Positive: bound review + valid raw file/sha256 -> accepted 'pass'."""
        with tempfile.TemporaryDirectory(prefix="r5-idx-good-") as td:
            root = Path(td) / "ev"; root.mkdir()
            _, rsha = self._write_run(root, "r5-good")
            runs = self._build(td, root, {"r5-good": {"accepted_status": "pass",
                                                      "result_sha256": rsha}})
            self.assertEqual(runs["r5-good"]["accepted_status"], "pass",
                             runs["r5-good"].get("review_note"))

    def test_index_missing_raw_hash_rejected(self):
        """index_missing_raw_hash: bound 'pass' review but evidence lacks sha256."""
        with tempfile.TemporaryDirectory(prefix="r5-idx-hash-") as td:
            root = Path(td) / "ev"; root.mkdir()
            _, rsha = self._write_run(root, "r5-nosha", evidence="no_sha")
            runs = self._build(td, root, {"r5-nosha": {"accepted_status": "pass",
                                                       "result_sha256": rsha}})
            r = runs["r5-nosha"]
            self.assertEqual(r["accepted_status"], "pending_review")
            self.assertIn("missing valid 64-hex sha256", r["review_note"])

    def test_index_missing_exact_path_no_basename_fallback(self):
        """index_missing_exact_path_uses_basename: recorded absolute path does not
        exist; a same-basename file with the SAME hash sits next to the result.
        Must not be used as a fallback."""
        with tempfile.TemporaryDirectory(prefix="r5-idx-path-") as td:
            root = Path(td) / "ev"; root.mkdir()
            sibling = root / "r5-path.jsonl"
            sibling.write_text(json.dumps({"code": 1}) + "\n")
            ghost = Path(td) / "gone" / "r5-path.jsonl"
            _, rsha = self._write_run(root, "r5-path", evidence={
                "file": str(ghost),
                "sha256": hashlib.sha256(sibling.read_bytes()).hexdigest()})
            # _write_run overwrote the sibling with its own raw; restore the
            # hash relationship so a basename fallback WOULD verify.
            sibling.write_text(json.dumps({"code": 1}) + "\n")
            runs = self._build(td, root, {"r5-path": {"accepted_status": "pass",
                                                      "result_sha256": rsha}})
            r = runs["r5-path"]
            self.assertEqual(r["accepted_status"], "pending_review")
            self.assertIn("raw file missing", r["review_note"])

    def test_index_cross_mode_supersede_rejected(self):
        """index_cross_mode_cycle (as probed): idle<->stress mutual supersede.
        Neither may be accepted as superseded; mode mismatch is the reason."""
        with tempfile.TemporaryDirectory(prefix="r5-idx-xmode-") as td:
            root = Path(td) / "ev"; root.mkdir()
            _, s_idle = self._write_run(root, "g2-07-soak-idle", mode="idle")
            _, s_str = self._write_run(root, "g2-07-soak-stress", mode="stress")
            runs = self._build(td, root, {
                "g2-07-soak-idle": {"accepted_status": "superseded",
                                    "superseded_by": "g2-07-soak-stress",
                                    "result_sha256": s_idle},
                "g2-07-soak-stress": {"accepted_status": "superseded",
                                      "superseded_by": "g2-07-soak-idle",
                                      "result_sha256": s_str},
            })
            for rid in ("g2-07-soak-idle", "g2-07-soak-stress"):
                self.assertEqual(runs[rid]["accepted_status"], "pending_review", runs[rid])
                self.assertIsNone(runs[rid]["superseded_by"])
                self.assertIn("mode mismatch", runs[rid]["review_note"])

    def test_index_same_mode_cycle_detected(self):
        """Same-mode mutual supersede passes the mode check; graph cycle
        detection must still reject both."""
        with tempfile.TemporaryDirectory(prefix="r5-idx-cycle-") as td:
            root = Path(td) / "ev"; root.mkdir()
            _, sa = self._write_run(root, "g2-07-soak-idle-a", mode="idle")
            _, sb = self._write_run(root, "g2-07-soak-idle-b", mode="idle")
            runs = self._build(td, root, {
                "g2-07-soak-idle-a": {"accepted_status": "superseded",
                                      "superseded_by": "g2-07-soak-idle-b",
                                      "result_sha256": sa},
                "g2-07-soak-idle-b": {"accepted_status": "superseded",
                                      "superseded_by": "g2-07-soak-idle-a",
                                      "result_sha256": sb},
            })
            for rid in ("g2-07-soak-idle-a", "g2-07-soak-idle-b"):
                self.assertEqual(runs[rid]["accepted_status"], "pending_review", runs[rid])
                self.assertIsNone(runs[rid]["superseded_by"])
                self.assertIn("cyclic replacement", runs[rid]["review_note"])

    def test_valid_single_direction_supersede_accepted(self):
        """Positive: old superseded_by new, same mode, no cycle. R8-02: BOTH
        runs carry collector-measured actual coverage consistent with their
        started..ended windows (set explicitly here — the shared helper
        never fabricates actual fields)."""
        with tempfile.TemporaryDirectory(prefix="r5-idx-valid-") as td:
            root = Path(td) / "ev"; root.mkdir()
            so, _ = self._write_run(root, "g2-07-soak-idle-old", mode="idle", complete_meta=True, duration_seconds=60)
            sn, _ = self._write_run(root, "g2-07-soak-idle-new", mode="idle", complete_meta=True, duration_seconds=7200)
            # old: 60s measured coverage inside its own 60s window
            d_old = json.loads(so.read_text(encoding="utf-8"))
            d_old["actual_duration_seconds"] = 60
            d_old["judge_input"]["actual_duration_seconds"] = 60
            so.write_text(json.dumps(d_old), encoding="utf-8")
            # new: 7200s measured coverage; window widened to match
            d_new = json.loads(sn.read_text(encoding="utf-8"))
            d_new["actual_duration_seconds"] = 7200
            d_new["judge_input"]["actual_duration_seconds"] = 7200
            d_new["ended"] = "2026-10-28T14:00:00+0000"
            sn.write_text(json.dumps(d_new), encoding="utf-8")
            # re-bind content hashes (result_sha256 in manifest + reviews)
            for rp in (so, sn):
                mp = rp.with_name(rp.name.replace(".result.json", ".manifest.json"))
                m = json.loads(mp.read_text(encoding="utf-8"))
                m["result_sha256"] = hashlib.sha256(rp.read_bytes()).hexdigest()
                m["ended"] = json.loads(rp.read_text(encoding="utf-8"))["ended"]
                mp.write_text(json.dumps(m), encoding="utf-8")
            so_sha = hashlib.sha256(so.read_bytes()).hexdigest()
            runs = self._build(td, root, {
                "g2-07-soak-idle-old": {"accepted_status": "superseded",
                                        "superseded_by": "g2-07-soak-idle-new",
                                        "result_sha256": so_sha},
                "g2-07-soak-idle-new": {"accepted_status": "pass",
                                        "result_sha256": hashlib.sha256(sn.read_bytes()).hexdigest()},
            })
            self.assertEqual(runs["g2-07-soak-idle-old"]["accepted_status"], "superseded",
                             runs["g2-07-soak-idle-old"])
            self.assertEqual(runs["g2-07-soak-idle-old"]["superseded_by"], "g2-07-soak-idle-new")
            self.assertEqual(runs["g2-07-soak-idle-new"]["accepted_status"], "pass")


class _NoRealIO:
    """Context: real Client / secrets / serial must never be reached."""

    def __init__(self):
        self.attempts = []

    def __enter__(self):
        import run_g2 as rg
        import mwcp
        self.attempts = []

        def _blocked_client(*a, **kw):
            self.attempts.append(("mwcp.Client", a, kw))
            raise AssertionError("real Client constructed")

        self._p = [
            mock.patch.object(mwcp, "Client", side_effect=_blocked_client),
            mock.patch.object(rg, "load_secrets", return_value=({}, [])),
        ]
        for p in self._p:
            p.start()
        return self

    def __exit__(self, *exc):
        for p in reversed(self._p):
            p.stop()
        return False


def _run_main(argv, subcommand_name, fn, evidence_dir):
    import contextlib
    import io
    import run_g2 as rg
    out, err = io.StringIO(), io.StringIO()
    with mock.patch.object(sys, "argv", argv), \
         mock.patch.dict(rg.SUBCOMMANDS, {subcommand_name: fn}), \
         mock.patch.object(rg, "EVIDENCE_DIR", evidence_dir), \
         contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        rc = rg.main()
    return rc, out.getvalue(), err.getvalue()


class TestR1BOutputOwnership(unittest.TestCase):
    """R1-B probes through the REAL main() and REAL cmd_soak."""

    def setUp(self):
        self._td = tempfile.TemporaryDirectory(prefix="r5-r1b-")
        self.td = Path(self._td.name)
        self.evdir = self.td / "evidence-default"
        self.evdir.mkdir()

    def tearDown(self):
        self._td.cleanup()

    # -- main(): foreign file with identical run_id/status ---------------
    def test_foreign_same_run_status_main_exit1(self):
        """foreign_same_run_status: a foreign result with the SAME run_id and
        status appears after preflight. main must exit 1, leave the foreign
        bytes untouched and write a separate diagnostic."""
        raw = self.td / "probe.jsonl"
        res = self.td / "probe.result.json"
        foreign = json.dumps({"run_id": "fixture-run", "status": "pass",
                              "evidence": {"file": "foreign", "sha256": "0" * 64}}).encode()

        def sub(args):
            res.write_bytes(foreign)  # race: appears after the preflight
            return {"run_id": "fixture-run", "status": "pass",
                    "evidence": {"file": str(raw), "sha256": "1" * 64}}

        with _NoRealIO():
            rc, out, _ = _run_main(["run_g2", "probe", "--port", "FIXTURE", "--out", str(raw)],
                                   "probe", sub, self.evdir)
        self.assertEqual(rc, 1)
        self.assertEqual(res.read_bytes(), foreign, "foreign result modified")
        diags = list(self.td.glob("probe.collision-*.diag.json"))
        self.assertEqual(len(diags), 1, out)
        d = json.loads(diags[0].read_text(encoding="utf-8"))
        self.assertEqual(d["reason"], "foreign_result_not_owned")
        self.assertTrue(d["not_acceptance_evidence"])

    def test_claimed_path_but_hash_differs_rejected(self):
        """A subcommand that claims the path but whose recorded hash does not
        match the bytes on disk (file replaced) is not the owner."""
        raw = self.td / "claim.jsonl"
        res = self.td / "claim.result.json"

        def sub(args):
            res.write_text(json.dumps({"run_id": "r", "status": "pass"}), encoding="utf-8")
            sha = hashlib.sha256(res.read_bytes()).hexdigest()
            res.write_text(json.dumps({"run_id": "r", "status": "pass", "x": 1}), encoding="utf-8")
            return {"run_id": "r", "status": "pass", "evidence": {},
                    "_finalized_result_path": str(res.resolve()),
                    "_finalized_result_sha": sha}

        replaced = None
        with _NoRealIO():
            rc, _, _ = _run_main(["run_g2", "probe", "--port", "FIXTURE", "--out", str(raw)],
                                 "probe", sub, self.evdir)
            replaced = res.read_text(encoding="utf-8")
        self.assertEqual(rc, 1)
        self.assertIn('"x": 1', replaced)

    def test_owned_finalize_exit0(self):
        """Positive: subcommand x-creates its result and records path+hash."""
        raw = self.td / "own.jsonl"
        res = self.td / "own.result.json"

        def sub(args):
            body = {"run_id": "own", "status": "pass", "evidence": {}}
            with res.open("x", encoding="utf-8") as f:
                f.write(json.dumps(body))
            body["_finalized_result_path"] = str(res.resolve())
            body["_finalized_result_sha"] = hashlib.sha256(res.read_bytes()).hexdigest()
            return body

        with _NoRealIO():
            rc, _, _ = _run_main(["run_g2", "probe", "--port", "FIXTURE", "--out", str(raw)],
                                 "probe", sub, self.evdir)
        self.assertEqual(rc, 0)
        self.assertEqual(list(self.td.glob("*.diag.json")), [])
        self.assertEqual(list(self.evdir.glob("*.result.json")), [])

    # -- real cmd_soak ---------------------------------------------------
    def _soak(self, inject_race):
        import mwcp
        import soak_collector_integration_test as sct
        script = []
        for i in range(6):
            script.append(("resp", {"ok": True, "result": {
                "uptime_ms": 10000 * i, "radar_link": "healthy",
                "counters": {"rx_frames": i, "logs_dropped": 0}}}))
        script.append(("resp", {"ok": True, "result": {
            "state": "disconnected", "ssid": "", "ip": None, "rssi_dbm": None}}))
        injected = {}
        orig_close = mwcp.EvidenceWriter.close

        def racing_close(self_ev, *a, **kw):
            summary = orig_close(self_ev, *a, **kw)
            if inject_race and not injected:
                base = str(self_ev.path)[:-6]
                for suffix, body in ((".result.json", b'{"foreign":"result"}'),
                                     (".manifest.json", b'{"foreign":"manifest"}')):
                    p = Path(base + suffix)
                    p.write_bytes(body)
                    injected[p] = body
            return summary

        with _NoRealIO(), mock.patch.object(mwcp.EvidenceWriter, "close", racing_close):
            outcome, holder = sct.run_soak(script, seconds=60, mode="idle")
        return outcome, holder, injected

    def test_real_soak_racing_files_preserved(self):
        """real_soak_racing_files: foreign result AND manifest appear while the
        real cmd_soak is finalizing. Both must survive byte-for-byte, the run
        fails, and main() then refuses with a separate diagnostic."""
        outcome, holder, injected = self._soak(inject_race=True)
        self.assertEqual(len(injected), 2)
        self.assertEqual(outcome["status"], "fail")
        self.assertNotIn("_finalized_result_path", outcome)
        joined = " ".join(outcome.get("failures", []))
        self.assertIn("result_write_failure", joined)
        self.assertIn("manifest_write_failure", joined)
        for p, body in injected.items():
            self.assertEqual(p.read_bytes(), body, f"{p.name} overwritten")

        with _NoRealIO():
            rc, _, _ = _run_main(["run_g2", "soak", "--port", "FAKE"], "soak",
                                 lambda args: outcome, self.evdir)
        self.assertEqual(rc, 1)
        for p, body in injected.items():
            self.assertEqual(p.read_bytes(), body, f"{p.name} overwritten by main")
        raw_dir = holder["path"].parent
        self.assertEqual(len(list(raw_dir.glob("*.collision-*.diag.json"))), 1)
        self.assertEqual(list(self.evdir.glob("*.result.json")), [],
                         "main wrote a second result elsewhere")

    def test_real_soak_default_path_single_owned_result(self):
        """Positive (no --out): real cmd_soak owns the result beside its raw;
        main recognizes it and writes no second result under EVIDENCE_DIR."""
        outcome, holder, _ = self._soak(inject_race=False)
        res = Path(outcome["_finalized_result_path"])
        self.assertTrue(res.is_file())
        before = res.read_bytes()
        with _NoRealIO():
            rc, _, _ = _run_main(["run_g2", "soak", "--port", "FAKE"], "soak",
                                 lambda args: outcome, self.evdir)
        self.assertEqual(rc, 0 if outcome["status"] == "pass" else 1)
        self.assertEqual(res.read_bytes(), before)
        self.assertEqual(list(self.evdir.glob("*.result.json")), [])
        self.assertEqual(list(res.parent.glob("*.diag.json")), [])
        self.assertEqual(len(list(res.parent.glob("*.result.json"))), 1)


class TestR3ARealRunCycle(unittest.TestCase):
    """R3-A actual_power_wrong_transaction through the REAL run_cycle: the
    runner generates op_id, sends it in CONFIG_COMMIT, and the judge must
    compare it with the ACK. Serial/port/sleep/beep are all faked."""

    BASE = {
        "install.x_cm": 100.0, "install.y_cm": 0.0, "install.z_cm": 200.0,
        "install.yaw_deg": 0.0, "install.pitch_deg": 0.0, "install.roll_deg": 0.0,
        "geometry.boundary_cm": None, "areas.definitions": [],
    }

    def _run(self, ack_mode="echo", recovered_override=None):
        import power_cut_runner as pcr
        sent = {}

        class FakeClient:
            boot_id = "a" * 32

            def soft_call(self, name, *a, **kw):
                assert name == "DEVICE_INFO"
                return {"ok": True, "result": {"device_id": "r60-aabbccdd"}}

            def call(self, name, payload=None, **kw):
                assert name == "CONFIG_COMMIT", name
                sent.update(payload)
                res = {"op_id": payload["op_id"], "revision": "6",
                       "persisted": True, "restart_required": False}
                if ack_mode == "wrong_op":
                    res["op_id"] = "00000000-0000-0000-0000-000000000000"
                elif ack_mode == "missing_field":
                    del res["restart_required"]
                return {"ok": True, "result": res}

            def close(self):
                pass

        def fake_read_after(port, evidence, max_tries=5):
            cfg = dict(self.BASE)
            cfg.update(sent["changes"])
            if recovered_override:
                cfg.update(recovered_override)
            return cfg, "6", "b" * 32, "r60-aabbccdd"

        evidence = mock.MagicMock()
        with _NoRealIO(), \
             mock.patch.object(pcr, "robust_connect", return_value=FakeClient()), \
             mock.patch.object(pcr, "robust_connect_and_read", side_effect=fake_read_after), \
             mock.patch.object(pcr.run_g2, "read_all_config", return_value=(dict(self.BASE), "5")), \
             mock.patch.object(pcr, "wait_for_port", return_value=True), \
             mock.patch.object(pcr, "beep_unplug"), mock.patch.object(pcr, "beep_plug"), \
             mock.patch.object(pcr, "beep_success"), \
             mock.patch.object(pcr.time, "sleep"), \
             mock.patch("builtins.print"):
            rec = pcr.run_cycle("COM9", 1, evidence)
        return rec, sent

    def test_echoed_op_id_passes(self):
        rec, sent = self._run("echo")
        self.assertTrue(rec["passed"], rec["detail"])
        self.assertEqual(rec["verdict"], "COMMITTED_NEW_SAFE")
        self.assertEqual(rec["op_id"], sent["op_id"])
        self.assertEqual(rec["commit_response"]["result"]["op_id"], sent["op_id"])

    def test_wrong_ack_op_id_rejected(self):
        rec, sent = self._run("wrong_op")
        self.assertFalse(rec["passed"])
        self.assertEqual(rec["verdict"], "OP_ID_MISMATCH_REJECTED")
        self.assertEqual(rec["op_id"], sent["op_id"])

    def test_ack_missing_required_field_rejected(self):
        rec, _ = self._run("missing_field")
        self.assertFalse(rec["passed"])
        self.assertEqual(rec["verdict"], "INVALID_ACK_STRUCTURE_REJECTED")

    def test_recovered_out_of_range_rejected(self):
        rec, _ = self._run("echo", recovered_override={"install.pitch_deg": 999.0})
        self.assertFalse(rec["passed"])
        self.assertEqual(rec["verdict"], "INCOMPLETE_CONFIG_REJECTED")


class TestConfigValidation(unittest.TestCase):
    """Direct validation of is_valid_complete_config and is_valid_revision_string."""

    def test_valid_config(self):
        cfg = {
            "install.x_cm": 0.0, "install.y_cm": 0.0, "install.z_cm": 200.0,
            "install.yaw_deg": 0.0, "install.pitch_deg": 0.0, "install.roll_deg": 0.0,
            "geometry.boundary_cm": None, "areas.definitions": [],
        }
        self.assertTrue(hj.is_valid_complete_config(cfg))

    def test_valid_config_with_boundary_and_areas(self):
        cfg = {
            "install.x_cm": 100.0, "install.y_cm": -50.0, "install.z_cm": 300.0,
            "install.yaw_deg": 45.0, "install.pitch_deg": -30.0, "install.roll_deg": 10.0,
            "geometry.boundary_cm": [[0, 0], [100, 0], [100, 100]],
            "areas.definitions": [
                {"slot": 0, "enabled": True, "name": "zone1",
                 "points_cm": [[0, 0], [50, 0], [50, 50], [0, 50]]},
            ],
        }
        self.assertTrue(hj.is_valid_complete_config(cfg))

    def test_z_below_minimum_rejected(self):
        cfg = {
            "install.x_cm": 0.0, "install.y_cm": 0.0, "install.z_cm": 10.0,
            "install.yaw_deg": 0.0, "install.pitch_deg": 0.0, "install.roll_deg": 0.0,
            "geometry.boundary_cm": None, "areas.definitions": [],
        }
        self.assertFalse(hj.is_valid_complete_config(cfg))

    def test_z_above_maximum_rejected(self):
        cfg = {
            "install.x_cm": 0.0, "install.y_cm": 0.0, "install.z_cm": 700.0,
            "install.yaw_deg": 0.0, "install.pitch_deg": 0.0, "install.roll_deg": 0.0,
            "geometry.boundary_cm": None, "areas.definitions": [],
        }
        self.assertFalse(hj.is_valid_complete_config(cfg))

    def test_boundary_not_list_rejected(self):
        cfg = {
            "install.x_cm": 0.0, "install.y_cm": 0.0, "install.z_cm": 200.0,
            "install.yaw_deg": 0.0, "install.pitch_deg": 0.0, "install.roll_deg": 0.0,
            "geometry.boundary_cm": "bad", "areas.definitions": [],
        }
        self.assertFalse(hj.is_valid_complete_config(cfg))

    def test_boundary_two_points_rejected(self):
        cfg = {
            "install.x_cm": 0.0, "install.y_cm": 0.0, "install.z_cm": 200.0,
            "install.yaw_deg": 0.0, "install.pitch_deg": 0.0, "install.roll_deg": 0.0,
            "geometry.boundary_cm": [[0, 0], [1, 1]], "areas.definitions": [],
        }
        self.assertFalse(hj.is_valid_complete_config(cfg))

    def test_areas_none_item_rejected(self):
        cfg = {
            "install.x_cm": 0.0, "install.y_cm": 0.0, "install.z_cm": 200.0,
            "install.yaw_deg": 0.0, "install.pitch_deg": 0.0, "install.roll_deg": 0.0,
            "geometry.boundary_cm": None, "areas.definitions": [None],
        }
        self.assertFalse(hj.is_valid_complete_config(cfg))

    def test_areas_slot_out_of_range_rejected(self):
        cfg = {
            "install.x_cm": 0.0, "install.y_cm": 0.0, "install.z_cm": 200.0,
            "install.yaw_deg": 0.0, "install.pitch_deg": 0.0, "install.roll_deg": 0.0,
            "geometry.boundary_cm": None,
            "areas.definitions": [
                {"slot": 5, "enabled": True, "name": "bad", "points_cm": [[0, 0], [1, 1]]},
            ],
        }
        self.assertFalse(hj.is_valid_complete_config(cfg))

    def test_revision_ascii_digits_valid(self):
        self.assertTrue(hj.is_valid_revision_string("123"))
        self.assertTrue(hj.is_valid_revision_string("1"))
        self.assertTrue(hj.is_valid_revision_string("0"))
        self.assertTrue(hj.is_valid_revision_string("1" * 20))

    def test_revision_arabic_rejected(self):
        self.assertFalse(hj.is_valid_revision_string("\u0661\u0662\u0663"))

    def test_revision_fullwidth_rejected(self):
        self.assertFalse(hj.is_valid_revision_string("\uff10\uff11\uff12"))

    def test_revision_21_bytes_rejected(self):
        self.assertFalse(hj.is_valid_revision_string("1" * 21))

    def test_revision_empty_rejected(self):
        self.assertFalse(hj.is_valid_revision_string(""))

    def test_revision_non_string_rejected(self):
        self.assertFalse(hj.is_valid_revision_string(123))


if __name__ == "__main__":
    unittest.main()
