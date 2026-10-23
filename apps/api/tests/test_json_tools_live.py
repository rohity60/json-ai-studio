"""Live eval: lookup tools + questions on large documents (ADR-0024). Opt-in.

Pinned to the local Ollama deployment (see conftest `pinned_deployment`).

    cd apps/api && LIVE_LLM=1 PYTHONPATH=. uv run pytest tests/test_json_tools_live.py -v -s
"""

from __future__ import annotations

import copy
import json
import os
import time

import pytest

from src.json_ai_studio.services.chat_service import parse_sse
from test_chat_history_live import GITA, client, seed  # noqa: F401 (fixture)

pytestmark = pytest.mark.skipif(
    os.environ.get("LIVE_LLM") != "1", reason="live LLM eval; set LIVE_LLM=1"
)

BUSY = {"service_unavailable", "rate_limit", "credit_limit"}


def chat_events(client, sid, message, attempts=1):
    """Send a turn; returns (complete payload, tool events).

    No whole-turn retries by default: the gateway retries a failed tool
    round itself, and re-sending a whole multi-round turn burned per-minute
    token quotas (Google free tier) and made every attempt fail."""
    for _ in range(attempts):
        resp = client.post(
            "/api/chat", data={"session_id": sid, "message": message}, timeout=1200
        )
        events = [parse_sse(b) for b in resp.text.split("\n\n") if b.strip()]
        kinds = {e for e, _ in events}
        if kinds & BUSY or "complete" not in kinds:
            time.sleep(10)
            continue
        done = next(p for e, p in events if e == "complete")
        tools = [p for e, p in events if e == "tool"]
        print(
            f"\nUSER {message!r}\n  tools={[(t['name'], t['args']) for t in tools]}\n  -> {done['explanation']}"
        )
        if done.get("question"):
            print(f"  question={done['question']}")
        return done, tools
    pytest.fail("no complete event")


# -- synthetic UAssetAPI dump (structure only; not the user's file) ----------

T = lambda n: f"UAssetAPI.ExportTypes.{n}, UAssetAPI"  # noqa: E731
K = lambda n: f"UAssetAPI.Kismet.Bytecode.Expressions.{n}, UAssetAPI"  # noqa: E731
IMPORTS = [
    "MagazineStart",
    "MagazineStop",
    "BPStartUseAmmoSec",
    "HasAuthority",
    "IsLocallyControlled",
]


def _fn(name, stack_nodes, duration=5.0):
    return {
        "$type": T("FunctionExport"),
        "ObjectName": name,
        "OuterIndex": 1,
        "FunctionFlags": "FUNC_BlueprintEvent, FUNC_Public",
        "ScriptBytecode": [
            {
                "$type": K("EX_FinalFunction"),
                "StackNode": node,
                "Parameters": [{"$type": K("EX_FloatConst"), "Value": duration}],
            }
            for node in stack_nodes
        ]
        + [{"$type": K("EX_Return"), "ReturnExpression": {"$type": K("EX_Nothing")}}],
    }


UASSET = {
    "$type": "UAssetAPI.UAsset, UAssetAPI",
    "NameMap": ["BP_Ch015_ActionAttack_Unique3", *IMPORTS]
    + [f"Name_{i}" for i in range(800)],
    "Imports": [
        {
            "$type": "UAssetAPI.Import, UAssetAPI",
            "ObjectName": n,
            "ClassName": "Function",
            "OuterIndex": -1,
        }
        for n in IMPORTS
    ],
    "Exports": [
        {
            "$type": T("ClassExport"),
            "ObjectName": "BP_Ch015_ActionAttack_Unique3_C",
            "ClassFlags": "CLASS_Compiled",
        },
        # Only this function calls MagazineStop (StackNode -2 → Imports[1]).
        _fn("BPOnEmitted", [-3, -2], duration=8.0),
    ]
    + [_fn(f"ExecuteUbergraph_{i}", [-4, -5]) for i in range(300)],
}
assert len(json.dumps(UASSET, separators=(",", ":"))) > 120_000  # skeleton mode


def test_gita_hidden_record_found_with_tools(client):
    """Prod 2026-10-11: specific records were invisible in the skeleton."""
    doc = copy.deepcopy(GITA)
    sid = seed(client, doc)
    done, tools = chat_events(
        client, sid, "Change the sectionId to abc for slok 23 of chapter 3"
    )
    ids = [r["sectionId"] for r in done["working_json"]["records"]]
    target = 47 + 72 + 22  # chapters 1-2 then slok 23 of chapter 3
    assert ids[target] == "abc", (tools, done["explanation"])
    assert ids.count("abc") == 1


def test_uasset_analysis_traces_reference_without_editing(client):
    """Prod 2026-10-15: 'trace what ends the ability … before editing'."""
    sid = seed(client, UASSET)
    done, tools = chat_events(
        client,
        sid,
        "Analyze only, do not edit: which function export calls MagazineStop? "
        "Resolve the StackNode reference through Imports and cite the JSON paths.",
    )
    assert done["working_json"] == UASSET  # analysis only
    assert tools, "expected lookups"
    assert (
        "BPOnEmitted" in done["explanation"] or "/Exports/1" in done["explanation"]
    ), done["explanation"]


def test_vague_request_asks_or_analyzes_instead_of_patching(client):
    """Prod 2026-10-15: 'make this move last forever' with no context."""
    sid = seed(client, UASSET)
    done, _ = chat_events(client, sid, "make this move last forever")
    changed = done["working_json"] != UASSET
    assert done.get("question") or not changed, done["explanation"]


# -- small variant: same structure, ~20 functions, skeleton forced ----------
# Fits free-tier per-minute token caps (Google: 16k input tokens/min), so
# multi-round tool turns can complete; checks tool-use CORRECTNESS.

SMALL_UASSET = {
    **{k: v for k, v in UASSET.items() if k not in ("NameMap", "Exports")},
    "NameMap": ["BP_Ch015_ActionAttack_Unique3", *IMPORTS],
    "Exports": UASSET["Exports"][:2]
    + [_fn(f"ExecuteUbergraph_{i}", [-4, -5]) for i in range(20)],
}


@pytest.fixture
def small_skeleton(monkeypatch):
    from src.json_ai_studio.settings import get_settings

    monkeypatch.setenv("LLM_MAX_INLINE_CHARS", "2000")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_small_uasset_analysis_traces_reference(client, small_skeleton):
    sid = seed(client, SMALL_UASSET)
    done, tools = chat_events(
        client,
        sid,
        "Analyze only, do not edit: which function export calls MagazineStop? "
        "Resolve the StackNode reference through Imports and cite the JSON paths.",
    )
    assert done["working_json"] == SMALL_UASSET
    assert tools, "expected lookups"
    assert (
        "BPOnEmitted" in done["explanation"] or "/Exports/1" in done["explanation"]
    ), done["explanation"]


def test_small_uasset_vague_request(client, small_skeleton):
    sid = seed(client, SMALL_UASSET)
    done, _ = chat_events(client, sid, "make this move last forever")
    assert done.get("question") or done["working_json"] == SMALL_UASSET, done[
        "explanation"
    ]


def test_small_uasset_targeted_edit(client, small_skeleton):
    """A concrete edit on a value hidden in the skeleton: BPOnEmitted's
    duration constant (8.0, unlike every other function's 5.0)."""
    sid = seed(client, SMALL_UASSET)
    done, tools = chat_events(
        client,
        sid,
        "In the BPOnEmitted function, change the float duration constant 8.0 to 0.0",
    )
    params = [
        p["Value"]
        for expr in done["working_json"]["Exports"][1]["ScriptBytecode"]
        for p in expr.get("Parameters", [])
    ]
    assert params == [0.0, 0.0], (params, tools)
    others = [
        p["Value"]
        for e in done["working_json"]["Exports"][2:]
        for expr in e["ScriptBytecode"]
        for p in expr.get("Parameters", [])
    ]
    assert set(others) == {5.0}
