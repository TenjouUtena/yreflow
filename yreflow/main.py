"""Entry point for the yreflow Wolfery console client."""

import sys
from pathlib import Path

from .config import load_config
from .controller import Controller
from .ui.app import WolferyApp


_DEFAULT_SUBSCRIPTIONS = [
    "subscribe.core.info",
    "subscribe.tag.info",
    "subscribe.mail.info",
    "subscribe.note.info",
    "subscribe.report.info",
    "subscribe.support.info",
    "subscribe.client.web.info",
    "subscribe.core.nodes",
    "call.core.getPlayer",
    "call.core.getRoles",
    "subscribe.tag.tags",
    "subscribe.core.chars.awake",
]


def main():
    config_path = "config.toml"
    if len(sys.argv) > 1:
        config_path = sys.argv[1]

    if not Path(config_path).exists():
        # Try Samples/ as fallback
        fallback = Path("Samples/config.toml")
        if fallback.exists():
            config_path = str(fallback)
        else:
            config_path = None

    if config_path:
        config = load_config(config_path)
    else:
        # No config file — use defaults, will prompt for login
        config = {"default_subscriptions": _DEFAULT_SUBSCRIPTIONS}

    app = WolferyApp()
    controller = Controller(config, app)
    app.controller = controller

    app.run()


if __name__ == "__main__":
    main()
