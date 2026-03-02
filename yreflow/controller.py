"""Controller: glue between protocol layer and UI.

Subscribes to EventBus events from the protocol and routes them to UI calls.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .protocol.events import EventBus
from .protocol.model_store import ModelStore
from .protocol.connection import WolferyConnection
from .protocol.http_auth import obtain_token
from .commands.handler import CommandHandler, CommandResult
from .config import save_token, clear_token

if TYPE_CHECKING:
    from .ui.base import UIProtocol


class Controller:
    def __init__(self, config: dict, ui: UIProtocol):
        self.ui = ui
        self.event_bus = EventBus()
        self.store = ModelStore(event_bus=self.event_bus)
        self.connection = WolferyConnection(config, self.store, self.event_bus)
        self.commands = CommandHandler(self.connection, self.store)

        # Subscribe to protocol events
        self.event_bus.subscribe(r"^message\.received$", self._on_message)
        self.event_bus.subscribe(r"^notification$", self._on_notification)
        self.event_bus.subscribe(r"^room\.changed$", self._on_room_changed)
        self.event_bus.subscribe(r"^watches\.changed$", self._on_watches_changed)
        self.event_bus.subscribe(r"^characters\.changed$", self._on_characters_changed)
        self.event_bus.subscribe(r"^character\.tab\.needed$", self._on_tab_needed)
        self.event_bus.subscribe(r"^raw\.message$", self._on_raw_message)
        self.event_bus.subscribe(r"^connection\.closed$", self._on_connection_closed)
        self.event_bus.subscribe(r"^connection\.failed$", self._on_connection_failed)
        self.event_bus.subscribe(r"^look\.result$", self._on_look_result)
        self.event_bus.subscribe(r"^auth\.failed$", self._on_auth_failed)
        self.event_bus.subscribe(r"^auth\.token_expired$", self._on_token_expired)
        self.event_bus.subscribe(r"^system\.text$", self._on_system_text)

        # Rebuild sidebar when any character's LFRP status changes
        self.store.add_watch(r"^core\.char\.[^.]+$", self._on_char_rp_changed)

    async def start(self) -> None:
        await self.connection.connect()

    async def start_with_credentials(self, username: str, password: str) -> None:
        """Obtain a token via HTTP, save it, then connect with it."""
        token = await obtain_token(username, password)
        save_token(token)
        self.connection.token = token
        self.connection.auth_mode = "token"
        await self.connection.connect()

    async def handle_command(self, command: str, character: str) -> CommandResult:
        return await self.commands.process_command(command, character)

    # --- Event handlers ---

    async def _on_message(self, event_name: str, message: dict, style: str, character: str, **kw) -> None:
        await self.ui.display_message(message, style, character)

    async def _on_notification(self, event_name: str, text: str, **kw) -> None:
        await self.ui.notify(text)

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
            current_ids = set()
            for x in models:
                try:
                    current_ids.add(self.store.get(x["rid"])["id"])
                except KeyError:
                    continue
        except KeyError:
            current_ids = set()

        known = self.ui.get_known_characters()
        for char_id in known - current_ids:
            await self.ui.remove_character_tab(char_id)

    async def _on_tab_needed(self, event_name: str, character: str, **kw) -> None:
        await self.ui.ensure_character_tab(character)

    async def _on_raw_message(self, event_name: str, text: str, **kw) -> None:
        await self.ui.log_raw(text)

    async def _on_connection_closed(self, event_name: str, **kw) -> None:
        await self.ui.display_system_text("Connection closed.")

    async def _on_connection_failed(self, event_name: str, **kw) -> None:
        await self.ui.display_system_text("Could not connect to Wolfery!")

    async def _on_look_result(self, event_name: str, data: dict, **kw) -> None:
        await self.ui.display_look(data)

    async def _on_auth_failed(self, event_name: str, error: str, **kw) -> None:
        await self.ui.show_login(error=error)

    async def _on_system_text(self, event_name: str, text: str, **kw) -> None:
        await self.ui.display_system_text(text)

    async def _on_char_rp_changed(self, path: str, payload) -> None:
        if isinstance(payload, dict) and "rp" in payload:
            await self.ui.update_watch_list()

    async def _on_token_expired(self, event_name: str, **kw) -> None:
        clear_token()
        self.connection.token = None
        self.connection.auth_mode = "password"
        await self.ui.show_login(error="Session expired. Please log in again.")
