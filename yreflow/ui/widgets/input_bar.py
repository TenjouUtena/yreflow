"""Command input bar widget."""

from textual.events import Key
from textual.widgets import Input

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