"""Room command pattern matching and execution.

Room commands are custom per-room commands stored at core.roomcmd.<cmdId>
in the model store. When user input doesn't match any built-in command,
we check room command patterns as a fallback.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from .name_resolver import parse_name

if TYPE_CHECKING:
    from ..protocol.model_store import ModelStore


def parse_room_cmd_pattern(pattern: str) -> re.Pattern:
    """Convert a room command pattern into a compiled regex.

    Literal text is escaped; ``<FieldName>`` placeholders become named
    capture groups.  Example::

        "give <Character> = <Amount>"
        → ^give (?P<Character>.+?) = (?P<Amount>.+?)$
    """
    parts = re.split(r"(<\w+>)", pattern)
    regex = ""
    for part in parts:
        if part.startswith("<") and part.endswith(">"):
            name = part[1:-1]
            regex += f"(?P<{name}>.+?)"
        else:
            regex += re.escape(part)
    return re.compile(f"^{regex}$", re.IGNORECASE)


def resolve_field_value(
    store: ModelStore, field_name: str, field_def: dict, raw_value: str
) -> dict | int | str:
    """Resolve a raw captured string into the typed value for the API.

    Raises ``NameParseException`` for unresolvable char names and
    ``ValueError`` for invalid integers.
    """
    field_type = field_def.get("type", "")
    raw = raw_value.strip()

    if field_type == "char":
        char_id = parse_name(store, raw)
        return {"charId": char_id}

    if field_type == "integer":
        value = int(raw)
        opts = field_def.get("opts", {})
        minimum = opts.get("min")
        if minimum is not None and value < minimum:
            raise ValueError(
                f"{field_name} must be at least {minimum} (got {value})"
            )
        return value

    return raw


def match_room_commands(
    store: ModelStore, char_path: str, user_input: str
) -> tuple[str, dict | None, dict] | None:
    """Try to match user input against the current room's commands.

    Returns ``(cmd_id, values, cmd_data)`` on match, or ``None``.
    """
    room_pointer = store.get_room_rid(char_path)
    if not room_pointer:
        return None

    cmd_refs = store.get_room_cmds(room_pointer)
    if not cmd_refs:
        return None

    # Gather command data and sort by priority (higher first)
    commands = []
    for ref in cmd_refs:
        try:
            cmd_model = store.get(ref["rid"])
        except KeyError:
            continue
        cmd_data = cmd_model.get("cmd", {}).get("data", {})
        pattern = cmd_data.get("pattern")
        if not pattern:
            continue
        commands.append((
            cmd_model.get("priority", 0),
            cmd_model.get("id", ref["rid"].rsplit(".", 1)[-1]),
            cmd_data,
        ))

    commands.sort(key=lambda c: c[0], reverse=True)

    for _priority, cmd_id, cmd_data in commands:
        regex = parse_room_cmd_pattern(cmd_data["pattern"])
        m = regex.match(user_input)
        if not m:
            continue

        fields = cmd_data.get("fields") or {}
        if not fields:
            return (cmd_id, None, cmd_data)

        values: dict = {}
        for field_name, field_def in fields.items():
            raw = m.group(field_name)
            values[field_name] = resolve_field_value(
                store, field_name, field_def, raw
            )
        return (cmd_id, values, cmd_data)

    return None
