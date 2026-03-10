"""Realm configuration for Mucklet-based servers."""

from dataclasses import dataclass

DEFAULT_REALM_KEY = "wolfery"

# Known realm keys for /realm list
KNOWN_REALMS = {
    "wolfery": "Wolfery",
    "aurellion": "The World of Aurellion",
    "lastflameinn": "Last Flame Inn",
}


@dataclass(frozen=True)
class Realm:
    """Connection endpoints for a single realm."""

    key: str
    ws_url: str
    file_url: str
    cookie_name: str

    @classmethod
    def from_key(cls, key: str) -> "Realm":
        """Derive all URLs from a realm key.

        Wolfery is special-cased (wolfery.com); all others use {key}.mucklet.com.
        """
        if key == "wolfery":
            domain = "wolfery.com"
        else:
            domain = f"{key}.mucklet.com"

        return cls(
            key=key,
            ws_url=f"wss://api.{domain}/",
            file_url=f"https://file.{domain}",
            cookie_name=f"{key}-auth-token",
        )
