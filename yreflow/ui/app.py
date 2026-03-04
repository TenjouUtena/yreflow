"""Textual TUI application for Wolfery."""

import re
from datetime import datetime
from functools import partial

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.command import Provider, Hit, Hits
from textual.containers import Horizontal, Vertical
from textual.widgets import Header, Footer, Collapsible

from .widgets.message_view import MessageView
from .widgets.input_bar import InputBar
from .widgets.watch_list import Sidebar
from .widgets.character_bar import CharacterBar, CharacterButton, AddCharacterButton
from .screens.character_select import CharacterSelectScreen
from .screens.look_screen import LookScreen
from .screens.login_screen import LoginScreen
from .screens.profile_select import ProfileSelectScreen
from .screens.store_browser import StoreBrowserScreen
from ..config import load_config, save_preference
from ..formatter import format_message


_NAMED_COLORS: dict[str, tuple[int, int, int]] = {
    "black": (0, 0, 0), "white": (255, 255, 255),
    "red": (255, 0, 0), "green": (0, 128, 0), "blue": (0, 0, 255),
    "yellow": (255, 255, 0), "cyan": (0, 255, 255), "magenta": (255, 0, 255),
    "lime": (0, 255, 0), "orange": (255, 165, 0), "pink": (255, 192, 203),
    "purple": (128, 0, 128), "violet": (238, 130, 238),
    "brown": (165, 42, 42), "gold": (255, 215, 0),
    "silver": (192, 192, 192), "gray": (128, 128, 128), "grey": (128, 128, 128),
    "navy": (0, 0, 128), "teal": (0, 128, 128), "maroon": (128, 0, 0),
    "olive": (128, 128, 0), "aqua": (0, 255, 255), "fuchsia": (255, 0, 255),
    "coral": (255, 127, 80), "salmon": (250, 128, 114),
    "tomato": (255, 99, 71), "crimson": (220, 20, 60),
    "turquoise": (64, 224, 208), "indigo": (75, 0, 130),
    "khaki": (240, 230, 140), "lavender": (230, 230, 250),
    "plum": (221, 160, 221), "orchid": (218, 112, 214),
    "sienna": (160, 82, 45), "tan": (210, 180, 140),
    "thistle": (216, 191, 216), "wheat": (245, 222, 179),
    "hotpink": (255, 105, 180), "deeppink": (255, 20, 147),
    "skyblue": (135, 206, 235), "steelblue": (70, 130, 180),
    "lightblue": (173, 216, 230), "lightgreen": (144, 238, 144),
    "lightyellow": (255, 255, 224), "lightpink": (255, 182, 193),
    "darkred": (139, 0, 0), "darkgreen": (0, 100, 0), "darkblue": (0, 0, 139),
    "darkorange": (255, 140, 0), "darkviolet": (148, 0, 211),
}


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

    # Named CSS colors
    if s in _NAMED_COLORS:
        return _NAMED_COLORS[s]

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


class WolferyCommands(Provider):
    """Command palette entries for yreflow actions."""

    COMMANDS = [
        ("Toggle activity panel", "toggle_unimportant", "Show/hide the activity section (Ctrl+U)"),
        ("Toggle sidebar mode", "toggle_watch_mode", "Switch sidebar between compact and full (Ctrl+W)"),
        ("Next character", "next_character", "Switch to the next character tab (Ctrl+N)"),
        ("Previous character", "prev_character", "Switch to the previous character tab (Ctrl+P)"),
        ("Open character select", "open_character_select", "Awaken or switch to a character (Ctrl+F)"),
        ("Quit", "quit", "Exit yreflow (Ctrl+C)"),
        ("Toggle spellcheck", "toggle_spellcheck", "Inline spellcheck highlighting (Ctrl+S)"),
        ("Toggle markup preview", "toggle_markup_preview", "Wolfery markup preview (Ctrl+T)"),
        ("Browse store", "open_store_browser", "Browse the live model store for debugging (Ctrl+D)"),
    ]

    async def search(self, query: str) -> Hits:
        matcher = self.matcher(query)
        for name, action, help_text in self.COMMANDS:
            score = matcher.match(name)
            if score > 0:
                yield Hit(score, matcher.highlight(name), partial(self.app.run_action, action), help=help_text)


_UNIMPORTANT_STYLES = {"sleep", "leave", "arrive", "travel", "action", "wakeup"}


class WolferyApp(App):
    """Main Textual application -- satisfies UIProtocol structurally."""

    TITLE = "yreflow"
    COMMANDS = {WolferyCommands}
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
    .char-main-messages {
        height: 1fr;
    }
    .char-unimportant-collapse {
        height: auto;
        max-height: 12;
        padding: 0;
        border-top: solid $surface-lighten-1;
    }
    .char-unimportant-collapse.--collapsed {
        height: auto;
    }
    .char-unimportant-collapse Contents {
        padding: 0;
    }
    .char-unimportant-messages {
        height: auto;
        max-height: 10;
        color: $text-muted;
    }
    """
    BINDINGS = [
        Binding("ctrl+c", "quit", "Quit", priority=True),
        Binding("ctrl+u", "toggle_unimportant", "Toggle activity", priority=True),
        Binding("ctrl+w", "toggle_watch_mode", "Sidebar: compact/full", priority=True),
        Binding("ctrl+p", "prev_character", "Prev char", priority=True),
        Binding("ctrl+n", "next_character", "Next char", priority=True),
        Binding("ctrl+f", "open_character_select", "New char", priority=True),
        Binding("ctrl+grave_accent", "command_palette", "Commands", priority=True),
        Binding("ctrl+s", "toggle_spellcheck", "Spellcheck", priority=True),
        Binding("ctrl+t", "toggle_markup_preview", "Markup", priority=True),
        Binding("ctrl+d", "open_store_browser", "Store browser", priority=True),
    ]

    def __init__(self, controller=None, **kwargs):
        super().__init__(**kwargs)
        self.controller = controller
        self.active_character: str | None = None
        self.character_views: dict[str, dict] = {}
        self.unread_counts: dict[str, int] = {}
        self.character_order: list[str] = []
        self.unimportant_styles = _UNIMPORTANT_STYLES

    def compose(self) -> ComposeResult:
        yield Header()
        yield CharacterBar(id="character-bar")
        with Horizontal(id="content-area"):
            yield Vertical(id="message-column")
            yield Sidebar(id="sidebar")
        yield InputBar(id="input-bar")
        yield Footer()

    async def on_mount(self) -> None:
        # Restore highlighter preferences
        config = load_config()
        input_bar = self.query_one("#input-bar", InputBar)
        if config.get("spellcheck_enabled", False):
            input_bar.set_highlighter_state("spellcheck", True)
        if config.get("markup_preview_enabled", False):
            input_bar.set_highlighter_state("markup", True)

        if self.controller:
            if self.controller.connection.auth_mode == "token":
                self.run_worker(self.controller.start(), exclusive=True, name="websocket")
                self.set_timer(3.0, self._check_initial_characters)
            else:
                self.push_screen(LoginScreen(), callback=self._on_login_result)

    def _check_initial_characters(self) -> None:
        """Show character select if no characters appeared after connect."""
        if not self.character_order and self.controller and self.controller.connection.player:
            self.action_open_character_select()

    def _on_login_result(self, credentials: tuple[str, str] | None) -> None:
        """Handle login screen dismissal."""
        if credentials is None:
            self.exit()
            return
        username, password = credentials
        self.run_worker(
            self._login_and_connect(username, password),
            exclusive=True,
            name="websocket",
        )
        self.set_timer(3.0, self._check_initial_characters)

    async def _login_and_connect(self, username: str, password: str) -> None:
        """Obtain token via HTTP, then connect. Falls back to login screen on failure."""
        try:
            await self.controller.start_with_credentials(username, password)
        except ValueError as e:
            await self.show_login(error=str(e))

    async def show_login(self, error: str | None = None) -> None:
        """Show the login screen, optionally with an error message."""
        self.push_screen(LoginScreen(error=error), callback=self._on_login_result)

    # --- Input handling ---

    async def on_input_submitted(self, event: InputBar.Submitted) -> None:
        command = event.value.strip()
        event.input.clear()
        if not command:
            return

        input_bar = self.query_one("#input-bar", InputBar)
        input_bar.push_history(command)

        if self.controller and self.active_character:
            result = await self.controller.handle_command(command, self.active_character)
            if result and result.look_data:
                self.push_screen(LookScreen(result.look_data))
            if result and result.open_profile_select:
                self.push_screen(
                    ProfileSelectScreen(
                        self.controller.store,
                        self.controller.connection,
                        self.active_character,
                    ),
                    callback=self._on_profile_selected,
                )
            if result and result.display_text:
                await self.display_system_text(result.display_text)
            if result and result.notification:
                await self.notify(result.notification)

    def _on_profile_selected(self, profile_name: str | None) -> None:
        if profile_name:
            self.run_worker(self.notify(f"Morphing into {profile_name}..."))

    # --- Character switching ---

    def _switch_to_character(self, character: str) -> None:
        """Switch the active view to the given character."""
        if character not in self.character_views:
            return

        # Hide current character's container
        if self.active_character and self.active_character in self.character_views:
            self.character_views[self.active_character]["container"].display = False

        # Show new character's container
        self.active_character = character
        self.character_views[character]["container"].display = True

        # Update CharacterBar highlight and clear unread
        char_bar = self.query_one("#character-bar", CharacterBar)
        char_bar.set_active(character)
        self.unread_counts[character] = 0
        char_bar.update_unread(character, 0)

        # Switch input history to this character
        input_bar = self.query_one("#input-bar", InputBar)
        input_bar.set_active_character(character)

        # Rebuild sidebar for this character's room
        self._rebuild_sidebar()

    def _cycle_character(self, direction: int) -> None:
        if not self.character_order or not self.active_character:
            return
        try:
            idx = self.character_order.index(self.active_character)
        except ValueError:
            return
        new_idx = (idx + direction) % len(self.character_order)
        self._switch_to_character(self.character_order[new_idx])

    def on_character_button_clicked(self, event: CharacterButton.Clicked) -> None:
        self._switch_to_character(event.character_id)

    def on_add_character_button_clicked(self, event: AddCharacterButton.Clicked) -> None:
        self.action_open_character_select()

    # --- Actions ---

    def action_toggle_unimportant(self) -> None:
        if self.active_character and self.active_character in self.character_views:
            collapse = self.character_views[self.active_character]["collapsible"]
            collapse.collapsed = not collapse.collapsed

    def action_toggle_watch_mode(self) -> None:
        sidebar = self.query_one("#sidebar", Sidebar)
        sidebar.toggle_compact()
        self._rebuild_sidebar()

    def action_prev_character(self) -> None:
        self._cycle_character(-1)

    def action_next_character(self) -> None:
        self._cycle_character(1)

    def action_open_character_select(self) -> None:
        if not self.controller:
            return
        self.push_screen(
            CharacterSelectScreen(
                self.controller.store,
                self.controller.connection,
            )
        )

    def action_toggle_spellcheck(self) -> None:
        input_bar = self.query_one("#input-bar", InputBar)
        enabled = input_bar.toggle_spellcheck()
        save_preference("spellcheck_enabled", enabled)
        input_bar.refresh()
        self.notify(f"Spellcheck {'on' if enabled else 'off'}")

    def action_toggle_markup_preview(self) -> None:
        input_bar = self.query_one("#input-bar", InputBar)
        enabled = input_bar.toggle_markup_preview()
        save_preference("markup_preview_enabled", enabled)
        input_bar.refresh()
        self.notify(f"Markup preview {'on' if enabled else 'off'}")

    def action_open_store_browser(self) -> None:
        if self.controller:
            self.push_screen(StoreBrowserScreen(self.controller.store))

    def on_input_bar_recall_directed(self, event: InputBar.RecallDirected) -> None:
        """Handle ! recall: insert the nth directed contact into the input bar."""
        if not self.controller:
            return
        contacts = self.controller.connection.directed_contacts
        if not contacts:
            return
        contact = contacts[event.index % len(contacts)]
        names_str = ", ".join(contact.names)
        command = f"{contact.prefix} {names_str}="
        input_bar = self.query_one("#input-bar", InputBar)
        input_bar.value = command
        input_bar.cursor_position = len(command)

    # --- Sidebar ---

    def _rebuild_sidebar(self) -> None:
        if not self.controller:
            return
        sidebar = self.query_one("#sidebar", Sidebar)
        sidebar.rebuild(
            self.controller.store,
            self.controller.connection.player,
            self.active_character,
        )
        self._update_spellcheck_dictionary()

    def _update_spellcheck_dictionary(self) -> None:
        """Feed character names into the spellcheck custom dictionary."""
        if not self.controller:
            return
        store = self.controller.store
        words: set[str] = set()
        try:
            chars = store.get("core.char")
            for key in chars:
                name = store.get_character_attribute(key, "name")
                surname = store.get_character_attribute(key, "surname")
                if name:
                    for part in name.split():
                        words.add(part)
                if surname:
                    for part in surname.split():
                        words.add(part)
        except (KeyError, AttributeError):
            pass
        input_bar = self.query_one("#input-bar", InputBar)
        input_bar.update_spellcheck_words(words)

    # --- Focus color ---

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
        if character not in self.character_views:
            return

        views = self.character_views[character]
        if style in self.unimportant_styles:
            view = views["unimportant"]
        else:
            view = views["main"]

        sender = message["frm"].get("name", "???")
        sender_id = message["frm"].get("id", "")
        msg_text = format_message(message.get("msg", ""))
        j = message.get("j", {})
        target = message.get("t", {})
        target_first_name = target.get("name", "")
        targets_extra = j.get("targets", [])
        if targets_extra and target_first_name:
            all_names = [target_first_name] + [t.get("name", "") for t in targets_extra if t.get("name")]
            target_name = ", ".join(all_names)
        else:
            target_name = target_first_name
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

        # Unread tracking for non-active characters
        if character != self.active_character and style not in self.unimportant_styles:
            self.unread_counts[character] = self.unread_counts.get(character, 0) + 1
            char_bar = self.query_one("#character-bar", CharacterBar)
            char_bar.update_unread(character, self.unread_counts[character])

    def _format_timestamp(self, timestamp: str, focus_color: str | None) -> str:
        """Format the timestamp, applying focus background color if set."""
        if not timestamp:
            return ""
        if focus_color:
            rgb = _parse_css_color(focus_color)
            if rgb and _luminance(*rgb) > 0.3:
                fg = "#333333"
            else:
                fg = "#cccccc"
            return f"[{fg} on {focus_color}]{timestamp}[/] "
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

        if style == "leadRequest":
            return f"{ts}[bold yellow]>> [bold cyan]{sender}[/bold cyan] wants to lead {target_name}.[/bold yellow]"

        if style == "followRequest":
            return f"{ts}[bold yellow]>> [bold cyan]{sender}[/bold cyan] wants to follow {target_name}.[/bold yellow]"

        if style == "controlRequest":
            return f"{ts}[bold yellow]>> [bold cyan]{sender}[/bold cyan] requests control of {target_name}.[/bold yellow]"

        # Fallback
        return f"{ts}[bold cyan]{sender}[/bold cyan] {msg}"

    async def display_system_text(self, text: str) -> None:
        if self.active_character and self.active_character in self.character_views:
            view = self.character_views[self.active_character]["main"]
            view.write(f"[yellow]{text}[/yellow]")

    async def notify(self, text: str, **kwargs) -> None:
        if self.active_character and self.active_character in self.character_views:
            view = self.character_views[self.active_character]["main"]
            view.write(f"[bold yellow]>> {text}[/bold yellow]")

    async def update_room(self) -> None:
        self._rebuild_sidebar()

    async def update_watch_list(self) -> None:
        self._rebuild_sidebar()

    async def ensure_character_tab(self, character: str) -> None:
        if character in self.character_views:
            return

        # Get character display name
        name = "Unknown"
        if self.controller:
            store = self.controller.store
            name = store.get_character_attribute(character, "name")
            surname = store.get_character_attribute(character, "surname")
            if surname:
                name = f"{name} {surname}"

        # Create per-character message views
        main_view = MessageView(
            id=f"main-{character}", classes="char-main-messages",
        )
        unimportant_view = MessageView(
            id=f"unimportant-{character}", classes="char-unimportant-messages",
        )
        collapsible = Collapsible(
            unimportant_view,
            title="Activity",
            id=f"collapse-{character}",
            collapsed=True,
        )
        collapsible.add_class("char-unimportant-collapse")
        container = Vertical(
            id=f"char-container-{character}",
        )

        # Mount the container into message column
        msg_col = self.query_one("#message-column", Vertical)
        await msg_col.mount(container)

        # Mount children into the container
        await container.mount(collapsible)
        await container.mount(main_view)

        # Start hidden
        container.display = False

        # Store references
        self.character_views[character] = {
            "main": main_view,
            "unimportant": unimportant_view,
            "container": container,
            "collapsible": collapsible,
        }
        self.unread_counts[character] = 0
        self.character_order.append(character)

        # Add button to CharacterBar
        char_bar = self.query_one("#character-bar", CharacterBar)
        await char_bar.add_character(character, name or "Unknown")

        # If this is the first character, make it active
        if self.active_character is None:
            self._switch_to_character(character)

    async def remove_character_tab(self, character: str) -> None:
        """Remove a character's views and button after release."""
        if character not in self.character_views:
            return

        # Remove the UI container
        views = self.character_views[character]
        await views["container"].remove()

        # Remove from CharacterBar
        char_bar = self.query_one("#character-bar", CharacterBar)
        char_bar.remove_character(character)

        # Clean up data structures
        del self.character_views[character]
        del self.unread_counts[character]
        self.character_order.remove(character)

        # If this was the active character, switch to another or show select
        if self.active_character == character:
            self.active_character = None
            if self.character_order:
                self._switch_to_character(self.character_order[0])
            else:
                self.action_open_character_select()

    def get_known_characters(self) -> set[str]:
        return set(self.character_views.keys())

    async def display_look(self, data: dict) -> None:
        self.push_screen(LookScreen(data))

    async def log_raw(self, text: str) -> None:
        # Debug logging -- no-op for now
        pass
