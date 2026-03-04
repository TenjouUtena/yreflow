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

    can_focus = True

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
    CharacterOption:focus {
        background: $accent 50%;
    }
    CharacterOption.active {
        opacity: 60%;
    }
    """

    class Selected(Message):
        def __init__(self, character_id: str, is_awake: bool) -> None:
            super().__init__()
            self.character_id = character_id
            self.is_awake = is_awake

    def __init__(
        self,
        character_id: str,
        display: str,
        *,
        is_awake: bool = False,
        is_active: bool = False,
        **kwargs,
    ) -> None:
        super().__init__(display, markup=True, **kwargs)
        self.character_id = character_id
        self.is_awake = is_awake
        self.is_active = is_active
        if is_active:
            self.can_focus = False
            self.add_class("active")

    def on_click(self) -> None:
        if not self.is_active:
            self.post_message(self.Selected(self.character_id, self.is_awake))

    def on_key(self, event) -> None:
        if event.key in ("enter", "space"):
            if not self.is_active:
                self.post_message(self.Selected(self.character_id, self.is_awake))
        elif event.key in ("up", "down"):
            options = [
                o for o in self.screen.query("CharacterOption") if o.can_focus
            ]
            if self not in options:
                return
            idx = options.index(self)
            if event.key == "up" and idx > 0:
                options[idx - 1].focus()
                options[idx - 1].scroll_visible()
            elif event.key == "down" and idx < len(options) - 1:
                options[idx + 1].focus()
                options[idx + 1].scroll_visible()
            event.stop()


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

        # Build set of currently controlled character IDs
        controlled: set[str] = set()
        try:
            ctrls = self.store.get(f"core.player.{player}.ctrls._value")
            for ctrl_rid in ctrls:
                controlled.add(ctrl_rid["rid"].split(".")[2])
        except (KeyError, IndexError, AttributeError):
            pass

        for char_rid in chars:
            try:
                char = self.store.get(char_rid["rid"])
                char_id = char["id"]
                name = char.get("name", "?")
                surname = char.get("surname", "")
                display = f"{name} {surname}".strip()
                awake = self.store.get_character_attribute(char_id, "awake", False)
                is_active = char_id in controlled
                if is_active:
                    display += " [green](active)[/green]"
                elif awake:
                    display += " [yellow](awake)[/yellow]"
                else:
                    display += " [dim](sleeping)[/dim]"
                option = CharacterOption(
                    char_id,
                    display,
                    is_awake=bool(awake),
                    is_active=is_active,
                    id=f"charopt-{char_id}",
                )
                await char_list.mount(option)
            except (KeyError, AttributeError):
                continue

        focusable = [
            o for o in self.query("CharacterOption") if o.can_focus
        ]
        if focusable:
            focusable[0].focus()

    async def on_character_option_selected(
        self, event: CharacterOption.Selected
    ) -> None:
        """Take control of (and optionally wake up) the selected character."""
        char_id = event.character_id
        # Phase 1: take control of character
        msg_id = await self.connection.send(
            f"call.core.player.{self.connection.player}.controlChar",
            {"charId": char_id},
        )
        # Phase 2: wakeup only if the character is sleeping
        if not event.is_awake:
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
