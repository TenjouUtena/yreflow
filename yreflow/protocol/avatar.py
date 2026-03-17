"""Fetch character avatars from the Wolfery file server."""

import io
import logging
from typing import Literal

import httpx
from PIL import Image as PILImage

log = logging.getLogger(__name__)

AvatarSize = Literal["xxs","xs","s", "m", "l", "xl", "xxl"]

_DEFAULT_FILE_URL = "https://file.wolfery.com"
_DEFAULT_COOKIE = "wolfery-auth-token"


async def get_avatar(
    avatar_key: str,
    size: AvatarSize = "m",
    auth_token: str = "",
    file_base_url: str = "",
    cookie_name: str = "",
    timeout: float = 10.0,
) -> PILImage.Image:
    """Fetch a character avatar and return it as a PIL Image.

    Args:
        avatar_key: The avatar key from core.char.<id>.avatar.
        size: Thumbnail size — one of s, m, l, xl, xxl.
        auth_token: Optional auth-token cookie value.
        file_base_url: Base file server URL (e.g. https://file.wolfery.com).
        cookie_name: Auth cookie name (e.g. wolfery-auth-token).
        timeout: Request timeout in seconds.

    Raises:
        httpx.HTTPStatusError: On non-2xx responses.
        ValueError: If avatar_key is empty.
    """
    if not avatar_key:
        raise ValueError("avatar_key must not be empty")

    base = file_base_url or _DEFAULT_FILE_URL
    url = f"{base}/core/char/avatar/{avatar_key}"
    cookies = {}
    if auth_token:
        cookies[cookie_name or _DEFAULT_COOKIE] = auth_token

    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.get(url, params={"thumb": size}, cookies=cookies)
        resp.raise_for_status()

    return PILImage.open(io.BytesIO(resp.content))


async def get_char_image(
    image_id: str,
    auth_token: str = "",
    file_base_url: str = "",
    cookie_name: str = "",
    timeout: float = 10.0,
) -> PILImage.Image:
    """Fetch a character's full image and return it as a PIL Image.

    Args:
        image_id: The image model ID (from core.char.img.<id>).
        auth_token: Optional auth-token cookie value.
        file_base_url: Base file server URL.
        cookie_name: Auth cookie name.
        timeout: Request timeout in seconds.
    """
    if not image_id:
        raise ValueError("image_id must not be empty")

    base = file_base_url or _DEFAULT_FILE_URL
    url = f"{base}/core/char/img/{image_id}"
    cookies = {}
    if auth_token:
        cookies[cookie_name or _DEFAULT_COOKIE] = auth_token

    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.get(url, cookies=cookies)
        resp.raise_for_status()

    return PILImage.open(io.BytesIO(resp.content))
