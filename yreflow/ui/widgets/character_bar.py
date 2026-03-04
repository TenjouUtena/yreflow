"""Character switching bar widget."""

from __future__ import annotations

from textual.containers import Horizontal
from textual.widgets import Static
from textual.message import Message


class CharacterButton(Static):
    """A single character button in the CharacterBar."""

    DEFAULT_CSS = """
    CharacterButton {
        width: auto;
        padding: 0 2;
        height: 1;
        content-align: center middle;
    }
    CharacterButton.active {
        background: $accent;
        color: $text;
        text-style: bold;
    }
    CharacterButton.inactive {
        background: $surface;
        color: $text-muted;
    }
    CharacterButton.inactive:hover {
        background: $accent 30%;
    }
    """

    class Clicked(Message):
        """Posted when a character button is clicked."""

        def __init__(self, character_id: str) -> None:
            super().__init__()
            self.character_id = character_id

    def __init__(self, character_id: str, name: str, **kwargs) -> None:
        super().__init__(name, **kwargs)
        self.character_id = character_id
        self._base_name = name

    def set_active(self, active: bool) -> None:
        self.remove_class("active", "inactive")
        self.add_class("active" if active else "inactive")

    def update_label(self, unread: int, urgent: bool = False) -> None:
        if unread > 0:
            if urgent:
                self.update(f"{self._base_name} [{unread}]")
            else:
                self.update(f"{self._base_name} ({unread})")
        else:
            self.update(self._base_name)

    def on_click(self) -> None:
        self.post_message(self.Clicked(self.character_id))


class AddCharacterButton(Static):
    """The [+] button to open character select."""

    DEFAULT_CSS = """
    AddCharacterButton {
        width: auto;
        padding: 0 1;
        height: 1;
        background: $surface;
        color: $text-muted;
    }
    AddCharacterButton:hover {
        background: $accent 30%;
    }
    """

    class Clicked(Message):
        pass

    def __init__(self, **kwargs) -> None:
        super().__init__("\\[+]", **kwargs)

    def on_click(self) -> None:
        self.post_message(self.Clicked())


class CharacterBar(Horizontal):
    """Bar of character buttons at the top of the screen."""

    DEFAULT_CSS = """
    CharacterBar {
        dock: top;
        height: 1;
        background: $surface;
    }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._buttons: dict[str, CharacterButton] = {}

    def compose(self):
        yield AddCharacterButton(id="add-char-btn")

    async def add_character(self, character_id: str, name: str) -> None:
        """Add a new character button before the [+] button."""
        if character_id in self._buttons:
            return
        btn = CharacterButton(
            character_id, name, id=f"char-btn-{character_id}",
        )
        await self.mount(btn, before=self.query_one("#add-char-btn"))
        self._buttons[character_id] = btn

    def remove_character(self, character_id: str) -> None:
        """Remove a character button."""
        if character_id in self._buttons:
            self._buttons[character_id].remove()
            del self._buttons[character_id]

    def set_active(self, character_id: str) -> None:
        """Highlight the active character, dim others."""
        for cid, btn in self._buttons.items():
            btn.set_active(cid == character_id)

    def update_unread(self, character_id: str, count: int, urgent: bool = False) -> None:
        """Update the unread badge on a character button."""
        if character_id in self._buttons:
            self._buttons[character_id].update_label(count, urgent)
