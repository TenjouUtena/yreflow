"""URL catcher daemon — collects URLs found in formatted text."""

from __future__ import annotations

from collections import deque
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
        self._urls: deque[CaughtUrl] = deque(maxlen=max_urls)
        event_bus.subscribe(r"^url\.found$", self._on_url_found)

    def capture(self, display_text: str, url: str) -> None:
        ts = datetime.now().strftime("%H:%M")
        self._urls.append(CaughtUrl(ts, display_text, url))

    async def _on_url_found(self, event_name: str, display_text: str, url: str, **kw) -> None:
        self.capture(display_text, url)

    def recent(self, n: int = 20) -> list[CaughtUrl]:
        """Return the last *n* URLs, most recent last."""
        items = list(self._urls)
        return items[-n:]
