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

    async def publish_interceptable(self, event_name: str, **kwargs: Any) -> bool:
        """Publish an event that can be intercepted.

        Subscribers are called in order. If any returns a truthy value,
        the event is considered handled and no further subscribers are called.
        Returns True if any subscriber handled the event.
        """
        for pattern, callback in self._subscribers:
            if re.match(pattern, event_name):
                result = await callback(event_name=event_name, **kwargs)
                if result:
                    return True
        return False
