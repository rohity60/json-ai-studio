"""Live eval: format correctness (prompt rule 11 + FORMAT NOTES). Opt-in.

Policy: on every request the model also proposes fixes for values that are
wrong for the document's format, explaining each in the explanation — except
when the user explicitly asks for a specific value, which it applies and
warns about. Known formats (template formatSignature) get FORMAT NOTES.

Prod case 2026-10-19: a Zoom Rooms Controls profile with an invalid adapter
model ("GenericNetworkDevice"); asked to "make this code work with qsys", the
model changed it to "Q-SYS Core110f" — still invalid.

    cd apps/api && LIVE_LLM=1 PYTHONPATH=. uv run pytest tests/test_suggested_fixes_live.py -v -s
"""

from __future__ import annotations

import os

import pytest

from test_chat_history_live import chat, client, seed  # noqa: F401 (fixture)

pytestmark = pytest.mark.skipif(
    os.environ.get("LIVE_LLM") != "1", reason="live LLM eval; set LIVE_LLM=1"
)

VALID_ZOOM_MODELS = {"GenericNetworkAdapter", "iTachIP2SL", "iTachIP2CC"}

# Reconstructed from the prod diffs: 2 top-level keys, adapter-level name,
# invalid model, methods directly on the adapter, non-Zoom placeholders.
BROKEN_ZOOM_PROFILE = {
    "about": {"name": "Salon room controls", "version": "1.0"},
    "adapters": [
        {
            "name": "Core-Salon",
            "model": "GenericNetworkDevice",
            "ip": "tcp://192.168.1.140:1702",
            "methods": [
                {
                    "id": "share",
                    "name": "Share",
                    "command": 'sg "{{_param1}}" {{_param2}}\r\n',
                    "params": [
                        {"id": "start", "name": "Start", "value": "sharing_started"},
                        {"id": "stop", "name": "Stop", "value": "sharing_ended"},
                    ],
                    "type": "actions",
                }
            ],
        }
    ],
}


def test_zoom_profile_fix_uses_valid_model(client):
    sid = seed(client, BROKEN_ZOOM_PROFILE)
    done = chat(
        client,
        sid,
        "make this code work with qsys to control zoom room. the device is a "
        "q-sys core110f, IP address 192.168.1.140",
    )
    adapter = done["working_json"]["adapters"][0]
    assert (
        adapter["model"] == "GenericNetworkAdapter"
    ), adapter  # prod: "Q-SYS Core110f"
    assert adapter["ip"] == "tcp://192.168.1.140:1702"
    assert "model" in done["explanation"].lower(), done["explanation"]


def test_explicit_invalid_value_is_applied_with_warning(client):
    profile = {
        "adapters": [
            {
                "model": "GenericNetworkAdapter",
                "ip": "tcp://192.168.1.140:1702",
                "ports": [{"id": "core", "name": "Core", "methods": []}],
            }
        ]
    }
    sid = seed(client, profile)
    done = chat(client, sid, "Set the adapter model to Q-SYS Core110f")
    assert done["working_json"]["adapters"][0]["model"] == "Q-SYS Core110f"
    explanation = done["explanation"].lower()
    assert "genericnetworkadapter" in explanation or "not" in explanation, done[
        "explanation"
    ]


def test_package_json_fixes_are_explained(client):
    sid = seed(
        client,
        {"name": "My App", "version": "1.0", "scripts": {"start": "node index.js"}},
    )
    done = chat(client, sid, "is this package.json valid? fix anything that's wrong")
    pkg = done["working_json"]
    assert pkg["name"] == "my-app", pkg
    assert pkg["version"] == "1.0.0", pkg
    explanation = done["explanation"].lower()
    assert "name" in explanation, done["explanation"]
    assert "version" in explanation or "semver" in explanation, done["explanation"]
    assert pkg["scripts"] == {"start": "node index.js"}


def test_ordinary_edit_also_fixes_format_problems(client):
    """Policy: fixes are proactive, not only on request."""
    sid = seed(
        client,
        {"name": "My App", "version": "1.0", "scripts": {"start": "node index.js"}},
    )
    done = chat(client, sid, "Add a test script using vitest")
    pkg = done["working_json"]
    assert "test" in pkg["scripts"]
    assert pkg["name"] == "my-app" and pkg["version"] == "1.0.0", pkg
    assert "name" in done["explanation"].lower(), done["explanation"]


def test_valid_document_gets_no_extra_fixes(client):
    sid = seed(
        client,
        {"name": "my-app", "version": "1.0.0", "scripts": {"start": "node index.js"}},
    )
    done = chat(client, sid, "Add a test script using vitest")
    pkg = done["working_json"]
    assert "test" in pkg["scripts"]
    assert (pkg["name"], pkg["version"]) == ("my-app", "1.0.0")
