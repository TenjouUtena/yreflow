"""Command parsing and dispatch, extracted from Samples/CommandHandler.py.

UI coupling removed -- handlers return CommandResult instead of calling self.ui.*.
Singleton Application() replaced with injected connection/store references.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from .name_resolver import parse_name, NameParseException

if TYPE_CHECKING:
    from ..protocol.connection import WolferyConnection
    from ..protocol.model_store import ModelStore


@dataclass
class CommandResult:
    success: bool = True
    notification: str | None = None
    exit_app: bool = False


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
        return CommandResult(notification="Character released", exit_app=True)

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
