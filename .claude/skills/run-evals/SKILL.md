---
name: run-evals
description: Run the live model/prompt evals (apps/api/evals) against real LLM deployments, read the reports, debug failing cases from the model's raw output, decide prompt fix vs server repair, update baselines, and optionally smoke-check a running deployment (local or prod). Use after ANY change to apps/api/src/json_ai_studio/prompting.py, diff_utils.py (normalise_diffs / _apply_order / parse_llm_response), chat history replay, or a deployment's model; or when the user asks to "run evals", "check model behaviour", "did the prompt change break anything", or to smoke-test prod.
---

# Run model / prompt evals

The `tests/` suite stubs the LLM, so it can't tell whether a prompt edit still makes real models emit correct diffs. The evals in `apps/api/evals/` send real requests. This skill runs them the way we validated the array-index fix (PR #32 / #33): several runs per deployment, judged by pass RATE, failures traced to the model's raw diffs.

## 0. Setup (once per checkout)

- Work from `apps/api`. Live evals read keys and URLs from `apps/api/.env`: `OLLAMA_BASE_URL`, `NVIDIA_NIM_API_KEY`, `GOOGLE_AI_STUDIO_API_KEY`.
- **In a git worktree** there's no `.env`. Link the main checkout's (it's gitignored):
  `ln -sf <main-checkout>/apps/api/.env apps/api/.env`
  Symptom when it's missing: every case `skipped`, and the runner prints "skip reason: … no endpoint configured".
- First make sure the offline suite is green: `PYTHONPATH=. uv run pytest -q`. Strict `xfail`s are expected: they pin known gaps and turn into failures when someone fixes them.

## 1. Run, cheapest first

```bash
cd apps/api
uv run python evals/run_evals.py -d ollama_local                 # local, free, ~2 min
uv run python evals/run_evals.py -d nvidia_nim -r 3              # prod model, ~2 min, small quota
uv run python evals/run_evals.py -d google_ai_studio --spacing 30   # free tier 16k tok/min: ~30 min, run in background
```

- Default suite is `array_index`. Add `-s chat_history -s json_tools -s suggested_fixes` when the change touches history replay, lookup tools or format fixes. Add `-s restructure` for layout/move/guard changes in chat, and `-s review` for review-job changes (`job_service`, `job_packing`, `layout.py`).
- Models are noisy: use `-r 3` on the prod model (`nvidia_nim`) before trusting a result. Judge the rate over runs, never a single run.
- The Google run is long: start it with `run_in_background`, and don't poll it.
- Exit code 1 = a suite fell below its minimum in `evals/baselines.json`. The report is at `evals/reports/<timestamp>.md` (gitignored).

## 2. Read the report

Each report has a case × run table (✅ ❌ ⏭) plus, for every failure, the `RESULT FAIL` line with the model's diffs as the model sent them, before server repair. Classify each failure:

| Pattern in `model=[…]` | Class | Where it's handled |
|---|---|---|
| append index off by one / counted | model counted a long array | prompt: `-` appends, `ARRAY LENGTHS` |
| `delete /x/0`, `delete /x/1` for A and C | numbered one after another, not original-list | server: retarget by `old_value`; prompt rule 4c |
| `add /x/15, /x/16, /x/17` for one gap | numbered one after another | prompt rule 4b (same index); server can't tell |
| `add /x/*` | bulk wildcard in a plain diff | server: `_star_add_to_append` |
| `modify /x/2` old `'C'` (a field value) | path one level too high | server: deepen modify |
| extra `modify` with new == old | "shifting" untouched items | server: no-op drop |
| `model=[]` with a sensible explanation | malformed JSON the parser dropped | parser: `parse_llm_response` salvage |
| `model=[]` + question | asked instead of acting | prompt rule 12 / 4a |
| correct indices, wrong content | not an index problem | note it, don't chase it |

## 3. Debug one case from the raw output

```bash
LOG_LEVEL=DEBUG LIVE_LLM=1 LIVE_DEPLOYMENT=nvidia_nim PYTHONPATH=. \
  uv run pytest evals/test_array_index_live.py -s -q -k prod_four 2>&1 \
  | grep -E "^RESULT|llm raw output|normalise|retarget|FAILED op"
```

- `llm raw output (full)` is the exact model text. Look for broken JSON first: a missing `}` between entries, or entries run together with repeated keys.
- `normalise …` / `retarget …` log lines show which server repairs fired.
- Repeat the case about 5 times in a loop to tell a pattern from noise.

## 4. Decide the fix

- **Server repair** (`diff_utils.normalise_diffs`, `parse_llm_response`) only when the fix is unambiguous from the answer itself, e.g. `old_value` names a unique element, or an index is impossible as given. Never guess an add's position: adds carry no `old_value`.
- **Prompt** (`prompting.py`, rule 4 + examples) for everything else. Prefer a contrast example ("NOT 15, 16, 17") over more words. After any prompt edit, check that `tests/test_prompt_array_rules.py` still passes (update it if a rule was reworded on purpose).
- Every fix gets a unit test with the model's real broken output (trimmed) in `tests/test_diff_utils.py` or `tests/test_array_index_api.py`.
- Re-run step 1 on at least `ollama_local` and `nvidia_nim -r 3` and compare with the report from before the change.

## 5. Baselines

- `evals/baselines.json` holds the minimum pass rate per suite and deployment, plus the model and measured numbers. `null` = report only.
- Raise a gate only after 3+ runs on the new rate. Lower it only with a stated reason (a model change), in the same PR as the change.
- New eval case: add it to the suite file. Print one `RESULT ok|FAIL <label> model=[…]` line before asserting, keep the expected result exact, and run it 3× on two deployments before trusting it.

## 6. Smoke-check a running deployment (only when asked)

```bash
python3 .claude/skills/run-evals/scripts/smoke_array_index.py http://localhost:8000      # local API
python3 .claude/skills/run-evals/scripts/smoke_array_index.py https://jsonaistudio.com   # prod
```

- Runs 4 samples on synthetic data: 4 roles on 51, two inserts in one gap, delete + insert, append 3 + reject the middle one + accept-all. Exit 1 on any failure.
- **Prod spends real model calls** from the shared anonymous credit pool, so run it only when the user asks for a prod check. Use only the script's synthetic data, never user JSON.
- It goes through curl because Cloudflare rejects Python's default user agent (error 1010). Don't spoof user agents. It backs off on the anonymous 10 requests / 60 s limit.
- `[new-build]` on each line means diff entries carry `preview_path`, i.e. PR #32+ is deployed. Prod `/api/health` has no commit info.

## 7. Report back

Give the user: a per-deployment table (before → after rate, runs), each remaining failure with its class, which fixes went where (prompt vs server), and whether baselines changed. Don't call a change safe on one run of one model.
