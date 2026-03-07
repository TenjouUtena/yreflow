from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..protocol.model_store import ModelStore


class NameParseException(Exception):
    pass


def parse_name(
    store: ModelStore,
    name_to_parse: str,
    wants: str = "id",
    awake: bool = True,
    wants_list: bool = False,
) -> str | list[str]:
    """Fuzzy-match a character name from the model store.

    Extracted from Samples/CommandHandler.py:82-120.
    """
    chars = store.get("core.char")
    ntp = name_to_parse.casefold()
    retval = []

    for key, char in chars.items():
        if awake and "awake" not in char:
            continue
        if awake and "awake" in char and not char["awake"]:
            continue
        if "name" not in char:
            continue

        fullname = (
            store.get_character_attribute(key, "name")
            + " "
            + store.get_character_attribute(key, "surname")
        )

        if fullname.casefold() == ntp:
            return char["id"] if wants == "id" else fullname

        if fullname.casefold().startswith(ntp):
            payload = char["id"] if wants == "id" else fullname
            retval.append(payload)

    if not retval:
        raise NameParseException(f"No name found like {name_to_parse}")

    if (not wants_list) and len(retval) > 1:
        raise NameParseException(f"Too many players match {name_to_parse}")

    return retval if wants_list else retval[0]
