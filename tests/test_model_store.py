"""Tests for ModelStore get/set/pop/watch operations."""

import pytest

from yreflow.protocol.model_store import ModelStore
from yreflow.protocol.events import EventBus


@pytest.mark.asyncio
class TestBasicOperations:
    async def test_set_and_get(self):
        store = ModelStore()
        await store.set("a.b", {"x": 1})
        assert store.get("a.b.x") == 1

    async def test_get_missing_raises_keyerror(self):
        store = ModelStore()
        with pytest.raises(KeyError):
            store.get("nonexistent.path")

    async def test_set_nested_creates_hierarchy(self):
        store = ModelStore()
        await store.set("a.b.c", {"val": 42})
        assert store.get("a.b.c.val") == 42

    async def test_set_merges_existing(self):
        store = ModelStore()
        await store.set("a", {"x": 1})
        await store.set("a", {"y": 2})
        assert store.get("a.x") == 1
        assert store.get("a.y") == 2

    async def test_set_collection(self):
        store = ModelStore()
        await store.set("items", [{"rid": "a"}, {"rid": "b"}], collection=True)
        assert store.get("items._value") == [{"rid": "a"}, {"rid": "b"}]

    async def test_set_delete_action(self):
        store = ModelStore()
        await store.set("a", {"x": 1, "y": 2})
        await store.set("a", {"x": {"action": "delete"}})
        with pytest.raises(KeyError):
            store.get("a.x")
        assert store.get("a.y") == 2

    async def test_pop_removes_key(self):
        store = ModelStore()
        await store.set("a.b", {"x": 1})
        await store.pop("a.b")
        with pytest.raises(KeyError):
            store.get("a.b")

    async def test_pop_missing_no_error(self):
        store = ModelStore()
        await store.set("a", {"x": 1})
        await store.pop("a.nonexistent")  # should not raise


@pytest.mark.asyncio
class TestListOperations:
    async def test_list_add(self):
        store = ModelStore()
        await store.set("items", [{"rid": "a"}], collection=True)
        await store.list_operation("items.add", 1, {"rid": "b"})
        assert store.get("items._value") == [{"rid": "a"}, {"rid": "b"}]

    async def test_list_remove(self):
        store = ModelStore()
        await store.set("items", [{"rid": "a"}, {"rid": "b"}], collection=True)
        await store.list_operation("items.remove", 0)
        assert store.get("items._value") == [{"rid": "b"}]


@pytest.mark.asyncio
class TestWatches:
    async def test_watch_fires_on_matching_set(self):
        bus = EventBus()
        store = ModelStore(event_bus=bus)
        fired = []

        async def watcher(path, payload):
            fired.append((path, payload))

        store.add_watch(r"core\.char\..*", watcher)
        await store.set("core.char.alice", {"name": "Alice"})

        assert len(fired) == 1
        assert fired[0][0] == "core.char.alice"

    async def test_watch_no_fire_on_mismatch(self):
        bus = EventBus()
        store = ModelStore(event_bus=bus)
        fired = []

        async def watcher(path, payload):
            fired.append(path)

        store.add_watch(r"core\.room\..*", watcher)
        await store.set("core.char.alice", {"name": "Alice"})

        assert len(fired) == 0

    async def test_remove_watch(self):
        bus = EventBus()
        store = ModelStore(event_bus=bus)
        fired = []

        async def watcher(path, payload):
            fired.append(path)

        store.add_watch(r".*", watcher)
        store.remove_watch(watcher)
        await store.set("anything", {"x": 1})

        assert len(fired) == 0


@pytest.mark.asyncio
class TestHelpers:
    async def test_get_character_attribute_direct(self):
        store = ModelStore()
        await store.set("core.char.abc", {"name": "Thorn"})
        assert store.get_character_attribute("abc", "name") == "Thorn"

    async def test_get_character_attribute_subpath(self):
        store = ModelStore()
        await store.set("core.char.abc.owned", {"desc": "A wolf."})
        assert store.get_character_attribute("abc", "desc") == "A wolf."

    async def test_get_character_attribute_default(self):
        store = ModelStore()
        await store.set("core.char.abc", {"name": "Thorn"})
        assert store.get_character_attribute("abc", "missing", "fallback") == "fallback"

    async def test_get_room_rid(self):
        store = ModelStore()
        await store.set("core.char.abc.owned", {"inRoom": {"rid": "core.room.r1"}})
        assert store.get_room_rid("core.char.abc") == "core.room.r1"

    async def test_get_room_rid_missing(self):
        store = ModelStore()
        await store.set("core.char.abc", {"name": "Thorn"})
        assert store.get_room_rid("core.char.abc") is None

    async def test_get_room_chars(self):
        store = ModelStore()
        await store.set("core.room.r1.chars", {"_value": [{"rid": "core.char.a"}]})
        result = store.get_room_chars("core.room.r1")
        assert result == [{"rid": "core.char.a"}]

    async def test_get_room_chars_empty(self):
        store = ModelStore()
        result = store.get_room_chars("core.room.missing")
        assert result == []

    async def test_get_room_exits(self):
        store = ModelStore()
        await store.set("core.room.r1.exits", {"_value": [{"rid": "exit1"}]})
        result = store.get_room_exits("core.room.r1")
        assert result == [{"rid": "exit1"}]

    async def test_get_room_attribute(self):
        store = ModelStore()
        await store.set("core.room.r1", {"name": "Tavern"})
        assert store.get_room_attribute("r1", "name") == "Tavern"
