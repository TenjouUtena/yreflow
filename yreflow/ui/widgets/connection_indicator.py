"""Connection status indicator LED widget."""

from textual.timer import Timer
from textual.widgets import Static

_DOT = "\u25cf"

_STYLES = {
    "disconnected": f"[red]{_DOT}[/]",
    "reconnecting": f"[yellow]{_DOT}[/]",
    "connected": f"[green]{_DOT}[/]",
    "active": f"[bold bright_green]{_DOT}[/]",
}


class ConnectionIndicator(Static):
    """Single-character LED that shows connection state."""

    DEFAULT_CSS = """
    ConnectionIndicator {
        dock: right;
        width: 3;
        height: 1;
        content-align: right middle;
    }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(_STYLES["disconnected"], **kwargs)
        self._status = "disconnected"
        self._blink_timer: Timer | None = None

    def set_connected(self) -> None:
        self._status = "connected"
        self._cancel_blink()
        self.update(_STYLES["connected"])

    def set_disconnected(self) -> None:
        self._status = "disconnected"
        self._cancel_blink()
        self.update(_STYLES["disconnected"])

    def set_reconnecting(self) -> None:
        self._status = "reconnecting"
        self._cancel_blink()
        self.update(_STYLES["reconnecting"])

    def blink(self) -> None:
        """Flash bright green briefly, then revert to dim green."""
        if self._status != "connected":
            return
        self._cancel_blink()
        self.update(_STYLES["active"])
        self._blink_timer = self.set_timer(0.2, self._unblink)

    def _unblink(self) -> None:
        self._blink_timer = None
        if self._status == "connected":
            self.update(_STYLES["connected"])

    def _cancel_blink(self) -> None:
        if self._blink_timer is not None:
            self._blink_timer.stop()
            self._blink_timer = None
