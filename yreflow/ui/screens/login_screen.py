"""Login screen for Wolfery authentication."""

from __future__ import annotations

from textual.binding import Binding
from textual.screen import ModalScreen
from textual.widgets import Static, Button, Input
from textual.containers import Vertical

from .tabbable_modal import TabbableModal


class LoginScreen(TabbableModal, ModalScreen[tuple[str, str] | None]):
    """Modal screen for username/password login."""

    DEFAULT_CSS = """
    LoginScreen {
        align: center middle;
    }
    #login-container {
        width: 50;
        height: auto;
        background: $panel;
        border: solid $accent;
        padding: 1 2;
    }
    #login-title {
        text-style: bold;
        text-align: center;
        width: 100%;
        margin-bottom: 1;
    }
    .login-label {
        margin-top: 1;
    }
    #login-error {
        color: red;
        text-align: center;
        margin-top: 1;
    }
    #login-btn {
        margin-top: 1;
        width: 100%;
    }
    """

    BINDINGS = [
        Binding("escape", "quit_app", "Quit"),
    ]

    def __init__(self, error: str | None = None, **kwargs) -> None:
        super().__init__(**kwargs)
        self.error = error

    def compose(self):
        with Vertical(id="login-container"):
            yield Static("yreflow", id="login-title")
            yield Static("Username", classes="login-label")
            yield Input(id="login-username", placeholder="Wolfery username")
            yield Static("Password", classes="login-label")
            yield Input(id="login-password", placeholder="Password", password=True)
            error_text = self.error or ""
            yield Static(error_text, id="login-error")
            yield Button("Login", id="login-btn", variant="primary")

    def on_mount(self) -> None:
        if not self.error:
            self.query_one("#login-error", Static).display = False
        self.query_one("#login-username", Input).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "login-btn":
            self._submit()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self._submit()

    def _submit(self) -> None:
        username = self.query_one("#login-username", Input).value.strip()
        password = self.query_one("#login-password", Input).value
        if not username or not password:
            error = self.query_one("#login-error", Static)
            error.update("Username and password are required.")
            error.display = True
            return
        self.dismiss((username, password))

    def action_quit_app(self) -> None:
        self.app.exit()
