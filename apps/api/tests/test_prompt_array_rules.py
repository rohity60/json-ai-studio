"""Static guards for the array-index prompt contract (prompt rule 4).

Cheap checks that a prompt edit did not drop the pieces the live evals
(evals/test_array_index.py) depend on. Behaviour is verified by the evals.
"""

from __future__ import annotations

from src.json_ai_studio.prompting import (
    _HISTORY_RULES,
    build_array_lengths,
    build_system_prompt,
)


def _doc(n: int) -> dict:
    return {"roles": [{"name": f"r{i}"} for i in range(n)], "tags": ["a", "b"]}


class TestArrayLengths:
    def test_only_long_arrays_listed(self):
        assert build_array_lengths(_doc(51)) == ["/roles: 51 items (indices 0..50)"]
        assert build_array_lengths(_doc(10)) == []

    def test_nested_and_escaped_paths(self):
        doc = {"a/b": [{"items": list(range(12))}]}
        assert build_array_lengths(doc) == ["/a~1b/0/items: 12 items (indices 0..11)"]

    def test_capped(self):
        doc = {f"k{i}": list(range(11)) for i in range(60)}
        assert len(build_array_lengths(doc)) == 40


class TestPromptContract:
    def test_inline_prompt_carries_lengths(self):
        prompt = build_system_prompt(_doc(51), mode="inline")
        assert "ARRAY LENGTHS" in prompt
        assert "/roles: 51 items (indices 0..50)" in prompt

    def test_no_lengths_block_for_short_arrays(self):
        assert "ARRAY LENGTHS (counted" not in build_system_prompt(
            _doc(3), mode="inline"
        )

    def test_rule_4_pieces_present(self):
        prompt = build_system_prompt(_doc(3), mode="inline")
        for piece in (
            "ALWAYS refer to the CURRENT WORKING JSON exactly as shown",
            '"/<array>/-"',
            "all get the SAME index",
            "NOT 15, 16, 17",
            'Never put "*" in a plain diff path',
            'never a "modify" with "new_value" null',
            "When the user does not say WHERE new items go, append them",
        ):
            assert piece in prompt, piece

    def test_append_example_uses_dash_without_count_hint(self):
        prompt = build_system_prompt(_doc(3), mode="inline")
        assert '"path": "/howToRedeem/-"' in prompt
        assert "(the array currently has" not in prompt

    def test_history_rule_points_to_current_index(self):
        assert "find it in the CURRENT WORKING JSON (by its content)" in _HISTORY_RULES
