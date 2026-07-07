# Backend Requirements — JSON AI Studio Explain Feature

Derived from PRD `explain-feature.prd`. Only what the **server / API layer** must implement.

---

## 1. New Endpoint

| # | Requirement | Priority |
|---|-------------|----------|
| E-01 | `POST /api/explain` — non-streaming, single response. Returns markdown explanation as plain text. | MVP |
| E-02 | Accepts JSON body: `{ "sessionId": string, "workingJson": object (optional) }`. If `workingJson` omitted, reads from session store. | MVP |
| E-03 | Auth: all endpoints protected by `X-API-Key` header + rate limiter (same as existing endpoints). | MVP |
| E-04 | Returns `200` with `Content-Type: text/plain` containing markdown explanation. | MVP |
| E-05 | Returns `404` if session not found. Returns `401` / `429` for auth/rate-limit failures. | MVP |

### Request / Response Schema

```json
// POST /api/explain
// Headers: X-API-Key: <key>
// Body: {"sessionId": "abc123", "workingJson": {...}}  (workingJson optional)

// Response 200 (text/plain)
# Summary
This JSON represents...

# Main Objects
- customer
- shipping

# Interesting Observations
- Contains 4 products
- Total amount = $245
```

---

## 2. GatewayService — New `explain()` Method

| # | Requirement | Priority |
|---|-------------|----------|
| G-01 | `GatewayService.explain(session_id, api_key, working_json)` — classmethod. Returns `str` (markdown). | MVP |
| G-02 | Internally calls `invoke()` to stream the LLM response, collects all content chunks, returns combined string. | MVP |
| G-03 | Uses `EXPLAIN_SYSTEM_PROMPT` (new, in `prompting.py`) as the system prompt. The user message is empty string `""`. | MVP |
| G-04 | Same deployment selection, same credit tracking, same cost deduction as `invoke()`. Only the prompt differs. | MVP |
| G-05 | `reasoning_effort` set to `"default"` (higher than chat's `"none"`). | MVP |

---

## 3. Explain System Prompt

| # | Requirement | Priority |
|---|-------------|----------|
| P-01 | New file `prompting_explain.py` (or new section in `prompting.py`) with `EXPLAIN_TEMPLATE` string. | MVP |
| P-02 | Template instructs LLM to explain JSON as if helping a developer understand it for the first time. | MVP |
| P-03 | Must include sections: Summary, What this JSON represents, Domain Concepts, Main Objects, Relationships, Important Fields, Interesting Observations, Potential Issues, Suggested Next Questions. | MVP |
| P-04 | Output must be valid markdown. No code fences. | MVP |
| P-05 | Template contains general DOMAIN AWARENESS guidelines: the LLM identifies the domain from the keys/values present in the payload and explains only the domain concepts tied to those keys (lifecycles, naming/unit conventions, enum meanings). No hardcoded per-domain knowledge in code. | MVP |
| P-06 | Secret-like fields (secret, token, api_key, password): LLM assesses strength and flags weak/placeholder values, but never repeats the value in the explanation. | MVP |

---

## 4. Data Flow

### 4.1 Happy Path

```
1. Frontend calls POST /api/explain with {sessionId, workingJson}
2. Endpoint retrieves session from store (or uses provided workingJson)
3. GatewayService.explain() called with working_json
4. DeploymentRegistry.pick() selects deployment
5. litellm.acompletion() called with EXPLAIN_SYSTEM_PROMPT + empty user message
6. Content chunks streamed, collected into single string
7. Credits deducted, usage logged
8. Markdown string returned as 200 text/plain response
```

### 4.2 Session Not Found

```
1. POST /api/explain with invalid sessionId
2. get_session() returns None
3. Return 404 {"error": "Session not found"}
```

---

## 5. Excluded from MVP

- Explain selected node (partial JSON explain)
- Explain path (right-click context menu)
- Multiple detail levels (beginner / developer / expert)
- Architecture diagram generation
- Mermaid diagram generation
- Interactive follow-up chat on explanation
- Security / PII analysis
- Save explanation to session state
- Export explanation as file

---

*End of requirements. Feature branch: `explain-feature`. Implementation files: `main.py` (new endpoint), `gateway.py` (new method), `prompting.py` (new prompt).*
