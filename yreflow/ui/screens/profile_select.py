"""Profile selection modal screen."""

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
    from ...protocol.controlled_char import ControlledChar


class ProfileOption(Static):
    """A single profile option in the select screen."""

    DEFAULT_CSS = """
    ProfileOption {
        height: auto;
        padding: 0 2;
        margin: 0 1;
        background: $surface;
    }
    ProfileOption:hover {
        background: $accent 30%;
    }
    """

    class Selected(Message):
        def __init__(self, profile_id: str, profile_name: str) -> None:
            super().__init__()
            self.profile_id = profile_id
            self.profile_name = profile_name

    def __init__(self, profile_id: str, profile_name: str, display: str, **kwargs) -> None:
        super().__init__(display, markup=True, **kwargs)
        self.profile_id = profile_id
        self.profile_name = profile_name

    def on_click(self) -> None:
        self.post_message(self.Selected(self.profile_id, self.profile_name))


class ProfileSelectScreen(ModalScreen):
    """Modal screen for selecting a character profile."""

    DEFAULT_CSS = """
    ProfileSelectScreen {
        align: center middle;
    }
    #profile-container {
        width: 50;
        height: auto;
        max-height: 80%;
        background: $panel;
        border: solid $accent;
        padding: 1 2;
    }
    #profile-title {
        text-style: bold;
        text-align: center;
        width: 100%;
        margin-bottom: 1;
    }
    #profile-list {
        height: auto;
        max-height: 20;
    }
    #profile-close-btn {
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
        cc: ControlledChar,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self.store = store
        self.connection = connection
        self.cc = cc

    def compose(self):
        with Vertical(id="profile-container"):
            yield Static("Select a Profile", id="profile-title")
            yield VerticalScroll(id="profile-list")
            yield Button("Close", id="profile-close-btn", variant="default")

    async def on_mount(self) -> None:
        profile_list = self.query_one("#profile-list", VerticalScroll)
        try:
            profiles = self.store.get(
                f"core.char.{self.cc.char_id}.profiles._value"
            )
        except KeyError:
            await profile_list.mount(
                Static("[dim]No profiles found[/dim]", markup=True)
            )
            return

        for entry in profiles:
            try:
                profile = self.store.get(entry["rid"])
                profile_id = entry["rid"].split(".")[-1]
                name = profile.get("name", "?")
                key = profile.get("key", "")
                display = f"{name}"
                if key:
                    display += f" [dim]({key})[/dim]"
                await profile_list.mount(
                    ProfileOption(
                        profile_id, name, display, id=f"profopt-{profile_id}"
                    )
                )
            except (KeyError, AttributeError):
                continue

    async def on_profile_option_selected(
        self, event: ProfileOption.Selected
    ) -> None:
        """Switch to the selected profile."""
        await self.connection.send(
            f"call.{self.cc.ctrl_path}.useProfile",
            {"profileId": event.profile_id, "safe": True},
        )
        self.dismiss(event.profile_name)

    def action_close_screen(self) -> None:
        self.dismiss()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "profile-close-btn":
            self.dismiss()
