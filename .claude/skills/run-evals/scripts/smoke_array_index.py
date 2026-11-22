"""Smoke-check array-index handling against a running deployment.

    python3 .claude/skills/run-evals/scripts/smoke_array_index.py https://jsonaistudio.com
    python3 .claude/skills/run-evals/scripts/smoke_array_index.py http://localhost:8000

Synthetic data only. Uses anonymous sessions (one random X-API-Key per run)
and the deployment's real model, so it spends a little of the shared
anonymous credit pool. Prints one line per sample; exit code 1 if any fails.

Requests go through curl: Cloudflare in front of prod rejects Python's
default user agent (error 1010). The anonymous rate limit is 10 requests
per 60 s per key, so the script waits and retries on 429.

Each line shows [new-build] when diff entries carry "preview_path"
(PR #32+), which is how to tell the deployed build from behaviour —
/api/health has no commit info.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
import uuid

BASE = (sys.argv[1] if len(sys.argv) > 1 else "https://jsonaistudio.com").rstrip("/")
API = BASE + "/api"
KEY = f"evalcheck-{uuid.uuid4()}"


def req(method: str, path: str, data=None, form=None) -> str:
    cmd = ["curl", "-sS", "--fail-with-body", "-m", "300", "-X", method,
           API + path, "-H", f"X-API-Key: {KEY}"]
    if form is not None:
        for k, v in form.items():
            cmd += ["--form-string", f"{k}={v}"]
    elif data is not None:
        cmd += ["-H", "Content-Type: application/json", "-d", json.dumps(data)]
    for _ in range(4):
        out = subprocess.run(cmd, capture_output=True, text=True)
        if "Rate limit reached" not in out.stdout:
            break
        time.sleep(65)
    if out.returncode:
        raise RuntimeError(f"{method} {path}: {out.stdout[:300]} {out.stderr[:300]}")
    return out.stdout


def session(doc: dict) -> str:
    sid = json.loads(req("POST", "/sessions", {"name": "array-index smoke"}))["id"]
    req("POST", "/json/upload", form={"json_body": json.dumps(doc), "session_id": sid})
    return sid


def chat(sid: str, message: str):
    text = req("POST", "/chat", form={"session_id": sid, "message": message})
    events = []
    for block in text.split("\n\n"):
        ev, data = None, ""
        for line in block.splitlines():
            if line.startswith("event:"):
                ev = line[6:].strip()
            elif line.startswith("data:"):
                data += line[5:].strip()
        if ev:
            events.append((ev, json.loads(data) if data else None))
    diffs = [p["entry"] for e, p in events if e == "diff"]
    done = next((p for e, p in events if e == "complete"), {})
    busy = [e for e, _ in events
            if e in ("rate_limit", "credit_limit", "service_unavailable", "error")]
    return diffs, done, busy


def names(doc: dict, key: str) -> list:
    return [x.get("name") if isinstance(x, dict) else repr(x) for x in doc.get(key, [])]


ROLE_NAMES = (
    ["@everyone", "Owner", "Co-Owner", "Admin", "Head Moderator", "Moderator"]
    + ["Trial Staff", "Helper", "Server Booster", "Verified", "Muted"]
    + [f"Regiment {i}" for i in range(1, 21)]
    + [f"Level {i * 5}" for i in range(1, 21)]
)
SERVER = {
    "name": "Synthetic Test Server",
    "roles": [
        {"id": str(900000 + i), "name": n, "color": 0, "position": 50 - i,
         "permissions": "0"}
        for i, n in enumerate(ROLE_NAMES)
    ],
}
CARDS = {"cards": [{"name": n, "text": "t"} for n in "ABCD"]}
NEW = ["Senior Staff", "Recruitment Staff", "Event Staff", "Free Carriers"]
FAILURES = 0


def show(label: str, ok: bool, diffs: list, extra: str) -> None:
    global FAILURES
    FAILURES += not ok
    paths = [f"{d['operation']} {d['path']}" for d in diffs]
    build = "new-build" if any("preview_path" in d for d in diffs) else "OLD-BUILD?"
    print(f"{'ok  ' if ok else 'FAIL'} {label:24} [{build}] diffs={paths} {extra}",
          flush=True)


def main() -> int:
    # 1. prod case 2026-11-21: 4 new roles on a 51-role server
    sid = session(SERVER)
    diffs, done, busy = chat(
        sid,
        "Add new placeholder roles Senior Staff, Recruitment Staff, Event Staff and "
        "Free Carriers with minimal permissions (I'll supply real IDs later).",
    )
    got = names(done.get("working_json", {}), "roles")
    at = sorted(got.index(n) for n in NEW if n in got)
    ok = ([n for n in got if n not in NEW] == ROLE_NAMES and len(at) == 4
          and at == list(range(at[0], at[0] + 4)))
    show("4 roles on 51", ok, diffs, f"added_at={at} {busy or ''}")

    # 2. two inserts in one gap
    sid = session(CARDS)
    diffs, done, busy = chat(sid, "Insert two cards X then Y (text 'TBD') between A and B.")
    got = "".join(names(done.get("working_json", {}), "cards"))
    show("two inserts one gap", got == "AXYBCD", diffs, f"got={got} {busy or ''}")

    # 3. delete + insert later in the same list
    sid = session(CARDS)
    diffs, done, busy = chat(sid, "Delete card B, and insert a card X (text 'TBD') right before D.")
    got = "".join(names(done.get("working_json", {}), "cards"))
    show("delete + insert", got == "ACXD", diffs, f"got={got} {busy or ''}")

    # 4. append three, reject the middle one, accept the rest
    sid = session(CARDS)
    diffs, done, busy = chat(sid, "Append three cards named X, Y and Z (text 'TBD') at the end.")
    ids = {d["new_value"].get("name"): d["id"] for d in diffs
           if isinstance(d.get("new_value"), dict)}
    if "Y" in ids:
        rej = json.loads(req("POST", f"/sessions/{sid}/diffs/{ids['Y']}/reject"))
        fin = json.loads(req("POST", f"/sessions/{sid}/diffs/accept-all"))
        pv = "".join(names(rej["working_json"], "cards"))
        sv = "".join(names(fin["baseline_json"], "cards"))
        show("append 3, reject Y", pv == sv == "ABCDXZ", diffs, f"preview={pv} saved={sv}")
    else:
        show("append 3, reject Y", False, diffs, f"no Y diff {busy or ''}")

    print(f"{4 - FAILURES}/4 passed against {BASE}")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
