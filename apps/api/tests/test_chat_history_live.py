"""Live LLM eval for chat-history follow-ups (ADR-0021). Opt-in.

Replays production conversations (2026-10-01/02/11 logs) against a REAL
model, in-process via TestClient. Pinned to ONE deployment — by default the
local Ollama (`ollama_local`, needs OLLAMA_BASE_URL) so local runs never burn
cloud quota; see the `pinned_deployment` fixture in conftest.py. Skipped
unless ``LIVE_LLM=1``:

    cd apps/api && LIVE_LLM=1 PYTHONPATH=. uv run pytest tests/test_chat_history_live.py -v -s
    # other backend: LIVE_DEPLOYMENT=google_ai_studio  /  LIVE_MODEL=qwen3.6:35b-mlx

Model output varies run to run, so assertions are on SAFETY (never touch
values that don't match, never re-propose done work) with a coverage floor,
not exact diffs. Provider busy / rate-limit events are retried.

The prior turn is seeded through ``versions/restore`` so the follow-up runs
against the exact state production had (a single leaf change), independent
of how the model handles turn 1 today.
"""

from __future__ import annotations

import copy
import json
import os
import time
import uuid

import pytest

from src.json_ai_studio.services.chat_service import parse_sse

pytestmark = pytest.mark.skipif(
    os.environ.get("LIVE_LLM") != "1", reason="live LLM eval; set LIVE_LLM=1"
)

BUSY = {"service_unavailable", "rate_limit", "credit_limit"}


def _players(n: int = 6) -> list[dict]:
    return [
        {
            "id": i + 1,
            "name": f"Player {i + 1}",
            "overall": 70 + i,
            "rating": 3 + i % 3,
            "default_overall": 68 + i,
            "parameters": [99, 70 + i, 99 if i % 2 else 55, 99],
        }
        for i in range(n)
    ]


GAME = {
    "game": "Football Manager",
    "version": "1.4.2",
    "season": 2026,
    "league": "Super Lig",
    "team": "Istanbul FC",
    "currency": "TRY",
    "settings": {"difficulty": "hard"},
    "gameplayer_list": _players(),
}

DRAFT = {
    "league": "NBA",
    "updated": "2026-09-30",
    "owner": "ops",
    "files": [
        {"file": "roster_2026.json", "title": "Regular Season 2026"},
        {"file": "draft_2027_round1.json", "title": "Draft Season 2027 - Round 1"},
        {"file": "draft_2027_round2.json", "title": "Draft Season 2027 - Round 2"},
        {"file": "draft_2026.json", "title": "Draft Season 2026"},
    ],
    "archive": {"playoffs_2026.txt": {"size": 800}},
}


@pytest.fixture
def client(monkeypatch, pinned_deployment):
    from fastapi.testclient import TestClient

    from src.json_ai_studio.main import app

    monkeypatch.setenv("ANON_REQUESTS_PER_MINUTE", "10000")
    with TestClient(app, headers={"X-API-Key": f"live-{uuid.uuid4().hex}"}) as c:
        yield c


def seed(client, doc, turns=()) -> str:
    sid = client.post("/api/sessions", json={"name": "live"}).json()["id"]
    resp = client.post(
        f"/api/sessions/{sid}/versions/restore",
        json={"versions": [], "working_json": doc, "conversation_history": list(turns)},
    )
    assert resp.status_code == 200, resp.text
    return sid


def chat(client, sid: str, message: str, attempts: int = 5) -> dict:
    """Send a turn; retry provider-busy. Returns the complete payload."""
    for _ in range(attempts):
        resp = client.post(
            "/api/chat", data={"session_id": sid, "message": message}, timeout=180
        )
        events = [parse_sse(b) for b in resp.text.split("\n\n") if b.strip()]
        kinds = {e for e, _ in events}
        if kinds & BUSY or "complete" not in kinds:
            if pinned_deployment_is_local():
                pytest.fail(f"local deployment failed: {resp.text[-300:]}")
            time.sleep(25)
            continue
        done = next(p for e, p in events if e == "complete")
        print(f"\nUSER {message!r}\n  -> {done['explanation']}")
        return done
    pytest.skip("provider unavailable")


def pinned_deployment_is_local() -> bool:
    return os.environ.get("LIVE_DEPLOYMENT", "ollama_local") == "ollama_local"


def changed_cells(before: dict, after: dict) -> list[tuple[int, int, int, int]]:
    """(player, index, old, new) for every parameter that changed."""
    out = []
    for i, (b, a) in enumerate(
        zip(before["gameplayer_list"], after["gameplayer_list"])
    ):
        for j, (old, new) in enumerate(zip(b["parameters"], a["parameters"])):
            if old != new:
                out.append((i, j, old, new))
    return out


PROD_TURN_1 = '"parameters": [ 99, su oyuncularının parametreleri kisimlarını 60 yapımı'


@pytest.fixture
def after_first_change():
    """State after prod turn 1: only player 0's parameters[0] went 99 -> 60."""
    doc = copy.deepcopy(GAME)
    doc["gameplayer_list"][0]["parameters"][0] = 60
    turns = [
        {"id": "u1", "role": "user", "content": PROD_TURN_1},
        {
            "id": "a1",
            "role": "assistant",
            "content": "Changed the first player's first parameter from 99 to 60.",
            "diffs": [
                {
                    "id": "d1",
                    "path": "/gameplayer_list/0/parameters/0",
                    "operation": "modify",
                    "old_value": 99,
                    "new_value": 60,
                    "status": "accepted",
                }
            ],
        },
    ]
    return doc, turns


def test_explicit_all_99s_follow_up(client, after_first_change):
    """'Tum oyuncular icin degistir 99, olanlarin hepsi' (prod: 0 diffs)."""
    doc, turns = after_first_change
    done = chat(
        client,
        seed(client, doc, turns),
        "Tum oyuncular icin degistir 99, olanlarin hepsi",
    )

    changes = changed_cells(doc, done["working_json"])
    remaining_99 = sum(v == 99 for p in doc["gameplayer_list"] for v in p["parameters"])
    assert all(old == 99 and new == 60 for *_, old, new in changes), changes
    assert len(changes) >= remaining_99 - 2, f"{len(changes)}/{remaining_99} changed"


def test_vague_all_players_follow_up_is_not_destructive(client, after_first_change):
    """'Tum oyuncular icin degistir' — must generalise the 99 -> 60 leaf
    change, not overwrite whole parameter arrays."""
    doc, turns = after_first_change
    done = chat(client, seed(client, doc, turns), "Tum oyuncular icin degistir")

    changes = changed_cells(doc, done["working_json"])
    assert changes, "expected the change to be generalised"
    assert all(old == 99 and new == 60 for *_, old, new in changes), changes


def test_without_history_follow_up_fails(client):
    """Baseline (what production does today): no context → no useful edit."""
    doc = copy.deepcopy(GAME)
    doc["gameplayer_list"][0]["parameters"][0] = 60
    done = chat(client, seed(client, doc), "Tum oyuncular icin degistir")
    assert all(new != 60 for *_, new in changed_cells(doc, done["working_json"]))


def test_draft_season_delete_then_rephrase(client):
    """Prod: same delete request sent twice (2nd returned 'not found')."""
    sid = seed(client, DRAFT)
    first = chat(
        client,
        sid,
        "I want every file to be deleted that contains the draft season 2027",
    )
    titles = [f["title"] for f in first["working_json"]["files"]]
    assert titles == ["Regular Season 2026", "Draft Season 2026"], titles

    second = chat(client, sid, "I want every file deleted that says draft season 2027")
    assert second["working_json"]["files"] == first["working_json"]["files"]


# ---------------------------------------------------------------------------
# Large document (skeleton prompt) — prod 2026-10-11, gita.json, 701 records
# ---------------------------------------------------------------------------

_CHAPTER_SIZES = [
    47,
    72,
    43,
    42,
    29,
    47,
    30,
    28,
    34,
    42,
    55,
    20,
    35,
    27,
    20,
    24,
    28,
    78,
]


def _gita() -> dict:
    """Shape of the real export: slokNumber restarts per chapter; long text
    fields push it far past llm_max_inline_chars so the model gets only a
    skeleton (records[0] + "…+700 more items")."""
    records = []
    for ch, size in enumerate(_CHAPTER_SIZES, start=1):
        for n in range(1, size + 1):
            records.append(
                {
                    "status": "PENDING_SOURCE_MATCH",
                    "granthId": "bhagavad_gita",
                    "sectionId": f"bhagavad_gita_ch_{ch}",
                    "slokNumber": n,
                    "chapterName": f"Chapter {ch}",
                    "currentEnglish": f"Verse {ch}.{n} " + "lorem ipsum " * 60,
                }
            )
    return {
        "source": "gita",
        "purpose": "verse sync",
        "records": records,
        "recordCount": len(records),
    }


GITA = _gita()


@pytest.fixture
def gita_after_first_ten(client):
    """Prod state after turns 1-2: records 0..9 sectionId -> 'abc' (accepted)."""
    doc = copy.deepcopy(GITA)
    for r in doc["records"][:10]:
        r["sectionId"] = "abc"

    def change(i):
        return {
            "id": f"d{i}",
            "path": f"/records/{i}/sectionId",
            "operation": "modify",
            "old_value": "bhagavad_gita_ch_1",
            "new_value": "abc",
            "status": "accepted",
        }

    turns = [
        {
            "id": "u1",
            "role": "user",
            "content": "change bhagavad_gita_ch_1 to abc where shok number is 1",
        },
        {
            "id": "a1",
            "role": "assistant",
            "content": "Changed sectionId to 'abc' for the record with slokNumber 1.",
            "diffs": [change(0)],
        },
        {"id": "u2", "role": "user", "content": "do same for shlok 1 to 10"},
        {
            "id": "a2",
            "role": "assistant",
            "content": "Updated sectionId to 'abc' for slokNumbers 2 through 10.",
            "diffs": [change(i) for i in range(1, 10)],
        },
    ]
    return doc, seed(client, doc, turns)


def _section_ids(done) -> list[str]:
    return [r["sectionId"] for r in done["working_json"]["records"]]


def test_gita_first_100_uses_bulk(client, gita_after_first_ten):
    """'ok mag first 100 la change apply kar' — prod refused (skeleton).
    Must change the first 100 records (positional) and nothing else."""
    doc, sid = gita_after_first_ten
    done = chat(client, sid, "ok mag first 100 la change apply kar")
    ids = _section_ids(done)
    assert ids[:100] == ["abc"] * 100, ids[:100]
    assert ids[100:] == [r["sectionId"] for r in doc["records"][100:]]


def test_gita_all_records_same_change(client, gita_after_first_ten):
    """'theek ahe sagely records al same change apply kar' (all records, same
    change). Same change = bhagavad_gita_ch_1 -> abc, so only chapter-1
    records may change; any other sectionId must be left alone."""
    doc, sid = gita_after_first_ten
    done = chat(client, sid, "theek ahe sagely records al same change apply kar")
    ids = _section_ids(done)
    changed = [
        i for i, (a, b) in enumerate(zip(doc["records"], ids)) if a["sectionId"] != b
    ]
    assert changed, "expected a bulk change, got a refusal"
    assert (
        all(doc["records"][i]["sectionId"] == "bhagavad_gita_ch_1" for i in changed)
        or len(changed) == len(ids) - 1
    ), "changed a mix of chapters that matches neither reading"
