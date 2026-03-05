"""Abstract UI interface that any frontend must implement.

Uses Protocol (structural subtyping) instead of ABC to avoid metaclass
conflicts with Textual's App.
"""

from typing import Protocol, runtime_checkable


@runtime_checkable
class UIProtocol(Protocol):

    async def display_message(self, message: dict, style: str, character: str) -> None:
        """Display a game message (say, pose, whisper, ooc, etc.)."""
        ...

    async def display_system_text(self, text: str) -> None:
        """Display a system notification."""
        ...

    async def notify(self, text: str, character: str | None = None) -> None:
        """Show a transient notification, optionally routed to a specific character tab."""
        ...

    async def update_room(self) -> None:
        """Refresh the room display."""
        ...

    async def ensure_character_tab(self, character: str) -> None:
        """Ensure a tab/view exists for a character."""
        ...

    async def update_watch_list(self) -> None:
        """Refresh the watch list sidebar."""
        ...

    async def remove_character_tab(self, character: str) -> None:
        """Remove the tab/view for a released character."""
        ...

    def get_known_characters(self) -> set[str]:
        """Return set of character IDs that have active tabs."""
        ...

    async def display_look(self, data: dict) -> None:
        """Display the look modal (room or character)."""
        ...

    async def show_login(self, error: str | None = None) -> None:
        """Show the login screen, optionally with an error message."""
        ...

    async def log_raw(self, text: str) -> None:
        """Log raw protocol text (debug)."""
        ...
