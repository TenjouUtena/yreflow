"""Controller: glue between protocol layer and UI.

Subscribes to EventBus events from the protocol and routes them to UI calls.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

log = logging.getLogger("yreflow.controller")

from .protocol.events import EventBus
from .protocol.model_store import ModelStore
from .protocol.connection import WolferyConnection
from .protocol.controlled_char import ControlledChar
from .protocol.http_auth import obtain_token
from .commands.handler import CommandHandler, CommandResult
from .commands.console_handler import ConsoleHandler
from .plugins import PluginManager
from .url_catcher import UrlCatcher
from .config import load_config, save_token, clear_token

if TYPE_CHECKING:
    from .ui.base import UIProtocol


class Controller:
    def __init__(self, config: dict, ui: UIProtocol):
        self.ui = ui
        self.event_bus = EventBus()
        self.store = ModelStore(event_bus=self.event_bus)
        self.connection = WolferyConnection(config, self.store, self.event_bus)
        self.commands = CommandHandler(self.connection, self.store)
        self.console_commands = ConsoleHandler(self.connection, self.store)
        self.url_catcher = UrlCatcher(self.event_bus)
        self.plugin_manager = PluginManager(self.event_bus, self.store, self.connection)
        self._reconnect_delay = 5.0

        # Subscribe to protocol events
        # NOTE: message.received is subscribed in start() so plugins
        # (which load first) can intercept messages via publish_interceptable.
        self.event_bus.subscribe(r"^notification$", self._on_notification)
        self.event_bus.subscribe(r"^room\.changed$", self._on_room_changed)
        self.event_bus.subscribe(r"^watches\.changed$", self._on_watches_changed)
        self.event_bus.subscribe(r"^characters\.changed$", self._on_characters_changed)
        self.event_bus.subscribe(r"^character\.tab\.needed$", self._on_tab_needed)
        self.event_bus.subscribe(r"^raw\.message$", self._on_raw_message)
        self.event_bus.subscribe(r"^connection\.closed$", self._on_connection_closed)
        self.event_bus.subscribe(r"^connection\.established$", self._on_connection_established)
        self.event_bus.subscribe(r"^connection\.failed$", self._on_connection_failed)
        self.event_bus.subscribe(r"^look\.result$", self._on_look_result)
        self.event_bus.subscribe(r"^look\.update$", self._on_look_update)
        self.event_bus.subscribe(r"^whois\.result$", self._on_whois_result)
        self.event_bus.subscribe(r"^auth\.failed$", self._on_auth_failed)
        self.event_bus.subscribe(r"^auth\.token_expired$", self._on_token_expired)
        self.event_bus.subscribe(r"^system\.text$", self._on_system_text)
        self.event_bus.subscribe(r"^protocol\.error$", self._on_protocol_error)
        self.event_bus.subscribe(r"^mail\.result$", self._on_mail_result)
        self.event_bus.subscribe(r"^autocomplete\.results$", self._on_autocomplete_results)

        # Rebuild sidebar when any character's LFRP or idle status changes
        self.store.add_watch(r"^core\.char\.[^.]+\.lfrp", self._on_char_changed)
        self.store.add_watch(r"^core\.char\.[^.]+\.idle", self._on_char_changed)

        # Notify unread mail on first load after connect
        self._mail_notified = False
        self.store.add_watch(r"^mail\.player\.\w+\.unread", self._on_mail_unread)

    async def start(self) -> None:
        await self.plugin_manager.discover_builtin()
        self.event_bus.subscribe(r"^message\.received$", self._on_message)
        await self.connection.connect()

    async def start_with_credentials(self, username: str, password: str) -> None:
        """Obtain a token via HTTP, save it, then connect with it."""
        token = await obtain_token(username, password)
        save_token(token)
        self.connection.token = token
        self.connection.auth_mode = "token"
        await self.plugin_manager.discover_builtin()
        self.event_bus.subscribe(r"^message\.received$", self._on_message)
        await self.connection.connect()

    async def handle_command(self, command: str, ctrl_id: str) -> CommandResult:
        cc = self.connection.get_controlled_char(ctrl_id)
        if cc is None:
            cc = ControlledChar(char_id=ctrl_id)
        return await self.commands.process_command(command, cc)

    async def handle_console_command(self, command: str) -> CommandResult:
        return await self.console_commands.process_command(command)

    # --- Event handlers ---

    async def _on_message(self, event_name: str, message: dict, style: str, character: str, **kw) -> None:
        await self.ui.display_message(message, style, character)

    async def _on_notification(self, event_name: str, text: str, character: str | None = None, **kw) -> None:
        await self.ui.notify(text, character=character)

    async def _on_room_changed(self, event_name: str, **kw) -> None:
        await self.ui.update_room()

    async def _on_watches_changed(self, event_name: str, **kw) -> None:
        await self.ui.update_watch_list()

    async def _on_characters_changed(self, event_name: str, **kw) -> None:
        """Remove tabs for characters no longer under player control."""
        if not self.connection.player:
            return
        try:
            models = self.store.get(
                f"core.player.{self.connection.player}.ctrls._value"
            )
            current_ctrl_ids = set()
            for x in models:
                try:
                    cc = WolferyConnection._parse_ctrl_rid(x["rid"])
                    current_ctrl_ids.add(cc.ctrl_id)
                except (KeyError, IndexError):
                    continue
        except KeyError:
            current_ctrl_ids = set()

        known = self.ui.get_known_characters()
        for ctrl_id in known - current_ctrl_ids:
            if ctrl_id.startswith("__"):
                continue
            await self.ui.remove_character_tab(ctrl_id)

    async def _on_tab_needed(self, event_name: str, character: str, **kw) -> None:
        await self.ui.ensure_character_tab(character)

    async def _on_raw_message(self, event_name: str, text: str, **kw) -> None:
        await self.ui.log_raw(text)
        await self.ui.blink_connection_indicator()

    async def _on_connection_established(self, event_name: str, **kw) -> None:
        self._reconnect_delay = 5.0
        self._mail_notified = False
        await self.ui.update_connection_status("connected")

    async def _on_connection_closed(self, event_name: str, **kw) -> None:
        await self.ui.update_connection_status("disconnected")
        await self.ui.display_system_text("Connection closed.")
        if load_config().get("auto_reconnect", False):
            await self.ui.update_connection_status("reconnecting")
            delay = self._reconnect_delay
            await self.ui.display_system_text(f"Reconnecting in {delay:.0f} seconds...")
            await asyncio.sleep(delay)
            self._reconnect_delay = min(delay * 2, 120.0)
            await self.connection.connect()

    async def _on_connection_failed(self, event_name: str, **kw) -> None:
        await self.ui.update_connection_status("disconnected")
        realm_name = self.connection.realm.key.capitalize()
        await self.ui.display_system_text(f"Could not connect to {realm_name}!")

    async def _on_look_result(self, event_name: str, data: dict, **kw) -> None:
        log.debug("_on_look_result() called, type=%s, name=%s",
                  data.get("type"), data.get("name"))
        self._active_look_screen = await self.ui.display_look(
            data, on_dismiss=self._on_look_dismissed
        )
        log.debug("_on_look_result() screen=%s (id=%s)",
                  self._active_look_screen, id(self._active_look_screen))

    async def _on_look_update(self, event_name: str, data: dict, **kw) -> None:
        screen = getattr(self, "_active_look_screen", None)
        log.debug("_on_look_update() called, screen=%s (id=%s)",
                  screen, id(screen) if screen else None)
        if screen is not None:
            await screen.update_data(data)

    async def _on_whois_result(self, event_name: str, data: dict, **kw) -> None:
        await self.ui.display_look(data, on_dismiss=None)

    def _on_look_dismissed(self) -> None:
        self._active_look_screen = None
        self.commands._remove_look_watch()
        # Tell server to stop looking at the target (look at self instead).
        ctrl_id = getattr(self.ui, "active_character", None)
        if ctrl_id:
            cc = self.connection.get_controlled_char(ctrl_id)
            if cc:
                asyncio.create_task(self.connection.stop_look_at(cc))

    async def _on_auth_failed(self, event_name: str, error: str, **kw) -> None:
        await self.ui.show_login(error=error)

    async def _on_system_text(self, event_name: str, text: str, **kw) -> None:
        await self.ui.display_system_text(text)

    async def _on_protocol_error(self, event_name: str, data: dict, **kw) -> None:
        error = data.get("error", {})
        code = error.get("code", "")
        message = error.get("message", "Unknown error")
        await self.ui.display_system_text(f"Protocol error: {message} ({code})")

    async def _on_char_changed(self, path: str, payload) -> None:
        await self.ui.update_watch_list()

    async def _on_token_expired(self, event_name: str, **kw) -> None:
        clear_token()
        self.connection.token = None
        self.connection.auth_mode = "password"
        await self.ui.show_login(error="Session expired. Please log in again.")

    async def _on_mail_result(self, event_name: str, text: str, **kw) -> None:
        await self.ui.display_system_text(text)

    async def _on_mail_unread(self, path: str, payload) -> None:
        if self._mail_notified:
            return
        self._mail_notified = True
        count = self.commands.mail_manager.check_unread()
        if count > 0:
            plural = "s" if count != 1 else ""
            await self.ui.notify(f"You have {count} unread message{plural}.")

    async def _on_autocomplete_results(
        self, event_name: str, results: list[str], prefix_len: int, **kw
    ) -> None:
        await self.ui.apply_completions(results, prefix_len)
