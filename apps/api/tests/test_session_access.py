"""Session ownership (ADR-0027): owner-only access, claiming, admin key,
masked emails in logs. Stubbed: no LLM, no database, no live Auth0."""

from __future__ import annotations

import json
import logging
import uuid

import pytest

from src.json_ai_studio.auth import anon_owner, mask_email
from src.json_ai_studio.db.session_store import store
from src.json_ai_studio.services import user_service
from src.json_ai_studio.settings import get_settings

DOC = {"name": "doc", "entries": [{"id": i, "content": "teh text"} for i in range(3)]}
NOT_FOUND = "Session not found"


def key() -> dict[str, str]:
    return {"X-API-Key": f"test-{uuid.uuid4().hex}"}


class _Records(logging.Handler):
    def __init__(self) -> None:
        super().__init__(level=logging.DEBUG)
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)

    def text(self) -> str:
        return "\n".join(r.getMessage() for r in self.records)


@pytest.fixture
def logs():
    """App loggers do not propagate to root (ADR-0017), so caplog sees
    nothing: attach a handler to the package logger instead."""
    handler = _Records()
    pkg = logging.getLogger("json_ai_studio")
    old_level = pkg.level
    pkg.addHandler(handler)
    pkg.setLevel(logging.DEBUG)
    yield handler
    pkg.removeHandler(handler)
    pkg.setLevel(old_level)


@pytest.fixture
def client(monkeypatch):
    from fastapi.testclient import TestClient

    from src.json_ai_studio.main import app

    monkeypatch.setenv("ANON_REQUESTS_PER_MINUTE", "10000")
    monkeypatch.setenv("USER_REQUESTS_PER_MINUTE", "10000")
    get_settings.cache_clear()
    with TestClient(app) as c:
        yield c


def new_session(client, headers) -> str:
    sid = client.post("/api/sessions", json={"name": "t"}, headers=headers).json()["id"]
    resp = client.post(
        "/api/json/upload",
        files={"json_body": (None, json.dumps(DOC)), "session_id": (None, sid)},
        headers=headers,
    )
    assert resp.status_code == 200 and resp.json()["session_id"] == sid
    return sid


def session_routes(sid: str, job_id: str) -> list[tuple[str, str, dict]]:
    """Every session-scoped route, with a valid-looking request body."""
    base = f"/api/sessions/{sid}"
    return [
        ("GET", base, {}),
        ("DELETE", f"{base}/chat", {}),
        ("GET", f"{base}/versions", {}),
        ("POST", f"{base}/versions", {"json": {"label": "x", "json_data": {}}}),
        ("POST", f"{base}/versions/select", {"json": {"versionId": "v1"}}),
        ("POST", f"{base}/versions/restore", {"json": {"versions": []}}),
        ("POST", f"{base}/diffs/accept-all", {}),
        ("POST", f"{base}/diffs/reject-all", {}),
        ("POST", f"{base}/diffs/d1/accept", {}),
        ("POST", f"{base}/diffs/d1/reject", {}),
        (
            "POST",
            f"{base}/jobs",
            {"json": {"scope_path": "/entries", "instruction": "fix"}},
        ),
        ("GET", f"{base}/jobs/{job_id}", {}),
        ("DELETE", f"{base}/jobs/{job_id}", {}),
        ("POST", f"{base}/jobs/{job_id}/next", {}),
        ("POST", "/api/chat", {"data": {"session_id": sid, "message": "hi"}}),
        ("POST", "/api/explain", {"json": {"sessionId": sid}}),
    ]


class TestOwnerOnly:
    def test_other_key_gets_404_on_every_session_route(self, client):
        owner = key()
        sid = new_session(client, owner)
        job = client.post(
            f"/api/sessions/{sid}/jobs",
            json={"scope_path": "/entries", "instruction": "fix"},
            headers=owner,
        )
        assert job.status_code == 201, job.text
        job_id = job.json()["id"]
        before = json.loads(json.dumps(store._sessions[sid]))

        stranger = key()
        for method, path, kwargs in session_routes(sid, job_id):
            resp = client.request(method, path, headers=stranger, **kwargs)
            assert resp.status_code == 404, (method, path, resp.text)
            assert resp.json()["detail"] == NOT_FOUND, (method, path)

        # Nothing the stranger sent changed the session.
        assert store._sessions[sid] == before

    def test_foreign_and_unknown_ids_look_the_same(self, client):
        sid = new_session(client, key())
        stranger = key()
        foreign = client.get(f"/api/sessions/{sid}", headers=stranger)
        unknown = client.get(f"/api/sessions/{uuid.uuid4().hex}", headers=stranger)
        assert foreign.status_code == unknown.status_code == 404
        assert foreign.json() == unknown.json()

    def test_owner_keeps_access(self, client):
        owner = key()
        sid = new_session(client, owner)
        resp = client.get(f"/api/sessions/{sid}", headers=owner)
        assert resp.status_code == 200
        assert resp.json()["working_json"] == DOC
        assert "owner" not in resp.json()
        assert (
            client.post(
                f"/api/sessions/{sid}/versions",
                json={"label": "v", "json_data": DOC},
                headers=owner,
            ).status_code
            == 200
        )
        assert (
            client.get(f"/api/sessions/{sid}/versions", headers=owner).json()["count"]
            == 1
        )

    def test_owner_is_a_digest_not_the_key(self, client):
        owner = key()
        sid = new_session(client, owner)
        stored = store._sessions[sid]["owner"]
        assert stored == anon_owner(owner["X-API-Key"])
        assert owner["X-API-Key"] not in stored

    def test_upload_to_foreign_id_lands_in_new_session(self, client):
        owner = key()
        sid = new_session(client, owner)
        stranger = key()
        resp = client.post(
            "/api/json/upload",
            files={
                "json_body": (None, json.dumps({"evil": True})),
                "session_id": (None, sid),
            },
            headers=stranger,
        )
        assert resp.status_code == 200
        new_sid = resp.json()["session_id"]
        assert new_sid != sid
        assert store._sessions[sid]["working_json"] == DOC
        assert (
            client.get(f"/api/sessions/{new_sid}", headers=stranger).status_code == 200
        )

    def test_template_session_belongs_to_creator(self, client):
        owner = key()
        resp = client.post(
            "/api/sessions/from-template",
            json={"templateSlug": "t", "json_doc": {"a": 1}},
            headers=owner,
        )
        assert resp.status_code == 201, resp.text
        sid = resp.json()["id"]
        assert "owner" not in resp.json()
        assert client.get(f"/api/sessions/{sid}", headers=owner).status_code == 200
        assert client.get(f"/api/sessions/{sid}", headers=key()).status_code == 404


@pytest.fixture
def user(auth0_mock, monkeypatch):
    """Bearer token for a fake user; the DB upsert is stubbed out."""

    class _User:
        id = uuid.uuid4()
        email = "rohit@gmail.com"

    async def fake_upsert(claims, token):
        return _User()

    monkeypatch.setattr(user_service, "upsert_from_claims", fake_upsert)
    return {"Authorization": f"Bearer {auth0_mock(sub='auth0|claimer')}"}


class TestClaiming:
    def test_bearer_alone_cannot_open_anonymous_session(self, client, user):
        sid = new_session(client, key())
        assert client.get(f"/api/sessions/{sid}", headers=user).status_code == 404

    def test_bearer_with_wrong_key_cannot_claim(self, client, user):
        sid = new_session(client, key())
        resp = client.get(f"/api/sessions/{sid}", headers={**user, **key()})
        assert resp.status_code == 404
        assert store._sessions[sid]["owner"].startswith("key:")

    def test_bearer_plus_original_key_claims(self, client, user):
        anon = key()
        sid = new_session(client, anon)

        resp = client.get(f"/api/sessions/{sid}", headers={**user, **anon})
        assert resp.status_code == 200
        assert store._sessions[sid]["owner"] == "user:auth0|claimer"

        # Now the user's: bearer alone works, the bare anonymous key does not.
        assert client.get(f"/api/sessions/{sid}", headers=user).status_code == 200
        assert client.get(f"/api/sessions/{sid}", headers=anon).status_code == 404

    def test_user_session_not_claimable_by_other_user(self, client, user, auth0_mock):
        sid = client.post("/api/sessions", json={"name": "u"}, headers=user).json()[
            "id"
        ]
        other = {"Authorization": f"Bearer {auth0_mock(sub='auth0|other')}"}
        resp = client.get(f"/api/sessions/{sid}", headers={**other, **key()})
        assert resp.status_code == 404
        assert store._sessions[sid]["owner"] == "user:auth0|claimer"


class TestAdminKey:
    def test_admin_key_opens_any_session_and_is_logged(self, client, monkeypatch, logs):
        monkeypatch.setenv("ADMIN_API_KEY", "support-key-0123456789")
        get_settings.cache_clear()
        sid = new_session(client, key())
        admin = {**key(), "X-Admin-Key": "support-key-0123456789"}
        resp = client.get(f"/api/sessions/{sid}", headers=admin)
        assert resp.status_code == 200
        assert any(
            r.levelno == logging.WARNING
            and "admin session access" in r.getMessage()
            and sid in r.getMessage()
            for r in logs.records
        )

    def test_wrong_admin_key_is_refused(self, client, monkeypatch):
        monkeypatch.setenv("ADMIN_API_KEY", "support-key-0123456789")
        get_settings.cache_clear()
        sid = new_session(client, key())
        bad = {**key(), "X-Admin-Key": "guess-guess-guess"}
        assert client.get(f"/api/sessions/{sid}", headers=bad).status_code == 404

    def test_admin_key_unset_means_no_bypass(self, client):
        sid = new_session(client, key())
        bad = {**key(), "X-Admin-Key": "anything-at-all"}
        assert client.get(f"/api/sessions/{sid}", headers=bad).status_code == 404


class TestMaskEmail:
    @pytest.mark.parametrize(
        "raw, masked",
        [
            ("rohit@gmail.com", "r***@g***.com"),
            ("a.b@mail.example.co.uk", "a***@m***.uk"),
            ("x@localhost", "x***@l***"),
            ("not-an-email", "***"),
            (None, "<none>"),
            ("", "<none>"),
        ],
    )
    def test_mask_email(self, raw, masked):
        assert mask_email(raw) == masked

    def test_emails_never_reach_logs(self, client, user, logs):
        resp = client.post("/api/sessions", json={"name": "u"}, headers=user)
        assert resp.status_code == 200
        text = logs.text()
        assert "principal resolved kind=user" in text
        assert "rohit@gmail.com" not in text
        assert "r***@g***.com" in text
