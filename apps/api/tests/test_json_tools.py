"""Large-document lookup (ADR-0024): key-union skeleton, search/read tools,
gateway tool loop, clarifying questions. Deterministic — LiteLLM is faked.

Prod motivation: gita.json (701 records) edits refused/guessed; an Unreal
UAssetAPI dump where Exports[0] (ClassExport) hid ScriptBytecode entirely.
"""

from __future__ import annotations

import json
import uuid
from types import SimpleNamespace

import pytest

from src.json_ai_studio.json_tools import JsonToolbox
from src.json_ai_studio.prompting import (
    build_array_stats,
    build_skeleton,
    build_system_prompt,
    is_skeleton_mode,
)

T = lambda n: f"UAssetAPI.ExportTypes.{n}, UAssetAPI"  # noqa: E731
K = lambda n: f"UAssetAPI.Kismet.Bytecode.Expressions.{n}, UAssetAPI"  # noqa: E731

UASSET = {
    "Imports": [
        {
            "$type": "UAssetAPI.Import, UAssetAPI",
            "ObjectName": n,
            "ClassName": "Function",
        }
        for n in ["MagazineStart", "MagazineStop"]
    ],
    "Exports": [
        {
            "$type": T("ClassExport"),
            "ObjectName": "BP_C",
            "ClassFlags": "CLASS_Compiled",
        },
        {
            "$type": T("FunctionExport"),
            "ObjectName": "ExecuteUbergraph",
            "ScriptBytecode": [
                {
                    "$type": K("EX_FinalFunction"),
                    "StackNode": -2,
                    "Parameters": [{"$type": K("EX_FloatConst"), "Value": 5.0}],
                },
                {
                    "$type": K("EX_Return"),
                    "ReturnExpression": {"$type": K("EX_Nothing")},
                },
            ],
        },
        {
            "$type": T("FunctionExport"),
            "ObjectName": "BPOnEmitted",
            "ScriptBytecode": [
                {
                    "$type": K("EX_Return"),
                    "ReturnExpression": {"$type": K("EX_Nothing")},
                }
            ],
        },
    ],
}

RECORDS = {
    "records": [
        {"sectionId": f"ch_{c}", "slokNumber": n, "text": f"verse {c}.{n}"}
        for c in (1, 2, 3)
        for n in range(1, 6)
    ]
}


# ---------------------------------------------------------------------------
# Key-union skeleton
# ---------------------------------------------------------------------------


class TestKeyUnionSkeleton:
    def test_uniform_array_unchanged(self):
        sk = build_skeleton(RECORDS)
        assert sk["records"] == [
            {"sectionId": "ch_1", "slokNumber": 1, "text": "verse 1.1"},
            "…+14 more items",
        ]

    def test_typed_array_shows_every_type(self):
        sk = build_skeleton(UASSET)
        exports = sk["Exports"]
        assert [e["$type"] for e in exports[:-1]] == [
            T("ClassExport"),
            T("FunctionExport"),
        ]
        assert exports[-1] == "…3 items by $type: ClassExport×1, FunctionExport×2"
        assert "ScriptBytecode" in exports[1]  # hidden by first-element-only skeletons

    def test_nested_arrays_merged_across_parents(self):
        bytecode = build_skeleton(UASSET)["Exports"][1]["ScriptBytecode"]
        assert (
            bytecode[-1]
            == "…3 items across 2 arrays by $type: EX_FinalFunction×1, EX_Return×2"
        )

    def test_partial_keys_listed(self):
        sk = build_skeleton({"items": [{"a": 1, "b": 2}, {"a": 3}, {"a": 4, "c": 5}]})
        assert sk["items"][0] == {
            "a": 1,
            "b": 2,
            "c": 5,
            "…keys in only some items": "b (1/3), c (1/3)",
        }

    def test_stats_use_short_type_names(self):
        stats = build_array_stats(UASSET)
        assert any('"FunctionExport"×2' in line for line in stats)

    def test_skeleton_header_and_mode(self, monkeypatch):
        from src.json_ai_studio.settings import get_settings

        assert not is_skeleton_mode(UASSET)
        monkeypatch.setenv("LLM_MAX_INLINE_CHARS", "50")
        get_settings.cache_clear()
        assert is_skeleton_mode(UASSET)
        assert "EVERY key that occurs anywhere" in build_system_prompt(UASSET)


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


class TestTools:
    tb = JsonToolbox(RECORDS)

    def call(self, name, **args):
        return json.loads(self.tb.call(name, args))

    def test_search_values_in_document_order_with_context(self):
        r = self.call("search", query="ch_3", limit=2, context_levels=1)
        assert r["total"] == 5 and r["truncated"]
        assert [m["path"] for m in r["matches"]] == [
            "/records/10/sectionId",
            "/records/11/sectionId",
        ]
        assert r["matches"][0]["context"]["path"] == "/records/10"
        assert "verse 3.1" in r["matches"][0]["context"]["value"]

    def test_search_keys_and_prefix(self):
        r = json.loads(
            JsonToolbox(UASSET).call(
                "search", {"query": "scriptbytecode", "scope": "keys"}
            )
        )
        assert [m["path"] for m in r["matches"]] == [
            "/Exports/1/ScriptBytecode",
            "/Exports/2/ScriptBytecode",
        ]
        r = json.loads(
            JsonToolbox(UASSET).call(
                "search", {"query": "Magazine", "path_prefix": "/Imports"}
            )
        )
        assert r["total"] == 2

    def test_read_exact_value_and_reference_hop(self):
        assert self.call("read", path="/records/12/slokNumber")["value"] == 3
        tb = JsonToolbox(UASSET)
        stack_node = json.loads(
            tb.call("read", {"path": "/Exports/1/ScriptBytecode/0/StackNode"})
        )["value"]
        target = json.loads(tb.call("read", {"path": f"/Imports/{-stack_node - 1}"}))[
            "value"
        ]
        assert target["ObjectName"] == "MagazineStop"

    def test_read_large_value_is_truncated_with_hint(self):
        r = json.loads(
            JsonToolbox(RECORDS, result_max_chars=300).call("read", {"path": ""})
        )
        assert "value_truncated" in r and "hint" in r

    @pytest.mark.parametrize(
        "name, args, error",
        [
            ("read", {"path": "/records/99"}, "no such index"),
            ("read", {"path": "/nope"}, "no such key"),
            ("search", {}, "query is required"),
            ("search", {"query": "x", "scope": "all"}, "scope must be"),
            ("drop_table", {}, "unknown tool"),
        ],
    )
    def test_errors_are_returned_as_data(self, name, args, error):
        assert error in self.call(name, **args)["error"]

    def test_bad_argument_json(self):
        assert "error" in json.loads(self.tb.call("search", "{not json"))

    def test_schemas_offer_search_query_read(self):
        assert [s["function"]["name"] for s in JsonToolbox.schemas()] == [
            "search",
            "query",
            "read",
        ]

    def test_query_matches_two_fields_at_once(self):
        """Live 2026-10-23: search('slokNumber: 23, sectionId: …') found
        nothing — field conditions need query."""
        r = self.call(
            "query", path="/records/*", where={"slokNumber": 2, "sectionId": "ch_3"}
        )
        assert r["total"] == 1 and r["matches"][0]["path"] == "/records/11"

    def test_query_reverse_reference_lookup(self):
        r = json.loads(
            JsonToolbox(UASSET).call(
                "query",
                {"path": "/Exports/*/ScriptBytecode/*", "where": {"StackNode": -2}},
            )
        )
        assert [m["path"] for m in r["matches"]] == ["/Exports/1/ScriptBytecode/0"]

    def test_query_without_where_lists_and_counts(self):
        r = self.call("query", path="/records/*/sectionId", limit=3)
        assert r["total"] == 15 and len(r["matches"]) == 3 and r["truncated"]

    def test_query_rejects_relative_path(self):
        assert "JSON Pointer" in self.call("query", path="records/*")["error"]


# ---------------------------------------------------------------------------
# Gateway tool loop (LiteLLM faked)
# ---------------------------------------------------------------------------


def _response(content="", calls=(), prompt=10, completion=5):
    tool_calls = [
        SimpleNamespace(
            id=f"c{i}", function=SimpleNamespace(name=n, arguments=json.dumps(a))
        )
        for i, (n, a) in enumerate(calls)
    ]
    message = SimpleNamespace(content=content, tool_calls=tool_calls or None)
    return SimpleNamespace(
        choices=[SimpleNamespace(message=message)],
        usage=SimpleNamespace(prompt_tokens=prompt, completion_tokens=completion),
    )


@pytest.fixture(params=["stream", "no-stream"])
def gateway(monkeypatch, request):
    from src.json_ai_studio import gateway as gw
    from src.json_ai_studio.services import credit_service

    deployment = SimpleNamespace(
        name="fake",
        model_prefix="fake/",
        base_model="m",
        base_url="http://fake",
        api_key="",
        supports_tools=True,
        tool_streaming=request.param == "stream",
        litellm_model=lambda m: m,
        completion_params=lambda model, reasoning=None: {},
        pricing=lambda m: (0.0, 0.0),
    )
    monkeypatch.setattr(
        gw.DeploymentRegistry, "pick_default", classmethod(lambda cls: deployment)
    )
    deducted = []

    async def fake_deduct(principal, credits, tokens):
        deducted.append(tokens)

    monkeypatch.setattr(credit_service, "deduct", fake_deduct)
    script: list = []
    calls: list = []

    built: list = []

    async def fake_acompletion(**kw):
        calls.append(kw)
        item = script.pop(0)
        if not kw.get("stream") or not hasattr(item, "choices"):
            return item  # non-streaming response, or a prepared stream

        async def chunks():  # stream: text as deltas; builder returns item
            text = item.choices[0].message.content or ""
            for piece in (text[: len(text) // 2], text[len(text) // 2 :]):
                if piece:
                    yield SimpleNamespace(
                        choices=[SimpleNamespace(delta=SimpleNamespace(content=piece))]
                    )

        built.append(item)
        return chunks()

    monkeypatch.setattr(gw.litellm, "acompletion", fake_acompletion)
    monkeypatch.setattr(
        gw.litellm, "stream_chunk_builder", lambda chunks, messages=None: built.pop(0)
    )
    return SimpleNamespace(
        gw=gw,
        deployment=deployment,
        script=script,
        calls=calls,
        deducted=deducted,
        mode=request.param,
    )


async def _run(gw, toolbox, message="find ch_3 slok 2"):
    from src.json_ai_studio.auth import Principal

    principal = Principal(kind="anonymous", quota_key="pool", rate_key="rk")
    events = []
    async for text in gw.GatewayService.invoke(
        "s", message, principal, "SYSTEM", toolbox=toolbox
    ):
        from src.json_ai_studio.services.chat_service import parse_sse

        events.append(parse_sse(text))
    return events


async def test_tool_round_then_final_answer(gateway):
    final = {"diffs": [], "explanation": "found /records/11"}
    gateway.script.extend(
        [
            _response(calls=[("search", {"query": "ch_3"})]),
            _response(content=json.dumps(final), prompt=40, completion=20),
        ]
    )
    events = await _run(gateway.gw, JsonToolbox(RECORDS))

    tool_events = [p for e, p in events if e == "tool"]
    assert [(t["round"], t["name"]) for t in tool_events] == [(1, "search")]
    thinking = [p["text"] for e, p in events if e == "thinking"]
    assert json.loads(thinking[0]) == final
    # Round 2 saw the tool result; tool instructions appended to system prompt.
    second = gateway.calls[1]["messages"]
    assert (
        second[0]["content"].startswith("SYSTEM") and "TOOLS —" in second[0]["content"]
    )
    assert (
        second[-1]["role"] == "tool"
        and '"/records/10/sectionId"' in second[-1]["content"]
    )
    assert all(c["tools"] == JsonToolbox.schemas() for c in gateway.calls)
    assert gateway.deducted == [10 + 5 + 40 + 20]  # summed, charged once
    assert all(
        c.get("stream", False) == (gateway.mode == "stream") for c in gateway.calls
    )
    drafts = "".join(p["text"] for e, p in events if e == "draft")
    assert drafts == (json.dumps(final) if gateway.mode == "stream" else "")


async def test_round_cap_forces_final_answer(gateway, monkeypatch):
    monkeypatch.setenv("CHAT_TOOL_MAX_ROUNDS", "2")
    from src.json_ai_studio.settings import get_settings

    get_settings.cache_clear()
    loop = _response(calls=[("read", {"path": "/records/0"})])
    gateway.script.extend(
        [loop, loop, _response(content='{"diffs": [], "explanation": "ok"}')]
    )
    events = await _run(gateway.gw, JsonToolbox(RECORDS))

    assert len(gateway.calls) == 3
    assert "Tool budget used up" in gateway.calls[2]["messages"][-1]["content"]
    assert [p["text"] for e, p in events if e == "thinking"] == [
        '{"diffs": [], "explanation": "ok"}'
    ]


def test_streamed_tool_call_fragments_reassemble():
    """Real LiteLLM chunk builder: a tool call split across deltas."""
    import litellm
    from litellm.types.utils import (
        ChatCompletionDeltaToolCall,
        Delta,
        Function,
        ModelResponseStream,
        StreamingChoices,
    )

    def chunk(**delta):
        return ModelResponseStream(
            choices=[StreamingChoices(index=0, delta=Delta(**delta))]
        )

    parts = [
        chunk(
            tool_calls=[
                ChatCompletionDeltaToolCall(
                    index=0,
                    id="c1",
                    type="function",
                    function=Function(name="search", arguments='{"que'),
                )
            ]
        ),
        chunk(
            tool_calls=[
                ChatCompletionDeltaToolCall(
                    index=0, function=Function(arguments='ry": "MagazineStop"}')
                )
            ]
        ),
    ]
    msg = litellm.stream_chunk_builder(parts).choices[0].message
    (call,) = msg.tool_calls
    assert (call.id, call.function.name) == ("c1", "search")
    assert json.loads(call.function.arguments) == {"query": "MagazineStop"}


async def test_no_tools_without_deployment_support(gateway):
    gateway.deployment.supports_tools = False

    async def stream():
        yield SimpleNamespace(
            choices=[SimpleNamespace(delta=SimpleNamespace(content='{"diffs": []}'))],
            usage=None,
        )

    gateway.script.append(stream())
    events = await _run(gateway.gw, JsonToolbox(RECORDS))
    assert "tools" not in gateway.calls[0] and gateway.calls[0]["stream"] is True
    assert not [e for e, _ in events if e == "tool"]


# ---------------------------------------------------------------------------
# chat_service: toolbox only for skeleton docs; questions flow end-to-end
# ---------------------------------------------------------------------------


@pytest.fixture
def client(monkeypatch):
    from fastapi.testclient import TestClient

    from src.json_ai_studio.main import app

    monkeypatch.setenv("ANON_REQUESTS_PER_MINUTE", "10000")
    with TestClient(app, headers={"X-API-Key": f"jt-{uuid.uuid4().hex}"}) as c:
        yield c


@pytest.fixture
def fake_invoke(monkeypatch):
    from src.json_ai_studio.gateway import GatewayService

    seen: list = []
    replies: list = []

    async def invoke(session_id, message, principal, system_prompt, **kw):
        if kw.get("planner"):  # ADR-0025: prompt comes from the turn planner
            plan = kw["planner"](SimpleNamespace(name="fake"), "fake/m")
            kw = {**kw, "toolbox": plan.toolbox, "history": plan.messages[1:-1]}
        seen.append(kw)
        yield "event: thinking\ndata: " + json.dumps(
            {"text": json.dumps(replies.pop(0))}
        ) + "\n\n"

    monkeypatch.setattr(GatewayService, "invoke", staticmethod(invoke))
    return seen, replies


def _session(client, doc):
    sid = client.post("/api/sessions", json={"name": "jt"}).json()["id"]
    client.post(
        "/api/json/upload",
        files={"json_body": (None, json.dumps(doc)), "session_id": (None, sid)},
    )
    return sid


def _chat(client, sid, msg):
    from src.json_ai_studio.services.chat_service import parse_sse

    r = client.post("/api/chat", data={"session_id": sid, "message": msg})
    return [parse_sse(b) for b in r.text.split("\n\n") if b.strip()]


def test_toolbox_only_in_skeleton_mode(client, fake_invoke, monkeypatch):
    seen, replies = fake_invoke
    replies.extend(
        [{"diffs": [], "explanation": "a"}, {"diffs": [], "explanation": "b"}]
    )
    sid = _session(client, RECORDS)
    _chat(client, sid, "hi")
    assert seen[0]["toolbox"] is None

    monkeypatch.setenv("LLM_MAX_INLINE_CHARS", "100")
    from src.json_ai_studio.settings import get_settings

    get_settings.cache_clear()
    _chat(client, sid, "hi again")
    assert isinstance(seen[1]["toolbox"], JsonToolbox)


def test_question_reaches_client_history_and_replay(client, fake_invoke):
    seen, replies = fake_invoke
    q = {
        "text": "Apply 'abc' to which records?",
        "options": ["Only chapter 1", "All 15 records", "x", "y", "dropped 5th"],
    }
    replies.extend(
        [
            {"diffs": [], "question": q, "explanation": "Ambiguous: two readings."},
            {"diffs": [], "explanation": "ok"},
        ]
    )
    sid = _session(client, RECORDS)
    events = _chat(client, sid, "apply the same change to all records")

    done = next(p for e, p in events if e == "complete")
    assert done["question"]["text"] == q["text"]
    assert done["question"]["options"] == q["options"][:4]  # capped at 4
    turn = client.get(f"/api/sessions/{sid}").json()["conversation_history"][1]
    assert turn["question"]["options"][0] == "Only chapter 1"

    _chat(client, sid, "Only chapter 1")
    replay = json.loads(seen[1]["history"][1]["content"])
    assert replay["question"]["text"] == q["text"]


def test_prompt_rules_for_questions_and_analysis():
    prompt = build_system_prompt(RECORDS)
    assert "12. QUESTIONS — ask only when" in prompt
    assert "Never ask instead of looking something up" in prompt
    assert "13. ANALYSIS" in prompt
    assert '"question": {"text":' in prompt


# ---------------------------------------------------------------------------
# Per-round transient retry (Google free tier: 16k input tokens/min → 429
# "Please retry in 3.7s", plus frequent 500s)
# ---------------------------------------------------------------------------


def _rate_limited(hint_s: float):
    import litellm

    return litellm.RateLimitError(
        message=f"Quota exceeded … Please retry in {hint_s}s.",
        llm_provider="gemini",
        model="gemma",
    )


@pytest.fixture
def no_sleep(monkeypatch):
    from src.json_ai_studio import gateway as gw

    waits: list = []

    async def fake_sleep(seconds):
        waits.append(seconds)

    monkeypatch.setattr(gw.asyncio, "sleep", fake_sleep)
    return waits


async def test_rate_limited_round_not_retried_by_default(
    gateway, no_sleep, monkeypatch
):
    async def limited(**kw):
        raise _rate_limited(3.7)

    monkeypatch.setattr(gateway.gw.litellm, "acompletion", limited)
    events = await _run(gateway.gw, JsonToolbox(RECORDS))
    assert no_sleep == []  # 0 retries (ADR-0025)
    event, payload = events[-1]
    assert event == "rate_limit" and payload["scope"] == "model"


async def test_rate_limited_round_retried_when_enabled(gateway, no_sleep, monkeypatch):
    from src.json_ai_studio.settings import get_settings

    monkeypatch.setenv("CHAT_TOOL_RETRY_ATTEMPTS", "1")
    get_settings.cache_clear()
    final = '{"diffs": [], "explanation": "ok"}'
    gateway.script.extend(
        [_response(calls=[("search", {"query": "ch_3"})]), _response(content=final)]
    )
    real = gateway.gw.litellm.acompletion
    failures = [_rate_limited(3.7)]

    async def flaky(**kw):
        if failures and len(gateway.calls) == 1:  # fail round 2 once
            raise failures.pop()
        return await real(**kw)

    monkeypatch.setattr(gateway.gw.litellm, "acompletion", flaky)
    try:
        events = await _run(gateway.gw, JsonToolbox(RECORDS))
    finally:
        monkeypatch.delenv("CHAT_TOOL_RETRY_ATTEMPTS")
        get_settings.cache_clear()  # don't leak attempts=1 into later tests
    assert no_sleep == [pytest.approx(4.2)]  # provider hint + 0.5s
    assert [p["text"] for e, p in events if e == "thinking"] == [final]


async def test_long_retry_hint_gives_up(gateway, no_sleep, monkeypatch):
    async def always_limited(**kw):
        raise _rate_limited(45)

    monkeypatch.setattr(gateway.gw.litellm, "acompletion", always_limited)
    events = await _run(gateway.gw, JsonToolbox(RECORDS))
    assert no_sleep == []
    # Provider 429 is model capacity with its real delay, not "busy" (ADR-0025).
    event, payload = events[-1]
    assert event == "rate_limit"
    assert payload["scope"] == "model"
    assert payload["retry_after"] == 45
    assert payload["login_available"] is False


async def test_server_error_not_retried(gateway, no_sleep, monkeypatch):
    import litellm

    async def broken(**kw):
        raise litellm.InternalServerError(
            message="500 Internal", llm_provider="gemini", model="gemma"
        )

    monkeypatch.setattr(gateway.gw.litellm, "acompletion", broken)
    events = await _run(gateway.gw, JsonToolbox(RECORDS))
    # 5xx never retried: each retry would add to the provider's per-minute
    # count (ADR-0025); pacing keeps load down instead.
    assert no_sleep == []
    assert len(gateway.calls) == 0  # broken() raised before recording
    assert [e for e, _ in events][-1] == "service_unavailable"
