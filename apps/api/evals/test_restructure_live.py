"""Live eval: restructure every element of an array into a new layout.

    cd apps/api && LIVE_LLM=1 LIVE_DEPLOYMENT=nvidia_nim PYTHONPATH=. \\
        uv run pytest evals/test_restructure_live.py -s
    # LIVE_DEPLOYMENT=ollama_local (default) | nvidia_nim; SKIN_COUNTS=40,449

Prod case 2026-11-22: 449 skins, model emitted per-element modifies with
{"$from": ...} placeholders (resolved server-side since 2026-11-23).

Each case prints one RESULT line with an outcome:
  mapped    every skin's id == its old localization_name (correct)
  asked     no diffs, model asked how to map (acceptable)
  unchanged diffs applied elsewhere (e.g. pack) but no skin changed
  partial   skins changed but not fully mapped; each keeps its own values
  nopack    (prod) skins mapped but the requested "pack" object is missing
  guarded   stamp guard held every-skin-identical diffs and asked
  flattened a skin lost its own name/texture/geometry (data loss) -> FAIL
  leaked    "$from" left in the document -> FAIL
"""

from __future__ import annotations

import json
import os

import pytest

from test_array_index_live import chat, client, raw_diffs, seed  # noqa: F401

pytestmark = pytest.mark.skipif(
    os.environ.get("LIVE_LLM") != "1", reason="live LLM eval; set LIVE_LLM=1"
)

COUNTS = [int(n) for n in os.environ.get("SKIN_COUNTS", "40,449").split(",")]
NAMES = ["Target", "Elemental Mage", "Oracle", "Sandcastle", "Thor", "Biohazard"]


def make_doc(n: int) -> dict:
    return {
        "skins": [
            {
                "localization_name": f"{NAMES[i % len(NAMES)]} {i}",
                "geometry": f"geometry.a{i}",
                "texture": f"a{i}.png",
                "type": "free",
            }
            for i in range(n)
        ]
    }


PROD = """change all the things in the skins json to match this layout exactly:
{
  "pack": {"id": "MyCustomPack", "type": "bedrock", "name": "My Custom Bedrock Pack"},
  "skins": [
    {"id": "Steve", "model": "steve", "geometry": "models/steve.obj",
     "textures": {"body": "assets/textures/steve_body.png"}}
  ]
}"""

EXPLICIT = (
    "Restructure every skin: rename localization_name to id, move texture "
    'into textures.body, add "model": "steve", and remove type. Keep each '
    "skin's own values."
)

MESSAGES = {"prod": PROD, "explicit": EXPLICIT}


OWN = ("localization_name", "texture", "geometry")  # per-skin values to keep


def classify(before: dict, after: dict, n_diffs: int, done: dict, kind: str) -> str:
    if "$from" in json.dumps(after):
        return "leaked"
    if str(done.get("explanation", "")).startswith("Not applied"):
        return "guarded"  # stamp guard held the stamped diffs and asked
    if n_diffs == 0:
        return "asked"
    skins = after.get("skins") if isinstance(after, dict) else None
    if not isinstance(skins, list) or len(skins) != len(before["skins"]):
        return "flattened"
    mapped = untouched = 0
    for old, new in zip(before["skins"], skins):
        if new == old:
            untouched += 1
        elif any(old[k] not in json.dumps(new) for k in OWN):
            return "flattened"  # this skin's own name / texture / geometry is gone
        elif isinstance(new, dict) and new.get("id") == old["localization_name"]:
            mapped += 1
    if mapped == len(skins):
        return "mapped" if kind != "prod" or "pack" in after else "nopack"
    if untouched == len(skins):
        return "unchanged"
    return "partial"


@pytest.mark.parametrize("count", COUNTS)
@pytest.mark.parametrize("kind", list(MESSAGES))
def test_restructure(client, raw_diffs, kind, count):  # noqa: F811
    doc = make_doc(count)
    sid = seed(client, doc)
    done = chat(client, sid, MESSAGES[kind])
    raw = [d for batch in raw_diffs for d in batch]
    after = client.get(f"/api/sessions/{sid}").json().get("working_json")
    turn = client.get(f"/api/sessions/{sid}").json()["conversation_history"][-1]
    statuses = [d.get("status") for d in turn.get("diffs", [])]
    model_from = sum("$from" in json.dumps(d.get("new_value")) for d in raw)
    outcome = classify(doc, after, len(raw), done, kind)
    print(
        f"\nRESULT {outcome:9} {kind:8} n={count:<4} diffs={len(raw)} "
        f"failed={statuses.count('failed')} model_$from={model_from} "
        f"pack={'pack' in (after or {})} "
        f"skin0={json.dumps((after or {}).get('skins', [None])[0])[:160]} "
        f"expl={str(done.get('explanation'))[:120]!r}"
    )
    skin0 = [
        {k: d.get(k) for k in ("operation", "path", "new_value")}
        for d in raw
        if str(d.get("path", "")).startswith("/skins/0/") or d.get("path") == "/skins/0"
    ]
    applied0 = [
        {k: d.get(k) for k in ("operation", "path", "new_value", "status")}
        for d in turn.get("diffs", [])
        if str(d.get("path", "")).startswith("/skins/0")
    ]
    print(f"  RAW skin0: {json.dumps(skin0)[:600]}")
    for d in turn.get("diffs", []):
        if d.get("status") == "failed":
            print(
                f"  FAILED {d.get('operation')} {d.get('path')}: {d.get('failure_reason')}"
            )
    if len(raw) <= 3:
        print(f"  RAW all: {json.dumps(raw)[:600]}")
    print(f"  STORED skin0: {json.dumps(applied0)[:600]}")
    assert outcome not in ("leaked", "flattened"), outcome
