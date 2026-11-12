"""Job proposal for whole-document reviews (ADR-0026, PRD C §2).

When a message asks to review the whole document (intent `review`) and the
document does not fit one planned turn, nothing is sent to the model: the
chat answers with what the review costs as a batch job — records, batches,
tokens, time — computed by the packer that will size the real batches.
"""

from __future__ import annotations

import logging
from typing import Any

from ..deployment import DeploymentRegistry
from . import job_packing
from .intent import REVIEW, Intent
from .progress import _duration
from .turn_planner import TurnPlan, plan_turn

logger = logging.getLogger("json_ai_studio.review_proposal")


def default_deployment() -> tuple[Any, str] | None:
    """(deployment, litellm model) default traffic would use next; no
    round-robin advance, no call. None when nothing is enabled."""
    deployment = DeploymentRegistry.peek_default()
    if deployment is None:
        return None
    model = f"{deployment.model_prefix}{deployment.base_model}"
    return deployment, deployment.litellm_model(model)


def scope_for(doc: Any, intent: Intent) -> str:
    """The user's named collection when it resolves, else the dominant one."""
    named = intent.scope_path
    if named and isinstance(job_packing.resolve(doc, named), (dict, list)):
        return named
    return job_packing.dominant_scope(doc)


def propose(
    working_json: Any,
    message: str,
    intent: Intent,
    history: list[dict[str, str]],
    deployment: Any,
    litellm_model: str,
) -> dict[str, Any] | None:
    """JobProposal payload, or None when the turn should run as usual:
    not a review, or the whole document fits one inline call (C-10)."""
    if intent.kind != REVIEW:
        return None
    plan = plan_turn(working_json, message, list(history), deployment, litellm_model)
    if isinstance(plan, TurnPlan) and plan.mode == "inline":
        return None
    job = job_packing.plan_job(
        working_json,
        scope_for(working_json, intent),
        message,
        deployment,
        litellm_model,
    )
    if job.batch_count == 0:
        return None
    return {
        "scope_path": job.scope_path,
        "record_count": job.record_count,
        "batch_count": job.batch_count,
        "est_tokens": job.est_tokens,
        "eta_s": job.eta_s,
        "instruction": message,
    }


def explanation(proposal: dict[str, Any]) -> str:
    """The proposal in plain words; built in code, never by the model."""
    records, batches = proposal["record_count"], proposal["batch_count"]
    where = proposal["scope_path"] or "the document"
    return (
        "This is a review of the whole document, which is too large for one "
        f"request: {records:,} item{'s' if records != 1 else ''} in {where}. "
        f"I can go through it in {batches:,} batch"
        f"{'es' if batches != 1 else ''} — about "
        f"{_duration(proposal['eta_s'])} on the current AI model. Each batch's "
        "changes appear as pending diffs you can accept or reject, and you "
        "can pause at any time. Start the review to begin; nothing has been "
        "sent to the AI yet."
    )
