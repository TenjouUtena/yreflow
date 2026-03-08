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
