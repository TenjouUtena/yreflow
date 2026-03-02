"""Command parsing and dispatch, extracted from Samples/CommandHandler.py.

UI coupling removed -- handlers return CommandResult instead of calling self.ui.*.
Singleton Application() replaced with injected connection/store references.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING

from .name_resolver import parse_name, NameParseException

if TYPE_CHECKING:
    from ..protocol.connection import WolferyConnection
    from ..protocol.model_store import ModelStore


@dataclass
class CommandResult:
    success: bool = True
    notification: str | None = None
    look_data: dict | None = None
    open_profile_select: bool = False
    display_text: str | None = None


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

        for style in patterns:
            for matcher, extractor in patterns[style]["patterns"]:
                if matcher(command_text):
                    return (style, extractor(command_text), patterns[style]["function"])

        return ("unknown", command_text, None)

    async def process_command(self, command: str, character: str) -> CommandResult:
        command = command.strip()
        if not command:
            return CommandResult()

        command_type, content, func_call = self.detect_command_type(command)
        if func_call:
            return await func_call(content, character)
        return CommandResult(success=False, notification=f"Unknown command: {command}")

    # --- Handlers ---

    def _parse_directed_content(self, raw_msg: str):
        """Parse 'Name=message' with optional pose/ooc flags."""
        m = re.match(r"([\w ]+)=(.*)", raw_msg, re.DOTALL)
        if not m:
            return None
        name = m.group(1)
        msg = m.group(2)
        pose = False
        ooc = False

        if msg[:2] in (":>", ">:"):
            pose, ooc, msg = True, True, msg[2:]
        elif msg[0:1] == ">":
            ooc, msg = True, msg[1:]
        elif msg[0:1] == ":":
            pose, msg = True, msg[1:]

        return name, msg, pose, ooc

    async def handle_say(self, content, character) -> CommandResult:
        await self.conn.send(
            f"call.core.char.{character}.ctrl.say", {"msg": content}
        )
        return CommandResult()

    async def handle_pose(self, content, character) -> CommandResult:
        await self.conn.send(
            f"call.core.char.{character}.ctrl.pose", {"msg": content}
        )
        return CommandResult()

    async def handle_ooc(self, content, character) -> CommandResult:
        payload = {"msg": content["msg"]}
        if content["pose"]:
            payload["pose"] = True
        await self.conn.send(
            f"call.core.char.{character}.ctrl.ooc", payload
        )
        return CommandResult()

    async def handle_whisper(self, content, character) -> CommandResult:
        parsed = self._parse_directed_content(content["msg"])
        if not parsed:
            return CommandResult(success=False, notification="Could not parse whisper")
        name, msg, pose, ooc = parsed
        try:
            target = parse_name(self.store, name)
        except NameParseException as e:
            return CommandResult(success=False, notification=str(e))
        self.conn.last_directed = target
        await self.conn.send(
            f"call.core.char.{character}.ctrl.whisper",
            {"charIds": [target], "msg": msg, "pose": pose, "ooc": ooc},
        )
        return CommandResult()

    async def handle_page(self, content, character) -> CommandResult:
        parsed = self._parse_directed_content(content["msg"])
        if not parsed:
            return CommandResult(success=False, notification="Could not parse page")
        name, msg, pose, ooc = parsed
        try:
            target = parse_name(self.store, name)
        except NameParseException as e:
            return CommandResult(success=False, notification=str(e))
        self.conn.last_directed = target
        await self.conn.send(
            f"call.core.char.{character}.ctrl.message",
            {"charIds": [target], "msg": msg, "pose": pose, "ooc": ooc},
        )
        return CommandResult()

    async def handle_address(self, content, character) -> CommandResult:
        parsed = self._parse_directed_content(content["msg"])
        if not parsed:
            return CommandResult(success=False, notification="Could not parse address")
        name, msg, pose, ooc = parsed
        try:
            target = parse_name(self.store, name)
        except NameParseException as e:
            return CommandResult(success=False, notification=str(e))
        self.conn.last_directed = target
        await self.conn.send(
            f"call.core.char.{character}.ctrl.address",
            {"charIds": [target], "msg": msg, "pose": pose, "ooc": ooc},
        )
        return CommandResult()

    async def handle_home(self, content, character) -> CommandResult:
        await self.conn.send(
            f"call.core.char.{character}.ctrl.teleportHome", {}
        )
        return CommandResult(notification="Teleporting home...")

    async def handle_teleport(self, location, character) -> CommandResult:
        try:
            nodes = self.store.get("core.node")
        except KeyError:
            return CommandResult(
                success=False, notification="Cannot teleport: no nodes found."
            )
        location_key = location.strip().lower()
        node_id = None
        for node_key in nodes:
            node_data = nodes[node_key]
            if "key" in node_data and node_data["key"].lower() == location_key:
                node_id = node_data["id"]
                break
        if not node_id:
            return CommandResult(
                success=False,
                notification=f"Cannot teleport: '{location}' not found.",
            )
        await self.conn.send(
            f"call.core.char.{character}.ctrl.teleport", {"nodeId": node_id}
        )
        return CommandResult(notification=f"Teleported to {location}.")

    async def handle_sweep(self, content, character) -> CommandResult:
        await self.conn.send(
            f"call.core.char.{character}.ctrl.sweep", {}
        )
        return CommandResult()

    async def handle_go(self, exit_name, character) -> CommandResult:
        try:
            room_pointer = self.store.get(
                f"core.char.{character}.owned.inRoom"
            )["rid"]
        except KeyError:
            return CommandResult(
                success=False, notification="Could not determine current room."
            )
        try:
            room_exits = self.store.get(room_pointer + ".exits._value")
        except KeyError:
            room_exits = []

        the_exit = None
        for e in room_exits:
            exit_model = self.store.get(e["rid"])
            for k in exit_model["keys"]["data"]:
                if k.casefold() == exit_name.casefold():
                    the_exit = exit_model
        if not the_exit:
            return CommandResult(
                success=False, notification=f"Couldn't go {exit_name}"
            )
        await self.conn.send(
            f"call.core.char.{character}.ctrl.useExit",
            {"exitId": the_exit["id"]},
        )
        return CommandResult()

    async def handle_status(self, status_text, character) -> CommandResult:
        await self.conn.send(
            f"call.core.char.{character}.ctrl.set", {"status": status_text}
        )
        note = f"Status set to: {status_text}" if status_text else "Status cleared"
        return CommandResult(notification=note)

    async def handle_release(self, content, character) -> CommandResult:
        await self.conn.send(
            f"call.core.char.{character}.ctrl.release", {}
        )
        return CommandResult(notification="Character released")

    async def handle_focus(self, content, character) -> CommandResult:
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
        await self.conn.send(
            f"call.core.player.{self.conn.player}.focusChar",
            {"targetId": target_id, "charId": character, "color": color},
        )
        return CommandResult()

    async def handle_unfocus(self, content, character) -> CommandResult:
        try:
            target_id = parse_name(self.store, content, wants="id")
        except NameParseException:
            return CommandResult(
                success=False, notification="Could not find a unique person."
            )
        await self.conn.send(
            f"call.core.player.{self.conn.player}.unfocusChar",
            {"targetId": target_id, "charId": character},
        )
        return CommandResult()

    async def handle_summon(self, name_to_summon, character) -> CommandResult:
        try:
            target_id = parse_name(self.store, name_to_summon)
        except NameParseException as e:
            return CommandResult(success=False, notification=str(e))
        await self.conn.send(
            f"call.core.char.{character}.ctrl.summon", {"charId": target_id}
        )
        return CommandResult(notification=f"Summoning {name_to_summon}...")

    async def handle_join(self, name_to_join, character) -> CommandResult:
        try:
            target_id = parse_name(self.store, name_to_join)
        except NameParseException as e:
            return CommandResult(success=False, notification=str(e))
        await self.conn.send(
            f"call.core.char.{character}.ctrl.join", {"charId": target_id}
        )
        return CommandResult(notification=f"Joining {name_to_join}...")

    async def handle_lead(self, name_to_lead, character) -> CommandResult:
        try:
            target_id = parse_name(self.store, name_to_lead)
        except NameParseException as e:
            return CommandResult(success=False, notification=str(e))
        await self.conn.send(
            f"call.core.char.{character}.ctrl.lead", {"charId": target_id}
        )
        return CommandResult(notification=f"Leading {name_to_lead}...")

    async def handle_follow(self, name_to_follow, character) -> CommandResult:
        try:
            target_id = parse_name(self.store, name_to_follow)
        except NameParseException as e:
            return CommandResult(success=False, notification=str(e))
        await self.conn.send(
            f"call.core.char.{character}.ctrl.follow", {"charId": target_id}
        )
        return CommandResult(notification=f"Following {name_to_follow}...")

    async def handle_profile(self, profile_name, character) -> CommandResult:
        if not profile_name:
            return CommandResult(open_profile_select=True)
        # Look up profile by keyword first, then by name
        try:
            profiles = self.store.get(
                f"core.char.{character}.profiles._value"
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
                    return await self._switch_profile(entry, profile, character)
            except (KeyError, AttributeError):
                continue
        # Pass 2: match name
        for entry in profiles:
            try:
                profile = self.store.get(entry["rid"])
                if profile.get("name", "").lower() == search:
                    return await self._switch_profile(entry, profile, character)
            except (KeyError, AttributeError):
                continue
        return CommandResult(
            success=False,
            notification=f"Profile not found: {profile_name}",
        )

    async def _switch_profile(self, entry, profile, character) -> CommandResult:
        profile_id = entry["rid"].split(".")[-1]
        await self.conn.send(
            f"call.core.char.{character}.ctrl.useProfile",
            {"profileId": profile_id, "safe": True},
        )
        return CommandResult(
            notification=f"Morphing into {profile.get('name', '?')}..."
        )

    async def handle_wa(self, content, character) -> CommandResult:
        """Handle whereat (wa) command -- show area population tree."""
        try:
            room_pointer = self.store.get(
                f"core.char.{character}.owned.inRoom"
            )["rid"]
        except KeyError:
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

    async def handle_laston(self, name_to_check, character) -> CommandResult:
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
        last_awake = datetime.fromtimestamp(
            char_data["lastAwake"] / 1000.0
        ).strftime("%Y-%m-%d %H:%M:%S")
        char_name = char_data.get("name", "?")
        if "surname" in char_data:
            char_name += f" {char_data['surname']}"
        return CommandResult(
            display_text=f"{char_name} was last online {last_awake}"
        )

    async def handle_look(self, content, character) -> CommandResult:
        if content is None:
            return self._look_room(character)
        return await self._look_character(content, character)
    
    async def handle_lookup(self, content, character) -> CommandResult:
        msg_id = await self.conn.send(f"core.char.{character}.lookupChars",
                             {"extended": True,
                              "name": content})
        self.conn.add_message_wait(
            msg_id,
            lambda _result: self._lookup_result(_result)
        )

    def _lookup_result(self, payload) -> CommandResult:
        output += f"{'Char:':<30}{'Gender':<10}{'Species:':<20}{'Last On:':<20}\n"
        for char in payload.get("chars",[]):
            #output lines
            surname_len = 29 - (len(char['name']) + len(char['surname']))
            output += f"{char['name']} {char['surname']}{' '*surname_len}{char['gender']:<10}{char['species']:<20}{char['lastAwake']}"
        return CommandResult(display_text=output)


    def _look_room(self, character: str) -> CommandResult:
        """Gather room data from the store and return it for display."""
        try:
            room_pointer = self.store.get(
                f"core.char.{character}.owned.inRoom"
            )["rid"]
            room_id = room_pointer.split(".")[2]
        except KeyError:
            return CommandResult(success=False, notification="Could not determine current room.")

        room_name = self.store.get_room_attribute(room_id, "name") or "Unknown Room"
        room_desc = self.store.get_room_attribute(room_id, "desc") or ""

        # Exits
        exits = []
        try:
            room_exits = self.store.get(room_pointer + ".exits._value")
            for e in room_exits:
                try:
                    exit_model = self.store.get(e["rid"])
                    keys = exit_model.get("keys", {}).get("data", [])
                    exits.append({
                        "name": exit_model.get("name", "?"),
                        "keys": ", ".join(keys),
                    })
                except KeyError:
                    continue
        except KeyError:
            pass

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

    async def _look_character(self, name_str: str, character: str) -> CommandResult:
        """Look at a character: send ctrl.look, then gather data on response."""
        try:
            target_id = parse_name(self.store, name_str.strip())
        except NameParseException as e:
            return CommandResult(success=False, notification=str(e))

        msg_id = await self.conn.look_at(target_id, character)
        self.conn.add_message_wait(
            msg_id,
            lambda _result, tid=target_id: self._on_look_result(tid),
        )
        return CommandResult(notification="Looking...")

    async def _on_look_result(self, char_id: str) -> None:
        """Called when the look_at response arrives. Publishes look data."""
        data = self._gather_character_data(char_id)
        await self.conn.event_bus.publish("look.result", data=data)

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

        return {
            "type": "character",
            "name": full_name,
            "species": species.capitalize() if species else "",
            "gender": gender.capitalize() if gender else "",
            "desc": desc,
            "about": about,
            "tags": tags,
        }
