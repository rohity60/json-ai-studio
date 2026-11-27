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
    return {
        "roles": [{"name": f"role {chr(97 + i % 26)}"} for i in range(n)],
        "tags": ["a", "b"],
    }


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


class TestNumberedIds:
    """Prod 2026-11-24: ids m1..m6 at indices 0..5 read as indices 1..6."""

    def test_short_array_with_numbered_ids_listed_with_mapping(self):
        doc = {"rulebook": {"meters": [{"id": f"m{i}"} for i in range(1, 7)]}}
        assert build_array_lengths(doc) == [
            '/rulebook/meters: 6 items (indices 0..5) — index 0 is id "m1", '
            'index 5 is id "m6"'
        ]

    def test_integer_ids_and_name_fallback(self):
        assert build_array_lengths({"a": [{"id": 1}, {"id": 2}]}) == [
            "/a: 2 items (indices 0..1) — index 0 is id 1, index 1 is id 2"
        ]
        assert build_array_lengths({"a": [{"name": "Step 1"}, {"name": "Step 2"}]}) == [
            '/a: 2 items (indices 0..1) — index 0 is name "Step 1", '
            'index 1 is name "Step 2"'
        ]

    def test_short_arrays_without_numbered_ids_not_listed(self):
        assert build_array_lengths({"a": [{"id": "trust"}, {"id": "love"}]}) == []
        assert build_array_lengths({"a": [{"id": "m1"}]}) == []  # one element
        assert build_array_lengths({"a": [1, 2, 3]}) == []
        assert build_array_lengths({"a": [{"id": True}, {"id": False}]}) == []

    def test_long_array_gets_mapping_too(self):
        doc = {"roles": [{"name": f"r{i}"} for i in range(51)]}
        assert build_array_lengths(doc) == [
            '/roles: 51 items (indices 0..50) — index 0 is name "r0", '
            'index 50 is name "r50"'
        ]

    def test_prompt_rules_present(self):
        prompt = build_system_prompt({"a": 1}, mode="inline")
        assert "4f. An element's id or name" in prompt
        assert 'X0. "replace_text" works ONLY on a string value' in prompt
        assert '"path": "/meters/0/keywords/-"' in prompt


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
