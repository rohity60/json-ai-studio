"""Preview markers shared by everything that shows the model a cut-down
value (skeleton prompt, tool results) and by the edit guard that refuses
to write such a preview back as a full value (edit-safety ES-01..07).

Producers import these constants instead of hard-coding "…", so the guard
in diff_utils always knows every marker the model can have seen.
"""

from __future__ import annotations

import re

ELLIPSIS = "…"  # skeleton str_cap, tool _compact, read value_truncated
TRUNCATED_SUFFIX = ELLIPSIS + "(truncated)"  # whole tool result cut
# "…+700 more items" (skeleton arrays), "+N more keys" lives in a "…" key.
_MORE_ITEMS_RE = re.compile(r"…\+\d+ more (?:items|keys)$")


def ends_with_preview_marker(text: str) -> bool:
    """True when `text` ends the way a truncated preview does."""
    return (
        text.endswith(ELLIPSIS)
        or text.endswith(TRUNCATED_SUFFIX)
        or bool(_MORE_ITEMS_RE.search(text))
    )
