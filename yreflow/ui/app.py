"""Textual TUI application for Wolfery."""

import re
from datetime import datetime
from functools import partial

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.command import Provider, Hit, Hits
from textual.screen import ModalScreen
from textual.containers import Horizontal, Vertical
from textual.widgets import Header, Footer, Collapsible

from .widgets.message_view import MessageView
from .widgets.input_bar import InputBar
from .widgets.nav_panel import NavPanel
from .widgets.watch_list import Sidebar
from .widgets.character_bar import CharacterBar, CharacterButton, AddCharacterButton
from .widgets.connection_indicator import ConnectionIndicator
from .screens.character_select import CharacterSelectScreen
from .screens.look_screen import LookScreen
from .screens.login_screen import LoginScreen
from .screens.profile_select import ProfileSelectScreen
from .screens.store_browser import StoreBrowserScreen
from .screens.url_screen import UrlScreen
from .screens.settings_screen import SettingsScreen
from ..config import load_config, save_preference, formatter_settings
from ..formatter import format_message
from .format_line import (
    format_line as _format_line_fn,
    format_timestamp as _format_timestamp_fn,
    _parse_css_color,
)

from ..constants import NAMED_COLORS


def _color_to_hex(color_str: str) -> str | None:
    """Convert a CSS color string to #rrggbb for Rich markup, or None."""
    rgb = _parse_css_color(color_str)
    if rgb:
        return f"#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}"
    return None


class WolferyCommands(Provider):
    """Command palette entries for yreflow actions."""

    COMMANDS = [
        ("Toggle muted panel", "toggle_unimportant", "Show/hide the muted section (F3)"),
        ("Recent URLs", "show_urls", "Show recently captured URLs (Ctrl+U)"),
        ("Toggle sidebar mode", "toggle_watch_mode", "Switch sidebar between compact and full (Ctrl+W)"),
        ("Next character", "next_character", "Switch to the next character tab (Ctrl+N)"),
        ("Previous character", "prev_character", "Switch to the previous character tab (Ctrl+P)"),
        ("Open character select", "open_character_select", "Awaken or switch to a character (Ctrl+F)"),
        ("Quit", "quit", "Exit yreflow (Ctrl+C)"),
        ("Toggle spellcheck", "toggle_spellcheck", "Inline spellcheck highlighting (Ctrl+S)"),
        ("Toggle markup preview", "toggle_markup_preview", "Wolfery markup preview (Ctrl+T)"),
        ("Browse store", "open_store_browser", "Browse the live model store for debugging (Ctrl+D)"),
        ("Toggle navigation", "toggle_nav_panel", "Open/close navigation panel (Ctrl+G)"),
        ("Settings", "open_settings", "Open settings screen"),
    ]

    async def search(self, query: str) -> Hits:
        matcher = self.matcher(query)
        for name, action, help_text in self.COMMANDS:
            score = matcher.match(name)
            if score > 0:
                yield Hit(score, matcher.highlight(name), partial(self.app.run_action, action), help=help_text)


_UNIMPORTANT_STYLES = {"sleep", "leave", "arrive", "travel", "action", "wakeup"}
_TRAVEL_STYLES = {"leave", "arrive", "travel", "wakeup", "sleep"}
_OOC_STYLES = {"ooc"}
_CONSOLE_ID = "__console__"


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
        Binding("ctrl+u", "show_urls", "URLs", priority=True),
        Binding("f3", "toggle_unimportant", "Toggle muted", priority=True),
        Binding("ctrl+w", "toggle_watch_mode", "Sidebar: compact/full", priority=True),
        Binding("ctrl+p", "prev_character", "Prev char", priority=True),
        Binding("ctrl+n", "next_character", "Next char", priority=True),
        Binding("ctrl+f", "open_character_select", "New char", priority=True),
        Binding("ctrl+grave_accent", "command_palette", "Commands", priority=True),
        Binding("ctrl+d", "open_store_browser", "Store browser", priority=True),
        Binding("ctrl+g", "toggle_nav_panel", "Navigation", priority=True),
        Binding("tab", "autocomplete", "Fire Autocomplete", priority=True)
    ]

    async def action_autocomplete(self):
        # On modal screens, Tab should cycle focus instead of autocomplete.
        if isinstance(self.screen, ModalScreen):
            self.screen.focus_next()
            return
        input_bar = self.query_one("#input-bar", InputBar)
        # If we're already cycling through completions, just cycle.
        if input_bar._autocompleting:
            input_bar.cycle_completion()
            return
        # Let plugins try to handle autocomplete first.
        if self.controller and self.active_character:
            handled = await self.controller.event_bus.publish_interceptable(
                "autocomplete.try",
                input=input_bar.value,
                cursor=input_bar.cursor_position,
                ctrl_id=self.active_character,
            )
            if handled:
                return
        await input_bar.autocomplete()


    def __init__(self, controller=None, **kwargs):
        super().__init__(**kwargs)
        self.controller = controller
        self.active_character: str | None = None
        self.character_views: dict[str, dict] = {}
        self._pending_notifications: dict[str, list[str]] = {}
        self.unread_counts: dict[str, int] = {}
        self.urgent_unreads: dict[str, bool] = {}
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

        input_bar.focus()

        if config.get("console_enabled", False):
            await self._create_console_tab()

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

    # --- Console tab ---

    async def _create_console_tab(self) -> None:
        """Create the console tab (no collapsible, just a single message view)."""
        if _CONSOLE_ID in self.character_views:
            return
        main_view = MessageView(
            id=f"main-{_CONSOLE_ID}", classes="char-main-messages",
        )
        container = Vertical(id=f"char-container-{_CONSOLE_ID}")
        msg_col = self.query_one("#message-column", Vertical)
        await msg_col.mount(container)
        await container.mount(main_view)
        container.display = False

        self.character_views[_CONSOLE_ID] = {
            "main": main_view,
            "container": container,
        }
        self.unread_counts[_CONSOLE_ID] = 0
        self.urgent_unreads[_CONSOLE_ID] = False
        self.character_order.insert(0, _CONSOLE_ID)

        char_bar = self.query_one("#character-bar", CharacterBar)
        await char_bar.add_character(_CONSOLE_ID, "Console", console=True)

    async def _remove_console_tab(self) -> None:
        """Remove the console tab."""
        if _CONSOLE_ID not in self.character_views:
            return
        views = self.character_views[_CONSOLE_ID]
        await views["container"].remove()
        char_bar = self.query_one("#character-bar", CharacterBar)
        char_bar.remove_character(_CONSOLE_ID)
        del self.character_views[_CONSOLE_ID]
        del self.unread_counts[_CONSOLE_ID]
        del self.urgent_unreads[_CONSOLE_ID]
        self.character_order.remove(_CONSOLE_ID)
        if self.active_character == _CONSOLE_ID:
            self.active_character = None
            if self.character_order:
                self._switch_to_character(self.character_order[0])

    async def toggle_console_tab(self, enabled: bool) -> None:
        """Create or remove the console tab (called from settings)."""
        if enabled:
            await self._create_console_tab()
        else:
            await self._remove_console_tab()

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

        if not self.controller or not self.active_character:
            return

        # Console tab: separate command handler
        if self.active_character == _CONSOLE_ID:
            result = await self.controller.handle_console_command(command)
            if result and result.display_text:
                await self.display_system_text(result.display_text)
            if result and result.notification:
                await self.notify(result.notification)
            return

        # Character/puppet tabs
        # Nav mode: check if typed text matches an exit name
        views = self.character_views.get(self.active_character, {})
        nav_panel = views.get("nav_panel")
        if nav_panel and nav_panel.display:
            matched = nav_panel.find_exit_by_key(command)
            if matched:
                cc = self.controller.connection.get_controlled_char(self.active_character)
                if cc:
                    await self.controller.connection.send(
                        f"call.{cc.ctrl_path}.useExit",
                        {"exitId": matched["id"]},
                    )
                    return

        result = await self.controller.handle_command(command, self.active_character)
        if result and result.look_data:
            self.push_screen(LookScreen(result.look_data, on_url=self._publish_url))
        if result and result.open_profile_select:
            cc = self.controller.connection.get_controlled_char(self.active_character)
            if cc is None:
                from ..protocol.controlled_char import ControlledChar
                cc = ControlledChar(char_id=self.active_character)
            self.push_screen(
                ProfileSelectScreen(
                    self.controller.store,
                    self.controller.connection,
                    cc,
                ),
                callback=self._on_profile_selected,
            )
        if result and result.open_settings:
            self.action_open_settings()
        if result and result.toggle_nav:
            await self.action_toggle_nav_panel()
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
        self.urgent_unreads[character] = False
        char_bar.update_unread(character, 0, False)

        # Switch input history to this character
        input_bar = self.query_one("#input-bar", InputBar)
        input_bar.set_active_character(character)

        if character == _CONSOLE_ID:
            # Console has no nav panel or room context
            input_bar.set_nav_mode(False)
            return

        # Sync nav mode with new character's nav panel state
        nav_panel = self.character_views[character].get("nav_panel")
        input_bar.set_nav_mode(bool(nav_panel and nav_panel.display))

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

    def action_open_settings(self) -> None:
        self.push_screen(SettingsScreen())

    def action_open_store_browser(self) -> None:
        if self.controller:
            self.push_screen(StoreBrowserScreen(self.controller.store))

    def action_show_urls(self) -> None:
        if self.controller:
            self.push_screen(UrlScreen(self.controller.url_catcher.recent(20)))

    def _publish_url(self, display_text: str, url: str) -> None:
        """Synchronous callback for format_message — captures the URL directly."""
        if self.controller:
            self.controller.url_catcher.capture(display_text, url)

    async def action_toggle_nav_panel(self) -> None:
        if not self.controller or not self.active_character:
            return
        views = self.character_views.get(self.active_character)
        if not views:
            return
        input_bar = self.query_one("#input-bar", InputBar)
        nav_panel = views.get("nav_panel")
        if nav_panel is None:
            # First open: mount the panel into the character container
            nav_panel = NavPanel(on_url=self._publish_url, id=f"nav-panel-{self.active_character}")
            container = views["container"]
            await container.mount(nav_panel)
            views["nav_panel"] = nav_panel
            char_path = self._resolve_char_path(self.active_character)
            await nav_panel.refresh_data(self.controller.store, char_path)
            input_bar.set_nav_mode(True)
        elif nav_panel.display:
            nav_panel.display = False
            input_bar.set_nav_mode(False)
        else:
            nav_panel.display = True
            char_path = self._resolve_char_path(self.active_character)
            await nav_panel.refresh_data(self.controller.store, char_path)
            input_bar.set_nav_mode(True)

    async def on_nav_panel_exit_selected(self, event: NavPanel.ExitSelected) -> None:
        """Handle directional navigation from the nav panel."""
        if not self.controller or not self.active_character:
            return
        cc = self.controller.connection.get_controlled_char(self.active_character)
        if cc is None:
            return
        await self.controller.connection.send(
            f"call.{cc.ctrl_path}.useExit",
            {"exitId": event.exit_id},
        )

    def on_nav_panel_close_requested(self, event: NavPanel.CloseRequested) -> None:
        """Close the navigation panel on ESC."""
        if self.active_character and self.active_character in self.character_views:
            nav_panel = self.character_views[self.active_character].get("nav_panel")
            if nav_panel:
                nav_panel.display = False
                input_bar = self.query_one("#input-bar", InputBar)
                input_bar.set_nav_mode(False)

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
        active_char_path = self._resolve_char_path(self.active_character) if self.active_character else None
        sidebar.rebuild(
            self.controller.store,
            self.controller.connection.player,
            active_char_path,
        )
        self._update_spellcheck_dictionary()

    def _update_spellcheck_dictionary(self) -> None:
        """Feed character names into the spellcheck custom dictionary."""
        if not self.controller:
            return
        store = self.controller.store
        words: set[str] = {
            "unwatch", "whois", "laston", "teleport", "lfrp",
            "unfocus", "ooc",
        }
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

    # --- Character settings helpers ---

    def _get_mute_travel(self, character: str) -> bool:
        """Check the muteTravel setting for a character. Defaults to True."""
        if not self.controller:
            return True
        store = self.controller.store
        cc = self.controller.connection.get_controlled_char(character)
        char_id = cc.char_id if cc else character
        try:
            return bool(store.get(f"core.char.{char_id}.settings.muteTravel"))
        except (KeyError, AttributeError):
            return True

    def _get_mute_ooc(self, character: str) -> bool:
        """Check the muteOoc setting for a character. Defaults to False."""
        if not self.controller:
            return False
        store = self.controller.store
        cc = self.controller.connection.get_controlled_char(character)
        char_id = cc.char_id if cc else character
        try:
            return bool(store.get(f"core.char.{char_id}.settings.muteOoc"))
        except (KeyError, AttributeError):
            return False

    # --- Focus color ---

    def _get_focus_color(self, sender_id: str, character: str) -> str | None:
        """Check if sender_id is focused by character. Returns hex color or None."""
        if not self.controller or not character:
            return None
        store = self.controller.store
        cc = self.controller.connection.get_controlled_char(character)
        char_id = cc.char_id if cc else character
        focus = store.get_character_attribute(char_id, "focus", {})
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
        mute_travel = self._get_mute_travel(character)
        mute_ooc = self._get_mute_ooc(character)
        if style in self.unimportant_styles:
            # If muteTravel is off, travel messages go to the main view
            if not mute_travel and style in _TRAVEL_STYLES:
                view = views["main"]
            else:
                view = views["unimportant"]
        elif mute_ooc and style in _OOC_STYLES:
            view = views["unimportant"]
        else:
            view = views["main"]

        sender = message["frm"].get("name", "")
        if style == 'describe':
            sender = message["frm"].get("name","") + ' ' + message["frm"].get("surname","")

        sender_id = message["frm"].get("id", "")
        if style == "roll":
            msg_text = message.get("msg", "")  # already Rich-formatted
        else:
            msg_text = format_message(message.get("msg", ""), on_url=self._publish_url, **formatter_settings())
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
        view.write(f"{line}")

        # Unread tracking for non-active characters
        is_muted = (
            (style in self.unimportant_styles and not (not mute_travel and style in _TRAVEL_STYLES))
            or (mute_ooc and style in _OOC_STYLES)
        )
        if character != self.active_character and not is_muted:
            self.unread_counts[character] = self.unread_counts.get(character, 0) + 1
            if style in ("whisper", "message", "address"):
                self.urgent_unreads[character] = True
            self._update_unread_display(character)

    def _update_unread_display(self, character: str) -> None:
        """Push current unread count and urgency to the CharacterBar."""
        char_bar = self.query_one("#character-bar", CharacterBar)
        count = self.unread_counts.get(character, 0)
        urgent = self.urgent_unreads.get(character, False)
        char_bar.update_unread(character, count, urgent)

    def _format_timestamp(self, timestamp: str, focus_color: str | None) -> str:
        return _format_timestamp_fn(timestamp, focus_color)

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
        return _format_line_fn(
            style, sender, msg, target_name, has_pose, is_ooc, timestamp, focus_color
        )

    async def display_system_text(self, text: str) -> None:
        if self.active_character and self.active_character in self.character_views:
            view = self.character_views[self.active_character]["main"]
            view.write(f"[yellow]{text}[/yellow]")
        # Also write to console tab (if it exists and isn't already the active tab)
        if _CONSOLE_ID in self.character_views and self.active_character != _CONSOLE_ID:
            self.character_views[_CONSOLE_ID]["main"].write(f"[yellow]{text}[/yellow]")
            self.unread_counts[_CONSOLE_ID] = self.unread_counts.get(_CONSOLE_ID, 0) + 1
            self._update_unread_display(_CONSOLE_ID)

    async def notify(self, text: str, character: str | None = None, **kwargs) -> None:
        target = character or self.active_character
        if target and target not in self.character_views:
            # Tab not ready yet — buffer for later
            self._pending_notifications.setdefault(target, []).append(text)
            return
        if target and target in self.character_views:
            view = self.character_views[target]["main"]
            view.write(f"[bold yellow]>> {text}[/bold yellow]")
        # Track unread + urgent for notifications on non-active tab
        if target and target != self.active_character and target in self.character_views:
            self.unread_counts[target] = self.unread_counts.get(target, 0) + 1
            if character is not None:
                self.urgent_unreads[target] = True
            self._update_unread_display(target)
        # Also write to console tab
        if _CONSOLE_ID in self.character_views and target != _CONSOLE_ID:
            self.character_views[_CONSOLE_ID]["main"].write(f"[bold yellow]>> {text}[/bold yellow]")
            if self.active_character != _CONSOLE_ID:
                self.unread_counts[_CONSOLE_ID] = self.unread_counts.get(_CONSOLE_ID, 0) + 1
                self._update_unread_display(_CONSOLE_ID)

    async def update_room(self) -> None:
        self._rebuild_sidebar()
        # Refresh nav panel if open
        if self.active_character and self.active_character in self.character_views:
            nav_panel = self.character_views[self.active_character].get("nav_panel")
            if nav_panel and nav_panel.display and self.controller:
                char_path = self._resolve_char_path(self.active_character)
                await nav_panel.refresh_data(self.controller.store, char_path)

    async def update_watch_list(self) -> None:
        self._rebuild_sidebar()

    def _resolve_char_path(self, ctrl_id: str) -> str:
        """Return the full model path for a ctrl_id (handles puppets)."""
        if self.controller:
            cc = self.controller.connection.get_controlled_char(ctrl_id)
            if cc:
                return cc.char_path
        return f"core.char.{ctrl_id}"

    async def ensure_character_tab(self, character: str) -> None:
        if character in self.character_views:
            return

        # Get character display name (character param is ctrl_id)
        name = "Unknown"
        if self.controller:
            store = self.controller.store
            cc = self.controller.connection.get_controlled_char(character)
            char_id = cc.char_id if cc else character
            name = store.get_character_attribute(char_id, "name")
            surname = store.get_character_attribute(char_id, "surname")
            if surname:
                name = f"{name} {surname}"
            if cc and cc.is_puppet:
                puppeteer_name = store.get_character_attribute(
                    cc.puppeteer_id, "name"
                )
                name = f"{name} ({puppeteer_name}'s puppet)"

        # Create per-character message views
        main_view = MessageView(
            id=f"main-{character}", classes="char-main-messages",
        )
        unimportant_view = MessageView(
            id=f"unimportant-{character}", classes="char-unimportant-messages",
        )
        collapsible = Collapsible(
            unimportant_view,
            title="Muted",
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
        self.urgent_unreads[character] = False
        self.character_order.append(character)

        # Add button to CharacterBar
        char_bar = self.query_one("#character-bar", CharacterBar)
        await char_bar.add_character(character, name or "Unknown")

        # If this is the first character, make it active
        if self.active_character is None:
            self._switch_to_character(character)

        # Flush any notifications that arrived before the tab existed
        for text in self._pending_notifications.pop(character, []):
            await self.notify(text, character=character)

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
        del self.urgent_unreads[character]
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

    async def display_look(self, data: dict, on_dismiss=None) -> "LookScreen":
        screen = LookScreen(data, on_url=self._publish_url)
        self.push_screen(screen, callback=lambda _: on_dismiss() if on_dismiss else None)
        return screen

    async def log_raw(self, text: str) -> None:
        # Debug logging -- no-op for now
        pass

    async def update_connection_status(self, status: str) -> None:
        indicator = self.query_one("#connection-indicator", ConnectionIndicator)
        if status == "connected":
            indicator.set_connected()
        elif status == "disconnected":
            indicator.set_disconnected()
        elif status == "reconnecting":
            indicator.set_reconnecting()

    async def blink_connection_indicator(self) -> None:
        try:
            indicator = self.query_one("#connection-indicator", ConnectionIndicator)
            indicator.blink()
        except Exception:
            pass

    async def apply_completions(self, results: list[str], prefix_len: int) -> None:
        try:
            input_bar = self.query_one("#input-bar", InputBar)
            input_bar.apply_completions(results, prefix_len)
        except Exception:
            pass
