"""Live eval: whole-document review jobs (ADR-0026), incl. layout changes. Opt-in.

    cd apps/api && LIVE_LLM=1 LIVE_DEPLOYMENT=nvidia_nim PYTHONPATH=. \\
        uv run pytest evals/test_review_live.py -s
    # LIVE_DEPLOYMENT=ollama_local (default) | nvidia_nim; REVIEW_SKINS=449

Drives a job the way the web client does: one POST .../next per batch,
retrying a failed batch, answering a guard's question with the "keep own
values" option. Each case prints one ``RESULT`` line (grep it).

Cases:
  layout_skins   prod 2026-11-22/23: 449 skins → the example skin's layout
                 (+ a top-level "pack"). Live 2026-11-23 before layout.py:
                 pack copied into skins, skins wrapped/inserted, names lost.
  layout_tracks  another domain: tracks → {name, artist, length}; "artist"
                 has no counterpart, so every track gets the example's.
  typos          a plain review (no example): fix "teh" in every entry; the
                 layout rules must not change how it works.

Hard failures: data loss (a record's own value gone), records added or
removed, layout rules in a non-layout prompt. Exact-layout rate has a floor
(model variance), printed in RESULT.
"""

from __future__ import annotations

import json
import os
import time

import pytest

from src.json_ai_studio.services import job_packing
from src.json_ai_studio.services.chat_service import parse_sse
from test_array_index_live import client, seed  # noqa: F401 (fixture)

pytestmark = pytest.mark.skipif(
    os.environ.get("LIVE_LLM") != "1", reason="live LLM eval; set LIVE_LLM=1"
)

KEEP = "Keep each element's own values"  # prefix of both guards' keep option
SKINS = int(os.environ.get("REVIEW_SKINS", "449"))
NAMES = ["Target", "Elemental Mage", "Oracle", "Sandcastle", "Thor", "Biohazard"]


# -- driver ----------------------------------------------------------------


def _next(client, sid, jid, guidance=None):
    body = {"json": {"guidance": guidance}} if guidance else {}
    resp = client.post(f"/api/sessions/{sid}/jobs/{jid}/next", timeout=900, **body)
    assert resp.status_code == 200, resp.text
    events = [parse_sse(b) for b in resp.text.split("\n\n") if b.strip()]
    for kind in ("batch_complete", "batch_failed", "rate_limit", "credit_limit"):
        for e, p in events:
            if e == kind:
                return e, p or {}
    return "none", {}


def run_job(client, sid, scope, instruction, max_calls=40) -> dict:
    """Run a review to the end. Returns counts for the RESULT line."""
    resp = client.post(
        f"/api/sessions/{sid}/jobs",
        json={"scope_path": scope, "instruction": instruction},
    )
    assert resp.status_code == 201, resp.text
    jid = resp.json()["id"]
    stats = {"calls": 0, "batches": 0, "failed": 0, "held": 0, "errors": []}
    guidance = None
    while stats["calls"] < max_calls:
        stats["calls"] += 1
        kind, data = _next(client, sid, jid, guidance)
        guidance = None
        if kind == "batch_complete":
            stats["batches"] += 1
            if data.get("held"):
                stats["held"] += 1
                options = (data.get("question") or {}).get("options") or []
                guidance = next((o for o in options if o.startswith(KEEP)), None)
            if data["job"]["status"] == "done":
                stats["done"] = True
                return stats
        elif kind == "batch_failed":
            stats["failed"] += 1
            stats["errors"].append(data.get("error", "")[:120])
        else:  # quota / provider busy: wait and ask again
            time.sleep(int(data.get("retry_after") or 20))
    stats["done"] = False
    return stats


def working(client, sid) -> dict:
    return client.get(f"/api/sessions/{sid}").json()["working_json"]


def result(case, ok, stats, extra):
    errs = "; ".join(sorted(set(stats["errors"])))[:300]
    print(
        f"\nRESULT {'ok  ' if ok else 'FAIL'} {case:14} calls={stats['calls']} "
        f"batches={stats['batches']} failed={stats['failed']} held={stats['held']} "
        f"{extra} errors=[{errs}]"
    )


# -- cases -----------------------------------------------------------------

SKIN_EXAMPLE = {
    "pack": {"id": "MyCustomPack", "type": "bedrock", "name": "My Custom Bedrock Pack"},
    "skins": [
        {
            "id": "Steve",
            "model": "steve",
            "geometry": "models/steve.obj",
            "textures": {"body": "assets/textures/steve_body.png"},
        }
    ],
}


def test_layout_skins(client):  # noqa: F811
    before = [
        {
            "localization_name": f"{NAMES[i % len(NAMES)]} {i}",
            "geometry": f"geometry.a{i}",
            "texture": f"a{i}.png",
            "type": "free",
        }
        for i in range(SKINS)
    ]
    sid = seed(client, {"skins": before})
    stats = run_job(
        client,
        sid,
        "/skins",
        "Review all skins and make each one match this layout exactly: "
        + json.dumps(SKIN_EXAMPLE),
    )
    after = working(client, sid)
    skins = after["skins"]
    want = [
        {
            "id": b["localization_name"],
            "model": "steve",
            "geometry": b["geometry"],
            "textures": {"body": b["texture"]},
        }
        for b in before
    ]
    exact = sum(a == w for a, w in zip(skins, want))
    lost = [
        i
        for i, (a, b) in enumerate(zip(skins, before))
        if not {b["localization_name"], b["geometry"], b["texture"]} <= set(_strings(a))
    ]
    ok = (
        stats["done"]
        and len(skins) == len(before)
        and after.get("pack") == SKIN_EXAMPLE["pack"]
        and not lost
        and exact >= 0.95 * len(before)
    )
    result(
        "layout_skins",
        ok,
        stats,
        f"n={len(before)} exact={exact} lost={len(lost)} count={len(skins)} "
        f"pack={after.get('pack') == SKIN_EXAMPLE['pack']} "
        f"skin0={json.dumps(skins[0])[:140]}",
    )
    assert stats["done"], stats
    assert len(skins) == len(before), "records added or removed"
    assert not lost, f"own values lost in {len(lost)} skins, e.g. {skins[lost[0]]}"
    assert after.get("pack") == SKIN_EXAMPLE["pack"]
    assert exact >= 0.95 * len(before), f"only {exact} skins in the exact layout"


def test_layout_tracks(client):  # noqa: F811
    genres = ["pop", "rock", "jazz"]
    before = [
        {"title": f"Song {i}", "duration": 120 + i, "genre": genres[i % 3]}
        for i in range(60)
    ]
    example = {"tracks": [{"name": "Intro", "artist": "The Band", "length": 200}]}
    sid = seed(client, {"album": "Live", "tracks": before})
    stats = run_job(
        client,
        sid,
        "/tracks",
        "Review every track and convert it to this layout: " + json.dumps(example),
    )
    tracks = working(client, sid)["tracks"]
    want = [
        {"name": b["title"], "artist": "The Band", "length": b["duration"]}
        for b in before
    ]
    exact = sum(a == w for a, w in zip(tracks, want))
    lost = [
        i
        for i, (a, b) in enumerate(zip(tracks, before))
        if not isinstance(a, dict)
        or a.get("name") != b["title"]
        or a.get("length") != b["duration"]
    ]
    ok = stats["done"] and len(tracks) == len(before) and not lost and exact >= 57
    result(
        "layout_tracks",
        ok,
        stats,
        f"n={len(before)} exact={exact} lost={len(lost)} "
        f"track0={json.dumps(tracks[0])}",
    )
    assert stats["done"], stats
    assert len(tracks) == len(before)
    assert not lost, f"own values lost in {len(lost)} tracks, e.g. {tracks[lost[0]]}"
    assert exact >= 57, f"only {exact}/60 tracks in the exact layout"


def test_typo_review_unchanged_by_layout_rules(client, monkeypatch):  # noqa: F811
    prompts: list[str] = []
    real = job_packing.lean_messages

    def spy(instruction, items, extra_rules=""):
        msgs = real(instruction, items, extra_rules)
        if items:
            prompts.append(msgs[0]["content"])
        return msgs

    monkeypatch.setattr(job_packing, "lean_messages", spy)
    before = [
        {"id": i, "content": f"This is teh note number {i} about the plan."}
        for i in range(40)
    ]
    sid = seed(client, {"name": "notes", "entries": before})
    stats = run_job(
        client, sid, "/entries", "Review all entries and fix the spelling mistakes"
    )
    entries = working(client, sid)["entries"]
    fixed = sum(
        "teh" not in e["content"] and "the note" in e["content"] for e in entries
    )
    damaged = [
        e
        for e, b in zip(entries, before)
        if e["id"] != b["id"] or f"number {b['id']} about" not in e["content"]
    ]
    rules = any("LAYOUT CHANGE" in p for p in prompts)
    ok = stats["done"] and not damaged and not rules and fixed >= 36
    result(
        "typos",
        ok,
        stats,
        f"n={len(before)} fixed={fixed} damaged={len(damaged)} layout_rules={rules}",
    )
    assert stats["done"], stats
    assert not rules, "layout rules leaked into a non-layout review"
    assert not damaged, f"entries damaged, e.g. {damaged[0]}"
    assert fixed >= 36, f"only {fixed}/40 typos fixed"


def _strings(node) -> list[str]:
    if isinstance(node, dict):
        return [s for v in node.values() for s in _strings(v)]
    if isinstance(node, list):
        return [s for v in node for s in _strings(v)]
    return [node] if isinstance(node, str) else []
