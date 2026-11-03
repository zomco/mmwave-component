"""Offline CONFIG_COMMIT identity and pending-write checks.

Uses mwcp.Client over the fake byte pipe. Pass an output directory; this file
does not call session_keeper_test.main and does not write offline-trace.json.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import mwcp
import session_flow as sf
import session_keeper_test as sk


LEGAL = "33333333-3333-4333-8333-333333333333"
OTHER = "44444444-4444-4444-8444-444444444444"
UNRESOLVED = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa1"
NEW_OP = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbb2"


class BadReply(sk.Device):
    def __init__(self, clock: sf.FakeClock, mode: str) -> None:
        super().__init__(clock)
        self.mode = mode

    def _commit(self, frame: dict, payload: dict) -> None:
        if self.mode == "wrong_then_legal":
            self._send(frame, frame["code"], self.session_id - 1, {"ok": True})
            super()._commit(frame, payload)
            return
        if self.mode == "stale_revision":
            self._send(frame, frame["code"], self.session_id, {
                "ok": True,
                "result": {
                    "op_id": payload["op_id"],
                    "revision": self.revision,
                    "persisted": True,
                    "restart_required": False,
                },
            })
            return
        self._bad(frame, payload, self.mode)

    def _bad(self, frame: dict, payload: dict, mode: str) -> None:
        sid = self.session_id - 1 if mode == "wrong_session" else self.session_id
        code = mwcp.CODE["PING"] if mode == "wrong_code" else frame["code"]
        if mode == "missing_result":
            body = {"ok": True}
        else:
            body = {
                "ok": True,
                "result": {
                    "op_id": "other-op" if mode == "wrong_op" else payload["op_id"],
                    "revision": "150",
                    "persisted": True,
                    "restart_required": False,
                },
            }
        self._send(frame, code, sid, body)

    def _send(self, frame: dict, code: int, session_id: int, body: dict) -> None:
        raw = json.dumps(body, separators=(",", ":")).encode("utf-8")
        self.pipe.rx.extend(mwcp.encode_frame(
            mwcp.KIND_RESPONSE, session_id, frame["request_id"], code, raw, self.seq
        ))
        self.seq += 1


def _order(device: sk.Device) -> list[dict]:
    return [
        {"name": item["name"], "body": item["body"], "session_id": item["session_id"]}
        for item in device.requests
    ]


def _run(device: sk.Device, clock: sf.FakeClock, directory: Path, fn):
    directory.mkdir(parents=True)
    with sk.patched(clock):
        flow, evidence = sk.open_flow(device, clock, str(directory), allow_write=True)
        try:
            result = fn(flow, device)
        finally:
            evidence.close()
            flow.client.close()
    result["requests"] = _order(device)
    result["commit_frames"] = device.commit_frames()
    result["device_revision"] = device.revision
    return result


def test_unrelated_replies(out: Path) -> dict:
    found = {}
    for mode in ("wrong_session", "wrong_code", "wrong_op", "missing_result"):
        clock = sf.FakeClock()
        device = BadReply(clock, mode)

        def once(flow, dev, mode=mode):
            outcome = flow.commit("requested-op", "149", {"install.x_cm": 31})
            assert outcome["result"] == sf.RESULT_UNKNOWN
            assert outcome["result"] != "known"
            assert outcome.get("executed") is None
            assert outcome["op_id"] == "requested-op"
            assert dev.revision == "149"
            assert dev.commit_frames() == 1
            assert flow.pending["op_id"] == "requested-op"
            assert flow.pending["base_revision"] == "149"
            assert flow.pending["changes"] == {"install.x_cm": 31}
            commits = [item for item in dev.requests if item["name"] == "CONFIG_COMMIT"]
            assert commits[0]["body"]["op_id"] == "requested-op"
            status = [item for item in dev.requests if item["name"] == "COMMIT_STATUS"]
            assert len(status) == 1 and status[0]["body"]["op_id"] == "requested-op"
            return {"result": outcome["result"], "kind": outcome.get("kind"), "pending": flow.pending["op_id"]}

        found[mode] = _run(device, clock, out / mode, once)
    return found


def test_controls(out: Path) -> dict:
    clock = sf.FakeClock()
    legal = _run(sk.Device(clock), clock, out / "legal_success", lambda flow, dev: _legal(flow, dev))

    clock = sf.FakeClock()
    cas = _run(sk.Device(clock), clock, out / "legal_cas", lambda flow, dev: _cas(flow, dev))

    clock = sf.FakeClock()
    followed = _run(BadReply(clock, "wrong_then_legal"), clock, out / "wrong_then_legal", _followed)

    clock = sf.FakeClock()
    only = _run(BadReply(clock, "wrong_session"), clock, out / "only_wrong", _only_wrong)

    clock = sf.FakeClock()
    stale = _run(BadReply(clock, "stale_revision"), clock, out / "stale_revision", _stale)
    return {
        "legal_success": legal,
        "legal_cas": cas,
        "wrong_then_legal": followed,
        "only_wrong": only,
        "stale_revision": stale,
    }


def _legal(flow, dev) -> dict:
    outcome = flow.commit(LEGAL, "149", {"install.x_cm": 31})
    assert outcome["result"] == "known"
    assert outcome["op_id"] == LEGAL
    assert outcome["body"]["result"]["revision"] == "150"
    assert flow.pending is None
    assert dev.commit_frames() == 1
    assert dev.names().count("COMMIT_STATUS") == 0
    assert dev.revision == "150"
    return {"result": outcome["result"], "op_id": outcome["op_id"]}


def _cas(flow, dev) -> dict:
    outcome = flow.commit(OTHER, "148", {"install.x_cm": 140})
    assert outcome["result"] == "known_failure"
    assert outcome["body"]["error"]["code"] == "REVISION_CONFLICT"
    assert flow.pending is None
    assert dev.commit_frames() == 1
    assert dev.names().count("COMMIT_STATUS") == 0
    assert dev.revision == "149"
    return {"result": outcome["result"], "code": outcome["body"]["error"]["code"]}


def _followed(flow, dev) -> dict:
    outcome = flow.commit(LEGAL, "149", {"install.x_cm": 31})
    assert outcome["result"] == "known"
    assert outcome["body"]["result"]["op_id"] == LEGAL
    assert outcome["body"]["result"]["revision"] == "150"
    assert flow.pending is None
    assert dev.commit_frames() == 1
    assert dev.revision == "150"
    return {"result": outcome["result"], "op_id": outcome["op_id"]}


def _only_wrong(flow, dev) -> dict:
    outcome = flow.commit(LEGAL, "149", {"install.x_cm": 31})
    assert outcome["result"] == sf.RESULT_UNKNOWN
    assert outcome["executed"] is None
    assert flow.pending["op_id"] == LEGAL
    assert dev.commit_frames() == 1
    assert dev.revision == "149"
    return {"result": outcome["result"], "pending": flow.pending["op_id"]}


def _stale(flow, dev) -> dict:
    outcome = flow.commit(LEGAL, "149", {"install.x_cm": 31})
    assert outcome["result"] == sf.RESULT_UNKNOWN
    assert outcome.get("kind") == sf.PROTOCOL_ERROR
    assert flow.pending["op_id"] == LEGAL
    assert dev.commit_frames() == 1
    assert dev.revision == "149"
    return {"result": outcome["result"], "kind": outcome["kind"]}


def test_pending_guard(out: Path) -> dict:
    clock = sf.FakeClock()
    device = sk.Device(clock)
    device.drop_commit = True
    device.hide_status = True

    def seq(flow, dev):
        first = flow.commit(UNRESOLVED, "149", {"install.x_cm": 31})
        assert first["result"] == sf.RESULT_UNKNOWN
        assert first["found"] is False
        assert first["executed"] is None
        assert flow.pending["op_id"] == UNRESOLVED
        sends = dev.commit_frames()
        second = flow.commit(NEW_OP, "150", {"install.x_cm": 32})
        assert second["result"] == "rejected"
        assert second["status"] == sf.CONFIRM_PREVIOUS
        assert second["sent"] is False
        assert second["op_id"] == UNRESOLVED
        assert second["base_revision"] == "149"
        assert second["changes"] == {"install.x_cm": 31}
        assert flow.pending["op_id"] == UNRESOLVED
        assert flow.pending["changes"] == {"install.x_cm": 31}
        assert dev.commit_frames() == sends
        again = flow.recover()
        assert again["found"] is False
        assert again["executed"] is None
        assert flow.pending["op_id"] == UNRESOLVED
        dev.hide_status = False
        confirmed = flow.recover()
        assert confirmed["found"] is True
        assert confirmed["op_id"] == UNRESOLVED
        assert confirmed["executed"] is None
        assert flow.pending is None
        saved = flow.commit(NEW_OP, "150", {"install.x_cm": 32})
        assert saved["result"] == "known"
        assert saved["op_id"] == NEW_OP
        assert dev.commit_frames() == sends + 1
        return {
            "first": first["result"],
            "rejected": second["status"],
            "confirmed_op": confirmed["op_id"],
            "saved": saved["result"],
        }

    return _run(device, clock, out / "pending_guard", seq)


def test_explicit_release(out: Path) -> dict:
    clock = sf.FakeClock()
    device = sk.Device(clock)
    device.drop_commit = True
    device.hide_status = True

    def seq(flow, dev):
        first = flow.commit(UNRESOLVED, "149", {"install.x_cm": 31})
        assert first["found"] is False
        sends = dev.commit_frames()
        released = flow.release_pending("abandon-tracking")
        assert released["result"] == "released"
        assert released["executed"] is None
        assert released["op_id"] == UNRESOLVED
        assert released["queried"] is False
        assert flow.release_log[-1]["reason"] == "abandon-tracking"
        assert flow.pending is None
        assert dev.commit_frames() == sends
        saved = flow.commit(NEW_OP, "150", {"install.x_cm": 32})
        assert saved["result"] == "known"
        assert dev.commit_frames() == sends + 1
        return {"released": released["result"], "executed": released["executed"], "saved": saved["result"]}

    return _run(device, clock, out / "explicit_release", seq)


def test_port_reattach(out: Path) -> dict:
    clock = sf.FakeClock()
    device = sk.Device(clock)
    device.close_after_commit = True
    directory = out / "port_reattach"
    directory.mkdir(parents=True)
    with sk.patched(clock):
        flow, evidence = sk.open_flow(device, clock, str(directory), allow_write=True)
        first = flow.commit(UNRESOLVED, "149", {"install.x_cm": 31})
        assert first["kind"] == sf.PORT_CLOSED
        assert flow.pending["op_id"] == UNRESOLVED
        try:
            flow.commit(NEW_OP, "150", {"install.x_cm": 32})
        except sf.ClassifiedTimeout as ex:
            assert ex.kind == sf.PORT_CLOSED
        else:
            raise AssertionError("closed port sent a second commit")
        assert device.commit_frames() == 1
        assert flow.pending["op_id"] == UNRESOLVED
        held = flow.recover()
        assert held["queried"] is False
        assert held["op_id"] == UNRESOLVED
        evidence.close()
        flow.client.close()
        evidence2 = mwcp.EvidenceWriter(directory / "ev-reconnect.jsonl", mwcp.Redactor())
        pipe = sk.Pipe(device)
        device.bind(pipe)
        client = mwcp.Client("TEST", evidence2, allow_write=True, ser=pipe)
        flow.attach(client)
        queried = flow.recover()
        assert queried["queried"] is True
        assert queried["op_id"] == UNRESOLVED
        assert queried["found"] is True
        assert queried["executed"] is None
        assert device.commit_frames() == 1
        assert flow.pending is None
        order = _order(device)
        evidence2.close()
        client.close()
    return {
        "first_kind": first["kind"],
        "recovered_op": queried["op_id"],
        "commit_frames": device.commit_frames(),
        "device_revision": device.revision,
        "requests": order,
    }


def main(argv: list[str]) -> None:
    if len(argv) != 2:
        raise SystemExit("usage: session_commit_guard_test.py OUTPUT_DIR")
    out = Path(argv[1])
    out.mkdir(parents=True)
    report = {
        "unrelated": test_unrelated_replies(out),
        "controls": test_controls(out),
        "pending_guard": test_pending_guard(out),
        "explicit_release": test_explicit_release(out),
        "port_reattach": test_port_reattach(out),
    }
    (out / "request-order.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print("session commit guard passed")


if __name__ == "__main__":
    main(sys.argv)
