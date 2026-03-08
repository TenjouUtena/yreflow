"""Tests for parse_name fuzzy character matching."""

import pytest

from yreflow.commands.name_resolver import parse_name, NameParseException
from yreflow.protocol.model_store import ModelStore


@pytest.fixture
def char_store():
    """Synchronously build a store with test characters."""
    store = ModelStore()
    # Manually populate without async set()
    store.models = {
        "core": {
            "char": {
                "abc123": {
                    "id": "abc123",
                    "name": "Thorn",
                    "surname": "Ashvale",
                    "awake": True,
                },
                "ghi789": {
                    "id": "ghi789",
                    "name": "Pip",
                    "surname": "Meadowbrook",
                    "awake": True,
                },
                "mno345": {
                    "id": "mno345",
                    "name": "Moss",
                    "surname": "Ferndale",
                    "awake": True,
                },
                "stu901": {
                    "id": "stu901",
                    "name": "Wren",
                    "surname": "Ashvale",
                    "awake": False,
                },
            }
        }
    }
    return store


class TestParseName:
    def test_exact_match(self, char_store):
        result = parse_name(char_store, "Thorn Ashvale")
        assert result == "abc123"

    def test_prefix_match(self, char_store):
        result = parse_name(char_store, "Pip")
        assert result == "ghi789"

    def test_case_insensitive(self, char_store):
        result = parse_name(char_store, "thorn")
        assert result == "abc123"

    def test_no_match_raises(self, char_store):
        with pytest.raises(NameParseException, match="No name found"):
            parse_name(char_store, "Nonexistent")

    def test_ambiguous_raises(self, char_store):
        # Both "Thorn Ashvale" and sleeping "Wren Ashvale" start with "Ashvale"
        # But Wren is asleep so only Thorn matches — need a different ambiguous case
        # Thorn and Moss both start with no common prefix... let's use first-letter
        # Actually: we need two awake chars with overlapping prefixes
        # Let's add a char manually
        char_store.models["core"]["char"]["extra"] = {
            "id": "extra",
            "name": "Thorn",
            "surname": "Bramble",
            "awake": True,
        }
        with pytest.raises(NameParseException, match="Too many"):
            parse_name(char_store, "Thorn")

    def test_wants_name(self, char_store):
        result = parse_name(char_store, "Pip", wants="name")
        assert result == "Pip Meadowbrook"

    def test_sleeping_filtered(self, char_store):
        with pytest.raises(NameParseException, match="No name found"):
            parse_name(char_store, "Wren", awake=True)

    def test_sleeping_included_when_awake_false(self, char_store):
        result = parse_name(char_store, "Wren", awake=False)
        assert result == "stu901"

    def test_wants_list(self, char_store):
        char_store.models["core"]["char"]["extra"] = {
            "id": "extra",
            "name": "Thorn",
            "surname": "Bramble",
            "awake": True,
        }
        result = parse_name(char_store, "Thorn", wants_list=True)
        assert set(result) == {"abc123", "extra"}
