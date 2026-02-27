"""Controller: glue between protocol layer and UI.

Subscribes to EventBus events from the protocol and routes them to UI calls.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .protocol.events import EventBus
from .protocol.model_store import ModelStore
from .protocol.connection import WolferyConnection
from .commands.handler import CommandHandler, CommandResult

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

    async def start(self) -> None:
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
        # Phase 3: update character tabs
        pass

    async def _on_tab_needed(self, event_name: str, character: str, **kw) -> None:
        await self.ui.ensure_character_tab(character)

    async def _on_raw_message(self, event_name: str, text: str, **kw) -> None:
        await self.ui.log_raw(text)

    async def _on_connection_closed(self, event_name: str, **kw) -> None:
        await self.ui.display_system_text("Connection closed.")

    async def _on_connection_failed(self, event_name: str, **kw) -> None:
        await self.ui.display_system_text("Could not connect to Wolfery!")
