"""TOML-driven test suite for format_line message formatting.

Each [[case]] in message_display_cases.toml specifies input params and
expected substrings in the Rich markup output.
"""

import tomllib
from pathlib import Path

import pytest

from yreflow.ui.format_line import format_line

CASES_FILE = Path(__file__).parent / "data" / "message_display_cases.toml"


def _load_cases() -> list[dict]:
    with open(CASES_FILE, "rb") as f:
        data = tomllib.load(f)
    return data["case"]


_CASES = _load_cases()


def _case_id(case: dict) -> str:
    return case.get("description", f"{case['style']}_{case['sender']}")


@pytest.mark.parametrize("case", _CASES, ids=[_case_id(c) for c in _CASES])
def test_format_line(case: dict):
    result = format_line(
        style=case["style"],
        sender=case["sender"],
        msg=case["msg"],
        target_name=case.get("target_name", ""),
        has_pose=case.get("has_pose", False),
        is_ooc=case.get("is_ooc", False),
        timestamp=case.get("timestamp", ""),
        focus_color=case.get("focus_color"),
    )

    if "expected_contains" in case:
        assert case["expected_contains"] in result, (
            f"\n  expected to contain: {case['expected_contains']!r}"
            f"\n  got: {result!r}"
        )

    if "expected_contains_2" in case:
        assert case["expected_contains_2"] in result, (
            f"\n  expected to contain: {case['expected_contains_2']!r}"
            f"\n  got: {result!r}"
        )

    if "expected_not_contains" in case:
        assert case["expected_not_contains"] not in result, (
            f"\n  expected NOT to contain: {case['expected_not_contains']!r}"
            f"\n  got: {result!r}"
        )
