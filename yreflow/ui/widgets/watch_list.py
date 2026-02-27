"""Sidebar widget with watch list and room characters."""

from __future__ import annotations

from typing import TYPE_CHECKING

from textual.widgets import Static, Rule
from textual.containers import VerticalScroll

if TYPE_CHECKING:
    from ...protocol.model_store import ModelStore


def _idle_style(idle) -> str:
    """Map idle level to Rich color style, matching the original GUI.

    Uses explicit hex colors to avoid ANSI downgrade issues where
    dark_orange renders as bright red on some terminals.
    """
    try:
        idle = int(idle)
    except (TypeError, ValueError):
        return "#808080"
    if idle == 1:
        return "bright_white"
    if idle == 2:
        return "#ffff00"
    if idle == 3:
        return "#ff8700"
    return "#808080"


def _format_compact(store: ModelStore, char_id: str) -> str:
    """Single-line: just the name, colored by idle."""
    name = store.get_character_attribute(char_id, "name")
    surname = store.get_character_attribute(char_id, "surname")
    idle = store.get_character_attribute(char_id, "idle")
    color = _idle_style(idle)
    display_name = f"{name} {surname}".strip()
    return f"[{color}]{display_name}[/{color}]"


def _format_expanded(store: ModelStore, char_id: str) -> str:
    """Multi-line: name, species/gender, status."""
    name = store.get_character_attribute(char_id, "name")
    surname = store.get_character_attribute(char_id, "surname")
    species = store.get_character_attribute(char_id, "species")
    gender = store.get_character_attribute(char_id, "gender")
    idle = store.get_character_attribute(char_id, "idle")
    status = store.get_character_attribute(char_id, "status")

    color = _idle_style(idle)
    display_name = f"{name} {surname}".strip()
    line = f"[{color}]{display_name}[/{color}]"

    details = []
    if gender:
        details.append(gender)
    if species:
        details.append(species)
    if details:
        line += f"\n  [dim]{' '.join(details)}[/dim]"

    if status:
        line += f"\n  [italic dim]({status})[/italic dim]"

    return line


class Sidebar(VerticalScroll):
    """Full-height sidebar with watch list on top and room characters below.

    Ctrl+W toggles between compact (name only) and expanded (name + details).
    """

    DEFAULT_CSS = """
    Sidebar {
        width: 28;
        border: solid $accent;
        padding: 0 1;
        dock: right;
    }
    Sidebar > .sidebar-title {
        text-style: bold;
        color: $text;
        background: $surface;
        width: 100%;
        padding: 0 1;
    }
    Sidebar > .sidebar-entry-expanded {
        margin-bottom: 1;
    }
    Sidebar > .sidebar-divider {
        margin: 1 0;
    }
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.compact = True

    def compose(self):
        yield Static("Watch List", classes="sidebar-title", id="watch-title")

    def toggle_compact(self) -> None:
        self.compact = not self.compact

    def _clear_entries(self) -> None:
        """Remove all dynamic entries, keep the initial Watch List title."""
        for child in list(self.children):
            if child.id == "watch-title":
                continue
            child.remove()

    def _mount_entry(self, markup: str) -> None:
        cls = "sidebar-entry-compact" if self.compact else "sidebar-entry-expanded"
        self.mount(Static(markup, classes=cls, markup=True))

    def rebuild(
        self,
        store: ModelStore,
        player: str | None,
        active_character: str | None,
    ) -> None:
        """Rebuild watch list and room characters from model state."""
        self._clear_entries()
        formatter = _format_compact if self.compact else _format_expanded

        # --- Watch list ---
        if player:
            try:
                watches = store.get(f"note.player.{player}.watches")
            except KeyError:
                watches = {}

            entries: list[tuple[str, int]] = []
            for key in watches:
                try:
                    char_note = store.get(watches[key]["rid"])
                    char_id = char_note["char"]["rid"].split(".")[2]
                    awake = store.get_character_attribute(char_id, "awake", False)
                    if not awake:
                        continue
                    last_awake = store.get_character_attribute(char_id, "lastAwake", 0)
                    entries.append((char_id, last_awake))
                except (KeyError, IndexError):
                    continue

            entries.sort(key=lambda x: x[1], reverse=True)

            for char_id, _ in entries:
                self._mount_entry(formatter(store, char_id))

        # --- Divider + Room characters ---
        if active_character:
            room_char_ids = self._get_room_characters(store, active_character)
            if room_char_ids:
                self.mount(Rule(classes="sidebar-divider"))
                self.mount(Static("In Room", classes="sidebar-title room-title"))
                for char_id in room_char_ids:
                    self._mount_entry(formatter(store, char_id))

    def _get_room_characters(self, store: ModelStore, character: str) -> list[str]:
        """Get character IDs of everyone in the active character's room."""
        try:
            room_pointer = store.get(f"core.char.{character}.owned.inRoom")["rid"]
        except (KeyError, AttributeError):
            return []
        try:
            room_chars = store.get(room_pointer + ".chars._value")
        except KeyError:
            return []

        char_ids = []
        for entry in room_chars:
            try:
                # rid looks like "core.char.{id}.inroom"
                char_id = entry["rid"].split(".")[2]
                char_ids.append(char_id)
            except (KeyError, IndexError):
                continue
        return char_ids
