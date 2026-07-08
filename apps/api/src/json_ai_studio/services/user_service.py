"""User provisioning + profile service (ADR-0015).

Users are upserted on every authenticated request (idempotent
INSERT ... ON CONFLICT). Auth0 access tokens carry only `sub` by
default, so email/name/picture are backfilled once from the tenant's
/userinfo endpoint while the row's email is NULL.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import httpx
from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from ..db.database import session_factory
from ..db.models_orm import User
from ..settings import get_settings

logger = logging.getLogger("json_ai_studio.user_service")

_CYCLE_SECONDS = 30 * 86400


def _require_db():
    factory = session_factory()
    if factory is None:
        raise HTTPException(
            status_code=503,
            detail="Login is temporarily unavailable (database not configured).",
        )
    return factory


async def upsert_from_claims(claims: dict[str, Any], token: str) -> User:
    """Insert-or-update a user from verified Auth0 claims; return the row."""
    settings = get_settings()
    factory = _require_db()
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    async with factory() as db:
        stmt = (
            pg_insert(User)
            .values(
                auth0_sub=claims["sub"],
                email=claims.get("email"),
                name=claims.get("name"),
                picture=claims.get("picture"),
                monthly_credit_limit=settings.user_monthly_credit_limit,
                per_minute_token_limit=settings.user_per_minute_token_limit,
                last_login_at=now,
            )
            .on_conflict_do_update(
                index_elements=["auth0_sub"],
                set_={"last_login_at": now},
            )
            .returning(User)
        )
        user = (await db.execute(stmt)).scalar_one()
        await db.commit()

        if user.email is None:
            profile = await _fetch_userinfo(token)
            if profile:
                await db.execute(
                    update(User)
                    .where(User.id == user.id)
                    .values(
                        email=profile.get("email"),
                        name=profile.get("name"),
                        picture=profile.get("picture"),
                    )
                )
                await db.commit()
                user.email = profile.get("email")
                user.name = profile.get("name")
                user.picture = profile.get("picture")

    return user


async def _fetch_userinfo(token: str) -> dict[str, Any] | None:
    """Best-effort GET https://{domain}/userinfo with the bearer token."""
    settings = get_settings()
    url = f"https://{settings.auth0_domain}/userinfo"
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(url, headers={"Authorization": f"Bearer {token}"})
            if resp.status_code == 200:
                return resp.json()
            logger.warning("userinfo backfill failed status=%s", resp.status_code)
    except httpx.HTTPError as exc:
        logger.warning("userinfo backfill error=%s", exc)
    return None


async def get_profile(user_id) -> dict[str, Any]:
    """Return profile + credits for /api/me, applying the 30-day cycle reset."""
    factory = _require_db()
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    async with factory() as db:
        user = (
            await db.execute(select(User).where(User.id == user_id))
        ).scalar_one_or_none()
        if user is None:
            raise HTTPException(status_code=404, detail="User not found")

        # Monthly cycle reset so /api/me never shows stale usage.
        if (now - user.billing_cycle_start).total_seconds() > _CYCLE_SECONDS:
            await db.execute(
                update(User)
                .where(User.id == user.id)
                .values(credits_used=0.0, billing_cycle_start=now)
            )
            await db.commit()
            user.credits_used = 0.0
            user.billing_cycle_start = now

        remaining = max(0.0, user.monthly_credit_limit - user.credits_used)
        return {
            "id": str(user.id),
            "email": user.email,
            "name": user.name,
            "picture": user.picture,
            "plan": user.plan,
            "credits": {
                "monthly_limit": user.monthly_credit_limit,
                "used": round(user.credits_used, 3),
                "remaining": round(remaining, 3),
                "billing_cycle_start": user.billing_cycle_start.isoformat(),
            },
            "per_minute_token_limit": user.per_minute_token_limit,
        }
