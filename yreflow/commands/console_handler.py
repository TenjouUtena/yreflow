"""Console command parsing and dispatch.

Handles commands typed in the console tab, separate from character commands.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .handler import CommandResult
from .name_resolver import NameParseException, parse_name
from ..protocol.realm import KNOWN_REALMS

if TYPE_CHECKING:
    from ..protocol.connection import WolferyConnection
    from ..protocol.model_store import ModelStore


class ConsoleHandler:
    def __init__(self, connection: WolferyConnection, store: ModelStore):
        self.conn = connection
        self.store = store

    async def process_command(self, command: str) -> CommandResult:
        command = command.strip()
        if not command:
            return CommandResult()

        parts = command.split(None, 1)
        cmd = parts[0].lower()
        args = parts[1] if len(parts) > 1 else ""

        handler = self._commands.get(cmd)
        if handler:
            return await handler(self, args)
        return CommandResult(success=False, notification=f"Unknown console command: {cmd}")

    async def _handle_help(self, args: str) -> CommandResult:
        lines = ["Console commands:"]
        for cmd in sorted(self._commands):
            lines.append(f"  {cmd}")
        return CommandResult(display_text="\n".join(lines))

    async def _handle_realm(self, args: str) -> CommandResult:
        args = args.strip().lower()
        current = self.conn.realm.key

        if not args:
            return CommandResult(display_text=f"Current realm: {current}")

        if args == "list":
            lines = ["Available realms:"]
            for key, name in sorted(KNOWN_REALMS.items()):
                marker = " (active)" if key == current else ""
                lines.append(f"  {key} — {name}{marker}")
            lines.append("\nYou can also use any realm key not listed here.")
            return CommandResult(display_text="\n".join(lines))

        from ..config import save_preference
        save_preference("realm", args)
        name = KNOWN_REALMS.get(args, args)
        return CommandResult(
            display_text=f"Realm set to '{name}'. Reconnect (Ctrl+R) for it to take effect."
        )

    async def _handle_lookup_name(self, args: str) -> CommandResult:
        try:
            fns = parse_name(self.store, args, "fullname", False, True)
            ids = parse_name(self.store, args, "id", False, True)
        except NameParseException:
            return CommandResult(display_text=f"No Names Matching '{args}' Found.", success=False)
        

        output = f"Names Matching {args}"

        for idx in range(len(fns)):
            fn = fns[idx]
            id = ids[idx]
            output += f"\n{fn} - {id}"
        return CommandResult(display_text=output)

    _commands: dict = {
        "help": _handle_help,
        "lookupname": _handle_lookup_name,
        "realm": _handle_realm,
    }
