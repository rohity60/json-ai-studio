"""Diff accept/reject business logic.

Lifecycle: diffs proposed in a chat turn are already applied to
working_json (preview state). Accepting a diff promotes it into
baseline_json; rejecting a diff reverts it from working_json.
baseline_json is never modified by a reject, and working_json is
never re-applied on accept (that previously duplicated array
inserts/deletes).
"""

from __future__ import annotations

import copy
import logging
from typing import Any

from ..db.session_store import store
from ..diff_utils import DiffUtils
from .errors import NotFoundError
from .session_service import get_session, now_iso

logger = logging.getLogger("json_ai_studio.diff_service")


def _find_diff_in_history(session: dict[str, Any], diff_id: str) -> dict | None:
    turns = session.get("conversation_history", [])
    for turn in reversed(turns):
        if turn.get("role") == "assistant" and turn.get("diffs"):
            for diff in turn["diffs"]:
                if diff.get("id") == diff_id:
                    return diff
    return None


async def accept_all(session_id: str) -> dict[str, Any]:
    session = await get_session(session_id)

    session["baseline_json"] = copy.deepcopy(session["working_json"])
    session["applied_diffs"] = []
    session["updated_at"] = now_iso()
    await store.save_session(session)
    logger.info("accept_all session_id=%s", session_id)
    logger.debug("accept_all baseline_json=%s", session["baseline_json"])
    return {
        "working_json": session["working_json"],
        "baseline_json": session["baseline_json"],
        "diffs": [],
    }


async def reject_all(session_id: str) -> dict[str, Any]:
    session = await get_session(session_id)

    session["working_json"] = copy.deepcopy(session.get("baseline_json", {}))
    session["applied_diffs"] = []
    session["updated_at"] = now_iso()
    await store.save_session(session)
    logger.info("reject_all session_id=%s", session_id)
    logger.debug("reject_all working_json=%s", session["working_json"])
    return {
        "working_json": session["working_json"],
        "baseline_json": session.get("baseline_json", {}),
        "diffs": [],
    }


async def accept_one(session_id: str, diff_id: str) -> dict[str, Any]:
    """Accept a single diff by ID: promote it into baseline_json.

    working_json already contains the change (applied during the chat
    stream), so only the baseline needs the diff applied. Raises
    DiffApplyError if the diff no longer resolves against the baseline.
    """
    session = await get_session(session_id)

    target = _find_diff_in_history(session, diff_id)
    if target is None:
        logger.info("accept_one miss session_id=%s diff_id=%s", session_id, diff_id)
        raise NotFoundError(f"Diff with id {diff_id} not found in conversation history")

    logger.debug(
        "accept_one session_id=%s diff_id=%s diff=%s", session_id, diff_id, target
    )
    baseline_json = DiffUtils.apply(target, session.get("baseline_json", {}))

    session["baseline_json"] = baseline_json
    session["applied_diffs"] = session.get("applied_diffs", []) + [target.get("id", "")]
    session["updated_at"] = now_iso()
    await store.save_session(session)
    logger.info("accept_one applied session_id=%s diff_id=%s", session_id, diff_id)
    return {
        "success": True,
        "working_json": session.get("working_json", {}),
        "baseline_json": baseline_json,
        "applied_diffs": session["applied_diffs"],
    }


async def reject_one(session_id: str, diff_id: str) -> dict[str, Any]:
    """Reject a single diff by ID: revert it from working_json.

    baseline_json never contained the change, so it is left untouched.
    Raises DiffApplyError if the diff no longer resolves.
    """
    session = await get_session(session_id)

    target = _find_diff_in_history(session, diff_id)
    if target is None:
        logger.info("reject_one miss session_id=%s diff_id=%s", session_id, diff_id)
        raise NotFoundError(f"Diff with id {diff_id} not found in conversation history")

    logger.debug(
        "reject_one session_id=%s diff_id=%s diff=%s", session_id, diff_id, target
    )
    working_json = DiffUtils.revert(target, session.get("working_json", {}))

    session["working_json"] = working_json
    session["rejected_diffs"] = session.get("rejected_diffs", []) + [
        target.get("id", "")
    ]
    session["updated_at"] = now_iso()
    await store.save_session(session)
    logger.info("reject_one reverted session_id=%s diff_id=%s", session_id, diff_id)
    return {
        "success": True,
        "working_json": working_json,
        "baseline_json": session.get("baseline_json", {}),
        "applied_diffs": session.get("applied_diffs", []),
        "rejected_diffs": session["rejected_diffs"],
    }
