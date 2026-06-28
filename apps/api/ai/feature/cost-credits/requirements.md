# JSON AI Studio — AI Gateway & Cost Credits Feature

**Version:** 1.0
**Status:** Requirements
**Feature branch:** `cost-credits`
**Implementation file:** `apps/api/src/json_ai_studio/gateway.py` (new)

---

## 1. Objective

Add a centralized AI Gateway layer that calculates costs per LLM request, tracks credit consumption, and enforces subscription-based credit limits. The gateway becomes the single component that communicates with LiteLLM, inserting credit checks before inference and usage logging after.

---

## 2. Background

JSON AI Studio uses LiteLLM to call AI models (currently `ollama/qwen3.6:35b-mlx` via local Ollama). All AI calls happen inline in `main.py`'s `endpoint_chat()`. There is zero cost tracking, zero credit system, and zero usage analytics.

This feature adds:
- Per-request cost calculation from token counts
- Credit deduction from a user's monthly balance
- Usage history logging per session
- SSE `event: usage` with cost/credit metadata
- HTTP 402 when credits are exhausted
- HTTP 503 when all providers fail

---

## 3. Goals

### Functional
- Calculate cost per LLM request from token counts + pricing table
- Deduct credits from user's monthly balance
- Log usage per session (tokens, cost, model, latency)
- Return usage metadata in SSE stream (`event: usage`)
- Block requests when credits are exhausted (HTTP 402)
- Support multiple AI providers via LiteLLM model routing

### Non-Functional
- Gateway is an in-module service (`gateway.py`), not a separate service
- In-memory data store (matches ADR-0006 — no DB dependency)
- <10ms overhead for credit check + cost calculation
- Streaming-compatible: billing happens after stream completes, does not block SSE
- Thread-safe for in-memory dicts (assume single-threaded FastAPI dev server)

---

## 4. Architecture

```
main.py endpoint_chat()
    └── GatewayService.invoke(session_id, message, api_key, working_json)
            ├── 1. Validate API key → check credit balance
            ├── 2. Resolve AI profile → model string
            ├── 3. Call litellm.acompletion(model, messages, stream=True)
            ├── 4. Stream chunks → SSE events (thinking, diff)
            ├── 5. Extract response.usage (prompt_tokens, completion_tokens)
            ├── 6. Calculate cost_usd from tokens + MODEL_PRICING
            ├── 7. Convert cost → credits (credits = cost_usd / 0.001)
            ├── 8. Deduct credits from _user_credits[api_key]
            ├── 9. Log usage to _usage_history[session_id]
            └── 10. Emit event:usage + event:complete
```

**Key principle:** The gateway is a single class (`GatewayService`) with no inheritance. All state lives in module-level dicts. No external dependencies beyond what `main.py` already imports.

---

## 5. Components

### 5.1 `GatewayService` — Core Gateway Class

Single class, module-level singleton. All methods are `async`.

```python
class GatewayService:
    MODEL_PRICING: dict[str, tuple[float, float]]   # model → (prompt_per_1k, completion_per_1k) in USD
    AI_PROFILES: dict[str, str]                      # profile_name → model_string
    _user_credits: dict[str, dict]                   # api_key → {plan, monthly_limit, credits_used, billing_cycle_start}
    _usage_history: dict[str, list]                  # session_id → [usage_records]

    async invoke(session_id, message, api_key, working_json, model=None, profile=None) → AsyncGenerator
```

### 5.2 `MODEL_PRICING` — Token Pricing Table

Maps model strings to per-1K-token pricing in USD. Used when `response_cost` is unavailable (e.g., local models, unsupported providers).

```python
MODEL_PRICING = {
    "ollama/qwen3.6:35b-mlx": (0.0, 0.0),           # Local model — free
    "gpt-4.1":            (0.001, 0.004),            # OpenAI per 1K tokens
    "gpt-4.1-mini":       (0.0001, 0.0004),           # OpenAI per 1K tokens
    "claude-sonnet-4-20250514": (0.003, 0.015),       # Anthropic per 1K tokens
    "claude-haiku-4-20250514":  (0.00025, 0.00125),   # Anthropic per 1K tokens
    "gemini-2.0-flash":   (0.0001, 0.0003),           # Google per 1K tokens
}
```

**Rules:**
- Tuple format: `(prompt_per_1k_tokens, completion_per_1k_tokens)` in USD.
- If model not in table, default to `(0.0, 0.0)` — free. No error.
- `response_cost` from LiteLLM takes priority over pricing table lookup.

### 5.3 `AI_PROFILES` — Model Abstraction Layer

Maps user-facing profile names to actual model strings. Hides model details from users.

```python
AI_PROFILES = {
    "fast":     "ollama/qwen3.6:35b-mlx",              # Quick edits, low latency
    "balanced": "ollama/qwen3.6:35b-mlx",              # Default editing
    "premium":  "gpt-4.1",                              # Complex reasoning
}
```

**Rules:**
- Profile name comes from request (optional). Falls back to `"balanced"`.
- If profile not found, falls back to `"ollama/qwen3.6:35b-mlx"`.
- Profiles are configurable — add new entries without code changes.

### 5.4 `UserCredits` — Per-API-Key Credit State

In-memory dict tracking each API key's credit balance.

```python
# Structure per api_key
{
    "plan": "free",                                    # Subscription tier
    "monthly_limit": 100,                              # Credits per billing cycle
    "credits_used": 0,                                 # Running total in current cycle
    "billing_cycle_start": "2026-06-01T00:00:00Z",   # When cycle began
}
```

**Plans:**

| Plan | Monthly Credits | Models |
|------|----------------|--------|
| `free` | 100 | Community models (Ollama, local) |
| `pro` | 5,000 | Premium models (GPT-4, Claude) |
| `team` | 25,000 | All models + shared workspace |
| `enterprise` | -1 (unlimited) | All models + BYOK |

**Rules:**
- `monthly_limit = -1` means unlimited (enterprise).
- `credits_used` resets on `billing_cycle_start` + 30 days.
- New API keys default to `free` plan with 100 credits.
- Credit deduction is in-memory only — no persistence across restarts.

### 5.5 `UsageRecord` — Per-Request Usage Log

Each LLM invocation produces one usage record.

```python
{
    "request_id": "uuid-hex",
    "api_key": "key-hex",
    "session_id": "session-hex",
    "model": "ollama/qwen3.6:35b-mlx",
    "provider": "ollama",
    "prompt_tokens": 100,
    "completion_tokens": 50,
    "total_tokens": 150,
    "cost_usd": 0.00015,
    "credits_used": 0.15,
    "latency_ms": 2300,
    "feature": "modify-json",
    "status": "success",                             # "success" | "failed" | "timeout"
    "timestamp": "2026-06-28T12:00:00Z",
}
```

**Rules:**
- `request_id`: UUID hex, unique per invocation.
- `cost_usd`: 0.0 if local/free model.
- `credits_used`: `round(cost_usd / 0.001, 3)` — 3 decimal places.
- `latency_ms`: Wall-clock time for the full LLM call (not SSE streaming).
- `status`: `"success"` if LLM returns, `"failed"` if exception, `"timeout"` if 120s exceeded.
- Stored in `_usage_history[session_id]` list.

---

## 6. API Contract

### 6.1 SSE Stream Events (Modified)

The `event: chat` SSE stream gains a new `event: usage` event between the last `event: diff` and `event: complete`.

**New event sequence:**

```
event: thinking
data: {"text": "Analyzing your request..."}

event: diff
data: {"entry": {"path": "/services/api/timeout", "operation": "modify", "old_value": 30, "new_value": 60}}

event: usage                                          # NEW
data: {"cost_usd": 0.015, "credits_used": 15, "model": "gpt-4.1", "provider": "openai", "tokens": {"prompt": 100, "completion": 50}}

event: complete
data: {"working_json": {...}, "explanation": "Done."}
```

**`event: usage` payload:**

```json
{
    "cost_usd": 0.015,
    "credits_used": 15,
    "model": "gpt-4.1",
    "provider": "openai",
    "tokens": {
        "prompt": 100,
        "completion": 50,
        "total": 150
    }
}
```

**Rules:**
- `event: usage` is emitted only after the full LLM response is received.
- It does NOT block SSE — it is yielded like any other event.
- For failed requests (exception), `event: usage` is omitted. Instead, `event: complete` includes `"billing_error": true`.
- For free/local models (cost_usd = 0), `event: usage` still emits with `cost_usd: 0, credits_used: 0`.

### 6.2 Error Responses

**HTTP 402 Payment Required — Insufficient Credits:**

```json
{
    "error": "Insufficient credits",
    "hint": "Upgrade your plan. Current balance: 0 credits.",
    "required": 15,
    "current_balance": 0
}
```

- Returned when `user_credits[api_key].credits_used >= user_credits[api_key].monthly_limit`.
- No LLM call is made. Stream does not start.
- `required` field: estimated credits for the request (0 if unknown).

**HTTP 503 Service Unavailable — All Providers Failed:**

```json
{
    "error": "All AI providers unavailable",
    "hint": "LiteLLM exhausted all fallback providers. Try again later."
}
```

- Returned when LiteLLM raises after exhausting fallback providers.
- No credits are deducted for failed requests.
- Usage record is logged with `status: "failed"`.

**HTTP 429 Rate Limit — Gateway Level:**

```json
{
    "error": "Gateway rate limited",
    "hint": "10 LLM calls per minute per API key. LiteLLM rate limit applies separately."
}
```

- Separate from the existing API key rate limiter in `auth.py`.
- Gateway-level rate limit: 10 LLM calls per minute per API key.
- Does not consume credits (it blocks before the LLM call).

### 6.3 Usage History Endpoint (Future)

```
GET /api/usage?session_id=<id>
Response: { "records": [...], "total_cost_usd": 0.15, "total_credits_used": 150 }
```

- Returns usage records for a session.
- Aggregates total cost and total credits.
- Not yet implemented in MVP — listed for reference.

---

## 7. Data Flow

### 7.1 Successful Request

```
1. endpoint_chat(session_id, message, api_key)
2. → GatewayService.invoke(session_id, message, api_key, working_json)
3. → _user_credits[api_key]: credits_used (5) < monthly_limit (100) → OK
4. → litellm.acompletion(model="ollama/qwen3.6:35b-mlx", stream=True)
5. → Stream chunks → yield event:thinking (each chunk)
6. → Parse diffs → yield event:diff (each diff)
7. → response.usage: prompt_tokens=100, completion_tokens=50
8. → cost_usd = (100 * 0.0 / 1000) + (50 * 0.0 / 1000) = 0.0
9. → credits_used = 0.0 / 0.001 = 0.0
10. → _user_credits[api_key].credits_used += 0.0  (no change)
11. → usage_record = {...cost_usd: 0.0, credits_used: 0.0, ...}
12. → _usage_history[session_id].append(usage_record)
13. → yield event:usage {cost_usd: 0.0, credits_used: 0.0, ...}
14. → yield event:complete {working_json, explanation}
```

### 7.2 Insufficient Credits

```
1. endpoint_chat(session_id, message, api_key)
2. → GatewayService.invoke(session_id, message, api_key, working_json)
3. → _user_credits[api_key]: credits_used (100) >= monthly_limit (100) → FAIL
4. → raise HTTPException(402, {"error": "Insufficient credits", ...})
5. → No LLM call. No credits deducted. No usage log.
```

### 7.3 Provider Failure

```
1. endpoint_chat(session_id, message, api_key)
2. → GatewayService.invoke(session_id, message, api_key, working_json)
3. → _user_credits[api_key]: OK (credits available)
4. → litellm.acompletion(...) → raises Exception
5. → catch exception → yield event:complete {working_json, explanation: "Error: ..."}
6. → usage_record = {...status: "failed", cost_usd: 0.0}
7. → _usage_history[session_id].append(usage_record)
8. → No credits deducted (cost is 0)
```

---

## 8. Implementation Details

### 8.1 File Structure

```
apps/api/src/json_ai_studio/
├── gateway.py          ← NEW: GatewayService class
├── main.py             ← MODIFIED: endpoint_chat uses gateway.invoke()
├── models.py           ← UNCHANGED
├── store.py            ← UNCHANGED
├── auth.py             ← UNCHANGED
└── utils.py            ← UNCHANGED
```

### 8.2 `gateway.py` Module Structure

```python
"""AI Gateway — cost calculation, credit tracking, usage logging.

Centralized LiteLLM integration. All LLM calls flow through GatewayService.
Calculates cost from token counts, deducts credits, logs usage.
"""

from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone
from typing import Any, AsyncGenerator

import litellm

# Pricing: model → (prompt_per_1k, completion_per_1k) in USD
MODEL_PRICING: dict[str, tuple[float, float]] = {
    "ollama/qwen3.6:35b-mlx": (0.0, 0.0),
}

# Profile → model mapping
AI_PROFILES: dict[str, str] = {
    "fast": "ollama/qwen3.6:35b-mlx",
    "balanced": "ollama/qwen3.6:35b-mlx",
    "premium": "gpt-4.1",
}

# In-memory state
_user_credits: dict[str, dict] = {}   # api_key → credit record
_usage_history: dict[str, list] = {}  # session_id → usage records


class GatewayService:
    """Single gateway class. All LLM calls flow through invoke()."""

    MODEL_PRICING = MODEL_PRICING
    AI_PROFILES = AI_PROFILES
    _user_credits = _user_credits
    _usage_history = _usage_history

    @classmethod
    async def invoke(
        cls,
        session_id: str,
        message: str,
        api_key: str,
        working_json: dict[str, Any],
        model: str | None = None,
        profile: str | None = None,
    ) -> AsyncGenerator[str, None]:
        """Full LLM pipeline: credit check → stream → cost → deduct → log."""
        ...

    @classmethod
    def _ensure_credits(cls, api_key: str) -> dict[str, Any]:
        """Create default credit record for unknown API key."""
        ...

    @classmethod
    def _check_credits(cls, api_key: str) -> None:
        """Raise HTTPException(402) if credits exhausted."""
        ...

    @classmethod
    def _calculate_cost(cls, prompt_tokens: int, completion_tokens: int, model: str) -> float:
        """Calculate cost_usd from tokens + pricing table."""
        ...

    @classmethod
    def _calculate_credits(cls, cost_usd: float) -> float:
        """Convert USD cost to credits. 1 credit = $0.001."""
        ...

    @classmethod
    def _deduct_credits(cls, api_key: str, credits: float) -> None:
        """Subtract credits from API key's monthly balance."""
        ...

    @classmethod
    def _log_usage(cls, session_id: str, api_key: str, record: dict[str, Any]) -> None:
        """Append usage record to session's usage history."""
        ...

    @classmethod
    def _resolve_model(cls, model: str | None, profile: str | None) -> str:
        """Resolve model from explicit param or profile mapping."""
        ...

    @classmethod
    def _make_usage_event(cls, cost_usd: float, credits_used: float, model: str, provider: str, prompt_tokens: int, completion_tokens: int) -> str:
        """Build SSE event:usage string."""
        ...

    @classmethod
    def get_usage(cls, session_id: str) -> list[dict[str, Any]]:
        """Return usage records for a session. For future GET /api/usage."""
        ...

    @classmethod
    def get_user_credits(cls, api_key: str) -> dict[str, Any]:
        """Return credit record for an API key. For future GET /api/credits."""
        ...
```

### 8.3 `main.py` Changes

**Before (current):**

```python
@app.post("/api/chat")
async def endpoint_chat(...):
    async def event_generator():
        async for event_text in _stream_llm(working_json, message):
            yield event_text
    return StreamingResponse(event_generator(), media_type="text/event-stream")
```

**After (with gateway):**

```python
from .gateway import GatewayService

@app.post("/api/chat")
async def endpoint_chat(
    session_id: str = Form(...),
    message: str = Form(...),
    working_json_str: str | None = Form(default=None),
    _auth=Depends(require_api_key),
):
    session = get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    api_key = _auth  # The API key from require_api_key dependency

    async def event_generator():
        try:
            working_json = (
                _json.loads(working_json_str)
                if working_json_str
                else session["working_json"]
            )
            async for event_text in GatewayService.invoke(
                session_id, message, api_key, working_json
            ):
                yield event_text
        except HTTPException as e:
            if e.status_code == 402:
                yield "event: complete\ndata" + _json.dumps({
                    "working_json": session["working_json"],
                    "billing_error": True,
                    "error": e.detail.get("error", "Insufficient credits"),
                }) + "\n\n"
            else:
                raise
        except Exception as e:
            yield "event: complete\ndata" + _json.dumps({
                "working_json": session["working_json"],
                "explanation": f"Error: {e}",
            }) + "\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")
```

**Key changes:**
1. Import `GatewayService` from `gateway.py`.
2. `endpoint_chat` passes `api_key` (from `_auth` dependency result) to `GatewayService.invoke()`.
3. `GatewayService.invoke()` replaces the inline `_stream_llm()` call.
4. SSE event structure is preserved — `event_generator` still yields SSE strings.
5. 402 handling in `event_generator` yields a special `event: complete` with `billing_error: true`.

### 8.4 SSE Event Emission in `invoke()`

```python
# Inside GatewayService.invoke():

# Stream chunks as thinking events
async for chunk in response:
    text = chunk.choices[0].delta.get("content")
    if text:
        content_parts.append(text)
        yield f'event: thinking\ndata{_json.dumps({"text": text})}\n\n'

# Try to parse diffs
combined = "".join(content_parts)
# ... diff extraction logic (same as current main.py) ...

# Calculate cost and credits
usage = response.get("usage", {})
prompt_tokens = usage.get("prompt_tokens", 0) or 0
completion_tokens = usage.get("completion_tokens", 0) or 0
model = response.get("model", "unknown")

# Prefer response_cost from LiteLLM, fallback to pricing table
cost_usd = response.get("response_cost")
if cost_usd is None:
    cost_usd = cls._calculate_cost(prompt_tokens, completion_tokens, model)

credits_used = cls._calculate_credits(cost_usd)

# Emit usage event BEFORE complete
yield cls._make_usage_event(cost_usd, credits_used, model, "ollama", prompt_tokens, completion_tokens)

# Deduct credits and log
cls._deduct_credits(api_key, credits_used)
cls._log_usage(session_id, api_key, {
    "request_id": uuid.uuid4().hex,
    "api_key": api_key,
    "session_id": session_id,
    "model": model,
    "provider": "ollama",
    "prompt_tokens": prompt_tokens,
    "completion_tokens": completion_tokens,
    "total_tokens": prompt_tokens + completion_tokens,
    "cost_usd": cost_usd,
    "credits_used": credits_used,
    "latency_ms": int((time.monotonic() - start_time) * 1000),
    "feature": "modify-json",
    "status": "success",
    "timestamp": datetime.now(timezone.utc).isoformat(),
})
```

---

## 9. Error Contracts

### 9.1 HTTP 402 — Insufficient Credits

```json
{
    "error": "Insufficient credits",
    "hint": "Upgrade your plan. Current balance: 0 credits.",
    "required": 15,
    "current_balance": 0
}
```

- Returned when `credits_used >= monthly_limit`.
- No LLM call is made.
- No credits deducted.
- No usage record logged.
- SSE stream does not start — the 402 is raised before any `yield`.

### 9.2 HTTP 503 — All Providers Failed

```json
{
    "error": "All AI providers unavailable",
    "hint": "LiteLLM exhausted all fallback providers. Try again later."
}
```

- Returned when `litellm.acompletion()` raises after exhausting fallbacks.
- SSE stream starts with error in `event: complete`.
- Usage record logged with `status: "failed"`.
- No credits deducted (cost is 0).

### 9.3 HTTP 429 — Gateway Rate Limit

```json
{
    "error": "Gateway rate limited",
    "hint": "10 LLM calls per minute per API key."
}
```

- Gateway-level rate limit separate from API key rate limiter in `auth.py`.
- Prevents credit exhaustion from abusive usage.
- No LLM call. No credits deducted.

### 9.4 SSE `event: complete` with Billing Error

```json
{
    "working_json": {...},
    "billing_error": true,
    "error": "Insufficient credits"
}
```

- Emitted when 402 is raised mid-stream (edge case).
- Frontend should show upgrade prompt.

---

## 10. Assumptions & Constraints

1. **In-memory only.** No database. Credits and usage are lost on server restart. Matches ADR-0006.
2. **Single-threaded.** FastAPI dev server runs single worker. No locking needed for dicts.
3. **API key auth unchanged.** `X-API-Key` header. No JWT migration.
4. **Streaming preserved.** SSE stream structure is not broken. `event: usage` is additive.
5. **Local models are free.** `ollama/qwen3.6:35b-mlx` has `(0.0, 0.0)` pricing. No credits consumed.
6. **Unknown models are free.** If model not in `MODEL_PRICING`, cost is 0.0.
7. **Credit unit = $0.001.** 1 credit = one-thousandth of a USD. `credits = cost_usd / 0.001`.
8. **No credit top-up.** Credits are not refilled automatically. Manual adjustment only.
9. **No multi-user.** Single API key per session. No workspace/tenant concept yet.
10. **No subscription enforcement logic.** Plans are metadata only. The system tracks `credits_used` but does not auto-block based on plan tier (yet).

---

## 11. Future Extensions (Out of Scope for MVP)

- `GET /api/usage` — Usage history endpoint with aggregation.
- `GET /api/credits` — Current credit balance for an API key.
- `POST /api/credits/topup` — Add credits to a user's balance.
- Subscription enforcement — Auto-block based on plan tier.
- Credit rollover — Unused credits carry to next month.
- Team credit pools — Shared credit balance across workspace members.
- BYOK (Bring Your Own Key) — User-provided API keys for LiteLLM.
- Admin dashboard — Revenue, provider spend, gross margin.
- DB persistence — Swap in-memory dicts for SQLite/PostgreSQL.
- JWT auth — Replace API key with JWT tokens.
- Usage forecasting — Predict monthly credit consumption.
- Budget alerts — Email/SMS when credits fall below threshold.

---

## 12. Verification

### Manual Tests

1. **Happy path:** Send chat message. Verify SSE stream includes `event: thinking`, `event: diff`, `event: usage`, `event: complete`. Check `event: usage` has `cost_usd`, `credits_used`, `model`, `tokens`.
2. **Free model:** Use `ollama/qwen3.6:35b-mlx`. Verify `cost_usd: 0`, `credits_used: 0`. No credit deduction.
3. **Insufficient credits:** Set `credits_used` equal to `monthly_limit`. Send chat. Verify 402 response. No LLM call.
4. **Unknown model:** Set model to `"unknown/model"`. Verify cost is 0.0. No crash.
5. **Provider failure:** Point LiteLLM at dead endpoint. Verify 503 response. No credits deducted.
6. **Usage history:** After successful request, check `_usage_history[session_id]` has one record. Verify fields: `cost_usd`, `credits_used`, `latency_ms`, `status`.

### Code Review Checklist

- [ ] `GatewayService.invoke()` is the only LiteLLM caller.
- [ ] `MODEL_PRICING` covers all models in use.
- [ ] `event: usage` is emitted before `event: complete`.
- [ ] 402 is raised before any LLM call.
- [ ] Credits are deducted only on successful LLM responses.
- [ ] Failed requests log usage with `status: "failed"` and `cost_usd: 0`.
- [ ] No external dependencies added (only `litellm`, `uuid`, `time`, `datetime`, `json`).
- [ ] Module docstring follows existing style.
- [ ] All methods are `@classmethod` on a singleton class.
- [ ] In-memory dicts are module-level (not per-instance).

---

## 13. Files Modified

| File | Action | Change |
|------|--------|--------|
| `apps/api/src/json_ai_studio/gateway.py` | **NEW** | `GatewayService` class, pricing tables, credit tracking, usage logging |
| `apps/api/src/json_ai_studio/main.py` | **MODIFIED** | `endpoint_chat()` calls `GatewayService.invoke()` instead of inline `_stream_llm()` |
| `apps/api/ai/cost-credits/requirements.md` | **NEW** | This document |

**No changes to:** `models.py`, `store.py`, `auth.py`, `utils.py`.

---

## 14. Glossary

| Term | Definition |
|------|-----------|
| **AI Gateway** | `GatewayService` class in `gateway.py`. Central LiteLLM integration layer. |
| **Credit** | Billing unit. 1 credit = $0.001 USD. Deducted per LLM request. |
| **Credit Unit Value** | Fixed at $0.001. `credits = cost_usd / 0.001`. |
| **Monthly Limit** | Max credits per billing cycle per API key. 100 (free), 5000 (pro), 25000 (team), -1 (enterprise). |
| **Credits Used** | Running total of credits consumed in current billing cycle. |
| **Usage Record** | Per-request log entry. Tokens, cost, model, latency, timestamp. |
| **AI Profile** | UX abstraction. `fast`/`balanced`/`premium` → maps to real model string. |
| **MODEL_PRICING** | Dict mapping model strings to `(prompt_per_1k, completion_per_1k)` in USD. |
| **response_cost** | LiteLLM-provided cost field. Takes priority over pricing table. |
| **SSE** | Server-Sent Events. `text/event-stream` media type. Streaming LLM responses. |
| **event: usage** | New SSE event type. Emits cost/credits/model/tokens after LLM response. |

---

*End of requirements. Feature branch: `cost-credits`. Implementation file: `gateway.py`.*