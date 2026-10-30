"""Structure-preserving JSON trimmer (ADR-0025) for the user's trimmed copy
offered with `input_too_large` — never for what the model sees.

Keeps the document's shape while shrinking it: arrays keep their first
`keep_items` elements, strings longer than `str_cap` end with an ellipsis,
and (only for the user's trimmed copy) objects keep their first `key_cap`
keys. Returns the trimmed value plus a cut report in user terms, aggregated
by path pattern (indices → `*`), e.g. `/records: 1240 → 25 items`.

`fit_trim` searches for the least aggressive trim a caller-supplied
`fits(trimmed, cuts)` accepts (the planner passes a token-budget check).
"""

from __future__ import annotations

from typing import Any, Callable

_STR_CAPS = (300, 120, 60)
_KEY_CAPS = (50, 20, 10, 5)
_ELLIPSIS = "…"


def _esc(part: str) -> str:
    return part.replace("~", "~0").replace("/", "~1")


def trim_json(
    data: Any, keep_items: int, str_cap: int, key_cap: int | None = None
) -> tuple[Any, list[dict[str, Any]]]:
    """Trimmed copy of `data` and its aggregated cut report."""
    arrays: dict[str, int] = {}  # pattern -> largest original length cut
    strings: dict[str, int] = {}  # pattern -> number of values capped
    keys: dict[str, int] = {}  # pattern -> largest original key count cut

    def walk(node: Any, pattern: str) -> Any:
        if isinstance(node, dict):
            items = list(node.items())
            if key_cap is not None and len(items) > key_cap:
                keys[pattern] = max(keys.get(pattern, 0), len(items))
                items = items[:key_cap]
            return {k: walk(v, f"{pattern}/{_esc(str(k))}") for k, v in items}
        if isinstance(node, list):
            if len(node) > keep_items:
                arrays[pattern] = max(arrays.get(pattern, 0), len(node))
            return [walk(v, f"{pattern}/*") for v in node[:keep_items]]
        if isinstance(node, str) and len(node) > str_cap:
            strings[pattern] = strings.get(pattern, 0) + 1
            return node[:str_cap] + _ELLIPSIS
        return node

    trimmed = walk(data, "")
    cuts: list[dict[str, Any]] = [
        {"path": p, "kind": "array", "from": n, "to": keep_items}
        for p, n in arrays.items()
    ]
    cuts += [
        {"path": p, "kind": "keys", "from": n, "to": key_cap} for p, n in keys.items()
    ]
    cuts += [
        {"path": p, "kind": "string", "count": n, "to": str_cap}
        for p, n in strings.items()
    ]
    return trimmed, cuts


def longest_array(data: Any) -> int:
    best = 0
    stack = [data]
    while stack:
        node = stack.pop()
        if isinstance(node, list):
            best = max(best, len(node))
            stack.extend(node)
        elif isinstance(node, dict):
            stack.extend(node.values())
    return best


def fit_trim(
    data: Any,
    fits: Callable[[Any, list[dict[str, Any]]], bool],
    min_items: int = 1,
    allow_key_cap: bool = False,
) -> tuple[Any, list[dict[str, Any]]] | None:
    """Least aggressive trim that `fits` accepts, or None.

    Prefers more array items over longer strings: for each string cap
    (300 → 60 chars) binary-searches the largest keep_items ≥ min_items.
    With allow_key_cap, falls back to capping object keys (lossy shape —
    only for a copy the user explicitly takes).
    """
    top = longest_array(data)
    if top <= min_items and not allow_key_cap:
        return None  # nothing to trim that would change the view
    for cap in _STR_CAPS:
        lo, hi, best = min_items, max(top, min_items), None
        while lo <= hi:
            mid = (lo + hi) // 2
            trimmed, cuts = trim_json(data, mid, cap)
            if fits(trimmed, cuts):
                best = (trimmed, cuts)
                lo = mid + 1
            else:
                hi = mid - 1
        if best is not None:
            return best
    if allow_key_cap:
        for key_cap in _KEY_CAPS:
            trimmed, cuts = trim_json(data, 1, _STR_CAPS[-1], key_cap)
            if fits(trimmed, cuts):
                return trimmed, cuts
    return None
