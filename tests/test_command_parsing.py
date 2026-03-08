"""TOML-driven test suite for CommandHandler.detect_command_type.

Each [[case]] in command_cases.toml specifies input text and expected style.
"""

import tomllib
from pathlib import Path

import pytest

from yreflow.commands.handler import CommandHandler


CASES_FILE = Path(__file__).parent / "data" / "command_cases.toml"


def _load_cases() -> list[dict]:
    with open(CASES_FILE, "rb") as f:
        data = tomllib.load(f)
    return data["case"]


_CASES = _load_cases()


def _case_id(case: dict) -> str:
    return case.get("description", case["input"][:40])


# CommandHandler needs conn and store but detect_command_type doesn't use them
_handler = CommandHandler(None, None)


@pytest.mark.parametrize("case", _CASES, ids=[_case_id(c) for c in _CASES])
def test_detect_command_type(case: dict):
    style, content, func = _handler.detect_command_type(case["input"])
    assert style == case["expected_style"], (
        f"\n  input:    {case['input']!r}"
        f"\n  expected: {case['expected_style']!r}"
        f"\n  got:      {style!r}"
    )
    assert func is not None, f"No handler found for {case['input']!r}"


def test_unknown_command():
    style, content, func = _handler.detect_command_type("xyzzy magic")
    assert func is None
