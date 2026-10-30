# Deployment token budget — manual test data (ADR-0025)

Four JSONs, one per planner outcome on `google_ai_studio` (free tier,
`tpm_input_limit: 16000`). Files 2–4 (~1.4 MB) are not committed — create
them first with `python3 make_test_data.py` in this folder (seeded,
identical output every time).

Upload each file in the Studio (Upload tab → drop file), then send the
prompts in order. Watch the API log (`logs/app.log`) for the
`turn plan mode=…` line and `budget …` lines.

> These calls hit the real Google key in `.env`. Google counts 16k input
> tokens per minute **per key**, shared with anyone else using it.

| File | Size | Before ADR-0025 | Now |
|---|---|---|---|
| `1-small-flags.json` | <1 KB | full JSON | full JSON, 1 call |
| `2-orders-mid.json` | 156 KB | full JSON (~50k tokens) → always 429 | skeleton + tools, up to 4 rounds |
| `3-catalog-large.json` | 592 KB | skeleton + 4 rounds → 429 mid-turn | skeleton + tools, rounds wait for capacity |
| `4-tenants-too-large.json` | 673 KB | skeleton | `input_too_large` dialog |

---

## 1. Small — full JSON inline

| Prompt | Expect |
|---|---|
| `Turn on darkMode for everyone and set its rollout to 100` | 2 diffs (`/flags/darkMode/enabled`, `/flags/darkMode/rollout`). Log: `turn plan mode=inline`. No waiting. |
| `Remove the staff segment from aiAssistant` | 1 diff on `/flags/aiAssistant/segments`. |

## 2. Mid-size — skeleton + lookup tools (used to always fail)

| Prompt | Expect |
|---|---|
| `Mark order ORD-0147 as shipped` | Chat shows "Searching…" (tool round), then 1 diff on `/orders/147/status`. Log: `turn plan mode=skeleton … max_rounds=4 tools=True`. |
| `Cancel every order from customer C-042` | A bulk op (`/orders/*/status` where `customerId == "C-042"`) expanded into N diffs — check a few match that customer. |
| `How many orders are pending?` | Answer in the explanation, no diffs (analysis via `query`). |

## 3. Large + multi-hop — rounds wait for capacity

Send these back to back (don't wait between them) to fill the minute.

| Prompt | Expect |
|---|---|
| `Find the bundle that contains P-0042 and set its discountPercent to 15` | Needs search → read (2+ rounds). Diff on `/products/1525/discountPercent`. If the minute fills, the chat shows **"Waiting for AI model capacity… ~Ns"** counting down, then continues. No "answer now" truncation. |
| `Increase price by 10% for every audio product` | Bulk op on `/products/*/price` where `category == "audio"`. Likely starts with a **waiting** countdown (previous turn used the window). |
| `Which bundles have discountPercent 5?` | Analysis answer listing bundle ids (bundles only appear after index 1500 — the key-union skeleton shows `contains` / `discountPercent`). |

Calls are paced 15 s apart on Google (`min_call_interval_s`), across all
users and tool rounds: a 2-lookup turn shows the countdown before each
lookup round and takes ≥ 30 s. A Google 500 is **not** retried — the turn
ends with "service busy"; send again after the countdown window.

Log lines to look for: `budget reserve …`, `budget wait … wait=…s`,
`budget settle … estimated=… actual=… ratio=…` (calibration).

## 4. Too large — dialog, sections, trimmed copy

| Step | Expect |
|---|---|
| Prompt: `Set sessionTimeoutMinutes to 30` | No LLM call. Dialog **"JSON too large for the AI model"**: "about 567 KB … about 33 KB at a time". Sections listed top-level first: `/defaults`, `/billing`, then `/tenants/t-001…`. |
| Click `/defaults` | Same prompt resent with `focus_path=/defaults`; user bubble shows `(Section: /defaults)`. 1 diff on **`/defaults/sessionTimeoutMinutes`** (full-document path). |
| Prompt again, click `/tenants/t-001`, ask `Enable sso for this tenant` | Diff on `/tenants/t-001/sso/enabled`. |
| Click **Download trimmed copy** | `trimmed.json` downloads; the Studio still shows the full document. |

## Capacity popup (optional)

Appears when a wait would exceed 60 s (5+ calls queued) or Google returns
any 429 (no retries, `CHAT_TOOL_RETRY_ATTEMPTS=0`). Expect **"AI model at
capacity"** with a countdown and **no** login button. A Google 500 shows
"Service busy" instead. Per-user limits still
show "Rate limit reached" with the login button (`scope: "user"`).
