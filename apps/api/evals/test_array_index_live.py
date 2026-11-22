"""Live LLM eval: does the model emit valid array indices? Opt-in.

Covers every multi-op array shape from the 2026-11-21 investigation
(appends, several inserts in one gap, inserts + deletes, replace,
delete + modify) on a small named list, the prod case (4 new roles on a
51-role Discord server JSON), and add-then-modify across two turns.

    cd apps/api && LIVE_LLM=1 PYTHONPATH=. uv run pytest evals/test_array_index_live.py -s
    # LIVE_DEPLOYMENT=nvidia_nim | google_ai_studio (+ LIVE_CALL_SPACING_S=60)

Each case prints one ``RESULT`` line: ok/FAIL, the model's raw diffs
(paths as the model sent them, before server normalisation), failures,
and the resulting list. Grep ``RESULT`` for the summary.
"""

from __future__ import annotations

import json
import os
import time
import uuid

import pytest

from src.json_ai_studio.diff_utils import DiffUtils
from src.json_ai_studio.services.chat_service import parse_sse

pytestmark = pytest.mark.skipif(
    os.environ.get("LIVE_LLM") != "1", reason="live LLM eval; set LIVE_LLM=1"
)

BUSY = {"service_unavailable", "rate_limit", "credit_limit"}

CARDS = {
    "deck": "Onboarding",
    "cards": [
        {"name": "A", "text": "Welcome to the team."},
        {"name": "B", "text": "Set up your laptop."},
        {"name": "C", "text": "Meet your buddy."},
        {"name": "D", "text": "Ship your first change."},
    ],
}

_ROLE_NAMES = (
    ["@everyone", "Owner", "Co-Owner", "Admin", "Head Moderator", "Moderator"]
    + ["Trial Staff", "Helper", "Server Booster", "Verified", "Muted"]
    + [f"Regiment {i}" for i in range(1, 21)]
    + [f"Level {i * 5}" for i in range(1, 21)]
)
assert len(_ROLE_NAMES) == 51


def _role(i: int, name: str) -> dict:
    return {
        "id": str(1572671157440870000 + i * 7919),
        "name": name,
        "color": (i * 104729) % 16777215,
        "colors": {"primary_color": (i * 104729) % 16777215, "secondary_color": None},
        "hoist": i < 8,
        "icon": None,
        "unicode_emoji": None,
        "position": 50 - i,
        "permissions": str(0 if i > 10 else 1 << (i + 10)),
        "managed": False,
        "mentionable": i % 3 == 0,
        "flags": 0,
        "tags": {} if i % 4 else {"premium_subscriber": None},
    }


SERVER = {
    "id": "1572671157440869999",
    "name": "The Moonlit Black Cats",
    "owner_id": "1572671157440860000",
    "verification_level": 2,
    "roles": [_role(i, n) for i, n in enumerate(_ROLE_NAMES)],
    "channels": [
        {"id": str(1572671157440880000 + i), "name": n, "type": 0, "position": i}
        for i, n in enumerate(["welcome", "rules", "general", "staff-chat", "logs"])
    ],
}


@pytest.fixture
def client(monkeypatch, pinned_deployment):
    from fastapi.testclient import TestClient

    from src.json_ai_studio.main import app

    monkeypatch.setenv("ANON_REQUESTS_PER_MINUTE", "10000")
    with TestClient(app, headers={"X-API-Key": f"live-{uuid.uuid4().hex}"}) as c:
        yield c


@pytest.fixture
def raw_diffs(monkeypatch):
    """Record the diffs each chat turn hands to the apply step (model paths)."""
    seen: list[list[dict]] = []
    real = DiffUtils.apply_all_verbose

    def spy(diffs, doc):
        seen.append([dict(d) for d in diffs])
        return real(diffs, doc)

    monkeypatch.setattr(DiffUtils, "apply_all_verbose", staticmethod(spy))
    return seen


def seed(client, doc) -> str:
    sid = client.post("/api/sessions", json={"name": "live"}).json()["id"]
    resp = client.post(
        f"/api/sessions/{sid}/versions/restore",
        json={"versions": [], "working_json": doc, "conversation_history": []},
    )
    assert resp.status_code == 200, resp.text
    return sid


def chat(client, sid: str, message: str, attempts: int = 4) -> dict:
    for _ in range(attempts):
        resp = client.post(
            "/api/chat", data={"session_id": sid, "message": message}, timeout=300
        )
        events = [parse_sse(b) for b in resp.text.split("\n\n") if b.strip()]
        kinds = {e for e, _ in events}
        if kinds & BUSY or "complete" not in kinds:
            time.sleep(20)
            continue
        return next(p for e, p in events if e == "complete")
    pytest.skip("provider unavailable")


def last_turn(client, sid) -> dict:
    return client.get(f"/api/sessions/{sid}").json()["conversation_history"][-1]


def names(doc, key="cards") -> list[str]:
    return [x.get("name") or "?" if isinstance(x, dict) else repr(x) for x in doc[key]]


def report(label, ok, raw, turn, got, want):
    model = [f"{d.get('operation')} {d.get('path')}" for d in raw]
    failed = [
        f"{d['path']}: {d.get('failure_reason')}"
        for d in turn.get("diffs", [])
        if d["status"] == "failed"
    ]
    print(
        f"\nRESULT {'ok  ' if ok else 'FAIL'} {label:34} model={model} "
        f"failed={failed} got={got} want={want}"
    )


CARD_CASES = [
    ("append_two", "Append two cards named X and Y (text 'TBD') at the end.", "ABCDXY"),
    (
        "insert_two_same_gap",
        "Insert two cards X then Y (text 'TBD') between A and B.",
        "AXYBCD",
    ),
    (
        "insert_two_gaps",
        "Insert a card X between A and B, and a card Y between C and D (text 'TBD').",
        "AXBCYD",
    ),
    ("delete_two", "Delete cards A and C.", "BD"),
    (
        "insert_and_delete",
        "Insert a card X (text 'TBD') between A and B, and delete card C.",
        "AXBD",
    ),
    (
        "delete_and_insert_later",
        "Delete card B, and insert a card X (text 'TBD') right before D.",
        "ACXD",
    ),
    (
        "replace",
        "Replace card C with a new card X with text 'TBD' (remove C, put X there).",
        "ABXD",
    ),
    (
        "delete_and_rename",
        "Delete card B and rename card C to C2.",
        ["A", "C2", "D"],
    ),
    (
        "delete_and_append",
        "Delete card B and add a card X (text 'TBD') at the end.",
        "ACDX",
    ),
]


@pytest.mark.parametrize(
    "message,want", [c[1:] for c in CARD_CASES], ids=[c[0] for c in CARD_CASES]
)
def test_cards(client, raw_diffs, message, want):
    sid = seed(client, CARDS)
    done = chat(client, sid, message)
    got = names(done["working_json"])
    want = list(want)
    report(
        message[:34],
        got == want,
        raw_diffs[-1] if raw_diffs else [],
        last_turn(client, sid),
        "".join(got) if all(len(n) == 1 for n in got) else got,
        "".join(want) if all(len(n) == 1 for n in want) else want,
    )
    assert got == want


NEW_ROLES = ["Senior Staff", "Recruitment Staff", "Event Staff", "Free Carriers"]


def test_prod_four_new_roles(client, raw_diffs):
    sid = seed(client, SERVER)
    done = chat(
        client,
        sid,
        "Add new placeholder roles Senior Staff, Recruitment Staff, Event Staff and "
        "Free Carriers with minimal permissions (I'll supply real IDs later).",
    )
    got = names(done["working_json"], "roles")
    old = [n for n in got if n not in NEW_ROLES]
    added = [n for n in got if n in NEW_ROLES]
    at = sorted(got.index(n) for n in added)
    contiguous = bool(at) and at == list(range(at[0], at[0] + len(at)))
    ok = old == _ROLE_NAMES and sorted(added) == sorted(NEW_ROLES) and contiguous
    report(
        "prod_four_new_roles",
        ok,
        raw_diffs[-1] if raw_diffs else [],
        last_turn(client, sid),
        f"len={len(got)} added_at={[got.index(n) for n in added]}",
        "51 kept in order + 4 new",
    )
    assert ok


def test_roles_insert_after_named(client, raw_diffs):
    sid = seed(client, SERVER)
    done = chat(
        client,
        sid,
        "Add two roles, Senior Staff and Event Staff, right after the Moderator "
        "role (before Trial Staff), with minimal permissions.",
    )
    got = names(done["working_json"], "roles")
    m = _ROLE_NAMES.index("Moderator")
    want = _ROLE_NAMES[: m + 1] + ["Senior Staff", "Event Staff"] + _ROLE_NAMES[m + 1 :]
    report(
        "roles_insert_after_named",
        got == want,
        raw_diffs[-1] if raw_diffs else [],
        last_turn(client, sid),
        got[m - 1 : m + 5],
        want[m - 1 : m + 5],
    )
    assert got == want


@pytest.mark.parametrize("accept_first", [False, True], ids=["pending", "accepted"])
@pytest.mark.parametrize(
    "where,first_want",
    [("at the end", "ABCDN"), ("between B and C", "ABNCD")],
    ids=["appended", "inserted"],
)
def test_add_then_modify(client, raw_diffs, accept_first, where, first_want):
    sid = seed(client, CARDS)
    done = chat(client, sid, f"Add a card named N with text 'TBD' {where}.")
    got1 = "".join(names(done["working_json"]))
    if accept_first:
        client.post(f"/api/sessions/{sid}/diffs/accept-all")
    done = chat(
        client,
        sid,
        "Rename the card you just added to Renamed and set its text to 'Hi'.",
    )
    cards = done["working_json"]["cards"]
    got = [c["name"] for c in cards]
    want = [("Renamed" if n == "N" else n) for n in first_want]
    renamed = next((c for c in cards if c["name"] == "Renamed"), {})
    ok = got1 == first_want and got == want and renamed.get("text") == "Hi"
    report(
        f"add_then_modify {where} {'acc' if accept_first else 'pend'}",
        ok,
        raw_diffs[-1] if raw_diffs else [],
        last_turn(client, sid),
        f"t1={got1} t2={got}",
        want,
    )
    assert ok
