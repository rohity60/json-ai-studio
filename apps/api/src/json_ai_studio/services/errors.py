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
