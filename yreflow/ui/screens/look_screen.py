"""Look screen modal for room and character inspection."""

from __future__ import annotations

import asyncio
import logging

from PIL import Image as PILImage
from textual.binding import Binding
from textual.screen import ModalScreen
from textual.widgets import Static, Button, TabbedContent, TabPane
from textual.containers import Vertical, VerticalScroll
from textual_image.widget import Image as TImage

from collections.abc import Callable

from ...formatter import format_message
from ...config import formatter_settings
from ...protocol.avatar import get_avatar


log = logging.getLogger("yreflow.look_screen")


class LookScreen(ModalScreen):
    """Modal screen displaying room or character info."""

    DEFAULT_CSS = """
    LookScreen {
        align: center middle;
    }
    #look-container {
        width: 70;
        height: auto;
        max-height: 85%;
        background: $panel;
        border: solid $accent;
        padding: 1 2;
    }
    #look-title {
        text-style: bold;
        text-align: center;
        width: 100%;
        margin-bottom: 1;
    }
    #look-subtitle {
        text-align: center;
        width: 100%;
        color: $text-muted;
    }
    #look-body {
        height: 1fr;
    }
    .look-section-title {
        text-style: bold;
        color: $accent;
        margin-top: 1;
    }
    .look-text {
        margin-bottom: 1;
    }
    .look-exit {
        padding: 0 1;
    }
    .look-tag-like {
        color: green;
    }
    .look-tag-dislike {
        color: red;
    }
    #look-avatar {
        height: 20;
        width: 100%;
        margin-bottom: 1;
    }
    #whois-avatar {
        height: auto;
        width: auto;
        max-height: 14;
        margin-bottom: 1;
    }
    #close-btn {
        margin-top: 1;
        width: 100%;
    }
    """

    BINDINGS = [
        Binding("escape", "close_screen", "Close"),
    ]

    def __init__(
        self,
        data: dict,
        on_url: Callable[[str, str], None] | None = None,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self.data = data
        self._on_url = on_url
        self._cached_image: PILImage.Image | None = None
        self._cached_image_url: str = ""
        self._update_lock = asyncio.Lock()
        self._pending_data: dict | None = None

    def compose(self):
        with Vertical(id="look-container"):
            yield Static(self.data.get("name", ""), id="look-title", markup=True)
            if self.data["type"] in ("character", "whois"):
                parts = []
                if self.data.get("gender"):
                    parts.append(self.data["gender"])
                if self.data.get("species"):
                    parts.append(self.data["species"])
                if parts:
                    yield Static(" ".join(parts), id="look-subtitle")
            yield VerticalScroll(id="look-body")
            yield Button("Close", id="close-btn", variant="default")

    async def on_mount(self) -> None:
        async with self._update_lock:
            body = self.query_one("#look-body", VerticalScroll)
            # If update_data() already populated the body while we waited
            # for the lock, skip — the content is already there (#74).
            if len(body.children) > 0:
                log.debug("on_mount() skipped — body already populated by update_data()")
                return
            if self.data["type"] == "room":
                await self._mount_room(body)
            elif self.data["type"] == "character":
                await self._mount_character(body)
            elif self.data["type"] == "whois":
                await self._mount_whois(body)
            elif self.data["type"] == "exit":
                await self._mount_exit(body)
            elif self.data["type"] == "rules":
                await self._mount_rules(body)

    async def _mount_room(self, body: VerticalScroll) -> None:
        areas = self.data.get("areas", [])

        if areas:
            # Use TabbedContent: Room tab + area tabs
            tabbed = TabbedContent()
            await body.mount(tabbed)

            # Room tab
            room_pane = TabPane("Room", id="tab-room")
            await tabbed.add_pane(room_pane)
            await self._mount_room_content(room_pane)

            # Area tabs
            for i, area in enumerate(areas):
                area_pane = TabPane(area["name"], id=f"tab-area-{i}")
                await tabbed.add_pane(area_pane)
                await self._mount_area_content(area_pane, area)
        else:
            # No areas, just show room content directly
            await self._mount_room_content(body)

    async def _mount_room_content(self, container) -> None:
        desc = self.data.get("desc", "")
        if desc:
            await container.mount(
                Static(format_message(desc, on_url=self._on_url, **formatter_settings()), classes="look-text", markup=True)
            )

        exits = self.data.get("exits", [])
        if exits:
            await container.mount(
                Static("Exits", classes="look-section-title", markup=True)
            )
            for ex in exits:
                keys = f" ({ex['keys']})" if ex.get("keys") else ""
                await container.mount(
                    Static(
                        f"  [bold]{ex['name']}[/bold]{keys}",
                        classes="look-exit",
                        markup=True,
                    )
                )

    async def _mount_exit(self, body: VerticalScroll) -> None:
        keys = self.data.get("keys", "")
        if keys:
            await body.mount(
                Static(f"[dim]({keys})[/dim]", classes="look-text", markup=True)
            )
        present = self.data.get("present", [])
        if present:
            await body.mount(
                Static("Present", classes="look-section-title", markup=True)
            )
            for name in present:
                await body.mount(
                    Static(f"  {name}", classes="look-exit", markup=True)
                )
        else:
            await body.mount(
                Static("[dim]No one visible.[/dim]", classes="look-text", markup=True)
            )

    async def _mount_area_content(self, container, area: dict) -> None:
        if area.get("pop", 0) > 0:
            await container.mount(
                Static(
                    f"Population: {area['pop']}",
                    classes="look-text",
                    markup=True,
                )
            )
        about = area.get("about", "")
        if about:
            await container.mount(
                Static(format_message(about, on_url=self._on_url, **formatter_settings()), classes="look-text", markup=True)
            )
        if not area.get("pop") and not about:
            await container.mount(
                Static("[dim]No details available.[/dim]", markup=True)
            )

    async def _mount_character(self, body: VerticalScroll) -> None:
        avatar_key = self.data.get("avatar", "")
        desc = self.data.get("desc","")
        if avatar_key:
            try:
                if avatar_key != self._cached_image_url or self._cached_image is None:
                    self._cached_image = await get_avatar(
                        avatar_key,
                        size="xl",
                        auth_token=self.data.get("auth_token", ""),
                        file_base_url=self.data.get("file_base_url", ""),
                        cookie_name=self.data.get("cookie_name", ""),
                    )
                    self._cached_image_url = avatar_key
                await body.mount(TImage(self._cached_image, id="look-avatar"))
            except Exception:
                pass

        if desc:
            await body.mount(
                Static(format_message(desc, on_url=self._on_url, **formatter_settings()), classes="look-text", markup=True)
            )

        about = self.data.get("about", "")
        if about:
            await body.mount(
                Static("About", classes="look-section-title", markup=True)
            )
            await body.mount(
                Static(format_message(about, on_url=self._on_url, **formatter_settings()), classes="look-text", markup=True)
            )

        await self._mount_tags(body)

        if not desc and not about and not self.data.get("tags"):
            await body.mount(
                Static("[dim]No information available.[/dim]", markup=True)
            )

    async def _mount_tags(self, body: VerticalScroll) -> None:
        tags = self.data.get("tags", [])
        if not tags:
            return
        await body.mount(
            Static("Tags", classes="look-section-title", markup=True)
        )
        likes = [t for t in tags if t["like"]]
        dislikes = [t for t in tags if not t["like"]]
        if likes:
            items = ", ".join(t["key"] for t in likes)
            await body.mount(
                Static(
                    f"  [green]Likes:[/green] {items}",
                    classes="look-tag-like",
                    markup=True,
                )
            )
        if dislikes:
            items = ", ".join(t["key"] for t in dislikes)
            await body.mount(
                Static(
                    f"  [red]Dislikes:[/red] {items}",
                    classes="look-tag-dislike",
                    markup=True,
                )
            )

    async def _mount_rules(self, body: VerticalScroll) -> None:
        rules = self.data.get("rules", "")
        if rules:
            await body.mount(
                Static(format_message(rules, on_url=self._on_url, **formatter_settings()), classes="look-text", markup=True)
            )
        else:
            await body.mount(
                Static("[dim]No rules available.[/dim]", markup=True)
            )

    async def _mount_whois(self, body: VerticalScroll) -> None:
        status = self.data.get("status", "")
        if status:
            await body.mount(
                Static(f"[italic]{status}[/italic]", classes="look-text", markup=True)
            )

        avatar_key = self.data.get("avatar", "")
        if avatar_key:
            try:
                if avatar_key != self._cached_image_url or self._cached_image is None:
                    self._cached_image = await get_avatar(
                        avatar_key,
                        size="m",
                        auth_token=self.data.get("auth_token", ""),
                        file_base_url=self.data.get("file_base_url", ""),
                        cookie_name=self.data.get("cookie_name", ""),
                    )
                    self._cached_image_url = avatar_key
                await body.mount(TImage(self._cached_image, id="whois-avatar"))
            except Exception:
                pass

        await self._mount_tags(body)

    async def update_data(self, data: dict) -> None:
        """Re-render the body with updated character data.

        Uses an asyncio.Lock to serialize updates — resclient often
        fires multiple store-change events in quick succession, which
        can cause interleaved mount operations and duplicate widgets (#74).
        If the lock is held, we stash the latest data so only the most
        recent update runs when the lock is released (coalescing).
        """
        if self._update_lock.locked():
            log.debug("update_data() coalesced — lock held, stashing data")
            self._pending_data = data
            return

        async with self._update_lock:
            self._pending_data = None
            await self._do_update(data)
            # Drain any updates that arrived while we held the lock
            while self._pending_data is not None:
                log.debug("update_data() draining pending update")
                deferred = self._pending_data
                self._pending_data = None
                await self._do_update(deferred)

    async def _do_update(self, data: dict) -> None:
        """Actually perform the body re-render."""
        self.data = data
        body = self.query_one("#look-body", VerticalScroll)
        await body.remove_children()
        if data["type"] == "room":
            await self._mount_room(body)
        elif data["type"] == "character":
            await self._mount_character(body)
        elif data["type"] == "exit":
            await self._mount_exit(body)
        elif data["type"] == "whois":
            await self._mount_whois(body)
        elif data["type"] == "rules":
            await self._mount_rules(body)

    def action_close_screen(self) -> None:
        self.dismiss()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "close-btn":
            self.dismiss()
