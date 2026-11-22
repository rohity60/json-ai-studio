# Live model / prompt evals

Real-model checks that a change to the **system prompt** (`src/json_ai_studio/prompting.py`), the **diff contract**, or the **server-side repairs** (`diff_utils.normalise_diffs`, `parse_llm_response`) did not break how the models behave. The unit/API suite in `tests/` stubs the LLM, so it can't catch a prompt edit that makes a model emit bad paths. These evals can.

They are kept out of the normal test run (`testpaths = ["tests"]` in `pyproject.toml`) and skip unless `LIVE_LLM=1`.

## When to run

- Before merging any edit to `prompting.py` (rules, examples, context blocks).
- After changing `normalise_diffs`, `_apply_order` or `parse_llm_response`.
- When a deployment's model changes (`deployments.yaml` `base_model`, or `--model`).

At minimum, run `array_index` on `ollama_local` (free) and `nvidia_nim` (the prod model) with `-r 3`.

## How to run

```bash
cd apps/api
uv run python evals/run_evals.py                              # array_index, ollama_local, 1 run
uv run python evals/run_evals.py -d nvidia_nim -r 3           # prod model, 3 runs
uv run python evals/run_evals.py -d google_ai_studio --spacing 30   # free tier: 16k tokens/min, slow (~30 min)
uv run python evals/run_evals.py -s array_index -s chat_history -d ollama_local -d nvidia_nim
uv run python evals/run_evals.py -d nvidia_nim -k prod_four   # one case, while debugging
```

The runner needs `apps/api/.env` with the deployment's key or URL (`OLLAMA_BASE_URL`, `NVIDIA_NIM_API_KEY`, `GOOGLE_AI_STUDIO_API_KEY`). If every case is skipped, it prints the skip reason. In a git worktree, link the main checkout's `.env`.

What a run produces:

- **Pass rate** per suite and deployment: passed / (passed + failed). Provider-busy skips are excluded.
- **Gate**: compared with `baselines.json`; below the minimum → exit code 1. `null` = report only.
- **Report** at `evals/reports/<timestamp>.md` (gitignored): a case × run table, plus the model's raw diffs for every failing case (the `RESULT` lines the evals print).

Models are not deterministic: judge a change by the rate over several runs, not one run. If a change moves a rate for good, update `baselines.json` in the same PR and say why.

## Suites

| Suite | File | Covers |
|---|---|---|
| `array_index` | `test_array_index_live.py` | Array indices (prompt rule 4): append via `-`, several inserts in one gap, inserts in two gaps, delete + insert, replace, delete + rename, delete + append, prod case (4 roles on a 51-role Discord JSON), insert after a named role in a long list, add-then-modify across turns (pending / accepted). |
| `chat_history` | `test_chat_history_live.py` | Follow-ups over replayed history (ADR-0021): "do the same for all", never re-propose done work. |
| `json_tools` | `test_json_tools_live.py` | Lookup-tool loop on large docs (ADR-0024). |
| `suggested_fixes` | `test_suggested_fixes_live.py` | Proactive format fixes (ADR-0023). |

You can also run a file directly: `LIVE_LLM=1 [LIVE_DEPLOYMENT=…] [LIVE_MODEL=…] [LIVE_CALL_SPACING_S=…] PYTHONPATH=. uv run pytest evals/<file> -s`.

## Baselines (array_index, 2026-11-23)

| Deployment | Model | Before PR #32 | After |
|---|---|---|---|
| ollama_local | gemma4:12b | 9/15 | 45/45 (+14/15 once) |
| nvidia_nim | nemotron-3.5-super-vl-120b-a12b | 7/15 | 58/60 |
| google_ai_studio | gemma-4-26b-a4b-it | 1/3 (stopped) | 12/13 |

Failure classes seen (and where they're handled):

- **Model counts a long array wrong** → `-` appends + `ARRAY LENGTHS` (prompt).
- **Numbering one after another instead of from the original list** → rule 4b (prompt). Delete/modify retargeted by `old_value`; add runs past the end folded into appends (server).
- **Several inserts in one gap get `/15, /16, /17`** → rule 4b (prompt).
- **`add /arr/*`**, **modify path one level too high**, **restating untouched elements** → `normalise_diffs` (server).
- **Malformed answers**: entries missing their `}`, or run together into one object with repeated keys → `parse_llm_response` (server).

## Adding a case

Add it to the relevant `test_*_live.py`. Make it print one `RESULT ok|FAIL <label> model=[…] …` line before asserting, so failures land in the report with the model's own diffs. Keep the expected result exact (named items, not counts), and run the new case on two deployments at least 3 times before setting a gate.
