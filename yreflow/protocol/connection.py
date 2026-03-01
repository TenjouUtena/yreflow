import json
import asyncio
import hmac
import hashlib
import base64
from datetime import datetime, timedelta

import websockets
from websockets.asyncio.client import connect

_PEPPER = b"TheStoryStartsHere"

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


class WolferyConnection:
    """WebSocket connection to Wolfery, extracted from Samples/Application.py.

    All UI coupling has been replaced with EventBus publishes.
    """

    def __init__(self, config: dict, store: ModelStore, event_bus: EventBus):
        self.config = config
        self.store = store
        self.event_bus = event_bus

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
        self.last_directed: str | None = None

        # Register model watches
        self.store.add_watch(r"core\.player.*", self._on_player_event)
        self.store.add_watch(r"core\.lookedat\.char\..*", self._on_looked_at)
        self.store.add_watch(r"core\.char\.\w+\.inroom", self._on_inroom_change)
        self.store.add_watch(r"core\.room\.\w+\.chars", self._on_inroom_change)
        self.store.add_watch(r"note\.player\.\w+\.watches", self._on_watches_change)
        self.store.add_watch(r"core\.chars\.awake", self._on_watches_change)
        self.store.add_watch(r"core\.player\.\w+\.ctrls\.remove", self._on_tabs_change)

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

    async def look_at(self, who: str, whoami: str):
        await self.send(f"subscribe.core.char.{who}.info")
        return await self.send(f"call.core.char.{whoami}.ctrl.look", {"charid": who})

    async def stop_look_at(self, whoami: str):
        return await self.send(f"call.core.char.{whoami}.ctrl.look", {"charid": whoami})

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
            one_hour_ago = datetime.now() - timedelta(hours=1)
            timestamp = int(one_hour_ago.timestamp() * 1000)
            for rid in payload:
                character = rid["rid"].split(".")[2]
                await self.event_bus.publish("character.tab.needed", character=character)
                f = await self.send(
                    "call.log.events.get",
                    {"charId": character, "startTime": timestamp},
                )
                self.add_message_wait(
                    f,
                    lambda e, ch=character: self._process_backlog(ch, e),
                )
        elif path.endswith("ctrls.add") and isinstance(payload, dict) and "rid" in payload:
            character = payload["rid"].split(".")[2]
            await self.event_bus.publish("character.tab.needed", character=character)

    async def _process_backlog(self, character: str, backlog) -> None:
        for e in backlog.get("events", []):
            await self._handle_output(e, character)

    async def _on_looked_at(self, path: str, payload) -> None:
        model_parts = path.split(".")
        for who_looked in payload:
            fname = self.store.get_character_attribute(who_looked, "name")
            sname = self.store.get_character_attribute(who_looked, "surname")
            myname = self.store.get_character_attribute(model_parts[3], "name")
            await self.event_bus.publish(
                "notification", text=f"{fname} {sname} looked at {myname}."
            )

    async def _on_inroom_change(self, path: str, payload) -> None:
        await self.event_bus.publish("room.changed")

    async def _on_watches_change(self, path: str, payload) -> None:
        await self.event_bus.publish("watches.changed")

    async def _on_tabs_change(self, path: str, payload) -> None:
        await self.event_bus.publish("characters.changed")

    # --- WebSocket connection ---

    async def connect(self) -> None:
        uri = "wss://api.wolfery.com/"
        headers = {}
        if self.auth_mode == "token" and self.token:
            headers["Cookie"] = f"wolfery-auth-token={self.token}"
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
                    result_payload = j["result"].get("payload", "")
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
                character = evt.split(".")[2]
                await self._handle_output(j["data"], character)
                handled = True

        if self.state == State.SUBSCRIBE:
            self.state = State.CON
            for s in self.default_subscriptions:
                await self.send(s)

    async def _handle_output(self, j: dict, character: str) -> None:
        frm = j.get("char", {"name": "", "id": ""})
        msg = j.get("msg", "")
        t = j.get("target", {"name": "", "id": ""})
        style = j["type"]
        output = {"frm": frm, "msg": msg, "t": t, "j": j}

        if style in ("summon", "join"):
            await self.event_bus.publish("notification", text="Summon/join received")
            return

        await self.event_bus.publish(
            "message.received", message=output, style=style, character=character
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
        await self.wsock.send(raw)
        await asyncio.sleep(0)
        return self.id

    def log_to_file(self, message: str) -> None:
        from ..config import get_log_dir

        log_dir = get_log_dir()
        log_dir.mkdir(parents=True, exist_ok=True)
        current_date = datetime.now().strftime("%Y-%m-%d")
        log_file = log_dir / f"{current_date}.log"
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(log_file, "a") as f:
            f.write(f"[{timestamp}] {message}\n")
