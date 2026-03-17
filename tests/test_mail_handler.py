"""Tests for MailManager — mail command handlers."""

import pytest

from yreflow.commands.mail_handler import MailManager
from yreflow.protocol.controlled_char import ControlledChar


@pytest.fixture
def mail(mock_conn, populated_store):
    return MailManager(mock_conn, populated_store)


@pytest.fixture
def cc_thorn():
    return ControlledChar(char_id="abc123def456")


@pytest.mark.asyncio
class TestMailDispatch:
    async def test_empty_lists_inbox(self, mail, cc_thorn):
        result = await mail.process_command("", cc_thorn)
        assert result.notification == "Fetching mail..."
        method, _ = mail.conn.sent[-1]
        assert "inbox?offset=0" in method

    async def test_send_dispatches(self, mail, cc_thorn):
        result = await mail.process_command("send Pip=hello", cc_thorn)
        assert result.notification == "Sending mail..."

    async def test_read_requires_number(self, mail, cc_thorn):
        result = await mail.process_command("read abc", cc_thorn)
        assert result.success is False
        assert "number" in result.notification.lower()

    async def test_more_requires_prior_list(self, mail, cc_thorn):
        result = await mail.process_command("more", cc_thorn)
        assert result.success is False

    async def test_unknown_subcommand(self, mail, cc_thorn):
        result = await mail.process_command("frobnicate", cc_thorn)
        assert result.success is False
        assert "usage" in result.notification.lower()


@pytest.mark.asyncio
class TestMailSend:
    async def test_send_resolves_name(self, mail, cc_thorn):
        result = await mail.process_command("send Pip=Hello friend", cc_thorn)
        assert result.success
        method, params = mail.conn.sent[-1]
        assert method == f"call.mail.player.{mail.conn.player}.inbox.send"
        assert params["toCharId"] == "ghi789jkl012"
        assert params["fromCharId"] == "abc123def456"
        assert params["text"] == "Hello friend"

    async def test_send_full_name(self, mail, cc_thorn):
        result = await mail.process_command("send Pip Meadowbrook = Hey", cc_thorn)
        assert result.success
        _, params = mail.conn.sent[-1]
        assert params["toCharId"] == "ghi789jkl012"

    async def test_send_unknown_name(self, mail, cc_thorn):
        result = await mail.process_command("send Nobody = hey", cc_thorn)
        assert result.success is False
        assert "no name found" in result.notification.lower()

    async def test_send_missing_equals(self, mail, cc_thorn):
        result = await mail.process_command("send Pip hello", cc_thorn)
        assert result.success is False

    async def test_send_empty_message(self, mail, cc_thorn):
        result = await mail.process_command("send Pip =  ", cc_thorn)
        assert result.success is False
        assert "empty" in result.notification.lower()

    async def test_send_callback(self, mail, cc_thorn):
        """Verify the send callback publishes a notification."""
        await mail.process_command("send Pip = test", cc_thorn)
        # Trigger the registered callback
        msg_id = list(mail.conn.message_waits.keys())[-1]
        callback = mail.conn.message_waits[msg_id]
        await callback({"toChar": {"name": "Pip", "surname": "Seedling"}})
        # EventBus should have received the notification
        # (we just verify it doesn't raise)


@pytest.mark.asyncio
class TestMailRead:
    async def test_read_empty_inbox(self, mail, cc_thorn):
        result = await mail.process_command("read 1", cc_thorn)
        assert result.success is False
        assert "#1" in result.notification

    async def test_read_out_of_range(self, mail, cc_thorn):
        mail.inbox = [{"rid": "mail.player.x.message.m1", "read": None}]
        result = await mail.process_command("read 5", cc_thorn)
        assert result.success is False

    async def test_read_valid(self, mail, cc_thorn, populated_store):
        msg_rid = "mail.message.msg001"
        env_rid = "mail.player.testplayer.message.msg001"
        await populated_store.set(msg_rid, {"text": "Hello there!", "ooc": False, "pose": False})
        mail.inbox = [
            {
                "rid": env_rid,
                "from": {"data": {"name": "Pip", "surname": "Seedling"}},
                "to": {"data": {"name": "Thorn", "surname": "Ashvale"}},
                "message": {"rid": msg_rid},
                "read": None,
                "received": 1772978050762,
            }
        ]
        result = await mail.process_command("read 1", cc_thorn)
        assert result.success
        assert "Hello there!" in result.display_text
        assert "Pip Seedling" in result.display_text
        # Should have sent a read call
        method, _ = mail.conn.sent[-1]
        assert method == f"call.{env_rid}.read"


@pytest.mark.asyncio
class TestMailList:
    async def test_list_subscribes_when_not_cached(self, mail, cc_thorn):
        """When store has no inbox data, sends a subscribe."""
        result = await mail.process_command("", cc_thorn)
        assert result.notification == "Fetching mail..."
        method, _ = mail.conn.sent[-1]
        assert method == f"subscribe.mail.player.{mail.conn.player}.inbox?offset=0&limit=11"

    async def test_list_uses_cached_data(self, mail, cc_thorn, populated_store):
        """When inbox data is already in the store, display immediately."""
        player = mail.conn.player
        env_rid = f"mail.player.{player}.message.msg001"
        store_key = f"mail.player.{player}.inbox?offset=0&limit=11"

        await populated_store.set(env_rid, {
            "from": {"data": {"name": "Pip", "surname": "Seedling"}},
            "to": {"data": {"name": "Thorn", "surname": "Ashvale"}},
            "message": {"rid": "mail.message.msg001"},
            "read": None,
            "received": 1772978050762,
        })
        await populated_store.set(store_key, [{"rid": env_rid}], collection=True)

        result = await mail.process_command("", cc_thorn)
        # Should return display_text immediately, no subscribe sent.
        assert result.display_text is not None
        assert "Pip Seedling" in result.display_text
        assert len(mail.conn.sent) == 0
        assert len(mail.inbox) == 1
        assert mail.inbox[0]["rid"] == env_rid

    async def test_list_watch_on_fresh_subscribe(self, mail, cc_thorn, populated_store):
        """When store has no data, subscribe is sent and watch callback
        populates the inbox when data arrives."""
        player = mail.conn.player
        env_rid = f"mail.player.{player}.message.msg001"
        store_key = f"mail.player.{player}.inbox?offset=0&limit=11"

        # First set envelope model data (arrives in models section).
        await populated_store.set(env_rid, {
            "from": {"data": {"name": "Pip", "surname": "Seedling"}},
            "to": {"data": {"name": "Thorn", "surname": "Ashvale"}},
            "message": {"rid": "mail.message.msg001"},
            "read": None,
            "received": 1772978050762,
        })

        # Issue the command — no cached collection, so subscribes.
        result = await mail.process_command("", cc_thorn)
        assert result.notification == "Fetching mail..."
        assert mail._pending_inbox is True

        # Simulate the collection arriving (triggers the watch).
        await populated_store.set(store_key, [{"rid": env_rid}], collection=True)

        assert mail._pending_inbox is False
        assert len(mail.inbox) == 1


@pytest.mark.asyncio
class TestUnreadCheck:
    async def test_no_unread(self, mail):
        assert mail.check_unread() == 0

    async def test_with_unread(self, mail, populated_store):
        player = mail.conn.player
        await populated_store.set(f"mail.player.{player}.unread", {
            "msg001": {"rid": f"mail.player.{player}.message.msg001", "soft": True},
            "msg002": {"rid": f"mail.player.{player}.message.msg002", "soft": True},
        })
        assert mail.check_unread() == 2

    async def test_deleted_not_counted(self, mail, populated_store):
        player = mail.conn.player
        await populated_store.set(f"mail.player.{player}.unread", {
            "msg001": {"rid": f"mail.player.{player}.message.msg001", "soft": True},
            "msg002": {"action": "delete"},
        })
        assert mail.check_unread() == 1


class TestFormatting:
    def test_format_inbox_empty(self, mail):
        result = mail._format_inbox([], start_index=1)
        assert "empty" in result.lower()

    def test_format_inbox_with_messages(self, mail):
        messages = [
            {
                "from": {"data": {"name": "Pip", "surname": "Seedling"}},
                "received": 1772978050762,
                "read": None,
            },
            {
                "from": {"data": {"name": "Moss", "surname": "Greenvale"}},
                "received": 1772978000000,
                "read": 1772978100000,
            },
        ]
        result = mail._format_inbox(messages, start_index=1, has_more=True)
        assert "Pip Seedling" in result
        assert "Moss Greenvale" in result
        assert "[NEW]" in result
        assert "mail more" in result.lower()

    def test_format_inbox_no_more(self, mail):
        messages = [
            {
                "from": {"data": {"name": "Pip", "surname": "Seedling"}},
                "received": 1772978050762,
                "read": 1772978100000,
            },
        ]
        result = mail._format_inbox(messages, start_index=1, has_more=False)
        assert "mail more" not in result.lower()

    def test_format_message(self, mail):
        envelope = {
            "from": {"data": {"name": "Pip", "surname": "Seedling"}},
            "to": {"data": {"name": "Thorn", "surname": "Ashvale"}},
            "received": 1772978050762,
        }
        msg_data = {"text": "Hello friend!"}
        result = mail._format_message(envelope, msg_data)
        assert "Pip Seedling" in result
        assert "Thorn Ashvale" in result
        assert "Hello friend!" in result

    def test_format_message_pose(self, mail):
        """Pose messages (starting with ':') prepend the sender's name."""
        envelope = {
            "from": {"data": {"name": "Pip", "surname": "Seedling"}},
            "to": {"data": {"name": "Thorn", "surname": "Ashvale"}},
            "received": 1772978050762,
        }
        msg_data = {"text": ":waves cheerfully."}
        result = mail._format_message(envelope, msg_data)
        assert "Pip Seedling" in result
        # The pose text should appear without the leading colon
        assert "waves cheerfully." in result
        # Should NOT contain the raw ':waves'
        assert ":waves" not in result

    def test_format_message_url(self, mail):
        """URLs with descriptions should be formatted, not shown raw."""
        envelope = {
            "from": {"data": {"name": "Pip", "surname": "Seedling"}},
            "to": {"data": {"name": "Thorn", "surname": "Ashvale"}},
            "received": 1772978050762,
        }
        msg_data = {"text": "Check this [cool site](https://example.com) out!"}
        result = mail._format_message(envelope, msg_data)
        # The link text should be present
        assert "cool site" in result
