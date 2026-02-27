"""Entry point for the yreflow Wolfery console client."""

import sys
from pathlib import Path

from .config import load_config
from .controller import Controller
from .ui.app import WolferyApp


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
            print(f"Config file not found: {config_path}")
            sys.exit(1)

    config = load_config(config_path)

    app = WolferyApp()
    controller = Controller(config, app)
    app.controller = controller

    app.run()


if __name__ == "__main__":
    main()
