"""URL catcher daemon — collects URLs found in formatted text."""

from __future__ import annotations

from datetime import datetime
from typing import NamedTuple

from .protocol.events import EventBus


class CaughtUrl(NamedTuple):
    timestamp: str  # HH:MM
    display_text: str
    url: str


class UrlCatcher:
    """Listens for ``url.found`` events and keeps a bounded history."""

    def __init__(self, event_bus: EventBus, max_urls: int = 50) -> None:
        self._max = max_urls
        self._urls: dict[str, CaughtUrl] = {}
        event_bus.subscribe(r"^url\.found$", self._on_url_found)

    def capture(self, display_text: str, url: str) -> None:
        ts = datetime.now().strftime("%H:%M")
        # Remove old entry so re-insert moves it to the end.
        self._urls.pop(url, None)
        self._urls[url] = CaughtUrl(ts, display_text, url)
        # Trim oldest entries if over capacity.
        while len(self._urls) > self._max:
            self._urls.pop(next(iter(self._urls)))

    async def _on_url_found(self, event_name: str, display_text: str, url: str, **kw) -> None:
        self.capture(display_text, url)

    def recent(self, n: int = 50) -> list[CaughtUrl]:
        """Return the last *n* URLs, most recent last."""
        items = list(self._urls.values())
        return items[-n:]
