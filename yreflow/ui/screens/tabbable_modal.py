"""Mixin that restores Tab/Shift+Tab focus cycling in modal screens.

The main app overrides Tab with priority=True for autocomplete.
This mixin re-binds Tab to focus_next/focus_previous so that modal
screens with multiple focusable widgets work as expected.
"""

from __future__ import annotations

from textual.binding import Binding


class TabbableModal:
    """Mixin for ModalScreen subclasses that need Tab focus cycling.

    Place this *before* ModalScreen in the MRO so its BINDINGS
    are merged first::

        class MyScreen(TabbableModal, ModalScreen):
            ...
    """

    BINDINGS = [
        Binding("tab", "app.focus_next", "Focus Next", show=False, priority=True),
        Binding(
            "shift+tab", "app.focus_previous", "Focus Previous",
            show=False, priority=True,
        ),
    ]
