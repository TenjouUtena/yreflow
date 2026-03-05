"""Data class representing a character under player control."""

from dataclasses import dataclass


@dataclass(frozen=True)
class ControlledChar:
    """Represents a character under player control.

    For regular characters: char_id == ctrl_id, puppeteer_id is None.
    For puppets: char_id is the puppet's ID, puppeteer_id is the controlling
    character's ID, and ctrl_id is "{char_id}_{puppeteer_id}".
    """

    char_id: str
    puppeteer_id: str | None = None

    @property
    def ctrl_id(self) -> str:
        """Unique key for tabs, views, and message routing."""
        if self.puppeteer_id:
            return f"{self.char_id}_{self.puppeteer_id}"
        return self.char_id

    @property
    def is_puppet(self) -> bool:
        return self.puppeteer_id is not None

    @property
    def char_path(self) -> str:
        """RID-style path for this character (for subscriptions/model lookups)."""
        if self.puppeteer_id:
            return f"core.char.{self.puppeteer_id}.puppet.{self.char_id}"
        return f"core.char.{self.char_id}"

    @property
    def ctrl_path(self) -> str:
        """RID-style path for ctrl API calls (e.g. call.{ctrl_path}.say)."""
        return f"{self.char_path}.ctrl"

    def __str__(self) -> str:
        return self.ctrl_id

    def __hash__(self) -> int:
        return hash(self.ctrl_id)

    def __eq__(self, other) -> bool:
        if isinstance(other, ControlledChar):
            return self.ctrl_id == other.ctrl_id
        if isinstance(other, str):
            return self.ctrl_id == other
        return NotImplemented
