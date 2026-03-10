"""Tests for CommandHandler async handlers — verify correct API calls are sent."""

import pytest

from yreflow.commands.handler import CommandHandler, CommandResult
from yreflow.protocol.controlled_char import ControlledChar


@pytest.mark.asyncio
class TestSimpleHandlers:
    """Handlers that just send a single API call with no store lookups."""

    async def test_handle_say(self, handler, cc_thorn):
        result = await handler.handle_say("Hello world", cc_thorn)
        assert result.success
        method, params = handler.conn.sent[-1]
        assert method == "call.core.char.abc123def456.ctrl.say"
        assert params == {"msg": "Hello world"}

    async def test_handle_pose(self, handler, cc_thorn):
        result = await handler.handle_pose("waves.", cc_thorn)
        assert result.success
        method, params = handler.conn.sent[-1]
        assert method == "call.core.char.abc123def456.ctrl.pose"
        assert params == {"msg": "waves."}

    async def test_handle_roll(self, handler, cc_thorn):
        result = await handler.handle_roll("1d20+5", cc_thorn)
        assert result.success
        method, params = handler.conn.sent[-1]
        assert method == "call.roller.char.abc123def456.roll"
        assert params == {"roll": "1d20+5"}

    async def test_handle_roll_puppet(self, handler, cc_puppet):
        """Roll uses char_id, not ctrl_path."""
        result = await handler.handle_roll("2d6", cc_puppet)
        method, params = handler.conn.sent[-1]
        assert method == "call.roller.char.pup567tuv.roll"
        assert params == {"roll": "2d6"}

    async def test_handle_ooc_plain(self, handler, cc_thorn):
        result = await handler.handle_ooc({"msg": "brb", "pose": False}, cc_thorn)
        assert result.success
        method, params = handler.conn.sent[-1]
        assert method == "call.core.char.abc123def456.ctrl.ooc"
        assert params["msg"] == "brb"
        assert "pose" not in params  # pose key omitted when False

    async def test_handle_ooc_pose(self, handler, cc_thorn):
        result = await handler.handle_ooc({"msg": "shrugs", "pose": True}, cc_thorn)
        assert result.success
        method, params = handler.conn.sent[-1]
        assert params["pose"] is True

    async def test_handle_describe(self, handler, cc_thorn):
        result = await handler.handle_describe("A cat sits on the mat.", cc_thorn)
        assert result.success
        method, params = handler.conn.sent[-1]
        assert method == "call.core.char.abc123def456.ctrl.describe"
        assert params == {"msg": "A cat sits on the mat."}

    async def test_handle_home(self, handler, cc_thorn):
        result = await handler.handle_home(None, cc_thorn)
        assert result.notification == "Teleporting home..."
        method, params = handler.conn.sent[-1]
        assert method == "call.core.char.abc123def456.ctrl.teleportHome"

    async def test_handle_status_set(self, handler, cc_thorn):
        result = await handler.handle_status("Looking for RP", cc_thorn)
        method, params = handler.conn.sent[-1]
        assert method == "call.core.char.abc123def456.ctrl.set"
        assert params == {"status": "Looking for RP"}
        assert "set to" in result.notification.lower()

    async def test_handle_status_clear(self, handler, cc_thorn):
        result = await handler.handle_status("", cc_thorn)
        method, params = handler.conn.sent[-1]
        assert params == {"status": ""}
        assert "cleared" in result.notification.lower()

    async def test_handle_release(self, handler, cc_thorn):
        result = await handler.handle_release(None, cc_thorn)
        method, params = handler.conn.sent[-1]
        assert method == "call.core.char.abc123def456.ctrl.release"

    async def test_handle_stop_follow(self, handler, cc_thorn):
        result = await handler.handle_stop_follow("", cc_thorn)
        method, _ = handler.conn.sent[-1]
        assert method == "call.core.char.abc123def456.ctrl.stopFollow"

    async def test_handle_stop_lead_no_target(self, handler, cc_thorn):
        result = await handler.handle_stop_lead("", cc_thorn)
        method, _ = handler.conn.sent[-1]
        assert method == "call.core.char.abc123def456.ctrl.stopLead"


@pytest.mark.asyncio
class TestPuppetHandlers:
    """Verify puppet characters use the correct ctrl_path."""

    async def test_puppet_say(self, handler, cc_puppet):
        await handler.handle_say("Hello", cc_puppet)
        method, params = handler.conn.sent[-1]
        assert method == "call.core.char.abc123def456.puppet.pup567tuv.ctrl.say"

    async def test_puppet_pose(self, handler, cc_puppet):
        await handler.handle_pose("barks.", cc_puppet)
        method, _ = handler.conn.sent[-1]
        assert method == "call.core.char.abc123def456.puppet.pup567tuv.ctrl.pose"

    async def test_puppet_describe(self, handler, cc_puppet):
        await handler.handle_describe("Spark glows.", cc_puppet)
        method, _ = handler.conn.sent[-1]
        assert method == "call.core.char.abc123def456.puppet.pup567tuv.ctrl.describe"


@pytest.mark.asyncio
class TestDirectedHandlers:
    """Handlers that need name resolution from the store."""

    async def test_handle_whisper(self, handler, cc_thorn):
        result = await handler.handle_whisper({"msg": "Pip=hey there"}, cc_thorn)
        assert result.success
        method, params = handler.conn.sent[-1]
        assert method == "call.core.char.abc123def456.ctrl.whisper"
        assert params["charIds"] == ["ghi789jkl012"]
        assert params["msg"] == "hey there"
        assert handler.conn.directed_contacts[-1][2] == "w"

    async def test_handle_whisper_bad_format(self, handler, cc_thorn):
        result = await handler.handle_whisper({"msg": "no equals sign"}, cc_thorn)
        assert result.success is False

    async def test_handle_page(self, handler, cc_thorn):
        result = await handler.handle_page({"msg": "Pip=hello"}, cc_thorn)
        assert result.success
        method, params = handler.conn.sent[-1]
        assert method == "call.core.char.abc123def456.ctrl.message"
        assert handler.conn.directed_contacts[-1][2] == "m"

    async def test_handle_address(self, handler, cc_thorn):
        result = await handler.handle_address({"msg": "Pip=greetings"}, cc_thorn)
        assert result.success
        method, params = handler.conn.sent[-1]
        assert method == "call.core.char.abc123def456.ctrl.address"
        assert handler.conn.directed_contacts[-1][2] == "@"

    async def test_handle_whisper_unknown_name(self, handler, cc_thorn):
        result = await handler.handle_whisper({"msg": "Nobody=hey"}, cc_thorn)
        assert result.success is False
        assert "no name found" in result.notification.lower()


@pytest.mark.asyncio
class TestSocialHandlers:
    """Summon, join, lead, follow — need name resolution."""

    async def test_handle_summon(self, handler, cc_thorn):
        result = await handler.handle_summon("Pip", cc_thorn)
        assert result.success
        method, params = handler.conn.sent[-1]
        assert method == "call.core.char.abc123def456.ctrl.summon"
        assert params == {"charId": "ghi789jkl012"}
        assert "Pip" in result.notification

    async def test_handle_join(self, handler, cc_thorn):
        result = await handler.handle_join("Moss", cc_thorn)
        method, params = handler.conn.sent[-1]
        assert method == "call.core.char.abc123def456.ctrl.join"
        assert params == {"charId": "mno345pqr678"}

    async def test_handle_lead(self, handler, cc_thorn):
        result = await handler.handle_lead("Pip", cc_thorn)
        method, params = handler.conn.sent[-1]
        assert method == "call.core.char.abc123def456.ctrl.lead"

    async def test_handle_follow(self, handler, cc_thorn):
        result = await handler.handle_follow("Moss", cc_thorn)
        method, params = handler.conn.sent[-1]
        assert method == "call.core.char.abc123def456.ctrl.follow"

    async def test_handle_sweep_no_target(self, handler, cc_thorn):
        result = await handler.handle_sweep(None, cc_thorn)
        method, params = handler.conn.sent[-1]
        assert method == "call.core.char.abc123def456.ctrl.sweep"
        assert params == {}

    async def test_handle_sweep_with_target(self, handler, cc_thorn):
        result = await handler.handle_sweep("Pip", cc_thorn)
        method, params = handler.conn.sent[-1]
        assert params["charId"] == "ghi789jkl012"


@pytest.mark.asyncio
class TestResultOnlyHandlers:
    """Handlers that return special CommandResult flags without sending."""

    async def test_handle_profile_no_args(self, handler, cc_thorn):
        result = await handler.handle_profile("", cc_thorn)
        assert result.open_profile_select is True
        assert len(handler.conn.sent) == 0

    async def test_handle_settings(self, handler, cc_thorn):
        result = await handler.handle_settings("", cc_thorn)
        assert result.open_settings is True

    async def test_handle_nav(self, handler, cc_thorn):
        result = await handler.handle_nav("", cc_thorn)
        assert result.toggle_nav is True


@pytest.mark.asyncio
class TestProcessCommand:
    async def test_unknown_command(self, handler, cc_thorn):
        result = await handler.process_command("xyzzy magic", cc_thorn)
        assert result.success is False
        assert "unknown" in result.notification.lower()

    async def test_empty_command(self, handler, cc_thorn):
        result = await handler.process_command("", cc_thorn)
        assert result.success is True
        assert len(handler.conn.sent) == 0

    async def test_say_via_process(self, handler, cc_thorn):
        result = await handler.process_command("say Hello", cc_thorn)
        assert result.success
        method, params = handler.conn.sent[-1]
        assert method == "call.core.char.abc123def456.ctrl.say"
        assert params == {"msg": "Hello"}


@pytest.mark.asyncio
class TestGoHandler:
    """Verify go sends exitKey directly (no local exit lookup)."""

    async def test_go_sends_exit_key(self, handler, cc_thorn):
        result = await handler.handle_go("north", cc_thorn)
        assert result.success
        method, params = handler.conn.sent[-1]
        assert method == "call.core.char.abc123def456.ctrl.useExit"
        assert params == {"exitKey": "north"}

    async def test_go_sends_arbitrary_key(self, handler, cc_thorn):
        """Even unknown exit keys are sent — server validates."""
        result = await handler.handle_go("secret passage", cc_thorn)
        assert result.success
        _, params = handler.conn.sent[-1]
        assert params == {"exitKey": "secret passage"}


@pytest.mark.asyncio
class TestWhoisHandler:
    async def test_whois_resolves_name(self, handler, cc_thorn):
        result = await handler.handle_whois("Pip", cc_thorn)
        assert result.notification == "Looking up..."
        method, params = handler.conn.sent[-1]
        assert "getChar" in method
        assert params["charId"] == "ghi789jkl012"

    async def test_whois_unknown_name(self, handler, cc_thorn):
        result = await handler.handle_whois("Nobody", cc_thorn)
        assert result.success is False
        assert "no name found" in result.notification.lower()

    async def test_on_whois_result_publishes(self, handler, cc_thorn):
        """Verify _on_whois_result publishes whois data with expected fields."""
        received = []

        async def _capture(event_name, data, **kw):
            received.append(data)

        handler.conn.event_bus.subscribe(r"^whois\.result$", _capture)
        await handler._on_whois_result("ghi789jkl012")
        assert len(received) == 1
        data = received[0]
        assert data["type"] == "whois"
        assert data["char_id"] == "ghi789jkl012"
        assert "Pip" in data["name"]
        assert data["auth_token"] == "fake-token"
        assert "file_base_url" in data
        assert "cookie_name" in data


@pytest.mark.asyncio
class TestRulesHandler:
    async def test_rules_found_in_current_area(self, handler, cc_thorn, populated_store):
        """Room links to parent area which has rules."""
        # The room's area is area001xyz (Greenwood Village) which has rules
        result = await handler.handle_rules(None, cc_thorn)
        assert result.success
        assert result.look_data is not None
        assert result.look_data["type"] == "rules"
        assert "Be kind" in result.look_data["rules"]
        assert "Greenwood Village" in result.look_data["name"]

    async def test_rules_found_in_parent_area(self, handler, cc_thorn, populated_store):
        """Child area has no rules, parent area does — walks up."""
        # Point room to child area (area002abc) which has no rules
        room_id = "room001abc"
        room_model = populated_store.get(f"core.room.{room_id}")
        room_model["area"] = {"rid": "core.area.area002abc"}

        result = await handler.handle_rules(None, cc_thorn)
        assert result.success
        assert result.look_data is not None
        assert "Be kind" in result.look_data["rules"]

    async def test_no_rules_anywhere(self, handler, cc_thorn, populated_store):
        """Area with no rules and no parent → notification."""
        room_id = "room001abc"
        room_model = populated_store.get(f"core.room.{room_id}")
        room_model["area"] = {"rid": "core.area.area003def"}

        result = await handler.handle_rules(None, cc_thorn)
        assert "no area rules" in result.notification.lower()

    async def test_rules_no_room(self, handler, populated_store):
        """Character with no room pointer → failure."""
        cc_lost = ControlledChar(char_id="nonexistent999")
        result = await handler.handle_rules(None, cc_lost)
        assert result.success is False
        assert "room" in result.notification.lower()


@pytest.mark.asyncio
class TestWatchHandler:
    async def test_watch_local_name(self, handler, cc_thorn):
        result = await handler.handle_watch("Pip", cc_thorn)
        assert result.success
        assert "watching" in result.notification.lower()
        method, params = handler.conn.sent[-1]
        assert "addWatcher" in method
        assert params["charId"] == "abc123def456"

    async def test_watch_empty_name(self, handler, cc_thorn):
        result = await handler.handle_watch("", cc_thorn)
        assert result.success is False
        assert "usage" in result.notification.lower()

    async def test_watch_unknown_falls_back(self, handler, cc_thorn):
        """Unknown local name → server-side getChar lookup."""
        result = await handler.handle_watch("Nobody", cc_thorn)
        assert result.notification == "Looking up..."
        method, params = handler.conn.sent[-1]
        assert "getChar" in method
        assert params["charName"] == "Nobody"


@pytest.mark.asyncio
class TestUnwatchHandler:
    async def test_unwatch_local_name(self, handler, cc_thorn):
        result = await handler.handle_unwatch("Pip", cc_thorn)
        assert result.success
        assert "unwatched" in result.notification.lower()
        method, _ = handler.conn.sent[-1]
        assert "delete" in method

    async def test_unwatch_empty_name(self, handler, cc_thorn):
        result = await handler.handle_unwatch("", cc_thorn)
        assert result.success is False
        assert "usage" in result.notification.lower()

    async def test_unwatch_from_watch_list(self, handler, cc_thorn, populated_store):
        """_find_watched_char_id matches a name in the watch list."""
        player = handler.conn.player
        # Set up a watch entry for Pip
        await populated_store.set(
            f"note.player.{player}.watches",
            {"w1": {"rid": f"note.player.{player}.watch.ghi789jkl012"}},
        )
        await populated_store.set(
            f"note.player.{player}.watch.ghi789jkl012",
            {"char": {"rid": "core.char.ghi789jkl012"}},
        )
        found = handler._find_watched_char_id("Pip")
        assert found == "ghi789jkl012"


@pytest.mark.asyncio
class TestCharacterDataGathering:
    async def test_gather_uses_avatar_and_realm_fields(self, handler, cc_thorn):
        """Verify _gather_character_data returns avatar, file_base_url, cookie_name."""
        data = handler._gather_character_data("abc123def456")
        assert data["type"] == "character"
        assert "avatar" in data
        assert "image_url" not in data
        assert data["auth_token"] == "fake-token"
        assert data["file_base_url"] == "https://file.wolfery.com"
        assert data["cookie_name"] == "wolfery-auth-token"
