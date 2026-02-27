"""Command input bar widget."""

from textual.events import Key
from textual.widgets import Input

# Keys that should pass through to app-level bindings even when input is focused.
_PASSTHROUGH_KEYS = {
    "ctrl+u", "ctrl+w", "ctrl+n", "ctrl+p", "ctrl+f", "ctrl+grave_accent",
}


class InputBar(Input):
    """Single-line command input at the bottom of the screen."""

    DEFAULT_CSS = """
    InputBar {
        dock: bottom;
        margin: 0 0;
        border: solid $accent;
    }
    """

    def __init__(self, **kwargs):
        super().__init__(
            placeholder="Type a command (say, :pose, >ooc, w Name=msg)...",
            **kwargs,
        )

    async def _on_key(self, event: Key) -> None:
        if event.key in _PASSTHROUGH_KEYS:
            return
        await super()._on_key(event)