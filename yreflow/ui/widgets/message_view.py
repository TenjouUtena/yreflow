"""Scrollable message display widget using RichLog."""

from textual.widgets import RichLog


class MessageView(RichLog):
    """Scrollable, auto-scrolling message log."""

    DEFAULT_CSS = """
    MessageView {
        border: solid $accent;
        scrollbar-size: 1 1;
    }
    """

    def __init__(self, **kwargs):
        super().__init__(
            highlight=False,
            markup=True,
            wrap=True,
            auto_scroll=True,
            **kwargs,
        )
