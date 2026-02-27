import re
from typing import Any


class ModelStore:
    """Hierarchical data model store with dot-notation path access.

    Extracted from Samples/Application.py. Stores the Resgate model tree
    and fires callbacks on the event bus when models change.
    """

    def __init__(self, event_bus=None):
        self.models: dict = {}
        self._event_watches: list[dict] = []
        self.event_bus = event_bus

    def add_watch(self, pattern: str, callback) -> None:
        self._event_watches.append({"id": pattern, "function": callback})

    def get(self, path: str) -> Any:
        hier = path.split(".")
        node = self.models
        for h in hier:
            node = node[h]
        return node

    async def set(self, path: str, payload: dict, collection: bool = False) -> None:
        hier = path.split(".")
        node = self.models
        for h in hier:
            if h not in node:
                node[h] = {}
            node = node[h]

        if collection:
            node["_value"] = payload
        else:
            actioned = False
            for k in payload:
                if isinstance(payload[k], dict) and "action" in payload[k]:
                    if payload[k]["action"] == "delete":
                        try:
                            del node[k]
                        except KeyError:
                            pass
                        actioned = True
            if not actioned:
                node |= payload

        await self._fire_watches(path, payload)

    async def pop(self, path: str) -> None:
        hier = path.split(".")[:-1]
        key_to_rem = path.split(".")[-1]
        node = self.models
        for h in hier:
            if h not in node:
                node[h] = {}
            node = node[h]
        try:
            del node[key_to_rem]
        except KeyError:
            pass
        await self._fire_watches(path, {})

    async def list_operation(self, path: str, index: int, value: Any = "") -> None:
        key = ".".join(path.split(".")[:-1])
        command = path.split(".")[-1]
        try:
            _value = self.get(key + "._value")
        except KeyError:
            await self.set(key, {"_value": []})
            _value = self.get(key + "._value")

        if command == "add":
            _value.insert(index, value)
        elif command == "remove":
            try:
                _value.pop(index)
            except IndexError:
                pass

        await self._fire_watches(path, value)

    def get_character_attribute(self, character: str, attribute: str, default: Any = "") -> Any:
        try:
            return self.get(f"core.char.{character}.{attribute}")
        except (KeyError, AttributeError):
            pass
        for v in ("inroom", "ctrls", "details", "info", "owned"):
            try:
                return self.get(f"core.char.{character}.{v}.{attribute}")
            except Exception:
                continue
        return default

    def get_room_attribute(self, room: str, attribute: str, default: Any = "") -> Any:
        try:
            return self.get(f"core.room.{room}.{attribute}")
        except (KeyError, AttributeError):
            pass
        for v in ("details", "info"):
            try:
                return self.get(f"core.room.{room}.{v}.{attribute}")
            except Exception:
                continue
        return default

    async def _fire_watches(self, path: str, payload: Any) -> None:
        for w in self._event_watches:
            if re.match(w["id"], path):
                await w["function"](path, payload)
