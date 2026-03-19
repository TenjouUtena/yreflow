import tomllib
from pathlib import Path

CONFIG_DIR = Path.home() / ".config" / "yreflow"
CONFIG_PATH = CONFIG_DIR / "config.toml"
DELETED_CHARS_PATH = CONFIG_DIR / "deletedchars.toml"
DEFAULT_LOG_DIR = CONFIG_DIR / "logs"


def load_config() -> dict:
    """Load config from ~/.config/yreflow/config.toml.

    Returns an empty dict if the file doesn't exist.
    """
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH, "rb") as f:
            return tomllib.load(f)
    return {}


def save_token(token: str) -> None:
    """Save auth token to config file, preserving other settings."""
    config = load_config()
    config["token"] = token
    _write_config(config)


def save_preference(key: str, value) -> None:
    """Save a single preference to config file, preserving other settings."""
    config = load_config()
    config[key] = value
    _write_config(config)


def get_log_dir() -> Path:
    """Return the log directory from config, or the default."""
    config = load_config()
    custom = config.get("log_dir")
    if custom:
        return Path(custom).expanduser()
    return DEFAULT_LOG_DIR


def clear_token() -> None:
    """Remove auth token from config file, preserving other settings."""
    config = load_config()
    config.pop("token", None)
    _write_config(config)


def load_last_seen() -> dict[str, int]:
    """Return the last_seen table from config (ctrl_id -> timestamp ms)."""
    return load_config().get("last_seen", {})


def save_last_seen(timestamps: dict[str, int]) -> None:
    """Persist per-character last-seen timestamps to config."""
    config = load_config()
    config["last_seen"] = {k: v for k, v in timestamps.items() if isinstance(v, int)}
    _write_config(config)


def formatter_settings() -> dict:
    """Return formatter-related settings with defaults."""
    cfg = load_config()
    return {
        "superscript_style": cfg.get("superscript_style", "highlight"),
        "superscript_color": cfg.get("superscript_color", "gold"),
        "subscript_style": cfg.get("subscript_style", "highlight"),
        "subscript_color": cfg.get("subscript_color", "skyblue"),
    }


def show_avatars() -> bool:
    """Return whether inline avatars should be shown next to messages."""
    return load_config().get("show_avatars", False)


def _write_config(config: dict) -> None:
    """Write config dict as TOML to the config file."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    lines = []
    for key, value in config.items():
        if isinstance(value, str):
            # Escape backslashes and quotes for TOML string
            escaped = value.replace("\\", "\\\\").replace('"', '\\"')
            lines.append(f'{key} = "{escaped}"')
        elif isinstance(value, bool):
            lines.append(f"{key} = {'true' if value else 'false'}")
        elif isinstance(value, (int, float)):
            lines.append(f"{key} = {value}")
        elif isinstance(value, dict):
            lines.append(f"\n[{key}]")
            for k, v in value.items():
                if isinstance(v, str):
                    escaped = v.replace("\\", "\\\\").replace('"', '\\"')
                    lines.append(f'{k} = "{escaped}"')
                elif isinstance(v, bool):
                    lines.append(f"{k} = {'true' if v else 'false'}")
                elif isinstance(v, (int, float)):
                    lines.append(f"{k} = {v}")
        elif isinstance(value, list):
            items = ", ".join(f'"{v}"' for v in value)
            lines.append(f"{key} = [{items}]")
    CONFIG_PATH.write_text("\n".join(lines) + "\n")


def load_deleted_chars() -> list[str]:
    """Load the list of deleted character IDs from deletedchars.toml."""
    if DELETED_CHARS_PATH.exists():
        with open(DELETED_CHARS_PATH, "rb") as f:
            data = tomllib.load(f)
        return list(data.get("deleted", []))
    return []


def save_deleted_chars(char_ids: list[str]) -> None:
    """Save the list of deleted character IDs to deletedchars.toml."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    unique = list(dict.fromkeys(char_ids))  # preserve order, deduplicate
    items = ", ".join(f'"{cid}"' for cid in unique)
    DELETED_CHARS_PATH.write_text(f"deleted = [{items}]\n")
