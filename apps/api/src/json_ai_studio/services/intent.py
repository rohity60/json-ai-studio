"""Intent classification for chat messages (ADR-0026, PRD C §1).

Deterministic keyword rules — no LLM call, so it costs nothing on a
per-minute token budget and always answers. English, Portuguese and
Spanish first. The classifier only decides *routing*:

  review     — review / repair the WHOLE document or a whole collection.
               Needs a scope signal ("all entries", "everything", an open
               "look for errors"); "review entry 5" is a point edit.
  bulk_edit  — one stated change applied to many elements ("set all … to").
  question   — asks about the document, changes nothing.
  point_edit — everything else, and anything unknown (today's behaviour).

Every result carries the id of the rule that matched (logged at INFO).
"""

from __future__ import annotations

import logging
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("json_ai_studio.intent")

POINT_EDIT = "point_edit"
BULK_EDIT = "bulk_edit"
REVIEW = "review"
QUESTION = "question"

_MAX_DEPTH = 4  # how deep doc_stats looks for collections and key names


@dataclass(frozen=True)
class Intent:
    kind: str
    scope_path: str | None = None  # collection the user named, if any
    rule: str = "default"


@dataclass(frozen=True)
class Collection:
    path: str  # JSON Pointer
    key: str  # last path segment, lowercased
    count: int
    chars: int  # approximate serialised size


@dataclass(frozen=True)
class DocStats:
    chars: int = 0
    collections: tuple[Collection, ...] = ()
    leaf_keys: frozenset[str] = field(default_factory=frozenset)


def _esc(part: str) -> str:
    return part.replace("~", "~0").replace("/", "~1")


def doc_stats(doc: Any) -> DocStats:
    """Sizes of the document's containers and its field names, one pass."""
    collections: list[Collection] = []
    leaf_keys: set[str] = set()

    def visit(node: Any, path: str, key: str, depth: int) -> int:
        if isinstance(node, dict):
            size = 2
            for k, v in node.items():
                size += (
                    len(str(k))
                    + 4
                    + visit(v, f"{path}/{_esc(str(k))}", str(k), depth + 1)
                )
        elif isinstance(node, list):
            size = 2
            for i, v in enumerate(node):
                size += 1 + visit(v, f"{path}/{i}", key, depth + 1)
        else:
            if depth <= _MAX_DEPTH and key and not key.isdigit():
                leaf_keys.add(_norm(key))
            return len(node) + 2 if isinstance(node, str) else len(str(node))
        if path and depth <= _MAX_DEPTH and len(node) >= 2:
            collections.append(Collection(path, _norm(key), len(node), size))
        return size

    total = visit(doc, "", "", 0)
    container_keys = {c.key for c in collections}
    return DocStats(
        chars=total,
        collections=tuple(collections),
        leaf_keys=frozenset(leaf_keys - container_keys),
    )


def _norm(text: str) -> str:
    """Lowercase, accents stripped, whitespace collapsed."""
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    return " ".join(text.lower().split())


def _rx(pattern: str) -> re.Pattern[str]:
    return re.compile(pattern, re.IGNORECASE)


# Verbs that by themselves mean "read it all and judge".
_STRONG_REVIEW = _rx(
    r"\b(review|revise|proof-?read|audit|look over|look through|go through|"
    r"go over|revis(ar|e|a|em|ao|ion)|audit(ar|e|a|oria))\b"
)
# Verbs that mean review only with an errors-object or a whole scope.
_WEAK_REVIEW = _rx(
    r"\b(check|inspect|repair|fix|correct|clean ?up|polish|improve|validate|"
    r"verify|corrig(ir|e|a|am)|corrij(a|am)|correg(ir|imos)|consert(ar|e|a)|"
    r"repar(ar|e|a)|verifi(car|que|ca)|chec(ar|a)|cheque|comprob(ar|a)|"
    r"comprueba|melhor(ar|e|a)|mejor(ar|a|e)|arregl(ar|a|e)|limp(ar|e|a)|"
    r"analis(ar|e|a)|analiz(ar|a|e))\b"
)
_ERRORS = (
    r"(errors?|mistakes?|typos?|problems?|issues?|inconsistenc(y|ies)|"
    r"misspellings?|erros?|errores?|problemas?|falhas?|fallos?|faltas?|"
    r"inconsistencias?)"
)
_ERRORS_OBJECT = _rx(rf"\b{_ERRORS}\b")
# "look for errors": inherently about the whole document.
_OPEN_SEARCH = _rx(
    r"\b(find|look for|search for|spot|detect|hunt for|procur(e|ar|a)|"
    r"encontr(e|ar|a)|ach(e|ar)|busc(a|ar|que)|localiz(e|ar|a))\b"
    rf".{{0,40}}\b{_ERRORS}\b"
)
_SCOPE = _rx(
    r"\b(entire|whole|everything|all|every|each|full|throughout|todo|toda|"
    r"todos|todas|tudo|inteir[oa]s?|enter[oa]s?|cada|complet[oa]s?)\b"
    r"|\b(the|this|o|el|este|esta|esse|essa) (document|file|json|lorebook|"
    r"documento|arquivo|ficheiro|archivo)\b"
)
# One named element or a subset: never a whole-document review.
_SPECIFIC = _rx(
    r"/[\w~.-]+(/[\w~.-]+)*/\d+\b"
    r"|\b(entry|entries|item|items|record|records|element|row|line|index|"
    r"number|entrada|entradas|registro|registros|elemento|linha|fila|indice|"
    r"numero)\s*#?\d+"
    r"|#\d+"
    r"|\b(only|just|apenas|somente|solo|solamente|unicamente)\b"
    r"|\b(first|last|second|third|primeir[oa]s?|ultim[oa]s?|segund[oa]s?|"
    r"primer[oa]?s?)\b"
)
_BULK_VERB = _rx(
    r"\b(set|change|update|replace|rename|remove|delete|add|increase|decrease|"
    r"convert|make|translate|defin(a|ir|e)|mud(e|ar|a)|alter(e|ar|a)|"
    r"troqu?(e|ar|a)|substitu(a|ir|i)|renome(ie|ar)|remov(a|er|e)|"
    r"apag(ue|ar|a)|exclu(a|ir|i)|adicion(e|ar|a)|aument(e|ar|a)|"
    r"diminu(a|ir|i)|convert(a|er|ir|e)|traduz(a|ir)?|cambi(a|ar|e)|"
    r"actualiz(a|ar|e)|reemplaz(a|ar)|elimin(a|ar|e)|borr(a|ar|e)|"
    r"agreg(a|ar)|anad(e|ir)|traduc(e|ir))\b"
)
# "… to 60", "= true": a stated new value → an edit, not a review.
_ASSIGNMENT = _rx(r"(\bto\b|\bpara\b|=|->|→)\s*(\"|'|“|\d|(true|false|null)\b)")
_QUESTION_START = _rx(
    r"^(what|which|why|how|where|who|when|is|are|does|do|did|can|could|would|"
    r"should|explain|describe|tell me|show|list|count|summari[sz]e|o que|qual|"
    r"quais|por ?que|como|quant[oa]s?|onde|quem|explique|descreva|mostre|"
    r"liste|conte|resum(a|e|ir)|que|cual|cuales|cuant[oa]s?|donde|quien|"
    r"explica|muestra|lista|cuenta)\b"
)
_POINTER = re.compile(r"(?<![\w/])(/[\w~.-]+(?:/[\w~.-]+)*)")


def _words(text: str) -> set[str]:
    return set(re.findall(r"[\w-]+", text))


def _stem(word: str) -> str:
    return word[:-1] if len(word) > 3 and word.endswith("s") else word


def _named_scope(text: str, stats: DocStats) -> str | None:
    """Collection the message names: an explicit pointer, else a key."""
    by_path = {c.path.lower(): c.path for c in stats.collections}
    for match in _POINTER.finditer(text):
        path = by_path.get(match.group(1))
        if path is not None:
            return path
    words = {_stem(w) for w in _words(text)}
    named = [c for c in stats.collections if c.key and _stem(c.key) in words]
    if not named:
        return None
    return max(named, key=lambda c: c.chars).path


def _mentions_field(text: str, stats: DocStats) -> bool:
    """True when the message names a plain (non-collection) field."""
    return bool(_words(text) & stats.leaf_keys)


def _classify(text: str, stats: DocStats) -> Intent:
    strong = bool(_STRONG_REVIEW.search(text))
    weak = bool(_WEAK_REVIEW.search(text))
    scope = bool(_SCOPE.search(text))
    errors = bool(_ERRORS_OBJECT.search(text))
    open_search = bool(_OPEN_SEARCH.search(text))
    bulk_verb = bool(_BULK_VERB.search(text))
    assignment = bool(_ASSIGNMENT.search(text))
    named = _named_scope(text, stats)

    if strong or weak or open_search:
        if _SPECIFIC.search(text):
            return Intent(POINT_EDIT, rule="point.specific_target")
        if (strong or weak) and scope and not assignment:
            if strong or errors or not bulk_verb:
                return Intent(REVIEW, named, "review.verb_scope")
        if strong and named and not assignment and not bulk_verb:
            # "review the entries": the collection is the scope.
            return Intent(REVIEW, named, "review.named_collection")
        if (open_search or errors) and not assignment:
            if _mentions_field(text, stats):
                return Intent(POINT_EDIT, rule="point.named_field")
            return Intent(REVIEW, named, "review.open_search")

    if (bulk_verb or weak) and scope:
        return Intent(BULK_EDIT, named, "bulk.verb_scope")
    if (_QUESTION_START.search(text) or text.endswith("?")) and not (
        bulk_verb or weak or strong
    ):
        return Intent(QUESTION, rule="question")
    return Intent(POINT_EDIT)


def might_be_review(message: str) -> bool:
    """Cheap pre-check on the text alone, before doc_stats() is paid for."""
    text = _norm(message or "")
    return bool(
        _STRONG_REVIEW.search(text)
        or _WEAK_REVIEW.search(text)
        or _OPEN_SEARCH.search(text)
    )


def classify_intent(message: str, stats: DocStats | None = None) -> Intent:
    """Route a chat message. Unknown → point_edit (C-03)."""
    intent = _classify(_norm(message or ""), stats or DocStats())
    logger.info(
        "intent kind=%s rule=%s scope_path=%s",
        intent.kind,
        intent.rule,
        intent.scope_path,
    )
    return intent
