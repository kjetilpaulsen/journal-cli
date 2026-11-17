"""Small modal dialogs: yes/no confirmation and changing the password."""

from typing import ClassVar

from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Input, Static

from journal_cli.api import ApiError, Unauthorized
from journal_cli.tui.screens import AppAccess

MIN_PASSWORD_LENGTH = 12  # journal-service enforces the same


class ConfirmScreen(ModalScreen[bool]):
    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("y", "answer(True)", "Yes"),
        Binding("n,escape", "answer(False)", "No"),
    ]

    def __init__(self, question: str) -> None:
        super().__init__()
        self.question = question

    def compose(self) -> ComposeResult:
        with Vertical(id="confirm-box", classes="dialog"):
            yield Static(self.question, id="confirm-question")
            yield Static("y  yes      n  no", classes="dialog-hint")

    def action_answer(self, yes: bool) -> None:
        self.dismiss(yes)


class PasswordScreen(AppAccess, ModalScreen[None]):
    """Change the password. Takes a few seconds: the key is re-encrypted with scrypt."""

    BINDINGS: ClassVar[list[BindingType]] = [Binding("escape", "cancel", "Cancel")]

    def compose(self) -> ComposeResult:
        with Vertical(id="password-box", classes="dialog"):
            yield Static("Change password", classes="dialog-title")
            yield Input(placeholder="current password", password=True, id="current")
            yield Input(
                placeholder=f"new password ({MIN_PASSWORD_LENGTH}+ characters)",
                password=True,
                id="new",
            )
            yield Input(placeholder="repeat new password", password=True, id="repeat")
            yield Static(
                "enter  next / change      esc  cancel", id="password-status", classes="dialog-hint"
            )

    def on_mount(self) -> None:
        self.query_one("#current", Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        event.stop()
        following = {"current": "#new", "new": "#repeat"}.get(event.input.id or "")
        if following:
            self.query_one(following, Input).focus()
        else:
            self._submit()

    def _submit(self) -> None:
        current = self.query_one("#current", Input).value
        new = self.query_one("#new", Input).value
        repeat = self.query_one("#repeat", Input).value
        if not current:
            return self._problem("Enter the current password.", "#current")
        if len(new) < MIN_PASSWORD_LENGTH:
            return self._problem(f"Use at least {MIN_PASSWORD_LENGTH} characters.", "#new")
        if new != repeat:
            return self._problem("The new passwords do not match.", "#repeat")

        self._busy(True)
        self.query_one("#password-status", Static).update("Changing password…")
        self.journal.call_api(
            lambda: self.journal.client.change_password(current, new),
            self._changed,
            on_error=self._failed,
            reauth=False,
        )

    def _changed(self, _result: None) -> None:
        self.app.notify("Password changed. Use the new one from now on.", title="journal")
        self.dismiss(None)

    def _failed(self, exc: ApiError) -> None:
        self._busy(False)
        if isinstance(exc, Unauthorized):
            self._problem("The current password is wrong.", "#current")
        else:
            self._problem(str(exc), "#new")

    def _problem(self, message: str, field: str) -> None:
        self.query_one("#password-status", Static).update(message)
        widget = self.query_one(field, Input)
        widget.value = ""
        widget.focus()

    def _busy(self, busy: bool) -> None:
        for widget in self.query(Input):
            widget.disabled = busy

    def action_cancel(self) -> None:
        self.dismiss(None)
