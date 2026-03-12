"""Schema-driven autocomplete plugin for Last Flame Inn.

Intercepts Tab, matches the current input against a pattern schema,
and sends a completion request via the ``muckproxy`` room command.
Results come back as a describe message containing a JSON array of strings.
"""

import json
import logging
import re

from yreflow.plugins import Plugin

log = logging.getLogger(__name__)

_SCHEMA_ = """
{
  "version": 1,
  "providers": {
    "awareness_target": {"kind": "resolver", "entity": "target"},
    "read_target": {"kind": "resolver", "entity": "target"},
    "inventory_item": {"kind": "resolver", "entity": "item"},
    "room_item": {"kind": "resolver", "entity": "item"},
    "contained_item": {"kind": "resolver", "entity": "item"},
    "container_any": {"kind": "resolver", "entity": "item"},
    "any_item": {"kind": "resolver", "entity": "item"},
    "room_character": {"kind": "resolver", "entity": "character"},
    "seat_item": {"kind": "resolver", "entity": "item"}
  },
  "patterns": [
    "glance",
    "examine",
    "examine {target:awareness_target}",
    "smell",
    "smell {target:awareness_target}",
    "listen",
    "listen {target:awareness_target}",
    "touch {target:awareness_target}",
    "taste {target:awareness_target}",
    "read {target:read_target}",
    "inv",
    "drop {item:inventory_item}",
    "take {item:room_item}",
    "take {item:contained_item} from {container:container_any}",
    "give {item:inventory_item} : {who:room_character}",
    "put {item:any_item} in {container:container_any}",
    "use {item:any_item}",
    "use {item:any_item} on {target:any_item}",
    "eat {item:any_item}",
    "drink {item:any_item}",
    "sit",
    "sit {seat:seat_item}",
    "stand",
    "char profile"
  ]
}
"""

# Regex to find {name:provider} slots in a pattern string.
_SLOT_RE = re.compile(r"\{(\w+):(\w+)\}")

# Regex to find a JSON array of strings in the describe response.
_JSON_ARRAY_RE = re.compile(r'\[(?:\s*"[^"]*"\s*,?\s*)*\]')

# Room command pattern prefixes we search for to find the muckproxy cmd ID.
_MUCKPROXY_NAMES = ("muckproxy meta complete", )


def _parse_pattern(pattern: str) -> list[dict]:
    """Parse a pattern string into a list of tokens.

    Each token is either:
      {"type": "literal", "text": "take"}
      {"type": "slot", "name": "item", "provider": "room_item"}
    """
    tokens: list[dict] = []
    pos = 0
    for m in _SLOT_RE.finditer(pattern):
        before = pattern[pos:m.start()].strip()
        if before:
            for word in before.split():
                tokens.append({"type": "literal", "text": word})
        tokens.append({"type": "slot", "name": m.group(1), "provider": m.group(2)})
        pos = m.end()
    after = pattern[pos:].strip()
    if after:
        for word in after.split():
            tokens.append({"type": "literal", "text": word})
    return tokens


def match_input(parsed_patterns: list[list[dict]], user_input: str) -> dict | None:
    """Try to match user_input against parsed patterns.

    Returns the best match dict with keys:
      provider: str  — the provider for the slot needing completion
      prefix: str    — what the user has typed so far for that slot
      captures: dict — already-resolved slot values
      name: str      — the slot name being completed

    Returns None if no pattern matches at a completable position.
    """
    user_input = user_input.strip()
    if not user_input:
        return None

    best: dict | None = None
    best_score = -1

    for tokens in parsed_patterns:
        result = _try_match(tokens, user_input)
        if result is not None:
            score = len(result.get("captures", {})) + len(tokens)
            if score > best_score:
                best = result
                best_score = score

    return best


def _try_match(tokens: list[dict], user_input: str) -> dict | None:
    """Try to match a single parsed pattern against user input.

    Walks tokens and input simultaneously. Literal tokens must match exactly.
    Slot tokens consume words up to the next literal delimiter (or end of input).
    If the input ends mid-slot, that's our completion point.
    """
    words = user_input.split()
    wi = 0
    captures: dict[str, str] = {}

    for ti, token in enumerate(tokens):
        if token["type"] == "literal":
            if wi >= len(words):
                return None
            if words[wi].lower() != token["text"].lower():
                return None
            wi += 1

        elif token["type"] == "slot":
            next_literal = None
            for ahead in tokens[ti + 1:]:
                if ahead["type"] == "literal":
                    next_literal = ahead["text"]
                    break

            if next_literal is None:
                remaining = words[wi:]
                prefix = " ".join(remaining) if remaining else ""
                return {
                    "provider": token["provider"],
                    "prefix": prefix,
                    "captures": captures,
                    "name": token["name"],
                }
            else:
                delim_idx = None
                for i in range(wi, len(words)):
                    if words[i].lower() == next_literal.lower():
                        delim_idx = i
                        break

                if delim_idx is None:
                    remaining = words[wi:]
                    prefix = " ".join(remaining) if remaining else ""
                    return {
                        "provider": token["provider"],
                        "prefix": prefix,
                        "captures": captures,
                        "name": token["name"],
                    }
                else:
                    slot_words = words[wi:delim_idx]
                    if not slot_words:
                        return None
                    captures[token["name"]] = " ".join(slot_words)
                    wi = delim_idx

    if wi < len(words):
        return None

    return None  # Fully matched, nothing to complete.


def _find_muckproxy_cmd_id(store, char_path: str) -> str | None:
    """Search room commands for the muckproxy completion command."""
    room_rid = store.get_room_rid(char_path)
    if not room_rid:
        return None

    cmd_refs = store.get_room_cmds(room_rid)
    if not cmd_refs:
        return None

    for ref in cmd_refs:
        try:
            cmd_model = store.get(ref["rid"])
        except KeyError:
            continue
        cmd_data = cmd_model.get("cmd", {}).get("data", {})
        pattern = (cmd_data.get("pattern") or "").lower()
        for name in _MUCKPROXY_NAMES:
            if pattern.startswith(name):
                log.info(f"Found COmmand: {name} {pattern} {cmd_data}")
                return cmd_model.get("id", ref["rid"].rsplit(".", 1)[-1])

    return None


class SchemaParser(Plugin):
    name = "Schema Parser - LFI"
    realm = "lastflameinn"

    def __init__(self) -> None:
        super().__init__()
        self.schema: dict = {}
        self._parsed_patterns: list[list[dict]] = []
        self._pending_complete: bool = False
        self._pending_prefix_len: int = 0

    async def on_connect(self, **kw):
        self.schema = json.loads(_SCHEMA_)
        self._parsed_patterns = [
            _parse_pattern(p) for p in self.schema.get("patterns", [])
        ]
        await self.event_bus.publish(
            "system.text",
            text=f"[Schema] Loaded {len(self._parsed_patterns)} patterns for autocomplete.",
        )

    async def on_autocomplete_try(self, input: str = "", cursor: int = 0, ctrl_id: str = "", **kw) -> bool:
        if not input or not self._parsed_patterns:
            return False

        text = input[:cursor] if cursor > 0 else input

        result = match_input(self._parsed_patterns, text)
        if result is None:
            return False

        provider = result["provider"]
        prefix = result["prefix"]
        captures = result["captures"]

        if not prefix:
            return False

        cc = self.connection.get_controlled_char(ctrl_id)
        if cc is None:
            return False

        # Find the muckproxy room command ID.
        cmd_id = _find_muckproxy_cmd_id(self.store, cc.char_path)
        if cmd_id is None:
            log.debug("No muckproxy room command found in current room")
            return False

        # Build the completion payload as single-line JSON (no encoding).
        payload_json = json.dumps({
            "version": 1,
            "provider": provider,
            "prefix": prefix,
            "captures": captures,
        }, separators=(",", ":"))

        self._pending_complete = True
        self._pending_prefix_len = len(prefix)

        log.debug("Sending muckproxy complete: cmdId=%s payload=%s", cmd_id, payload_json)
        await self.connection.send(
            f"call.{cc.ctrl_path}.execRoomCmd",
            {"cmdId": cmd_id, "values": {"value": {"value": payload_json}}},
        )
        return True

    async def on_message(self, message: dict, style: str, character: str, **kw):
        """Intercept completion response messages.

        Returns True to suppress display when the message is a completion
        result (message.received uses publish_interceptable).
        """
        if not self._pending_complete:
            return False
        if style not in ("describe", "info"):
            return False

        msg_text = message.get("msg", "")

        # Look for a JSON array of strings in the response.
        m = _JSON_ARRAY_RE.search(msg_text)
        if m is None:
            return False

        self._pending_complete = False
        try:
            results = json.loads(m.group())
        except json.JSONDecodeError:
            log.warning("Failed to parse completion response: %s", m.group())
            return True  # Still suppress the garbled response

        if not isinstance(results, list) or not results:
            return True  # Suppress empty results too

        log.debug("Got %d completion results", len(results))
        await self.event_bus.publish(
            "autocomplete.results",
            results=results,
            prefix_len=self._pending_prefix_len,
        )
        return True  # Suppress — don't display the raw JSON in chat


# PluginManager looks for this attribute.
plugin = SchemaParser
