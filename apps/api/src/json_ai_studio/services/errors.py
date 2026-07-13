"""Domain exceptions raised by services; controllers map them to HTTP codes.

NotFoundError -> 404, ConflictError -> 409, InvalidInputError -> 400.
Services never raise HTTPException directly (keeps them transport-agnostic).
"""


class NotFoundError(Exception):
    """Requested resource does not exist."""


class ConflictError(Exception):
    """Operation conflicts with the current resource state."""


class InvalidInputError(Exception):
    """Request payload failed parsing or validation."""


class LimitExceededError(ConflictError):
    """A workspace/document limit blocks the write — never evicted (ADR-0018).

    Carries the structured 409 detail the frontend renders as guidance.
    """

    def __init__(self, limit_type: str, limit: int):
        self.detail = {
            "error": "limit_exceeded",
            "limit_type": limit_type,
            "limit": limit,
        }
        super().__init__(f"{limit_type} limit of {limit} reached")


class DuplicateError(ConflictError):
    """A UNIQUE constraint would be violated (workspace name / document tag)."""

    def __init__(self, field: str):
        self.detail = {"error": "duplicate", "field": field}
        super().__init__(f"duplicate {field}")
