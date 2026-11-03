"""Controlled MWCP session path on top of one mwcp.Client.

This is the replacement for the unused FakeDevice keeper. It calls the real
client methods: hello() (session id stays on the instance), ping(), and
call(name, payload). CONFIG_COMMIT and the COMMIT_STATUS that can release a
pending write go out once, through raw_request_strict, so a lost response is
not sent again with a new op_id. The strict call keeps the frame's kind,
session, code, and request id; raw_request itself is unchanged.

A legal request refreshes local activity at send time. A slow response does
not move that timestamp forward. A write that has already been sent stays
unknown if it times out, even when the 15 s TTL has also elapsed. The original
op_id and base_revision are what COMMIT_STATUS and a fresh CONFIG_READ use.
An unresolved write blocks the next commit until that op is confirmed or the
caller explicitly releases it.
"""

from __future__ import annotations

import re
import time

import mwcp

SESSION_TTL_MS = 15000
PING_INTERVAL_MS = 5000
COMMIT_TIMEOUT_MS = 2000

SESSION_EXPIRED = "session_expired"
PORT_CLOSED = "port_closed"
PROTOCOL_ERROR = "protocol_error"
RESULT_UNKNOWN = "result_unknown"
CONFIRM_PREVIOUS = "confirm the previous save first"

_REVISION = re.compile(r"^[0-9]+$")
_OP_ID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
_ERROR_CODES = frozenset({
    "VERSION_UNSUPPORTED",
    "LIMIT_UNSUPPORTED",
    "UNSUPPORTED",
    "INVALID_ARGUMENT",
    "UNKNOWN_FIELD",
    "OUT_OF_RANGE",
    "PAYLOAD_TOO_LARGE",
    "ID_REUSE",
    "OP_ID_REUSE",
    "REQUEST_EXPIRED",
    "REVISION_CONFLICT",
    "BUSY",
    "RADAR_UNAVAILABLE",
    "RADAR_TIMEOUT",
    "VERIFY_FAILED",
    "STORAGE_FAILED",
    "RATE_LIMITED",
    "INTERNAL_ERROR",
})


class ClassifiedTimeout(Exception):
    def __init__(self, kind: str):
        super().__init__(kind)
        self.kind = kind


class InflightBusy(Exception):
    pass


class FakeClock:
    """Injected clock. sleep advances this clock and does not wait on the wall."""

    def __init__(self) -> None:
        self.ms = 0.0

    def now_ms(self) -> int:
        return int(self.ms)

    def sleep_ms(self, ms: int) -> None:
        if ms < 0:
            raise ValueError("negative wait")
        self.ms += ms

    def monotonic(self) -> float:
        return self.ms / 1000.0

    def time(self) -> float:
        return 1_700_000_000.0 + self.ms / 1000.0

    def sleep(self, seconds: float) -> None:
        if seconds < 0:
            raise ValueError("negative wait")
        self.ms += float(seconds) * 1000.0


class MonotonicClock:
    """Production clock. Tests pass FakeClock instead of sleeping for real."""

    def now_ms(self) -> int:
        return int(time.monotonic() * 1000)

    def sleep_ms(self, ms: int) -> None:
        if ms < 0:
            raise ValueError("negative wait")
        time.sleep(ms / 1000.0)


class SessionFlow:
    def __init__(self, client: mwcp.Client, clock=None) -> None:
        self.client = client
        self.clock = clock or MonotonicClock()
        self.last_activity_ms: int | None = None
        self.epoch = 0
        self.link_open = True
        self.pending: dict | None = None
        self.release_log: list[dict] = []
        self._inflight = False
        self._pages: list = []
        self._cursor_epoch = -1

    @property
    def session_id(self) -> int:
        return int(self.client.session_id or 0)

    def session_live(self) -> bool:
        if self.session_id == 0 or self.last_activity_ms is None:
            return False
        return self.clock.now_ms() - self.last_activity_ms < SESSION_TTL_MS

    def hello(self) -> dict:
        if not self.link_open:
            raise ClassifiedTimeout(PORT_CLOSED)
        sent = self.clock.now_ms()
        with self._owned():
            try:
                result = self.client.hello(timeout_ms=3000, client_name="session-flow")
            except TimeoutError:
                raise
            except OSError as ex:
                self.link_open = False
                raise ClassifiedTimeout(PORT_CLOSED) from ex
        if not self.client.session_id:
            raise ClassifiedTimeout(SESSION_EXPIRED)
        self.last_activity_ms = sent
        self.epoch += 1
        self._pages = []
        self._cursor_epoch = -1
        return result

    def ping(self) -> dict:
        self._require_live()
        resp, sent = self._rpc("PING", {})
        self._accept(resp)
        self.last_activity_ms = sent
        return resp

    def wait(self, ms: int, keepalive: bool = True) -> None:
        """Same thread. keepalive=False is the blocked-HA case: HELLO afterwards."""
        if ms < 0:
            raise ValueError("negative wait")
        end = self.clock.now_ms() + ms
        while self.clock.now_ms() < end:
            if not keepalive or not self.session_live():
                self.clock.sleep_ms(end - self.clock.now_ms())
                return
            due = self.last_activity_ms + PING_INTERVAL_MS
            if self.clock.now_ms() >= due:
                self.ping()
                continue
            self.clock.sleep_ms(min(end, due) - self.clock.now_ms())
            if self.clock.now_ms() < end and self.clock.now_ms() >= due and self.session_live():
                self.ping()

    def recover_after_block(self, ms: int) -> dict:
        """External wait with no background reader, then a new session and a fresh read."""
        self.wait(ms, keepalive=False)
        self.hello()
        return self.read_config()

    def read_page(self, cursor=None) -> dict:
        """One CONFIG_READ. A cursor from another session is discarded, not incremented."""
        self._require_live()
        if cursor is not None and self._cursor_epoch != self.epoch:
            cursor = None
        resp, sent = self._rpc("CONFIG_READ", {"cursor": cursor})
        self.last_activity_ms = sent
        self._accept(resp)
        result = resp.get("result") if isinstance(resp, dict) else None
        if not isinstance(result, dict):
            raise mwcp.ProtocolError("CONFIG_READ result missing")
        self._cursor_epoch = self.epoch
        return result

    def read_config(self) -> dict:
        """Read every page. A new session starts at cursor null and drops partial pages."""
        items: list = []
        cursor = None
        revision = None
        restarts = 0
        while True:
            if not self.session_live():
                if restarts >= 1:
                    raise ClassifiedTimeout(SESSION_EXPIRED)
                restarts += 1
                items = []
                cursor = None
                revision = None
                self._pages = []
                self.hello()
                continue
            result = self.read_page(cursor)
            page_rev = result.get("revision")
            page_items = result.get("items") or []
            if revision is None:
                revision = page_rev
            elif page_rev != revision:
                items = []
                cursor = None
                revision = None
                self._pages = []
                continue
            items.extend(page_items)
            self._pages = list(items)
            nxt = result.get("next_cursor")
            if not nxt:
                return {"revision": revision, "items": items}
            cursor = nxt

    def commit(self, op_id: str, base_revision: str, changes: dict) -> dict:
        """One CONFIG_COMMIT. CAS fields stay in the body. No second op_id."""
        if not self.link_open:
            raise ClassifiedTimeout(PORT_CLOSED)
        if self.pending is not None:
            return self._reject_pending()
        if not self.session_live():
            self.hello()
        body = {"base_revision": str(base_revision), "op_id": op_id, "changes": changes}
        self.pending = {
            "op_id": op_id,
            "base_revision": str(base_revision),
            "changes": dict(changes),
            "sent": False,
        }
        try:
            resp, sent = self._rpc("CONFIG_COMMIT", body, timeout_ms=COMMIT_TIMEOUT_MS)
        except TimeoutError:
            self.pending["sent"] = True
            return self._resolve_pending()
        except ClassifiedTimeout as ex:
            if ex.kind == PORT_CLOSED:
                self.pending["sent"] = True
                return {
                    "result": RESULT_UNKNOWN,
                    "kind": PORT_CLOSED,
                    "op_id": op_id,
                    "replayed": False,
                    "executed": None,
                }
            raise
        except mwcp.ProtocolError:
            if getattr(self.client, "_strict_sent", False) and self.pending is not None:
                self.pending["sent"] = True
                return self._resolve_pending(PROTOCOL_ERROR)
            self.pending = None
            raise
        self.last_activity_ms = sent
        if self._commit_success(resp, op_id, str(base_revision)):
            self.pending = None
            return {"result": "known", "op_id": op_id, "body": resp, "replayed": False}
        if self._commit_failure(resp):
            self.pending = None
            return {"result": "known_failure", "op_id": op_id, "body": resp, "replayed": False}
        self.pending["sent"] = True
        return self._resolve_pending(PROTOCOL_ERROR)

    def release_pending(self, reason: str) -> dict:
        """Stop tracking the unresolved write. Does not claim it never ran."""
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError("release reason required")
        if self.pending is None:
            record = {"result": "absent", "released": False, "executed": None, "reason": reason}
            self.release_log.append(record)
            return record
        held = self.pending
        record = {
            "result": "released",
            "released": True,
            "op_id": held["op_id"],
            "base_revision": held["base_revision"],
            "changes": dict(held["changes"]),
            "reason": reason,
            "executed": None,
            "replayed": False,
            "queried": False,
        }
        self.release_log.append(record)
        self.pending = None
        return record

    def _reject_pending(self) -> dict:
        held = self.pending or {}
        return {
            "result": "rejected",
            "status": CONFIRM_PREVIOUS,
            "op_id": held.get("op_id"),
            "base_revision": held.get("base_revision"),
            "changes": dict(held.get("changes") or {}),
            "sent": False,
            "replayed": False,
            "executed": None,
        }

    def attach(self, client: mwcp.Client) -> None:
        """A new open port. Pending writes stay; the old cursor does not."""
        self.client = client
        self.link_open = True
        self.last_activity_ms = None
        self.epoch += 1
        self._pages = []
        self._cursor_epoch = -1

    def recover(self) -> dict | None:
        """Query a pending write. Does nothing if the port is still closed."""
        if self.pending is None:
            return None
        if not self.link_open:
            return {
                "result": RESULT_UNKNOWN,
                "kind": PORT_CLOSED,
                "op_id": self.pending["op_id"],
                "queried": False,
                "replayed": False,
                "executed": None,
            }
        return self._resolve_pending()

    def _resolve_pending(self, kind: str | None = None) -> dict:
        pending = self.pending or {}
        op_id = pending.get("op_id")
        if not self.link_open:
            return {
                "result": RESULT_UNKNOWN,
                "kind": PORT_CLOSED,
                "op_id": op_id,
                "queried": False,
                "replayed": False,
                "executed": None,
            }
        if not self.session_live():
            self.hello()
        try:
            status_resp, sent = self._rpc("COMMIT_STATUS", {"op_id": op_id})
        except TimeoutError:
            return self._status_kept(pending, kind or "query_failed")
        except ClassifiedTimeout as ex:
            if ex.kind != PORT_CLOSED:
                raise
            return self._status_kept(pending, PORT_CLOSED, queried=False)
        self.last_activity_ms = sent
        status = self._status_result(status_resp)
        if status is None:
            return self._status_kept(pending, kind or "query_failed")
        config = self.read_config()
        found = status.get("found") is True
        # found false does not prove the write never ran, and does not drop the record.
        # Config readback is not a substitute for this status result.
        if self._status_confirms(status):
            self.pending = None
        out = {
            "result": RESULT_UNKNOWN,
            "op_id": op_id,
            "base_revision": pending.get("base_revision"),
            "status": status,
            "config": config,
            "found": found,
            "queried": True,
            "replayed": False,
            "executed": None,
        }
        if kind:
            out["kind"] = kind
        return out

    def _status_kept(self, pending: dict, kind: str, queried: bool = True) -> dict:
        """Query failed or the port closed. The original write stays unconfirmed."""
        return {
            "result": RESULT_UNKNOWN,
            "kind": kind,
            "op_id": pending.get("op_id"),
            "base_revision": pending.get("base_revision"),
            "found": False,
            "queried": queried,
            "replayed": False,
            "executed": None,
        }

    def _commit_success(self, body: dict, op_id: str, base_revision: str) -> bool:
        if not isinstance(body, dict) or set(body) != {"ok", "result"} or body.get("ok") is not True:
            return False
        result = body.get("result")
        if not isinstance(result, dict):
            return False
        if set(result) != {"op_id", "revision", "persisted", "restart_required"}:
            return False
        if result.get("op_id") != op_id or _OP_ID.fullmatch(op_id or "") is None:
            return False
        revision = result.get("revision")
        if not self._revision_text(revision) or not self._revision_text(base_revision):
            return False
        if int(revision) <= int(base_revision):
            return False
        return result.get("persisted") is True and result.get("restart_required") is False

    def _commit_failure(self, body: dict) -> bool:
        if not isinstance(body, dict) or set(body) != {"ok", "error"} or body.get("ok") is not False:
            return False
        error = body.get("error")
        if not isinstance(error, dict):
            return False
        if not {"code", "message"} <= set(error) <= {"code", "message", "field", "details"}:
            return False
        if error.get("code") not in _ERROR_CODES:
            return False
        message = error.get("message")
        if not isinstance(message, str) or not message or len(message.encode("utf-8")) > 160:
            return False
        if "field" in error:
            field = error.get("field")
            if not isinstance(field, str) or len(field.encode("utf-8")) > 64:
                return False
        details = error.get("details")
        if "details" in error and (not isinstance(details, dict) or len(details) > 16):
            return False
        return True

    @staticmethod
    def _status_result(body) -> dict | None:
        """Inner COMMIT_STATUS result. No op_id field: the frame identity is the query."""
        if not isinstance(body, dict) or set(body) != {"ok", "result"} or body.get("ok") is not True:
            return None
        result = body.get("result")
        if not isinstance(result, dict) or set(result) != {"found", "revision", "current_revision"}:
            return None
        if not isinstance(result.get("found"), bool):
            return None
        if not SessionFlow._revision_or_null(result.get("revision")):
            return None
        if not SessionFlow._revision_or_null(result.get("current_revision")):
            return None
        return result

    def _status_confirms(self, status: dict) -> bool:
        if status.get("found") is not True:
            return False
        return self._revision_text(status.get("revision")) and self._revision_text(status.get("current_revision"))

    @staticmethod
    def _revision_text(value) -> bool:
        return isinstance(value, str) and _REVISION.fullmatch(value) is not None and len(value.encode("utf-8")) <= 20

    @staticmethod
    def _revision_or_null(value) -> bool:
        return value is None or SessionFlow._revision_text(value)

    def _rpc(self, name: str, payload: dict, timeout_ms: int = 1000):
        if not self.link_open:
            raise ClassifiedTimeout(PORT_CLOSED)
        sent = self.clock.now_ms()
        with self._owned():
            try:
                if name == "CONFIG_COMMIT":
                    resp = self._commit_once(payload, timeout_ms)
                elif name == "COMMIT_STATUS":
                    resp = self._status_once(payload, timeout_ms)
                else:
                    resp = self.client.call(name, payload, timeout_ms=timeout_ms, retry_same=True)
            except TimeoutError:
                raise
            except OSError as ex:
                self.link_open = False
                raise ClassifiedTimeout(PORT_CLOSED) from ex
        return resp, sent

    def _commit_once(self, payload: dict, timeout_ms: int) -> dict:
        """One wire send. The strict call does not retry and does not mint an op_id."""
        self.client._req += 1
        rid = self.client._req + 1
        resp = self.client.raw_request_strict(rid, "CONFIG_COMMIT", payload, timeout_ms=timeout_ms)
        if resp is None:
            raise TimeoutError("CONFIG_COMMIT")
        return resp

    def _status_once(self, payload: dict, timeout_ms: int) -> dict:
        """One COMMIT_STATUS. A bad frame does not finish this wait or clear pending."""
        self.client._req += 1
        rid = self.client._req + 1
        resp = self.client.raw_request_strict(
            rid, "COMMIT_STATUS", payload, timeout_ms=timeout_ms, accept=SessionFlow._status_result,
        )
        if resp is None:
            raise TimeoutError("COMMIT_STATUS")
        return resp

    def _accept(self, resp: dict) -> None:
        if not isinstance(resp, dict) or resp.get("ok") is not True:
            raise mwcp.ProtocolError(f"request failed: {resp!r}"[:200])

    def _require_live(self) -> None:
        if not self.link_open:
            raise ClassifiedTimeout(PORT_CLOSED)
        if not self.session_live():
            raise ClassifiedTimeout(SESSION_EXPIRED)

    def _owned(self):
        flow = self

        class _Guard:
            def __enter__(self):
                if flow._inflight:
                    raise InflightBusy()
                flow._inflight = True
                return self

            def __exit__(self, exc_type, exc, tb):
                flow._inflight = False
                return False

        return _Guard()
