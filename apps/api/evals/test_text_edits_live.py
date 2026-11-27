"""Live LLM eval: rewriting a whole long string vs editing a phrase. Opt-in.

Prod 2026-11-25 (Retell voice agent, nemotron): "Yes, translate the entire
script to Slovak" → the model sent ONE replace_text whose "find" was the whole
12k-char /conversationFlow/global_prompt, retyped with small differences (or
copied from before an earlier turn's edit) → "not found", 3,914 output tokens
lost, nothing applied. Fix: prompt rule X4 (whole rewrite = one modify) and a
server fallback (loose find; a find that is the whole value retyped replaces
the whole value).

Cases:

- ``translate_whole``: translate the agent's script; the prompt must end up
  Slovak and complete, nothing else changed.
- ``translate_after_edit``: same, after an earlier turn appended a sentence
  to the prompt (the prod sequence; history carries the older text).
- ``fix_phrase``: control — change one phrase; the rest of the script must
  stay byte-identical (a whole rewrite here would be wrong).

    cd apps/api && LIVE_LLM=1 PYTHONPATH=. uv run pytest evals/test_text_edits_live.py -s
    # LIVE_DEPLOYMENT=nvidia_nim
"""

from __future__ import annotations

import os

import pytest

from test_array_index_live import chat, client, last_turn  # noqa: F401
from test_id_index_live import failures, model_diffs, raw_text, seed  # noqa: F401

pytestmark = pytest.mark.skipif(
    os.environ.get("LIVE_LLM") != "1", reason="live LLM eval; set LIVE_LLM=1"
)

PROMPT = """You are Natalie Freeman, a calm, warm, professional Compliance Support Representative from INCORP CENTRAL.
Your role is to call business owners whose annual report is due and help them file it on time.

## Opening
Greet the client by name, introduce yourself and the company, and ask if this is a good time to talk. If it is not, offer to call back later and ask for a convenient time.

## Purpose of the call
Explain that the state requires every company to file an annual report each year. Tell the client that their report is due at the end of this month and that missing the deadline can lead to a late fee or, after a longer delay, loss of good standing.

## Collecting information
Ask the client to confirm the company's registered address, the names of the current directors, and the best email address for the filing confirmation. Repeat each answer back to make sure it is correct. Never ask for bank details, card numbers or passwords.

## Objections
If the client says they already filed, thank them and ask when and how they filed so you can update the records. If the client is unsure, offer to email a short summary of what is needed. If the client is upset, stay calm, acknowledge their frustration and keep the conversation short.

## Closing
Summarise what was agreed, tell the client what happens next, and thank them for their time. Wish them a good day before ending the call.

## Rules
- Keep each reply short: two sentences at most.
- Speak naturally and pause <break time="1s"/> after asking a question.
- Never promise a result you cannot guarantee.
- If the client asks to stop calling, apologise and end the call politely.
"""

ADDED = " You speak Slovak throughout the call."


def agent(prompt: str = PROMPT, language: str = "sk-SK") -> dict:
    return {
        "agent_id": "agent_7f3c2a",
        "agent_name": "Natalie - Annual Report Reminder",
        "language": language,
        "voice_id": "11labs-Cimo",
        "voice_speed": 1.0,
        "max_call_duration_ms": 600000,
        "end_call_after_silence_ms": 30000,
        "conversationFlow": {
            "global_prompt": prompt,
            "start_speaker": "agent",
            "model_choice": {"type": "cascading", "model": "gpt-4.1"},
        },
    }


SLOVAK = set("áäčďéíĺľňóôŕšťúýž")
# English phrases from the script that a translation must not keep.
ENGLISH = [
    "annual report is due",
    "Greet the client",
    "Collecting information",
    "Never ask for bank details",
    "Summarise what was agreed",
    "Keep each reply short",
]


def _translated(old: str, new: str) -> tuple[bool, dict]:
    left = [p for p in ENGLISH if p in new]
    accents = sum(c in SLOVAK for c in new.lower())
    info = {
        "len": f"{len(old)}->{len(new)}",
        "english_left": left,
        "accents": accents,
        "kept_tag": '<break time="1s"/>' in new,
    }
    # Accents are reported, not gated: nemotron writes Slovak without them.
    ok = not left and len(new) >= 0.6 * len(old)
    return ok, info


def _others_unchanged(before: dict, after: dict) -> bool:
    """Everything but the prompt is unchanged (a localised agent_name is a
    fair reading of "translate", so it is not counted)."""
    skip = ("conversationFlow", "agent_name")
    b = {k: v for k, v in before.items() if k not in skip}
    a = {k: v for k, v in after.items() if k not in skip}
    bf = {k: v for k, v in before["conversationFlow"].items() if k != "global_prompt"}
    af = {k: v for k, v in after["conversationFlow"].items() if k != "global_prompt"}
    return a == b and af == bf


def _report(label: str, ok: bool, diffs: list[dict], **info) -> None:
    ops = sorted(
        {
            f"{d.get('operation')} {d.get('path')}"
            + (f" find={len(d.get('find') or '')}ch" if d.get("find") else "")
            for d in diffs
        }
    )
    extra = " ".join(f"{k}={v}" for k, v in info.items())
    print(f"\nRESULT {'ok  ' if ok else 'FAIL'} {label:22} {extra} model={ops[:8]}")


@pytest.mark.parametrize("after_edit", [False, True], ids=["whole", "after_edit"])
def test_translate(client, raw_text, after_edit):  # noqa: F811
    if after_edit:
        doc = agent(PROMPT.replace("INCORP CENTRAL.", "INCORP CENTRAL." + ADDED, 1))
        history = [
            {"role": "user", "content": "Speak Slovak throughout the call."},
            {
                "role": "assistant",
                "content": "Added an instruction to speak Slovak throughout "
                "the call in the global prompt.",
                "diffs": [
                    {
                        "id": "d1",
                        "path": "/conversationFlow/global_prompt",
                        "operation": "modify",
                        "old_value": PROMPT,
                        "new_value": doc["conversationFlow"]["global_prompt"],
                        "status": "accepted",
                    }
                ],
            },
        ]
    else:
        doc, history = agent(), []
    sid = seed(client, doc, history)
    done = chat(client, sid, "Translate the entire script to Slovak.")
    old = doc["conversationFlow"]["global_prompt"]
    # Prod: the model asked first and translated after "Yes". Asking once is
    # fine; the answer to "Yes" is what counts.
    asked = done["working_json"]["conversationFlow"]["global_prompt"] == old
    if asked:
        done = chat(client, sid, "Yes, translate the entire script to Slovak.")
    diffs = model_diffs(raw_text)
    after = done["working_json"]
    new = after["conversationFlow"]["global_prompt"]
    translated, info = _translated(old, new)
    failed = failures(last_turn(client, sid))
    others = _others_unchanged(doc, after)
    ok = translated and others and not failed
    note = (done.get("explanation") or "")[:120]
    _report(
        f"translate_{'after_edit' if after_edit else 'whole'}",
        ok,
        diffs,
        asked=asked,
        others_unchanged=others,
        failed=failed[:2],
        note=repr(note),
        **info,
    )
    assert ok


def test_fix_phrase(client, raw_text):  # noqa: F811
    doc = agent()
    sid = seed(client, doc)
    done = chat(
        client,
        sid,
        'In the script, change "two sentences at most" to "three sentences at most".',
    )
    diffs = model_diffs(raw_text)
    after = done["working_json"]
    want = PROMPT.replace("two sentences at most", "three sentences at most")
    got = after["conversationFlow"]["global_prompt"]
    failed = failures(last_turn(client, sid))
    ok = got == want and _others_unchanged(doc, after) and not failed
    _report("fix_phrase", ok, diffs, exact=got == want, failed=failed[:2])
    assert ok
