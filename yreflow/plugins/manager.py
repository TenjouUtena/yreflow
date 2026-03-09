"""PluginManager: discovers, loads, and wires plugins to the EventBus."""

from __future__ import annotations

import importlib
import logging
import pkgutil
from pathlib import Path
from typing import TYPE_CHECKING

from .base import Plugin

if TYPE_CHECKING:
    from ..protocol.events import EventBus
    from ..protocol.model_store import ModelStore
    from ..protocol.connection import WolferyConnection

from ..config import load_config

log = logging.getLogger(__name__)

# Maps EventBus event patterns to Plugin hook method names.
_EVENT_HOOKS: dict[str, str] = {
    r"^connection\.established$": "on_connect",
    r"^connection\.closed$": "on_disconnect",
    r"^connection\.failed$": "on_connection_failed",
    r"^message\.received$": "on_message",
    r"^room\.changed$": "on_room_changed",
    r"^characters\.changed$": "on_characters_changed",
    r"^watches\.changed$": "on_watches_changed",
    r"^notification$": "on_notification",
    r"^system\.text$": "on_system_text",
    r"^protocol\.error$": "on_protocol_error",
    r"^raw\.message$": "on_raw_message",
    r"^autocomplete\.try$": "on_autocomplete_try",
}


class PluginManager:
    """Load plugins and wire their hooks to an EventBus."""

    def __init__(
        self,
        event_bus: EventBus,
        store: ModelStore,
        connection: WolferyConnection,
    ) -> None:
        self.event_bus = event_bus
        self.store = store
        self.connection = connection
        self._plugins: list[Plugin] = []

    @property
    def plugins(self) -> list[Plugin]:
        return list(self._plugins)

    # -- Loading ------------------------------------------------------------

    async def load(self, plugin: Plugin) -> None:
        """Inject dependencies, wire hooks, and call on_load.

        Skips plugins whose name appears in the ``disabled_plugins``
        config list, or whose ``realm`` doesn't match the current realm.
        """
        disabled = load_config().get("disabled_plugins", [])
        if plugin.name in disabled:
            log.debug("Plugin %s is disabled via config", plugin.name)
            return

        realm_key = self.connection.realm.key
        if plugin.realm is not None and plugin.realm != realm_key:
            log.debug("Skipping plugin %s (realm %s != %s)", plugin.name, plugin.realm, realm_key)
            return

        plugin.event_bus = self.event_bus
        plugin.store = self.store
        plugin.connection = self.connection

        self._wire_hooks(plugin)
        await plugin.on_load()
        self._plugins.append(plugin)
        log.info("Loaded plugin: %s", plugin.name)

    async def unload(self, plugin: Plugin) -> None:
        """Call on_unload and remove the plugin."""
        await plugin.on_unload()
        self._plugins.remove(plugin)
        log.info("Unloaded plugin: %s", plugin.name)

    async def unload_all(self) -> None:
        for p in list(self._plugins):
            await self.unload(p)

    # -- Discovery ----------------------------------------------------------

    async def discover_builtin(self) -> None:
        """Auto-discover and load all plugins in ``yreflow.plugins.contrib``."""
        contrib_path = Path(__file__).parent / "contrib"
        if not contrib_path.is_dir():
            return

        for finder, module_name, _is_pkg in pkgutil.iter_modules([str(contrib_path)]):
            fqn = f"yreflow.plugins.contrib.{module_name}"
            try:
                mod = importlib.import_module(fqn)
            except Exception:
                log.exception("Failed to import plugin module %s", fqn)
                continue

            # Each contrib module should define a ``plugin`` attribute
            # which is either a Plugin instance or a Plugin subclass.
            obj = getattr(mod, "plugin", None)
            if obj is None:
                log.warning("Plugin module %s has no 'plugin' attribute", fqn)
                continue

            if isinstance(obj, type) and issubclass(obj, Plugin):
                obj = obj()
            if isinstance(obj, Plugin):
                await self.load(obj)

    # -- Internals ----------------------------------------------------------

    def _wire_hooks(self, plugin: Plugin) -> None:
        """Subscribe overridden plugin hooks to EventBus patterns."""
        base_methods = {name: getattr(Plugin, name) for name in dir(Plugin) if name.startswith("on_")}

        for pattern, hook_name in _EVENT_HOOKS.items():
            method = getattr(plugin, hook_name, None)
            if method is None:
                continue
            # Only wire hooks that the subclass actually overrides.
            base = base_methods.get(hook_name)
            if base is not None and getattr(method, "__func__", None) is base:
                continue
            self.event_bus.subscribe(pattern, method)
