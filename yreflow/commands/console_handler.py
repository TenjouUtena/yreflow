"""Console command parsing and dispatch.

Handles commands typed in the console tab, separate from character commands.
Player-level commands (mail, whois, laston, etc.) are delegated to
CommandHandler so the same logic is shared with character tabs.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .handler import CommandResult
from .name_resolver import NameParseException, parse_name
from ..protocol.realm import KNOWN_REALMS

if TYPE_CHECKING:
    from .handler import CommandHandler
    from ..protocol.connection import WolferyConnection
    from ..protocol.model_store import ModelStore

# Command types (from CommandHandler.detect_command_type) that are player-level
# and should be available in the console without an active character.
PLAYER_COMMANDS: set[str] = {
    "mail",
    "laston",
    "whois",
    "lookup",
    "watch",
    "unwatch",
    "settings",
}


class ConsoleHandler:
    def __init__(
        self,
        connection: WolferyConnection,
        store: ModelStore,
        command_handler: CommandHandler | None = None,
    ):
        self.conn = connection
        self.store = store
        self.command_handler = command_handler

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

        # Try player-level commands via the main CommandHandler.
        if self.command_handler:
            cmd_type, content, func = self.command_handler.detect_command_type(command)
            if cmd_type in PLAYER_COMMANDS and func is not None:
                return await func(content, None)

        return CommandResult(success=False, notification=f"Unknown console command: {cmd}")

    async def _handle_help(self, args: str) -> CommandResult:
        lines = ["Console commands:"]
        for cmd in sorted(self._commands):
            lines.append(f"  {cmd}")
        lines.append("")
        lines.append("Player commands (also available here):")
        for cmd in sorted(PLAYER_COMMANDS):
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

    async def _handle_create(self, args: str) -> CommandResult:
        parts = args.strip().split(None, 1)
        if not parts:
            return CommandResult(success=False, notification="Usage: create character FirstName LastName")
        subcmd = parts[0].lower()
        rest = parts[1] if len(parts) > 1 else ""

        if subcmd == "character":
            return await self._create_character(rest)

        return CommandResult(success=False, notification=f"Unknown create subcommand: {subcmd}")

    async def _create_character(self, args: str) -> CommandResult:
        names = args.strip().split()
        if len(names) < 2:
            return CommandResult(success=False, notification="Usage: create character FirstName LastName")

        name, surname = names[0], " ".join(names[1:])

        if not self.conn.player:
            return CommandResult(success=False, notification="Not logged in.")

        await self.conn.send(
            f"call.core.player.{self.conn.player}.createChar",
            {"name": name, "surname": surname},
        )
        return CommandResult(display_text=f"Creating character: {name} {surname}")

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
        "create": _handle_create,
        "help": _handle_help,
        "lookupname": _handle_lookup_name,
        "realm": _handle_realm,
    }
