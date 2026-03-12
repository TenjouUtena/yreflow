"""Entry point for the yreflow Wolfery console client."""

import logging
from datetime import date
from pathlib import Path

from .config import load_config
from .controller import Controller
from .ui.app import WolferyApp


def main():
    config = load_config()

    debug_log_path = config.get("debug_log_path")
    if debug_log_path:
        log_dir = Path(debug_log_path).expanduser()
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / f"yreflow_debug_{date.today().isoformat()}.log"
        logging.basicConfig(
            filename=str(log_file),
            level=logging.DEBUG,
            format="%(asctime)s.%(msecs)03d %(name)s %(message)s",
            datefmt="%H:%M:%S",
        )

    app = WolferyApp()
    controller = Controller(config, app)
    app.controller = controller

    app.run()


if __name__ == "__main__":
    main()
