"""Shared fixtures and mock objects for yreflow test suite."""

import tomllib
from pathlib import Path

import pytest
import pytest_asyncio

from yreflow.protocol.events import EventBus
from yreflow.protocol.model_store import ModelStore
from yreflow.protocol.controlled_char import ControlledChar
from yreflow.protocol.realm import Realm
from yreflow.commands.handler import CommandHandler

DATA_DIR = Path(__file__).parent / "data"
FIXTURES_FILE = DATA_DIR / "store_fixtures.toml"


class MockConnection:
    """Stand-in for WolferyConnection that records all send() calls."""

    def __init__(self, event_bus, player="testplayer"):
        self.event_bus = event_bus
        self.player = player
        self.token = "fake-token"
        self.realm = Realm.from_key("wolfery")
        self.sent: list[tuple[str, dict | None]] = []
        self.directed_contacts: list[tuple[list, list, str]] = []
        self.message_waits: dict = {}

    async def send(self, method: str, params: dict | None = None) -> int:
        self.sent.append((method, params))
        return len(self.sent)

    def push_directed_contact(self, char_ids, names, prefix):
        self.directed_contacts.append((char_ids, names, prefix))

    def add_message_wait(self, msg_id, function):
        self.message_waits[msg_id] = function

    async def look_at(self, who, cc):
        return await self.send(f"subscribe.core.char.{who}.info")


def _load_fixtures() -> dict:
    with open(FIXTURES_FILE, "rb") as f:
        return tomllib.load(f)


@pytest.fixture
def event_bus():
    return EventBus()


@pytest_asyncio.fixture
async def store(event_bus):
    return ModelStore(event_bus=event_bus)


@pytest.fixture
def mock_conn(event_bus):
    return MockConnection(event_bus)


@pytest_asyncio.fixture
async def populated_store(store):
    """ModelStore pre-loaded with fictional character and room data."""
    fixtures = _load_fixtures()

    # Load characters into core.char.<id>
    for _key, char in fixtures["characters"].items():
        char_id = char["id"]
        await store.set(f"core.char.{char_id}", {
            "id": char_id,
            "name": char["name"],
            "surname": char["surname"],
            "awake": char["awake"],
            "gender": char["gender"],
            "species": char["species"],
            "status": char.get("status", ""),
        })
        if char.get("desc"):
            await store.set(f"core.char.{char_id}.owned", {
                "desc": char["desc"],
            })

    # Load room
    room = fixtures["room"]
    room_id = room["id"]
    await store.set(f"core.room.{room_id}", {
        "id": room_id,
        "name": room["name"],
        "desc": room["desc"],
    })

    # Set up room exits as RID references
    exit_values = []
    for i, ex in enumerate(room.get("exits", [])):
        exit_id = f"exit{i:03d}"
        exit_rid = f"core.room.{room_id}.exit.{exit_id}"
        exit_data = {
            "id": exit_id,
            "name": ex["name"],
            "keys": {"data": ex["keys"]},
            "targetRoom": ex["target_room"],
        }
        if ex.get("transparent"):
            # Transparent exit: target -> afar model -> awake chars
            afar_rid = f"core.room.{ex['target_room']}.afar"
            exit_data["target"] = {"rid": afar_rid}
            # Set up afar model with awake characters
            awake_rid = f"{afar_rid}.awake"
            await store.set(afar_rid, {
                "awake": {"rid": awake_rid},
            })
            # Pip and Moss are visible through the cafe exit
            await store.set(awake_rid, {
                "_value": [
                    {"rid": "core.char.ghi789jkl012"},
                    {"rid": "core.char.mno345pqr678"},
                ],
            })
        await store.set(exit_rid, exit_data)
        exit_values.append({"rid": exit_rid})
    await store.set(f"core.room.{room_id}.exits", {"_value": exit_values})

    # Load areas
    for _key, area in fixtures.get("areas", {}).items():
        area_id = area["id"]
        data = {"name": area["name"], "rules": area.get("rules", "")}
        if area.get("parent_id"):
            data["parent"] = {"rid": f"core.area.{area['parent_id']}"}
        await store.set(f"core.area.{area_id}", data)

    # Link room to its area
    room_model = store.get(f"core.room.{room_id}")
    room_model["area"] = {"rid": f"core.area.{room['area_id']}"}

    # Set up character's inRoom pointer
    thorn_id = fixtures["characters"]["thorn"]["id"]
    await store.set(f"core.char.{thorn_id}.owned", {
        "inRoom": {"rid": f"core.room.{room_id}"},
    })

    # Load puppet
    puppet = fixtures["puppet"]
    await store.set(
        f"core.char.{puppet['puppeteer_id']}.puppet.{puppet['char_id']}",
        {"id": puppet["char_id"], "name": puppet["name"], "surname": puppet["surname"]},
    )

    # Load room commands
    cmd_values = {}
    for _key, cmd in fixtures.get("room_cmds", {}).items():
        cmd_id = cmd["id"]
        cmd_rid = f"core.roomcmd.{cmd_id}"
        cmd_data = {
            "pattern": cmd["pattern"],
            "desc": cmd["desc"],
        }
        if "fields" in cmd:
            fields = {}
            for fname, fdef in cmd["fields"].items():
                field_entry = {"type": fdef["type"], "desc": fdef["desc"]}
                opts = {}
                if "min" in fdef:
                    opts["min"] = fdef["min"]
                if "in_room" in fdef:
                    opts["inRoom"] = fdef["in_room"]
                if "state" in fdef:
                    opts["state"] = fdef["state"]
                if opts:
                    field_entry["opts"] = opts
                fields[fname] = field_entry
            cmd_data["fields"] = fields
        await store.set(cmd_rid, {
            "cmd": {"data": cmd_data},
            "id": cmd_id,
            "priority": cmd.get("priority", 0),
        })
        cmd_values[cmd_id] = {"rid": cmd_rid}
    await store.set(f"core.room.{room_id}.cmds", cmd_values)

    return store


@pytest.fixture
def handler(mock_conn, populated_store):
    return CommandHandler(mock_conn, populated_store)


@pytest.fixture
def cc_thorn():
    """Regular character: Thorn Ashvale."""
    return ControlledChar(char_id="abc123def456")


@pytest.fixture
def cc_puppet():
    """Puppet: Spark, controlled by Thorn."""
    return ControlledChar(char_id="pup567tuv", puppeteer_id="abc123def456")
