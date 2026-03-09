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
    capture groups.  A trailing placeholder (and its preceding whitespace)
    is made optional so that e.g. ``examine <what>`` matches bare ``examine``.

    Examples::

        "pull lever"                    → ^pull\\ lever$
        "examine <what>"                → ^examine(?: (?P<what>.+?))?$
        "give <Character> = <Amount>"   → ^give (?P<Character>.+?) =(?: (?P<Amount>.+?))?$
    """
    parts = re.split(r"(<\w+>)", pattern)
    # Build (regex_fragment, is_group) pairs, escaping literals up front
    # but keeping original text for literals so we can split whitespace later.
    regex_parts: list[str] = []
    original_parts: list[str] = []  # parallel list of original text (for literals)
    for part in parts:
        if part.startswith("<") and part.endswith(">"):
            name = part[1:-1]
            regex_parts.append(f"(?P<{name}>.+?)")
            original_parts.append(part)
        elif part:
            regex_parts.append(re.escape(part))
            original_parts.append(part)

    # If the last element is a capture group, make it (and preceding
    # whitespace separator) optional so bare commands still match.
    if len(regex_parts) >= 2 and regex_parts[-1].startswith("(?P<"):
        group = regex_parts.pop()
        original_parts.pop()
        # Work with the ORIGINAL text of the preceding literal to split
        # trailing whitespace correctly, then re-escape each piece.
        regex_parts.pop()
        orig_sep = original_parts.pop()
        stripped = orig_sep.rstrip()
        trailing_ws = orig_sep[len(stripped):]
        if stripped:
            regex_parts.append(re.escape(stripped))
        regex_parts.append(f"(?:{re.escape(trailing_ws)}{group})?")

    return re.compile(f"^{''.join(regex_parts)}$", re.IGNORECASE)


def resolve_field_value(
    store: ModelStore, field_name: str, field_def: dict, raw_value: str | None
) -> dict | int | str:
    """Resolve a raw captured string into the typed value for the API.

    Raises ``NameParseException`` for unresolvable char names and
    ``ValueError`` for invalid integers.
    """
    field_type = field_def.get("type", "")
    raw = (raw_value or "").strip()

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
        return {"value": value}

    return {"value": raw}


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
