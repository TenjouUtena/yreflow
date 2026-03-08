"""Command parsing and dispatch, extracted from Samples/CommandHandler.py.

UI coupling removed -- handlers return CommandResult instead of calling self.ui.*.
Singleton Application() replaced with injected connection/store references.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from .name_resolver import parse_name, NameParseException


def _relative_time(ms_timestamp: float) -> str:
    """Convert a millisecond timestamp to a human-readable relative string."""
    delta = datetime.now(timezone.utc) - datetime.fromtimestamp(ms_timestamp / 1000.0, tz=timezone.utc)
    seconds = int(delta.total_seconds())
    if seconds < 60:
        return f"{seconds} seconds ago"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes} minute{'s' if minutes != 1 else ''} ago"
    hours = minutes // 60
    if hours < 24:
        return f"{hours} hour{'s' if hours != 1 else ''} ago"
    days = hours // 24
    if days < 14:
        return f"{days} day{'s' if days != 1 else ''} ago"
    weeks = days // 7
    if days < 60:
        return f"{weeks} week{'s' if weeks != 1 else ''} ago"
    months = days // 30
    if days < 365:
        return f"{months} month{'s' if months != 1 else ''} ago"
    years = days // 365
    return f"{years} year{'s' if years != 1 else ''} ago"

if TYPE_CHECKING:
    from ..protocol.connection import WolferyConnection
    from ..protocol.model_store import ModelStore
    from ..protocol.controlled_char import ControlledChar


@dataclass
class CommandResult:
    success: bool = True
    notification: str | None = None
    look_data: dict | None = None
    open_profile_select: bool = False
    display_text: str | None = None
    open_settings: bool = False
    toggle_nav: bool = False


class CommandHandler:
    def __init__(self, connection: WolferyConnection, store: ModelStore):
        self.conn = connection
        self.store = store

    def detect_command_type(self, command_text: str):
        """Detect command type and return (style, content, handler_func)."""
        patterns = {}

        patterns["say"] = {
            "patterns": [
                (lambda cmd: cmd.startswith("say "), lambda cmd: cmd[4:]),
                (lambda cmd: cmd.startswith("\u201c"), lambda cmd: cmd[1:]),
                (lambda cmd: cmd.startswith("\u201d"), lambda cmd: cmd[1:]),
                (lambda cmd: cmd.startswith('"'), lambda cmd: cmd[1:]),
            ],
            "function": self.handle_say,
        }

        patterns["ooc"] = {
            "patterns": [
                (
                    lambda cmd: cmd.startswith("ooc ") and not cmd.startswith("ooc :"),
                    lambda cmd: {"msg": cmd[4:], "pose": False},
                ),
                (
                    lambda cmd: cmd.startswith(">:"),
                    lambda cmd: {"msg": cmd[2:], "pose": True},
                ),
                (
                    lambda cmd: cmd.startswith(":>"),
                    lambda cmd: {"msg": cmd[2:], "pose": True},
                ),
                (
                    lambda cmd: cmd.startswith("ooc :"),
                    lambda cmd: {"msg": cmd[5:], "pose": True},
                ),
                (
                    lambda cmd: cmd.startswith(">") and not cmd.startswith(">:"),
                    lambda cmd: {"msg": cmd[1:], "pose": False},
                ),
            ],
            "function": self.handle_ooc,
        }

        patterns["page"] = {
            "patterns": [
                (lambda cmd: cmd.startswith("p "), lambda cmd: {"msg": cmd[2:]}),
                (lambda cmd: cmd.startswith("m "), lambda cmd: {"msg": cmd[2:]}),
            ],
            "function": self.handle_page,
        }

        patterns["whisper"] = {
            "patterns": [
                (lambda cmd: cmd.startswith("w "), lambda cmd: {"msg": cmd[2:]}),
                (lambda cmd: cmd.startswith("wh "), lambda cmd: {"msg": cmd[3:]}),
            ],
            "function": self.handle_whisper,
        }

        patterns["address"] = {
            "patterns": [
                (
                    lambda cmd: cmd.strip().startswith("address "),
                    lambda cmd: {"msg": cmd[8:]},
                ),
                (
                    lambda cmd: cmd.strip().startswith("to "),
                    lambda cmd: {"msg": cmd[3:]},
                ),
                (
                    lambda cmd: cmd.strip().startswith("@"),
                    lambda cmd: {"msg": cmd[1:]},
                ),
            ],
            "function": self.handle_address,
        }

        patterns["pose"] = {
            "patterns": [
                (lambda cmd: cmd.startswith("pose "), lambda cmd: cmd[5:]),
                (lambda cmd: cmd.startswith(":"), lambda cmd: cmd[1:]),
            ],
            "function": self.handle_pose,
        }

        patterns["home"] = {
            "patterns": [
                (lambda cmd: cmd.strip() == "home", lambda cmd: None),
            ],
            "function": self.handle_home,
        }

        patterns["teleport"] = {
            "patterns": [
                (lambda cmd: cmd.startswith("teleport "), lambda cmd: cmd[9:]),
                (lambda cmd: cmd.startswith("t "), lambda cmd: cmd[2:]),
            ],
            "function": self.handle_teleport,
        }

        patterns["sweep"] = {
            "patterns": [
                (lambda cmd: cmd.strip() == "sweep", lambda cmd: None),
                (lambda cmd: cmd.startswith("sweep "), lambda cmd: cmd[6:]),
            ],
            "function": self.handle_sweep,
        }

        patterns["go"] = {
            "patterns": [
                (lambda cmd: cmd.startswith("go "), lambda cmd: cmd[3:]),
            ],
            "function": self.handle_go,
        }

        patterns["status"] = {
            "patterns": [
                (lambda cmd: cmd.strip() == "status", lambda cmd: ""),
                (lambda cmd: cmd.startswith("status "), lambda cmd: cmd[7:]),
            ],
            "function": self.handle_status,
        }

        patterns["release"] = {
            "patterns": [
                (lambda cmd: cmd.strip() == "quit", lambda cmd: None),
                (lambda cmd: cmd.strip() == "sleep", lambda cmd: None),
            ],
            "function": self.handle_release,
        }

        patterns["focus"] = {
            "patterns": [
                (lambda cmd: cmd.startswith("focus "), lambda cmd: cmd[6:]),
            ],
            "function": self.handle_focus,
        }

        patterns["unfocus"] = {
            "patterns": [
                (lambda cmd: cmd.startswith("unfocus "), lambda cmd: cmd[8:]),
            ],
            "function": self.handle_unfocus,
        }

        patterns["summon"] = {
            "patterns": [
                (lambda cmd: cmd.startswith("summon "), lambda cmd: cmd[7:]),
            ],
            "function": self.handle_summon,
        }

        patterns["join"] = {
            "patterns": [
                (lambda cmd: cmd.startswith("join "), lambda cmd: cmd[5:]),
            ],
            "function": self.handle_join,
        }

        patterns["lead"] = {
            "patterns": [
                (lambda cmd: cmd.startswith("lead "), lambda cmd: cmd[5:]),
            ],
            "function": self.handle_lead,
        }

        patterns["follow"] = {
            "patterns": [
                (lambda cmd: cmd.startswith("follow "), lambda cmd: cmd[7:]),
            ],
            "function": self.handle_follow,
        }

        patterns["profile"] = {
            "patterns": [
                (lambda cmd: cmd.strip() in ("profile", "morph"), lambda cmd: ""),
                (lambda cmd: cmd.startswith("profile "), lambda cmd: cmd[8:]),
                (lambda cmd: cmd.startswith("morph "), lambda cmd: cmd[6:]),
            ],
            "function": self.handle_profile,
        }

        patterns["look"] = {
            "patterns": [
                (lambda cmd: cmd.strip() == "look", lambda cmd: None),
                (lambda cmd: cmd.strip() == "l", lambda cmd: None),
                (lambda cmd: cmd.startswith("look "), lambda cmd: cmd[5:]),
                (lambda cmd: cmd.startswith("l "), lambda cmd: cmd[2:]),
            ],
            "function": self.handle_look,
        }

        patterns["whois"] = {
            "patterns": [
                (lambda cmd: cmd.startswith("whois "), lambda cmd: cmd[6:]),
            ],
            "function": self.handle_whois,
        }

        patterns["laston"] = {
            "patterns": [
                (lambda cmd: cmd.startswith("laston "), lambda cmd: cmd[7:]),
            ],
            "function": self.handle_laston,
        }

        patterns["wa"] = {
            "patterns": [
                (lambda cmd: cmd.strip() == "wa", lambda cmd: None),
                (lambda cmd: cmd.strip() == "whereat", lambda cmd: None),
            ],
            "function": self.handle_wa,
        }

        patterns["lookup"] = {
            "patterns": [
                (lambda cmd: cmd.startswith("lookup "), lambda cmd: cmd[7:])
            ],
            "function": self.handle_lookup
        }

        patterns["stop_follow"] = {
            "patterns": [
                (lambda cmd: cmd.strip() == "stop follow", lambda cmd: ""),
            ],
            "function": self.handle_stop_follow,
        }

        patterns["stop_lead"] = {
            "patterns": [
                (lambda cmd: cmd.strip() == "stop lead", lambda cmd: ""),
                (lambda cmd: cmd.startswith("stop lead "), lambda cmd: cmd[10:]),
            ],
            "function": self.handle_stop_lead,
        }

        patterns["stop_lfrp"] = {
            "patterns": [
                (lambda cmd: cmd.strip() == "stop lfrp", lambda cmd: ""),
            ],
            "function": self.handle_stop_lfrp,
        }

        patterns["lfrp"] = {
            "patterns": [
                (lambda cmd: cmd.strip() == "lfrp", lambda cmd: ""),
                (lambda cmd: cmd.startswith("lfrp "), lambda cmd: cmd[5:]),
            ],
            "function": self.handle_lfrp,
        }

        patterns["settings"] = {
            "patterns": [
                (lambda cmd: cmd.strip() == "settings", lambda cmd: ""),
            ],
            "function": self.handle_settings,
        }

        patterns["describe"] = {
            "patterns": [
                (lambda cmd: cmd.startswith("describe "), lambda cmd: cmd[9:]),
                (lambda cmd: cmd.startswith("desc "), lambda cmd: cmd[5:]),
                (lambda cmd: cmd.startswith("spoof "), lambda cmd: cmd[6:]),
            ],
            "function": self.handle_describe,
        }

        patterns["nav"] = {
            "patterns": [
                (lambda cmd: cmd.strip() == "nav", lambda cmd: ""),
            ],
            "function": self.handle_nav,
        }

        for style in patterns:
            for matcher, extractor in patterns[style]["patterns"]:
                if matcher(command_text):
                    return (style, extractor(command_text), patterns[style]["function"])

        return ("unknown", command_text, None)

    async def process_command(self, command: str, cc: ControlledChar) -> CommandResult:
        command = command.strip()
        if not command:
            return CommandResult()

        command_type, content, func_call = self.detect_command_type(command)
        if func_call:
            return await func_call(content, cc)
        return CommandResult(success=False, notification=f"Unknown command: {command}")

    # --- Handlers ---

    def _parse_directed_content(self, raw_msg: str):
        """Parse 'Name[, Name2, ...]=message' with optional pose/ooc flags.

        Returns (names_list, msg, pose, ooc) or None if unparseable.
        Names may be comma-separated for multi-recipient sends.
        """
        m = re.match(r"([\w ,-]+)=(.*)", raw_msg, re.DOTALL)
        if not m:
            return None
        names = [n.strip() for n in m.group(1).split(",") if n.strip()]
        msg = m.group(2).strip()
        pose = False
        ooc = False

        if msg[:2] in (":>", ">:"):
            pose, ooc, msg = True, True, msg[2:]
        elif msg[0:1] == ">":
            ooc, msg = True, msg[1:]
        elif msg[0:1] == ":":
            pose, msg = True, msg[1:]

        return names, msg, pose, ooc

    async def handle_say(self, content, cc: ControlledChar) -> CommandResult:
        await self.conn.send(
            f"call.{cc.ctrl_path}.say", {"msg": content}
        )
        return CommandResult()

    async def handle_pose(self, content, cc: ControlledChar) -> CommandResult:
        await self.conn.send(
            f"call.{cc.ctrl_path}.pose", {"msg": content}
        )
        return CommandResult()

    async def handle_ooc(self, content, cc: ControlledChar) -> CommandResult:
        payload = {"msg": content["msg"]}
        if content["pose"]:
            payload["pose"] = True
        await self.conn.send(
            f"call.{cc.ctrl_path}.ooc", payload
        )
        return CommandResult()

    def _resolve_directed_targets(self, names: list[str]):
        """Resolve a list of name strings to (char_ids, full_names) or raise."""
        char_ids, full_names = [], []
        for raw_name in names:
            char_id = parse_name(self.store, raw_name)
            first = self.store.get_character_attribute(char_id, "name") or ""
            last = self.store.get_character_attribute(char_id, "surname") or ""
            char_ids.append(char_id)
            full_names.append(f"{first} {last}".strip())
        return char_ids, full_names

    async def handle_whisper(self, content, cc: ControlledChar) -> CommandResult:
        parsed = self._parse_directed_content(content["msg"])
        if not parsed:
            return CommandResult(success=False, notification="Could not parse whisper")
        names, msg, pose, ooc = parsed
        try:
            char_ids, full_names = self._resolve_directed_targets(names)
        except NameParseException as e:
            return CommandResult(success=False, notification=str(e))
        self.conn.push_directed_contact(char_ids, full_names, "w")
        await self.conn.send(
            f"call.{cc.ctrl_path}.whisper",
            {"charIds": char_ids, "msg": msg, "pose": pose, "ooc": ooc},
        )
        return CommandResult()

    async def handle_page(self, content, cc: ControlledChar) -> CommandResult:
        parsed = self._parse_directed_content(content["msg"])
        if not parsed:
            return CommandResult(success=False, notification="Could not parse page")
        names, msg, pose, ooc = parsed
        try:
            char_ids, full_names = self._resolve_directed_targets(names)
        except NameParseException as e:
            return CommandResult(success=False, notification=str(e))
        self.conn.push_directed_contact(char_ids, full_names, "m")
        await self.conn.send(
            f"call.{cc.ctrl_path}.message",
            {"charIds": char_ids, "msg": msg, "pose": pose, "ooc": ooc},
        )
        return CommandResult()

    async def handle_address(self, content, cc: ControlledChar) -> CommandResult:
        parsed = self._parse_directed_content(content["msg"])
        if not parsed:
            return CommandResult(success=False, notification="Could not parse address")
        names, msg, pose, ooc = parsed
        try:
            char_ids, full_names = self._resolve_directed_targets(names)
        except NameParseException as e:
            return CommandResult(success=False, notification=str(e))
        self.conn.push_directed_contact(char_ids, full_names, "@")
        await self.conn.send(
            f"call.{cc.ctrl_path}.address",
            {"charIds": char_ids, "msg": msg, "pose": pose, "ooc": ooc},
        )
        return CommandResult()

    async def handle_home(self, content, cc: ControlledChar) -> CommandResult:
        await self.conn.send(
            f"call.{cc.ctrl_path}.teleportHome", {}
        )
        return CommandResult(notification="Teleporting home...")

    async def handle_teleport(self, location, cc: ControlledChar) -> CommandResult:
        location_key = location.strip().lower()
        node_id = None

        # Try character-specific nodes first
        try:
            char_node_refs = self.store.get(f"{cc.char_path}.nodes._value")
            for ref in char_node_refs:
                node_data = self.store.get(ref["rid"])
                if "key" in node_data and node_data["key"].lower() == location_key:
                    node_id = node_data["id"]
                    break
        except KeyError:
            pass

        # Fall back to global nodes
        if not node_id:
            try:
                nodes = self.store.get("core.node")
                for node_key in nodes:
                    node_data = nodes[node_key]
                    if "key" in node_data and node_data["key"].lower() == location_key:
                        node_id = node_data["id"]
                        break
            except KeyError:
                pass

        if not node_id:
            return CommandResult(
                success=False,
                notification=f"Cannot teleport: '{location}' not found.",
            )
        await self.conn.send(
            f"call.{cc.ctrl_path}.teleport", {"nodeId": node_id}
        )
        return CommandResult(notification=f"Teleported to {location}.")

    async def handle_sweep(self, content, cc: ControlledChar) -> CommandResult:
        params = {}
        if content:
            try:
                target_id = parse_name(self.store, content)
                display_name = parse_name(self.store, content, wants="name")
            except NameParseException as e:
                return CommandResult(success=False, notification=str(e))
            params["charId"] = target_id
        await self.conn.send(
            f"call.{cc.ctrl_path}.sweep", params
        )
        if content:
            return CommandResult(notification=f"Sweeping {display_name}...")
        return CommandResult()

    def _find_exit_by_key(self, cc: ControlledChar, exit_name: str) -> dict | None:
        """Find an exit in the character's current room matching exit_name."""
        room_pointer = self.store.get_room_rid(cc.char_path)
        if not room_pointer:
            return None

        for e in self.store.get_room_exits(room_pointer):
            try:
                exit_model = self.store.get(e["rid"])
                for k in exit_model.get("keys", {}).get("data", []):
                    if k.casefold() == exit_name.casefold():
                        return exit_model
            except KeyError:
                continue
        return None

    async def handle_go(self, exit_name, cc: ControlledChar) -> CommandResult:
        the_exit = self._find_exit_by_key(cc, exit_name)
        if not the_exit:
            return CommandResult(
                success=False, notification=f"Couldn't go {exit_name}"
            )
        await self.conn.send(
            f"call.{cc.ctrl_path}.useExit",
            {"exitId": the_exit["id"]},
        )
        return CommandResult()

    async def handle_status(self, status_text, cc: ControlledChar) -> CommandResult:
        await self.conn.send(
            f"call.{cc.ctrl_path}.set", {"status": status_text}
        )
        note = f"Status set to: {status_text}" if status_text else "Status cleared"
        return CommandResult(notification=note)

    async def handle_release(self, content, cc: ControlledChar) -> CommandResult:
        await self.conn.send(
            f"call.{cc.ctrl_path}.release", {}
        )
        return CommandResult(notification="Character released")

    async def handle_focus(self, content, cc: ControlledChar) -> CommandResult:
        m = re.match(r"([\w ]+)=(.*)", content, re.DOTALL)
        if not m:
            return CommandResult(success=False, notification="Could not parse focus")
        name, color = m.group(1), m.group(2)
        try:
            target_id = parse_name(self.store, name, wants="id")
        except NameParseException:
            return CommandResult(
                success=False, notification="Could not find a unique person."
            )
        params = {"targetId": target_id, "charId": cc.char_id, "color": color}
        if cc.is_puppet:
            params["puppeteerId"] = cc.puppeteer_id
        await self.conn.send(
            f"call.core.player.{self.conn.player}.focusChar", params,
        )
        return CommandResult()

    async def handle_unfocus(self, content, cc: ControlledChar) -> CommandResult:
        try:
            target_id = parse_name(self.store, content, wants="id")
        except NameParseException:
            return CommandResult(
                success=False, notification="Could not find a unique person."
            )
        params = {"targetId": target_id, "charId": cc.char_id}
        if cc.is_puppet:
            params["puppeteerId"] = cc.puppeteer_id
        await self.conn.send(
            f"call.core.player.{self.conn.player}.unfocusChar", params,
        )
        return CommandResult()

    async def handle_summon(self, name_to_summon, cc: ControlledChar) -> CommandResult:
        try:
            target_id = parse_name(self.store, name_to_summon)
            display_name = parse_name(self.store, name_to_summon, wants="name")
        except NameParseException as e:
            return CommandResult(success=False, notification=str(e))
        await self.conn.send(
            f"call.{cc.ctrl_path}.summon", {"charId": target_id}
        )
        return CommandResult(notification=f"Summoning {display_name}...")

    async def handle_join(self, name_to_join, cc: ControlledChar) -> CommandResult:
        try:
            target_id = parse_name(self.store, name_to_join)
            display_name = parse_name(self.store, name_to_join, wants="name")
        except NameParseException as e:
            return CommandResult(success=False, notification=str(e))
        await self.conn.send(
            f"call.{cc.ctrl_path}.join", {"charId": target_id}
        )
        return CommandResult(notification=f"Joining {display_name}...")

    async def handle_lead(self, name_to_lead, cc: ControlledChar) -> CommandResult:
        try:
            target_id = parse_name(self.store, name_to_lead)
            display_name = parse_name(self.store, name_to_lead, wants="name")
        except NameParseException as e:
            return CommandResult(success=False, notification=str(e))
        await self.conn.send(
            f"call.{cc.ctrl_path}.lead", {"charId": target_id}
        )
        return CommandResult(notification=f"Leading {display_name}...")

    async def handle_follow(self, name_to_follow, cc: ControlledChar) -> CommandResult:
        try:
            target_id = parse_name(self.store, name_to_follow)
            display_name = parse_name(self.store, name_to_follow, wants="name")
        except NameParseException as e:
            return CommandResult(success=False, notification=str(e))
        await self.conn.send(
            f"call.{cc.ctrl_path}.follow", {"charId": target_id}
        )
        return CommandResult(notification=f"Following {display_name}...")

    async def handle_stop_follow(self, content, cc: ControlledChar) -> CommandResult:
        await self.conn.send(f"call.{cc.ctrl_path}.stopFollow")
        return CommandResult(notification="Stopped following.")

    async def handle_stop_lead(self, content, cc: ControlledChar) -> CommandResult:
        params = {}
        if content:
            try:
                target_id = parse_name(self.store, content)
                display_name = parse_name(self.store, content, wants="name")
            except NameParseException as e:
                return CommandResult(success=False, notification=str(e))
            params["charId"] = target_id
            note = f"Stopped leading {display_name}."
        else:
            note = "Stopped leading."
        await self.conn.send(f"call.{cc.ctrl_path}.stopLead", params or None)
        return CommandResult(notification=note)

    async def handle_profile(self, profile_name, cc: ControlledChar) -> CommandResult:
        if not profile_name:
            return CommandResult(open_profile_select=True)
        # Look up profile by keyword first, then by name
        try:
            profiles = self.store.get(
                f"{cc.char_path}.profiles._value"
            )
        except KeyError:
            return CommandResult(
                success=False, notification="No profiles found."
            )
        search = profile_name.strip().lower()
        # Pass 1: match keyword
        for entry in profiles:
            try:
                profile = self.store.get(entry["rid"])
                if profile.get("key", "").lower() == search:
                    return await self._switch_profile(entry, profile, cc)
            except (KeyError, AttributeError):
                continue
        # Pass 2: match name
        for entry in profiles:
            try:
                profile = self.store.get(entry["rid"])
                if profile.get("name", "").lower() == search:
                    return await self._switch_profile(entry, profile, cc)
            except (KeyError, AttributeError):
                continue
        return CommandResult(
            success=False,
            notification=f"Profile not found: {profile_name}",
        )

    async def _switch_profile(self, entry, profile, cc: ControlledChar) -> CommandResult:
        profile_id = entry["rid"].split(".")[-1]
        await self.conn.send(
            f"call.{cc.ctrl_path}.useProfile",
            {"profileId": profile_id, "safe": True},
        )
        return CommandResult(
            notification=f"Morphing into {profile.get('name', '?')}..."
        )

    async def handle_wa(self, content, cc: ControlledChar) -> CommandResult:
        """Handle whereat (wa) command -- show area population tree."""
        room_pointer = self.store.get_room_rid(cc.char_path)
        if not room_pointer:
            return CommandResult(
                success=False, notification="Could not determine current room."
            )
        try:
            room = self.store.get(room_pointer)
            area_path = room["details"]["area"]["rid"]
        except KeyError:
            return CommandResult(
                success=False, notification=f"Could not determine current area. {room}"
            )

        # Walk up to top-level area
        while True:
            try:
                area = self.store.get(area_path)
                parent = area.get("parent") or area.get("details", {}).get("parent")
                if isinstance(parent, dict) and "rid" in parent:
                    area_path = parent["rid"]
                else:
                    break
            except KeyError:
                break

        area_id = ".".join(area_path.split(".")[:3])
        output = self._build_wa_output(area_id, level=0)
        if not output:
            return CommandResult(notification="No occupied areas found.")
        return CommandResult(display_text=output.rstrip("\n"))

    def _build_wa_output(self, base: str, level: int = 0) -> str:
        """Recursively build the whereat text output."""
        try:
            area = self.store.get(base)
            if len(area) == 1:
                try:
                    area = self.store.get(base + ".child")
                except KeyError:
                    pass
        except KeyError:
            try:
                area = self.store.get(base + ".child")
            except KeyError:
                return ""

        if "details" in area:
            children = area.get("children", {})
            area = area["details"]
        else:
            children = {}

        result = ""
        pop = area.get("pop", 0)
        name = area.get("name", "")
        if name and pop:
            indent = "  " * level
            result += f"{indent}{name} [bold]{pop}[/bold]\n"

        for key in children:
            try:
                child_rid = children[key]["rid"]
                child_base = ".".join(child_rid.split(".")[:3])
                result += self._build_wa_output(child_base, level + 1)
            except (KeyError, TypeError):
                continue

        return result

    async def handle_laston(self, name_to_check, cc: ControlledChar) -> CommandResult:
        try:
            target_id = parse_name(self.store, name_to_check, awake=False)
        except NameParseException as e:
            return CommandResult(success=False, notification=str(e))
        try:
            char_data = self.store.get(f"core.char.{target_id}")
        except KeyError:
            return CommandResult(success=False, notification="Character data not found.")
        if "lastAwake" not in char_data:
            return CommandResult(
                success=False,
                notification=f"No last online info for {name_to_check}",
            )
        last_awake = _relative_time(char_data["lastAwake"])
        char_name = char_data.get("name", "?")
        if "surname" in char_data:
            char_name += f" {char_data['surname']}"
        return CommandResult(
            display_text=f"{char_name} was last online {last_awake}"
        )

    async def handle_whois(self, name_to_check, cc: ControlledChar) -> CommandResult:
        try:
            target_id = parse_name(self.store, name_to_check, awake=False)
        except NameParseException as e:
            return CommandResult(success=False, notification=str(e))

        msg_id = await self.conn.send(
            f"call.core.player.{self.conn.player}.getChar",
            {"charId": target_id},
        )
        self.conn.add_message_wait(
            msg_id,
            lambda _result, tid=target_id: self._on_whois_result(tid),
        )
        return CommandResult(notification="Looking up...")

    async def _on_whois_result(self, char_id: str) -> None:
        """Called when the getChar response arrives. Publishes whois data."""
        s = self.store
        name = s.get_character_attribute(char_id, "name") or "?"
        surname = s.get_character_attribute(char_id, "surname") or ""
        full_name = f"{name} {surname}".strip()
        species = s.get_character_attribute(char_id, "species") or ""
        gender = s.get_character_attribute(char_id, "gender") or ""
        status = s.get_character_attribute(char_id, "status") or ""
        avatar = s.get_character_attribute(char_id, "avatar", default="")

        # Tags (reuse same logic as _gather_character_data)
        tags = []
        try:
            tags_ref = s.get_character_attribute(char_id, "tags")
            if isinstance(tags_ref, dict) and "rid" in tags_ref:
                tags_model = s.get(tags_ref["rid"])
                for key, entry in tags_model.items():
                    if not isinstance(entry, dict) or "rid" not in entry:
                        continue
                    try:
                        tag_info = s.get(entry["rid"])
                        like = "_like" in key
                        tags.append({
                            "key": tag_info.get("key", key),
                            "desc": tag_info.get("desc", ""),
                            "like": like,
                        })
                    except KeyError:
                        continue
        except (KeyError, TypeError):
            pass

        data = {
            "type": "whois",
            "char_id": char_id,
            "name": full_name,
            "species": species.capitalize() if species else "",
            "gender": gender.capitalize() if gender else "",
            "status": status,
            "tags": tags,
            "avatar": avatar,
            "auth_token": self.conn.token or "",
        }
        await self.conn.event_bus.publish("whois.result", data=data)

    async def handle_look(self, content, cc: ControlledChar) -> CommandResult:
        if content is None:
            return self._look_room(cc)
        return await self._look_character(content, cc)

    async def handle_lookup(self, content, cc: ControlledChar) -> CommandResult:
        payload = content.split(' ')[0]
        msg_id = await self.conn.send(f"call.core.player.{self.conn.player}.lookupChars",
                             {"extended": True,
                              "name": payload})
        self.conn.add_message_wait(
            msg_id,
            lambda _result: self._lookup_result(_result)
        )

    async def handle_lfrp(self, content: str, cc: ControlledChar) -> CommandResult:
        params = {"charId": cc.char_id, "lfrpDesc": content}
        if cc.is_puppet:
            params["puppeteerId"] = cc.puppeteer_id
        await self.conn.send(
            f"call.core.player.{self.conn.player}.setCharSettings", params,
        )
        await self.conn.send(
            f"call.{cc.ctrl_path}.set", {"rp": "lfrp"}
        )
        note = f"Looking for RP: {content}" if content else "Now looking for RP."
        return CommandResult(display_text=note)

    async def handle_stop_lfrp(self, content: str, cc: ControlledChar) -> CommandResult:
        await self.conn.send(
            f"call.{cc.ctrl_path}.set", {"rp": ""}
        )
        return CommandResult(display_text="No longer looking for RP.")

    async def handle_settings(self, content: str, cc: ControlledChar) -> CommandResult:
        return CommandResult(open_settings=True)

    async def handle_nav(self, content: str, cc: ControlledChar) -> CommandResult:
        return CommandResult(toggle_nav=True)

    async def handle_describe(self, content: str, cc: ControlledChar) -> CommandResult:
        await self.conn.send(
            f"call.{cc.ctrl_path}.describe", {"msg": content}
        )
        return CommandResult()

    async def _lookup_result(self, payload) -> None:
        output = f"{'Char:':<30}{'Gender':<10}{'Species:':<20}{'Last On:':<20}\n"
        for char in payload.get("chars",[]):
            surname_len = 29 - (len(char['name']) + len(char['surname']))
            last_awake = _relative_time(char['lastAwake'])
            output += f"{char['name']} {char['surname']}{' '*surname_len}{char['gender']:<10}{char['species']:<20}{last_awake}\n"
        await self.conn.event_bus.publish("system.text", text=output)


    def _look_room(self, cc: ControlledChar) -> CommandResult:
        """Gather room data from the store and return it for display."""
        room_pointer = self.store.get_room_rid(cc.char_path)
        if not room_pointer:
            return CommandResult(success=False, notification="Could not determine current room.")
        room_id = room_pointer.split(".")[2]

        room_name = self.store.get_room_attribute(room_id, "name") or "Unknown Room"
        room_desc = self.store.get_room_attribute(room_id, "desc") or ""

        # Exits
        exits = []
        for e in self.store.get_room_exits(room_pointer):
            try:
                exit_model = self.store.get(e["rid"])
                keys = exit_model.get("keys", {}).get("data", [])
                exits.append({
                    "name": exit_model.get("name", "?"),
                    "keys": ", ".join(keys),
                })
            except KeyError:
                continue

        # Area hierarchy
        areas = []
        try:
            room_model = self.store.get(f"core.room.{room_id}")
            area_ref = room_model.get("area", {})
            if isinstance(area_ref, dict) and "rid" in area_ref:
                area_path = area_ref["rid"]
                while area_path:
                    try:
                        area = self.store.get(area_path)
                        # Area may be nested under .details
                        details = area.get("details", area)
                        area_name = details.get("name", "")
                        area_about = details.get("about", "")
                        area_pop = details.get("pop", 0)
                        if area_name:
                            areas.append({
                                "name": area_name,
                                "about": area_about,
                                "pop": area_pop,
                            })
                        # Traverse parent
                        parent = area.get("parent") or details.get("parent")
                        if isinstance(parent, dict) and "rid" in parent:
                            area_path = parent["rid"]
                        else:
                            area_path = None
                    except KeyError:
                        break
        except KeyError:
            pass

        return CommandResult(look_data={
            "type": "room",
            "name": room_name,
            "desc": room_desc,
            "exits": exits,
            "areas": areas,
        })

    async def _look_character(self, name_str: str, cc: ControlledChar) -> CommandResult:
        """Look at a character: send ctrl.look, then gather data on response."""
        try:
            target_id = parse_name(self.store, name_str.strip())
        except NameParseException as e:
            return CommandResult(success=False, notification=str(e))

        msg_id = await self.conn.look_at(target_id, cc)
        self.conn.add_message_wait(
            msg_id,
            lambda _result, tid=target_id: self._on_look_result(tid),
        )
        return CommandResult(notification="Looking...")

    async def _on_look_result(self, char_id: str) -> None:
        """Called when the look_at response arrives. Publishes look data."""
        data = self._gather_character_data(char_id)
        await self.conn.event_bus.publish("look.result", data=data)

        # Watch for store updates to this character (e.g. desc arriving late)
        self._remove_look_watch()

        async def _on_char_update(path, payload):
            updated = self._gather_character_data(char_id)
            await self.conn.event_bus.publish("look.update", data=updated)

        self._look_watch_cb = _on_char_update
        self.store.add_watch(rf"core\.char\.{char_id}\.", _on_char_update)

        # Image model lives at core.char.img.* (separate from char path)
        try:
            image_ref = self.store.get_character_attribute(char_id, "image")
            if isinstance(image_ref, dict) and "rid" in image_ref:
                img_path = image_ref["rid"].replace(".", r"\.")
                self._look_img_watch_cb = _on_char_update
                self.store.add_watch(rf"{img_path}", _on_char_update)
        except (KeyError, TypeError):
            pass

    def _remove_look_watch(self) -> None:
        cb = getattr(self, "_look_watch_cb", None)
        if cb is not None:
            self.store.remove_watch(cb)
            self._look_watch_cb = None
        img_cb = getattr(self, "_look_img_watch_cb", None)
        if img_cb is not None:
            self.store.remove_watch(img_cb)
            self._look_img_watch_cb = None

    def _gather_character_data(self, char_id: str) -> dict:
        """Read character attributes from the store."""
        s = self.store
        name = s.get_character_attribute(char_id, "name") or "?"
        surname = s.get_character_attribute(char_id, "surname") or ""
        full_name = f"{name} {surname}".strip()
        species = s.get_character_attribute(char_id, "species") or ""
        gender = s.get_character_attribute(char_id, "gender") or ""
        desc = s.get_character_attribute(char_id, "desc") or ""
        about = s.get_character_attribute(char_id, "about") or ""

        # Tags (likes/dislikes)
        tags = []
        try:
            tags_ref = s.get_character_attribute(char_id, "tags")
            if isinstance(tags_ref, dict) and "rid" in tags_ref:
                tags_model = s.get(tags_ref["rid"])
                for key, entry in tags_model.items():
                    if not isinstance(entry, dict) or "rid" not in entry:
                        continue
                    try:
                        tag_info = s.get(entry["rid"])
                        like = "_like" in key
                        tags.append({
                            "key": tag_info.get("key", key),
                            "desc": tag_info.get("desc", ""),
                            "like": like,
                        })
                    except KeyError:
                        continue
        except (KeyError, TypeError):
            pass

        # Avatar key
        avatar = s.get_character_attribute(char_id, "avatar", default="")

        return {
            "type": "character",
            "char_id": char_id,
            "name": full_name,
            "species": species.capitalize() if species else "",
            "gender": gender.capitalize() if gender else "",
            "desc": desc,
            "about": about,
            "tags": tags,
            "avatar": avatar,
            "auth_token": self.conn.token or "",
        }
