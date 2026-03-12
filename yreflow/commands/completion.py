"""Context-aware tab completion: command detection + prioritized name resolution."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..protocol.model_store import ModelStore


class CompletionType(Enum):
    LOCAL_ONLY = auto()            # room chars only
    LOCAL_PREFERRED = auto()       # room → watch → online
    AWAKE_WATCH_PREFERRED = auto() # awake only, watch → online
    WATCH_PREFERRED = auto()       # watch → online
    NONE = auto()                  # no name completion


@dataclass
class CompletionContext:
    completion_type: CompletionType
    prefix: str       # text fragment to match against
    prose: bool       # True = firstname-first cycling; False = fullname cycling


# (prefixes, name_slot_type, after_=_type, name_slot_prose, after_=_prose)
# Longer prefixes checked first within each group to avoid shadowing.
_DIRECTED_RULES: list[tuple[tuple[str, ...], CompletionType, CompletionType]] = [
    (("wh ",),                CompletionType.LOCAL_ONLY,            CompletionType.LOCAL_PREFERRED),
    (("w ",),                 CompletionType.LOCAL_ONLY,            CompletionType.LOCAL_PREFERRED),
    (("address ",),           CompletionType.LOCAL_ONLY,            CompletionType.LOCAL_PREFERRED),
    (("to ",),                CompletionType.LOCAL_ONLY,            CompletionType.LOCAL_PREFERRED),
    (("@",),                  CompletionType.LOCAL_ONLY,            CompletionType.LOCAL_PREFERRED),
    (("p ",),                 CompletionType.AWAKE_WATCH_PREFERRED, CompletionType.WATCH_PREFERRED),
    (("m ",),                 CompletionType.AWAKE_WATCH_PREFERRED, CompletionType.WATCH_PREFERRED),
    (("mail send ",),         CompletionType.WATCH_PREFERRED,       CompletionType.WATCH_PREFERRED),
    (("mail s ",),            CompletionType.WATCH_PREFERRED,       CompletionType.WATCH_PREFERRED),
]

_UNDIRECTED_PROSE_RULES: list[tuple[tuple[str, ...], CompletionType]] = [
    (("say ",),               CompletionType.LOCAL_PREFERRED),
    (("\u201c",),             CompletionType.LOCAL_PREFERRED),
    (("\u201d",),             CompletionType.LOCAL_PREFERRED),
    (('"',),                  CompletionType.LOCAL_PREFERRED),
    (("pose ",),              CompletionType.LOCAL_PREFERRED),
    ((":",),                  CompletionType.LOCAL_PREFERRED),
    (("ooc ",),               CompletionType.LOCAL_PREFERRED),
    ((">",),                  CompletionType.LOCAL_PREFERRED),
]

_UNDIRECTED_NAME_RULES: list[tuple[tuple[str, ...], CompletionType]] = [
    (("look ",),              CompletionType.LOCAL_ONLY),
    (("l ",),                 CompletionType.LOCAL_ONLY),
    (("whois ", "wi "),       CompletionType.WATCH_PREFERRED),
    (("watch ",),             CompletionType.WATCH_PREFERRED),
    (("unwatch ",),           CompletionType.WATCH_PREFERRED),
    (("summon ",),            CompletionType.WATCH_PREFERRED),
    (("join ",),              CompletionType.WATCH_PREFERRED),
    (("lead ",),              CompletionType.LOCAL_ONLY),
    (("follow ",),            CompletionType.LOCAL_ONLY),
    (("focus ",),             CompletionType.LOCAL_ONLY),
    (("unfocus ",),           CompletionType.LOCAL_ONLY),
]


def detect_completion_context(text: str) -> CompletionContext:
    """Determine completion type and prefix from partially-typed input."""
    # --- Directed commands (have Name=message structure) ---
    for prefixes, name_type, msg_type in _DIRECTED_RULES:
        for pfx in prefixes:
            if text.lower().startswith(pfx):
                argument = text[len(pfx):]
                if "=" in argument:
                    # Cursor is in message slot (after =)
                    after_eq = argument.split("=", 1)[1]
                    word = after_eq.rsplit(" ", 1)[-1] if after_eq else ""
                    return CompletionContext(msg_type, word, prose=True)
                else:
                    # Cursor is in name slot (before =)
                    name_part = argument.lstrip("@")
                    return CompletionContext(name_type, name_part, prose=False)

    # --- Undirected prose commands (say, pose, ooc, etc.) ---
    for prefixes, ctype in _UNDIRECTED_PROSE_RULES:
        for pfx in prefixes:
            if text.lower().startswith(pfx) or text.startswith(pfx):
                argument = text[len(pfx):]
                word = argument.rsplit(" ", 1)[-1] if argument else ""
                return CompletionContext(ctype, word, prose=True)

    # --- Undirected name-target commands (look, whois, etc.) ---
    for prefixes, ctype in _UNDIRECTED_NAME_RULES:
        for pfx in prefixes:
            if text.lower().startswith(pfx):
                argument = text[len(pfx):]
                return CompletionContext(ctype, argument, prose=False)

    # --- Bare text: treat as say (local_preferred prose) ---
    word = text.rsplit(" ", 1)[-1] if text else ""
    return CompletionContext(CompletionType.LOCAL_PREFERRED, word, prose=True)


# ---------------------------------------------------------------------------
# Tier builders
# ---------------------------------------------------------------------------

def _get_room_char_ids(store: ModelStore, char_path: str | None) -> list[str]:
    """Get character IDs of everyone in the active character's room."""
    if not char_path:
        return []
    room_pointer = store.get_room_rid(char_path)
    if not room_pointer:
        return []
    result = []
    for entry in store.get_room_chars(room_pointer):
        try:
            result.append(entry["rid"].split(".")[2])
        except (KeyError, IndexError):
            continue
    return result


def _get_watch_char_ids(store: ModelStore, player: str | None) -> list[str]:
    """Get character IDs from the player's watch list."""
    if not player:
        return []
    try:
        watches = store.get(f"note.player.{player}.watches")
    except KeyError:
        return []
    result = []
    for key in watches:
        try:
            char_note = store.get(watches[key]["rid"])
            char_id = char_note["char"]["rid"].split(".")[2]
            result.append(char_id)
        except (KeyError, IndexError):
            continue
    return result


def _get_online_char_ids(store: ModelStore) -> list[str]:
    """Get all awake character IDs from the store."""
    try:
        chars = store.get("core.char")
    except KeyError:
        return []
    result = []
    for key, char in chars.items():
        if char.get("awake") and "name" in char:
            result.append(key)
    return result


def _build_fullname(store: ModelStore, char_id: str) -> str:
    name = store.get_character_attribute(char_id, "name")
    surname = store.get_character_attribute(char_id, "surname")
    return f"{name} {surname}".strip()


def _matches_prefix(fullname: str, prefix: str) -> bool:
    if not prefix:
        return True
    return fullname.casefold().startswith(prefix.casefold())


# ---------------------------------------------------------------------------
# Main resolver
# ---------------------------------------------------------------------------

def resolve_names(
    store: ModelStore,
    prefix: str,
    completion_type: CompletionType,
    char_path: str | None,
    player: str | None,
    prose: bool,
) -> list[str]:
    """Build a prioritized, deduplicated name list for tab completion.

    Returns fullnames (or interleaved firstname/fullname for prose mode).
    """
    if completion_type == CompletionType.NONE:
        return []

    # Build tier lists of char_ids based on completion type
    tiers: list[list[str]] = []
    awake_filter = False

    if completion_type == CompletionType.LOCAL_ONLY:
        tiers = [_get_room_char_ids(store, char_path)]
    elif completion_type == CompletionType.LOCAL_PREFERRED:
        tiers = [
            _get_room_char_ids(store, char_path),
            _get_watch_char_ids(store, player),
            _get_online_char_ids(store),
        ]
    elif completion_type == CompletionType.AWAKE_WATCH_PREFERRED:
        awake_filter = True
        tiers = [
            _get_watch_char_ids(store, player),
            _get_online_char_ids(store),
        ]
    elif completion_type == CompletionType.WATCH_PREFERRED:
        tiers = [
            _get_watch_char_ids(store, player),
            _get_online_char_ids(store),
        ]

    # Collect matches with deduplication across tiers
    seen: set[str] = set()
    results: list[str] = []

    for tier in tiers:
        for char_id in tier:
            if char_id in seen:
                continue
            if awake_filter and not store.get_character_attribute(char_id, "awake", False):
                continue
            fullname = _build_fullname(store, char_id)
            if not _matches_prefix(fullname, prefix):
                continue
            seen.add(char_id)

            if prose:
                # Offer firstname first, then fullname (skip dup if no surname)
                firstname = store.get_character_attribute(char_id, "name")
                results.append(firstname)
                if fullname != firstname:
                    results.append(fullname)
            else:
                results.append(fullname)

    return results
