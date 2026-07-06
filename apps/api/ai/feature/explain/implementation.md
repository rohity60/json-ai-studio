# JSON AI Studio — Explain Feature Implementation Guide

**Feature branch:** `explain-feature`
**Requirements:** `requirements.md`

---

## 1. Architecture

```
POST /api/explain
  → Session lookup (get_session)
  → GatewayService.explain(session_id, api_key, working_json)
    → DeploymentRegistry.pick(model)
    → litellm.acompletion(system_prompt=EXPLAIN_TEMPLATE, user="")
    → Stream chunks → collect string
    → Deduct credits, log usage
  → Return 200 text/plain markdown
```

**Key principle:** `GatewayService.explain()` is a thin wrapper around `invoke()`. It streams the LLM response internally, collects all content into a single string, then returns it. The HTTP endpoint is a simple non-streaming endpoint.

---

## 2. Component Details

### 2.1 `prompting.py` — Add `EXPLAIN_TEMPLATE`

**Location:** `apps/api/src/json_ai_studio/prompting.py`
**Action:** Append to end of file.

```python
EXPLAIN_TEMPLATE = """\
You are a JSON explanation engine. The user has uploaded a JSON document and wants
to understand what it represents, its structure, and important details.

Explain this JSON as if helping a developer understand it for the first time.

Respond with markdown sections in this exact order:

## Summary
One paragraph describing what this JSON represents at a high level (e.g., "This JSON represents an ecommerce order with customer details, shipping information, line items, and payment data.").

## What this JSON represents
2-3 sentences about the domain, purpose, and likely source of this JSON (API response, config file, log, etc.).

## Main Objects
Bullet list of top-level keys and what each one represents.

## Relationships
Describe how the main objects relate to each other (e.g., "customer.id matches the customerId field in orders").

## Important Fields
List key fields with their types and typical values. Note any nested structures.

## Interesting Observations
Highlight notable patterns: array lengths, computed totals, missing optional fields,
enum values, unusual nesting, or domain-specific insights.

## Potential Issues
Flag missing required fields, suspicious values, empty arrays, or potential data quality concerns.

## Suggested Next Questions
3-5 follow-up questions a developer might ask (e.g., "What does the customer object contain?", "Show payment flow", "Find nullable fields").

Do NOT use markdown code fences. Output raw markdown only.
"""
```

### 2.2 `gateway.py` — Add `GatewayService.explain()`

**Location:** `apps/api/src/json_ai_studio/gateway.py`
**Action:** Add new classmethod before `get_usage()`.

```python
@classmethod
def explain(cls, session_id: str, api_key: str, working_json: dict[str, Any]) -> str:
    """Explain a JSON document. Calls LLM, collects response, returns markdown string.

    This is a thin wrapper around invoke(): streams content, deducts credits,
    then returns the combined markdown as a plain string.
    """
    resolved_model = cls._resolve_model(None, None)
    cls._ensure_credits(api_key)
    cls._check_credits(api_key)

    deployment = DeploymentRegistry.pick(resolved_model)
    litellm_model = (
        resolved_model
        if resolved_model.startswith(deployment.model_prefix)
        else f"{deployment.model_prefix}{resolved_model}"
    )

    system_prompt = EXPLAIN_TEMPLATE  # imported from prompting

    content_parts: list[str] = []
    last_chunk = None

    async for chunk in litellm.acompletion(
        model=litellm_model,
        base_url=deployment.base_url,
        api_key=deployment.api_key or None,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": ""},
        ],
        stream=True,
        reasoning_effort="default",
        timeout=120.0,
        stream_options={"include_usage": True},
    ):
        last_chunk = chunk
        if not getattr(chunk, "choices", None):
            continue
        delta = chunk.choices[0].delta
        text = getattr(delta, "content", None) if isinstance(delta, dict) else delta.get("content") if isinstance(delta, dict) else None
        if text:
            content_parts.append(text)

    combined = "".join(content_parts)

    # Usage tracking (same pattern as invoke)
    prompt_tokens = 0
    completion_tokens = 0
    if last_chunk is not None:
        chunk_usage = getattr(last_chunk, "usage", None)
        if chunk_usage is not None:
            if isinstance(chunk_usage, dict):
                prompt_tokens = chunk_usage.get("prompt_tokens", 0) or 0
                completion_tokens = chunk_usage.get("completion_tokens", 0) or 0
            else:
                try:
                    usage_dict = vars(chunk_usage)
                    prompt_tokens = usage_dict.get("prompt_tokens", 0) or 0
                    completion_tokens = usage_dict.get("completion_tokens", 0) or 0
                except Exception:
                    pass

    cost_usd = cls._calculate_cost(prompt_tokens, completion_tokens, resolved_model)
    credits_used = cls._calculate_credits(cost_usd)
    total_tokens = prompt_tokens + completion_tokens
    cls._deduct_credits(api_key, credits_used, total_tokens)
    cls._log_usage(
        session_id,
        api_key,
        {
            "request_id": uuid.uuid4().hex,
            "api_key": api_key,
            "session_id": session_id,
            "model": resolved_model,
            "provider": "ollama",
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
            "cost_usd": cost_usd,
            "credits_used": credits_used,
            "feature": "explain-json",
            "status": "success",
        },
    )

    return combined
```

**Note:** The `explain()` method duplicates the credit deduction / usage logging pattern from `invoke()`. This is intentional for MVP — no refactoring of `invoke()` into smaller pieces. The duplication is documented as technical debt.

### 2.3 `main.py` — Add `POST /api/explain` Endpoint

**Location:** `apps/api/src/json_ai_studio/main.py`
**Action:** Add before the diff accept/reject section (around line 500).

```python
@app.post("/api/explain")
async def endpoint_explain(
    body: dict[str, Any],
    _auth=Depends(require_api_key),
):
    """Explain the JSON in a session. Returns markdown as plain text."""
    session_id = body.get("sessionId")
    if not session_id:
        raise HTTPException(status_code=400, detail="sessionId is required")

    session = get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    working_json = body.get("workingJson", session.get("working_json", {}))
    if not isinstance(working_json, dict):
        working_json = {}

    try:
        markdown = GatewayService.explain(session_id, _auth, working_json)
    except Exception as e:
        logger.exception("explain failed session=%s", session_id)
        raise HTTPException(status_code=500, detail=f"Explain failed: {e}")

    return Response(content=markdown, media_type="text/plain")
```

**Imports needed:**
- `from fastapi.responses import Response` (already imported as `StreamingResponse`, add `Response`)
- `from typing import Any` (already imported)

### 2.4 `prompting.py` — Import Statement

In `main.py`, add import for `EXPLAIN_TEMPLATE`:
```python
from .prompting import build_system_prompt, EXPLAIN_TEMPLATE
```

---

## 3. Data Flow

### 3.1 Happy Path

```
1. Frontend: POST /api/explain {sessionId: "abc", workingJson: {...}}
2. Endpoint: get_session("abc") → session dict
3. GatewayService.explain("abc", api_key, working_json)
4. DeploymentRegistry.pick("ollama/gemma4:12b") → deployment config
5. litellm.acompletion(system=EXPLAIN_TEMPLATE, user="") → stream
6. Collect chunks: "## Summary\nThis JSON represents...\n## Main Objects\n- customer\n..."
7. Deduct credits, log usage with feature="explain-json"
8. Return Response(content=markdown, media_type="text/plain")
```

### 3.2 Session Not Found

```
1. POST /api/explain {sessionId: "invalid"}
2. get_session("invalid") → None
3. Return 404 {"detail": "Session not found"}
```

### 3.3 LLM Error

```
1. POST /api/explain valid session
2. litellm.acompletion() raises exception
3. GatewayService.explain() propagates exception
4. Endpoint catches → 500 {"detail": "Explain failed: <error>"}
```

---

## 4. Error Handling

| Error | When | Response |
|-------|------|----------|
| `400` | Missing `sessionId` in body | `{"detail": "sessionId is required"}` |
| `404` | Session not found | `{"detail": "Session not found"}` |
| `401` | Invalid API key | Handled by `require_api_key` auth middleware |
| `429` | Rate limit exceeded | Handled by rate limiter |
| `500` | LLM call fails | `{"detail": "Explain failed: <error>"}` |

---

## 5. Assumptions & Constraints

1. **Non-streaming HTTP response.** The LLM call is internally streamed, but the HTTP response to the frontend is a single block. No SSE on the explain endpoint.
2. **Ephemeral explanations.** Explanations are not stored in session state. They are generated on-demand.
3. **Same credit system.** Explain uses the same credit deduction / usage logging as chat.
4. **No new models.** Uses the default model from `AI_PROFILES["balanced"]` (or `ollama/gemma4:12b`).
5. **`reasoning_effort="default"`** for explain (vs `"none"` for chat). Higher reasoning budget per PRD.
6. **Markdown output.** The LLM returns raw markdown. No code fences. No post-processing.
7. **Duplication accepted.** `explain()` duplicates credit deduction logic from `invoke()`. Refactor later.

---

## 6. Files Modified

| File | Action | Change |
|------|--------|--------|
| `apps/api/src/json_ai_studio/prompting.py` | **MODIFIED** | Append `EXPLAIN_TEMPLATE` string |
| `apps/api/src/json_ai_studio/gateway.py` | **MODIFIED** | Add `GatewayService.explain()` classmethod |
| `apps/api/src/json_ai_studio/main.py` | **MODIFIED** | Add `POST /api/explain` endpoint |

**No changes to:** `models.py`, `store.py`, `auth.py`, `utils.py`, `deployment.py`.

---

## 7. Verification

### Manual Tests

1. **Happy path:** Upload JSON. Call `POST /api/explain` with session ID. Verify 200 response with markdown starting with `## Summary`.
2. **Session not found:** Call with invalid session ID. Verify 404.
3. **Missing sessionId:** Call with empty body. Verify 400.
4. **Credits deducted:** Check `_user_credits` after explain call. Verify credits decreased.
5. **Usage logged:** Check `_usage_history[sessionId]`. Verify entry with `feature: "explain-json"`.
6. **Large JSON:** Upload large JSON (>60k chars). Verify explain still works (uses schema summary fallback).

---

*End of implementation guide. Feature branch: `explain-feature`.*
