"""Diff accept/reject business logic.

Lifecycle: diffs proposed in a chat turn are already applied to
working_json (preview state). Accepting a diff promotes it into
baseline_json; rejecting a diff reverts it from working_json.
baseline_json is never modified by a reject, and working_json is
never re-applied on accept (that previously duplicated array
inserts/deletes).

Every outcome is recorded as a ``status`` on the diff inside its chat
turn (pending -> accepted | rejected) so the next chat turn can replay
it to the LLM. The flat ``applied_diffs`` / ``rejected_diffs`` lists in
responses are derived from those statuses.
"""

from __future__ import annotations

import copy
import logging
from typing import Any

from ..db.session_store import store
from ..diff_utils import DiffUtils
from . import chat_history_service as history
from .errors import ConflictError, NotFoundError
from .session_service import get_session, now_iso

logger = logging.getLogger("json_ai_studio.diff_service")


def _require_pending(session: dict[str, Any], diff_id: str) -> dict[str, Any]:
    target = history.find_diff(session, diff_id)
    if target is None:
        raise NotFoundError(f"Diff with id {diff_id} not found in conversation history")
    status = target.get("status", "pending")
    if status != "pending":
        raise ConflictError(f"Diff {diff_id} is already {status}")
    return target


def _status_lists(session: dict[str, Any]) -> dict[str, Any]:
    return {
        "applied_diffs": history.diff_ids_with_status(session, "accepted"),
        "rejected_diffs": history.diff_ids_with_status(session, "rejected"),
        "conversation_history": session.get("conversation_history", []),
    }


async def accept_all(session_id: str) -> dict[str, Any]:
    session = await get_session(session_id)

    session["baseline_json"] = copy.deepcopy(session["working_json"])
    changed = history.mark_all_pending(session, "accepted")
    session["updated_at"] = now_iso()
    await store.save_session(session)
    logger.info("accept_all session_id=%s accepted=%d", session_id, changed)
    logger.debug("accept_all baseline_json=%s", session["baseline_json"])
    return {
        "working_json": session["working_json"],
        "baseline_json": session["baseline_json"],
        "diffs": [],
        **_status_lists(session),
    }


async def reject_all(session_id: str) -> dict[str, Any]:
    session = await get_session(session_id)

    session["working_json"] = copy.deepcopy(session.get("baseline_json", {}))
    changed = history.mark_all_pending(session, "rejected")
    session["updated_at"] = now_iso()
    await store.save_session(session)
    logger.info("reject_all session_id=%s rejected=%d", session_id, changed)
    logger.debug("reject_all working_json=%s", session["working_json"])
    return {
        "working_json": session["working_json"],
        "baseline_json": session.get("baseline_json", {}),
        "diffs": [],
        **_status_lists(session),
    }


async def accept_one(session_id: str, diff_id: str) -> dict[str, Any]:
    """Accept a single pending diff by ID: promote it into baseline_json.

    working_json already contains the change (applied during the chat
    stream), so only the baseline needs the diff applied. Raises
    NotFoundError (unknown id), ConflictError (not pending), or
    DiffApplyError if the diff no longer resolves against the baseline.
    """
    session = await get_session(session_id)

    try:
        target = _require_pending(session, diff_id)
    except (NotFoundError, ConflictError) as exc:
        logger.info("accept_one refused session_id=%s %s", session_id, exc)
        raise

    logger.debug(
        "accept_one session_id=%s diff_id=%s diff=%s", session_id, diff_id, target
    )
    baseline_json = DiffUtils.apply(target, session.get("baseline_json", {}))

    session["baseline_json"] = baseline_json
    target["status"] = "accepted"
    session["updated_at"] = now_iso()
    await store.save_session(session)
    logger.info("accept_one applied session_id=%s diff_id=%s", session_id, diff_id)
    return {
        "success": True,
        "working_json": session.get("working_json", {}),
        "baseline_json": baseline_json,
        **_status_lists(session),
    }


async def reject_one(session_id: str, diff_id: str) -> dict[str, Any]:
    """Reject a single pending diff by ID: revert it from working_json.

    baseline_json never contained the change, so it is left untouched.
    Raises NotFoundError, ConflictError, or DiffApplyError.
    """
    session = await get_session(session_id)

    try:
        target = _require_pending(session, diff_id)
    except (NotFoundError, ConflictError) as exc:
        logger.info("reject_one refused session_id=%s %s", session_id, exc)
        raise

    logger.debug(
        "reject_one session_id=%s diff_id=%s diff=%s", session_id, diff_id, target
    )
    working_json = DiffUtils.revert(target, session.get("working_json", {}))

    session["working_json"] = working_json
    target["status"] = "rejected"
    session["updated_at"] = now_iso()
    await store.save_session(session)
    logger.info("reject_one reverted session_id=%s diff_id=%s", session_id, diff_id)
    return {
        "success": True,
        "working_json": working_json,
        "baseline_json": session.get("baseline_json", {}),
        **_status_lists(session),
    }
