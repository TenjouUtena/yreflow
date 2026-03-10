"""Mail command handling: list inbox, send, read, and pagination."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from .handler import CommandResult, _relative_time
from .name_resolver import parse_name, NameParseException

if TYPE_CHECKING:
    from ..protocol.connection import WolferyConnection
    from ..protocol.model_store import ModelStore
    from ..protocol.controlled_char import ControlledChar

_PAGE_SIZE = 10


class MailManager:
    """Owns inbox cache and all mail command handlers."""

    def __init__(self, connection: WolferyConnection, store: ModelStore):
        self.conn = connection
        self.store = store
        self.inbox: list[dict] = []
        self.inbox_offset: int = 0
        self._pending_inbox: bool = False
        self._pending_more: bool = False
        # Watch fires *after* the ModelStore is updated, unlike message_waits.
        if self.store is not None:
            self.store.add_watch(r"^mail\.player\.\w+\.inbox", self._on_inbox_stored)

    # ------------------------------------------------------------------
    # Dispatch
    # ------------------------------------------------------------------

    async def process_command(
        self, content: str, cc: ControlledChar
    ) -> CommandResult:
        content = content.strip()

        if not content:
            return await self.handle_mail_list(cc)
        if content.startswith("send "):
            return await self.handle_mail_send(content[5:].strip(), cc)
        if content.startswith("read "):
            return await self.handle_mail_read(content[5:].strip(), cc)
        if content == "more":
            return await self.handle_mail_more(cc)

        return CommandResult(
            success=False,
            notification="Usage: mail | mail send Name = msg | mail read # | mail more",
        )

    # ------------------------------------------------------------------
    # List inbox
    # ------------------------------------------------------------------

    def _inbox_store_key(self, offset: int) -> str:
        return (
            f"mail.player.{self.conn.player}"
            f".inbox?offset={offset}&limit={_PAGE_SIZE + 1}"
        )

    def _collect_envelopes(self, store_key: str) -> list[dict]:
        """Read envelope data from the store for a given inbox key."""
        player = self.conn.player
        prefix = f"mail.player.{player}.message."
        try:
            collection = self.store.get(f"{store_key}._value")
        except KeyError:
            return []

        envelopes = []
        for entry in collection:
            rid = entry if isinstance(entry, str) else entry.get("rid", "")
            if not rid.startswith(prefix):
                continue
            try:
                env = self.store.get(rid)
                envelopes.append({"rid": rid, **env})
            except KeyError:
                continue
        return envelopes

    async def handle_mail_list(self, cc: ControlledChar) -> CommandResult:
        self.inbox_offset = 0
        store_key = self._inbox_store_key(0)

        # Step 1: check if we already have this batch cached.
        envelopes = self._collect_envelopes(store_key)
        if envelopes:
            text = self._build_inbox(envelopes, reset=True)
            return CommandResult(display_text=text)

        # Step 2: not cached — subscribe and wait for the watch.
        self._pending_inbox = True
        self._pending_more = False
        await self.conn.send(f"subscribe.{store_key}")
        return CommandResult(notification="Fetching mail...")

    async def _on_inbox_stored(self, path: str, payload) -> None:
        """ModelStore watch callback — fires after inbox collection is stored."""
        if self._pending_inbox:
            self._pending_inbox = False
            envelopes = self._collect_envelopes(path)
            text = self._build_inbox(envelopes, reset=True)
            await self.conn.event_bus.publish("mail.result", text=text)
        elif self._pending_more:
            self._pending_more = False
            envelopes = self._collect_envelopes(path)
            text = self._build_inbox(envelopes, reset=False)
            await self.conn.event_bus.publish("mail.result", text=text)

    def _build_inbox(self, envelopes: list[dict], reset: bool) -> str:
        """Sort, paginate, cache, and format envelope list. Returns markup."""
        envelopes.sort(key=lambda e: e.get("received", 0), reverse=True)
        has_more = len(envelopes) > _PAGE_SIZE
        page = envelopes[:_PAGE_SIZE] if has_more else envelopes

        if reset:
            self.inbox = page
            start = 1
        else:
            self.inbox.extend(page)
            start = self.inbox_offset + 1

        return self._format_inbox(page, start_index=start, has_more=has_more)

    # ------------------------------------------------------------------
    # More (pagination)
    # ------------------------------------------------------------------

    async def handle_mail_more(self, cc: ControlledChar) -> CommandResult:
        if not self.inbox:
            return CommandResult(
                success=False, notification="No mail loaded. Type 'mail' first."
            )
        self.inbox_offset += _PAGE_SIZE
        store_key = self._inbox_store_key(self.inbox_offset)

        envelopes = self._collect_envelopes(store_key)
        if envelopes:
            text = self._build_inbox(envelopes, reset=False)
            return CommandResult(display_text=text)

        self._pending_more = True
        await self.conn.send(f"subscribe.{store_key}")
        return CommandResult(notification="Fetching more mail...")

    # ------------------------------------------------------------------
    # Send
    # ------------------------------------------------------------------

    async def handle_mail_send(
        self, content: str, cc: ControlledChar
    ) -> CommandResult:
        m = re.match(r"([\w ,-]+?)\s*=\s*(.*)", content, re.DOTALL)
        if not m:
            return CommandResult(
                success=False,
                notification="Usage: mail send Name = message",
            )

        name = m.group(1).strip()
        text = m.group(2).strip()
        if not text:
            return CommandResult(
                success=False, notification="Mail message cannot be empty."
            )

        try:
            target_id = parse_name(self.store, name, awake=False)
        except NameParseException as e:
            return CommandResult(success=False, notification=str(e))

        msg_id = await self.conn.send(
            f"call.mail.player.{self.conn.player}.inbox.send",
            {
                "toCharId": target_id,
                "fromCharId": cc.char_id,
                "text": text,
            },
        )
        self.conn.add_message_wait(msg_id, self._on_send_result)
        return CommandResult(notification="Sending mail...")

    async def _on_send_result(self, payload) -> None:
        to_char = payload.get("toChar", {}) if isinstance(payload, dict) else {}
        name = to_char.get("name", "")
        surname = to_char.get("surname", "")
        full = f"{name} {surname}".strip() or "recipient"
        await self.conn.event_bus.publish(
            "notification", text=f"Mail sent to {full}.", character=None
        )

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    async def handle_mail_read(
        self, number_str: str, cc: ControlledChar
    ) -> CommandResult:
        try:
            idx = int(number_str)
        except ValueError:
            return CommandResult(
                success=False, notification="Usage: mail read <number>"
            )

        if idx < 1 or idx > len(self.inbox):
            return CommandResult(
                success=False,
                notification=f"No message #{idx}. Type 'mail' to list messages.",
            )

        envelope = self.inbox[idx - 1]

        # Resolve message content from the store.
        msg_rid = ""
        message_ref = envelope.get("message", {})
        if isinstance(message_ref, dict):
            msg_rid = message_ref.get("rid", "")

        msg_data = {}
        if msg_rid:
            try:
                msg_data = self.store.get(msg_rid)
            except KeyError:
                pass

        text = self._format_message(envelope, msg_data)

        # Mark as read.
        envelope_rid = envelope.get("rid", "")
        if envelope_rid:
            await self.conn.send(f"call.{envelope_rid}.read")

        return CommandResult(display_text=text)

    # ------------------------------------------------------------------
    # Unread check (called by controller on login)
    # ------------------------------------------------------------------

    def check_unread(self) -> int:
        try:
            unread = self.store.get(
                f"mail.player.{self.conn.player}.unread"
            )
        except KeyError:
            return 0
        if not isinstance(unread, dict):
            return 0
        return sum(
            1 for v in unread.values()
            if isinstance(v, dict) and v.get("action") != "delete"
        )

    # ------------------------------------------------------------------
    # Formatting helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _char_name(char_data: dict) -> str:
        if isinstance(char_data, dict):
            data = char_data.get("data", char_data)
            name = data.get("name", "")
            surname = data.get("surname", "")
            return f"{name} {surname}".strip()
        return "?"

    def _is_unread(self, envelope: dict) -> bool:
        return envelope.get("read") is None

    def _format_inbox(
        self,
        messages: list[dict],
        start_index: int = 1,
        has_more: bool = False,
    ) -> str:
        if not messages:
            return "Mail inbox is empty."

        lines = ["[bold]Mail Inbox:[/bold]"]
        lines.append(
            f"  {'#':>3}  {'':6}  {'From':<20}  {'Received'}"
        )

        for i, env in enumerate(messages, start=start_index):
            from_name = self._char_name(env.get("from", {}))
            received = env.get("received", 0)
            time_str = _relative_time(received) if received else "?"
            unread = "[NEW]" if self._is_unread(env) else ""
            lines.append(
                f"  {i:>3}  {unread:6}  {from_name:<20}  {time_str}"
            )

        lines.append("")
        lines.append("Type 'mail read #' to read a message.")
        if has_more:
            lines.append("Type 'mail more' for older messages.")

        return "\n".join(lines)

    def _format_message(self, envelope: dict, msg_data: dict) -> str:
        from_name = self._char_name(envelope.get("from", {}))
        to_name = self._char_name(envelope.get("to", {}))
        received = envelope.get("received", 0)
        time_str = _relative_time(received) if received else "?"
        text = msg_data.get("text", "(no content)")

        lines = [
            f"[bold]Mail from {from_name}[/bold] ({time_str}):",
            f"To: {to_name}",
            "",
            text,
            "",
            "Type 'mail' to return to inbox.",
        ]
        return "\n".join(lines)
