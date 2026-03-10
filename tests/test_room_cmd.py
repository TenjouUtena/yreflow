"""Tests for room command pattern matching, field resolution, and integration."""

import pytest

from yreflow.commands.room_cmd import (
    match_room_commands,
    parse_room_cmd_pattern,
    resolve_field_value,
)
from yreflow.commands.name_resolver import NameParseException


class TestParseRoomCmdPattern:
    def test_simple_pattern(self):
        pat = parse_room_cmd_pattern("pull lever")
        assert pat.match("pull lever")
        assert pat.match("Pull Lever")  # case-insensitive
        assert not pat.match("pull levers")
        assert not pat.match("pull")

    def test_pattern_with_placeholders(self):
        pat = parse_room_cmd_pattern("give <Character> = <Amount>")
        m = pat.match("give Pip = 5")
        assert m
        assert m.group("Character") == "Pip"
        assert m.group("Amount") == "5"

    def test_pattern_with_special_chars(self):
        pat = parse_room_cmd_pattern("press button (red)")
        assert pat.match("press button (red)")
        assert not pat.match("press button red")

    def test_single_placeholder(self):
        pat = parse_room_cmd_pattern("pet <Character>")
        m = pat.match("pet Thorn Ashvale")
        assert m
        assert m.group("Character") == "Thorn Ashvale"

    def test_trailing_placeholder_optional(self):
        pat = parse_room_cmd_pattern("examine <what>")
        # With argument
        m = pat.match("examine table")
        assert m
        assert m.group("what") == "table"
        # Without argument — trailing placeholder is optional
        m = pat.match("examine")
        assert m
        assert m.group("what") is None

    def test_trailing_placeholder_case_insensitive(self):
        pat = parse_room_cmd_pattern("smell <what>")
        m = pat.match("Smell")
        assert m
        assert m.group("what") is None
        m = pat.match("SMELL roses")
        assert m
        assert m.group("what") == "roses"


class TestResolveFieldValue:
    def test_char_type(self, populated_store):
        field_def = {"type": "char", "opts": {"inRoom": True, "state": "awake"}}
        result = resolve_field_value(populated_store, "Character", field_def, "Pip")
        assert result == {"charId": "ghi789jkl012"}

    def test_char_type_not_found(self, populated_store):
        field_def = {"type": "char"}
        with pytest.raises(NameParseException):
            resolve_field_value(populated_store, "Character", field_def, "Nobody")

    def test_integer_type(self, populated_store):
        field_def = {"type": "integer", "opts": {"min": 1}}
        assert resolve_field_value(populated_store, "Amount", field_def, "5") == {"value": 5}

    def test_integer_type_below_min(self, populated_store):
        field_def = {"type": "integer", "opts": {"min": 1}}
        with pytest.raises(ValueError, match="at least 1"):
            resolve_field_value(populated_store, "Amount", field_def, "0")

    def test_integer_type_invalid(self, populated_store):
        field_def = {"type": "integer"}
        with pytest.raises(ValueError):
            resolve_field_value(populated_store, "Amount", field_def, "abc")

    def test_unknown_type(self, populated_store):
        field_def = {"type": "text"}
        assert resolve_field_value(populated_store, "Note", field_def, " hello ") == {"value": "hello"}

    def test_text_type_none(self, populated_store):
        """None raw value (from optional trailing group) → empty string."""
        field_def = {"type": "text"}
        assert resolve_field_value(populated_store, "what", field_def, None) == {"value": ""}


@pytest.mark.asyncio
class TestMatchRoomCommands:
    async def test_simple_match(self, populated_store):
        result = match_room_commands(
            populated_store, "core.char.abc123def456", "pull lever"
        )
        assert result is not None
        cmd_id, values, cmd_data = result
        assert cmd_id == "cmd001simple"
        assert values is None
        assert cmd_data["pattern"] == "pull lever"

    async def test_match_with_fields(self, populated_store):
        result = match_room_commands(
            populated_store, "core.char.abc123def456", "give Pip = 5"
        )
        assert result is not None
        cmd_id, values, cmd_data = result
        assert cmd_id == "cmd002fields"
        assert values == {"Character": {"charId": "ghi789jkl012"}, "Amount": {"value": 5}}

    async def test_no_match(self, populated_store):
        result = match_room_commands(
            populated_store, "core.char.abc123def456", "dance"
        )
        assert result is None

    async def test_case_insensitive(self, populated_store):
        result = match_room_commands(
            populated_store, "core.char.abc123def456", "PULL LEVER"
        )
        assert result is not None
        assert result[0] == "cmd001simple"

    async def test_priority_ordering(self, populated_store):
        """Higher priority commands should match first."""
        result = match_room_commands(
            populated_store, "core.char.abc123def456", "pull lever"
        )
        # cmd001simple has priority 100, should win
        assert result[0] == "cmd001simple"

    async def test_bad_char_name_raises(self, populated_store):
        with pytest.raises(NameParseException):
            match_room_commands(
                populated_store, "core.char.abc123def456", "give Nobody = 5"
            )

    async def test_bad_integer_raises(self, populated_store):
        with pytest.raises(ValueError):
            match_room_commands(
                populated_store, "core.char.abc123def456", "give Pip = abc"
            )

    async def test_text_field_with_value(self, populated_store):
        result = match_room_commands(
            populated_store, "core.char.abc123def456", "examine table"
        )
        assert result is not None
        cmd_id, values, _ = result
        assert cmd_id == "cmd003examine"
        assert values == {"what": {"value": "table"}}

    async def test_text_field_blank(self, populated_store):
        """Bare command with no argument sends empty string for text field."""
        result = match_room_commands(
            populated_store, "core.char.abc123def456", "examine"
        )
        assert result is not None
        cmd_id, values, _ = result
        assert cmd_id == "cmd003examine"
        assert values == {"what": {"value": ""}}


@pytest.mark.asyncio
class TestProcessCommandRoomCmd:
    """Integration: room commands via process_command fallback."""

    async def test_room_cmd_via_process_command(self, handler, cc_thorn):
        result = await handler.process_command("pull lever", cc_thorn)
        assert result.success
        method, params = handler.conn.sent[-1]
        assert method == "call.core.char.abc123def456.ctrl.execRoomCmd"
        assert params == {"cmdId": "cmd001simple", "values": None}

    async def test_room_cmd_with_fields_via_process_command(self, handler, cc_thorn):
        result = await handler.process_command("give Pip = 5", cc_thorn)
        assert result.success
        method, params = handler.conn.sent[-1]
        assert method == "call.core.char.abc123def456.ctrl.execRoomCmd"
        assert params == {
            "cmdId": "cmd002fields",
            "values": {"Character": {"charId": "ghi789jkl012"}, "Amount": {"value": 5}},
        }

    async def test_builtin_not_shadowed(self, handler, cc_thorn):
        """Built-in commands should still work, not be caught as room cmds."""
        result = await handler.process_command("say hello", cc_thorn)
        assert result.success
        method, _ = handler.conn.sent[-1]
        assert method == "call.core.char.abc123def456.ctrl.say"

    async def test_unknown_still_fails(self, handler, cc_thorn):
        result = await handler.process_command("xyzzy", cc_thorn)
        assert not result.success
        assert "Unknown command" in result.notification

    async def test_bad_field_returns_error(self, handler, cc_thorn):
        result = await handler.process_command("give Nobody = 5", cc_thorn)
        assert not result.success

    async def test_text_field_blank_via_process_command(self, handler, cc_thorn):
        result = await handler.process_command("examine", cc_thorn)
        assert result.success
        method, params = handler.conn.sent[-1]
        assert method == "call.core.char.abc123def456.ctrl.execRoomCmd"
        assert params == {
            "cmdId": "cmd003examine",
            "values": {"what": {"value": ""}},
        }

    async def test_do_alias_simple(self, handler, cc_thorn):
        """'do pull lever' should work like 'pull lever'."""
        result = await handler.process_command("do pull lever", cc_thorn)
        assert result.success
        method, params = handler.conn.sent[-1]
        assert method == "call.core.char.abc123def456.ctrl.execRoomCmd"
        assert params == {"cmdId": "cmd001simple", "values": None}

    async def test_do_alias_with_fields(self, handler, cc_thorn):
        """'do give Pip = 5' should work like 'give Pip = 5'."""
        result = await handler.process_command("do give Pip = 5", cc_thorn)
        assert result.success
        method, params = handler.conn.sent[-1]
        assert method == "call.core.char.abc123def456.ctrl.execRoomCmd"
        assert params == {
            "cmdId": "cmd002fields",
            "values": {"Character": {"charId": "ghi789jkl012"}, "Amount": {"value": 5}},
        }

    async def test_do_alias_case_insensitive(self, handler, cc_thorn):
        """'Do pull lever' and 'DO pull lever' should both work."""
        result = await handler.process_command("Do pull lever", cc_thorn)
        assert result.success
        assert handler.conn.sent[-1][1] == {"cmdId": "cmd001simple", "values": None}

    async def test_do_alone_not_matched(self, handler, cc_thorn):
        """Bare 'do' should not crash or match."""
        result = await handler.process_command("do", cc_thorn)
        assert not result.success

    async def test_puppet_room_cmd(self, handler, cc_puppet, populated_store):
        """Puppet should use puppet ctrl_path for room commands."""
        # Set up puppet's inRoom pointer
        await populated_store.set(
            "core.char.abc123def456.puppet.pup567tuv.owned",
            {"inRoom": {"rid": "core.room.room001abc"}},
        )
        result = await handler.process_command("pull lever", cc_puppet)
        assert result.success
        method, params = handler.conn.sent[-1]
        assert method == "call.core.char.abc123def456.puppet.pup567tuv.ctrl.execRoomCmd"
        assert params == {"cmdId": "cmd001simple", "values": None}
