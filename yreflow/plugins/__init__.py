"""Plugin system for yreflow.

Plugins hook into the EventBus to react to protocol events like connect,
disconnect, messages, room changes, etc.  Realm-specific plugins can
customise behaviour per server.
"""

from .base import Plugin
from .manager import PluginManager

__all__ = ["Plugin", "PluginManager"]
