"""Live LLM eval: numbered ids vs array indices, and list edits. Opt-in.

Prod 2026-11-24 ("Love" rulebook): meters at indices 0..5 had ids m1..m6.
After the user confirmed with "Yes", the model added keywords at
/rulebook/meters/1..6/keywords/- (id number used as the index: 10 adds to
the missing meters/6 failed, the rest landed one meter late) and sent
replace_text edits on keyword LISTS (refused: "not a text value"). Locally
gemma4:12b repeated both (2/3 id slips, 3/3 text edits on lists).

Cases (the prod document is not available; LOVE is rebuilt from the log):

- ``yes_turn``: the prod turn — the expansion request + the model's
  confirmation question in history, then "Yes".
- ``append_numbered[small|big]``: "add these keywords" to meters with ids
  m1..m6; every keyword must land on its own meter, as a list item.
- ``append_plain_ids``: control — the same request on meters with ids that
  are words ("trust", ...), which do not look like indices.

    cd apps/api && LIVE_LLM=1 PYTHONPATH=. uv run pytest evals/test_id_index_live.py -s
    # LIVE_DEPLOYMENT=nvidia_nim
"""

from __future__ import annotations

import json
import os

import pytest

from src.json_ai_studio.services import chat_service
from test_array_index_live import chat, client, last_turn  # noqa: F401

pytestmark = pytest.mark.skipif(
    os.environ.get("LIVE_LLM") != "1", reason="live LLM eval; set LIVE_LLM=1"
)

LABELS = ["Trust", "Affection", "Attraction", "Arousal", "Intimacy", "Love"]
OLD_KEYWORDS = [
    ["promise", "honest", "rely on", "secret"],
    ["hug", "kiss", "sweet", "cuddle", "care"],
    ["handsome", "beautiful", "cute", "stare"],
    ["flirt", "tease", "touch", "blush"],
    ["close", "together", "share", "open up"],
    ["love", "adore", "miss you", "forever"],
]


def _levels(label: str) -> dict:
    """Prod's meters were large (8.4k prompt tokens for 6): per-level prose."""
    low = label.lower()
    return {
        "levels": [
            {
                "at": t,
                "name": f"{label} {n}",
                "behaviour": (
                    f"At {t} {low} the character {verb} the user. They mention it "
                    "in their own words, keep their own boundaries, and react to "
                    f"how the user treats them; a careless reply lowers {low} by "
                    "2 and a thoughtful one raises it by 1."
                ),
            }
            for t, n, verb in [
                (0, "none", "barely notices"),
                (20, "low", "is curious about"),
                (40, "warm", "looks forward to talking with"),
                (60, "strong", "openly cares about"),
                (80, "deep", "is devoted to"),
            ]
        ],
        "effects": (
            f"{label} changes the tone of replies: higher {low} makes the "
            "character warmer, more patient and more personal; lower values make "
            "them distant, brief and guarded."
        ),
    }


def love(ids: str = "numbered", big: bool = False) -> dict:
    meters = []
    for i, (label, kws) in enumerate(zip(LABELS, OLD_KEYWORDS)):
        meters.append(
            {
                "id": f"m{i + 1}" if ids == "numbered" else label.lower(),
                "type": "bar",
                "label": label,
                "tracks": "chat",
                "visible": True,
                "min": 0,
                "max": 100,
                "def": 0,
                "decay": 1,
                "description": f"How strong {label.lower()} is between the character and the user.",
                "keywords": list(kws),
                **(_levels(label) if big else {}),
            }
        )
    return {
        "name": "Love",
        "description": "Tracks how a romantic relationship develops during the chat.",
        "rulebook": {
            "meters": meters,
            "rules": [
                "Meters rise slowly; one message never moves a meter more than 5.",
                "Every meter decays by its decay value each day without contact.",
            ],
        },
    }


REQUEST = """# Expansion Request: Love Rulebook

I want to expand my existing SpicyChat rulebook called **Love** into a detailed relationship simulation with realistic emotional development, relationship dynamics, personal preferences, and biological cycle tracking.

The goal is to make characters feel like individual people with their own personalities, feelings, needs, habits, boundaries, and changing reactions rather than having every character behave the same way.

## 1. Romantic Desire and Attraction
Add separate meters for Physical Attraction, Romantic Attraction, Desire and Lust, and Libido. Each character should have baseline tendencies and preferences, their own ways of expressing attraction, and these should increase, decrease and develop depending on circumstances and emotional intimacy.

## 2. Affection
Split affection into Verbal Affection, Physical Affection, Quality Time, Acts of Kindness and Personal Intimacy so each character can prefer different ways of giving and receiving love.

## 3. Keywords
Update the keyword lists of the existing meters so each meter has its own distinct keywords (comfort, support, reassurance, honest conversation, mutual respect, shared experience, closeness, sharing feelings, understanding).
"""

CONFIRM = (
    "Your request asks for many new meters to expand the Love rulebook. "
    "I need confirmation before adding them."
)

APPEND = (
    "Add these keywords (keep the existing ones): Trust: reassurance, honest "
    "conversation. Affection: compliments, comfort. Attraction: chemistry. "
    "Arousal: lust. Intimacy: vulnerability, bond. Love: devotion, cherish."
)
WANT = {
    "Trust": ["reassurance", "honest conversation"],
    "Affection": ["compliments", "comfort"],
    "Attraction": ["chemistry"],
    "Arousal": ["lust"],
    "Intimacy": ["vulnerability", "bond"],
    "Love": ["devotion", "cherish"],
}


@pytest.fixture
def raw_text(monkeypatch):
    """The model's raw answer for each chat turn."""
    seen: list[str] = []
    real = chat_service.parse_llm_response

    def spy(text):
        seen.append(text)
        return real(text)

    monkeypatch.setattr(chat_service, "parse_llm_response", spy)
    return seen


def model_diffs(raw_text: list[str]) -> list[dict]:
    """The diffs as the model wrote them (fence / slightly broken JSON ok)."""
    if not raw_text:
        return []
    text = raw_text[-1].strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0]
    try:
        return json.loads(text).get("diffs") or []
    except ValueError:
        return _PARSE(raw_text[-1])[0] or []


_PARSE = chat_service.parse_llm_response  # the real parser, before the spy


def seed(client, doc, history=None) -> str:  # noqa: F811
    sid = client.post("/api/sessions", json={"name": "live"}).json()["id"]
    resp = client.post(
        f"/api/sessions/{sid}/versions/restore",
        json={
            "versions": [],
            "working_json": doc,
            "conversation_history": history or [],
        },
    )
    assert resp.status_code == 200, resp.text
    return sid


def id_slips(diffs: list[dict], doc: dict) -> list[str]:
    """Diffs whose meter index does not hold the meter their old_value names,
    or that point past the end of the meters list."""
    meters = doc["rulebook"]["meters"]
    out = []
    for d in diffs:
        parts = (d.get("path") or "").split("/")
        if len(parts) < 4 or parts[2] != "meters" or not parts[3].isdigit():
            continue
        i = int(parts[3])
        if len(parts) == 4 and d.get("operation") == "add":
            continue  # a new meter: adds past the end are folded to appends
        if i >= len(meters):
            out.append(f"{d.get('path')} (no meter {i})")
            continue
        old = d.get("old_value")
        if (
            len(parts) == 4
            and isinstance(old, dict)
            and old.get("id") != meters[i]["id"]
        ):
            out.append(f"{d.get('path')} old id {old.get('id')} != {meters[i]['id']}")
    return out


def failures(turn: dict) -> list[str]:
    return [
        f"{d['path']}: {d.get('failure_reason')}"
        for d in turn.get("diffs") or []
        if d["status"] == "failed"
    ]


def report(label, ok, diffs, **info):
    paths = sorted({f"{d.get('operation')} {d.get('path')}" for d in diffs})
    extra = " ".join(f"{k}={v}" for k, v in info.items())
    print(f"\nRESULT {'ok  ' if ok else 'FAIL'} {label:22} {extra} model={paths[:14]}")


def test_yes_turn(client, raw_text):  # noqa: F811
    doc = love()
    history = [
        {"role": "user", "content": REQUEST},
        {"role": "assistant", "content": CONFIRM, "diffs": []},
    ]
    sid = seed(client, doc, history)
    done = chat(client, sid, "Yes")
    diffs = model_diffs(raw_text)
    slips = id_slips(diffs, doc)
    text_on_list = [
        d.get("path")
        for d in diffs
        if d.get("operation") == "replace_text"
        and not isinstance(_at(doc, d.get("path")), str)
    ]
    failed = failures(last_turn(client, sid))
    meters = done["working_json"]["rulebook"]["meters"]
    labels = [m.get("label") for m in meters]
    # Renames ("Attraction" -> "Physical Attraction") are a fair reading of
    # the request; losing a meter is not.
    ids = {m.get("id") for m in meters}
    kept = all(m["id"] in ids for m in doc["rulebook"]["meters"])
    ok = not slips and not text_on_list and not failed and kept and len(labels) > 6
    for d in diffs:
        if d.get("operation") == "replace_text":
            print(
                "  TEXT",
                d.get("path"),
                repr(d.get("find"))[:80],
                "->",
                repr(d.get("replace"))[:80],
            )
    report(
        "yes_turn",
        ok,
        diffs,
        slips=slips,
        text_on_list=text_on_list,
        failed=failed[:3],
        meters=len(labels),
        kept=kept,
    )
    assert ok


def _at(doc, path):
    node = doc
    for part in (path or "").split("/")[1:]:
        try:
            node = node[int(part)] if isinstance(node, list) else node[part]
        except (KeyError, IndexError, ValueError, TypeError):
            return None
    return node


@pytest.mark.parametrize(
    "ids,big",
    [("numbered", False), ("numbered", True), ("plain", False)],
    ids=["append_numbered_small", "append_numbered_big", "append_plain_ids"],
)
def test_append_keywords(client, raw_text, ids, big):  # noqa: F811
    doc = love(ids, big)
    sid = seed(client, doc)
    done = chat(client, sid, APPEND)
    diffs = model_diffs(raw_text)
    got = {
        m["label"]: m["keywords"] for m in done["working_json"]["rulebook"]["meters"]
    }
    old = dict(zip(LABELS, OLD_KEYWORDS))
    wrong = {
        lab: [k for k in got[lab] if k not in old[lab] and k not in WANT[lab]]
        for lab in LABELS
    }
    wrong = {k: v for k, v in wrong.items() if v}
    missing = {lab: [k for k in WANT[lab] if k not in got[lab]] for lab in LABELS}
    missing = {k: v for k, v in missing.items() if v}
    lost = {lab: [k for k in old[lab] if k not in got[lab]] for lab in LABELS}
    lost = {k: v for k, v in lost.items() if v}
    failed = failures(last_turn(client, sid))
    ok = not wrong and not missing and not lost and not failed
    report(
        f"append_{ids}_{'big' if big else 'small'}",
        ok,
        diffs,
        wrong=wrong,
        missing=missing,
        lost=lost,
        failed=failed[:3],
    )
    assert ok
