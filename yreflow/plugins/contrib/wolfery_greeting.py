"""Example realm-specific plugin: Wolfery connect greeting.

Demonstrates how to write a plugin that only activates on a specific
realm and reacts to connection lifecycle events.
"""

from yreflow.plugins import Plugin


class WolferyGreeting(Plugin):
    name = "Wolfery Greeting"
    realm = "wolfery"

    async def on_connect(self, **kw):
        await self.event_bus.publish(
            "system.text",
            text="[Wolfery plugin] Welcome to Wolfery!",
        )

    async def on_disconnect(self, **kw):
        await self.event_bus.publish(
            "system.text",
            text="[Wolfery plugin] Disconnected from Wolfery.",
        )


# PluginManager looks for this attribute.
plugin = WolferyGreeting
