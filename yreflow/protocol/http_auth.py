"""HTTP-based authentication to obtain a auth-token.

Performs a POST to auth.mucklet.com/login, extracts the session cookie,
and returns it for use as a WebSocket auth token.
"""

import hashlib
import hmac
import base64
import logging

import httpx

log = logging.getLogger(__name__)

_PEPPER = b"TheStoryStartsHere"
_LOGIN_URL = "https://auth.mucklet.com/login"


def _hash_password(password: str) -> tuple[str, str]:
    """Compute Wolfery's required password hashes.

    Returns (pass_hash, hmac_hash), both base64-encoded.
    """
    trimmed = password.strip()

    # pass = base64(sha256(password))
    sha256_digest = hashlib.sha256(trimmed.encode("utf-8")).digest()
    pass_hash = base64.b64encode(sha256_digest).decode("ascii")

    # hash = base64(hmac_sha256(key=pepper, msg=password))
    hmac_digest = hmac.new(
        _PEPPER, trimmed.encode("utf-8"), hashlib.sha256
    ).digest()
    hmac_hash = base64.b64encode(hmac_digest).decode("ascii")

    return pass_hash, hmac_hash


def _extract_token(client: httpx.AsyncClient, response: httpx.Response) -> str | None:
    """Extract auth-token from cookies or Set-Cookie headers."""
    # Check client cookie jar (accumulated across redirects)
    token = client.cookies.get("auth-token")
    if token:
        return token

    # Check response cookies directly
    token = response.cookies.get("auth-token")
    if token:
        return token

    # Manual Set-Cookie header parsing as fallback
    for header_value in response.headers.get_list("set-cookie"):
        if "auth-token=" in header_value:
            for part in header_value.split(";"):
                part = part.strip()
                if part.startswith("auth-token="):
                    return part.split("=", 1)[1]

    return None


async def obtain_token(username: str, password: str) -> str:
    """Log in to Wolfery via HTTP and return the auth token.

    Raises ValueError on authentication failure.
    """
    pass_hash, hmac_hash = _hash_password(password)

    async with httpx.AsyncClient(follow_redirects=True, timeout=20.0) as client:
        response = await client.post(
            f"{_LOGIN_URL}?noredirect",
            files={
                "name": (None, username),
                "pass": (None, pass_hash),
                "hash": (None, hmac_hash),
            },
        )

        log.debug("HTTP %s %s", response.status_code, response.url)
        log.debug("Response headers: %s", dict(response.headers))
        log.debug("Client cookies: %s", dict(client.cookies))
        log.debug("Response cookies: %s", dict(response.cookies))
        log.debug("Response body (first 500): %s", response.text[:500])
        # Log full redirect history
        for r in response.history:
            log.debug("Redirect: %s %s", r.status_code, r.url)
            log.debug("  Set-Cookie: %s", r.headers.get_list("set-cookie"))
            log.debug("  Cookies in jar after: %s", dict(client.cookies))

        if response.status_code >= 400:
            raise ValueError(f"Login failed (HTTP {response.status_code})")

        token = _extract_token(client, response)
        if not token:
            raise ValueError("Login succeeded but no auth token was returned")

        return token
