"""Deployment token budget, turn planner, trimmer (ADR-0025).

LLM calls are stubbed; token estimates are pinned to chars/4 so planner
decisions are deterministic.
"""

from __future__ import annotations

import json
import math
import uuid
from types import SimpleNamespace

import pytest

from src.json_ai_studio import gateway as gw
from src.json_ai_studio.auth import Principal
from src.json_ai_studio.json_trim import fit_trim, trim_json
from src.json_ai_studio.services import credit_service
from src.json_ai_studio.services import deployment_budget as budget
from src.json_ai_studio.services import turn_planner
from src.json_ai_studio.services.chat_service import parse_sse
from src.json_ai_studio.services.turn_planner import TooLarge, TurnPlan, plan_turn
from src.json_ai_studio.settings import get_settings

RECORDS = {
    "source": "test",
    "records": [
        {"id": i, "chapter": f"ch_{i // 10}", "text": "lorem ipsum " * 20}
        for i in range(200)
    ],
}


def _chars4(model, messages):
    return sum(len(str(m.get("content") or "")) for m in messages) // 4


@pytest.fixture(autouse=True)
def clean(monkeypatch):
    budget.reset()
    monkeypatch.setattr(budget, "estimate_tokens", _chars4)
    get_settings.cache_clear()
    yield
    budget.reset()
    get_settings.cache_clear()


def _deployment(tpm=None, tools=True, name="fake", interval=0):
    return SimpleNamespace(
        name=name,
        model_prefix="fake/",
        base_model="m",
        base_url="http://fake",
        api_key="",
        supports_tools=tools,
        tool_streaming=False,
        tpm_input_limit=tpm,
        context_tokens=None,
        min_call_interval_s=interval,
        litellm_model=lambda m: m,
        completion_params=lambda model, reasoning=None: {},
        pricing=lambda model: (0.0, 0.0),
    )


def _overhead() -> int:
    """Tokens of the system prompt + user message with an empty document."""
    from src.json_ai_studio.prompting import build_system_prompt

    return _chars4("", [{"content": build_system_prompt({}, mode="inline")}]) + 1


def _tpm_for(plan_tokens: int) -> int:
    """tpm_input_limit whose planning budget (× headroom) is plan_tokens."""
    return math.ceil(plan_tokens / get_settings().deployment_budget_headroom)


# ---------------------------------------------------------------------------
# Counter
# ---------------------------------------------------------------------------


def test_reserve_within_limit_then_wait():
    dep = _deployment(tpm=1000)  # gated at 800 (headroom 0.8)
    res, wait = budget.try_reserve(dep, "m", 600)
    assert res is not None and wait == 0
    res2, wait2 = budget.try_reserve(dep, "m", 300)
    assert res2 is None
    assert 59 < wait2 <= 60  # frees when the first call leaves the window


def test_call_larger_than_limit_never_fits():
    res, wait = budget.try_reserve(_deployment(tpm=1000), "m", 801)
    assert res is None and math.isinf(wait)


def test_release_gives_tokens_back():
    dep = _deployment(tpm=1000)
    res, _ = budget.try_reserve(dep, "m", 700)
    budget.release(res)
    assert budget.try_reserve(dep, "m", 700)[0] is not None


def test_settle_replaces_estimate_and_calibrates():
    dep = _deployment(tpm=1000)
    res, _ = budget.try_reserve(dep, "m", 400)
    budget.settle(res, 200)  # provider counted fewer tokens
    assert budget.try_reserve(dep, "m", 650)[0] is not None  # 200 + 650*ratio
    assert budget.calibrated("fake:m", 100) < 100


def test_gate_is_headroom_not_full_limit():
    dep = _deployment(tpm=16_000)  # Google free tier → gated at 12.8k
    for _ in range(2):
        assert budget.try_reserve(dep, "m", 4_800)[0] is not None
    res, wait = budget.try_reserve(dep, "m", 4_800)  # would reach 14.4k
    assert res is None and wait > 0


def test_block_after_provider_429():
    dep = _deployment(tpm=1000)
    budget.block(dep, "m", 13)
    res, wait = budget.try_reserve(dep, "m", 1)
    assert res is None and 12 < wait <= 13


def test_no_limit_is_a_no_op():
    res, wait = budget.try_reserve(_deployment(tpm=None), "m", 10**9)
    assert res is not None and res.entry is None and wait == 0


def test_keys_are_per_deployment_and_model():
    a, b = _deployment(tpm=1000, name="a"), _deployment(tpm=1000, name="b")
    assert budget.try_reserve(a, "m", 700)[0] is not None
    assert budget.try_reserve(b, "m", 700)[0] is not None
    assert budget.try_reserve(a, "other", 700)[0] is not None


# ---------------------------------------------------------------------------
# Trimmer
# ---------------------------------------------------------------------------


def test_trim_keeps_keys_and_reports_cuts():
    trimmed, cuts = trim_json(RECORDS, keep_items=3, str_cap=50)
    assert len(trimmed["records"]) == 3
    assert set(trimmed["records"][0]) == {"id", "chapter", "text"}
    assert trimmed["records"][0]["text"].endswith("…")
    by_kind = {c["kind"]: c for c in cuts}
    assert by_kind["array"] == {
        "path": "/records",
        "kind": "array",
        "from": 200,
        "to": 3,
    }
    assert by_kind["string"]["path"] == "/records/*/text"
    assert by_kind["string"]["count"] == 3


def test_fit_trim_keeps_as_many_items_as_fit():
    def fits(trimmed, cuts):
        return len(json.dumps(trimmed)) <= 5_000

    trimmed, _ = fit_trim(RECORDS, fits, min_items=1)
    n = len(trimmed["records"])
    assert n > 1
    assert len(json.dumps(trim_json(RECORDS, n + 1, 300)[0])) > 5_000


def test_fit_trim_gives_up_below_min_items():
    assert fit_trim(RECORDS, lambda t, c: False, min_items=3) is None


# ---------------------------------------------------------------------------
# Planner
# ---------------------------------------------------------------------------


def test_no_budget_keeps_legacy_behaviour():
    plan = plan_turn(RECORDS, "hi", [], _deployment(tpm=None), "fake/m")
    assert isinstance(plan, TurnPlan)
    assert plan.mode == "inline"  # under LLM_MAX_INLINE_CHARS
    assert plan.toolbox is None


def test_small_doc_inlines_under_budget():
    plan = plan_turn({"a": 1}, "hi", [], _deployment(tpm=16_000), "fake/m")
    assert plan.mode == "inline" and plan.max_rounds == 0


def test_mid_size_doc_gets_skeleton_and_tools_not_inline():
    # ~60k chars: fine for the old 120k-char cap, far over 16k tokens/min.
    plan = plan_turn(RECORDS, "hi", [], _deployment(tpm=16_000), "fake/m")
    assert plan.mode == "skeleton"
    assert plan.toolbox is not None  # lookups reach the full document
    assert "STRUCTURAL SKELETON" in plan.messages[0]["content"]
    assert "TRIMMED" not in plan.messages[0]["content"]


def test_skeleton_first_call_fits_and_keeps_all_rounds():
    # Rounds are not cut up front: later rounds wait for capacity instead.
    dep = _deployment(tpm=16_000)
    plan = plan_turn(RECORDS, "hi", [], dep, "fake/m")
    limit = turn_planner.turn_budget(dep, "fake/m")
    assert budget.calibrated("fake:fake/m", plan.raw_estimate) <= limit
    assert plan.max_rounds == get_settings().chat_tool_max_rounds


def test_history_dropped_before_shrinking_view():
    history = [
        {"role": "user", "content": "x" * 4_000},
        {"role": "assistant", "content": "y" * 4_000},
    ]
    # ~1k-token doc + ~2k-token history; budget fits the doc alone.
    dep = _deployment(tpm=_tpm_for(_overhead() + 1_500))
    doc = {"a": "z" * 4_000}
    plan = plan_turn(doc, "hi", history, dep, "fake/m")
    assert plan.mode == "inline"
    assert len(plan.messages) == 2  # system + user, history dropped


def test_without_tools_falls_back_to_skeleton_or_too_large():
    plan = plan_turn(RECORDS, "hi", [], _deployment(tpm=16_000, tools=False), "fake/m")
    assert isinstance(plan, TurnPlan)
    assert plan.toolbox is None and plan.max_rounds == 0


def test_too_large_reports_kb_sections_and_trimmed_copy():
    doc = {
        "settings": {"theme": "dark", "lang": "en"},
        "records": RECORDS["records"],
    }
    # Room for ~200 doc tokens: not even the skeleton fits.
    dep = _deployment(tpm=_tpm_for(_overhead() + 200))
    plan = plan_turn(doc, "hi", [], dep, "fake/m")
    assert isinstance(plan, TooLarge)
    assert plan.doc_kb > plan.max_kb > 0
    assert plan.sections[0] == {"path": "/settings", "kb": 1}  # top level first
    assert "/records" not in [s["path"] for s in plan.sections]
    copy = plan.trimmed
    assert copy is not None
    assert len(json.dumps(copy["working_json"])) < len(json.dumps(doc))
    assert any(c["path"] == "/records" for c in copy["cuts"])


# ---------------------------------------------------------------------------
# Gateway: deployment budget vs user quota
# ---------------------------------------------------------------------------


@pytest.fixture
def stub_llm(monkeypatch):
    calls: list = []
    deducted: list = []

    async def fake_deduct(principal, credits, tokens):
        deducted.append(tokens)

    async def fake_acompletion(**kw):
        calls.append(kw)
        reply = json.dumps({"diffs": [], "explanation": "ok"})

        async def chunks():
            yield SimpleNamespace(
                choices=[SimpleNamespace(delta=SimpleNamespace(content=reply))],
                usage=None,
            )
            yield SimpleNamespace(
                choices=[],
                usage={"prompt_tokens": 100, "completion_tokens": 5},
            )

        return chunks()

    # The budget's clock only moves when the gateway sleeps.
    import time as _time

    clock = {"now": _time.monotonic()}

    async def fake_sleep(seconds):
        clock["now"] += seconds

    monkeypatch.setattr(credit_service, "deduct", fake_deduct)
    monkeypatch.setattr(gw.litellm, "acompletion", fake_acompletion)
    monkeypatch.setattr(gw.asyncio, "sleep", fake_sleep)
    monkeypatch.setattr(budget, "time", SimpleNamespace(monotonic=lambda: clock["now"]))
    return SimpleNamespace(calls=calls, deducted=deducted)


async def _invoke(monkeypatch, dep, planner=None):
    monkeypatch.setattr(
        gw.DeploymentRegistry, "pick_default", classmethod(lambda cls: dep)
    )
    principal = Principal(kind="anonymous", quota_key=uuid.uuid4().hex, rate_key="r")
    events = []
    async for text in gw.GatewayService.invoke(
        "s", "hi", principal, "SYSTEM", planner=planner
    ):
        events.append(parse_sse(text))
    return events


async def test_wait_beyond_max_rejects_before_calling_provider(monkeypatch, stub_llm):
    dep = _deployment(tpm=1_000)
    budget.block(dep, "fake/m", 120)  # provider said: retry in 2 minutes
    events = await _invoke(monkeypatch, dep)
    event, payload = events[-1]
    assert event == "rate_limit"
    assert payload["scope"] == "model"
    assert payload["login_available"] is False
    assert 115 <= payload["retry_after"] <= 120
    assert stub_llm.calls == []  # provider never called → never 429s
    assert stub_llm.deducted == []  # user quota untouched


async def test_short_wait_streams_waiting_then_answers(monkeypatch, stub_llm):
    dep = _deployment(tpm=1_000)
    budget.block(dep, "fake/m", 3)  # frees within deployment_budget_max_wait_s
    events = await _invoke(monkeypatch, dep)
    names = [e for e, _ in events]
    assert "waiting" in names
    assert names.index("waiting") < names.index("thinking")
    assert stub_llm.calls and stub_llm.deducted == [105]


async def test_full_window_waits_then_answers(monkeypatch, stub_llm):
    dep = _deployment(tpm=1_000)
    budget.try_reserve(dep, "fake/m", 800)  # another user's turn filled it
    events = await _invoke(monkeypatch, dep)
    waits = [p["retry_after"] for e, p in events if e == "waiting"]
    assert waits and waits[0] == 60 and waits == sorted(waits, reverse=True)
    assert [e for e, _ in events][-1] == "usage"  # answered after the wait
    assert len(stub_llm.calls) == 1


async def test_tool_round_waits_for_capacity_instead_of_forcing(monkeypatch, stub_llm):
    from src.json_ai_studio.json_tools import JsonToolbox

    def response(content="", calls=(), prompt=10):
        tool_calls = [
            SimpleNamespace(
                id=f"c{i}", function=SimpleNamespace(name=n, arguments=json.dumps(a))
            )
            for i, (n, a) in enumerate(calls)
        ]
        message = SimpleNamespace(content=content, tool_calls=tool_calls or None)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=message)],
            usage=SimpleNamespace(prompt_tokens=prompt, completion_tokens=5),
        )

    final = json.dumps({"diffs": [], "explanation": "found it"})
    script = [response(calls=[("search", {"query": "ch_3"})], prompt=1_500)]
    script.append(response(content=final, prompt=150))
    sent: list = []

    async def fake_acompletion(**kw):
        sent.append(kw["messages"])
        return script.pop(0)

    monkeypatch.setattr(gw.litellm, "acompletion", fake_acompletion)
    dep = _deployment(tpm=2_000)  # gated at 1.6k
    monkeypatch.setattr(
        gw.DeploymentRegistry, "pick_default", classmethod(lambda cls: dep)
    )
    principal = Principal(kind="anonymous", quota_key="q", rate_key="r")
    events = []
    async for text in gw.GatewayService.invoke(
        "s", "hi", principal, "SYSTEM", toolbox=JsonToolbox(RECORDS)
    ):
        events.append(parse_sse(text))
    names = [e for e, _ in events]
    # Round 1 used 1.5k of 1.6k: round 2 waited for the window, then ran.
    assert names.index("tool") < names.index("waiting") < names.index("thinking")
    assert [p["text"] for e, p in events if e == "thinking"] == [final]
    assert len(sent) == 2
    assert not any("Tool budget used up" in str(m) for m in sent[1])


async def test_success_settles_provider_count(monkeypatch, stub_llm):
    dep = _deployment(tpm=1_000)
    await _invoke(monkeypatch, dep)
    q = budget._windows["fake:fake/m"]
    assert [t for _, t in q] == [100.0]  # estimate replaced by usage


async def test_too_large_ends_turn_without_llm_call(monkeypatch, stub_llm):
    dep = _deployment(tpm=16_000)
    tl = TooLarge(doc_kb=180, max_kb=40, sections=[], trimmed=None)
    events = await _invoke(monkeypatch, dep, planner=lambda d, m: tl)
    event, payload = events[-1]
    assert event == "input_too_large"
    assert payload["doc_kb"] == 180 and payload["max_kb"] == 40
    assert "180 KB" in payload["message"]
    assert "token" not in payload["message"].lower()
    assert stub_llm.calls == [] and stub_llm.deducted == []


async def test_provider_429_is_model_rate_limit_and_blocks(monkeypatch, stub_llm):
    import litellm

    async def limited(**kw):
        raise litellm.RateLimitError(
            message="Quota exceeded. Please retry in 13.5s.",
            llm_provider="gemini",
            model="gemma",
        )

    monkeypatch.setattr(gw.litellm, "acompletion", limited)
    dep = _deployment(tpm=1_000)
    events = await _invoke(monkeypatch, dep)
    event, payload = events[-1]
    assert event == "rate_limit"
    assert payload == {
        "scope": "model",
        "message": gw.MODEL_BUSY_MESSAGE,
        "retry_after": 14,
        "login_available": False,
    }
    assert budget.try_reserve(dep, "fake/m", 1)[0] is None  # blocked
    # Google counts a failed call's input too: the reservation stays.
    assert len(budget._windows["fake:fake/m"]) == 1


async def test_server_error_not_retried_and_stays_counted(monkeypatch, stub_llm):
    import litellm

    attempts = []

    async def broken(**kw):
        attempts.append(1)
        raise litellm.InternalServerError(
            message="500 Internal error encountered.", llm_provider="gemini", model="g"
        )

    monkeypatch.setattr(gw.litellm, "acompletion", broken)
    dep = _deployment(tpm=1_000)
    events = await _invoke(monkeypatch, dep)
    assert events[-1][0] == "service_unavailable"
    assert len(attempts) == 1  # no retry on 5xx
    # Google counts the failed call's input: the reservation stays.
    assert len(budget._windows["fake:fake/m"]) == 1


# ---------------------------------------------------------------------------
# Pacing: min_call_interval_s between call starts, global per deployment
# ---------------------------------------------------------------------------


def test_slots_are_spaced_across_callers():
    dep = _deployment(tpm=16_000, interval=15)
    waits = [budget.claim_slot(dep, "m") for _ in range(4)]
    assert waits[0] == 0
    assert [round(w) for w in waits[1:]] == [15, 30, 45]


def test_no_interval_means_no_pacing():
    dep = _deployment(tpm=16_000)
    assert budget.claim_slot(dep, "m") == budget.claim_slot(dep, "m") == 0


async def test_second_turn_waits_for_its_slot(monkeypatch, stub_llm):
    dep = _deployment(tpm=16_000, interval=15)
    await _invoke(monkeypatch, dep)  # takes slot 0
    events = await _invoke(monkeypatch, dep)  # another user, right after
    waits = [p["retry_after"] for e, p in events if e == "waiting"]
    assert waits[0] == 15 and waits == sorted(waits, reverse=True)
    assert [e for e, _ in events][-1] == "usage"
    assert len(stub_llm.calls) == 2


async def test_tool_rounds_are_paced(monkeypatch, stub_llm):
    from src.json_ai_studio.json_tools import JsonToolbox

    tool_call = SimpleNamespace(
        id="c0",
        function=SimpleNamespace(name="search", arguments='{"query": "ch_3"}'),
    )
    script = [
        SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content="", tool_calls=[tool_call])
                )
            ],
            usage=SimpleNamespace(prompt_tokens=100, completion_tokens=5),
        ),
        SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content='{"diffs": [], "explanation": "ok"}', tool_calls=None
                    )
                )
            ],
            usage=SimpleNamespace(prompt_tokens=120, completion_tokens=5),
        ),
    ]

    async def fake_acompletion(**kw):
        return script.pop(0)

    monkeypatch.setattr(gw.litellm, "acompletion", fake_acompletion)
    dep = _deployment(tpm=16_000, interval=15)
    monkeypatch.setattr(
        gw.DeploymentRegistry, "pick_default", classmethod(lambda cls: dep)
    )
    principal = Principal(kind="anonymous", quota_key="q", rate_key="r")
    events = []
    async for text in gw.GatewayService.invoke(
        "s", "hi", principal, "SYSTEM", toolbox=JsonToolbox(RECORDS)
    ):
        events.append(parse_sse(text))
    names = [e for e, _ in events]
    # Plenty of tokens left, but round 2 still waits for its 15 s slot.
    assert names.index("tool") < names.index("waiting") < names.index("thinking")
    assert [p["retry_after"] for e, p in events if e == "waiting"][0] == 15


async def test_slot_beyond_max_wait_rejects(monkeypatch, stub_llm):
    dep = _deployment(tpm=16_000, interval=15)
    for _ in range(5):  # four queued calls ahead: next slot is 75 s away
        budget.claim_slot(dep, "fake/m")
    events = await _invoke(monkeypatch, dep)
    event, payload = events[-1]
    assert event == "rate_limit" and payload["scope"] == "model"
    assert stub_llm.calls == []


async def test_single_call_not_retried_after_text_streamed(monkeypatch, stub_llm):
    import litellm

    async def breaks_mid_answer(**kw):
        async def chunks():
            yield SimpleNamespace(
                choices=[SimpleNamespace(delta=SimpleNamespace(content='{"diffs"'))],
                usage=None,
            )
            raise litellm.InternalServerError(
                message="500", llm_provider="gemini", model="g"
            )

        return chunks()

    monkeypatch.setattr(gw.litellm, "acompletion", breaks_mid_answer)
    events = await _invoke(monkeypatch, _deployment(tpm=16_000))
    names = [e for e, _ in events]
    assert names.count("thinking") == 1  # partial text not repeated
    assert names[-1] == "service_unavailable"


def test_user_quota_event_is_user_scope():
    from fastapi import HTTPException

    text = gw._quota_sse_event(
        HTTPException(429, detail={"login_available": True, "retry_after": 20})
    )
    event, payload = parse_sse(text)
    assert event == "rate_limit"
    assert payload["scope"] == "user" and payload["login_available"] is True


# ---------------------------------------------------------------------------
# focus_path end to end
# ---------------------------------------------------------------------------


async def test_focus_path_prefixes_model_paths(monkeypatch):
    from fastapi.testclient import TestClient

    from src.json_ai_studio.main import app

    seen: list = []

    async def fake_invoke(session_id, message, principal, system_prompt, **kw):
        plan = kw["planner"](_deployment(tpm=None), "fake/m")
        seen.append(plan.messages[0]["content"])
        reply = {
            "diffs": [
                {
                    "path": "/theme",
                    "operation": "modify",
                    "old_value": "dark",
                    "new_value": "light",
                }
            ],
            "explanation": "Switched theme.",
        }
        yield "event: thinking\ndata: " + json.dumps(
            {"text": json.dumps(reply)}
        ) + "\n\n"

    monkeypatch.setattr(gw.GatewayService, "invoke", staticmethod(fake_invoke))
    monkeypatch.setenv("ANON_REQUESTS_PER_MINUTE", "10000")
    get_settings.cache_clear()
    doc = {"settings": {"theme": "dark"}, "zz_items": RECORDS["records"][:3]}
    with TestClient(app, headers={"X-API-Key": f"fp-{uuid.uuid4().hex}"}) as c:
        sid = c.post("/api/sessions", json={"name": "fp"}).json()["id"]
        c.post(
            "/api/json/upload",
            files={"json_body": (None, json.dumps(doc)), "session_id": (None, sid)},
        )
        resp = c.post(
            "/api/chat",
            data={"session_id": sid, "message": "light", "focus_path": "/settings"},
        )
    events = [parse_sse(b) for b in resp.text.split("\n\n") if b.strip()]
    assert "zz_items" not in seen[0]  # model saw only the subtree
    diffs = [p["entry"] for e, p in events if e == "diff"]
    assert [d["path"] for d in diffs] == ["/settings/theme"]
    done = next(p for e, p in events if e == "complete")
    assert done["working_json"]["settings"]["theme"] == "light"
    assert len(done["working_json"]["zz_items"]) == 3
