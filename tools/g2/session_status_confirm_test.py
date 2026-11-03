"""COMMIT_STATUS must not clear a pending write on an unrelated frame.

Real mwcp.Client encode/decode, fake byte pipe. Pass an output directory.
Does not call session_keeper_test.main and does not write offline-trace.json.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import mwcp
import session_commit_guard_test as guard
import session_flow as sf
import session_keeper_test as sk


class BadStatus(sk.Device):
    """Applied commit, dropped response, then a bad status frame before the real one."""

    def __init__(self, clock: sf.FakeClock, mode: str, follow: str) -> None:
        super().__init__(clock)
        self.mode = mode
        self.follow = follow
        self.drop_commit = True

    def _reply(self, frame: dict, result, ok: bool = True, error: dict | None = None) -> None:
        if frame["code"] != mwcp.CODE["COMMIT_STATUS"]:
            super()._reply(frame, result, ok, error)
            return
        self._inject(frame)
        if self.follow == "found_false":
            super()._reply(frame, {"found": False, "revision": None, "current_revision": self.revision})
        elif self.follow == "found_true":
            super()._reply(frame, {
                "found": True,
                "revision": self.revision,
                "current_revision": self.revision,
            })

    def _inject(self, frame: dict) -> None:
        if self.mode == "wrong_session":
            sid = self.session_id - 1
            code = frame["code"]
            body = {"ok": True, "result": {"found": True, "revision": "150", "current_revision": "150"}}
        elif self.mode == "wrong_code":
            sid = self.session_id
            code = mwcp.CODE["PING"]
            body = {"ok": True, "result": {"found": True, "revision": "150", "current_revision": "150"}}
        else:
            sid, code = self.session_id, frame["code"]
            body = {"found": True, "revision": "150", "current_revision": "150"}
        raw = json.dumps(body).encode("utf-8")
        self.pipe.rx.extend(mwcp.encode_frame(
            mwcp.KIND_RESPONSE, sid, frame["request_id"], code, raw, self.seq
        ))
        self.seq += 1


def _held(flow, outcome) -> None:
    assert outcome["result"] == sf.RESULT_UNKNOWN
    assert outcome["found"] is not True
    assert outcome["executed"] is None
    assert flow.pending is not None
    assert flow.pending["op_id"] == guard.UNRESOLVED
    assert flow.pending["base_revision"] == "149"
    assert flow.pending["changes"] == {"install.x_cm": 31}


def _reject_next(flow, dev) -> dict:
    sends = dev.commit_frames()
    second = flow.commit(guard.NEW_OP, "150", {"install.x_cm": 32})
    assert second["result"] == "rejected"
    assert second["status"] == sf.CONFIRM_PREVIOUS
    assert second["sent"] is False
    assert dev.commit_frames() == sends == 1
    assert flow.pending["op_id"] == guard.UNRESOLVED
    assert flow.pending["base_revision"] == "149"
    assert flow.pending["changes"] == {"install.x_cm": 31}
    status = [item for item in dev.requests if item["name"] == "COMMIT_STATUS"]
    assert len(status) == 1 and status[0]["body"]["op_id"] == guard.UNRESOLVED
    return {"result": second["result"], "status": second["status"]}


def _probe(mode: str, follow: str):
    def run(flow, dev):
        started = time.perf_counter()
        outcome = flow.commit(guard.UNRESOLVED, "149", {"install.x_cm": 31})
        elapsed = time.perf_counter() - started
        assert elapsed < 2.0, elapsed
        _held(flow, outcome)
        rejected = _reject_next(flow, dev)
        return {
            "confirmed": False,
            "found": outcome["found"],
            "kind": outcome.get("kind"),
            "pending_op": flow.pending["op_id"],
            "rejected": rejected["status"],
        }

    return run


def test_status_counterexamples(out: Path) -> dict:
    found = {}
    for mode in ("wrong_session", "wrong_code", "missing_envelope"):
        clock = sf.FakeClock()
        device = BadStatus(clock, mode, "found_false")
        found[mode] = guard._run(device, clock, out / ("status_" + mode), _probe(mode, "found_false"))
    return found


def test_same_window_confirms(out: Path) -> dict:
    clock = sf.FakeClock()
    device = BadStatus(clock, "wrong_session", "found_true")

    def run(flow, dev):
        outcome = flow.commit(guard.UNRESOLVED, "149", {"install.x_cm": 31})
        assert outcome["found"] is True
        assert outcome["status"]["found"] is True
        assert outcome["executed"] is None
        assert flow.pending is None
        saved = flow.commit(guard.NEW_OP, "150", {"install.x_cm": 32})
        assert saved["result"] == "known"
        assert saved["op_id"] == guard.NEW_OP
        assert dev.commit_frames() == 2
        status = [item for item in dev.requests if item["name"] == "COMMIT_STATUS"]
        assert len(status) == 1 and status[0]["body"]["op_id"] == guard.UNRESOLVED
        return {"found": True, "saved": saved["result"], "saved_op": saved["op_id"]}

    return guard._run(device, clock, out / "status_same_window_confirm", run)


def test_invalid_only_times_out(out: Path) -> dict:
    clock = sf.FakeClock()
    device = BadStatus(clock, "missing_envelope", "none")

    def run(flow, dev):
        started = time.perf_counter()
        outcome = flow.commit(guard.UNRESOLVED, "149", {"install.x_cm": 31})
        elapsed = time.perf_counter() - started
        assert elapsed < 2.0, elapsed
        assert clock.now_ms() < 5000
        _held(flow, outcome)
        assert outcome["kind"] == "query_failed"
        rejected = _reject_next(flow, dev)
        return {"kind": outcome["kind"], "pending_op": flow.pending["op_id"], "rejected": rejected["status"]}

    return guard._run(device, clock, out / "status_invalid_only", run)


def main(argv: list[str]) -> None:
    if len(argv) != 2:
        raise SystemExit("usage: session_status_confirm_test.py OUTPUT_DIR")
    out = Path(argv[1])
    out.mkdir(parents=True, exist_ok=True)
    report = {
        "counterexamples": test_status_counterexamples(out),
        "same_window_confirm": test_same_window_confirms(out),
        "invalid_only": test_invalid_only_times_out(out),
    }
    (out / "status-order.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print("session status confirm passed")


if __name__ == "__main__":
    main(sys.argv)
