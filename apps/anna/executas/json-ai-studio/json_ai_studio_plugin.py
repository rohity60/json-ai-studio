"""JSON AI Studio — Anna Executa entry point (stdio JSON-RPC 2.0).

Host → us: ``initialize``, ``describe``, ``health``, ``invoke``,
``shutdown``. While an invoke runs we call back into the host for LLM
completions and storage (see ``jstudio.rpc``).

stdout is the protocol channel: nothing else may be printed there.
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
import threading
from typing import Any

# stdout belongs to the protocol. Keep the real stream for frames and point
# sys.stdout at stderr *before* importing anything else, so a library that
# prints or logs to stdout (LiteLLM does) cannot corrupt the channel.
_PROTOCOL_OUT = sys.stdout
sys.stdout = sys.stderr

VERSION = "0.1.0"
NAME = "tool-dev-json-ai-studio"

logging.basicConfig(
    stream=sys.stderr,
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("jstudio.plugin")

from jstudio import tools, wiring  # noqa: E402
from jstudio.rpc import bind_invoke, host, unbind_invoke  # noqa: E402

MANIFEST: dict[str, Any] = {
    "name": NAME,
    "display_name": "JSON AI Studio",
    "version": VERSION,
    "description": (
        "Edit JSON configs by chat: every change comes back as a diff you "
        "accept or reject, with saved versions and plain-language explanations."
    ),
    "tools": tools.manifest_tools(),
}


async def _invoke(req_id: Any, params: dict[str, Any]) -> None:
    context = params.get("context") or {}
    token = bind_invoke(context.get("invoke_id"))
    try:
        result = await tools.run(str(params.get("tool")), params.get("arguments") or {})
        host.reply(req_id, result)
    except Exception:  # tools.run already guards; this is the last resort
        logger.exception("invoke crashed")
        host.reply(req_id, {"success": False, "error": "Something went wrong."})
    finally:
        unbind_invoke(token)


def _read_stdin(loop: asyncio.AbstractEventLoop) -> None:
    for raw in sys.stdin:
        raw = raw.strip()
        if not raw:
            continue
        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            continue
        method = msg.get("method")
        if method is None:
            host.dispatch_response(msg)  # answer to one of our requests
            continue
        req_id = msg.get("id")
        if method == "initialize":
            host.reply(
                req_id,
                {
                    "protocolVersion": "2.0",
                    "serverInfo": {"name": NAME, "version": VERSION},
                    "server_info": {"name": NAME, "version": VERSION},
                    "capabilities": {
                        "sampling": {},
                        "storage": {"kv": True, "files": True},
                    },
                },
            )
        elif method == "describe":
            host.reply(req_id, MANIFEST)
        elif method == "health":
            host.reply(req_id, {"status": "ready"})
        elif method == "shutdown":
            host.reply(req_id, {})
            return
        elif method == "invoke":
            asyncio.run_coroutine_threadsafe(
                _invoke(req_id, msg.get("params") or {}), loop
            )
        else:
            host.reply_error(req_id, -32601, f"method not found: {method}")


def _write_frame(line: str) -> None:
    _PROTOCOL_OUT.write(line + "\n")
    _PROTOCOL_OUT.flush()


async def _serve() -> None:
    host.set_writer(_write_frame)
    wiring.install()
    reader = threading.Thread(
        target=_read_stdin, args=(asyncio.get_running_loop(),), daemon=True
    )
    reader.start()
    while reader.is_alive():  # until the host closes stdin
        await asyncio.sleep(0.2)


def main() -> None:
    asyncio.run(_serve())


if __name__ == "__main__":
    main()
