"""Unit tests for fixes found by the live evals (2026-11-24)."""

from src.json_ai_studio.format_hints import format_notes_block, match_formats
from src.json_ai_studio.gateway import looks_like_tool_markup
from src.json_ai_studio.prompting import build_system_prompt

UASSET = {
    "$type": "UAssetAPI.UAsset, UAssetAPI",
    "NameMap": ["A", "MagazineStop"],
    "Imports": [{"ObjectName": "MagazineStop"}],
    "Exports": [{"ObjectName": "F"}],
}


def test_uassetapi_note_matches_and_explains_negative_indexes():
    assert [f["id"] for f in match_formats(UASSET)] == ["uassetapi-json"]
    block = format_notes_block(UASSET)
    assert "-2 → /Imports/1" in block and "StackNode -2" in block
    assert "uassetapi" not in str(match_formats({"Imports": [], "x": 1}))


def test_uassetapi_note_reaches_skeleton_prompt():
    assert "Package indexes" in build_system_prompt(UASSET, mode="skeleton")


def test_tool_markup_detection():
    assert looks_like_tool_markup('<tool_call>\n<function=read>{"path": "/x"}')
    assert looks_like_tool_markup('{"tool_calls": [{"name": "read"}]}')
    assert not looks_like_tool_markup('{"diffs": [], "explanation": "<function=x>"}')
    assert not looks_like_tool_markup("No changes needed.")
    assert not looks_like_tool_markup("")


def test_rule_11_requires_warning_for_explicit_invalid_value():
    prompt = build_system_prompt({"a": 1}, mode="inline")
    assert '"explanation" MUST warn' in prompt
