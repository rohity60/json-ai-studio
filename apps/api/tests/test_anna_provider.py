"""Anna provider tests (ADR-0028).

The Anna App's Executa serves LLM calls through a litellm custom provider
registered under ``anna/``. These tests register a stand-in handler there
and drive the real gateway (planner, streaming, diff application) over
HTTP, so the only thing faked is the transport to the Anna host.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

import litellm
import pytest
from litellm import CustomLLM
from litellm.types.utils import GenericStreamingChunk

from src.json_ai_studio.deployment import DeploymentRegistry
from src.json_ai_studio.services.chat_service import parse_sse
from src.json_ai_studio.settings import get_settings

DOC = {"service": {"timeout": 30, "retryCount": 3}}


def _anna() -> Any:
    return next(p for p in DeploymentRegistry.list_deployments() if p.name == "anna")


class FakeAnnaHost(CustomLLM):
    """Records each call and streams one canned reply."""

    def __init__(self, reply: dict[str, Any]) -> None:
        super().__init__()
        self.reply = reply
        self.calls: list[dict[str, Any]] = []

    async def astreaming(self, *args, **kwargs):
        self.calls.append(
            {
                "model": kwargs.get("model"),
                "messages": kwargs.get("messages"),
                "optional_params": kwargs.get("optional_params"),
            }
        )
        yield GenericStreamingChunk(
            text=json.dumps(self.reply),
            is_finished=True,
            finish_reason="stop",
            index=0,
            tool_use=None,
            usage={"prompt_tokens": 40, "completion_tokens": 20, "total_tokens": 60},
        )


@pytest.fixture
def anna_only(monkeypatch):
    """Registry as the Executa sees it: only the anna deployment enabled."""
    monkeypatch.setenv("ANNA_ENABLED", "1")
    get_settings.cache_clear()
    DeploymentRegistry.reload()
    for p in DeploymentRegistry.list_deployments():
        monkeypatch.setattr(p, "enabled", p.name == "anna")
    host = FakeAnnaHost(
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
    monkeypatch.setattr(
        litellm, "custom_provider_map", [{"provider": "anna", "custom_handler": host}]
    )
    yield host
    get_settings.cache_clear()
    DeploymentRegistry.reload()


@pytest.fixture
def client(monkeypatch, auth_disabled):
    from fastapi.testclient import TestClient

    from src.json_ai_studio.main import app

    monkeypatch.setenv("ANON_REQUESTS_PER_MINUTE", "10000")
    with TestClient(app, headers={"X-API-Key": f"test-{uuid.uuid4().hex}"}) as c:
        yield c


def test_disabled_unless_anna_enabled(monkeypatch):
    monkeypatch.setenv("ANNA_ENABLED", "0")
    get_settings.cache_clear()
    DeploymentRegistry.reload()
    assert _anna().enabled is False


def test_enabled_and_always_states_thinking(anna_only):
    anna = _anna()
    assert anna.enabled is True
    assert anna.litellm_model(anna.base_model) == "anna/default"
    assert anna.completion_params("default") == {"anna_thinking": False}
    assert anna.completion_params("default", "low") == {"anna_thinking": "low"}


def test_chat_turn_runs_through_the_real_gateway(anna_only, client):
    sid = client.post("/api/sessions", json={"name": "t"}).json()["id"]
    resp = client.post(
        "/api/json/upload",
        files={"json_body": (None, json.dumps(DOC)), "session_id": (None, sid)},
    )
    assert resp.status_code == 200

    resp = client.post(
        "/api/chat", data={"session_id": sid, "message": "set timeout to 60"}
    )
    assert resp.status_code == 200
    events = [parse_sse(b) for b in resp.text.split("\n\n") if b.strip()]
    names = [e for e, _ in events]
    assert "error" not in names, events

    # The call reached the anna/ handler, with thinking stated explicitly.
    assert len(anna_only.calls) == 1
    call = anna_only.calls[0]
    assert call["optional_params"]["anna_thinking"] is False
    assert call["messages"][-1]["content"].endswith("set timeout to 60")

    diffs = [p["entry"] for e, p in events if e == "diff"]
    assert [d["path"] for d in diffs] == ["/service/timeout"]
    complete = next(p for e, p in events if e == "complete")
    assert complete["explanation"] == "Raised the timeout."

    resp = client.post(f"/api/sessions/{sid}/diffs/accept-all")
    assert resp.status_code == 200
    working = client.get(f"/api/sessions/{sid}").json()["working_json"]
    assert working["service"]["timeout"] == 60
