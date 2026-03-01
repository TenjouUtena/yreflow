import tomllib
from pathlib import Path

CONFIG_DIR = Path.home() / ".config" / "yreflow"
CONFIG_PATH = CONFIG_DIR / "config.toml"
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
        elif isinstance(value, list):
            items = ", ".join(f'"{v}"' for v in value)
            lines.append(f"{key} = [{items}]")
    CONFIG_PATH.write_text("\n".join(lines) + "\n")
