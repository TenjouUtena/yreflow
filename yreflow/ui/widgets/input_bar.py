"""Command input bar widget."""

from textual.events import Key
from textual.widgets import Input

# Keys that should pass through to app-level bindings even when input is focused.
_PASSTHROUGH_KEYS = {
    "ctrl+u", "ctrl+w", "ctrl+n", "ctrl+p", "ctrl+f", "ctrl+grave_accent",
}

_MAX_HISTORY = 20


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
        self._histories: dict[str, list[str]] = {}
        self._positions: dict[str, int] = {}
        self._active_char: str | None = None
        self._saved_input: dict[str, str] = {}

    def set_active_character(self, character: str) -> None:
        """Switch which character's history is active."""
        self._active_char = character
        if character not in self._histories:
            self._histories[character] = []
        self._positions[character] = len(self._histories[character])
        self._saved_input[character] = ""

    def push_history(self, command: str) -> None:
        """Add a command to the active character's history."""
        if not self._active_char or not command:
            return
        history = self._histories[self._active_char]
        if not history or history[-1] != command:
            history.append(command)
            if len(history) > _MAX_HISTORY:
                history.pop(0)
        self._positions[self._active_char] = len(history)
        self._saved_input[self._active_char] = ""

    async def _on_key(self, event: Key) -> None:
        if event.key == "up":
            if self._active_char:
                history = self._histories.get(self._active_char, [])
                pos = self._positions.get(self._active_char, 0)
                if pos > 0:
                    if pos == len(history):
                        self._saved_input[self._active_char] = self.value
                    pos -= 1
                    self._positions[self._active_char] = pos
                    self.value = history[pos]
                    self.cursor_position = len(self.value)
            event.prevent_default()
            return

        if event.key == "down":
            if self._active_char:
                history = self._histories.get(self._active_char, [])
                pos = self._positions.get(self._active_char, 0)
                if pos < len(history):
                    pos += 1
                    self._positions[self._active_char] = pos
                    if pos == len(history):
                        self.value = self._saved_input.get(self._active_char, "")
                    else:
                        self.value = history[pos]
                    self.cursor_position = len(self.value)
            event.prevent_default()
            return

        if event.key == "shift+enter":
            self.insert_text_at_cursor("\n")

        await super()._on_key(event)
