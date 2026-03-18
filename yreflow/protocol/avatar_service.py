"""Avatar caching service — fetches avatars and renders them as inline Rich markup.

Each avatar is displayed as a 2-character-wide, 1-line-tall block using Unicode
half-block characters (▀) with colored foreground/background to pack 2×2 pixels
into 2 terminal cells.
"""

import asyncio
import logging
from typing import TYPE_CHECKING

from PIL import Image as PILImage

from .avatar import get_avatar

if TYPE_CHECKING:
    from .model_store import ModelStore

log = logging.getLogger(__name__)

# Upper-half block: foreground = top pixel, background = bottom pixel
_HALF_BLOCK = "\u2580"


def _render_2x1(img: PILImage.Image) -> str:
    """Convert a PIL Image to a 2-char-wide, 1-line-tall Rich markup string.

    Resizes to 2×2 pixels, then uses half-block characters so each cell
    encodes two vertical pixels via fg/bg colors.
    """
    tiny = img.convert("RGB").resize((2, 2), PILImage.Resampling.LANCZOS)
    pixels = tiny.load()
    parts = []
    for x in range(2):
        top = pixels[x, 0]
        bot = pixels[x, 1]
        fg = f"#{top[0]:02x}{top[1]:02x}{top[2]:02x}"
        bg = f"#{bot[0]:02x}{bot[1]:02x}{bot[2]:02x}"
        parts.append(f"[{fg} on {bg}]{_HALF_BLOCK}[/]")
    return "".join(parts)


# Sentinel for "no avatar available" (empty key or fetch failed)
_NO_AVATAR = ""


class AvatarService:
    """Async avatar fetcher with in-memory cache.

    Avatars are fetched lazily: the first message from a character triggers a
    background fetch.  Subsequent messages use the cached Rich markup.  If the
    fetch fails or the character has no avatar key, a sentinel is stored so we
    don't retry endlessly.
    """

    def __init__(self) -> None:
        self._cache: dict[str, str] = {}  # char_id -> Rich markup or _NO_AVATAR
        self._pending: set[str] = set()   # char_ids currently being fetched

    def get_avatar_markup(self, char_id: str) -> str | None:
        """Return cached Rich markup for *char_id*, or None if not yet available."""
        cached = self._cache.get(char_id)
        if cached is _NO_AVATAR:
            return None
        return cached  # str or None (not in cache yet)

    def ensure_cached(
        self,
        char_id: str,
        store: "ModelStore",
        token: str | None,
    ) -> None:
        """Kick off a background fetch if *char_id* isn't cached yet."""
        if char_id in self._cache or char_id in self._pending:
            return
        avatar_key = store.get_character_attribute(char_id, "avatar", "")
        log.info("avatar lookup char_id=%s avatar_key=%r type=%s", char_id, avatar_key, type(avatar_key).__name__)
        if not avatar_key:
            self._cache[char_id] = _NO_AVATAR
            return
        self._pending.add(char_id)
        asyncio.create_task(self._fetch(char_id, avatar_key, token or ""))

    async def _fetch(self, char_id: str, avatar_key: str, token: str) -> None:
        try:
            log.info("fetching avatar for %s key=%s", char_id, avatar_key)
            img = await get_avatar(avatar_key, size="s", auth_token=token)
            markup = _render_2x1(img)
            log.info("avatar fetched for %s, markup=%r", char_id, markup)
            self._cache[char_id] = markup
        except Exception:
            log.warning("avatar fetch failed for %s", char_id, exc_info=True)
            self._cache[char_id] = _NO_AVATAR
        finally:
            self._pending.discard(char_id)
