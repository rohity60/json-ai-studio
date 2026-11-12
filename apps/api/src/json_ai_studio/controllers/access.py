"""Session ownership gate for `/api/sessions/{session_id}/**` (ADR-0027).

Use `Depends(require_session_owner)` in place of `Depends(require_api_key)`
on any route with a `session_id` path parameter. It resolves the principal
(auth + rate limit, cached per request by FastAPI) and answers 404 when the
session is unknown or belongs to someone else.
"""

from __future__ import annotations

from fastapi import Depends, HTTPException

from ..auth import Principal, get_principal
from ..services import session_service
from ..services.errors import NotFoundError


async def require_session_owner(
    session_id: str,
    principal: Principal = Depends(get_principal),
) -> Principal:
    try:
        await session_service.get_owned_session(session_id, principal)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return principal
