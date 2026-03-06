"""URL catcher screen — shows recently captured URLs."""

from __future__ import annotations

from textual.binding import Binding
from textual.screen import ModalScreen
from textual.widgets import Static, Button, Link
from textual.containers import Vertical, Horizontal, VerticalScroll

from ...url_catcher import CaughtUrl


class UrlScreen(ModalScreen):
    """Modal listing the most recently captured URLs."""

    DEFAULT_CSS = """
    UrlScreen {
        align: center middle;
    }
    #url-container {
        width: 80;
        height: auto;
        max-height: 85%;
        background: $panel;
        border: solid $accent;
        padding: 1 2;
    }
    #url-title {
        text-style: bold;
        text-align: center;
        width: 100%;
        margin-bottom: 1;
    }
    #url-body {
        height: 1fr;
    }
    .url-row {
        height: auto;
    }
    .url-ts {
        width: auto;
        color: $text-muted;
        margin-right: 1;
    }
    .url-link {
        width: 1fr;
    }
    .url-raw {
        color: $text-muted;
        margin-left: 7;
        margin-bottom: 1;
    }
    #url-empty {
        text-align: center;
        color: $text-muted;
    }
    #url-close-btn {
        margin-top: 1;
        width: 100%;
    }
    """

    BINDINGS = [
        Binding("escape", "close_screen", "Close"),
    ]

    def __init__(self, urls: list[CaughtUrl], **kwargs) -> None:
        super().__init__(**kwargs)
        self.urls = urls

    def compose(self):
        with Vertical(id="url-container"):
            yield Static("Recent URLs", id="url-title", markup=True)
            yield VerticalScroll(id="url-body")
            yield Button("Close", id="url-close-btn", variant="default")

    async def on_mount(self) -> None:
        body = self.query_one("#url-body", VerticalScroll)
        if not self.urls:
            await body.mount(
                Static("[dim]No URLs captured yet.[/dim]", id="url-empty", markup=True)
            )
            return

        for entry in reversed(self.urls):
            safe_url = entry.url.replace("[", "\\[")
            row = Horizontal(classes="url-row")
            await body.mount(row)
            await row.mount(
                Static(entry.timestamp, classes="url-ts"),
                Link(entry.display_text, url=entry.url, classes="url-link"),
            )
            await body.mount(
                Static(f"[dim]{safe_url}[/dim]", classes="url-raw", markup=True)
            )

    def action_close_screen(self) -> None:
        self.dismiss()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "url-close-btn":
            self.dismiss()
