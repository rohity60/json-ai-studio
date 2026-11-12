"""In-memory stand-in for the Anna host (storage, files, sampling)."""

from __future__ import annotations

import json
from typing import Any

import httpx

from jstudio.rpc import HostError


class FakeHost:
    """Implements ``call``/``progress`` like ``HostRpc``, without stdio."""

    def __init__(self) -> None:
        self.kv: dict[str, Any] = {}
        self.objects: dict[str, bytes] = {}
        self.replies: list[dict[str, Any] | HostError] = []
        self.sampling_calls: list[dict[str, Any]] = []
        self.progress_events: list[dict[str, Any]] = []
        self.methods: list[str] = []

    # --- HostRpc surface --------------------------------------------------

    async def call(self, method: str, params: dict[str, Any], timeout: float = 60.0):
        self.methods.append(method)
        return self.handle(method, params)

    def progress(self, data: dict[str, Any]) -> None:
        self.progress_events.append(data)

    # --- host behaviour ---------------------------------------------------

    def handle(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        if method == "storage/get":
            key = params["key"]
            if key in self.kv:
                return {"value": self.kv[key], "exists": True, "etag": "e"}
            return {"value": None, "exists": False, "etag": None}
        if method == "storage/set":
            size = len(json.dumps(params["value"]).encode())
            if size > 64 * 1024:
                raise HostError(-32025, "VALUE_TOO_LARGE")
            self.kv[params["key"]] = json.loads(json.dumps(params["value"]))
            return {"etag": "e", "size_bytes": size}
        if method == "storage/delete":
            self.kv.pop(params["key"], None)
            return {"deleted": True}
        if method == "files/upload_begin":
            return {"put_url": f"https://objects.test/{params['path']}", "headers": {}}
        if method == "files/upload_complete":
            return {"path": params["path"], "etag": "o"}
        if method == "files/download_url":
            return {"url": f"https://objects.test/{params['path']}"}
        if method == "files/delete":
            self.objects.pop(params["path"], None)
            return {"deleted": True}
        if method == "sampling/createMessage":
            self.sampling_calls.append(params)
            reply = self.replies.pop(0)
            if isinstance(reply, HostError):
                raise reply
            return {
                "role": "assistant",
                "content": {"type": "text", "text": json.dumps(reply)},
                "model": "fake-model",
                "stopReason": "endTurn",
                "usage": {"inputTokens": 50, "outputTokens": 20, "totalTokens": 70},
            }
        raise HostError(-32601, f"method not found: {method}")

    def transport(self) -> httpx.MockTransport:
        """Serves the presigned object URLs handed out above."""

        def handler(request: httpx.Request) -> httpx.Response:
            path = request.url.path.lstrip("/")
            if request.method == "PUT":
                self.objects[path] = request.content
                return httpx.Response(200, headers={"etag": "o"})
            if path in self.objects:
                return httpx.Response(200, content=self.objects[path])
            return httpx.Response(404)

        return httpx.MockTransport(handler)
