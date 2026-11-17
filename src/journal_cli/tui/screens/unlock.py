"""The password prompt: shown first, after locking, and when a session expires mid-action."""

import logging
from typing import ClassVar

from textual import work
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Input, Static

from journal_cli.api import ApiError, Conflict, Unauthorized
from journal_cli.tui.screens import AppAccess

log = logging.getLogger(__name__)

NOT_INITIALIZED = (
    "journal-service has no password yet. Set one with:\n"
    "podman exec -it journal-service journal-service init"
)


class UnlockScreen(AppAccess, ModalScreen[bool]):
    BINDINGS: ClassVar[list[BindingType]] = [Binding("escape", "cancel", "Cancel", show=False)]

    def __init__(self, reason: str | None = None, *, cancellable: bool = False) -> None:
        super().__init__()
        self.reason = reason
        self.cancellable = cancellable

    def compose(self) -> ComposeResult:
        with Vertical(id="unlock-box", classes="dialog"):
            yield Static("journal", classes="dialog-title")
            yield Input(placeholder="password", password=True, id="password")
            hint = "esc  cancel" if self.cancellable else "ctrl+q  quit"
            yield Static(
                self.reason or f"enter  unlock      {hint}",
                id="unlock-status",
                classes="dialog-hint",
            )

    def on_mount(self) -> None:
        self.query_one(Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        event.stop()
        if not event.value:
            return
        event.input.disabled = True
        self.query_one("#unlock-status", Static).update("Unlocking…")
        self._unlock(event.value)

    @work(thread=True, exclusive=True)
    def _unlock(self, password: str) -> None:
        try:
            self.journal.client.unlock(password)
        except Unauthorized:
            log.warning("unlock failed: wrong password")
            self.app.call_from_thread(self._failed, "Wrong password.")
        except Conflict:
            self.app.call_from_thread(self._failed, NOT_INITIALIZED)
        except ApiError as exc:
            self.app.call_from_thread(self._failed, str(exc))
        else:
            log.info("unlocked")
            self.app.call_from_thread(self.dismiss, True)

    def _failed(self, message: str) -> None:
        self.query_one("#unlock-status", Static).update(message)
        field = self.query_one(Input)
        field.disabled = False
        field.value = ""
        field.focus()

    def action_cancel(self) -> None:
        if self.cancellable:
            self.dismiss(False)
