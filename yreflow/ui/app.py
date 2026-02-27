"""Textual TUI application for Wolfery."""

import re
from datetime import datetime

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import Header, Footer, Static, Collapsible

from .widgets.message_view import MessageView
from .widgets.input_bar import InputBar
from .widgets.watch_list import Sidebar
from ..formatter import format_message


def _parse_css_color(color_str: str) -> tuple[int, int, int] | None:
    """Parse a CSS color string (hex, rgb(), named) into (r, g, b).

    Returns None if unparseable.
    """
    s = color_str.strip().lower()

    # #rrggbb or #rgb
    m = re.match(r"^#([0-9a-f]{6})$", s)
    if m:
        h = m.group(1)
        return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    m = re.match(r"^#([0-9a-f]{3})$", s)
    if m:
        h = m.group(1)
        return int(h[0] * 2, 16), int(h[1] * 2, 16), int(h[2] * 2, 16)

    # rgb(r, g, b) or rgba(r, g, b, a)
    m = re.match(r"^rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)", s)
    if m:
        return int(m.group(1)), int(m.group(2)), int(m.group(3))

    return None


def _luminance(r: int, g: int, b: int) -> float:
    """Relative luminance (0-1) per WCAG formula."""
    def lin(c):
        c = c / 255.0
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)


def _color_to_hex(color_str: str) -> str | None:
    """Convert a CSS color string to #rrggbb for Rich markup, or None."""
    rgb = _parse_css_color(color_str)
    if rgb:
        return f"#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}"
    return None


class StatusLine(Static):
    """Connection status and current character display."""

    DEFAULT_CSS = """
    StatusLine {
        dock: top;
        height: 1;
        background: $accent;
        color: $text;
        text-style: bold;
        padding: 0 1;
    }
    """


class WolferyApp(App):
    """Main Textual application -- satisfies UIProtocol structurally."""

    TITLE = "yreflow"
    CSS = """
    Screen {
        layout: vertical;
    }
    #content-area {
        height: 1fr;
    }
    #message-column {
        width: 1fr;
    }
    #main-messages {
        height: 1fr;
    }
    #unimportant-collapse {
        height: auto;
        max-height: 12;
    }
    #unimportant-collapse.--collapsed {
        height: auto;
    }
    #unimportant-messages {
        height: auto;
        max-height: 10;
        color: $text-muted;
    }
    """
    BINDINGS = [
        Binding("ctrl+c", "quit", "Quit", priority = True),
        Binding("ctrl+u", "toggle_unimportant", "Toggle activity", priority = True),
        Binding("ctrl+w", "toggle_watch_mode", "Sidebar: compact/full", priority = True),
    ]

    def __init__(self, controller=None, **kwargs):
        super().__init__(**kwargs)
        self.controller = controller
        self.active_character: str | None = None
        self.unimportant_styles = {"sleep", "leave", "arrive", "travel", "action", "wakeup"}

    def compose(self) -> ComposeResult:
        yield Header()
        yield StatusLine("Connecting...", id="status-line")
        with Horizontal(id="content-area"):
            with Vertical(id="message-column"):
                with Collapsible(title="Activity", id="unimportant-collapse", collapsed=True):
                    yield MessageView(id="unimportant-messages")
                yield MessageView(id="main-messages")
            yield Sidebar(id="sidebar")
        yield InputBar(id="input-bar")
        yield Footer()

    async def on_mount(self) -> None:
        if self.controller:
            self.run_worker(self.controller.start(), exclusive=True, name="websocket")

    async def on_input_submitted(self, event: InputBar.Submitted) -> None:
        command = event.value.strip()
        event.input.clear()
        if not command:
            return

        if self.controller and self.active_character:
            result = await self.controller.handle_command(command, self.active_character)
            if result and result.notification:
                await self.notify(result.notification)
            if result and result.exit_app:
                self.exit()

    def action_toggle_unimportant(self) -> None:
        collapse = self.query_one("#unimportant-collapse", Collapsible)
        collapse.collapsed = not collapse.collapsed

    def action_toggle_watch_mode(self) -> None:
        sidebar = self.query_one("#sidebar", Sidebar)
        sidebar.toggle_compact()
        self._rebuild_sidebar()

    def _rebuild_sidebar(self) -> None:
        if not self.controller:
            return
        sidebar = self.query_one("#sidebar", Sidebar)
        sidebar.rebuild(
            self.controller.store,
            self.controller.connection.player,
            self.active_character,
        )

    def _get_focus_color(self, sender_id: str, character: str) -> str | None:
        """Check if sender_id is focused by character. Returns hex color or None."""
        if not self.controller or not character:
            return None
        store = self.controller.store
        focus = store.get_character_attribute(character, "focus", {})
        if not isinstance(focus, dict):
            return None
        if sender_id in focus:
            try:
                css_color = focus[sender_id]["data"]["color"]
                return _color_to_hex(css_color) or css_color
            except (KeyError, TypeError):
                return None
        return None

    # --- UIProtocol implementation ---

    async def display_message(self, message: dict, style: str, character: str) -> None:
        if style in self.unimportant_styles:
            view = self.query_one("#unimportant-messages", MessageView)
        else:
            view = self.query_one("#main-messages", MessageView)

        sender = message["frm"].get("name", "???")
        sender_id = message["frm"].get("id", "")
        msg_text = format_message(message.get("msg", ""))
        target = message.get("t", {})
        target_name = target.get("name", "")
        j = message.get("j", {})
        has_pose = j.get("pose", False)
        is_ooc = j.get("ooc", False)

        timestamp = ""
        if "time" in j:
            dt = datetime.fromtimestamp(j["time"] / 1000.0)
            timestamp = dt.strftime("%H:%M")

        focus_color = self._get_focus_color(sender_id, character)

        line = self._format_line(
            style, sender, msg_text, target_name,
            has_pose, is_ooc, timestamp, focus_color,
        )
        view.write(line)

    def _format_timestamp(self, timestamp: str, focus_color: str | None) -> str:
        """Format the timestamp, applying focus background color if set."""
        if not timestamp:
            return ""
        if focus_color:
            # Determine text color based on background luminance
            rgb = _parse_css_color(focus_color)
            if rgb and _luminance(*rgb) > 0.4:
                fg = "#333333"
            else:
                fg = "#cccccc"
            return f"[{fg} on {focus_color}] {timestamp} [/] "
        return f"[dim]{timestamp}[/dim] "

    def _format_line(
        self,
        style: str,
        sender: str,
        msg: str,
        target_name: str,
        has_pose: bool,
        is_ooc: bool,
        timestamp: str,
        focus_color: str | None = None,
    ) -> str:
        ts = self._format_timestamp(timestamp, focus_color)

        if is_ooc and style not in ("ooc",):
            msg = f"[dim]{msg}[/dim]"

        if style == "say":
            return f'{ts}[bold cyan]{sender}[/bold cyan] says, "{msg}"'

        if style == "pose":
            return f"{ts}[bold cyan]{sender}[/bold cyan] {msg}"

        if style == "ooc":
            if has_pose:
                return f"{ts}[dim]\\[OOC][/dim] [bold cyan]{sender}[/bold cyan] [dim]{msg}[/dim]"
            return f'{ts}[dim]\\[OOC][/dim] [bold cyan]{sender}[/bold cyan] [dim]says, "{msg}"[/dim]'

        if style == "whisper":
            label = f"[magenta]whisper {target_name}[/magenta]"
            if has_pose:
                return f"{ts}[bold cyan]{sender}[/bold cyan] ({label}) {msg}"
            return f'{ts}[bold cyan]{sender}[/bold cyan] ({label}) whispers, "{msg}"'

        if style == "message":
            label = f"[yellow]msg {target_name}[/yellow]"
            if has_pose:
                return f"{ts}[bold cyan]{sender}[/bold cyan] ({label}) {msg}"
            return f'{ts}[bold cyan]{sender}[/bold cyan] ({label}) messages, "{msg}"'

        if style == "address":
            label = f"[green]@{target_name}[/green]"
            if has_pose:
                return f"{ts}[bold cyan]{sender}[/bold cyan] ({label}) {msg}"
            return f'{ts}[bold cyan]{sender}[/bold cyan] ({label}) says, "{msg}"'

        if style == "describe":
            return f"{ts}[italic]{msg}[/italic]"

        if style in ("arrive", "leave", "travel", "sleep", "action", "wakeup"):
            return f"{ts}[dim][bold]{sender}[/bold] {msg}[/dim]"

        if style == "roll":
            return f"{ts}[bold cyan]{sender}[/bold cyan] {msg}"

        # Fallback
        return f"{ts}[bold cyan]{sender}[/bold cyan] {msg}"

    async def display_system_text(self, text: str) -> None:
        view = self.query_one("#main-messages", MessageView)
        view.write(f"[yellow]{text}[/yellow]")

    async def notify(self, text: str, **kwargs) -> None:
        view = self.query_one("#main-messages", MessageView)
        view.write(f"[bold yellow]>> {text}[/bold yellow]")

    async def update_room(self) -> None:
        self._rebuild_sidebar()

    async def update_watch_list(self) -> None:
        self._rebuild_sidebar()

    async def ensure_character_tab(self, character: str) -> None:
        if self.active_character is None:
            self.active_character = character
            status = self.query_one("#status-line", StatusLine)
            name = "Unknown"
            if self.controller:
                store = self.controller.store
                name = store.get_character_attribute(character, "name")
                surname = store.get_character_attribute(character, "surname")
                if surname:
                    name = f"{name} {surname}"
            status.update(f"Connected as: {name} ({character})")

    async def log_raw(self, text: str) -> None:
        # Debug logging -- no-op for now
        pass
