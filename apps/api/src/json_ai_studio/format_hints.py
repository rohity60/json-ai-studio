"""Format hints: known-format notes injected into the chat prompt.

The model edits documents of formats it may not know (e.g. Zoom Rooms
Controls profiles) and used to "fix" them into invalid values. Templates on
the web side declare a ``formatSignature`` (JSON Pointers with ``*``) plus
hand-written field docs; ``apps/web/scripts/export-format-notes.mjs`` exports
them to ``config/format_notes.json``. When every signature pointer resolves in
the working JSON, that format's notes go into the system prompt as
FORMAT NOTES.
"""

from __future__ import annotations

import json
import logging
import os
from functools import lru_cache
from typing import Any

from .bulk_edits import _walk
from .diff_utils import _split_path

logger = logging.getLogger("json_ai_studio.format_hints")

_NOTES_PATH = os.path.join(os.path.dirname(__file__), "config", "format_notes.json")
_MAX_FORMATS = 2  # cap prompt growth if several signatures match


@lru_cache(maxsize=1)
def load_formats() -> tuple[dict[str, Any], ...]:
    try:
        with open(_NOTES_PATH, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        logger.warning("format notes unavailable at %s", _NOTES_PATH)
        return ()
    return tuple(
        f
        for f in data.get("formats", [])
        if isinstance(f.get("signature"), list) and f["signature"]
    )


def _resolves(doc: Any, pointer: str) -> bool:
    try:
        parts = _split_path(pointer)
    except ValueError:
        return False
    return any(exists for _, exists, _, _ in _walk(doc, parts, [], None))


def match_formats(doc: Any) -> list[dict[str, Any]]:
    """Formats whose whole signature resolves in ``doc``."""
    if not isinstance(doc, (dict, list)):
        return []
    hits = [f for f in load_formats() if all(_resolves(doc, p) for p in f["signature"])]
    return hits[:_MAX_FORMATS]


def format_notes_block(doc: Any) -> str:
    """Prompt section for matched formats; "" when none match."""
    matched = match_formats(doc)
    if not matched:
        return ""
    logger.info("format hints matched=%s", [f["id"] for f in matched])
    sections = []
    for f in matched:
        lines = "\n".join(f"- {n}" for n in f.get("notes", []))
        sections.append(f"FORMAT NOTES — {f['title']}:\n{lines}")
    return (
        "The CURRENT WORKING JSON matches a known format. These notes are "
        "authoritative for it (rule 11):\n" + "\n\n".join(sections) + "\n\n"
    )
