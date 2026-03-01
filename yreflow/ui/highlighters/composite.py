"""Composite highlighter that chains multiple Rich Highlighters."""

from rich.highlighter import Highlighter
from rich.text import Text


class CompositeHighlighter(Highlighter):
    """Chains multiple Highlighter instances.

    Each enabled child's highlight() is called in sequence on the same
    Text object.  Rich Text.stylize() spans compose naturally.
    """

    def __init__(self) -> None:
        self._children: dict[str, Highlighter] = {}
        self._enabled: dict[str, bool] = {}

    def register(self, name: str, highlighter: Highlighter, *, enabled: bool = False) -> None:
        """Register a named child highlighter."""
        self._children[name] = highlighter
        self._enabled[name] = enabled

    def set_enabled(self, name: str, enabled: bool) -> None:
        """Toggle a child highlighter on or off."""
        self._enabled[name] = enabled

    def is_enabled(self, name: str) -> bool:
        return self._enabled.get(name, False)

    def highlight(self, text: Text) -> None:
        """Apply all enabled children's highlight() in sequence."""
        for name, child in self._children.items():
            if self._enabled.get(name, False):
                child.highlight(text)
