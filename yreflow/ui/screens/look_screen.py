"""Look screen modal for room and character inspection."""

from __future__ import annotations

from textual.binding import Binding
from textual.screen import ModalScreen
from textual.widgets import Static, Button, TabbedContent, TabPane
from textual.containers import Vertical, VerticalScroll

from ...formatter import format_message


class LookScreen(ModalScreen):
    """Modal screen displaying room or character info."""

    DEFAULT_CSS = """
    LookScreen {
        align: center middle;
    }
    #look-container {
        width: 70;
        height: auto;
        max-height: 85%;
        background: $panel;
        border: solid $accent;
        padding: 1 2;
    }
    #look-title {
        text-style: bold;
        text-align: center;
        width: 100%;
        margin-bottom: 1;
    }
    #look-subtitle {
        text-align: center;
        width: 100%;
        color: $text-muted;
    }
    #look-body {
        height: 1fr;
    }
    .look-section-title {
        text-style: bold;
        color: $accent;
        margin-top: 1;
    }
    .look-text {
        margin-bottom: 1;
    }
    .look-exit {
        padding: 0 1;
    }
    .look-tag-like {
        color: green;
    }
    .look-tag-dislike {
        color: red;
    }
    #close-btn {
        margin-top: 1;
        width: 100%;
    }
    """

    BINDINGS = [
        Binding("escape", "close_screen", "Close"),
    ]

    def __init__(self, data: dict, **kwargs) -> None:
        super().__init__(**kwargs)
        self.data = data

    def compose(self):
        with Vertical(id="look-container"):
            yield Static(self.data.get("name", ""), id="look-title", markup=True)
            if self.data["type"] == "character":
                parts = []
                if self.data.get("species"):
                    parts.append(self.data["species"])
                if self.data.get("gender"):
                    parts.append(self.data["gender"])
                if parts:
                    yield Static(" \u00b7 ".join(parts), id="look-subtitle")
            yield VerticalScroll(id="look-body")
            yield Button("Close", id="close-btn", variant="default")

    async def on_mount(self) -> None:
        body = self.query_one("#look-body", VerticalScroll)
        if self.data["type"] == "room":
            await self._mount_room(body)
        elif self.data["type"] == "character":
            await self._mount_character(body)

    async def _mount_room(self, body: VerticalScroll) -> None:
        areas = self.data.get("areas", [])

        if areas:
            # Use TabbedContent: Room tab + area tabs
            tabbed = TabbedContent()
            await body.mount(tabbed)

            # Room tab
            room_pane = TabPane("Room", id="tab-room")
            await tabbed.add_pane(room_pane)
            await self._mount_room_content(room_pane)

            # Area tabs
            for i, area in enumerate(areas):
                area_pane = TabPane(area["name"], id=f"tab-area-{i}")
                await tabbed.add_pane(area_pane)
                await self._mount_area_content(area_pane, area)
        else:
            # No areas, just show room content directly
            await self._mount_room_content(body)

    async def _mount_room_content(self, container) -> None:
        desc = self.data.get("desc", "")
        if desc:
            await container.mount(
                Static(format_message(desc), classes="look-text", markup=True)
            )

        exits = self.data.get("exits", [])
        if exits:
            await container.mount(
                Static("Exits", classes="look-section-title", markup=True)
            )
            for ex in exits:
                keys = f" ({ex['keys']})" if ex.get("keys") else ""
                await container.mount(
                    Static(
                        f"  [bold]{ex['name']}[/bold]{keys}",
                        classes="look-exit",
                        markup=True,
                    )
                )

    async def _mount_area_content(self, container, area: dict) -> None:
        if area.get("pop", 0) > 0:
            await container.mount(
                Static(
                    f"Population: {area['pop']}",
                    classes="look-text",
                    markup=True,
                )
            )
        about = area.get("about", "")
        if about:
            await container.mount(
                Static(format_message(about), classes="look-text", markup=True)
            )
        if not area.get("pop") and not about:
            await container.mount(
                Static("[dim]No details available.[/dim]", markup=True)
            )

    async def _mount_character(self, body: VerticalScroll) -> None:
        desc = self.data.get("desc", "")
        if desc:
            await body.mount(
                Static(format_message(desc), classes="look-text", markup=True)
            )

        about = self.data.get("about", "")
        if about:
            await body.mount(
                Static("About", classes="look-section-title", markup=True)
            )
            await body.mount(
                Static(format_message(about), classes="look-text", markup=True)
            )

        tags = self.data.get("tags", [])
        if tags:
            await body.mount(
                Static("Tags", classes="look-section-title", markup=True)
            )
            likes = [t for t in tags if t["like"]]
            dislikes = [t for t in tags if not t["like"]]
            if likes:
                items = ", ".join(t["key"] for t in likes)
                await body.mount(
                    Static(
                        f"  [green]Likes:[/green] {items}",
                        classes="look-tag-like",
                        markup=True,
                    )
                )
            if dislikes:
                items = ", ".join(t["key"] for t in dislikes)
                await body.mount(
                    Static(
                        f"  [red]Dislikes:[/red] {items}",
                        classes="look-tag-dislike",
                        markup=True,
                    )
                )

        if not desc and not about and not tags:
            await body.mount(
                Static("[dim]No information available.[/dim]", markup=True)
            )

    def action_close_screen(self) -> None:
        self.dismiss()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "close-btn":
            self.dismiss()
