"""Command input bar widget."""

from textual.events import Key
from textual.message import Message
from textual.widgets import Input

from ..highlighters import CompositeHighlighter, MarkupPreviewHighlighter, SpellCheckHighlighter

# Keys that should pass through to app-level bindings even when input is focused.
_PASSTHROUGH_KEYS = {
    "ctrl+u", "ctrl+w", "ctrl+n", "ctrl+p", "ctrl+f", "ctrl+grave_accent",
    "ctrl+s", "ctrl+t", "ctrl+d", "ctrl+g",
}

# Keys that pass through when nav mode is active (so they reach NavPanel).
_NAV_PASSTHROUGH_KEYS = {
    "up", "down", "left", "right",
    "home", "end", "pageup", "pagedown",
    "escape",
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

    class RecallDirected(Message):
        """Posted when the user presses ! to recall a directed message contact."""
        def __init__(self, index: int) -> None:
            super().__init__()
            self.index = index

    def __init__(self, **kwargs):
        self._composite = CompositeHighlighter()
        self._spell_highlighter = SpellCheckHighlighter()
        self._markup_highlighter = MarkupPreviewHighlighter()
        self._composite.register("markup", self._markup_highlighter)
        self._composite.register("spellcheck", self._spell_highlighter)

        super().__init__(
            placeholder="Type a command (say, :pose, >ooc, w Name=msg)...",
            highlighter=self._composite,
            **kwargs,
        )
        self._histories: dict[str, list[str]] = {}
        self._positions: dict[str, int] = {}
        self._active_char: str | None = None
        self._saved_input: dict[str, str] = {}
        self._in_recall_mode: bool = False
        self._recall_index: int = -1
        self._nav_mode: bool = False

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

    def set_nav_mode(self, enabled: bool) -> None:
        """Enable/disable navigation mode (arrow keys pass through to NavPanel)."""
        self._nav_mode = enabled

    async def _on_key(self, event: Key) -> None:
        # In nav mode, let directional keys bubble up to NavPanel
        if self._nav_mode and event.key in _NAV_PASSTHROUGH_KEYS:
            return

        # Reset recall mode on any printable non-! key, or on backspace/delete
        if self._in_recall_mode:
            if event.key in ("backspace", "delete") or (
                event.character and event.character != "!"
            ):
                self._in_recall_mode = False
                self._recall_index = -1

        # ! recall: cycle through directed contacts
        if event.character == "!":
            if self.value == "" or self._in_recall_mode:
                if not self._in_recall_mode:
                    self._recall_index = 0
                else:
                    self._recall_index += 1
                self._in_recall_mode = True
                self.post_message(self.RecallDirected(self._recall_index))
                event.prevent_default()
                return

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

    # --- Highlighter controls ---

    def toggle_spellcheck(self) -> bool:
        """Toggle spellcheck on/off. Returns new state."""
        new = not self._composite.is_enabled("spellcheck")
        self._composite.set_enabled("spellcheck", new)
        return new

    def toggle_markup_preview(self) -> bool:
        """Toggle markup preview on/off. Returns new state."""
        new = not self._composite.is_enabled("markup")
        self._composite.set_enabled("markup", new)
        return new

    def set_highlighter_state(self, name: str, enabled: bool) -> None:
        """Set a named highlighter's state (used when restoring config)."""
        self._composite.set_enabled(name, enabled)

    def update_spellcheck_words(self, words: set[str]) -> None:
        """Feed custom words (character names, etc.) to the spellchecker."""
        self._spell_highlighter.update_custom_words(words)
