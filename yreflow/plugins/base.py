"""Base Plugin class with lifecycle hooks mapped to EventBus events."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..protocol.events import EventBus
    from ..protocol.model_store import ModelStore
    from ..protocol.connection import WolferyConnection


class Plugin:
    """Base class for yreflow plugins.

    Subclass this and override the ``on_*`` hooks you care about.
    The PluginManager wires each hook to the corresponding EventBus event.

    Attributes:
        name:  Human-readable plugin name (defaults to class name).
        realm: If set, the plugin only activates for this realm key
               (e.g. ``"wolfery"``, ``"aurellion"``).  ``None`` means
               the plugin is active for every realm.
    """

    name: str = ""
    realm: str | None = None

    def __init__(self) -> None:
        if not self.name:
            self.name = type(self).__name__

        # Injected by PluginManager before on_load
        self.event_bus: EventBus
        self.store: ModelStore
        self.connection: WolferyConnection

    # -- Lifecycle ----------------------------------------------------------

    async def on_load(self) -> None:
        """Called once when the plugin is loaded into the manager.

        Use this to set up model-store watches or subscribe to custom
        EventBus patterns beyond the standard hooks.
        """

    async def on_unload(self) -> None:
        """Called when the plugin is removed or the app exits."""

    # -- Connection ---------------------------------------------------------

    async def on_connect(self, **kw: Any) -> None:
        """Fired after a successful WebSocket connection + auth."""

    async def on_disconnect(self, **kw: Any) -> None:
        """Fired when the connection closes."""

    async def on_connection_failed(self, **kw: Any) -> None:
        """Fired when a connection attempt fails entirely."""

    # -- Messages -----------------------------------------------------------

    async def on_message(self, message: dict, style: str, character: str, **kw: Any) -> None:
        """Fired for every incoming message (say, pose, whisper, …)."""

    # -- Room ---------------------------------------------------------------

    async def on_room_changed(self, **kw: Any) -> None:
        """Fired when the current room's state changes."""

    # -- Characters ---------------------------------------------------------

    async def on_characters_changed(self, **kw: Any) -> None:
        """Fired when the set of controlled characters changes."""

    # -- Watches ------------------------------------------------------------

    async def on_watches_changed(self, **kw: Any) -> None:
        """Fired when the watch-list updates."""

    # -- Notifications ------------------------------------------------------

    async def on_notification(self, text: str, character: str | None = None, **kw: Any) -> None:
        """Fired for in-game notifications (look, summon, etc.)."""

    # -- System -------------------------------------------------------------

    async def on_system_text(self, text: str, **kw: Any) -> None:
        """Fired for system-level text messages."""

    async def on_protocol_error(self, data: dict, **kw: Any) -> None:
        """Fired on protocol errors from the server."""

    # -- Autocomplete -------------------------------------------------------

    async def on_autocomplete_try(self, input: str, cursor: int, ctrl_id: str, **kw: Any) -> bool:
        """Fired when the user presses Tab.

        Return ``True`` to claim the event (prevents the default name-based
        autocomplete).  Return ``False`` / ``None`` to let it fall through.
        """
        return False

    # -- Raw ----------------------------------------------------------------

    async def on_raw_message(self, text: str, **kw: Any) -> None:
        """Fired for every raw WebSocket frame (useful for logging/debugging)."""
