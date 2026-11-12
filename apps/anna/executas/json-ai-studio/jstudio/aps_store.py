"""SessionStore backed by Anna Persistent Storage (APS).

Each Anna user gets their own bucket, enforced by the host through the
per-invoke ``storage_token`` — there is no user id on our side.

Layout (scope ``app``: this user × the JSON AI Studio app — the bucket the
host attests for invokes coming from the app's own window, and the only
one that needs no ``storage.scopes`` declaration in the app manifest):

- ``sessions/index``  KV  ``{session_id: {"name", "updated_at"}}``
- ``sessions/<id>``   KV  ``{"inline": <session>}`` for small sessions, or
                          ``{"file": "sessions/<id>.json"}`` for large ones
- ``sessions/<id>.json``  object holding the session JSON (large sessions)

KV values are capped around 64 KB, so anything bigger goes to the object
store: upload_begin → HTTP PUT to the presigned URL → upload_complete.
"""

from __future__ import annotations

import json
import logging
from datetime import date, datetime, timezone
from typing import Any
from uuid import uuid4

import httpx

from json_ai_studio.db.session_store import SessionStore

from .rpc import HostRpc, host

logger = logging.getLogger("jstudio.aps_store")

SCOPE = "app"
INDEX_KEY = "sessions/index"
# Stay well under the ~64 KB KV cap (the envelope adds a little).
INLINE_MAX_BYTES = 48 * 1024
HTTP_TIMEOUT_S = 60.0


def _jsonable(value: Any) -> Any:
    """Sessions hold pydantic snapshots and datetimes; store plain JSON."""
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    raise TypeError(f"not JSON serializable: {type(value).__name__}")


def _dumps(session: dict[str, Any]) -> str:
    return json.dumps(session, ensure_ascii=False, default=_jsonable)


def _key(session_id: str) -> str:
    return f"sessions/{session_id}"


def _path(session_id: str) -> str:
    return f"sessions/{session_id}.json"


class ApsSessionStore(SessionStore):
    def __init__(
        self,
        rpc: HostRpc | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._rpc = rpc or host
        self._transport = transport  # test seam for the presigned-URL calls

    def _http(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(timeout=HTTP_TIMEOUT_S, transport=self._transport)

    # --- KV / object helpers -------------------------------------------

    async def _get(self, key: str) -> dict[str, Any]:
        cur = await self._rpc.call("storage/get", {"scope": SCOPE, "key": key})
        logger.debug("storage/get key=%s keys=%s", key, sorted(cur))
        # Older hosts (and the local harness's in-memory backend) omit
        # `exists`: a non-null value then means the key is there.
        if "exists" not in cur:
            cur = {**cur, "exists": cur.get("value") is not None}
        return cur

    async def _set(self, key: str, value: Any) -> None:
        await self._rpc.call(
            "storage/set", {"scope": SCOPE, "key": key, "value": value}
        )

    async def _put_object(self, path: str, body: bytes) -> None:
        begin = await self._rpc.call(
            "files/upload_begin",
            {
                "scope": SCOPE,
                "path": path,
                "size_bytes": len(body),
                "content_type": "application/json",
            },
        )
        url = begin.get("put_url") or begin.get("presigned_url")
        if not url:
            raise RuntimeError("files/upload_begin returned no upload URL")
        async with self._http() as client:
            resp = await client.put(
                url, content=body, headers=begin.get("headers") or {}
            )
            resp.raise_for_status()
        await self._rpc.call(
            "files/upload_complete",
            {
                "scope": SCOPE,
                "path": path,
                "etag": resp.headers.get("etag"),
                "size_bytes": len(body),
            },
        )

    async def _get_object(self, path: str) -> bytes:
        res = await self._rpc.call("files/download_url", {"scope": SCOPE, "path": path})
        url = res.get("url") or res.get("get_url")
        if not url:
            raise RuntimeError("files/download_url returned no URL")
        async with self._http() as client:
            resp = await client.get(url)
            resp.raise_for_status()
            return resp.content

    async def _index(self) -> dict[str, Any]:
        cur = await self._get(INDEX_KEY)
        value = cur.get("value") if cur.get("exists") else None
        return value if isinstance(value, dict) else {}

    # --- SessionStore ---------------------------------------------------

    async def create_session(self, *, name: str | None = None) -> dict[str, Any]:
        now = datetime.now(timezone.utc).isoformat()
        session: dict[str, Any] = {
            "id": uuid4().hex,
            "name": name,
            "working_json": {},
            "baseline_json": {},
            "versions": [],
            "conversation_history": [],
            "applied_diffs": [],
            "rejected_diffs": [],
            "active_version_id": None,
            "created_at": now,
            "updated_at": now,
        }
        await self.save_session(session)
        return session

    async def get_session(self, session_id: str) -> dict[str, Any] | None:
        cur = await self._get(_key(session_id))
        record = cur.get("value") if cur.get("exists") else None
        if not isinstance(record, dict):
            return None
        if "inline" in record:
            return record["inline"]
        if record.get("file"):
            return json.loads(await self._get_object(record["file"]))
        return None

    async def save_session(self, session: dict[str, Any]) -> None:
        sid = session["id"]
        body = _dumps(session).encode("utf-8")
        if len(body) <= INLINE_MAX_BYTES:
            await self._set(_key(sid), {"inline": json.loads(body)})
        else:
            # Object first, pointer second: a reader never sees a pointer
            # to an object that is not there yet.
            await self._put_object(_path(sid), body)
            await self._set(_key(sid), {"file": _path(sid), "size_bytes": len(body)})
        index = await self._index()
        index[sid] = {
            "name": session.get("name"),
            "updated_at": session.get("updated_at"),
            "size_bytes": len(body),
        }
        await self._set(INDEX_KEY, index)
        logger.debug("session saved id=%s bytes=%d", sid, len(body))

    async def list_sessions(self) -> list[str]:
        return list(await self._index())

    async def list_summaries(self) -> list[dict[str, Any]]:
        """Id, name and last update of every session, newest first."""
        items = [{"id": sid, **meta} for sid, meta in (await self._index()).items()]
        return sorted(items, key=lambda i: i.get("updated_at") or "", reverse=True)

    async def delete_session(self, session_id: str) -> bool:
        index = await self._index()
        existed = index.pop(session_id, None) is not None
        cur = await self._get(_key(session_id))
        record = cur.get("value") if cur.get("exists") else None
        if isinstance(record, dict) and record.get("file"):
            await self._rpc.call(
                "files/delete", {"scope": SCOPE, "path": record["file"]}
            )
        await self._rpc.call(
            "storage/delete", {"scope": SCOPE, "key": _key(session_id)}
        )
        await self._set(INDEX_KEY, index)
        return existed
