"""Turn progress messages (PRD B §8): built in code, never by the model."""

import json
from types import SimpleNamespace

from src.json_ai_studio.services import deployment_budget as budget
from src.json_ai_studio.services import progress
from src.json_ai_studio.services.chat_service import parse_sse


def _ev(text):
    return parse_sse(text)


def test_search_message_uses_real_count_and_short_term():
    msg = progress.describe_tool_call(
        "search", json.dumps({"query": "x" * 80, "scope": "both"}), {"total": 3}
    )
    assert msg.startswith("Searched field names and values for “")
    assert msg.endswith("— 3 matches")
    assert len(msg) < 120


def test_search_no_matches_and_path_prefix():
    msg = progress.describe_tool_call(
        "search", {"query": "timeout", "path_prefix": "/svc"}, {"total": 0}
    )
    assert msg == "Searched values in /svc for “timeout” — no matches"


def test_read_reports_partial_read_of_long_field():
    doc = {"data": {"description": "a" * 7485}}
    msg = progress.describe_tool_call(
        "read", {"path": "/data/description"}, {"value_truncated": "a" * 3800}, doc
    )
    assert msg == "Read /data/description (first 3,800 of 7,485 characters)"


def test_read_full_and_query_and_error():
    assert (
        progress.describe_tool_call("read", {"path": "/n"}, {"value": 1}, {"n": 1})
        == "Read /n (1 character)"
    )
    assert (
        progress.describe_tool_call(
            "query", {"path": "/items/*", "where": {"a": 1}}, {"total": 2}
        )
        == "Queried /items/* with conditions — 2 items matched"
    )
    assert progress.describe_tool_call(
        "read", {"path": "/x"}, {"error": "path '/x' does not exist"}
    ).startswith("Lookup (read) could not run: ")


def test_never_includes_document_values():
    doc = {"secret": "TOP-SECRET-VALUE " * 50}
    msg = progress.describe_tool_call(
        "read", {"path": "/secret"}, {"value_truncated": doc["secret"][:500]}, doc
    )
    assert "TOP-SECRET" not in msg


def test_plan_message_for_budgeted_tool_turn():
    budget.reset()
    dep = SimpleNamespace(name="g", min_call_interval_s=15, tpm_input_limit=16_000)
    event, data = _ev(progress.plan_event("skeleton", 5, dep, "m", 6000))
    assert event == "plan"
    assert data["steps"] == 5 and data["rounds_planned"] == 4
    assert 1 <= data["calls_per_min"] <= 4
    assert "steps per minute" in data["message"] or "step per minute" in data["message"]
    assert data["eta_s"] > 60


def test_plan_without_limits_has_no_rate_sentence():
    dep = SimpleNamespace(name="o", min_call_interval_s=0, tpm_input_limit=None)
    _, data = _ev(progress.plan_event("skeleton", 5, dep, "m", 6000))
    assert data["calls_per_min"] is None
    assert (
        data["message"]
        == "Large document — the AI will look things up in up to 5 steps."
    )


def test_waiting_and_retrying_messages():
    _, wait = _ev(progress.waiting_event(12.2, "pacing", 2))
    assert wait == {
        "retry_after": 13,
        "reason": "pacing",
        "message": progress.WAIT_MESSAGES["pacing"],
        "step": 2,
    }
    _, retry = _ev(progress.retrying_event(1, 3, 3.0, "provider_error"))
    assert retry["message"].endswith("retrying (1/3)")


def test_calling_messages():
    assert (
        _ev(progress.calling(2, 5, False))[1]["message"]
        == "Step 2/5 — asking the AI model"
    )
    final = _ev(progress.calling(5, 5, True))[1]
    assert (
        final["stage"] == "answering"
        and final["message"] == "Step 5/5 — writing the answer"
    )
    assert _ev(progress.applying(1))[1]["message"] == "Applying 1 change…"
