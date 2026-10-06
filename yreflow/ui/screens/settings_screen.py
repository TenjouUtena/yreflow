"""Settings screen for yreflow preferences."""

from __future__ import annotations

from textual.binding import Binding
from textual.screen import ModalScreen
from textual.widgets import Static, Switch, Select
from textual.containers import Vertical, Horizontal, VerticalScroll

from ...config import load_config, save_preference
from ...constants import NAMED_COLORS
from .tabbable_modal import TabbableModal


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


class _SettingSelect(Horizontal):
    """A label + dropdown row."""

    DEFAULT_CSS = """
    _SettingSelect {
        height: auto;
        padding: 0 1;
        margin-bottom: 1;
    }
    _SettingSelect Static {
        width: 1fr;
        content-align-vertical: middle;
        height: 3;
    }
    _SettingSelect Select {
        width: 20;
    }
    """

    def __init__(
        self,
        label: str,
        setting_key: str,
        options: list[tuple[str, str]],
        value: str,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self.setting_key = setting_key
        self._label = label
        self._options = options
        self._value = value

    def compose(self):
        yield Static(self._label)
        yield Select(
            [(text, val) for text, val in self._options],
            value=self._value,
            allow_blank=False,
            id=f"select-{self.setting_key}",
        )


_STYLE_OPTIONS = [("Unicode", "unicode"), ("Highlight", "highlight")]
_COLOR_OPTIONS = [(name.capitalize(), name) for name in sorted(NAMED_COLORS)]


class SettingsScreen(TabbableModal, ModalScreen[None]):
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
        Binding("up", "focus_previous", "Previous", show=False, priority=True),
        Binding("down", "focus_next", "Next", show=False, priority=True),
    ]

    SETTINGS = [
        ("Spellcheck", "spellcheck_enabled"),
        ("Markup Preview", "markup_preview_enabled"),
        ("Auto-Reconnect", "auto_reconnect"),
        ("Console Tab", "console_enabled"),
        ("Show Avatars", "show_avatars"),
    ]

    def compose(self):
        config = load_config()
        with VerticalScroll(id="settings-container"):
            yield Static("Settings", id="settings-title")
            _DEFAULTS = {"show_avatars": False}
            for label, key in self.SETTINGS:
                yield _SettingRow(label, key, config.get(key, _DEFAULTS.get(key, True)))

            # Superscript style
            sup_style = config.get("superscript_style", "highlight")
            yield _SettingSelect(
                "Superscript Style", "superscript_style",
                _STYLE_OPTIONS, sup_style,
            )
            sup_color = config.get("superscript_color", "gold")
            yield _SettingSelect(
                "Superscript Color", "superscript_color",
                _COLOR_OPTIONS, sup_color,
                id="row-superscript_color",
            )

            # Subscript style
            sub_style = config.get("subscript_style", "highlight")
            yield _SettingSelect(
                "Subscript Style", "subscript_style",
                _STYLE_OPTIONS, sub_style,
            )
            sub_color = config.get("subscript_color", "skyblue")
            yield _SettingSelect(
                "Subscript Color", "subscript_color",
                _COLOR_OPTIONS, sub_color,
                id="row-subscript_color",
            )

    def on_mount(self) -> None:
        config = load_config()
        # Hide color rows if style is unicode
        if config.get("superscript_style", "highlight") != "highlight":
            self.query_one("#row-superscript_color").display = False
        if config.get("subscript_style", "highlight") != "highlight":
            self.query_one("#row-subscript_color").display = False

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
        elif key == "console_enabled":
            self.app.run_worker(self.app.toggle_console_tab(event.value))

    def on_select_changed(self, event: Select.Changed) -> None:
        select_id = event.select.id or ""
        if not select_id.startswith("select-"):
            return
        key = select_id.removeprefix("select-")
        save_preference(key, event.value)

        # Toggle color picker visibility
        if key == "superscript_style":
            self.query_one("#row-superscript_color").display = (event.value == "highlight")
        elif key == "subscript_style":
            self.query_one("#row-subscript_color").display = (event.value == "highlight")

    def action_close(self) -> None:
        self.dismiss(None)
