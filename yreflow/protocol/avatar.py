"""Fetch character avatars from the Wolfery file server."""

import io
import logging
from typing import Literal

import httpx
from PIL import Image as PILImage

log = logging.getLogger(__name__)

AvatarSize = Literal["s", "m", "l", "xl", "xxl"]

_BASE_URL = "https://file.wolfery.com/core/char/avatar"


async def get_avatar(
    avatar_key: str,
    size: AvatarSize = "m",
    auth_token: str = "",
    timeout: float = 10.0,
) -> PILImage.Image:
    """Fetch a character avatar and return it as a PIL Image.

    Args:
        avatar_key: The avatar key from core.char.<id>.avatar.
        size: Thumbnail size — one of s, m, l, xl, xxl.
        auth_token: Optional wolfery-auth-token cookie value.
        timeout: Request timeout in seconds.

    Raises:
        httpx.HTTPStatusError: On non-2xx responses.
        ValueError: If avatar_key is empty.
    """
    if not avatar_key:
        raise ValueError("avatar_key must not be empty")

    url = f"{_BASE_URL}/{avatar_key}"
    cookies = {}
    if auth_token:
        cookies["wolfery-auth-token"] = auth_token

    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.get(url, params={"thumb": size}, cookies=cookies)
        resp.raise_for_status()

    return PILImage.open(io.BytesIO(resp.content))
