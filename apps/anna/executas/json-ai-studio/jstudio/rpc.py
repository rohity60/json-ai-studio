"""Reverse JSON-RPC to the Anna host over the plugin's stdio.

The host speaks line-delimited JSON-RPC 2.0. It sends us requests
(``initialize``, ``describe``, ``invoke``); while an invoke is running we
may send our own requests on stdout (``sampling/createMessage``,
``storage/*``, ``files/*``) and the answers come back on stdin, matched
by ``id``. Progress updates are notifications (no ``id``, no answer).

stdout carries protocol frames only — logs go to stderr.
"""

from __future__ import annotations

import asyncio
import json
import sys
import threading
import uuid
from contextvars import ContextVar
from typing import Any, Callable

_invoke_id: ContextVar[str | None] = ContextVar("anna_invoke_id", default=None)


class HostError(Exception):
    """JSON-RPC error returned by the host for one of our requests."""

    def __init__(self, code: int, message: str, data: dict | None = None) -> None:
        super().__init__(f"[{code}] {message}")
        self.code = code
        self.message = message
        self.data = data or {}


def bind_invoke(invoke_id: str | None):
    """Bind the invoke this task is serving; returns the reset token."""
    return _invoke_id.set(invoke_id)


def unbind_invoke(token) -> None:
    _invoke_id.reset(token)


def current_invoke_id() -> str | None:
    return _invoke_id.get()


class HostRpc:
    """One per process. Thread-safe writer; responses resolved on the loop."""

    def __init__(self, write: Callable[[str], None] | None = None) -> None:
        self._write_line = write or self._stdout_write
        self._lock = threading.Lock()
        self._pending: dict[str, tuple[asyncio.AbstractEventLoop, asyncio.Future]] = {}

    def set_writer(self, write: Callable[[str], None]) -> None:
        """Use `write` for outgoing frames (the plugin's protocol stream)."""
        self._write_line = write

    @staticmethod
    def _stdout_write(line: str) -> None:
        sys.stdout.write(line + "\n")
        sys.stdout.flush()

    def send(self, frame: dict[str, Any]) -> None:
        line = json.dumps(frame, ensure_ascii=False, default=str)
        with self._lock:
            self._write_line(line)

    def reply(self, req_id: Any, result: dict[str, Any]) -> None:
        self.send({"jsonrpc": "2.0", "id": req_id, "result": result})

    def reply_error(self, req_id: Any, code: int, message: str) -> None:
        self.send(
            {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": code, "message": message},
            }
        )

    async def call(
        self, method: str, params: dict[str, Any], timeout: float = 60.0
    ) -> dict[str, Any]:
        """Send a request to the host and wait for its result."""
        params = dict(params)
        invoke_id = current_invoke_id()
        if invoke_id:
            # Correlates the request with the invoke that owns the tokens.
            context = dict(params.get("context") or {})
            context.setdefault("invoke_id", invoke_id)
            params["context"] = context
        rid = uuid.uuid4().hex
        loop = asyncio.get_running_loop()
        future: asyncio.Future = loop.create_future()
        self._pending[rid] = (loop, future)
        try:
            self.send({"jsonrpc": "2.0", "id": rid, "method": method, "params": params})
            return await asyncio.wait_for(future, timeout)
        finally:
            self._pending.pop(rid, None)

    def dispatch_response(self, msg: dict[str, Any]) -> bool:
        """Route a host response to its waiter. Safe from the reader thread."""
        entry = self._pending.get(str(msg.get("id")))
        if entry is None:
            return False
        loop, future = entry

        def resolve() -> None:
            if future.done():
                return
            err = msg.get("error")
            if err:
                future.set_exception(
                    HostError(
                        int(err.get("code", -32603)),
                        str(err.get("message", "host error")),
                        err.get("data") if isinstance(err.get("data"), dict) else None,
                    )
                )
            else:
                future.set_result(msg.get("result") or {})

        loop.call_soon_threadsafe(resolve)
        return True

    def progress(self, data: dict[str, Any]) -> None:
        """Best-effort step update for async jobs; dropped for sync invokes."""
        invoke_id = current_invoke_id()
        if not invoke_id:
            return
        try:
            self.send(
                {
                    "jsonrpc": "2.0",
                    "method": "executa/progress",
                    "params": {
                        "type": "progress",
                        "data": data,
                        "context": {"invoke_id": invoke_id},
                    },
                }
            )
        except Exception:  # progress must never break the tool
            pass


host = HostRpc()
