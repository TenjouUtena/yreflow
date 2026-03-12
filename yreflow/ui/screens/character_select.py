"""Character selection modal screen."""

from __future__ import annotations

from typing import TYPE_CHECKING

from textual.binding import Binding
from textual.screen import ModalScreen
from textual.widgets import Static, Button
from textual.containers import Vertical, VerticalScroll
from textual.message import Message

from .tabbable_modal import TabbableModal

if TYPE_CHECKING:
    from ...protocol.model_store import ModelStore
    from ...protocol.connection import WolferyConnection


class _SelectableOption(Static):
    """Base class for selectable options with keyboard navigation."""

    can_focus = True

    DEFAULT_CSS = """
    _SelectableOption {
        height: auto;
        padding: 0 2;
        margin: 0 1;
        background: $surface;
    }
    _SelectableOption:hover {
        background: $accent 30%;
    }
    _SelectableOption:focus {
        background: $accent 50%;
    }
    _SelectableOption.active {
        opacity: 60%;
    }
    """

    def on_key(self, event) -> None:
        if event.key in ("up", "down"):
            options = [
                o for o in self.screen.query("CharacterOption, PuppetOption")
                if o.can_focus
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


class CharacterOption(_SelectableOption):
    """A single character option in the select screen."""

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
        else:
            super().on_key(event)


class PuppetOption(_SelectableOption):
    """A puppet option in the select screen."""

    class Selected(Message):
        def __init__(self, puppet_id: str, puppeteer_id: str) -> None:
            super().__init__()
            self.puppet_id = puppet_id
            self.puppeteer_id = puppeteer_id

    def __init__(
        self,
        puppet_id: str,
        puppeteer_id: str,
        display: str,
        *,
        is_active: bool = False,
        **kwargs,
    ) -> None:
        super().__init__(display, markup=True, **kwargs)
        self.puppet_id = puppet_id
        self.puppeteer_id = puppeteer_id
        self.is_active = is_active
        if is_active:
            self.can_focus = False
            self.add_class("active")

    def on_click(self) -> None:
        if not self.is_active:
            self.post_message(self.Selected(self.puppet_id, self.puppeteer_id))

    def on_key(self, event) -> None:
        if event.key in ("enter", "space"):
            if not self.is_active:
                self.post_message(self.Selected(self.puppet_id, self.puppeteer_id))
        else:
            super().on_key(event)


class CharacterSelectScreen(TabbableModal, ModalScreen):
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
        self._dismissed = False

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

        # --- Puppets section ---
        try:
            puppets = self.store.get(f"core.player.{player}.puppets._value")
        except KeyError:
            puppets = []

        if puppets:
            await char_list.mount(
                Static("\n[bold]Puppets[/bold]", markup=True)
            )
            active_ctrl_ids = {
                cc.ctrl_id for cc in self.connection.ctrl_chars.values()
            }
            for puppet_entry in puppets:
                try:
                    puppet_data = self.store.get(puppet_entry["rid"])
                    puppet_char = self.store.get(puppet_data["puppet"]["rid"])
                    puppeteer_char = self.store.get(puppet_data["char"]["rid"])
                    puppet_id = puppet_char["id"]
                    puppeteer_id = puppeteer_char["id"]

                    puppet_name = puppet_char.get("name", "?")
                    puppet_surname = puppet_char.get("surname", "")
                    puppeteer_name = puppeteer_char.get("name", "?")
                    display = f"{puppet_name} {puppet_surname}".strip()
                    display += f" [dim](via {puppeteer_name})[/dim]"

                    ctrl_id = f"{puppet_id}_{puppeteer_id}"
                    is_active = ctrl_id in active_ctrl_ids
                    if is_active:
                        display += " [green](active)[/green]"

                    option = PuppetOption(
                        puppet_id,
                        puppeteer_id,
                        display,
                        is_active=is_active,
                        id=f"puppetopt-{ctrl_id}",
                    )
                    await char_list.mount(option)
                except (KeyError, AttributeError):
                    continue

        focusable = [
            o for o in self.query("CharacterOption, PuppetOption")
            if o.can_focus
        ]
        if focusable:
            focusable[0].focus()

    async def on_puppet_option_selected(
        self, event: PuppetOption.Selected
    ) -> None:
        """Take control of a puppet character."""
        if self._dismissed:
            return
        self._dismissed = True
        msg_id = await self.connection.send(
            f"call.core.player.{self.connection.player}.controlPuppet",
            {"charId": event.puppeteer_id, "puppetId": event.puppet_id},
        )
        # Chain wakeup after control succeeds -- puppet ctrl path needed
        ctrl_path = f"core.char.{event.puppeteer_id}.puppet.{event.puppet_id}.ctrl"
        self.connection.add_message_wait(
            msg_id,
            lambda _result, cp=ctrl_path: self._wakeup_phase_2(cp),
        )
        self.dismiss()

    async def on_character_option_selected(
        self, event: CharacterOption.Selected
    ) -> None:
        """Take control of (and optionally wake up) the selected character."""
        if self._dismissed:
            return
        self._dismissed = True
        char_id = event.character_id
        # Phase 1: take control of character
        msg_id = await self.connection.send(
            f"call.core.player.{self.connection.player}.controlChar",
            {"charId": char_id},
        )
        # Phase 2: wakeup only if the character is sleeping
        if not event.is_awake:
            ctrl_path = f"core.char.{char_id}.ctrl"
            self.connection.add_message_wait(
                msg_id,
                lambda _result, cp=ctrl_path: self._wakeup_phase_2(cp),
            )
        self.dismiss()

    async def _wakeup_phase_2(self, ctrl_path: str) -> None:
        """Send wakeup command after controlChar/controlPuppet succeeds."""
        await self.connection.send(f"call.{ctrl_path}.wakeup")

    def action_close_screen(self) -> None:
        self.dismiss()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "close-btn":
            self.dismiss()
