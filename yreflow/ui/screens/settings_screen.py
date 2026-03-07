"""Settings screen for yreflow preferences."""

from __future__ import annotations

from textual.binding import Binding
from textual.screen import ModalScreen
from textual.widgets import Static, Switch
from textual.containers import Vertical, Horizontal

from ...config import load_config, save_preference


class _SettingRow(Horizontal):
    """A label + switch row."""

    DEFAULT_CSS = """
    _SettingRow {
        height: auto;
        padding: 0 1;
        margin-bottom: 1;
    }
    _SettingRow Static {
        width: 1fr;
        content-align-vertical: middle;
        height: 3;
    }
    _SettingRow Switch {
        width: auto;
    }
    """

    def __init__(self, label: str, setting_key: str, value: bool, **kwargs) -> None:
        super().__init__(**kwargs)
        self.setting_key = setting_key
        self._label = label
        self._value = value

    def compose(self):
        yield Static(self._label)
        yield Switch(value=self._value, id=f"setting-{self.setting_key}")


class SettingsScreen(ModalScreen[None]):
    """Modal settings screen with toggle switches."""

    DEFAULT_CSS = """
    SettingsScreen {
        align: center middle;
    }
    #settings-container {
        width: 60;
        height: auto;
        max-height: 80%;
        background: $panel;
        border: solid $accent;
        padding: 1 2;
    }
    #settings-title {
        text-style: bold;
        text-align: center;
        width: 100%;
        margin-bottom: 1;
    }
    """

    BINDINGS = [
        Binding("escape", "close", "Close"),
    ]

    SETTINGS = [
        ("Spellcheck", "spellcheck_enabled"),
        ("Markup Preview", "markup_preview_enabled"),
        ("Auto-Reconnect", "auto_reconnect"),
    ]

    def compose(self):
        config = load_config()
        with Vertical(id="settings-container"):
            yield Static("Settings", id="settings-title")
            for label, key in self.SETTINGS:
                yield _SettingRow(label, key, config.get(key, False))

    def on_switch_changed(self, event: Switch.Changed) -> None:
        switch_id = event.switch.id or ""
        if not switch_id.startswith("setting-"):
            return
        key = switch_id.removeprefix("setting-")
        save_preference(key, event.value)

        # Live-update highlighters if applicable
        if key == "spellcheck_enabled":
            from ..widgets.input_bar import InputBar
            input_bar = self.app.query_one("#input-bar", InputBar)
            input_bar.set_highlighter_state("spellcheck", event.value)
            input_bar.refresh()
        elif key == "markup_preview_enabled":
            from ..widgets.input_bar import InputBar
            input_bar = self.app.query_one("#input-bar", InputBar)
            input_bar.set_highlighter_state("markup", event.value)
            input_bar.refresh()

    def action_close(self) -> None:
        self.dismiss(None)
