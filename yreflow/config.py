import tomllib
from pathlib import Path

CONFIG_DIR = Path.home() / ".config" / "yreflow"
CONFIG_PATH = CONFIG_DIR / "config.toml"


def load_config() -> dict:
    """Load config from ~/.config/yreflow/config.toml.

    Returns an empty dict if the file doesn't exist.
    """
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH, "rb") as f:
            return tomllib.load(f)
    return {}
