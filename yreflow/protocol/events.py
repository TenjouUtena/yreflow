import re
from typing import Any, Callable, Awaitable


class EventBus:
    """Pub/sub event bus with pattern matching on event names."""

    def __init__(self):
        self._subscribers: list[tuple[str, Callable[..., Awaitable]]] = []

    def subscribe(self, pattern: str, callback: Callable[..., Awaitable]) -> None:
        self._subscribers.append((pattern, callback))

    async def publish(self, event_name: str, **kwargs: Any) -> None:
        for pattern, callback in self._subscribers:
            if re.match(pattern, event_name):
                await callback(event_name=event_name, **kwargs)
