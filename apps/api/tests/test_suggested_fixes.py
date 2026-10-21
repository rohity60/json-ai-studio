"""Suggested fixes (prompt rule 11) — deterministic tests, stubbed LLM.

The behaviour itself is the model's (see test_suggested_fixes_live.py); these
lock the contract: the rule and its example are in every chat prompt, fixes
travel as ordinary diffs, and the per-fix rationale reaches the user via the
explanation (no separate per-diff field), including in history replay.
"""

from __future__ import annotations

import json
import uuid

import pytest

from src.json_ai_studio.gateway import GatewayService
from src.json_ai_studio.models import DiffEntry
from src.json_ai_studio.prompting import build_system_prompt
from src.json_ai_studio.services.chat_service import parse_sse

PKG = {"name": "My App", "version": "1.0", "scripts": {"start": "node index.js"}}
FIX_EXPLANATION = (
    "Fixed 2 issues: name 'My App' → 'my-app' because npm package names must be "
    "lowercase with no spaces; version '1.0' → '1.0.0' because npm requires full "
    "semver (major.minor.patch)."
)


MATCH_MARKER = "The CURRENT WORKING JSON matches a known format"

ZOOM = {
    "adapters": [
        {
            "model": "GenericNetworkDevice",
            "ip": "tcp://192.168.1.140:1702",
            "methods": [],
        }
    ]
}


class TestPromptContract:
    @pytest.fixture
    def prompt(self):
        return build_system_prompt(PKG)

    def test_rule_is_proactive_with_explicit_request_exception(self, prompt):
        assert "11. FORMAT CORRECTNESS — on EVERY request" in prompt
        assert (
            "EXCEPTION: when the user explicitly asks for a specific key or value"
            in prompt
        )
        assert "never silently override the user" in prompt

    def test_rationale_goes_in_explanation_not_a_field(self, prompt):
        assert 'in "explanation" list EACH fix and why' in prompt
        assert '"reason"' not in prompt
        assert "reason" not in DiffEntry.model_fields

    def test_guards_against_invented_values(self, prompt):
        assert "never invent model names, ports, commands or IDs" in prompt
        assert "If nothing is wrong, propose no extra fixes." in prompt

    def test_examples_cover_proactive_fix_and_explicit_warning(self, prompt):
        assert 'User: "Add a test script using vitest." (rule 11' in prompt
        assert 'User: "Set the name to My App." (explicit request' in prompt

    def test_rule_also_present_in_skeleton_mode(self, monkeypatch):
        from src.json_ai_studio.settings import get_settings

        monkeypatch.setenv("LLM_MAX_INLINE_CHARS", "10")
        get_settings.cache_clear()
        prompt = build_system_prompt(ZOOM)
        assert "STRUCTURAL SKELETON" in prompt
        assert "11. FORMAT CORRECTNESS" in prompt
        assert MATCH_MARKER in prompt  # notes still injected for large docs


class TestFormatHints:
    def test_zoom_profile_gets_format_notes(self):
        prompt = build_system_prompt(ZOOM)
        assert MATCH_MARKER in prompt
        assert "FORMAT NOTES — Zoom Rooms Controls profile for Q-SYS:" in prompt
        assert "GenericNetworkAdapter" in prompt.split(MATCH_MARKER, 1)[1]

    def test_unrelated_document_gets_none(self):
        assert MATCH_MARKER not in build_system_prompt(PKG)

    def test_partial_signature_does_not_match(self):
        from src.json_ai_studio.format_hints import match_formats

        assert match_formats({"adapters": [{"model": "x"}]}) == []  # no ip
        assert match_formats({"adapters": [{"ip": "x"}]}) == []
        assert match_formats([1, 2]) == []
        assert [f["id"] for f in match_formats(ZOOM)] == ["zoom-rooms-qsys-controls"]

    def test_exported_notes_match_template_source(self):
        """config/format_notes.json is generated — fail if it drifted from the
        template (re-run: node --no-warnings apps/web/scripts/export-format-notes.mjs).
        """
        import re
        from pathlib import Path

        from src.json_ai_studio.format_hints import load_formats

        src = (
            Path(__file__).resolve().parents[2]
            / "web/src/content/templates/zoom-rooms-qsys-controls.ts"
        ).read_text()
        (fmt,) = [f for f in load_formats() if f["id"] == "zoom-rooms-qsys-controls"]
        sig = re.search(r"formatSignature: \[(.*?)\]", src).group(1)
        assert fmt["signature"] == re.findall(r"'([^']+)'", sig)
        for note in fmt["notes"]:
            assert note.replace("\\", "\\\\") in src or note.split(" — ")[0] in src

    def test_missing_notes_file_is_harmless(self, monkeypatch):
        from src.json_ai_studio import format_hints

        monkeypatch.setattr(format_hints, "_NOTES_PATH", "/nonexistent.json")
        format_hints.load_formats.cache_clear()
        try:
            assert format_hints.match_formats(ZOOM) == []
        finally:
            format_hints.load_formats.cache_clear()


@pytest.fixture
def client(monkeypatch):
    from fastapi.testclient import TestClient

    from src.json_ai_studio.main import app

    monkeypatch.setenv("ANON_REQUESTS_PER_MINUTE", "10000")
    with TestClient(app, headers={"X-API-Key": f"fix-{uuid.uuid4().hex}"}) as c:
        yield c


@pytest.fixture
def replies(monkeypatch):
    queue: list[dict] = []
    calls: list[dict] = []

    async def fake_invoke(session_id, message, principal, system_prompt, **kw):
        calls.append({"history": kw.get("history") or []})
        yield "event: thinking\ndata: " + json.dumps(
            {"text": json.dumps(queue.pop(0))}
        ) + "\n\n"

    monkeypatch.setattr(GatewayService, "invoke", staticmethod(fake_invoke))
    return queue, calls


def chat(client, sid, message):
    resp = client.post("/api/chat", data={"session_id": sid, "message": message})
    return [parse_sse(b) for b in resp.text.split("\n\n") if b.strip()]


def test_fixes_flow_as_diffs_with_rationale_in_explanation(client, replies):
    queue, calls = replies
    sid = client.post("/api/sessions", json={"name": "fix"}).json()["id"]
    client.post(
        "/api/json/upload",
        files={"json_body": (None, json.dumps(PKG)), "session_id": (None, sid)},
    )
    queue.extend(
        [
            {
                "diffs": [
                    {
                        "path": "/name",
                        "operation": "modify",
                        "old_value": "My App",
                        "new_value": "my-app",
                    },
                    {
                        "path": "/version",
                        "operation": "modify",
                        "old_value": "1.0",
                        "new_value": "1.0.0",
                    },
                ],
                "explanation": FIX_EXPLANATION,
            },
            {"diffs": [], "explanation": "ok"},
        ]
    )
    events = chat(client, sid, "is this package.json valid? fix anything that's wrong")

    diffs = [p["entry"] for e, p in events if e == "diff"]
    assert [(d["path"], d["new_value"]) for d in diffs] == [
        ("/name", "my-app"),
        ("/version", "1.0.0"),
    ]
    done = next(p for e, p in events if e == "complete")
    assert done["explanation"] == FIX_EXPLANATION  # full multi-fix text, not truncated
    assert done["working_json"]["name"] == "my-app"

    # The rationale is replayed on the next turn ("undo the version fix").
    chat(client, sid, "undo the version fix")
    replay = json.loads(calls[1]["history"][1]["content"])
    assert replay["explanation"] == FIX_EXPLANATION


def test_noop_modify_diffs_are_dropped(client, replies):
    """Prod/local 2026-10-21: model fixed model but also re-emitted the
    unchanged ip, so the user saw an identical before/after and thought
    nothing changed."""
    queue, _ = replies
    sid = client.post("/api/sessions", json={"name": "noop"}).json()["id"]
    doc = {
        "adapters": [
            {"model": "GenericNetworkDevice", "ip": "tcp://192.168.1.140:1702"}
        ]
    }
    client.post(
        "/api/json/upload",
        files={"json_body": (None, json.dumps(doc)), "session_id": (None, sid)},
    )
    queue.append(
        {
            "diffs": [
                {
                    "path": "/adapters/0/model",
                    "operation": "modify",
                    "old_value": "GenericNetworkDevice",
                    "new_value": "GenericNetworkAdapter",
                },
                {
                    "path": "/adapters/0/ip",
                    "operation": "modify",
                    "old_value": "tcp://192.168.1.140:1702",
                    "new_value": "tcp://192.168.1.140:1702",
                },
            ],
            "explanation": "Fixed model.",
        }
    )
    events = chat(client, sid, "make this work")
    assert [p["entry"]["path"] for e, p in events if e == "diff"] == [
        "/adapters/0/model"
    ]
    stored = client.get(f"/api/sessions/{sid}").json()["conversation_history"][1][
        "diffs"
    ]
    assert [d["path"] for d in stored] == ["/adapters/0/model"]


def test_all_noop_reply_reports_no_changes(client, replies):
    queue, _ = replies
    sid = client.post("/api/sessions", json={"name": "noop2"}).json()["id"]
    client.post(
        "/api/json/upload",
        files={"json_body": (None, json.dumps({"a": 1})), "session_id": (None, sid)},
    )
    queue.append(
        {
            "diffs": [
                {"path": "/a", "operation": "modify", "old_value": 1, "new_value": 1}
            ],
            "explanation": "Set a to 1.",
        }
    )
    events = chat(client, sid, "set a to 1")
    assert not [e for e, _ in events if e == "diff"]
    done = next(p for e, p in events if e == "complete")
    assert done["working_json"] == {"a": 1}
