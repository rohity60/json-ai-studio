"""User profile endpoints (ADR-0015)."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException

from ..auth import Principal, get_principal
from ..models import UserProfile
from ..services import user_service

logger = logging.getLogger("json_ai_studio.controllers.users")

router = APIRouter(prefix="/api", tags=["users"])


@router.get("/me", response_model=UserProfile)
async def endpoint_get_me(principal: Principal = Depends(get_principal)):
    """Return the logged-in user's profile + credit quota. 401 for anonymous."""
    logger.info(
        "GET /api/me principal=%s user_id=%s", principal.kind, principal.user_id
    )
    if principal.kind != "user" or principal.user_id is None:
        raise HTTPException(
            status_code=401,
            detail="Login required. Send an Authorization: Bearer token.",
        )
    return await user_service.get_profile(principal.user_id)
