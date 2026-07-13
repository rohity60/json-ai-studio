"""Workspace controller tests (ADR-0018).

Covers the router's own logic — bearer-only gating (`_require_user`) and
domain-error -> HTTP mapping (`_map_error`) — as unit tests, plus the
anonymous 401 path end-to-end through the app (no DB needed). The DB-backed
behaviour is exercised in test_workspace_service.py.
"""

import uuid

import pytest
from fastapi import HTTPException

from src.json_ai_studio.auth import Principal
from src.json_ai_studio.controllers.workspaces import _map_error, _require_user
from src.json_ai_studio.services.errors import (
    ConflictError,
    DuplicateError,
    LimitExceededError,
    NotFoundError,
)

# ---------------------------------------------------------------------------
# _require_user — bearer-only gating
# ---------------------------------------------------------------------------


class TestRequireUser:
    def test_anonymous_rejected_with_login_available(self):
        principal = Principal(kind="anonymous", quota_key="", rate_key="key")
        with pytest.raises(HTTPException) as exc:
            _require_user(principal)
        assert exc.value.status_code == 401
        assert exc.value.detail["login_available"] is True

    def test_user_returns_id(self):
        uid = uuid.uuid4()
        principal = Principal(
            kind="user", quota_key=f"user:{uid}", rate_key=f"user:{uid}", user_id=uid
        )
        assert _require_user(principal) == uid

    def test_user_kind_without_id_rejected(self):
        principal = Principal(kind="user", quota_key="", rate_key="", user_id=None)
        with pytest.raises(HTTPException) as exc:
            _require_user(principal)
        assert exc.value.status_code == 401


# ---------------------------------------------------------------------------
# _map_error — domain exception -> HTTP status
# ---------------------------------------------------------------------------


class TestMapError:
    def test_not_found_to_404(self):
        http = _map_error(NotFoundError("Workspace not found"))
        assert http.status_code == 404
        assert http.detail == "Workspace not found"

    def test_limit_exceeded_to_409_structured(self):
        http = _map_error(LimitExceededError("jsons", 5))
        assert http.status_code == 409
        assert http.detail == {
            "error": "limit_exceeded",
            "limit_type": "jsons",
            "limit": 5,
        }

    def test_duplicate_to_409_structured(self):
        http = _map_error(DuplicateError("tag"))
        assert http.status_code == 409
        assert http.detail == {"error": "duplicate", "field": "tag"}

    def test_plain_conflict_to_409_string(self):
        http = _map_error(ConflictError("The default workspace cannot be deleted."))
        assert http.status_code == 409
        assert http.detail == "The default workspace cannot be deleted."

    def test_unknown_error_reraised(self):
        """Non-domain errors are not swallowed as 4xx."""
        with pytest.raises(ValueError):
            _map_error(ValueError("boom"))


# ---------------------------------------------------------------------------
# Anonymous request end-to-end (no DB, no Auth0 needed)
# ---------------------------------------------------------------------------


class TestAnonymousGating:
    @pytest.fixture
    def client(self):
        from fastapi.testclient import TestClient

        from src.json_ai_studio.main import app

        with TestClient(app) as c:
            yield c

    def test_list_workspaces_anonymous_401(self, client):
        resp = client.get("/api/workspaces", headers={"X-API-Key": "anon-browser-key"})
        assert resp.status_code == 401
        assert resp.json()["detail"]["login_available"] is True

    def test_create_workspace_anonymous_401(self, client):
        resp = client.post(
            "/api/workspaces",
            headers={"X-API-Key": "anon-browser-key"},
            json={"name": "x"},
        )
        assert resp.status_code == 401
        assert resp.json()["detail"]["login_available"] is True
