"""Character selection modal screen."""

from __future__ import annotations

from typing import TYPE_CHECKING

from textual.binding import Binding
from textual.screen import ModalScreen
from textual.widgets import Static, Button
from textual.containers import Vertical, VerticalScroll
from textual.message import Message

if TYPE_CHECKING:
    from ...protocol.model_store import ModelStore
    from ...protocol.connection import WolferyConnection


class CharacterOption(Static):
    """A single character option in the select screen."""

    DEFAULT_CSS = """
    CharacterOption {
        height: auto;
        padding: 0 2;
        margin: 0 1;
        background: $surface;
    }
    CharacterOption:hover {
        background: $accent 30%;
    }
    """

    class Selected(Message):
        def __init__(self, character_id: str) -> None:
            super().__init__()
            self.character_id = character_id

    def __init__(self, character_id: str, display: str, **kwargs) -> None:
        super().__init__(display, markup=True, **kwargs)
        self.character_id = character_id

    def on_click(self) -> None:
        self.post_message(self.Selected(self.character_id))


class CharacterSelectScreen(ModalScreen):
    """Modal screen for selecting a character to awaken."""

    DEFAULT_CSS = """
    CharacterSelectScreen {
        align: center middle;
    }
    #select-container {
        width: 50;
        height: auto;
        max-height: 80%;
        background: $panel;
        border: solid $accent;
        padding: 1 2;
    }
    #select-title {
        text-style: bold;
        text-align: center;
        width: 100%;
        margin-bottom: 1;
    }
    #char-list {
        height: auto;
        max-height: 20;
    }
    #close-btn {
        margin-top: 1;
        width: 100%;
    }
    """

    BINDINGS = [
        Binding("escape", "close_screen", "Close"),
    ]

    def __init__(
        self,
        store: ModelStore,
        connection: WolferyConnection,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self.store = store
        self.connection = connection

    def compose(self):
        with Vertical(id="select-container"):
            yield Static("Select a Character", id="select-title")
            yield VerticalScroll(id="char-list")
            yield Button("Close", id="close-btn", variant="default")

    async def on_mount(self) -> None:
        char_list = self.query_one("#char-list", VerticalScroll)
        try:
            player = self.connection.player
            chars = self.store.get(f"core.player.{player}.chars._value")
        except KeyError:
            await char_list.mount(Static("[dim]No characters found[/dim]", markup=True))
            return

        for char_rid in chars:
            try:
                char = self.store.get(char_rid["rid"])
                char_id = char["id"]
                name = char.get("name", "?")
                surname = char.get("surname", "")
                display = f"{name} {surname}".strip()
                awake = char.get("awake", False)
                if awake:
                    display += " [green](awake)[/green]"
                else:
                    display += " [dim](sleeping)[/dim]"
                await char_list.mount(
                    CharacterOption(char_id, display, id=f"charopt-{char_id}")
                )
            except (KeyError, AttributeError):
                continue

    async def on_character_option_selected(
        self, event: CharacterOption.Selected
    ) -> None:
        """Initiate two-phase wakeup for the selected character."""
        char_id = event.character_id
        # Phase 1: take control of character
        msg_id = await self.connection.send(
            f"call.core.player.{self.connection.player}.controlChar",
            {"charId": char_id},
        )
        # Phase 2: wakeup on response
        self.connection.add_message_wait(
            msg_id,
            lambda _result, cid=char_id: self._wakeup_phase_2(cid),
        )
        self.dismiss()

    async def _wakeup_phase_2(self, character_id: str) -> None:
        """Send wakeup command after controlChar succeeds."""
        await self.connection.send(
            f"call.core.char.{character_id}.ctrl.wakeup"
        )

    def action_close_screen(self) -> None:
        self.dismiss()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "close-btn":
            self.dismiss()
