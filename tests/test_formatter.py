"""TOML-driven test suite for yreflow.formatter.format_message.

Test cases live in formatter_cases.toml alongside this file.
Each [[case]] entry specifies an input string and expected output,
plus optional formatter kwargs (superscript_style, etc.).
"""

import tomllib
from pathlib import Path

import pytest

from yreflow.formatter import format_message

CASES_FILE = Path(__file__).with_name("formatter_cases.toml")

def _load_cases() -> list[dict]:
    with open(CASES_FILE, "rb") as f:
        data = tomllib.load(f)
    return data["case"]


_CASES = _load_cases()


def _case_id(case: dict) -> str:
    return case.get("description", case["input"][:40])


@pytest.mark.parametrize("case", _CASES, ids=[_case_id(c) for c in _CASES])
def test_format_message(case: dict):
    if case.get("xfail"):
        pytest.xfail(reason=case.get("description", "known failure"))

    kwargs = {}
    for key in ("superscript_style", "superscript_color",
                "subscript_style", "subscript_color"):
        if key in case:
            kwargs[key] = case[key]

    result = format_message(case["input"], **kwargs)
    assert result == case["expected"], (
        f"\n  input:    {case['input']!r}"
        f"\n  expected: {case['expected']!r}"
        f"\n  got:      {result!r}"
    )
