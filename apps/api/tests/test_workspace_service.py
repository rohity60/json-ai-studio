"""Workspace persistence service tests (ADR-0018).

Integration tests against a dedicated Postgres database (see conftest
`ws_db`) so JSONB, the partial unique index, FOR UPDATE, and cascade
deletes all behave as in production.

Run from apps/api with `PYTHONPATH=. uv run pytest tests/test_workspace_service.py`.
Requires Postgres on :5433 (docker-compose db) and the json_ai_studio_test
database (created by the test harness / manually once).
"""

import uuid

import pytest
from fastapi import HTTPException

from src.json_ai_studio.services import workspace_service as svc
from src.json_ai_studio.services.errors import (
    ConflictError,
    DuplicateError,
    LimitExceededError,
    NotFoundError,
)
from src.json_ai_studio.settings import get_settings


def _set_limits(monkeypatch, *, jsons=None, versions=None):
    """Shrink workspace limits for a test; settings re-read on next call."""
    if jsons is not None:
        monkeypatch.setenv("WORKSPACE_MAX_JSONS", str(jsons))
    if versions is not None:
        monkeypatch.setenv("JSON_MAX_VERSIONS", str(versions))
    get_settings.cache_clear()


# ---------------------------------------------------------------------------
# Provisioning — ensure_default_workspace (P-01)
# ---------------------------------------------------------------------------


class TestDefaultWorkspace:
    async def test_creates_default_when_missing(self, user_id):
        await svc.ensure_default_workspace(user_id)
        rows = await svc.list_workspaces(user_id)
        assert len(rows) == 1
        assert rows[0]["is_default"] is True
        assert rows[0]["name"] == "default"

    async def test_idempotent_no_duplicate(self, user_id):
        await svc.ensure_default_workspace(user_id)
        await svc.ensure_default_workspace(user_id)
        await svc.ensure_default_workspace(user_id)
        rows = await svc.list_workspaces(user_id)
        assert len(rows) == 1

    async def test_survives_rename(self, user_id):
        """Keyed on is_default, not name — a rename must not re-provision."""
        await svc.ensure_default_workspace(user_id)
        ws = (await svc.list_workspaces(user_id))[0]
        await svc.rename_workspace(user_id, ws["id"], "renamed-default")
        await svc.ensure_default_workspace(user_id)
        rows = await svc.list_workspaces(user_id)
        assert len(rows) == 1
        assert rows[0]["name"] == "renamed-default"
        assert rows[0]["is_default"] is True


# ---------------------------------------------------------------------------
# Workspace CRUD
# ---------------------------------------------------------------------------


class TestWorkspaceCrud:
    async def test_create_returns_summary(self, user_id):
        ws = await svc.create_workspace(user_id, "payments")
        assert ws["name"] == "payments"
        assert ws["is_default"] is False
        assert ws["document_count"] == 0

    async def test_duplicate_name_rejected(self, user_id):
        await svc.create_workspace(user_id, "dup")
        with pytest.raises(DuplicateError):
            await svc.create_workspace(user_id, "dup")

    async def test_same_name_different_user_allowed(self, user_id, other_user_id):
        await svc.create_workspace(user_id, "shared-name")
        # No raise: UNIQUE is (user_id, name).
        ws = await svc.create_workspace(other_user_id, "shared-name")
        assert ws["name"] == "shared-name"

    async def test_list_ordered_with_counts(self, user_id):
        a = await svc.create_workspace(user_id, "a")
        await svc.create_workspace(user_id, "b")
        await svc.save_document(
            user_id, a["id"], "doc1", [{"label": "v1", "content": {"x": 1}}]
        )
        rows = await svc.list_workspaces(user_id)
        assert [r["name"] for r in rows] == ["a", "b"]
        assert rows[0]["document_count"] == 1
        assert rows[1]["document_count"] == 0

    async def test_list_isolated_per_user(self, user_id, other_user_id):
        await svc.create_workspace(user_id, "mine")
        await svc.create_workspace(other_user_id, "theirs")
        mine = await svc.list_workspaces(user_id)
        assert [r["name"] for r in mine] == ["mine"]

    async def test_rename(self, user_id):
        ws = await svc.create_workspace(user_id, "old")
        out = await svc.rename_workspace(user_id, ws["id"], "new")
        assert out["name"] == "new"

    async def test_rename_to_existing_name_rejected(self, user_id):
        await svc.create_workspace(user_id, "taken")
        ws = await svc.create_workspace(user_id, "free")
        with pytest.raises(DuplicateError):
            await svc.rename_workspace(user_id, ws["id"], "taken")

    async def test_rename_other_users_workspace_404(self, user_id, other_user_id):
        ws = await svc.create_workspace(other_user_id, "theirs")
        with pytest.raises(NotFoundError):
            await svc.rename_workspace(user_id, ws["id"], "hijack")

    async def test_delete_cascades(self, user_id):
        ws = await svc.create_workspace(user_id, "temp")
        doc = await svc.save_document(
            user_id, ws["id"], "d", [{"label": "v1", "content": {"a": 1}}]
        )
        await svc.delete_workspace(user_id, ws["id"])
        assert await svc.list_workspaces(user_id) == []
        # Document is gone with it.
        with pytest.raises(NotFoundError):
            await svc.get_document(user_id, ws["id"], doc["id"])

    async def test_delete_default_blocked(self, user_id):
        await svc.ensure_default_workspace(user_id)
        ws = (await svc.list_workspaces(user_id))[0]
        with pytest.raises(ConflictError):
            await svc.delete_workspace(user_id, ws["id"])

    async def test_delete_other_users_404(self, user_id, other_user_id):
        ws = await svc.create_workspace(other_user_id, "theirs")
        with pytest.raises(NotFoundError):
            await svc.delete_workspace(user_id, ws["id"])

    async def test_malformed_uuid_is_404_not_500(self, user_id):
        with pytest.raises(NotFoundError):
            await svc.rename_workspace(user_id, "not-a-uuid", "x")


# ---------------------------------------------------------------------------
# Documents (J-02 .. J-05)
# ---------------------------------------------------------------------------


class TestDocuments:
    async def test_save_numbers_versions_sequentially(self, user_id):
        ws = await svc.create_workspace(user_id, "w")
        doc = await svc.save_document(
            user_id,
            ws["id"],
            "cfg",
            [
                {"label": "v1", "content": {"n": 1}},
                {"label": "v2", "content": {"n": 2}},
            ],
        )
        assert doc["version_count"] == 2
        assert doc["latest_version_number"] == 2
        detail = await svc.get_document(user_id, ws["id"], doc["id"])
        assert [v["version_number"] for v in detail["versions"]] == [1, 2]
        assert [v["content"]["n"] for v in detail["versions"]] == [1, 2]

    async def test_duplicate_tag_same_workspace_rejected(self, user_id):
        ws = await svc.create_workspace(user_id, "w")
        await svc.save_document(
            user_id, ws["id"], "tag", [{"label": "a", "content": {}}]
        )
        with pytest.raises(DuplicateError):
            await svc.save_document(
                user_id, ws["id"], "tag", [{"label": "b", "content": {}}]
            )

    async def test_same_tag_different_workspace_allowed(self, user_id):
        w1 = await svc.create_workspace(user_id, "w1")
        w2 = await svc.create_workspace(user_id, "w2")
        await svc.save_document(
            user_id, w1["id"], "shared", [{"label": "a", "content": {}}]
        )
        doc2 = await svc.save_document(
            user_id, w2["id"], "shared", [{"label": "a", "content": {}}]
        )
        assert doc2["tag"] == "shared"

    async def test_document_limit_blocks(self, user_id, monkeypatch):
        _set_limits(monkeypatch, jsons=2)
        ws = await svc.create_workspace(user_id, "w")
        await svc.save_document(
            user_id, ws["id"], "d1", [{"label": "a", "content": {}}]
        )
        await svc.save_document(
            user_id, ws["id"], "d2", [{"label": "a", "content": {}}]
        )
        with pytest.raises(LimitExceededError) as exc:
            await svc.save_document(
                user_id, ws["id"], "d3", [{"label": "a", "content": {}}]
            )
        assert exc.value.detail["limit_type"] == "jsons"
        # The blocked doc was not written.
        assert len(await svc.list_documents(user_id, ws["id"])) == 2

    async def test_save_over_version_limit_rejected(self, user_id, monkeypatch):
        _set_limits(monkeypatch, versions=2)
        ws = await svc.create_workspace(user_id, "w")
        with pytest.raises(LimitExceededError) as exc:
            await svc.save_document(
                user_id,
                ws["id"],
                "big",
                [{"label": str(i), "content": {"i": i}} for i in range(3)],
            )
        assert exc.value.detail["limit_type"] == "versions"
        assert len(await svc.list_documents(user_id, ws["id"])) == 0

    async def test_list_documents_counts(self, user_id):
        ws = await svc.create_workspace(user_id, "w")
        doc = await svc.save_document(
            user_id,
            ws["id"],
            "d",
            [{"label": "a", "content": {}}, {"label": "b", "content": {}}],
        )
        rows = await svc.list_documents(user_id, ws["id"])
        assert rows[0]["id"] == doc["id"]
        assert rows[0]["version_count"] == 2
        assert rows[0]["latest_version_number"] == 2

    async def test_get_document_other_user_404(self, user_id, other_user_id):
        ws = await svc.create_workspace(other_user_id, "theirs")
        doc = await svc.save_document(
            other_user_id, ws["id"], "d", [{"label": "a", "content": {}}]
        )
        with pytest.raises(NotFoundError):
            await svc.get_document(user_id, ws["id"], doc["id"])

    async def test_rename_tag(self, user_id):
        ws = await svc.create_workspace(user_id, "w")
        doc = await svc.save_document(
            user_id, ws["id"], "old-tag", [{"label": "a", "content": {}}]
        )
        out = await svc.rename_document(user_id, ws["id"], doc["id"], "new-tag")
        assert out["tag"] == "new-tag"

    async def test_rename_tag_duplicate_rejected(self, user_id):
        ws = await svc.create_workspace(user_id, "w")
        await svc.save_document(
            user_id, ws["id"], "taken", [{"label": "a", "content": {}}]
        )
        doc = await svc.save_document(
            user_id, ws["id"], "free", [{"label": "a", "content": {}}]
        )
        with pytest.raises(DuplicateError):
            await svc.rename_document(user_id, ws["id"], doc["id"], "taken")

    async def test_delete_document_cascades_versions(self, user_id):
        ws = await svc.create_workspace(user_id, "w")
        doc = await svc.save_document(
            user_id,
            ws["id"],
            "d",
            [{"label": "a", "content": {}}, {"label": "b", "content": {}}],
        )
        await svc.delete_document(user_id, ws["id"], doc["id"])
        assert await svc.list_documents(user_id, ws["id"]) == []


# ---------------------------------------------------------------------------
# Versions — append / delete (V-01, V-02, DB-06)
# ---------------------------------------------------------------------------


class TestVersions:
    async def test_append_continues_numbering(self, user_id):
        ws = await svc.create_workspace(user_id, "w")
        doc = await svc.save_document(
            user_id, ws["id"], "d", [{"label": "v1", "content": {"n": 1}}]
        )
        created = await svc.append_versions(
            user_id, ws["id"], doc["id"], [{"label": "v2", "content": {"n": 2}}]
        )
        assert [v["version_number"] for v in created] == [2]
        detail = await svc.get_document(user_id, ws["id"], doc["id"])
        assert [v["version_number"] for v in detail["versions"]] == [1, 2]

    async def test_append_over_limit_writes_nothing(self, user_id, monkeypatch):
        _set_limits(monkeypatch, versions=2)
        ws = await svc.create_workspace(user_id, "w")
        doc = await svc.save_document(
            user_id, ws["id"], "d", [{"label": "v1", "content": {}}]
        )
        with pytest.raises(LimitExceededError) as exc:
            await svc.append_versions(
                user_id,
                ws["id"],
                doc["id"],
                [{"label": "v2", "content": {}}, {"label": "v3", "content": {}}],
            )
        assert exc.value.detail["limit_type"] == "versions"
        detail = await svc.get_document(user_id, ws["id"], doc["id"])
        assert len(detail["versions"]) == 1  # nothing appended

    async def test_deleted_top_number_not_reused(self, user_id):
        """DB-06: high-water mark, not MAX(surviving), drives the next number."""
        ws = await svc.create_workspace(user_id, "w")
        doc = await svc.save_document(
            user_id,
            ws["id"],
            "d",
            [
                {"label": "v1", "content": {"n": 1}},
                {"label": "v2", "content": {"n": 2}},
            ],
        )
        detail = await svc.get_document(user_id, ws["id"], doc["id"])
        v2_id = detail["versions"][1]["id"]
        await svc.delete_version(user_id, ws["id"], doc["id"], v2_id)
        # Next append must be #3, not a reused #2.
        created = await svc.append_versions(
            user_id, ws["id"], doc["id"], [{"label": "v3", "content": {"n": 3}}]
        )
        assert created[0]["version_number"] == 3

    async def test_delete_version_frees_slot(self, user_id):
        ws = await svc.create_workspace(user_id, "w")
        doc = await svc.save_document(
            user_id,
            ws["id"],
            "d",
            [{"label": "v1", "content": {}}, {"label": "v2", "content": {}}],
        )
        detail = await svc.get_document(user_id, ws["id"], doc["id"])
        await svc.delete_version(
            user_id, ws["id"], doc["id"], detail["versions"][0]["id"]
        )
        after = await svc.get_document(user_id, ws["id"], doc["id"])
        assert [v["version_number"] for v in after["versions"]] == [2]

    async def test_delete_last_version_blocked(self, user_id):
        ws = await svc.create_workspace(user_id, "w")
        doc = await svc.save_document(
            user_id, ws["id"], "d", [{"label": "only", "content": {}}]
        )
        detail = await svc.get_document(user_id, ws["id"], doc["id"])
        with pytest.raises(ConflictError):
            await svc.delete_version(
                user_id, ws["id"], doc["id"], detail["versions"][0]["id"]
            )

    async def test_delete_version_bad_uuid_404(self, user_id):
        ws = await svc.create_workspace(user_id, "w")
        doc = await svc.save_document(
            user_id,
            ws["id"],
            "d",
            [{"label": "a", "content": {}}, {"label": "b", "content": {}}],
        )
        with pytest.raises(NotFoundError):
            await svc.delete_version(user_id, ws["id"], doc["id"], "not-a-uuid")

    async def test_delete_nonexistent_version_404(self, user_id):
        ws = await svc.create_workspace(user_id, "w")
        doc = await svc.save_document(
            user_id,
            ws["id"],
            "d",
            [{"label": "a", "content": {}}, {"label": "b", "content": {}}],
        )
        with pytest.raises(NotFoundError):
            await svc.delete_version(user_id, ws["id"], doc["id"], str(uuid.uuid4()))


# ---------------------------------------------------------------------------
# No-DB mode (A-02)
# ---------------------------------------------------------------------------


class TestNoDatabase:
    async def test_service_503_without_database(self, monkeypatch):
        """No configured factory → 503, not a crash (anonymous mode)."""
        from src.json_ai_studio.db import database as db_mod

        monkeypatch.setattr(db_mod, "_session_factory", None)
        with pytest.raises(HTTPException) as exc:
            await svc.list_workspaces(uuid.uuid4())
        assert exc.value.status_code == 503
