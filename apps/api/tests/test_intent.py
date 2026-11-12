"""Intent rules (ADR-0026, PRD C §1): deterministic, no LLM call."""

from __future__ import annotations

import pytest

from src.json_ai_studio.services import intent as rules
from src.json_ai_studio.services.intent import (
    BULK_EDIT,
    POINT_EDIT,
    QUESTION,
    REVIEW,
    classify_intent,
    doc_stats,
)

DOC = {
    "name": "Sample book",
    "description": "A short description.",
    "entries": [{"id": i, "content": f"Entry number {i}."} for i in range(40)],
    "data": {"extra": {"entries": [{"id": 1}, {"id": 2}]}},
}
STATS = doc_stats(DOC)


@pytest.mark.parametrize(
    "message",
    [
        # English
        "review all entries",
        "Review, repair and polish the ENTIRE document",
        "proofread everything",
        "check every entry for typos",
        "fix all the spelling mistakes",
        "look for errors",
        "find typos and inconsistencies",
        "review the entries",
        "can you review the whole file?",
        # Portuguese
        "revise todas as entradas",
        "procure erros no documento",
        "corrija os erros de todo o documento",
        "revisão completa do arquivo, por favor: revise tudo",
        # Spanish
        "revisa todas las entradas",
        "busca errores en el documento",
        "corrige todos los errores",
    ],
)
def test_whole_document_requests_are_review(message):
    assert classify_intent(message, STATS).kind == REVIEW


@pytest.mark.parametrize(
    "message",
    [
        "review entry 5",
        "fix /entries/12",
        "revise a entrada 7",
        "revisa la entrada 3",
        "fix the typo in description",  # one named field
        "proofread only the first entry",
        "review item #4",
    ],
)
def test_review_of_one_target_stays_point_edit(message):
    intent = classify_intent(message, STATS)
    assert intent.kind == POINT_EDIT
    assert intent.rule.startswith("point.")


@pytest.mark.parametrize(
    "message",
    [
        "set timeout to 30",
        "add a new entry called Dragon",
        "rename name to title",
        "",
        "asdf qwer",
        "muda o nome para Livro",
    ],
)
def test_unknown_or_plain_edits_default_to_point_edit(message):
    intent = classify_intent(message, STATS)
    assert (intent.kind, intent.rule) == (POINT_EDIT, "default")


@pytest.mark.parametrize(
    "message",
    [
        "set all enabled flags to true",
        "fix all timeouts to 60",
        "delete every entry where id is 3",
        "mude todos os valores para 10",
        "cambia todas las claves a minúsculas",
    ],
)
def test_one_change_on_many_elements_is_bulk_edit(message):
    assert classify_intent(message, STATS).kind == BULK_EDIT


@pytest.mark.parametrize(
    "message",
    [
        "what is this document about?",
        "how many entries are there",
        "explain the data section",
        "quantas entradas existem?",
        "¿qué contiene este archivo?",
    ],
)
def test_questions(message):
    assert classify_intent(message, STATS).kind == QUESTION


def test_question_with_an_edit_verb_is_not_a_question():
    assert classify_intent("can you fix entry 5?", STATS).kind == POINT_EDIT
    assert classify_intent("could you change the name?", STATS).kind == POINT_EDIT


def test_scope_path_is_the_named_collection_largest_first():
    intent = classify_intent("review all entries", STATS)
    assert intent.scope_path == "/entries"  # not /data/extra/entries


def test_scope_path_from_an_explicit_pointer():
    intent = classify_intent("review everything in /data/extra/entries", STATS)
    assert (intent.kind, intent.scope_path) == (REVIEW, "/data/extra/entries")


def test_no_named_collection_leaves_scope_to_the_planner():
    assert classify_intent("proofread everything", STATS).scope_path is None


def test_works_without_doc_stats():
    assert classify_intent("review the whole document").kind == REVIEW


def test_every_result_names_its_rule():
    assert classify_intent("review all entries", STATS).rule == "review.verb_scope"
    assert classify_intent("look for errors", STATS).rule == "review.open_search"
    assert classify_intent("review the entries", STATS).rule == (
        "review.named_collection"
    )


def test_might_be_review_prefilter():
    assert rules.might_be_review("look for errors")
    assert not rules.might_be_review("set timeout to 30")
