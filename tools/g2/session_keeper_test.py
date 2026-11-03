"""Offline session-flow tests through mwcp.Client.

The serial port and the clock are fakes. mwcp.Client still encodes, writes,
and decodes real frames. No hardware, no network, and no 20/50 s wall sleep.
"""

from __future__ import annotations

import json
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path

import mwcp
import session_flow as sf


BOOT = "dcda0cf8f274468f13b0d417f86ec114"
DEVICE = "dcda0cf8f274"


class Pipe:
    def __init__(self, device: "Device") -> None:
        self.device = device
        self.rx = bytearray()
        self.closed = False
        self.acc = bytearray()

    def write(self, data: bytes) -> None:
        if self.closed:
            raise OSError("port closed")
        self.acc.extend(data)
        self._drain()

    def _drain(self) -> None:
        while 0 in self.acc:
            cut = self.acc.index(0)
            block = bytes(self.acc[:cut])
            del self.acc[: cut + 1]
            if not block:
                continue
            decoded = mwcp.cobs_decode(block)
            if not decoded:
                continue
            frame = mwcp.decode_decoded(decoded)
            if frame:
                self.device.on_frame(frame)

    def read(self, n: int) -> bytes:
        if self.closed:
            raise OSError("port closed")
        out = bytes(self.rx[:n])
        del self.rx[:n]
        return out

    @property
    def in_waiting(self) -> int:
        if self.closed:
            raise OSError("port closed")
        return len(self.rx)

    def close(self) -> None:
        self.closed = True


class Device:
    def __init__(self, clock: sf.FakeClock) -> None:
        self.clock = clock
        self.pipe: Pipe | None = None
        self.session_id = 0
        self.generation = 0
        self.touched: int | None = None
        self.revision = "149"
        self.x = 30
        self.commits: list[dict] = []
        self.requests: list[dict] = []
        self.seq = 1
        self.drop_commit = False
        self.stall_commit_ms = 0
        self.stall_read_ms = 0
        self.hide_status = False
        self.close_after_commit = False
        self.reenter = None
        self.saw_busy = False

    def bind(self, pipe: Pipe) -> None:
        self.pipe = pipe

    def on_frame(self, frame: dict) -> None:
        payload = json.loads(frame["payload"].decode("utf-8"))
        name = next(key for key, code in mwcp.CODE.items() if code == frame["code"])
        self.requests.append({
            "name": name,
            "session_id": frame["session_id"],
            "request_id": frame["request_id"],
            "body": payload,
        })
        if name != "HELLO" and not self._accept(frame["session_id"]):
            return
        if name == "HELLO":
            self.generation += 1
            self.session_id = 4096 + self.generation
            self.touched = self.clock.now_ms()
            self._reply(frame, {
                "nonce": payload["nonce"],
                "protocol": {"major": 1, "minor": 0},
                "boot_id": BOOT,
                "session_ttl_ms": 15000,
                "limits": {"max_payload": 4096, "rpc_inflight": 1},
                "identity": {"device_id": DEVICE, "configured_model": "r60abd1", "dimension": "2D"},
                "cap_revision": "r60-cap-1",
            })
            return
        self.touched = self.clock.now_ms()
        if self.reenter is not None and name == "PING":
            try:
                self.reenter()
            except sf.InflightBusy:
                self.saw_busy = True
        if name == "PING":
            self._reply(frame, {"uptime_ms": self.clock.now_ms()})
            return
        if name == "CONFIG_READ":
            if self.stall_read_ms:
                self.clock.sleep_ms(self.stall_read_ms)
                self.stall_read_ms = 0
            self._reply(frame, self._page(payload.get("cursor")))
            return
        if name == "CONFIG_COMMIT":
            self._commit(frame, payload)
            return
        if name == "COMMIT_STATUS":
            op_id = payload.get("op_id")
            found = any(item["op_id"] == op_id for item in self.commits)
            if self.hide_status:
                found = False
            rev = next((item["revision"] for item in self.commits if item["op_id"] == op_id), None)
            self._reply(frame, {
                "found": found,
                "revision": rev if found else None,
                "current_revision": self.revision,
            })
            return
        raise AssertionError(name)

    def _accept(self, session_id: int) -> bool:
        if session_id != self.session_id or session_id == 0:
            return False
        if self.touched is None or self.clock.now_ms() - self.touched >= sf.SESSION_TTL_MS:
            return False
        return True

    def _page(self, cursor) -> dict:
        pages = [
            [{"key": "install.x_cm", "value": self.x}, {"key": "install.y_cm", "value": 0}],
            [{"key": "install.z_cm", "value": 50}],
        ]
        index = 0
        own = f"cfg:{self.session_id}:2:{self.revision}"
        if cursor == own:
            index = 1
        elif cursor not in (None,):
            index = 0
        nxt = own if index == 0 else None
        return {"revision": self.revision, "items": pages[index], "next_cursor": nxt}

    def _commit(self, frame: dict, payload: dict) -> None:
        op_id = payload["op_id"]
        if payload.get("base_revision") != self.revision:
            self._reply(frame, None, ok=False, error={
                "code": "REVISION_CONFLICT",
                "message": "Configuration changed",
                "field": "base_revision",
                "details": {"current_revision": self.revision},
            })
            return
        if not any(item["op_id"] == op_id for item in self.commits):
            self.revision = str(int(self.revision) + 1)
            if "install.x_cm" in payload["changes"]:
                self.x = payload["changes"]["install.x_cm"]
            self.commits.append({"op_id": op_id, "revision": self.revision, "body": payload})
        if self.stall_commit_ms:
            self.clock.sleep_ms(self.stall_commit_ms)
            self.stall_commit_ms = 0
        if self.close_after_commit:
            self.pipe.closed = True
            return
        if self.drop_commit:
            self.drop_commit = False
            return
        self._reply(frame, {
            "op_id": op_id,
            "revision": self.revision,
            "persisted": True,
            "restart_required": False,
        })

    def _reply(self, frame: dict, result, ok: bool = True, error: dict | None = None) -> None:
        if ok:
            body = {"ok": True, "result": result}
        else:
            body = {"ok": False, "error": error}
        raw = json.dumps(body, separators=(",", ":")).encode("utf-8")
        wire = mwcp.encode_frame(
            mwcp.KIND_RESPONSE, self.session_id, frame["request_id"], frame["code"], raw, self.seq
        )
        self.seq += 1
        self.pipe.rx.extend(wire)

    def names(self) -> list[str]:
        return [item["name"] for item in self.requests]

    def commit_frames(self) -> int:
        return sum(1 for item in self.requests if item["name"] == "CONFIG_COMMIT")

    def assert_ids(self) -> None:
        grouped: dict[int, list[int]] = {}
        for item in self.requests:
            if item["name"] == "HELLO":
                assert item["request_id"] == 1
                continue
            grouped.setdefault(item["session_id"], []).append(item["request_id"])
        for ids in grouped.values():
            assert ids == sorted(ids) and len(ids) == len(set(ids)) and ids[0] >= 2


@contextmanager
def patched(clock: sf.FakeClock):
    old = (time.monotonic, time.time, time.sleep)
    time.monotonic = clock.monotonic
    time.time = clock.time
    time.sleep = clock.sleep
    try:
        yield
    finally:
        time.monotonic, time.time, time.sleep = old


def open_flow(device: Device, clock: sf.FakeClock, directory: str, allow_write: bool = True):
    evidence = mwcp.EvidenceWriter(Path(directory) / f"ev-{len(list(Path(directory).glob('ev-*')))}.jsonl", mwcp.Redactor())
    pipe = Pipe(device)
    device.bind(pipe)
    client = mwcp.Client("TEST", evidence, allow_write=allow_write, ser=pipe)
    flow = sf.SessionFlow(client, clock)
    hello = flow.hello()
    assert client.session_id == device.session_id
    assert client.session_id not in hello
    assert client.boot_id == BOOT
    assert client.device_id == DEVICE
    return flow, evidence


def test_keepalive_spans_ha_waits() -> None:
    for wait_ms in (20000, 50000):
        clock = sf.FakeClock()
        device = Device(clock)
        with tempfile.TemporaryDirectory() as directory, patched(clock):
            started = time.perf_counter()
            flow, evidence = open_flow(device, clock, directory)
            flow.wait(wait_ms, keepalive=True)
            elapsed = time.perf_counter() - started
            assert elapsed < 1.0, elapsed
            assert clock.now_ms() >= wait_ms
            assert flow.session_live()
            assert "PING" in device.names()
            body = flow.read_config()
            assert body["revision"] == "149"
            assert flow.client.boot_id == BOOT
            device.assert_ids()
            evidence.close()
            flow.client.close()


def test_no_keepalive_expires_without_reset() -> None:
    clock = sf.FakeClock()
    device = Device(clock)
    with tempfile.TemporaryDirectory() as directory, patched(clock):
        flow, evidence = open_flow(device, clock, directory)
        session = flow.session_id
        flow.wait(20000, keepalive=False)
        assert "PING" not in device.names()
        try:
            flow.read_page(None)
        except sf.ClassifiedTimeout as ex:
            assert ex.kind == sf.SESSION_EXPIRED
        else:
            raise AssertionError("expired read was sent")
        assert device.names().count("CONFIG_READ") == 0
        assert flow.session_id == session
        assert not hasattr(flow, "reset")
        device.assert_ids()
        evidence.close()
        flow.client.close()


def test_rehello_restores_read() -> None:
    for wait_ms in (20000, 50000):
        clock = sf.FakeClock()
        device = Device(clock)
        with tempfile.TemporaryDirectory() as directory, patched(clock):
            started = time.perf_counter()
            flow, evidence = open_flow(device, clock, directory)
            first = flow.session_id
            body = flow.recover_after_block(wait_ms)
            assert time.perf_counter() - started < 1.0
            assert flow.session_id != first
            assert flow.client.boot_id == BOOT
            assert body["revision"] == "149"
            assert [item["key"] for item in body["items"]] == ["install.x_cm", "install.y_cm", "install.z_cm"]
            device.assert_ids()
            evidence.close()
            flow.client.close()


def test_pagination_restarts_after_new_session() -> None:
    clock = sf.FakeClock()
    device = Device(clock)
    with tempfile.TemporaryDirectory() as directory, patched(clock):
        flow, evidence = open_flow(device, clock, directory)
        device.stall_read_ms = 20000
        body = flow.read_config()
        assert [item["key"] for item in body["items"]] == ["install.x_cm", "install.y_cm", "install.z_cm"]
        hellos = [i for i, item in enumerate(device.requests) if item["name"] == "HELLO"]
        assert len(hellos) == 2
        after = device.requests[hellos[1] + 1 :]
        assert after[0]["name"] == "CONFIG_READ" and after[0]["body"]["cursor"] is None
        old = f"cfg:{4096 + 1}:"
        assert all(old not in json.dumps(item["body"]) for item in after)
        device.assert_ids()
        evidence.close()
        flow.client.close()


def test_unknown_commit_is_not_replayed() -> None:
    clock = sf.FakeClock()
    device = Device(clock)
    device.drop_commit = True
    with tempfile.TemporaryDirectory() as directory, patched(clock):
        flow, evidence = open_flow(device, clock, directory, allow_write=True)
        outcome = flow.commit("op-7", "149", {"install.x_cm": 31})
        assert outcome["result"] == sf.RESULT_UNKNOWN
        assert outcome["replayed"] is False
        assert outcome["executed"] is None
        assert outcome["op_id"] == "op-7"
        assert outcome["found"] is True
        assert outcome["config"]["revision"] == "150"
        assert device.commit_frames() == 1
        assert device.names().count("COMMIT_STATUS") == 1
        device.assert_ids()
        evidence.close()
        flow.client.close()


def test_port_closed_does_not_query_or_reset() -> None:
    clock = sf.FakeClock()
    device = Device(clock)
    device.close_after_commit = True
    with tempfile.TemporaryDirectory() as directory, patched(clock):
        flow, evidence = open_flow(device, clock, directory, allow_write=True)
        outcome = flow.commit("op-9", "149", {"install.x_cm": 32})
        assert outcome["kind"] == sf.PORT_CLOSED
        assert outcome["executed"] is None
        assert device.commit_frames() == 1
        held = flow.recover()
        assert held["queried"] is False
        assert device.names().count("COMMIT_STATUS") == 0
        stopped = len(device.requests)
        evidence.close()
        flow.client.close()
        evidence2 = mwcp.EvidenceWriter(Path(directory) / "ev-reconnect.jsonl", mwcp.Redactor())
        pipe = Pipe(device)
        device.bind(pipe)
        client = mwcp.Client("TEST", evidence2, allow_write=True, ser=pipe)
        flow.attach(client)
        queried = flow.recover()
        assert queried["queried"] is True
        assert queried["op_id"] == "op-9"
        assert queried["found"] is True
        assert queried["replayed"] is False
        assert device.commit_frames() == 1
        assert device.requests[stopped]["name"] == "HELLO"
        assert "COMMIT_STATUS" in device.names()
        device.assert_ids()
        evidence2.close()
        client.close()


def test_one_inflight() -> None:
    clock = sf.FakeClock()
    device = Device(clock)
    with tempfile.TemporaryDirectory() as directory, patched(clock):
        flow, evidence = open_flow(device, clock, directory)
        device.reenter = flow.read_page
        flow.ping()
        assert device.saw_busy is True
        assert device.names().count("CONFIG_READ") == 0
        device.assert_ids()
        evidence.close()
        flow.client.close()


def test_continuous_reads_refresh_activity() -> None:
    clock = sf.FakeClock()
    device = Device(clock)
    with tempfile.TemporaryDirectory() as directory, patched(clock):
        flow, evidence = open_flow(device, clock, directory)
        first = flow.last_activity_ms
        for _ in range(4):
            clock.sleep_ms(5000)
            before = clock.now_ms()
            flow.read_page(None)
            assert flow.last_activity_ms == before
            assert flow.session_live()
        assert clock.now_ms() - first > sf.SESSION_TTL_MS
        device.assert_ids()
        evidence.close()
        flow.client.close()


def test_executed_commit_timeout_crosses_ttl() -> None:
    clock = sf.FakeClock()
    device = Device(clock)
    device.drop_commit = True
    device.stall_commit_ms = 16000
    with tempfile.TemporaryDirectory() as directory, patched(clock):
        flow, evidence = open_flow(device, clock, directory, allow_write=True)
        outcome = flow.commit("audit-op", "149", {"install.x_cm": 31})
        assert outcome["result"] == sf.RESULT_UNKNOWN
        assert outcome["executed"] is None
        assert outcome["found"] is True
        assert outcome["status"]["revision"] == "150"
        assert outcome["base_revision"] == "149"
        assert device.commit_frames() == 1
        assert device.revision == "150"
        assert device.names().count("COMMIT_STATUS") == 1
        assert device.names().count("HELLO") == 2
        device.assert_ids()
        evidence.close()
        flow.client.close()


def test_expired_before_write_handshakes_once() -> None:
    clock = sf.FakeClock()
    device = Device(clock)
    with tempfile.TemporaryDirectory() as directory, patched(clock):
        flow, evidence = open_flow(device, clock, directory, allow_write=True)
        flow.wait(20000, keepalive=False)
        op_id = "22222222-2222-4222-8222-222222222222"
        outcome = flow.commit(op_id, "149", {"install.x_cm": 33})
        assert outcome["result"] == "known"
        assert device.commit_frames() == 1
        assert device.names().count("HELLO") == 2
        commit = next(item for item in device.requests if item["name"] == "CONFIG_COMMIT")
        assert commit["body"]["base_revision"] == "149"
        assert commit["body"]["op_id"] == op_id
        device.assert_ids()
        evidence.close()
        flow.client.close()


def test_cas_conflict_is_not_retried() -> None:
    clock = sf.FakeClock()
    device = Device(clock)
    with tempfile.TemporaryDirectory() as directory, patched(clock):
        flow, evidence = open_flow(device, clock, directory, allow_write=True)
        outcome = flow.commit("op-stale", "148", {"install.x_cm": 140})
        assert outcome["result"] == "known_failure"
        assert outcome["body"]["error"]["code"] == "REVISION_CONFLICT"
        assert device.revision == "149"
        assert device.commit_frames() == 1
        assert device.names().count("COMMIT_STATUS") == 0
        body = next(item["body"] for item in device.requests if item["name"] == "CONFIG_COMMIT")
        assert body["base_revision"] == "148"
        assert body["op_id"] == "op-stale"
        device.assert_ids()
        evidence.close()
        flow.client.close()


def test_status_not_found_is_not_not_executed() -> None:
    clock = sf.FakeClock()
    device = Device(clock)
    device.drop_commit = True
    device.hide_status = True
    with tempfile.TemporaryDirectory() as directory, patched(clock):
        flow, evidence = open_flow(device, clock, directory, allow_write=True)
        outcome = flow.commit("op-hidden", "149", {"install.x_cm": 34})
        assert outcome["result"] == sf.RESULT_UNKNOWN
        assert outcome["found"] is False
        assert outcome["executed"] is None
        assert outcome["status"]["current_revision"] == "150"
        assert device.commit_frames() == 1
        device.assert_ids()
        evidence.close()
        flow.client.close()


def test_slow_response_does_not_refresh_from_arrival() -> None:
    clock = sf.FakeClock()
    device = Device(clock)
    with tempfile.TemporaryDirectory() as directory, patched(clock):
        flow, evidence = open_flow(device, clock, directory)
        device.stall_read_ms = 16000
        before = clock.now_ms()
        page = flow.read_page(None)
        assert page["revision"] == "149"
        assert flow.last_activity_ms == before
        assert clock.now_ms() - flow.last_activity_ms >= 16000
        assert not flow.session_live()
        device.assert_ids()
        evidence.close()
        flow.client.close()


def _public_trace() -> dict:
    """Request names and CAS fields only. No evidence files are kept."""
    samples = {}
    clock = sf.FakeClock()
    device = Device(clock)
    device.drop_commit = True
    device.stall_commit_ms = 16000
    with tempfile.TemporaryDirectory() as directory, patched(clock):
        flow, evidence = open_flow(device, clock, directory, allow_write=True)
        flow.commit("audit-op", "149", {"install.x_cm": 31})
        samples["ttl_crossed_commit"] = [
            {"name": item["name"], "body": item["body"], "session_id": item["session_id"]}
            for item in device.requests
        ]
        evidence.close()
        flow.client.close()
    return samples


def main() -> None:
    started = time.perf_counter()
    test_keepalive_spans_ha_waits()
    test_no_keepalive_expires_without_reset()
    test_rehello_restores_read()
    test_pagination_restarts_after_new_session()
    test_unknown_commit_is_not_replayed()
    test_port_closed_does_not_query_or_reset()
    test_one_inflight()
    test_continuous_reads_refresh_activity()
    test_executed_commit_timeout_crosses_ttl()
    test_expired_before_write_handshakes_once()
    test_cas_conflict_is_not_retried()
    test_status_not_found_is_not_not_executed()
    test_slow_response_does_not_refresh_from_arrival()
    out = Path(r"D:/Users/zomco/Documents/GitHub/mmwave-workspace/tmp/g2-session-20261103-r26a")
    out.mkdir(parents=True, exist_ok=True)
    (out / "offline-trace.json").write_text(json.dumps(_public_trace(), indent=2) + "\n", encoding="utf-8")
    elapsed = time.perf_counter() - started
    assert elapsed < 5.0, elapsed
    print(f"session flow test passed ({elapsed:.3f}s)")


if __name__ == "__main__":
    main()
