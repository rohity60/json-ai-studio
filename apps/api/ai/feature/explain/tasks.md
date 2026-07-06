# Explain Feature — Task List

**Feature branch:** `explain-feature`
**Requirements:** `requirements.md`
**Implementation:** `implementation.md`

---

## Tasks

| # | Task | Status |
|---|------|--------|
| 1 | Add `EXPLAIN_TEMPLATE` to `apps/api/src/json_ai_studio/prompting.py` — markdown sections: Summary, What this JSON represents, Main Objects, Relationships, Important Fields, Interesting Observations, Potential Issues, Suggested Next Questions | pending |
| 2 | Add `GatewayService.explain()` to `apps/api/src/json_ai_studio/gateway.py` — classmethod that calls `litellm.acompletion()` with EXPLAIN_TEMPLATE, collects chunks, deducts credits, returns markdown string | pending |
| 3 | Add `POST /api/explain` endpoint to `apps/api/src/json_ai_studio/main.py` — accepts `{sessionId, workingJson}`, calls `GatewayService.explain()`, returns `Response(content=markdown, media_type="text/plain")` | pending |
| 4 | Verify — run server, upload JSON, call `POST /api/explain` via Swagger or curl, verify markdown response | pending |

---

*Total: 4 tasks. Sequential: 1→2→3→4.*
