"""Tests for ConsoleHandler — realm and create commands."""

from unittest.mock import patch

import pytest

from yreflow.commands.console_handler import ConsoleHandler


@pytest.mark.asyncio
class TestRealmCommand:
    async def test_realm_no_args(self, mock_conn, populated_store):
        ch = ConsoleHandler(mock_conn, populated_store)
        result = await ch.process_command("realm")
        assert result.success
        assert "wolfery" in result.display_text.lower()

    async def test_realm_list(self, mock_conn, populated_store):
        ch = ConsoleHandler(mock_conn, populated_store)
        result = await ch.process_command("realm list")
        assert "wolfery" in result.display_text.lower()
        assert "aurellion" in result.display_text.lower()
        assert "(active)" in result.display_text

    async def test_realm_set(self, mock_conn, populated_store):
        ch = ConsoleHandler(mock_conn, populated_store)
        with patch("yreflow.config.save_preference") as mock_save:
            result = await ch.process_command("realm aurellion")
            mock_save.assert_called_once_with("realm", "aurellion")
        assert "reconnect" in result.display_text.lower()


@pytest.mark.asyncio
class TestCreateCommand:
    async def test_create_character(self, mock_conn, populated_store):
        ch = ConsoleHandler(mock_conn, populated_store)
        result = await ch.process_command("create character Willow Birch")
        assert result.success
        method, params = mock_conn.sent[-1]
        assert "createChar" in method
        assert params == {"name": "Willow", "surname": "Birch"}

    async def test_create_character_missing_name(self, mock_conn, populated_store):
        ch = ConsoleHandler(mock_conn, populated_store)
        result = await ch.process_command("create character Willow")
        assert result.success is False
        assert "usage" in result.notification.lower()

    async def test_create_no_login(self, mock_conn, populated_store):
        mock_conn.player = None
        ch = ConsoleHandler(mock_conn, populated_store)
        result = await ch.process_command("create character Willow Birch")
        assert result.success is False
        assert "not logged in" in result.notification.lower()

    async def test_create_no_subcommand(self, mock_conn, populated_store):
        ch = ConsoleHandler(mock_conn, populated_store)
        result = await ch.process_command("create")
        assert result.success is False
