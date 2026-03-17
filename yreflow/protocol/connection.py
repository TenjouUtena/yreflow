import json
import asyncio
import hmac
import hashlib
import base64
from dataclasses import dataclass, field
from datetime import datetime, timedelta

import websockets
from websockets.asyncio.client import connect

_PEPPER = b"TheStoryStartsHere"
_MAX_DIRECTED = 20
_DIRECTED_PREFIX = {"whisper": "w", "message": "m", "address": "@"}


@dataclass
class DirectedContact:
    """A directed message recipient (one or more characters)."""
    char_ids: list[str]
    names: list[str]       # full display names, same order as char_ids
    prefix: str            # "w", "m", or "@"

_DEFAULT_SUBSCRIPTIONS = [
    "subscribe.core.info",
    "subscribe.tag.info",
    "subscribe.mail.info",
    "subscribe.note.info",
    "subscribe.report.info",
    "subscribe.support.info",
    "subscribe.client.web.info",
    "subscribe.core.nodes",
    "call.core.getPlayer",
    "call.core.getRoles",
    "subscribe.tag.tags",
    "subscribe.core.chars.awake",
]

from .state import State
from .model_store import ModelStore
from .events import EventBus
from .controlled_char import ControlledChar
from .realm import Realm, DEFAULT_REALM_KEY
from ..config import load_last_seen, save_last_seen


class WolferyConnection:
    """WebSocket connection to Wolfery, extracted from Samples/Application.py.

    All UI coupling has been replaced with EventBus publishes.
    """

    def __init__(self, config: dict, store: ModelStore, event_bus: EventBus,
                 realm: Realm | None = None):
        self.config = config
        self.store = store
        self.event_bus = event_bus
        self.realm = realm or Realm.from_key(
            config.get("realm", DEFAULT_REALM_KEY)
        )

        self.token: str | None = config.get("token")
        self.default_subscriptions: list[str] = _DEFAULT_SUBSCRIPTIONS
        self.auth_mode: str = "token" if self.token else "password"
        self.credentials: dict | None = None

        self.wsock = None
        self.state = State.NEW
        self.id = 0
        self.message_waits: dict = {}
        self.player: str | None = None
        self.subscribe_watches = False
        self.directed_contacts: list[DirectedContact] = []
        self.ctrl_chars: dict[str, ControlledChar] = {}
        self.last_seen: dict[str, int] = load_last_seen()

        # Register model watches
        self.store.add_watch(r"core\.player.*", self._on_player_event)
        self.store.add_watch(r"core\.lookedat\.char\..*", self._on_looked_at)
        self.store.add_watch(r"core\.char\.\w+\.inroom", self._on_inroom_change)
        self.store.add_watch(r"core\.room\.\w+\.chars", self._on_inroom_change)
        self.store.add_watch(r"core\.room\.\w+\.exits", self._on_inroom_change)
        self.store.add_watch(r"note\.player\.\w+\.watches", self._on_watches_change)
        self.store.add_watch(r"core\.chars\.awake", self._on_watches_change)
        self.store.add_watch(r"core\.player\.\w+\.ctrls\.remove", self._on_tabs_change)
        self.store.add_watch(r"core\.player\.\w+\.controlLost", self._on_control_lost)

    def set_credentials(self, username: str, password: str) -> None:
        """Set username/password for password-based auth."""
        self.auth_mode = "password"
        self.credentials = {
            "name": username,
            "hash": self._compute_hash(password),
        }

    @staticmethod
    def _compute_hash(password: str) -> str:
        """HMAC-SHA256 of password with public pepper, base64-encoded."""
        return base64.b64encode(
            hmac.new(_PEPPER, password.strip().encode("utf-8"), hashlib.sha256).digest()
        ).decode("ascii")

    def add_message_wait(self, msg_id: int, function) -> None:
        self.message_waits[msg_id] = {"function": function}

    @staticmethod
    def _parse_ctrl_rid(rid: str) -> ControlledChar:
        """Parse a ctrls RID into a ControlledChar.

        Regular char RID: core.char.<charId>
        Puppet RID:       core.char.<puppeteerId>.puppet.<puppetId>.ctrl
        """
        parts = rid.split(".")
        if ".puppet." in rid and len(parts) >= 5:
            puppeteer_id = parts[2]
            puppet_id = parts[4]
            return ControlledChar(char_id=puppet_id, puppeteer_id=puppeteer_id)
        return ControlledChar(char_id=parts[2])

    def get_controlled_char(self, ctrl_id: str) -> ControlledChar | None:
        """Look up a ControlledChar by its ctrl_id."""
        return self.ctrl_chars.get(ctrl_id)

    def _char_id_to_ctrl_id(self, char_id: str) -> str:
        """Map a raw charId to its ctrl_id. Falls back to charId if not found."""
        for cc in self.ctrl_chars.values():
            if cc.char_id == char_id:
                return cc.ctrl_id
        return char_id

    async def look_at(self, who: str, cc: ControlledChar):
        await self.send(f"subscribe.core.char.{who}.info")
        return await self.send(f"call.{cc.ctrl_path}.look", {"charid": who})

    async def stop_look_at(self, cc: ControlledChar):
        return await self.send(f"call.{cc.ctrl_path}.look", {"charid": cc.char_id})

    def push_directed_contact(
        self, char_ids: list[str], names: list[str], prefix: str
    ) -> None:
        """Add/promote a contact to the front of directed_contacts (deduplicated)."""
        id_set = set(char_ids)
        self.directed_contacts = [
            c for c in self.directed_contacts if set(c.char_ids) != id_set
        ]
        self.directed_contacts.insert(0, DirectedContact(char_ids, names, prefix))
        if len(self.directed_contacts) > _MAX_DIRECTED:
            self.directed_contacts.pop()

    async def _on_login_success(self, result) -> None:
        """Called when auth.auth.login succeeds — proceed to getUser."""
        self.state = State.AUTH
        await self.send("call.auth.getUser")

    # --- Model watches (replace self.ui.* calls) ---

    async def _on_player_event(self, path: str, payload) -> None:
        if self.player and not self.subscribe_watches:
            await self.send(f"subscribe.note.player.{self.player}.watches")
            self.subscribe_watches = True

        if path.endswith("ctrls"):
            one_hour_ago = int((datetime.now() - timedelta(hours=1)).timestamp() * 1000)
            for rid in payload:
                cc = self._parse_ctrl_rid(rid["rid"])
                self.ctrl_chars[cc.ctrl_id] = cc
                await self.event_bus.publish("character.tab.needed", character=cc.ctrl_id)
                await self.send(f"subscribe.{cc.char_path}.nodes")
                saved = self.last_seen.get(cc.ctrl_id)
                timestamp = max(saved, one_hour_ago) if saved else one_hour_ago
                log_params = {"charId": cc.char_id, "startTime": timestamp}
                if cc.is_puppet:
                    log_params["puppeteerId"] = cc.puppeteer_id
                f = await self.send("call.log.events.get", log_params)
                self.add_message_wait(
                    f,
                    lambda e, cid=cc.ctrl_id: self._process_backlog(cid, e),
                )
        elif path.endswith("ctrls.add") and isinstance(payload, dict) and "rid" in payload:
            cc = self._parse_ctrl_rid(payload["rid"])
            self.ctrl_chars[cc.ctrl_id] = cc
            await self.event_bus.publish("character.tab.needed", character=cc.ctrl_id)
            await self.send(f"subscribe.{cc.char_path}.nodes")

    async def _process_backlog(self, character: str, backlog) -> None:
        for e in backlog.get("events", []):
            await self._handle_output(e, character)

    async def _on_looked_at(self, path: str, payload) -> None:
        model_parts = path.split(".")
        character = model_parts[3]
        ctrl_id = self._char_id_to_ctrl_id(character)
        for who_looked in payload:
            fname = self.store.get_character_attribute(who_looked, "name")
            sname = self.store.get_character_attribute(who_looked, "surname")
            myname = self.store.get_character_attribute(character, "name")
            await self.event_bus.publish(
                "notification",
                text=f"{fname} {sname} looked at {myname}.",
                character=ctrl_id,
            )

    async def _on_inroom_change(self, path: str, payload) -> None:
        await self.event_bus.publish("room.changed")

    async def _on_watches_change(self, path: str, payload) -> None:
        await self.event_bus.publish("watches.changed")

    async def _on_control_lost(self, path: str, payload) -> None:
        """Handle controlLost player event (another player took over a puppet)."""
        puppet_name = ""
        if isinstance(payload, dict):
            puppet = payload.get("puppet", {})
            puppet_name = puppet.get("name", "")
            if puppet.get("surname"):
                puppet_name += f" {puppet['surname']}"
        text = f"Control of {puppet_name} lost." if puppet_name else "Puppet control lost."
        await self.event_bus.publish("notification", text=text)

    async def _on_tabs_change(self, path: str, payload) -> None:
        # Clean up ctrl_chars for removed characters
        if isinstance(payload, dict) and "rid" in payload:
            removed = self._parse_ctrl_rid(payload["rid"])
            self.ctrl_chars.pop(removed.ctrl_id, None)
        await self.event_bus.publish("characters.changed")

    # --- WebSocket connection ---

    async def connect(self) -> None:
        uri = self.realm.ws_url
        headers = {}
        if self.auth_mode == "token" and self.token:
            headers["Cookie"] = f"{self.realm.cookie_name}={self.token}"
        try:
            async with connect(
                uri,
                additional_headers=headers,
            ) as wsock:
                await self._on_open(wsock)
                await self._consumer_handler(wsock)
        except TimeoutError:
            await self.event_bus.publish("connection.failed")
        except websockets.exceptions.ConnectionClosedError:
            pass
        finally:
            await self._on_close()

    async def _on_open(self, ws) -> None:
        self.wsock = ws
        self.state = State.AUTH
        self.log_to_file("CONNECTION OPENED")
        await self.send("version", {"protocol": "1.2.3"})

    async def _consumer_handler(self, websocket) -> None:
        async for message in websocket:
            try:
                await self._on_message(message)
            except websockets.exceptions.ConnectionClosedError:
                break

    async def _on_close(self) -> None:
        self.state = State.NEW
        self.wsock = None
        if self.last_seen:
            save_last_seen(self.last_seen)
        await self.event_bus.publish("connection.closed")
        self.log_to_file("CONNECTION CLOSED.")
        

    async def _on_message(self, message: str) -> None:
        await self.event_bus.publish("raw.message", text=message)
        self.log_to_file(f"INCOMING: {message}")

        try:
            j = json.loads(message)
        except json.JSONDecodeError as e:
            self.log_to_file(f"JSON Decode Error: {e}")
            return

        if "error" in j:
            msg_id = j.get("id")
            if msg_id in self.message_waits:
                self.message_waits.pop(msg_id)
            if self.state == State.LOGIN:
                error_msg = j["error"].get("message", "Authentication failed")
                await self.event_bus.publish("auth.failed", error=error_msg)
                if self.wsock:
                    await self.wsock.close()
                return
            if self.state == State.AUTH and self.auth_mode == "token":
                await self.event_bus.publish("auth.token_expired")
                if self.wsock:
                    await self.wsock.close()
                return
            await self.event_bus.publish("protocol.error", data=j)

        if "result" in j:
            # Handle message waits
            found = None
            for i in self.message_waits:
                if i == j["id"]:
                    result_payload = j["result"].get("payload", j["result"])
                    await self.message_waits[i]["function"](result_payload)
                    found = i
            if found:
                self.message_waits.pop(found)

            if "rid" in j["result"] and self.state == State.AUTH:
                self.state = State.SUBSCRIBE
            if "rid" in j["result"] and "player" in j["result"]["rid"]:
                self.player = j["result"]["rid"].split(".")[2]
            if "protocol" in j["result"] and self.state == State.AUTH:
                if self.auth_mode == "password" and self.credentials:
                    self.state = State.LOGIN
                    msg_id = await self.send("auth.auth.login", self.credentials)
                    self.add_message_wait(msg_id, self._on_login_success)
                else:
                    await self.send("call.auth.getUser")
            if "models" in j["result"]:
                for m in j["result"]["models"]:
                    await self.store.set(m, j["result"]["models"][m])
            if "collections" in j["result"]:
                for c in j["result"]["collections"]:
                    await self.store.set(
                        c, j["result"]["collections"][c], collection=True
                    )

        if "event" in j:
            evt = j["event"]
            handled = False

            if evt.split(".")[-1] in ("add", "remove"):
                if "models" in j["data"]:
                    for m in j["data"]["models"]:
                        await self.store.set(m, j["data"]["models"][m])
                if "collections" in j["data"]:
                    for c in j["data"]["collections"]:
                        await self.store.set(
                            c, j["data"]["collections"][c], collection=True
                        )
                index = j["data"]["idx"]
                value = j["data"].get("value", "")
                await self.store.list_operation(evt, index, value)
                handled = True

            if evt.split(".")[-1] == "delete":
                await self.store.pop(".".join(evt.split(".")[:-1]))
                handled = True

            if evt.split(".")[-1] == "change":
                if "models" in j["data"]:
                    for m in j["data"]["models"]:
                        await self.store.set(m, j["data"]["models"][m])
                if "collections" in j["data"]:
                    for c in j["data"]["collections"]:
                        await self.store.set(
                            c, j["data"]["collections"][c], collection=True
                        )
                await self.store.set(
                    ".".join(evt.split(".")[:-1]), j["data"]["values"]
                )
                handled = True

            if evt.endswith("ctrl.out"):
                # Parse the event path to extract ctrl_id
                # Regular: core.char.<id>.ctrl.out
                # Puppet:  core.char.<puppeteerId>.puppet.<puppetId>.ctrl.out
                ctrl_rid = evt.removesuffix(".out")
                cc = self._parse_ctrl_rid(ctrl_rid)
                await self._handle_output(j["data"], cc.ctrl_id)
                handled = True

        if self.state == State.SUBSCRIBE:
            self.state = State.CON
            await self.event_bus.publish("connection.established")
            for s in self.default_subscriptions:
                await self.send(s)

    @staticmethod
    def _format_roll(j: dict) -> str:
        """Build Rich-markup string from a roll event's result/total."""
        result = j.get("result", [])
        total = j.get("total", 0)
        formula_parts: list[str] = []
        detail_parts: list[str] = []

        for i, entry in enumerate(result):
            op = entry.get("op", "+")
            op_prefix = op if i > 0 else ""

            if entry["type"] == "std":
                count = entry["count"]
                sides = entry["sides"]
                dice = entry["dice"]
                formula_parts.append(f"{op_prefix}{count}d{sides}")
                dice_strs = [f"d{sides}·{v}" for v in dice]
                inner = " + ".join(dice_strs)
                if count > 1:
                    inner = f"({inner})"
                if i > 0:
                    detail_parts.append(f" {op} {inner}")
                else:
                    detail_parts.append(inner)
            elif entry["type"] == "mod":
                value = entry["value"]
                formula_parts.append(f"{op_prefix}{value}")
                if i > 0:
                    detail_parts.append(f" {op} {value}")
                else:
                    detail_parts.append(str(value))

        formula = "".join(formula_parts)
        detail = "".join(detail_parts)
        return f"rolls {formula}: {total} [dim]{detail}[/dim]"

    async def _handle_output(self, j: dict, ctrl_id: str) -> None:
        ts = j.get("time")
        if isinstance(ts, (int, float)):
            ts = int(ts)
            prev = self.last_seen.get(ctrl_id, 0)
            if ts > prev:
                self.last_seen[ctrl_id] = ts

        frm = j.get("char", {"name": "", "id": ""})
        msg = j.get("msg", "")
        t = j.get("target", {"name": "", "id": ""})
        style = j["type"]

        if style == "roll":
            msg = self._format_roll(j)

        output = {"frm": frm, "msg": msg, "t": t, "j": j}

        if style in ("summon", "join"):
            sender = (
                frm.get("name", "") + " " + frm.get("surname", "")
            ).strip() or "Someone"
            target_name = (
                t.get("name", "") + " " + t.get("surname", "")
            ).strip() or "someone"
            cc = self.ctrl_chars.get(ctrl_id)
            char_id = cc.char_id if cc else ctrl_id
            if frm.get("id") == char_id:
                text = f"You tried to {style} {target_name}."
            else:
                text = f"{sender} wants to {style} {target_name}."
            await self.event_bus.publish(
                "notification", text=text, character=ctrl_id
            )
            return

        if style in ("follow", "stopFollow", "stopLead"):
            sender = (
                frm.get("name", "") + " " + frm.get("surname", "")
            ).strip() or "Someone"
            target_name = (
                t.get("name", "") + " " + t.get("surname", "")
            ).strip() or "someone"
            cc = self.ctrl_chars.get(ctrl_id)
            char_id = cc.char_id if cc else ctrl_id
            if style == "follow":
                if frm.get("id") == char_id:
                    text = f"You are now following {target_name}."
                elif t.get("id") == char_id:
                    text = f"{sender} is now following you."
                else:
                    text = f"{sender} is now following {target_name}."
            elif style == "stopFollow":
                if frm.get("id") == char_id:
                    text = f"You stopped following {target_name}."
                elif t.get("id") == char_id:
                    text = f"{sender} stopped following you."
                else:
                    text = f"{sender} stopped following {target_name}."
            else:  # stopLead
                if frm.get("id") == char_id:
                    text = f"You stopped leading {target_name}."
                elif t.get("id") == char_id:
                    text = f"{sender} stopped leading you."
                else:
                    text = f"{sender} stopped leading {target_name}."
            await self.event_bus.publish(
                "notification", text=text, character=ctrl_id
            )
            return

        # Track incoming directed messages from other characters
        cc = self.ctrl_chars.get(ctrl_id)
        char_id = cc.char_id if cc else ctrl_id
        if style in _DIRECTED_PREFIX and frm.get("id") != char_id:
            sender_id = frm.get("id", "")
            sender_name = (
                frm.get("name", "") + " " + frm.get("surname", "")
            ).strip()
            if sender_id and sender_name:
                self.push_directed_contact(
                    [sender_id], [sender_name], _DIRECTED_PREFIX[style]
                )

        await self.event_bus.publish_interceptable(
            "message.received", message=output, style=style, character=ctrl_id
        )

    async def send(self, method: str = "", params: dict | None = None) -> int:
        if self.wsock is None:
            return 0
        self.id += 1
        msg = {"id": self.id, "method": method}
        if params:
            msg["params"] = params
        raw = json.dumps(msg)
        self.log_to_file(f"OUTGOING: {raw}")
        try:
            await self.wsock.send(raw)
        except websockets.exceptions.ConnectionClosedError:
            self.log_to_file("SEND FAILED: connection already closed")
            return 0
        await asyncio.sleep(0)
        return self.id

    def log_to_file(self, message: str) -> None:
        from ..config import get_log_dir

        log_dir = get_log_dir()
        log_dir.mkdir(parents=True, exist_ok=True)
        current_date = datetime.now().strftime("%Y-%m-%d")
        log_file = log_dir / f"{current_date}.log"
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(f"[{timestamp}] {message}\n")
