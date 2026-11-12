"""The plugin as the Anna host runs it: a subprocess speaking JSON-RPC over
stdio. This test plays the host — it sends ``invoke`` and answers the
plugin's own storage and sampling requests."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from fake_host import FakeHost
from jstudio.rpc import HostError

PLUGIN = Path(__file__).resolve().parent.parent / "json_ai_studio_plugin.py"
# Set JSTUDIO_PLUGIN_BINARY to a built launcher (build_binary.sh) to run the
# same host conversation against the shipped binary instead of the source.
BINARY = os.environ.get("JSTUDIO_PLUGIN_BINARY")
COMMAND = [BINARY] if BINARY else [sys.executable, str(PLUGIN)]


class HostSide:
    def __init__(self) -> None:
        self.fake = FakeHost()
        self.proc = subprocess.Popen(
            COMMAND,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            bufsize=1,
        )
        self.progress: list[dict[str, Any]] = []
        self._next_id = 0

    def _send(self, frame: dict[str, Any]) -> None:
        self.proc.stdin.write(json.dumps(frame) + "\n")
        self.proc.stdin.flush()

    def request(self, method: str, params: dict[str, Any] | None = None) -> Any:
        """Send one host request; serve reverse RPCs until its answer."""
        self._next_id += 1
        rid = self._next_id
        self._send(
            {"jsonrpc": "2.0", "id": rid, "method": method, "params": params or {}}
        )
        while True:
            line = self.proc.stdout.readline()
            assert line, "plugin closed stdout"
            msg = json.loads(line)  # every stdout line must be a frame
            if msg.get("method") == "executa/progress":
                self.progress.append(msg["params"])
            elif "method" in msg:  # reverse RPC from the plugin
                try:
                    result = self.fake.handle(msg["method"], msg["params"])
                    self._send({"jsonrpc": "2.0", "id": msg["id"], "result": result})
                except HostError as exc:
                    self._send(
                        {
                            "jsonrpc": "2.0",
                            "id": msg["id"],
                            "error": {"code": exc.code, "message": exc.message},
                        }
                    )
            elif msg.get("id") == rid:
                assert "error" not in msg, msg
                return msg["result"]

    def invoke(self, tool: str, **arguments: Any) -> Any:
        result = self.request(
            "invoke",
            {
                "tool": tool,
                "arguments": arguments,
                "context": {"invoke_id": f"inv-{self._next_id}"},
            },
        )
        assert result["success"], result
        return result["data"]

    def close(self) -> int:
        self.proc.stdin.close()  # host shutdown contract: close stdin
        return self.proc.wait(timeout=15)


def test_plugin_serves_a_chat_turn_over_stdio():
    host = HostSide()
    try:
        init = host.request("initialize", {"protocolVersion": "2.0"})
        assert init["protocolVersion"] == "2.0"
        assert "sampling" in init["capabilities"]

        manifest = host.request("describe")
        names = [t["name"] for t in manifest["tools"]]
        assert {"create_doc", "chat_turn", "accept_all", "get_doc"} <= set(names)
        assert host.request("health")["status"] == "ready"

        sid = host.invoke("create_doc", json={"service": {"timeout": 30}})["session_id"]
        host.fake.replies.append(
            {
                "diffs": [
                    {
                        "path": "/service/timeout",
                        "operation": "modify",
                        "old_value": 30,
                        "new_value": 60,
                    }
                ],
                "explanation": "Raised the timeout.",
            }
        )
        turn = host.invoke("chat_turn", session_id=sid, message="set timeout to 60")
        assert [e["event"] for e in turn["events"]].count("diff") == 1

        # The sampling request was correlated with the invoke that owns it.
        (call,) = host.fake.sampling_calls
        assert call["context"]["invoke_id"].startswith("inv-")
        assert all(p["context"]["invoke_id"] for p in host.progress)

        host.invoke("accept_all", session_id=sid)
        doc = host.invoke("get_doc", session_id=sid)
        assert doc["working_json"]["service"]["timeout"] == 60
    finally:
        assert host.close() == 0
