"""Entry point for the yreflow Wolfery console client."""

from .config import load_config
from .controller import Controller
from .ui.app import WolferyApp


def main():
    config = load_config()

    app = WolferyApp()
    controller = Controller(config, app)
    app.controller = controller

    app.run()


if __name__ == "__main__":
    main()
