"""Navigation panel widget with compass rose and room info."""

from __future__ import annotations

from textual.binding import Binding
from textual.containers import Grid, Horizontal, Vertical, VerticalScroll
from textual.events import Key
from textual.message import Message
from textual.widget import Widget
from textual.widgets import Static, TabbedContent, TabPane

from ...formatter import format_message

# Maps Textual key names to standard MUD compass nav values.
_KEY_TO_NAV = {
    "up": "n",
    "down": "s",
    "left": "w",
    "right": "e",
    "home": "nw",
    "end": "sw",
    "pageup": "ne",
    "pagedown": "se",
}

# Ordered compass cells for the 3x3 grid + up/down row.
_COMPASS_CELLS = ["nw", "n", "ne", "w", "", "e", "sw", "s", "se"]
# Display labels for compass directions.
_DIR_LABELS = {
    "n": "N", "s": "S", "e": "E", "w": "W",
    "ne": "NE", "nw": "NW", "se": "SE", "sw": "SW",
}

_DIR_ICONS = {
    "n": "↑", "s": "↓", "e": "→", "w": "←",
    "ne": "↗", "nw": "↖", "se": "↘", "sw": "↙",
}


class _NavCell(Static):
    """A clickable compass cell."""

    class Clicked(Message):
        def __init__(self, nav_dir: str) -> None:
            super().__init__()
            self.nav_dir = nav_dir

    def __init__(self, nav_dir: str, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.nav_dir = nav_dir

    def on_click(self) -> None:
        if self.nav_dir:
            self.post_message(self.Clicked(self.nav_dir))


class NavRose(Widget):
    """Compass rose showing available exits as a directional grid."""

    DEFAULT_CSS = """
    NavRose {
        width: auto;
        height: auto;
        padding: 0 1;
    }
    .nav-grid {
        grid-size: 3 3;
        grid-gutter: 0;
        width: 21;
        height: 9;
    }
    .nav-cell {
        width: 7;
        height: 3;
        content-align: center middle;
        text-align: center;
    }
    .nav-cell-active {
        background: $surface-lighten-1;
    }
    .nav-cell-empty {
        color: $text-disabled;
    }
    .nav-cell-center {
        color: $accent;
    }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._exits_by_nav: dict[str, dict] = {}

    def compose(self):
        with Grid(classes="nav-grid"):
            for nav_dir in _COMPASS_CELLS:
                if nav_dir == "":
                    yield _NavCell("", "*", classes="nav-cell nav-cell-center", id="nav-center", markup=True)
                else:
                    icon = _DIR_ICONS.get(nav_dir, "")
                    label = _DIR_LABELS.get(nav_dir, nav_dir)
                    yield _NavCell(
                        nav_dir,
                        f"[dim]{icon}\n{label}[/dim]",
                        classes="nav-cell nav-cell-empty",
                        id=f"nav-{nav_dir}",
                        markup=True,
                    )
    def update_exits(self, exits: list[dict]) -> None:
        """Update the rose with current exit data.

        Each exit dict should have: id, name, keys, icon, nav.
        """
        self._exits_by_nav.clear()

        # Reset all cells to empty
        all_dirs = [d for d in _COMPASS_CELLS if d]
        for nav_dir in all_dirs:
            try:
                cell = self.query_one(f"#nav-{nav_dir}", _NavCell)
                label = _DIR_LABELS.get(nav_dir, nav_dir)
                cell.update(f"[dim]\n{label}[/dim]")
                cell.remove_class("nav-cell-active")
                cell.add_class("nav-cell-empty")
            except Exception:
                pass

        # Populate active exits
        for ex in exits:
            nav = ex.get("nav", "")
            if not nav:
                continue
            nav_lower = nav.lower()
            self._exits_by_nav[nav_lower] = ex
            try:
                cell = self.query_one(f"#nav-{nav_lower}", _NavCell)
                icon_text = ex.get("icon", "")
                icon = _DIR_ICONS.get(icon_text, icon_text)
                label = _DIR_LABELS.get(nav_lower, nav_lower)
                cell.update(f"[bold]{icon}\n{label}[/bold]")
                cell.remove_class("nav-cell-empty")
                cell.add_class("nav-cell-active")
            except Exception:
                pass

    def on__nav_cell_clicked(self, event: _NavCell.Clicked) -> None:
        """Bubble up as an ExitSelected if a valid exit exists for this direction."""
        ex = self._exits_by_nav.get(event.nav_dir)
        if ex:
            # Stop here and let NavPanel post the ExitSelected message
            self.post_message(NavPanel.ExitSelected(ex["id"]))
            event.stop()

    def get_exit_for_nav(self, nav_dir: str) -> dict | None:
        """Return the exit matching a nav direction, or None."""
        return self._exits_by_nav.get(nav_dir.lower())


class NavPanel(Widget):
    """Navigation panel overlaying the bottom of the output pane."""

    DEFAULT_CSS = """
    NavPanel {
        dock: bottom;
        height: 50%;
        background: $panel;
        border-top: solid $accent;
    }
    .nav-panel-inner {
        height: 1fr;
    }
    .nav-left {
        width: 3fr;
        height: 1fr;
        border-right: solid $surface-lighten-1;
        padding: 0 1;
    }
    .nav-right {
        width: 2fr;
        height: 1fr;
        padding: 0 1;
    }
    .nav-room-title {
        text-style: bold;
        text-align: center;
        width: 100%;
        margin-bottom: 1;
    }
    .nav-section-title {
        text-style: bold;
        color: $accent;
        margin-top: 1;
    }
    .nav-exit-item {
        padding: 0 1;
    }
    """

    BINDINGS = [
        Binding("escape", "close_panel", "Close", priority=True),
    ]

    class ExitSelected(Message):
        """Posted when the user selects an exit via key or click."""

        def __init__(self, exit_id: str) -> None:
            super().__init__()
            self.exit_id = exit_id

    class CloseRequested(Message):
        """Posted when the user presses ESC to close the panel."""

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._exits: list[dict] = []

    def compose(self):
        with Horizontal(classes="nav-panel-inner"):
            yield VerticalScroll(classes="nav-left", id="nav-left-scroll")
            with Vertical(classes="nav-right"):
                yield NavRose(id="nav-rose")
                yield Static("Exits", classes="nav-section-title", markup=True)
                yield VerticalScroll(id="nav-exit-list")

    def action_close_panel(self) -> None:
        self.post_message(self.CloseRequested())

    async def on_key(self, event: Key) -> None:
        nav_dir = _KEY_TO_NAV.get(event.key)
        if nav_dir:
            rose = self.query_one("#nav-rose", NavRose)
            ex = rose.get_exit_for_nav(nav_dir)
            if ex:
                self.post_message(self.ExitSelected(ex["id"]))
            event.prevent_default()
            event.stop()

    async def refresh_data(self, store, char_id: str) -> None:
        """Pull room/exit/area data from the store and update the panel."""
        try:
            room_pointer = store.get(
                f"core.char.{char_id}.owned.inRoom"
            )["rid"]
            room_id = room_pointer.split(".")[2]
        except KeyError:
            return

        room_name = store.get_room_attribute(room_id, "name") or "Unknown Room"
        room_desc = store.get_room_attribute(room_id, "desc") or ""

        # Gather exits with icon and nav fields
        exits = []
        try:
            room_exits = store.get(room_pointer + ".exits._value")
            for e in room_exits:
                try:
                    exit_model = store.get(e["rid"])
                    keys = exit_model.get("keys", {}).get("data", [])
                    exits.append({
                        "id": exit_model.get("id", ""),
                        "name": exit_model.get("name", "?"),
                        "keys": keys,
                        "icon": exit_model.get("icon", ""),
                        "nav": exit_model.get("nav", ""),
                    })
                except KeyError:
                    continue
        except KeyError:
            pass
        self._exits = exits

        # Gather area hierarchy
        areas = []
        try:
            room_model = store.get(f"core.room.{room_id}")
            area_ref = room_model.get("area", {})
            if isinstance(area_ref, dict) and "rid" in area_ref:
                area_path = area_ref["rid"]
                while area_path:
                    try:
                        area = store.get(area_path)
                        details = area.get("details", area)
                        area_name = details.get("name", "")
                        area_about = details.get("about", "")
                        area_pop = details.get("pop", 0)
                        if area_name:
                            areas.append({
                                "name": area_name,
                                "about": area_about,
                                "pop": area_pop,
                            })
                        parent = area.get("parent") or details.get("parent")
                        if isinstance(parent, dict) and "rid" in parent:
                            area_path = parent["rid"]
                        else:
                            area_path = None
                    except KeyError:
                        break
        except KeyError:
            pass

        # Update left panel: room info + area tabs
        left = self.query_one("#nav-left-scroll", VerticalScroll)
        await left.remove_children()

        if areas:
            tabbed = TabbedContent()
            await left.mount(tabbed)
            room_pane = TabPane("Room", id="nav-tab-room")
            await tabbed.add_pane(room_pane)
            await room_pane.mount(
                Static(f"[bold]{room_name}[/bold]", classes="nav-room-title", markup=True)
            )
            if room_desc:
                await room_pane.mount(
                    Static(format_message(room_desc), markup=True)
                )
            for i, area in enumerate(areas):
                area_pane = TabPane(area["name"], id=f"nav-tab-area-{i}")
                await tabbed.add_pane(area_pane)
                if area.get("pop", 0) > 0:
                    await area_pane.mount(
                        Static(f"Population: {area['pop']}", markup=True)
                    )
                about = area.get("about", "")
                if about:
                    await area_pane.mount(
                        Static(format_message(about), markup=True)
                    )
                if not area.get("pop") and not about:
                    await area_pane.mount(
                        Static("[dim]No details available.[/dim]", markup=True)
                    )
        else:
            await left.mount(
                Static(f"[bold]{room_name}[/bold]", classes="nav-room-title", markup=True)
            )
            if room_desc:
                await left.mount(
                    Static(format_message(room_desc), markup=True)
                )

        # Update compass rose
        rose = self.query_one("#nav-rose", NavRose)
        rose.update_exits(exits)

        # Update exit list
        exit_list = self.query_one("#nav-exit-list", VerticalScroll)
        await exit_list.remove_children()
        for ex in exits:
            keys_str = ", ".join(ex["keys"]) if ex["keys"] else ""
            keys_display = f" ({keys_str})" if keys_str else ""
            await exit_list.mount(
                Static(
                    f"  [bold]{ex['name']}[/bold]{keys_display}",
                    classes="nav-exit-item",
                    markup=True,
                )
            )

    def find_exit_by_key(self, text: str) -> dict | None:
        """Match typed text against exit keys. Returns exit dict or None."""
        text_lower = text.casefold()
        for ex in self._exits:
            for k in ex.get("keys", []):
                if k.casefold() == text_lower:
                    return ex
        return None
