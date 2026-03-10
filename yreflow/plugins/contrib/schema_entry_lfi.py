"""Schema-driven autocomplete plugin for Last Flame Inn.

Intercepts Tab, matches the current input against a pattern schema,
and sends a ``__complete`` room command to Wolfery when the cursor is
at a completable slot.  Results come back as a describe message whose
body is JSON containing the matches.
"""

import base64
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

# Example payload for __complete
# {
#   "provider": "container_any",
#   "prefix": "wo",
#   "captures": {
#     "item": "coffee cup"
#   }
# }

# Regex to find {name:provider} slots in a pattern string.
_SLOT_RE = re.compile(r"\{(\w+):(\w+)\}")

# Marker that identifies a describe message as a __complete response.
_COMPLETE_MARKER = "__complete_response"


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

    # Try each pattern, prefer longer (more specific) matches.
    best: dict | None = None
    best_score = -1

    for tokens in parsed_patterns:
        result = _try_match(tokens, user_input)
        if result is not None:
            # Score by how many tokens were consumed (more = better).
            score = len(result.get("captures", {})) + len(tokens)
            if score > best_score:
                best = result
                best_score = score

    return best


def _try_match(tokens: list[dict], user_input: str) -> dict | None:
    """Try to match a single parsed pattern against user input.

    We walk the tokens and the input simultaneously. Literal tokens must
    match exactly.  Slot tokens consume words up to the next literal
    delimiter (or the end of input).

    If the input ends mid-slot (i.e., the slot is the last thing and the
    user has typed a partial word), that's our completion point.
    """
    words = user_input.split()
    wi = 0  # word index into user input
    captures: dict[str, str] = {}

    for ti, token in enumerate(tokens):
        if token["type"] == "literal":
            if wi >= len(words):
                return None  # input too short for this literal
            if words[wi].lower() != token["text"].lower():
                return None  # mismatch
            wi += 1

        elif token["type"] == "slot":
            # Find the next literal token to know where this slot ends.
            next_literal = None
            for ahead in tokens[ti + 1:]:
                if ahead["type"] == "literal":
                    next_literal = ahead["text"]
                    break

            if next_literal is None:
                # This slot runs to the end of the input.
                # Everything remaining is either a captured value or a prefix.
                remaining = words[wi:]
                prefix = " ".join(remaining) if remaining else ""
                return {
                    "provider": token["provider"],
                    "prefix": prefix,
                    "captures": captures,
                    "name": token["name"],
                }
            else:
                # Find the delimiter in the remaining words.
                delim_idx = None
                for i in range(wi, len(words)):
                    if words[i].lower() == next_literal.lower():
                        delim_idx = i
                        break

                if delim_idx is None:
                    # Delimiter not found — user hasn't typed it yet.
                    # The slot value so far is everything remaining.
                    remaining = words[wi:]
                    prefix = " ".join(remaining) if remaining else ""
                    return {
                        "provider": token["provider"],
                        "prefix": prefix,
                        "captures": captures,
                        "name": token["name"],
                    }
                else:
                    # Capture the slot value (words between current pos and delimiter).
                    slot_words = words[wi:delim_idx]
                    if not slot_words:
                        return None  # empty slot value
                    captures[token["name"]] = " ".join(slot_words)
                    wi = delim_idx
                    # Don't advance past delimiter — the next literal token will consume it.

    # If we consumed all tokens but there are leftover words, no match.
    if wi < len(words):
        return None

    return None  # Fully matched pattern with no pending slot — nothing to complete.


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

        # Only consider input up to the cursor position.
        text = input[:cursor] if cursor > 0 else input

        result = match_input(self._parsed_patterns, text)
        if result is None:
            return False

        provider = result["provider"]
        prefix = result["prefix"]
        captures = result["captures"]

        if not prefix:
            # No partial word typed yet — nothing to complete.
            return False

        # Build the __complete payload.
        payload = {
            "provider": provider,
            "prefix": prefix,
            "captures": captures,
        }
        encoded = base64.b64encode(json.dumps(payload).encode()).decode()

        # Get the ctrl_path for the active character.
        cc = self.connection.get_controlled_char(ctrl_id)
        if cc is None:
            return False

        self._pending_complete = True
        self._pending_prefix_len = len(prefix)

        log.debug("Sending __complete: %s", payload)
        await self.connection.send(
            f"call.{cc.ctrl_path}.execRoomCmd",
            {"cmdId": "__complete", "values": {"data": encoded}},
        )
        return True

    async def on_message(self, message: dict, style: str, character: str, **kw):
        """Intercept describe messages that are __complete responses."""
        if not self._pending_complete:
            return
        if style != "describe":
            return

        msg_text = message.get("msg", "")
        if _COMPLETE_MARKER not in msg_text:
            return

        # This is our response. Parse it.
        self._pending_complete = False
        try:
            # Extract JSON from the message. The marker might be a wrapper.
            # Try to find JSON in the message text.
            json_start = msg_text.index("{")
            json_end = msg_text.rindex("}") + 1
            data = json.loads(msg_text[json_start:json_end])
            results = data.get("matches", [])
        except (ValueError, json.JSONDecodeError):
            log.warning("Failed to parse __complete response: %s", msg_text)
            return

        if results:
            await self.event_bus.publish(
                "autocomplete.results",
                results=results,
                prefix_len=self._pending_prefix_len,
            )


# PluginManager looks for this attribute.
plugin = SchemaParser
