"""Tests for context-aware tab completion."""

import pytest
import pytest_asyncio

from yreflow.protocol.events import EventBus
from yreflow.protocol.model_store import ModelStore
from yreflow.commands.completion import (
    CompletionType,
    detect_completion_context,
    resolve_names,
    resolve_exits,
    resolve_teleport_nodes,
)


# ---------------------------------------------------------------------------
# detect_completion_context tests
# ---------------------------------------------------------------------------

class TestDetectCompletionContext:
    """Test command-prefix detection and slot identification."""

    # --- Directed commands: name slot (before =) ---

    @pytest.mark.parametrize("text,expected_type", [
        ("w Jo",          CompletionType.LOCAL_ONLY),
        ("wh Jo",         CompletionType.LOCAL_ONLY),
        ("@Jo",           CompletionType.LOCAL_ONLY),
        ("address Jo",    CompletionType.LOCAL_ONLY),
        ("to Jo",         CompletionType.LOCAL_ONLY),
    ])
    def test_directed_name_slot_local_only(self, text, expected_type):
        ctx = detect_completion_context(text)
        assert ctx.completion_type == expected_type
        assert ctx.prose is False

    @pytest.mark.parametrize("text,expected_type", [
        ("p Jo",          CompletionType.AWAKE_WATCH_PREFERRED),
        ("m Jo",          CompletionType.AWAKE_WATCH_PREFERRED),
    ])
    def test_directed_name_slot_awake_watch(self, text, expected_type):
        ctx = detect_completion_context(text)
        assert ctx.completion_type == expected_type
        assert ctx.prose is False

    @pytest.mark.parametrize("text,expected_type", [
        ("mail send Jo",  CompletionType.WATCH_PREFERRED),
        ("mail s Jo",     CompletionType.WATCH_PREFERRED),
    ])
    def test_directed_name_slot_watch(self, text, expected_type):
        ctx = detect_completion_context(text)
        assert ctx.completion_type == expected_type
        assert ctx.prose is False

    # --- Directed commands: message slot (after =) ---

    def test_whisper_after_eq(self):
        ctx = detect_completion_context("w John=hey Tho")
        assert ctx.completion_type == CompletionType.LOCAL_PREFERRED
        assert ctx.prefix == "Tho"
        assert ctx.prose is True

    def test_page_after_eq(self):
        ctx = detect_completion_context("m John=hey Tho")
        assert ctx.completion_type == CompletionType.WATCH_PREFERRED
        assert ctx.prefix == "Tho"
        assert ctx.prose is True

    def test_address_after_eq(self):
        ctx = detect_completion_context("@John=hey Tho")
        assert ctx.completion_type == CompletionType.LOCAL_PREFERRED
        assert ctx.prefix == "Tho"
        assert ctx.prose is True

    # --- Undirected prose commands ---

    @pytest.mark.parametrize("text", [
        "say hello Tho",
        '"hello Tho',
        "\u201chello Tho",
        ":waves to Tho",
        "pose waves to Tho",
        ">ooc Tho",
        "ooc Tho",
    ])
    def test_prose_commands_local_preferred(self, text):
        ctx = detect_completion_context(text)
        assert ctx.completion_type == CompletionType.LOCAL_PREFERRED
        assert ctx.prefix == "Tho"
        assert ctx.prose is True

    # --- Undirected name-target commands ---

    @pytest.mark.parametrize("text,expected_type", [
        ("look Tho",      CompletionType.LOCAL_ONLY),
        ("l Tho",         CompletionType.LOCAL_ONLY),
        ("lead Tho",      CompletionType.LOCAL_ONLY),
        ("follow Tho",    CompletionType.LOCAL_ONLY),
        ("focus Tho",     CompletionType.LOCAL_ONLY),
        ("unfocus Tho",   CompletionType.LOCAL_ONLY),
    ])
    def test_name_commands_local_only(self, text, expected_type):
        ctx = detect_completion_context(text)
        assert ctx.completion_type == expected_type
        assert ctx.prefix == "Tho"
        assert ctx.prose is False

    @pytest.mark.parametrize("text,expected_type", [
        ("whois Tho",     CompletionType.WATCH_PREFERRED),
        ("wi Tho",        CompletionType.WATCH_PREFERRED),
        ("watch Tho",     CompletionType.WATCH_PREFERRED),
        ("unwatch Tho",   CompletionType.WATCH_PREFERRED),
        ("summon Tho",    CompletionType.WATCH_PREFERRED),
        ("join Tho",      CompletionType.WATCH_PREFERRED),
    ])
    def test_name_commands_watch_preferred(self, text, expected_type):
        ctx = detect_completion_context(text)
        assert ctx.completion_type == expected_type
        assert ctx.prefix == "Tho"
        assert ctx.prose is False

    # --- Prefix extraction ---

    def test_prefix_extraction_directed(self):
        ctx = detect_completion_context("w Thorn Ash")
        assert ctx.prefix == "Thorn Ash"

    def test_prefix_extraction_at_stripped(self):
        ctx = detect_completion_context("@Tho")
        assert ctx.prefix == "Tho"

    def test_prefix_extraction_look_multiword(self):
        ctx = detect_completion_context("look Thorn Ash")
        assert ctx.prefix == "Thorn Ash"

    def test_prefix_extraction_prose_last_word(self):
        ctx = detect_completion_context("say hello there Tho")
        assert ctx.prefix == "Tho"

    # --- Bare text (treated as say) ---

    def test_bare_text(self):
        ctx = detect_completion_context("hello Tho")
        assert ctx.completion_type == CompletionType.LOCAL_PREFERRED
        assert ctx.prefix == "Tho"
        assert ctx.prose is True

    # --- Edge cases ---

    def test_empty_input(self):
        ctx = detect_completion_context("")
        assert ctx.prefix == ""

    def test_wh_longer_prefix_not_shadowed_by_w(self):
        """'wh ' should match before 'w ' would match 'wh'."""
        ctx = detect_completion_context("wh Thorn")
        assert ctx.completion_type == CompletionType.LOCAL_ONLY
        assert ctx.prefix == "Thorn"


# ---------------------------------------------------------------------------
# resolve_names tests
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def completion_store():
    """ModelStore with room chars, watch list, and online-only chars."""
    store = ModelStore(event_bus=EventBus())

    # --- Characters ---
    # Room occupants: Alice Bloom, Bob Cedar
    for char_id, name, surname, awake in [
        ("alice01", "Alice", "Bloom", True),
        ("bob02", "Bob", "Cedar", True),
        ("carol03", "Carol", "Dune", True),    # watch list only
        ("dave04", "Dave", "Elm", True),        # online only
        ("eve05", "Eve", "Frost", False),       # asleep (in watch list)
        ("alice06", "Alice", "Stone", True),    # online only, same first name
    ]:
        await store.set(f"core.char.{char_id}", {
            "id": char_id,
            "name": name,
            "surname": surname,
            "awake": awake,
        })

    # --- Room setup: alice01 and bob02 are in the room ---
    room_id = "room01"
    await store.set(f"core.room.{room_id}", {"id": room_id, "name": "Test Room"})
    await store.set(f"core.room.{room_id}.chars", {
        "_value": [
            {"rid": "core.char.alice01.inroom"},
            {"rid": "core.char.bob02.inroom"},
        ]
    })

    # Set up character's inRoom pointer
    await store.set("core.char.alice01.owned", {
        "inRoom": {"rid": f"core.room.{room_id}"},
    })

    # --- Watch list: carol03 and eve05 ---
    player = "player01"
    await store.set(f"note.player.{player}.watches", {
        "w1": {"rid": f"note.player.{player}.watches.w1"},
        "w2": {"rid": f"note.player.{player}.watches.w2"},
    })
    await store.set(f"note.player.{player}.watches.w1", {
        "char": {"rid": "core.char.carol03.info"},
    })
    await store.set(f"note.player.{player}.watches.w2", {
        "char": {"rid": "core.char.eve05.info"},
    })

    return store


CHAR_PATH = "core.char.alice01"
PLAYER = "player01"


class TestResolveNames:

    def test_local_only_returns_room_chars(self, completion_store):
        results = resolve_names(
            completion_store, "", CompletionType.LOCAL_ONLY,
            CHAR_PATH, PLAYER, prose=False,
        )
        assert "Alice Bloom" in results
        assert "Bob Cedar" in results
        assert "Carol Dune" not in results
        assert "Dave Elm" not in results

    def test_local_preferred_room_first(self, completion_store):
        results = resolve_names(
            completion_store, "", CompletionType.LOCAL_PREFERRED,
            CHAR_PATH, PLAYER, prose=False,
        )
        # Room chars come first
        room_names = {"Alice Bloom", "Bob Cedar"}
        first_two = set(results[:2])
        assert first_two == room_names
        # Watch list and online chars also present
        assert "Carol Dune" in results
        assert "Dave Elm" in results

    def test_local_preferred_deduplication(self, completion_store):
        results = resolve_names(
            completion_store, "", CompletionType.LOCAL_PREFERRED,
            CHAR_PATH, PLAYER, prose=False,
        )
        # Alice Bloom should appear once (room), not again (online)
        assert results.count("Alice Bloom") == 1

    def test_awake_watch_preferred_excludes_sleeping(self, completion_store):
        results = resolve_names(
            completion_store, "", CompletionType.AWAKE_WATCH_PREFERRED,
            CHAR_PATH, PLAYER, prose=False,
        )
        # Eve is asleep and on watch list — should be excluded
        assert "Eve Frost" not in results
        # Carol is awake and on watch list — should be first
        assert results[0] == "Carol Dune"

    def test_watch_preferred_includes_sleeping(self, completion_store):
        results = resolve_names(
            completion_store, "", CompletionType.WATCH_PREFERRED,
            CHAR_PATH, PLAYER, prose=False,
        )
        # Eve is on watch list — should be included (watch_preferred doesn't filter awake)
        assert "Eve Frost" in results
        # Watch list chars come before online-only chars
        carol_idx = results.index("Carol Dune")
        dave_idx = results.index("Dave Elm")
        assert carol_idx < dave_idx

    def test_prefix_matching(self, completion_store):
        results = resolve_names(
            completion_store, "Ali", CompletionType.LOCAL_PREFERRED,
            CHAR_PATH, PLAYER, prose=False,
        )
        assert "Alice Bloom" in results
        assert "Alice Stone" in results
        assert "Bob Cedar" not in results

    def test_prefix_case_insensitive(self, completion_store):
        results = resolve_names(
            completion_store, "ali", CompletionType.LOCAL_ONLY,
            CHAR_PATH, PLAYER, prose=False,
        )
        assert "Alice Bloom" in results

    def test_prose_interleaves_firstname_fullname(self, completion_store):
        results = resolve_names(
            completion_store, "Ali", CompletionType.LOCAL_PREFERRED,
            CHAR_PATH, PLAYER, prose=True,
        )
        # Should be: Alice, Alice Bloom (room), Alice, Alice Stone (online)
        assert results[0] == "Alice"
        assert results[1] == "Alice Bloom"
        assert results[2] == "Alice"
        assert results[3] == "Alice Stone"

    def test_prose_no_duplicate_when_no_surname(self, completion_store):
        """If fullname == firstname (no surname), only list once."""
        # Add a character with no surname
        import asyncio
        asyncio.get_event_loop().run_until_complete(
            completion_store.set("core.char.zara07", {
                "id": "zara07", "name": "Zara", "surname": "", "awake": True,
            })
        )
        results = resolve_names(
            completion_store, "Zar", CompletionType.LOCAL_PREFERRED,
            CHAR_PATH, PLAYER, prose=True,
        )
        assert results.count("Zara") == 1

    def test_none_type_returns_empty(self, completion_store):
        results = resolve_names(
            completion_store, "Ali", CompletionType.NONE,
            CHAR_PATH, PLAYER, prose=False,
        )
        assert results == []

    def test_no_match_returns_empty(self, completion_store):
        results = resolve_names(
            completion_store, "Zzzzz", CompletionType.LOCAL_PREFERRED,
            CHAR_PATH, PLAYER, prose=False,
        )
        assert results == []


# ---------------------------------------------------------------------------
# detect_completion_context: go / teleport / tport
# ---------------------------------------------------------------------------

class TestDetectCompletionContextGoTeleport:

    @pytest.mark.parametrize("text", ["go mar", "go north"])
    def test_go_exits(self, text):
        ctx = detect_completion_context(text)
        assert ctx.completion_type == CompletionType.EXITS
        assert ctx.prose is False

    def test_go_prefix_extraction(self):
        ctx = detect_completion_context("go mar")
        assert ctx.prefix == "mar"

    @pytest.mark.parametrize("text,expected_prefix", [
        ("teleport hom", "hom"),
        ("tport hom", "hom"),
        ("t hom", "hom"),
    ])
    def test_teleport_nodes(self, text, expected_prefix):
        ctx = detect_completion_context(text)
        assert ctx.completion_type == CompletionType.TELEPORT_NODES
        assert ctx.prefix == expected_prefix
        assert ctx.prose is False


# ---------------------------------------------------------------------------
# resolve_exits tests
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def exit_store():
    """ModelStore with room exits."""
    store = ModelStore(event_bus=EventBus())

    room_id = "room01"
    await store.set(f"core.room.{room_id}", {"id": room_id, "name": "Test Room"})

    # Set up exits
    exit0_rid = f"core.room.{room_id}.exit.exit000"
    await store.set(exit0_rid, {
        "id": "exit000", "name": "Market Square",
        "keys": {"data": ["market", "north"]},
    })
    exit1_rid = f"core.room.{room_id}.exit.exit001"
    await store.set(exit1_rid, {
        "id": "exit001", "name": "Back Alley",
        "keys": {"data": ["alley", "south"]},
    })
    await store.set(f"core.room.{room_id}.exits", {
        "_value": [{"rid": exit0_rid}, {"rid": exit1_rid}]
    })

    # Character in this room
    await store.set("core.char.char01.owned", {
        "inRoom": {"rid": f"core.room.{room_id}"},
    })

    return store


class TestResolveExits:

    def test_all_exits_with_empty_prefix(self, exit_store):
        results = resolve_exits(exit_store, "", "core.char.char01")
        assert "Market Square" in results
        assert "Back Alley" in results

    def test_exit_name_prefix_match(self, exit_store):
        results = resolve_exits(exit_store, "Mar", "core.char.char01")
        assert "Market Square" in results
        assert "Back Alley" not in results

    def test_exit_key_prefix_match(self, exit_store):
        results = resolve_exits(exit_store, "nor", "core.char.char01")
        assert "north" in results
        assert "Market Square" not in results  # "Market" doesn't start with "nor"

    def test_case_insensitive(self, exit_store):
        results = resolve_exits(exit_store, "back", "core.char.char01")
        assert "Back Alley" in results

    def test_no_char_path_returns_empty(self, exit_store):
        results = resolve_exits(exit_store, "", None)
        assert results == []


# ---------------------------------------------------------------------------
# resolve_teleport_nodes tests
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def teleport_store():
    """ModelStore with character-specific and global teleport nodes."""
    store = ModelStore(event_bus=EventBus())

    # Character-specific nodes
    char_node_rid = "core.node.charnode01"
    await store.set(char_node_rid, {"id": "charnode01", "key": "home"})
    await store.set("core.char.char01.nodes", {
        "_value": [{"rid": char_node_rid}],
    })

    # Global nodes
    await store.set("core.node.global01", {"id": "global01", "key": "haven"})
    await store.set("core.node.global02", {"id": "global02", "key": "hub"})
    await store.set("core.nodes", {
        "_value": [{"rid": "core.node.global01"}, {"rid": "core.node.global02"}],
    })

    return store


class TestResolveTeleportNodes:

    def test_char_specific_nodes(self, teleport_store):
        results = resolve_teleport_nodes(teleport_store, "ho", "core.char.char01")
        assert "home" in results

    def test_global_nodes(self, teleport_store):
        results = resolve_teleport_nodes(teleport_store, "ha", "core.char.char01")
        assert "haven" in results

    def test_all_nodes_with_h_prefix(self, teleport_store):
        results = resolve_teleport_nodes(teleport_store, "h", "core.char.char01")
        assert "home" in results
        assert "haven" in results
        assert "hub" in results

    def test_char_nodes_before_global(self, teleport_store):
        """Character-specific nodes should appear before global nodes."""
        results = resolve_teleport_nodes(teleport_store, "h", "core.char.char01")
        home_idx = results.index("home")
        haven_idx = results.index("haven")
        assert home_idx < haven_idx

    def test_deduplication(self, teleport_store):
        """If a key appears in both char and global, only list once."""
        import asyncio
        loop = asyncio.get_event_loop()
        # Add "home" as a global node too
        loop.run_until_complete(
            teleport_store.set("core.node.global03", {"id": "global03", "key": "home"})
        )
        # Add it to the global nodes collection
        cur = teleport_store.get("core.nodes._value")
        cur.append({"rid": "core.node.global03"})
        results = resolve_teleport_nodes(teleport_store, "ho", "core.char.char01")
        assert results.count("home") == 1

    def test_no_char_path_still_returns_global(self, teleport_store):
        results = resolve_teleport_nodes(teleport_store, "h", None)
        assert "haven" in results
        assert "hub" in results
        assert "home" not in results  # char-specific only

    def test_no_match_returns_empty(self, teleport_store):
        results = resolve_teleport_nodes(teleport_store, "zzz", "core.char.char01")
        assert results == []
