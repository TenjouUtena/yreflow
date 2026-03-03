"""Store browser screen for debugging the model store."""

from __future__ import annotations

import json
from typing import Any

from rich.markup import escape
from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import ModalScreen
from textual.widgets import Static, Button, Tree, RichLog
from textual.widgets.tree import TreeNode
from textual.containers import Horizontal, Vertical

from ...protocol.model_store import ModelStore


def _preview(value: Any, max_len: int = 50) -> str:
    """Short human-readable preview of a value for the tree label."""
    if isinstance(value, dict):
        return f"{{…}} {len(value)} key{'s' if len(value) != 1 else ''}"
    if isinstance(value, list):
        return f"[…] {len(value)} item{'s' if len(value) != 1 else ''}"
    s = repr(value)
    return s if len(s) <= max_len else s[:max_len] + "…"


def _build_subtree(parent: TreeNode, data: dict, path: str) -> None:
    """Recursively populate *parent* from *data*."""
    for key in sorted(data.keys()):
        value = data[key]
        child_path = f"{path}.{key}" if path else key
        safe_key = escape(str(key))
        if isinstance(value, dict):
            label = f"[bold]{safe_key}[/bold]  [dim]{escape(_preview(value))}[/dim]"
            child = parent.add(label, data={"path": child_path, "value": value})
            if value:
                _build_subtree(child, value, child_path)
        else:
            label = f"[bold]{safe_key}[/bold]: [dim]{escape(_preview(value))}[/dim]"
            parent.add_leaf(label, data={"path": child_path, "value": value})


class StoreBrowserScreen(ModalScreen):
    """Modal screen for browsing the live model store contents."""

    DEFAULT_CSS = """
    StoreBrowserScreen {
        align: center middle;
    }
    #browser-container {
        width: 95%;
        height: 90%;
        background: $panel;
        border: solid $accent;
        padding: 1 2;
    }
    #browser-title {
        text-style: bold;
        text-align: center;
        width: 100%;
        margin-bottom: 1;
    }
    #browser-body {
        height: 1fr;
    }
    #store-tree {
        width: 55%;
        height: 1fr;
        border: solid $surface-lighten-1;
        margin-right: 1;
    }
    #detail-panel {
        width: 1fr;
        height: 1fr;
    }
    #detail-path {
        color: $accent;
        text-style: bold;
        width: 100%;
        padding: 0 1;
        background: $surface-lighten-1;
        margin-bottom: 1;
        height: 1;
    }
    #detail-value {
        height: 1fr;
        border: solid $surface-lighten-1;
    }
    #btn-row {
        height: 3;
        margin-top: 1;
        align: right middle;
    }
    #refresh-btn {
        margin-right: 1;
    }
    """

    BINDINGS = [
        Binding("escape", "close_screen", "Close"),
        Binding("r", "refresh_store", "Refresh"),
    ]

    def __init__(self, store: ModelStore, **kwargs) -> None:
        super().__init__(**kwargs)
        self.store = store

    def compose(self) -> ComposeResult:
        with Vertical(id="browser-container"):
            yield Static("Store Browser", id="browser-title")
            with Horizontal(id="browser-body"):
                yield Tree("store", id="store-tree")
                with Vertical(id="detail-panel"):
                    yield Static(
                        "[dim](select a node)[/dim]",
                        id="detail-path",
                        markup=True,
                    )
                    yield RichLog(id="detail-value", markup=False, highlight=True)
            with Horizontal(id="btn-row"):
                yield Button("Refresh [dim](r)[/dim]", id="refresh-btn", variant="default")
                yield Button("Close [dim](Esc)[/dim]", id="close-btn", variant="default")

    def on_mount(self) -> None:
        self._populate_tree()

    def _populate_tree(self) -> None:
        tree = self.query_one("#store-tree", Tree)
        tree.clear()
        root = tree.root
        _build_subtree(root, self.store.models, "")
        root.expand()
        # Reset detail panel
        self.query_one("#detail-path", Static).update("[dim](select a node)[/dim]")
        self.query_one("#detail-value", RichLog).clear()

    def on_tree_node_selected(self, event: Tree.NodeSelected) -> None:
        data = event.node.data
        if not data:
            return
        path = data.get("path", "")
        value = data.get("value")
        self.query_one("#detail-path", Static).update(escape(path) if path else "(root)")
        detail = self.query_one("#detail-value", RichLog)
        detail.clear()
        try:
            detail.write(json.dumps(value, indent=2, default=repr))
        except Exception:
            detail.write(repr(value))

    def action_close_screen(self) -> None:
        self.dismiss()

    def action_refresh_store(self) -> None:
        self._populate_tree()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "close-btn":
            self.dismiss()
        elif event.button.id == "refresh-btn":
            self.action_refresh_store()
