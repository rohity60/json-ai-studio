"""Principal-aware credit + token-rate quota service (ADR-0015).

Single seam the gateway calls before/after every LLM invocation:

    await credit_service.check(principal)    # raises 402 / 429
    await credit_service.deduct(principal, credits, tokens)

Anonymous principals share one in-memory pool keyed by GENERAL_API_KEY
(pre-login behavior, resets on restart — accepted). Logged-in users have
DB-backed monthly credits (persist across restarts) plus an in-memory
per-minute token window (per-process, same trade-off as before).

Raised HTTPExceptions carry a structured `detail` dict with
`login_available` so the frontend can offer login as the fix.
"""

from __future__ import annotations

import logging
import time
from collections import deque
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select, update

from ..auth import Principal, mask_secret
from ..db.database import session_factory
from ..db.models_orm import User
from ..settings import get_settings

logger = logging.getLogger("json_ai_studio.credit_service")

_CYCLE_SECONDS = 30 * 86400
_WINDOW_SECONDS = 60

# In-memory state.
_anon_credits: dict[str, dict[str, Any]] = {}  # quota_key -> credit record
_per_minute_tokens: dict[str, deque] = {}  # quota_key -> deque[(ts, tokens)]


def _now_naive_utc() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _window_tokens(quota_key: str) -> int:
    """Sum tokens used in the sliding 60s window (pruning old entries)."""
    q = _per_minute_tokens.setdefault(quota_key, deque())
    window_start = time.monotonic() - _WINDOW_SECONDS
    while q and q[0][0] < window_start:
        q.popleft()
    return sum(tokens for _, tokens in q)


def _credit_error(login_available: bool) -> HTTPException:
    hint = (
        "Log in to get your own free monthly quota."
        if login_available
        else "Your monthly free credits are used up. Upgrade your plan."
    )
    return HTTPException(
        status_code=402,
        detail={
            "error": "Insufficient credits",
            "hint": hint,
            "login_available": login_available,
            "retry_after": None,
        },
    )


def _token_rate_error(login_available: bool) -> HTTPException:
    return HTTPException(
        status_code=429,
        detail={
            "error": "Per-minute token limit exceeded",
            "hint": (
                "Log in for higher free limits."
                if login_available
                else "Please wait a moment and try again."
            ),
            "login_available": login_available,
            "retry_after": _WINDOW_SECONDS,
        },
        headers={"Retry-After": str(_WINDOW_SECONDS)},
    )


def _ensure_anon_record(quota_key: str) -> dict[str, Any]:
    settings = get_settings()
    record = _anon_credits.get(quota_key)
    if record is None:
        record = {
            "plan": "free",
            "monthly_limit": settings.anon_monthly_credit_limit,
            "credits_used": 0.0,
            "billing_cycle_start": _now_naive_utc(),
        }
        _anon_credits[quota_key] = record
    # Monthly cycle reset.
    if (
        _now_naive_utc() - record["billing_cycle_start"]
    ).total_seconds() > _CYCLE_SECONDS:
        record["credits_used"] = 0.0
        record["billing_cycle_start"] = _now_naive_utc()
    return record


async def check(principal: Principal) -> None:
    """Raise HTTPException 402 (credits) or 429 (token rate) if over quota."""
    settings = get_settings()
    logger.debug(
        "quota check kind=%s quota_key=%s window_tokens=%d",
        principal.kind,
        mask_secret(principal.quota_key),
        _window_tokens(principal.quota_key),
    )

    if principal.kind == "user":
        factory = session_factory()
        if factory is None:
            raise HTTPException(
                status_code=503,
                detail="Login is temporarily unavailable (database not configured).",
            )
        async with factory() as db:
            user = (
                await db.execute(select(User).where(User.id == principal.user_id))
            ).scalar_one_or_none()
            if user is None:
                raise HTTPException(status_code=401, detail="Unknown user")
            # Monthly cycle reset (persisted).
            now = _now_naive_utc()
            if (now - user.billing_cycle_start).total_seconds() > _CYCLE_SECONDS:
                await db.execute(
                    update(User)
                    .where(User.id == user.id)
                    .values(credits_used=0.0, billing_cycle_start=now)
                )
                await db.commit()
                user.credits_used = 0.0
            logger.debug(
                "user quota credits_used=%.3f limit=%s",
                user.credits_used,
                user.monthly_credit_limit,
            )
            if (
                user.monthly_credit_limit != -1
                and user.credits_used >= user.monthly_credit_limit
            ):
                logger.info(
                    "credit limit hit user_id=%s used=%.3f limit=%s",
                    principal.user_id,
                    user.credits_used,
                    user.monthly_credit_limit,
                )
                raise _credit_error(login_available=False)
            if _window_tokens(principal.quota_key) >= user.per_minute_token_limit:
                logger.info(
                    "token-rate limit hit user_id=%s limit=%d",
                    principal.user_id,
                    user.per_minute_token_limit,
                )
                raise _token_rate_error(login_available=False)
        return

    # Anonymous: shared pool.
    record = _ensure_anon_record(principal.quota_key)
    logger.debug(
        "anon quota credits_used=%.3f limit=%s",
        record["credits_used"],
        record["monthly_limit"],
    )
    if (
        record["monthly_limit"] != -1
        and record["credits_used"] >= record["monthly_limit"]
    ):
        logger.info(
            "anon credit limit hit quota_key=%s used=%.3f limit=%s",
            mask_secret(principal.quota_key),
            record["credits_used"],
            record["monthly_limit"],
        )
        raise _credit_error(login_available=True)
    if _window_tokens(principal.quota_key) >= settings.anon_per_minute_token_limit:
        logger.info(
            "anon token-rate limit hit quota_key=%s limit=%d",
            mask_secret(principal.quota_key),
            settings.anon_per_minute_token_limit,
        )
        raise _token_rate_error(login_available=True)


async def deduct(principal: Principal, credits: float, tokens: int = 0) -> None:
    """Record spend: monthly credits + per-minute token window."""
    logger.debug(
        "quota deduct kind=%s quota_key=%s credits=%.6f tokens=%d",
        principal.kind,
        mask_secret(principal.quota_key),
        credits,
        tokens,
    )
    if principal.kind == "user":
        factory = session_factory()
        if factory is not None:
            async with factory() as db:
                # Atomic increment — no read-modify-write race.
                await db.execute(
                    update(User)
                    .where(User.id == principal.user_id)
                    .values(credits_used=User.credits_used + credits)
                )
                await db.commit()
    else:
        record = _ensure_anon_record(principal.quota_key)
        record["credits_used"] = record.get("credits_used", 0.0) + credits

    if tokens > 0:
        _per_minute_tokens.setdefault(principal.quota_key, deque()).append(
            (time.monotonic(), tokens)
        )


def get_anon_credits(quota_key: str) -> dict[str, Any]:
    """Debug/inspection helper for the shared anonymous pool."""
    return _anon_credits.get(quota_key, {})
