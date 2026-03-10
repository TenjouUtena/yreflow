"""Tests for WolferyConnection._format_roll — roll event formatting."""

import pytest

from yreflow.protocol.connection import WolferyConnection


class TestFormatRoll:
    def test_single_die_plus_modifier(self):
        j = {
            "result": [
                {"type": "std", "op": "+", "count": 1, "sides": 20, "dice": [14]},
                {"type": "mod", "op": "+", "value": 5},
            ],
            "total": 19,
        }
        out = WolferyConnection._format_roll(j)
        assert "rolls 1d20+5: 19" in out
        assert "d20\u00b714" in out  # d20·14
        assert "+ 5" in out

    def test_multi_dice_parenthesized(self):
        j = {
            "result": [
                {"type": "std", "op": "+", "count": 3, "sides": 6, "dice": [2, 5, 1]},
            ],
            "total": 8,
        }
        out = WolferyConnection._format_roll(j)
        assert "rolls 3d6: 8" in out
        assert "(d6\u00b72 + d6\u00b75 + d6\u00b71)" in out

    def test_minus_operator(self):
        j = {
            "result": [
                {"type": "std", "op": "+", "count": 1, "sides": 20, "dice": [15]},
                {"type": "std", "op": "-", "count": 2, "sides": 6, "dice": [3, 4]},
            ],
            "total": 8,
        }
        out = WolferyConnection._format_roll(j)
        assert "rolls 1d20-2d6: 8" in out
        assert " - (d6\u00b73 + d6\u00b74)" in out

    def test_complex_roll(self):
        """Full example from the Wolfery protocol."""
        j = {
            "result": [
                {"type": "std", "op": "+", "count": 1, "sides": 20, "dice": [9]},
                {"type": "mod", "op": "+", "value": 5},
                {"type": "std", "op": "+", "count": 4, "sides": 6, "dice": [1, 3, 6, 6]},
                {"type": "mod", "op": "+", "value": 3},
            ],
            "total": 33,
        }
        out = WolferyConnection._format_roll(j)
        assert "rolls 1d20+5+4d6+3: 33" in out
        assert "d20\u00b79" in out
        assert "(d6\u00b71 + d6\u00b73 + d6\u00b76 + d6\u00b76)" in out
        assert "[dim]" in out

    def test_modifier_only(self):
        j = {
            "result": [
                {"type": "mod", "op": "+", "value": 10},
            ],
            "total": 10,
        }
        out = WolferyConnection._format_roll(j)
        assert "10: 10" in out

    def test_empty_result(self):
        j = {"result": [], "total": 0}
        out = WolferyConnection._format_roll(j)
        assert ": 0" in out
