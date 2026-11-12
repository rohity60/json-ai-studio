"""Whole-document review jobs (ADR-0026, PRD C §3–§4).

The client drives the job: every `POST .../jobs/{id}/next` processes
exactly one batch — pack → one lean LLM call → parse diffs → apply as
pending → advance the cursor. There is no background worker; closing the
tab pauses the job. State lives in the session dict (in memory) and is
lost with it on a backend restart.

The LLM call goes through `GatewayService.invoke` with a planner callback,
so a batch gets the same credit check, deployment pick, budget gate
(`waiting` events), retries, usage and credit deduction as a chat turn.
Packing happens inside that callback — only there the serving deployment
(its limits and calibration) is known.
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import re
import time
from typing import Any, AsyncGenerator
from uuid import uuid4

from ..db.session_store import store
from ..diff_utils import DiffUtils, parse_llm_response
from ..gateway import SERVICE_BUSY_MESSAGE, GatewayService
from ..settings import get_settings
from ..text_edits import REPLACE_TEXT, expand_text_edits
from . import chat_history_service, job_packing, review_proposal
from . import deployment_budget as budget
from .errors import ConflictError, InvalidInputError, NotFoundError
from .session_service import get_session, now_iso
from .turn_planner import TurnPlan

logger = logging.getLogger("json_ai_studio.jobs")

ACTIVE = frozenset({"ready", "running", "failed"})
# A `running` flag older than this is a crashed/abandoned stream, not a
# batch in flight (the longest batch waits one budget window + retries).
_RUNNING_STALE_S = 900.0
_OUT_OF_BATCH = "outside this batch — only records shown to the AI may change"
_CUT_OFF = (
    "The AI's answer for this batch was cut off or unreadable. Retrying uses "
    "a smaller batch."
)
_QUOTA_EVENTS = ("rate_limit", "credit_limit", "input_too_large")


def sse(event: str, payload: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(payload, default=str)}\n\n"


def _parse_sse(block: str) -> tuple[str | None, dict[str, Any] | None]:
    from .chat_service import parse_sse  # chat_service imports the gateway too

    return parse_sse(block)


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------


def _jobs(session: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return session.setdefault("jobs", {})


def active_job(session: dict[str, Any]) -> dict[str, Any] | None:
    for job in _jobs(session).values():
        if job["status"] in ACTIVE:
            return job
    return None


def running_job(session: dict[str, Any]) -> dict[str, Any] | None:
    """The job with a batch in flight right now, if any (C-26)."""
    job = active_job(session)
    if job is None or job["status"] != "running":
        return None
    if time.monotonic() - job.get("running_since", 0.0) > _RUNNING_STALE_S:
        return None
    return job


def _require(session: dict[str, Any], job_id: str) -> dict[str, Any]:
    job = _jobs(session).get(job_id)
    if job is None:
        raise NotFoundError(f"Job {job_id} not found")
    return job


def public(job: dict[str, Any], session: dict[str, Any]) -> dict[str, Any]:
    """Wire shape (spec: Job) — internal cursor details stay out."""
    pending = sum(
        1
        for d in chat_history_service.pending_diffs(session)
        if d.get("job_id") == job["id"]
    )
    status = job["status"]
    if status == "running" and running_job(session) is None:
        status = "ready"  # abandoned stream
    return {
        "id": job["id"],
        "status": status,
        "scope_path": job["scope_path"],
        "instruction": job["instruction"],
        "source_turn_id": job.get("source_turn_id"),
        "cursor": job["cursor"],
        "total": job["total"],
        "batches_done": job["batches_done"],
        "batch_count": job.get("batch_count"),
        "diffs_pending": pending,
        "eta_s": job.get("eta_s"),
        "error": job.get("error"),
        "batches": [
            {k: b[k] for k in ("batch_no", "start", "end", "diffs", "failed")}
            | {"explanation": b.get("explanation", "")}
            for b in job["batches"]
        ],
        "created_at": job["created_at"],
        "updated_at": job["updated_at"],
    }


# ---------------------------------------------------------------------------
# Create / get / cancel (C-20, C-22, C-23)
# ---------------------------------------------------------------------------


async def create_job(
    session_id: str,
    scope_path: str | None,
    instruction: str,
    source_turn_id: str | None = None,
) -> dict[str, Any]:
    session = await get_session(session_id)
    current = active_job(session)
    if current is not None:
        raise ConflictError(current["id"])
    doc = session.get("working_json") or {}
    if not doc:
        raise InvalidInputError("Upload a JSON document before starting a review")
    if scope_path is None:
        scope_path = job_packing.dominant_scope(doc)
    if not isinstance(job_packing.resolve(doc, scope_path), (dict, list)):
        raise InvalidInputError(f"scope_path {scope_path!r} is not a collection")
    units = job_packing.build_units(doc, scope_path)
    if not units:
        raise InvalidInputError(f"Nothing to review in {scope_path or '/'}")

    # Same estimate as the proposal; None when no deployment is enabled.
    batch_count: int | None = None
    eta_s: int | None = None
    try:
        target = review_proposal.default_deployment()
        if target is not None:
            plan = job_packing.plan_job(doc, scope_path, instruction, *target)
            batch_count, eta_s = plan.batch_count, plan.eta_s
    except Exception:
        logger.exception("job estimate failed session=%s", session_id)

    now = now_iso()
    job: dict[str, Any] = {
        "id": uuid4().hex,
        "status": "ready",
        "scope_path": scope_path,
        "instruction": instruction.strip(),
        "source_turn_id": source_turn_id,
        "cursor": 0,
        "sub": None,  # [leaf, char offset] inside a split record
        "total": len(units),
        "batches_done": 0,
        "batch_count": batch_count,
        "eta_s": eta_s,
        "error": None,
        "batches": [],
        "shrink": 1.0,  # room factor for the next attempt (output cut off)
        "elapsed_s": 0.0,
        "created_at": now,
        "updated_at": now,
    }
    _jobs(session)[job["id"]] = job
    session["active_job_id"] = job["id"]
    session["updated_at"] = now
    await store.save_session(session)
    logger.info(
        "job created session=%s job=%s scope=%s total=%d batches_est=%s",
        session_id,
        job["id"],
        scope_path or "/",
        job["total"],
        batch_count,
    )
    return public(job, session)


async def get_job(session_id: str, job_id: str) -> dict[str, Any]:
    session = await get_session(session_id)
    return public(_require(session, job_id), session)


async def cancel_job(session_id: str, job_id: str) -> dict[str, Any]:
    """Cancel; diffs already produced stay pending (C-23)."""
    session = await get_session(session_id)
    job = _require(session, job_id)
    if running_job(session) is job:
        raise ConflictError("job_running")
    if job["status"] in ACTIVE:
        job["status"] = "cancelled"
        job["updated_at"] = now_iso()
        if session.get("active_job_id") == job_id:
            session["active_job_id"] = None
        await store.save_session(session)
        logger.info(
            "job cancelled session=%s job=%s cursor=%d/%d",
            session_id,
            job_id,
            job["cursor"],
            job["total"],
        )
    return public(job, session)


# ---------------------------------------------------------------------------
# One batch (C-21, C-24..C-27, C-33, C-36)
# ---------------------------------------------------------------------------


async def begin_next(session_id: str, job_id: str) -> tuple[dict, dict]:
    """Check the job may run a batch and mark it running. Raises before
    any stream starts, so the controller can answer with an HTTP code."""
    session = await get_session(session_id)
    job = _require(session, job_id)
    if job["status"] in ("done", "cancelled"):
        raise ConflictError("job_finished")
    if running_job(session) is job:
        raise ConflictError("job_running")
    job["status"] = "running"
    job["running_since"] = time.monotonic()
    return session, job


def _in_batch(path: str, unit_paths: list[str]) -> bool:
    return any(path == p or path.startswith(p + "/") for p in unit_paths)


def _unreadable(text: str) -> bool:
    """The answer looks like JSON but does not parse: cut off mid-output."""
    body = text.strip()
    if not body:
        return True
    if body.startswith("```"):
        body = body.strip("`").split("\n", 1)[-1]
    if not body.lstrip().startswith(("{", "[")):
        return False  # prose: "nothing to change"
    try:
        json.loads(body)
        return False
    except ValueError:
        return True


def _string_hits(path: str, node: Any, find: str) -> list[str]:
    """Paths of the strings at/under `path` that contain `find`."""
    if isinstance(node, str):
        return [path] if find in node else []
    if isinstance(node, (dict, list)):
        return [
            p
            for p, value in job_packing._leaves(job_packing.Unit(path, node))
            if isinstance(value, str) and find in value
        ]
    return []


def _retarget_text_edits(
    diffs: list[dict[str, Any]], doc: Any, shown: list[str] | None = None
) -> list[dict[str, Any]]:
    """Point a replace_text at the one string that holds its "find" text.

    - Models often name the record they were shown ("/entries/7") instead
      of the field ("/entries/7/content") — live run 2026-11-13, Nemotron:
      every fix of a batch addressed the record.
    - They also put a fix on a NEIGHBOURING record of the batch (live
      2026-11-13: the typo of entry 42 addressed to /entries/22, 45's to
      /entries/42). When the named path does not contain the text, every
      record of this batch is searched.
    "find" is exact text, so exactly one containing string is the only
    possible target; zero or several → left as is (the edit then fails
    with its normal note).
    """
    out = []
    for d in diffs:
        find = d.get("find")
        if d.get("operation") == REPLACE_TEXT and isinstance(find, str) and find:
            path = str(d.get("path", ""))
            hits = _string_hits(path, job_packing.resolve(doc, path), find)
            if not hits and shown:
                hits = sorted(
                    {
                        h
                        for unit in shown
                        for h in _string_hits(
                            unit, job_packing.resolve(doc, unit), find
                        )
                    }
                )
                if len(hits) == 1:
                    logger.info("job text edit retargeted from=%s to=%s", path, hits[0])
            if len(hits) == 1 and hits[0] != path:
                d = {**d, "path": hits[0]}
        out.append(d)
    return out


_NOTE_PATH = re.compile(r"^Text edit on (\S+) ")


def _hash(value: Any) -> str:
    text = json.dumps(value, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:16]


def _estimate_rest(job: dict[str, Any], total: int) -> None:
    """Batches and seconds left, from what this run has shown so far."""
    done, cursor = job["batches_done"], job["cursor"]
    left_units = max(0, total - cursor)
    if left_units == 0 and not job["sub"]:
        job["batch_count"], job["eta_s"] = done, 0
        return
    if cursor > 0:
        left = max(1, math.ceil(left_units * done / cursor))
    else:  # still inside the first (split) record
        left = max(1, (job.get("batch_count") or done + 1) - done)
    job["batch_count"] = done + left
    # The last batch's real time is the best guide: the first batch of a
    # run usually skips the budget wait every later batch pays.
    per_batch = max(job.get("last_s", 0.0), job.get("pace_s", 0.0) / max(1, done))
    job["eta_s"] = int(math.ceil(left * per_batch))


async def run_batch(
    session: dict[str, Any], job: dict[str, Any], principal: Any
) -> AsyncGenerator[str, None]:
    """SSE stream for exactly one batch of `job` (after begin_next)."""
    session_id = session["id"]
    batch_no = job["batches_done"] + 1
    started = time.monotonic()
    settings = get_settings()
    holder: dict[str, Any] = {}

    def fail(message: str) -> str:
        job["status"] = "failed"
        job["error"] = message
        return sse(
            "batch_failed",
            {
                "batch_no": batch_no,
                "error": message,
                "retryable": True,
                "job": public(job, session),
            },
        )

    def planner(deployment: Any, litellm_model: str) -> TurnPlan:
        # Units are re-read from the current document (C-33): records not
        # yet processed are reviewed with whatever value they have now.
        units = job_packing.build_units(session["working_json"], job["scope_path"])
        overhead = job_packing.overhead_tokens(
            deployment, litellm_model, job["instruction"]
        )
        room = job_packing.batch_room(
            deployment, litellm_model, overhead, job["shrink"]
        )
        batch = job_packing.pack_next(
            units,
            job["cursor"],
            tuple(job["sub"]) if job["sub"] else None,
            room,
            job_packing.make_sizer(deployment, litellm_model),
            settings.job_max_records_per_batch,
        )
        messages = job_packing.lean_messages(job["instruction"], batch.items)
        holder.update(
            batch=batch,
            units=units,
            # Sustained time per batch at this deployment's pace (budget
            # window share, pacing): the ETA floor, since the first batch
            # usually runs without waiting.
            pace_s=job_packing.batch_seconds(
                deployment, batch.tokens + overhead, settings.job_est_call_s
            ),
        )
        logger.info(
            "job batch packed session=%s job=%s batch=%d items=%d units=%d-%d "
            "tokens=%d room=%d overhead=%d deployment=%s",
            session_id,
            job["id"],
            batch_no,
            len(batch.items),
            batch.start,
            batch.end,
            batch.tokens,
            room,
            overhead,
            getattr(deployment, "name", "?"),
        )
        logger.debug("job batch prompt session=%s messages=%s", session_id, messages)
        return TurnPlan(
            "inline",
            messages,
            None,
            0,
            budget.estimate_tokens(litellm_model, messages),
        )

    try:
        total = len(job_packing.build_units(session["working_json"], job["scope_path"]))
        if job["cursor"] >= total:
            # Nothing left (e.g. records were deleted since the last batch).
            job.update(status="done", total=total, eta_s=0, error=None)
            session["active_job_id"] = None
            yield sse(
                "batch_complete",
                {
                    "batch_no": job["batches_done"],
                    "range": None,
                    "diffs": [],
                    "cursor": job["cursor"],
                    "total": total,
                    "eta_s": 0,
                    "explanation": "The review is complete.",
                    "working_json": session["working_json"],
                    "job": public(job, session),
                },
            )
            return

        parts: list[str] = []
        stop: str | None = None
        async for event_text in GatewayService.invoke(
            session_id, job["instruction"], principal, "", planner=planner
        ):
            event, payload = _parse_sse(event_text)
            if event == "thinking":
                text = (payload or {}).get("text")
                if isinstance(text, str):
                    parts.append(text)
                    yield sse("draft", {"text": text})  # keep-alive only
            elif event in _QUOTA_EVENTS:
                stop = "quota"
                yield event_text
            elif event in ("service_unavailable", "error"):
                stop = "failed"
            else:
                yield event_text

        if stop == "quota":
            # C-27: the caller's quota or the model's capacity ended the
            # batch; nothing was processed, the cursor stays.
            job["status"] = "ready"
            logger.info("job batch quota stop session=%s job=%s", session_id, job["id"])
            return
        batch: job_packing.Batch | None = holder.get("batch")
        if stop == "failed" or batch is None:
            logger.warning(
                "job batch failed session=%s job=%s batch=%d",
                session_id,
                job["id"],
                batch_no,
            )
            yield fail(SERVICE_BUSY_MESSAGE)
            return

        combined = "".join(parts)
        logger.debug("job batch output session=%s: %s", session_id, combined)
        if _unreadable(combined):
            job["shrink"] = max(0.25, job["shrink"] * 0.5)
            logger.warning(
                "job batch unreadable session=%s job=%s batch=%d output_len=%d "
                "next_shrink=%.2f",
                session_id,
                job["id"],
                batch_no,
                len(combined),
                job["shrink"],
            )
            yield fail(_CUT_OFF)
            return

        diffs, explanation = parse_llm_response(combined)
        units: list[job_packing.Unit] = holder["units"]
        shown = [u.path for u in units[batch.start : batch.end + 1]]
        outside = [d for d in diffs if not _in_batch(str(d.get("path", "")), shown)]
        diffs = [d for d in diffs if _in_batch(str(d.get("path", "")), shown)]

        # The document may have changed while the model worked (a diff was
        # rejected, a chat edit landed): expand and apply against it as it
        # is NOW. Text edits run on the full value; every diff goes through
        # the truncation guard and the normal failed-diff path (C-36).
        doc = session["working_json"]
        diffs = _retarget_text_edits(diffs, doc, shown)
        diffs, notes = expand_text_edits(diffs, doc)
        if notes:
            logger.info(
                "job batch text edits skipped session=%s job=%s batch=%d notes=%s",
                session_id,
                job["id"],
                batch_no,
                notes[:10],
            )
        from .chat_service import _is_noop

        diffs = [d for d in diffs if not _is_noop(d, doc)]
        merged, applied, failed = DiffUtils.apply_all_verbose(diffs, doc)
        tag = {"job_id": job["id"], "batch_no": batch_no}
        applied_entries = [
            {**d, "id": str(uuid4()), "status": "pending", **tag} for d in applied
        ]
        failed_entries = [
            {**d, "id": str(uuid4()), "status": "failed", "failure_reason": r, **tag}
            for d, r in [*failed, *((d, _OUT_OF_BATCH) for d in outside)]
            if d.get("operation") in ("add", "modify", "delete")
        ]
        # Text edits that could not apply are shown as failed changes too,
        # so a batch whose fixes all missed never looks clean.
        for note in notes:
            match = _NOTE_PATH.match(note)
            failed_entries.append(
                {
                    "path": match.group(1) if match else "",
                    "operation": "modify",
                    "old_value": None,
                    "new_value": None,
                    "id": str(uuid4()),
                    "status": "failed",
                    "failure_reason": note,
                    **tag,
                }
            )
        session["working_json"] = merged

        # Progress.
        job["cursor"] = batch.cursor
        job["sub"] = list(batch.sub) if batch.sub else None
        job["batches_done"] = batch_no
        job["shrink"] = 1.0
        job["error"] = None
        job["total"] = len(units)
        job["last_s"] = time.monotonic() - started
        job["elapsed_s"] += job["last_s"]
        job["pace_s"] = job.get("pace_s", 0.0) + holder.get("pace_s", 0.0)
        finished = job["cursor"] >= len(units)
        job["status"] = "done" if finished else "ready"
        if finished:
            session["active_job_id"] = None
        _estimate_rest(job, len(units))

        # Compact history turn (C-25): later chat turns see the progress.
        first, last = batch.start + 1, batch.end + 1
        span = f"item {first}" if first == last else f"items {first}–{last}"
        n = len(applied_entries)
        content = (
            f"Review batch {batch_no}: {span} of {len(units)}, "
            f"{n} change{'s' if n != 1 else ''}"
        )
        if failed_entries:
            content += f", {len(failed_entries)} could not be applied"
        content += "."
        turn = chat_history_service.make_turn(
            "assistant",
            content,
            diffs=[*applied_entries, *failed_entries],
            kind="job_batch",
        )
        turn.update(tag)
        chat_history_service.append_turns(session, turn)
        job["batches"].append(
            {
                "batch_no": batch_no,
                "start": batch.start,
                "end": batch.end,
                "diffs": n,
                "failed": len(failed_entries),
                "explanation": explanation or "",
                "record_hashes": [
                    _hash(u.value) for u in units[batch.start : batch.end + 1]
                ],
            }
        )
        job["updated_at"] = session["updated_at"] = now_iso()
        await store.save_session(session)
        logger.info(
            "job batch done session=%s job=%s batch=%d units=%d-%d applied=%d "
            "failed=%d cursor=%d/%d status=%s eta_s=%s",
            session_id,
            job["id"],
            batch_no,
            batch.start,
            batch.end,
            n,
            len(failed_entries),
            job["cursor"],
            len(units),
            job["status"],
            job["eta_s"],
        )

        for entry in applied_entries:
            yield sse("diff", {"entry": entry})
        yield sse(
            "batch_complete",
            {
                "batch_no": batch_no,
                "range": [batch.start, batch.end],
                "diffs": [*applied_entries, *failed_entries],
                "cursor": job["cursor"],
                "total": len(units),
                "eta_s": job["eta_s"],
                "explanation": explanation or content,
                "working_json": merged,
                "turn": turn,
                "job": public(job, session),
            },
        )
    except Exception:
        logger.exception(
            "job batch crashed session=%s job=%s batch=%d",
            session_id,
            job["id"],
            batch_no,
        )
        yield fail(SERVICE_BUSY_MESSAGE)
    finally:
        # Interrupted (client went away mid-call) → runnable again.
        if job["status"] == "running":
            job["status"] = "ready"
        job["updated_at"] = now_iso()
        await store.save_session(session)
