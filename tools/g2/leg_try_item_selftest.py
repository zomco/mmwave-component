#!/usr/bin/env python3
"""Offline stub tests for the REAL leg_driver2.try_item and environment key
(r2 review G2-R3-A/B). Device reset, bank persistence and the attempt log
are replaced by in-memory stubs; the actual try_item / environment_key code
runs unchanged. No serial port, no device.

Covers:
A1 first-attempt success executes once, zero resets, returns True
A2 failure path runs all attempts and returns False, every attempt logged
A3 exception path is logged and traceable
A4 a later success never erases an earlier recorded failure
B1 full identical environment reuses the bank (fn never runs)
B2 same image but changed runner/client/source re-runs
B3 missing identity (incomplete manifest) forbids reuse entirely
B4 run_id differs but the stable key matches -> reuse allowed
"""

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import leg_driver2 as ld  # noqa: E402


class Stubs:
    def __init__(self):
        self.resets = 0
        self.fn_calls = 0
        self._saved_banks = []

    def reset_device(self):
        self.resets += 1

    def bank_save(self, bank):
        self._saved_banks.append(json.loads(json.dumps(bank)))


def main() -> int:
    failures = []

    def expect(name, ok, detail=""):
        print(f"[{'PASS' if ok else 'FAIL'}] {name} {detail}")
        if not ok:
            failures.append(name)

    with tempfile.TemporaryDirectory() as td:
        ld.STATE = Path(td) / "bank.json"
        ld.ATTEMPTS = Path(td) / "attempts.jsonl"
        ld.PENDING_OPS = Path(td) / "pending-ops.jsonl"
        ld.EVIDENCE = Path(td)  # flash-log lookup stays inside the sandbox
        # sandbox flash-log carrying the current build image SHA so the
        # offline tests exercise the full (complete) identity path
        ld.TARGET_DEVICE_ID = "dc:da:0c:f8:f2:74"
        env0 = ld.environment()
        # structured flash record (r3c): JSON with status/image/board
        (Path(td) / "flash-log-r2.txt").write_text(
            json.dumps({"status": "success",
                        "image_sha256": env0.get("image_sha256"),
                        "board_id": "dc:da:0c:f8:f2:74", "seq": 0,
                        "verify": "ok",
                        "timestamp": "2026-10-27T00:00:00Z"}) + chr(10),
            encoding="utf-8")
        ld.ENV = None  # recompute with the sandbox flash-log in place
        s = Stubs()
        ld.reset_device = s.reset_device
        ld.bank_save = s.bank_save

        # A1: first-attempt success -> one execution, zero resets, True
        def fn_ok():
            s.fn_calls += 1
            return True, "ok"

        bank = {}
        rc = ld.try_item(bank, "item_x", fn_ok)
        expect("A1 success runs once", s.fn_calls == 1 and s.resets == 0 and rc is True,
               f"fn={s.fn_calls} resets={s.resets} rc={rc}")

        # A2/A3: failure + exception paths log every attempt and return False
        s.fn_calls = 0

        def fn_fail():
            s.fn_calls += 1
            return False, f"fail #{s.fn_calls}"

        rc = ld.try_item(bank, "item_y", fn_fail, attempts=3)
        lines = [json.loads(l) for l in ld.ATTEMPTS.read_text(encoding="utf-8").splitlines()]
        y_lines = [l for l in lines if l["item"] == "item_y"]
        expect("A2 failures run all attempts, logged, False",
               s.fn_calls == 3 and rc is False and len(y_lines) == 3
               and all(l["status"] == "fail" for l in y_lines),
               f"fn={s.fn_calls} rc={rc} logged={len(y_lines)}")
        expect("A2 failure attempts reset between tries", s.resets == 3, f"resets={s.resets}")

        def fn_raise():
            raise RuntimeError("boom")

        rc = ld.try_item(bank, "item_z", fn_raise, attempts=2)
        lines = [json.loads(l) for l in ld.ATTEMPTS.read_text(encoding="utf-8").splitlines()]
        z_lines = [l for l in lines if l["item"] == "item_z"]
        expect("A3 exceptions traceable", rc is False and len(z_lines) == 2
               and all(l["status"] == "exception" and "boom" in l["detail"] for l in z_lines))

        # A4: a later success must not erase the recorded failure
        rc = ld.try_item(bank, "item_y", fn_ok)
        log_text = ld.ATTEMPTS.read_text(encoding="utf-8")
        fail_lines = log_text.count('"status": "fail"')
        expect("A4 failure survives a later success", rc is True and fail_lines >= 3,
               f"rc={rc} fail_records={fail_lines}")

        # B1: identical full environment reuses (fn never runs)
        s.fn_calls = 0
        key = ld.environment_key()
        env_backup = json.loads(json.dumps(ld.ENV))  # deep snapshot for restore
        expect("B1 sanity: environment key is a full sha256",
               isinstance(key, str) and len(key) == 64, f"key={str(key)[:16]}..")
        bank2 = {"item_x": {"pass": True, "env": key}}
        rc = ld.try_item(bank2, "item_x", fn_ok)
        expect("B1 identical environment reuses without executing",
               rc is True and s.fn_calls == 0, f"rc={rc} fn={s.fn_calls}")

        # B2: same image, changed runner -> must re-run
        ld.ENV["runner"] = "0" * 64
        new_key = ld.environment_key()
        bank3 = {"item_x": {"pass": True, "env": key}}
        s.fn_calls = 0
        rc = ld.try_item(bank3, "item_x", fn_ok)
        expect("B2 changed runner re-runs", rc is True and s.fn_calls == 1 and new_key != key,
               f"fn={s.fn_calls}")
        ld.ENV["runner"] = env_backup["runner"]

        # B2b: same image, changed profile -> must re-run
        ld.ENV["profile"] = "1" * 64
        bank4 = {"item_x": {"pass": True, "env": key}}
        s.fn_calls = 0
        rc = ld.try_item(bank4, "item_x", fn_ok)
        expect("B2b changed profile re-runs", rc is True and s.fn_calls == 1, f"fn={s.fn_calls}")
        ld.ENV["profile"] = env_backup["profile"]

        # B3: incomplete identity forbids reuse entirely
        ld.ENV["complete"] = False
        ld.ENV["missing"] = ["image_sha256"]
        bank5 = {"item_x": {"pass": True, "env": "whatever"}}
        s.fn_calls = 0
        rc = ld.try_item(bank5, "item_x", fn_ok)
        expect("B3 incomplete identity forbids reuse", rc is False and s.fn_calls == 0,
               f"rc={rc} fn={s.fn_calls}")
        ld.ENV["complete"] = env_backup["complete"]
        ld.ENV["missing"] = env_backup["missing"]

        # B4: run_id is not part of the stable key. The manifest content at
        # this point equals the B1 baseline (all mutations restored), so the
        # key must be identical when only run_id changes.
        key_now = ld.environment_key()
        expect("B4 precondition: restored env matches B1 key", key_now == key,
               f"{str(key_now)[:12]} vs {str(key)[:12]}")
        saved_run = ld.RUN_ID
        ld.RUN_ID = "different-run"
        key2 = ld.environment_key()
        expect("B4 run_id excluded from stable key", key2 == key_now,
               f"{str(key2)[:12]} vs {str(key_now)[:12]}")
        ld.RUN_ID = saved_run

        # --- G2-R3-02 combined chain tests: real try_item wrapping real
        # commit_with_query. Only the device, persistence and reset are
        # stubbed; the driver and helper run for real. --------------------
        class FakeSession:
            """Scripted device: records every request; actions per call."""

            def __init__(self, actions):
                self.actions = list(actions)
                self.calls = []  # (name, op_id)

            def call(self, name, payload=None, **kw):
                op_id = (payload or {}).get("op_id")
                self.calls.append({"name": name, "op_id": op_id})
                action = self.actions.pop(0) if self.actions else "timeout"
                if action == "timeout":
                    raise TimeoutError(f"{name} (request_id=?) no response")
                if action == "unknown_error":
                    raise RuntimeError("connection gone")
                return action

        def commit_fn(sess, changes):
            return lambda: ld.commit_with_query(sess, "chain_item", "rev1", changes)

        # C1 (the r3 review's exact counterexample): every request times
        # out. Expected: UNKNOWN stops the chain - exactly ONE op_id, ONE
        # CONFIG_COMMIT + ONE COMMIT_STATUS, ZERO resets, rc False, one
        # attempt with status unknown.
        s = Stubs()
        ld.reset_device = s.reset_device
        sess = FakeSession([])
        bank = {}
        rc = ld.try_item(bank, "chain_item", commit_fn(sess, {"install.x_cm": 1.0}))
        ops = [json.loads(l) for l in ld.PENDING_OPS.read_text(encoding="utf-8").splitlines()]
        commits = [c for c in sess.calls if c["name"] == "CONFIG_COMMIT"]
        statuses = [c for c in sess.calls if c["name"] == "COMMIT_STATUS"]
        attempts = [json.loads(l) for l in ld.ATTEMPTS.read_text(encoding="utf-8").splitlines()
                    if json.loads(l)["item"] == "chain_item"]
        expect("C1 all-timeout: one op_id only",
               len(ops) == 1 and len(commits) == 1 and commits[0]["op_id"] == ops[0]["op_id"],
               f"ops={len(ops)} commits={len(commits)}")
        expect("C1 COMMIT_STATUS queried with the SAME op_id",
               len(statuses) == 1 and statuses[0]["op_id"] == ops[0]["op_id"],
               f"statuses={len(statuses)}")
        expect("C1 no reset on unknown, chain stopped",
               s.resets == 0 and rc is False and len(attempts) == 1
               and attempts[0]["status"] == "unknown",
               f"resets={s.resets} rc={rc} attempts={len(attempts)}")
        expect("C1 bank marks outcome unknown (never auto-skipped)",
               bank.get("chain_item", {}).get("outcome") == "unknown"
               and bank.get("chain_item", {}).get("pass") is False)

        # C2: lost response, COMMIT_STATUS found=true -> success resolved
        sess = FakeSession([
            "timeout",
            {"ok": True, "result": {"found": True, "revision": "41", "current_revision": "41"}},
        ])
        ok, detail = ld.commit_with_query(sess, "c2", "rev1", {"install.x_cm": 2.0})
        names = [c["name"] for c in sess.calls]
        expect("C2 found=true resolves success via COMMIT_STATUS",
               ok is True and names == ["CONFIG_COMMIT", "COMMIT_STATUS"],
               f"detail={detail[:70]}")

        # C3: found=false must stay UNKNOWN (replay cache eviction is
        # indistinguishable from never-executed per the protocol contract)
        sess = FakeSession([
            "timeout",
            {"ok": True, "result": {"found": False, "revision": None, "current_revision": "41"}},
        ])
        raised_unknown = False
        try:
            ld.commit_with_query(sess, "c3", "rev1", {"install.x_cm": 3.0})
        except ld.UnknownOutcome:
            raised_unknown = True
        expect("C3 found=false stays UNKNOWN (eviction ambiguity)",
               raised_unknown)

        # C4: COMMIT_STATUS with missing fields -> UNKNOWN
        sess = FakeSession(["timeout", {"ok": True, "result": {}}])
        raised_unknown = False
        try:
            ld.commit_with_query(sess, "c4", "rev1", {"install.x_cm": 4.0})
        except ld.UnknownOutcome:
            raised_unknown = True
        expect("C4 missing fields -> UNKNOWN", raised_unknown)

        # C5: COMMIT_STATUS query itself times out -> UNKNOWN
        sess = FakeSession(["timeout", "timeout"])
        raised_unknown = False
        try:
            ld.commit_with_query(sess, "c5", "rev1", {"install.x_cm": 5.0})
        except ld.UnknownOutcome:
            raised_unknown = True
        expect("C5 query timeout -> UNKNOWN", raised_unknown)

        # C6: known failure (immediate protocol error) -> plain fail
        sess = FakeSession([
            {"ok": False, "error": {"code": "OUT_OF_RANGE", "message": "z"}},
            {"ok": False, "error": {"code": "OUT_OF_RANGE", "message": "z"}},
        ])
        ok, detail = ld.commit_with_query(sess, "c6", "rev1", {"install.z_cm": 601.0})
        expect("C6 immediate protocol error -> known failure", ok is False)

        # C7: first-attempt success produces exactly one success attempt.
        # The op_id is generated inside commit_with_query, so capture it via
        # the FakeSession (it sees the payload) and echo it back correctly.
        class EchoOpSession(FakeSession):
            def call(self, name, payload=None, **kw):
                self.calls.append({"name": name, "op_id": (payload or {}).get("op_id")})
                return {"ok": True, "result": {"op_id": (payload or {}).get("op_id"),
                                               "persisted": True, "revision": "42",
                                               "restart_required": False}}
        sess = EchoOpSession([])
        bank2 = {}
        rc = ld.try_item(bank2, "success_item",
                         lambda: ld.commit_with_query(sess, "success_item", "rev1",
                                                      {"install.x_cm": 7.0}))
        succ = [json.loads(l) for l in ld.ATTEMPTS.read_text(encoding="utf-8").splitlines()
                if json.loads(l)["item"] == "success_item"]
        expect("C7 success once -> one success attempt logged before return",
               rc is True and len(succ) == 1 and succ[0]["status"] == "pass",
               f"rc={rc} attempts={len(succ)}")

        # C9 (r3b review's exact counterexample): the exception is a WRITE
        # timeout (not the "no response" text). The chain must NOT treat it
        # as retryable: one op_id, one COMMIT + one COMMIT_STATUS, zero
        # resets, chain stops with unknown.
        class SerialTimeoutFake(FakeSession):
            def call(self, name, payload=None, **kw):
                op_id = (payload or {}).get("op_id")
                self.calls.append({"name": name, "op_id": op_id})
                if name == "CONFIG_COMMIT":
                    raise Exception("SerialTimeoutException('Write timeout')")
                raise TimeoutError(f"{name} no response")

        s2 = Stubs()
        ld.reset_device = s2.reset_device
        sess = SerialTimeoutFake([])
        bankw = {}
        rc = ld.try_item(bankw, "write_timeout_item",
                         lambda: ld.commit_with_query(sess, "write_timeout_item",
                                                      "rev1", {"install.x_cm": 11.0}))
        opsw = [json.loads(l) for l in ld.PENDING_OPS.read_text(encoding="utf-8").splitlines()
                if json.loads(l)["item"] == "write_timeout_item"]
        commitsw = [c for c in sess.calls if c["name"] == "CONFIG_COMMIT"]
        statusesw = [c for c in sess.calls if c["name"] == "COMMIT_STATUS"]
        expect("C9 write-timeout: single op_id, chain stopped",
               len(opsw) == 1 and len(commitsw) == 1 and len(statusesw) == 1
               and s2.resets == 0 and rc is False,
               f"ops={len(opsw)} commits={len(commitsw)} statuses={len(statusesw)} "
               f"resets={s2.resets} rc={rc}")

        # C10: serial disconnect mid-call -> also "possibly executed" ->
        # COMMIT_STATUS query -> unknown stops.
        class SerialDisconnectFake(FakeSession):
            def call(self, name, payload=None, **kw):
                op_id = (payload or {}).get("op_id")
                self.calls.append({"name": name, "op_id": op_id})
                raise Exception("SerialException('device disconnected')")

        sess = SerialDisconnectFake([])
        raised = False
        try:
            ld.commit_with_query(sess, "c10", "rev1", {"install.x_cm": 10.0})
        except ld.UnknownOutcome:
            raised = True
        expect("C10 serial disconnect -> UNKNOWN (not re-raised as retryable)",
               raised and [c["name"] for c in sess.calls] == ["CONFIG_COMMIT", "COMMIT_STATUS"])

        # C11: a malformed response object (not a dict) must not crash into
        # a known failure - treated as unusable -> UNKNOWN.
        class MalformedFake(FakeSession):
            def call(self, name, payload=None, **kw):
                self.calls.append({"name": name, "op_id": (payload or {}).get("op_id")})
                if name == "CONFIG_COMMIT":
                    return "not-a-dict"
                raise TimeoutError("COMMIT_STATUS no response")

        sess = MalformedFake([])
        raised = False
        try:
            ld.commit_with_query(sess, "c11", "rev1", {"install.x_cm": 12.0})
        except ld.UnknownOutcome:
            raised = True
        except Exception as other:  # noqa: BLE001
            raised = f"WRONG-EXC:{other!r}"
        expect("C11 malformed response -> UNKNOWN", raised is True,
               f"raised={raised}")

        # C12: found=true WITHOUT mandatory fields stays UNKNOWN
        sess = FakeSession([
            "timeout",
            {"ok": True, "result": {"found": True}},  # no revision/current_revision
        ])
        raised = False
        try:
            ld.commit_with_query(sess, "c12", "rev1", {"install.x_cm": 13.0})
        except ld.UnknownOutcome:
            raised = True
        expect("C12 found=true missing mandatory fields -> UNKNOWN", raised)

        # C13: found=true WITH mandatory fields succeeds
        sess = FakeSession([
            "timeout",
            {"ok": True, "result": {"found": True, "revision": "42",
                                    "current_revision": "42"}},
        ])
        ok, detail = ld.commit_with_query(sess, "c13", "rev1", {"install.x_cm": 14.0})
        expect("C13 found=true with mandatory fields -> success",
               ok is True and "revision=42" in detail, detail[:60])

        # --- G2-R3-02 (r3c review A): unified contract validators --------
        # Each uncertain shape must produce UNKNOWN with exactly one op_id,
        # zero resets, and a bank outcome of unknown. A real try_item wraps
        # the real helper for every case.
        def unknown_case(name, actions, expect_note=""):
            sess = FakeSession(actions)
            sN = Stubs()
            ld.reset_device = sN.reset_device
            bankN = {}
            rcN = ld.try_item(bankN, name,
                              lambda: ld.commit_with_query(sess, name, "rev1",
                                                           {"install.x_cm": 1.0}))
            opsN = [json.loads(l) for l in ld.PENDING_OPS.read_text(encoding="utf-8").splitlines()
                    if json.loads(l)["item"] == name]
            attN = [json.loads(l) for l in ld.ATTEMPTS.read_text(encoding="utf-8").splitlines()
                    if json.loads(l)["item"] == name]
            expect(name, rcN is False and len(opsN) == 1 and sN.resets == 0
                   and bankN.get(name, {}).get("outcome") == "unknown"
                   and len(attN) == 1 and attN[0]["status"] == "unknown",
                   f"ops={len(opsN)} resets={sN.resets} rc={rcN} "
                   f"outcome={bankN.get(name, {}).get('outcome')} {expect_note}")

        # non-boolean ok values
        unknown_case("A_ok_str_false", [{"ok": "false", "error": {"code": "BROKEN", "message": "x"}}])
        unknown_case("A_ok_int_0", [{"ok": 0, "error": {"code": "BROKEN", "message": "x"}}])
        unknown_case("A_ok_null", [{"ok": None}])
        unknown_case("A_ok_list", [{"ok": [True]}])
        # malformed error envelopes
        unknown_case("A_err_code_42", [{"ok": False, "error": {"code": 42, "message": "x"}}])
        unknown_case("A_err_code_obj", [{"ok": False, "error": {"code": {"bad": 1}, "message": "x"}}])
        unknown_case("A_err_missing", [{"ok": False}])
        unknown_case("A_err_no_msg", [{"ok": False, "error": {"code": "X"}}])
        # success with only persisted (missing op_id/revision/restart_required)
        unknown_case("A_succ_persisted_only", [{"ok": True, "result": {"persisted": True}}])
        # success returning a different op_id
        sess = FakeSession([{"ok": True, "result": {"op_id": "wrong-op", "revision": "2",
                                                    "persisted": True, "restart_required": False}}])
        raised = False
        try:
            ld.commit_with_query(sess, "A_wrong_op", "rev1", {"install.x_cm": 1.0})
        except ld.UnknownOutcome:
            raised = True
        expect("A_wrong_op_id -> UNKNOWN", raised)

        # invalid revisions (schema: ^[0-9]+$, max 20 chars). The op_id
        # mismatch in these cases does not mask the revision check because
        # _validate_commit_success checks op_id FIRST, so a wrong op_id
        # fails even with a valid revision — but we want to also prove the
        # revision check itself fires. Use an echoing session.
        class EchoSess(FakeSession):
            def call(self, name, payload=None, **kw):
                self.calls.append({"name": name, "op_id": (payload or {}).get("op_id")})
                a = self.actions.pop(0) if self.actions else "timeout"
                if a == "timeout":
                    raise TimeoutError(f"{name} no response")
                return a
        for rev in ("-2", "abc", "2x", "", "1" * 21, None, 42):
            sess = EchoSess([{"ok": True, "result": {"op_id": "ECHO", "revision": rev,
                                                     "persisted": True,
                                                     "restart_required": False}}])
            # substitute the echo marker after capture
            sess.result_override = None
            def echo_call(name2, payload2=None, **kw2):
                sess.calls.append({"name": name2, "op_id": (payload2 or {}).get("op_id")})
                a = sess.actions.pop(0) if sess.actions else "timeout"
                if a == "timeout":
                    raise TimeoutError(f"{name2} no response")
                res = dict(a.get("result", {})) if isinstance(a, dict) else {}
                if res.get("op_id") == "ECHO":
                    res["op_id"] = (payload2 or {}).get("op_id")
                return {"ok": a.get("ok"), "result": res} if isinstance(a, dict) else a
            sess.call = echo_call
            raised = False
            try:
                ld.commit_with_query(sess, "A_bad_rev", "rev1", {"install.x_cm": 1.0})
            except ld.UnknownOutcome as e:
                raised = "revision" in str(e) or "invalid" in str(e).lower()
            expect(f"A_invalid_revision {rev!r:.20} -> UNKNOWN", raised)

        # valid success with all mandatory fields passes (positive control)
        def make_echo_session(result):
            """Fresh scripted session echoing the real op_id with the given
            result template (ECHO marker replaced by the actual op_id)."""
            s = FakeSession([{"ok": True, "result": result}])

            def echo_call(name2, payload2=None, **kw2):
                s.calls.append({"name": name2, "op_id": (payload2 or {}).get("op_id")})
                a = s.actions.pop(0) if s.actions else "timeout"
                if a == "timeout":
                    raise TimeoutError(f"{name2} no response")
                res = dict(a.get("result", {})) if isinstance(a, dict) else {}
                if res.get("op_id") == "ECHO":
                    res["op_id"] = (payload2 or {}).get("op_id")
                return {"ok": a.get("ok"), "result": res} if isinstance(a, dict) else a
            s.call = echo_call
            return s

        sess = make_echo_session({"op_id": "ECHO", "revision": "2",
                                  "persisted": True, "restart_required": False})
        ok, detail = ld.commit_with_query(sess, "A_succ_ok", "rev1", {"install.x_cm": 1.0})
        expect("A_valid_success passes", ok is True, detail[:60])

        # ---- G2-R3-02 (r3d E): revision ASCII/uint64 boundary + schema
        # const restart_required:false. Each negative is one variable. ----
        def expect_unknown_revision(name, rev):
            s2 = make_echo_session({"op_id": "ECHO", "revision": rev,
                                    "persisted": True, "restart_required": False})
            raised = False
            try:
                ld.commit_with_query(s2, name, "rev1", {"install.x_cm": 1.0})
            except ld.UnknownOutcome as e:
                raised = "revision" in str(e).lower()
            except Exception as other:  # noqa: BLE001
                raised = f"WRONG-EXC:{other!r}"
            expect(name, raised is True, f"raised={raised}")

        # r3d: Arabic-Indic digit - str.isdigit() accepts it, the schema
        # ^[0-9]+$ does not
        expect_unknown_revision("F1 unicode arabic-indic revision '١'",
                                "\u0661")
        # fullwidth digits (also isdigit()-true, not ASCII)
        expect_unknown_revision("F2 fullwidth digits '１２'", "\uff11\uff12")
        # 20 chars = max bytes, but > uint64 max
        expect_unknown_revision("F3 uint64 overflow 20 digits",
                                "99999999999999999999")
        # one above the uint64 maximum (18446744073709551615 + 1)
        expect_unknown_revision("F4 uint64 max + 1", "18446744073709551616")
        # superscript digits (isdigit()-true Unicode, not ASCII)
        expect_unknown_revision("F5 superscript digits '²'", "\u00b2")

        # POSITIVE: the exact uint64 maximum is legal (pattern + range ok)
        sess = make_echo_session({"op_id": "ECHO", "revision": "18446744073709551615",
                                  "persisted": True, "restart_required": False})
        ok, detail = ld.commit_with_query(sess, "F6", "rev1", {"install.x_cm": 1.0})
        expect("F6 uint64-max revision accepted", ok is True, detail[:70])

        # r3d: restart_required=true violates the schema const:false -> the
        # success envelope is UNKNOWN, not tolerated future semantics
        sess = make_echo_session({"op_id": "ECHO", "revision": "2",
                                  "persisted": True, "restart_required": True})
        raised = False
        try:
            ld.commit_with_query(sess, "F7", "rev1", {"install.x_cm": 1.0})
        except ld.UnknownOutcome as e:
            raised = "restart_required" in str(e)
        expect("F7 restart_required=true -> UNKNOWN (schema const:false)",
               raised)

        # valid known failure passes (positive control)
        sess = FakeSession([{"ok": False, "error": {"code": "OUT_OF_RANGE",
                                                    "message": "z"}}])
        ok, detail = ld.commit_with_query(sess, "A_fail_ok", "rev1", {"install.z_cm": 601.0})
        expect("A_valid_known_failure passes", ok is False)

        # found=true with valid contract revisions passes
        sess = FakeSession(["timeout", {"ok": True, "result": {
            "found": True, "revision": "42", "current_revision": "42"}}])
        ok, detail = ld.commit_with_query(sess, "A_status_ok", "rev1", {"install.x_cm": 1.0})
        expect("A_status_valid_revision passes", ok is True)

        # found=true with non-contract revisions fails
        sess = FakeSession(["timeout", {"ok": True, "result": {
            "found": True, "revision": "abc", "current_revision": "42"}}])
        raised = False
        try:
            ld.commit_with_query(sess, "A_status_bad_rev", "rev1", {"install.x_cm": 1.0})
        except ld.UnknownOutcome:
            raised = True
        expect("A_status_noncontract_revision -> UNKNOWN", raised)

        # C14-C17 (r3b review A): fail-closed response-shape validation
        sess = FakeSession([{}])
        bankx = {}
        s3 = Stubs()
        ld.reset_device = s3.reset_device
        rc = ld.try_item(bankx, "c14_empty_commit",
                         lambda: ld.commit_with_query(sess, "c14_empty_commit",
                                                      "rev1", {"x": 1.0}))
        ops14 = [json.loads(l) for l in ld.PENDING_OPS.read_text(encoding="utf-8").splitlines()
                 if json.loads(l)["item"] == "c14_empty_commit"]
        expect("C14 commit={} -> UNKNOWN, one op_id, zero resets",
               rc is False and len(ops14) == 1 and s3.resets == 0
               and bankx.get("c14_empty_commit", {}).get("outcome") == "unknown",
               f"ops={len(ops14)} resets={s3.resets} rc={rc}")

        # C15: write timeout then COMMIT_STATUS returns None -> UNKNOWN
        class NoneStatusFake(FakeSession):
            def call(self, name, payload=None, **kw):
                op_id = (payload or {}).get("op_id")
                self.calls.append({"name": name, "op_id": op_id})
                if name == "CONFIG_COMMIT":
                    raise Exception("SerialTimeoutException('Write timeout')")
                return None  # COMMIT_STATUS -> None
        s4 = Stubs()
        ld.reset_device = s4.reset_device
        sess = NoneStatusFake([])
        bankx = {}
        rc = ld.try_item(bankx, "c15_query_none",
                         lambda: ld.commit_with_query(sess, "c15_query_none",
                                                      "rev1", {"x": 2.0}))
        ops15 = [json.loads(l) for l in ld.PENDING_OPS.read_text(encoding="utf-8").splitlines()
                 if json.loads(l)["item"] == "c15_query_none"]
        statuses15 = [c for c in sess.calls if c["name"] == "COMMIT_STATUS"]
        expect("C15 query=None -> UNKNOWN, one op_id, one STATUS, zero resets",
               rc is False and len(ops15) == 1 and len(statuses15) == 1
               and s4.resets == 0
               and bankx.get("c15_query_none", {}).get("outcome") == "unknown",
               f"ops={len(ops15)} statuses={len(statuses15)} resets={s4.resets}")

        # C16: query returns a list / string -> UNKNOWN
        for shape in ([], "garbage"):
            sess = FakeSession(["timeout", shape])
            raised = False
            try:
                ld.commit_with_query(sess, "c16", "rev1", {"x": 16.0})
            except ld.UnknownOutcome:
                raised = True
            expect(f"C16 query={type(shape).__name__} -> UNKNOWN", raised)

        # C17: found=true with null revision / null current_revision /
        # non-string types -> UNKNOWN
        for res in ({"found": True, "revision": None, "current_revision": None},
                    {"found": True, "revision": None, "current_revision": "42"},
                    {"found": True, "revision": 42, "current_revision": 42}):
            sess = FakeSession(["timeout", {"ok": True, "result": res}])
            raised = False
            try:
                ld.commit_with_query(sess, "c17", "rev1", {"x": 17.0})
            except ld.UnknownOutcome:
                raised = True
            expect(f"C17 found=true invalid revision {json.dumps(res.get('revision'))} -> UNKNOWN",
                   raised)

        # C18: commit responses that are not proven outcomes -> UNKNOWN
        for resp in ({"ok": True, "result": {"persisted": False}},
                     {"ok": True}, {},
                     {"ok": False, "error": "oops"}):
            sess = FakeSession([resp])
            raised = False
            try:
                ld.commit_with_query(sess, "c18", "rev1", {"x": 18.0})
            except ld.UnknownOutcome:
                raised = True
            expect(f"C18 commit {json.dumps(resp, default=str)[:40]} -> UNKNOWN", raised)

        # C14 (R3-05b): the environment fingerprint promotes the build-tree
        # hash ONLY as a hint - flashed evidence requires a flash/verify
        # record. An identity built from a build hint alone must never
        # satisfy reuse: the manifest marks flashed_image_sha256 unverified,
        # so two "same environment" keys built from build hints differ and
        # reuse is forbidden. (leg_driver2's fingerprint is a runner/
        # environment identity, distinct from index acceptance; this test
        # pins that its image_sha256 field is documented as a hint.)
        import inspect
        src = inspect.getsource(ld.environment_fingerprint)
        ok = 'image_sha256' in src and 'hint' in (ld.ENV_HINT_DOC if hasattr(ld, 'ENV_HINT_DOC') else src)
        expect("C14 fingerprint documents the image hash as a hint (not flashed proof)",
               ok, "doc in fingerprint source")

        # C8: an unknown bank entry blocks re-issuing on the next run
        bank3 = {"chain_item": {"pass": False, "outcome": "unknown", "env": ld.environment_key()}}
        sess = FakeSession([])
        rc = ld.try_item(bank3, "chain_item", commit_fn(sess, {"install.x_cm": 9.0}))
        expect("C8 unknown outcome blocks re-issue across runs",
               rc is False and len(sess.calls) == 0,
               f"rc={rc} calls={len(sess.calls)}")

        # ---- G2-R3-05 (r3c E): structured flash/verify record gates ------
        # The flash log must contain a JSON record with status=success,
        # the matching image_sha256, and the matching board mac_hint.
        # FAILED text / wrong board / different image -> no complete.

        # sandbox a fresh environment + flash log
        def sandbox_flash(content):
            ld.EVIDENCE = Path(td)
            (Path(td) / "flash-log-r2.txt").write_text(content, encoding="utf-8")
            ld.ENV = None
            return ld.environment()

        img_sha = "0" * 64  # a fake 64-hex image sha
        img_other = "e" * 64  # a DIFFERENT image flashed later
        board = "dc:da:0c:f8:f2:74"
        # the sandbox environment's real image hash (positive tests must
        # match THIS, since environment_fingerprint hashes the build tree)
        env_probe = ld.environment()
        env_img = env_probe.get("image_sha256") if env_probe.get("image_sha256") else img_sha

        def rec(status, image, seq, verify="ok", board_id=board, timestamp=None):
            r = {"status": status, "image_sha256": image,
                 "board_id": board_id, "seq": seq,
                 "timestamp": timestamp or f"2026-10-2{seq}T00:00:00Z"}
            if verify is not None:
                r["verify"] = verify
            return json.dumps(r)

        # negative: "FAILED verification; image <SHA> was NOT flashed; unrelated board"
        env = sandbox_flash(
            'FAILED verification; image ' + img_sha + ' was NOT flashed; unrelated board' + chr(10))
        expect("E4 FAILED-record text -> not complete (no structured record)",
               env["complete"] is False and env["flashed_evidence"] is False,
               f"flashed={env['flashed_evidence']}")

        # negative: JSON record with status=failed
        env = sandbox_flash(rec("failed", img_sha, 1) + chr(10))
        expect("E5 JSON record status=failed -> not complete",
               env["complete"] is False and env["flashed_evidence"] is False)

        # negative: success record but WRONG board
        env = sandbox_flash(rec("success", img_sha, 1, board_id="aa:bb:cc:dd:ee:ff") + chr(10))
        expect("E6 success record wrong board -> not complete",
               env["complete"] is False and env["flashed_evidence"] is False)

        # negative: success record but WRONG image
        env = sandbox_flash(rec("success", "1" * 64, 1) + chr(10))
        expect("E7 success record wrong image -> not complete",
               env["complete"] is False and env["flashed_evidence"] is False)

        # r3d E-B2: SAME board, seq1 flashes OUR image (success), seq2 later
        # flashes a DIFFERENT image (success) -> the latest state supersedes
        # the historical match; complete must be False.
        env = sandbox_flash(rec("success", img_sha, 1) + chr(10) +
                            rec("success", img_other, 2) + chr(10))
        expect("E9 later success flash of a different image supersedes",
               env["complete"] is False and env["flashed_evidence"] is False
               and "DIFFERENT" in env.get("flashed_evidence_reason", ""),
               env.get("flashed_evidence_reason", "")[:60])

        # r3d E-B2b: same board, our image flashed, then a FAILED reflash ->
        # latest state is failed -> unknown/complete False.
        env = sandbox_flash(rec("success", img_sha, 1) + chr(10) +
                            rec("failed", img_other, 2) + chr(10))
        expect("E10 later FAILED reflash invalidates the previous success",
               env["complete"] is False and env["flashed_evidence"] is False
               and "failed" in env.get("flashed_evidence_reason", ""),
               env.get("flashed_evidence_reason", "")[:60])

        # r3d E-B2c: our image then an erase -> latest state erased.
        env = sandbox_flash(rec("success", img_sha, 1) + chr(10) +
                            rec("erased", None, 2) + chr(10))
        expect("E11 later erase invalidates the previous success",
               env["complete"] is False and env["flashed_evidence"] is False,
               env.get("flashed_evidence_reason", "")[:60])

        # r3d E-B2d: records without ANY seq/timestamp cannot be replayed ->
        # unverifiable, not complete (a bare success line cannot prove the
        # CURRENT board state).
        env = sandbox_flash(
            json.dumps({"status": "success", "image_sha256": img_sha,
                        "board_id": board}) + chr(10))
        expect("E12 flash records without order cannot prove current state",
               env["complete"] is False and env["flashed_evidence"] is False,
               env.get("flashed_evidence_reason", "")[:60])

        # r3d E-B2e: a different board's records are irrelevant; the positive
        # control is OUR board's latest success with OUR image. Both success
        # records use the sandbox's ACTUAL image hash, so the board's latest
        # flash state matches the current build identity.
        env = sandbox_flash(rec("success", env_img, 1, board_id="aa:bb:cc:dd:ee:ff") + chr(10) +
                            rec("success", env_img, 2) + chr(10))
        expect("E13 other-board history ignored; our latest success counts",
               env["flashed_evidence"] is True and env["complete"] is True
               and env.get("flashed_evidence_reason", "").startswith("latest flash"),
               env.get("flashed_evidence_reason", "")[:60])

        # r3d E-B2f: latest success whose verify != ok -> not complete
        env = sandbox_flash(rec("success", env_img, 1, verify="failed") + chr(10))
        expect("E14 latest flash not verify-ok -> not complete",
               env["complete"] is False and env["flashed_evidence"] is False,
               env.get("flashed_evidence_reason", "")[:60])

        # r3d E-B2g (review's exact recheck case): seq1 success A (ours),
        # seq2 success B — build hint is A -> complete must be FALSE (the
        # probe's superseded_flash_A_then_B scenario).
        env = sandbox_flash(rec("success", env_img, 1,
                                timestamp="2026-10-26T00:00:00Z") + chr(10) +
                            rec("success", img_other, 2,
                                timestamp="2026-10-27T00:00:00Z") + chr(10))
        expect("E15 probe case A-then-B: historical success does not survive",
               env["complete"] is False and env["flashed_evidence"] is False,
               env.get("flashed_evidence_reason", "")[:60])

        # r3e E16: Old A (seq1, success) -> unknown (seq2) -> latest is unknown -> False
        env = sandbox_flash(rec("success", env_img, 1, timestamp="2026-10-26T00:00:00Z") + chr(10) +
                            rec("unknown", env_img, 2, timestamp="2026-10-27T00:00:00Z") + chr(10))
        expect("E16 old A then unknown seq2 invalidates certainty",
               env["complete"] is False and env["flashed_evidence"] is False
               and "unknown" in env.get("flashed_evidence_reason", ""),
               env.get("flashed_evidence_reason", "")[:60])

        # r3e E17: Old ordered A -> unorderable partial record (missing seq and timestamp) -> False
        env = sandbox_flash(rec("success", env_img, 1, timestamp="2026-10-26T00:00:00Z") + chr(10) +
                            json.dumps({"status": "partial", "board_id": board}) + chr(10))
        expect("E17 unorderable partial record invalidates replay order",
               env["complete"] is False and env["flashed_evidence"] is False
               and "unorderable" in env.get("flashed_evidence_reason", ""),
               env.get("flashed_evidence_reason", "")[:60])

        # r3e E18: Old A (seq1, 10-26) -> new B (timestamp-only 10-27) -> B supersedes A -> False
        env = sandbox_flash(rec("success", env_img, 1, timestamp="2026-10-26T00:00:00Z") + chr(10) +
                            json.dumps({"status": "success", "image_sha256": img_other, "board_id": board,
                                        "verify": "ok", "timestamp": "2026-10-27T00:00:00Z"}) + chr(10))
        expect("E18 timestamp-only later flash B supersedes earlier seq flash A",
               env["complete"] is False and env["flashed_evidence"] is False
               and "DIFFERENT" in env.get("flashed_evidence_reason", ""),
               env.get("flashed_evidence_reason", "")[:60])

        # r3e E19: success missing verify (verify=None) -> unverified -> False
        env = sandbox_flash(json.dumps({"status": "success", "image_sha256": env_img, "board_id": board,
                                        "seq": 1, "timestamp": "2026-10-26T00:00:00Z"}) + chr(10))
        expect("E19 success without verify fails",
               env["complete"] is False and env["flashed_evidence"] is False
               and "verify" in env.get("flashed_evidence_reason", ""),
               env.get("flashed_evidence_reason", "")[:60])

        # r3e E20: anomalous future timestamp -> fails
        env = sandbox_flash(json.dumps({"status": "success", "image_sha256": env_img, "board_id": board,
                                        "seq": 1, "verify": "ok", "timestamp": "2099-01-01T00:00:00Z"}) + chr(10))
        expect("E20 anomalous future timestamp fails",
               env["complete"] is False and env["flashed_evidence"] is False
               and "future" in env.get("flashed_evidence_reason", ""),
               env.get("flashed_evidence_reason", "")[:60])

        # r3e E21: other board records mixed in do not poison our verified record
        env = sandbox_flash(rec("failed", img_other, 1, board_id="other:board:mac") + chr(10) +
                            rec("success", env_img, 1, timestamp="2026-10-26T00:00:00Z") + chr(10))
        expect("E21 other board records do not poison our verified record",
               env["complete"] is True and env["flashed_evidence"] is True,
               env.get("flashed_evidence_reason", "")[:60])

        # r3f: E22 mixed incomparable records (timestamp-only and seq-only)
        env = sandbox_flash(
            json.dumps({"status": "success", "image_sha256": "a"*64,
                        "board_id": "dc:da:0c:f8:f2:74", "verify": "ok",
                        "timestamp": "2026-10-26T00:00:00Z"}) + "\n" +
            json.dumps({"status": "partial", "board_id": "dc:da:0c:f8:f2:74",
                        "seq": 2}) + "\n")
        expect("E22 mixed incomparable records rejected",
               env["complete"] is False and env["flashed_evidence"] is False,
               env.get("flashed_evidence_reason", "")[:70])

        # r3f: E23 duplicate order conflict (same seq and timestamp with conflicting status)
        env = sandbox_flash(
            json.dumps({"status": "partial", "image_sha256": "a"*64,
                        "board_id": "dc:da:0c:f8:f2:74", "seq": 1, "verify": "ok",
                        "timestamp": "2026-10-26T00:00:00Z"}) + "\n" +
            json.dumps({"status": "success", "image_sha256": "a"*64,
                        "board_id": "dc:da:0c:f8:f2:74", "seq": 1, "verify": "ok",
                        "timestamp": "2026-10-26T00:00:00Z"}) + "\n")
        expect("E23 duplicate order conflict rejected",
               env["complete"] is False and env["flashed_evidence"] is False,
               env.get("flashed_evidence_reason", "")[:70])

        # r3f: E24 future five minute flash rejected
        import datetime as _dt
        future_ts = (_dt.datetime.now(_dt.timezone.utc) + _dt.timedelta(minutes=5)).isoformat()
        env = sandbox_flash(
            json.dumps({"status": "success", "image_sha256": "b"*64,
                        "board_id": "dc:da:0c:f8:f2:74", "seq": 1, "verify": "ok",
                        "timestamp": "2026-10-26T00:00:00Z"}) + "\n" +
            json.dumps({"status": "success", "image_sha256": "a"*64,
                        "board_id": "dc:da:0c:f8:f2:74", "seq": 2, "verify": "ok",
                        "timestamp": future_ts}) + "\n")
        expect("E24 future timestamp flash rejected",
               env["complete"] is False and env["flashed_evidence"] is False,
               env.get("flashed_evidence_reason", "")[:70])

        # positive: success + correct image + correct board (sandbox may not
        # have the real build SHA, so we accept complete=True for the board
        # check alone — the point is the record parses and gates correctly)
        real_sha = None
        # build a fake env with the right image sha for the positive test
        real_img = ld.COMPONENT / ".esphome-host" / "build" / "r60abd1-host-nops" / "build" / "firmware.factory.bin"
        if real_img.is_file():
            import hashlib as _h
            real_sha = _h.sha256(real_img.read_bytes()).hexdigest()
        if real_sha:
            env = sandbox_flash(
                json.dumps({"status": "success", "image_sha256": real_sha,
                            "board_id": "dc:da:0c:f8:f2:74", "seq": 1,
                            "verify": "ok",
                            "timestamp": "2026-10-27T12:00:00Z"}) + chr(10))
            expect("E8 success+correct image+board -> complete",
                   env["complete"] is True and env["flashed_evidence"] is True,
                   f"flashed={env['flashed_evidence']}")
        else:
            expect("E8 (skipped: no build image)", True, "")


        # restore a valid flash log for the fingerprint after the E tests
        env_real = ld.environment()
        if env_real.get("image_sha256"):
            (Path(td) / "flash-log-r2.txt").write_text(
                json.dumps({"status": "success",
                            "image_sha256": env_real["image_sha256"],
                            "board_id": "dc:da:0c:f8:f2:74", "seq": 99,
                            "verify": "ok",
                            "timestamp": "2026-10-27T12:00:00Z"}) + chr(10),
                encoding="utf-8")
            ld.ENV = None

        # r3g: duplicate seq conflict rejected
        env_dup = sandbox_flash(
            rec("partial", img_sha, 1, timestamp="2026-10-26T00:00:00Z") + chr(10) +
            rec("success", img_sha, 1, timestamp="2026-10-27T00:00:00Z") + chr(10))
        expect("E10 duplicate seq conflict -> not complete",
               env_dup["complete"] is False and env_dup["flashed_evidence"] is False
               and "duplicate sequence conflict" in env_dup.get("flashed_evidence_reason", ""))

        # r3g: seq vs timestamp contradiction rejected
        env_contra = sandbox_flash(
            rec("success", img_sha, 2, timestamp="2026-10-26T00:00:00Z") + chr(10) +
            rec("partial", img_sha, 1, timestamp="2026-10-27T00:00:00Z") + chr(10))
        expect("E11 sequence/timestamp contradiction -> not complete",
               env_contra["complete"] is False and env_contra["flashed_evidence"] is False
               and "contradiction" in env_contra.get("flashed_evidence_reason", ""))

        # r3g: missing live identity without injection rejected
        ld.TARGET_DEVICE_ID = None
        ld.ENV = None
        img_valid = "a" * 64
        from unittest.mock import patch
        with patch.object(ld, "_sha256", lambda p: img_valid):
            env_noid = sandbox_flash(rec("success", img_valid, 1) + chr(10))
            expect("E12 missing live device identity -> not complete",
                   env_noid["complete"] is False and env_noid["flashed_evidence"] is False
                   and "missing verified live device identity" in env_noid.get("flashed_evidence_reason", ""))
        ld.TARGET_DEVICE_ID = None
        ld.ENV = None
    print("VERDICT:", "pass" if not failures else f"FAIL ({len(failures)})")
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())
