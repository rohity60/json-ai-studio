"""Run live model/prompt evals and gate them against baselines.

Run this after ANY change to the system prompt (prompting.py), the diff
contract or the server-side repairs (diff_utils.normalise_diffs), and
when switching a deployment's model. It sends real requests to the
chosen deployments (Ollama is local and free; cloud ones use quota).

    cd apps/api
    uv run python evals/run_evals.py                          # array_index on ollama_local, 1 run
    uv run python evals/run_evals.py -d nvidia_nim -r 3       # 3 runs: pass RATE, models are noisy
    uv run python evals/run_evals.py -d google_ai_studio --spacing 30   # free tier: 16k tokens/min
    uv run python evals/run_evals.py -s array_index -s chat_history -d ollama_local -d nvidia_nim

Each case's outcome per run is parsed from pytest's junit XML. The suite
pass rate (passed / (passed + failed); provider-busy skips excluded) is
compared with evals/baselines.json; below the minimum → exit code 1.
A markdown report (per-case results + the model's diffs for failures,
from the RESULT lines the evals print) goes to evals/reports/.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path

EVALS = Path(__file__).resolve().parent
API = EVALS.parent
SUITES = {
    "array_index": "test_array_index_live.py",
    "chat_history": "test_chat_history_live.py",
    "json_tools": "test_json_tools_live.py",
    "suggested_fixes": "test_suggested_fixes_live.py",
}


def run_once(suite: str, deployment: str, args) -> tuple[dict[str, str], list[str]]:
    """One pytest run → ({case: passed|failed|skipped}, RESULT lines)."""
    env = {
        **os.environ,
        "LIVE_LLM": "1",
        "LIVE_DEPLOYMENT": deployment,
        "PYTHONPATH": str(API),
    }
    if args.spacing:
        env["LIVE_CALL_SPACING_S"] = str(args.spacing)
    if args.model:
        env["LIVE_MODEL"] = args.model
    with tempfile.TemporaryDirectory() as tmp:
        junit = Path(tmp) / "junit.xml"
        cmd = [
            sys.executable,
            "-m",
            "pytest",
            str(EVALS / SUITES[suite]),
            "-q",
            "-s",
            "-p",
            "no:cacheprovider",
            f"--junitxml={junit}",
        ]
        if args.k:
            cmd += ["-k", args.k]
        proc = subprocess.run(cmd, cwd=API, env=env, capture_output=True, text=True)
        results: dict[str, str] = {}
        skips: list[str] = []
        if junit.exists():
            for case in ET.parse(junit).iter("testcase"):
                name = case.get("name", "?")
                if case.find("failure") is not None or case.find("error") is not None:
                    results[name] = "failed"
                elif case.find("skipped") is not None:
                    results[name] = "skipped"
                    reason = case.find("skipped").get("message", "")
                    if reason and f"skip reason: {reason}" not in skips:
                        skips.append(f"skip reason: {reason}")
                else:
                    results[name] = "passed"
        lines = [
            re.sub(r"^RESULT\s+", "", ln)
            for ln in proc.stdout.splitlines()
            if ln.startswith("RESULT")
        ]
        if not results:
            lines.append("pytest produced no results:\n" + proc.stdout[-2000:])
        if results and all(o == "skipped" for o in results.values()):
            lines += skips  # e.g. no OLLAMA_BASE_URL / API key in .env
        return results, lines


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("-s", "--suite", action="append", choices=sorted(SUITES))
    ap.add_argument("-d", "--deployment", action="append")
    ap.add_argument("-r", "--runs", type=int, default=1)
    ap.add_argument("--spacing", type=float, help="seconds between LLM calls")
    ap.add_argument("--model", help="override the deployment's base_model")
    ap.add_argument("-k", help="pytest -k filter (debugging one case)")
    args = ap.parse_args()
    suites = args.suite or ["array_index"]
    deployments = args.deployment or ["ollama_local"]
    baselines = json.loads((EVALS / "baselines.json").read_text())

    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    report = [f"# Eval report {stamp}", ""]
    failed_gates: list[str] = []
    for suite in suites:
        for dep in deployments:
            outcomes: dict[str, list[str]] = defaultdict(list)
            result_lines: list[str] = []
            for run in range(1, args.runs + 1):
                print(f"[{suite} / {dep}] run {run}/{args.runs} …", flush=True)
                res, lines = run_once(suite, dep, args)
                for case, outcome in res.items():
                    outcomes[case].append(outcome)
                result_lines += [f"run {run}: {ln}" for ln in lines]
            passed = sum(o.count("passed") for o in outcomes.values())
            failed = sum(o.count("failed") for o in outcomes.values())
            skipped = sum(o.count("skipped") for o in outcomes.values())
            rate = passed / (passed + failed) if passed + failed else None
            gate = baselines.get(suite, {}).get(dep, {}).get("min_pass_rate")
            ok = rate is not None and (gate is None or rate >= gate)
            verdict = (
                "no results"
                if rate is None
                else ("PASS" if ok else "BELOW BASELINE")
                + (f" (min {gate:.0%})" if gate is not None else " (no gate)")
            )
            if not ok:
                failed_gates.append(f"{suite}/{dep}")
            summary = (
                f"{suite} / {dep}: {passed} passed, {failed} failed, {skipped} skipped"
                + (f" → {rate:.0%}" if rate is not None else "")
                + f" — {verdict}"
            )
            print(summary, flush=True)
            report += [
                f"## {summary}",
                "",
                "| case | "
                + " | ".join(f"run {i}" for i in range(1, args.runs + 1))
                + " |",
                "|---|" + "---|" * args.runs,
            ]
            icon = {"passed": "✅", "failed": "❌", "skipped": "⏭"}
            for case, outs in sorted(outcomes.items()):
                report.append(f"| {case} | " + " | ".join(icon[o] for o in outs) + " |")
            bad = [
                ln
                for ln in result_lines
                if " FAIL " in f" {ln} " or "no results" in ln or "skip reason" in ln
            ]
            if rate is None:
                print("\n".join(dict.fromkeys(bad)) or "no cases ran", flush=True)
            if bad:
                report += ["", "Failures (model diffs as sent):", "```", *bad, "```"]
            report.append("")

    out = EVALS / "reports" / f"{stamp}.md"
    out.parent.mkdir(exist_ok=True)
    out.write_text("\n".join(report))
    print(f"report: {out}")
    if failed_gates:
        print("BELOW BASELINE: " + ", ".join(failed_gates))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
