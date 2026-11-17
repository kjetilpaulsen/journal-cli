"""The Textual application: owns the client, the decrypted entries (in memory only), locking.

Every call to journal-service runs in a worker thread (unlocking alone takes about a second
of scrypt), and its result comes back to the UI thread through `call_api`.
"""

import logging
import time
from collections.abc import Callable
from typing import ClassVar

from textual import events, work
from textual.app import App
from textual.binding import Binding, BindingType

from journal_cli.api import ApiError, Entry, JournalClient, Unauthorized
from journal_cli.settings import Settings
from journal_cli.tui.format import describe
from journal_cli.tui.screens.dialogs import ConfirmScreen
from journal_cli.tui.screens.editor import EditorScreen
from journal_cli.tui.screens.entries import EntriesScreen
from journal_cli.tui.screens.unlock import UnlockScreen

log = logging.getLogger(__name__)

IDLE_CHECK_SECONDS = 15


class JournalApp(App[str | None]):
    TITLE = "journal"
    CSS_PATH = "journal.tcss"
    ENABLE_COMMAND_PALETTE = False
    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("ctrl+q", "quit", "Quit", show=False, priority=True)
    ]

    def __init__(
        self, client: JournalClient, settings: Settings, *, quick_entry: bool = False
    ) -> None:
        super().__init__()
        self.client = client
        self.settings = settings
        self.quick_entry = quick_entry
        self.entries: dict[str, Entry] = {}  # decrypted; dropped on lock
        self.last_input = time.monotonic()

    def on_mount(self) -> None:
        self.theme = self.settings.theme
        if self.quick_entry:
            # Writing needs no password: entries are encrypted to the service's public key.
            self.push_screen(EditorScreen(), callback=self._quick_entry_done)
            return
        if self.settings.auto_lock is not None:
            self.set_interval(IDLE_CHECK_SECONDS, self.lock_if_idle)
        self._ask_password()

    def _ask_password(self, reason: str | None = None) -> None:
        def unlocked(ok: bool | None) -> None:
            if ok:
                self.push_screen(EntriesScreen())

        self.push_screen(UnlockScreen(reason), callback=unlocked)

    def _quick_entry_done(self, saved: Entry | None) -> None:
        self.exit(f"Saved the entry for {describe(saved)}." if saved else None)

    # -- locking ---------------------------------------------------------------------------

    async def on_event(self, event: events.Event) -> None:
        if isinstance(
            event, events.Key | events.MouseDown | events.MouseScrollUp | events.MouseScrollDown
        ):
            self.last_input = time.monotonic()
        await super().on_event(event)

    def _unsaved_draft(self) -> bool:
        return any(isinstance(s, EditorScreen) and s.dirty for s in self.screen_stack)

    def lock_if_idle(self) -> None:
        limit = self.settings.auto_lock
        if limit is None or not self.client.unlocked or self._unsaved_draft():
            return  # never throw away a draft; saving a new entry needs no session anyway
        if time.monotonic() - self.last_input >= limit.total_seconds():
            self.lock(f"Locked after {int(limit.total_seconds() // 60)} minutes without input.")

    def action_lock(self) -> None:
        self.lock()

    def lock(self, reason: str | None = None) -> None:
        self.client.lock()
        self.entries.clear()
        while len(self.screen_stack) > 1:
            self.pop_screen()
        log.info("locked%s", f" ({reason})" if reason else "")
        self._ask_password(reason)

    async def action_quit(self) -> None:
        if self._unsaved_draft():

            def answer(discard: bool | None) -> None:
                if discard:
                    self._lock_and_exit()

            self.push_screen(ConfirmScreen("Discard the unsaved entry and quit?"), callback=answer)
            return
        self._lock_and_exit()

    def _lock_and_exit(self) -> None:
        self.client.lock()
        self.exit()

    # -- calling journal-service -------------------------------------------------------------

    def call_api[T](
        self,
        func: Callable[[], T],
        on_success: Callable[[T], None],
        *,
        on_error: Callable[[ApiError], None] | None = None,
        reauth: bool = True,
    ) -> None:
        """Run `func` in a thread. If the session expired, ask for the password and retry once."""
        self._call_api(func, on_success, on_error, reauth)

    @work(thread=True, group="api")
    def _call_api(self, func, on_success, on_error, reauth) -> None:  # type: ignore[no-untyped-def]
        try:
            result = func()
        except Unauthorized as exc:
            if reauth:
                self.call_from_thread(self._reauthenticate, func, on_success, on_error)
            else:
                self.call_from_thread(self._failed, exc, on_error)
        except ApiError as exc:
            self.call_from_thread(self._failed, exc, on_error)
        except Exception as exc:  # a bug: keep the UI, and any draft, alive
            log.exception("unexpected error talking to journal-service")
            self.call_from_thread(self._failed, ApiError(f"unexpected error: {exc}"), on_error)
        else:
            self.call_from_thread(on_success, result)

    def _reauthenticate(self, func, on_success, on_error) -> None:  # type: ignore[no-untyped-def]
        self.client.forget_session()

        def unlocked(ok: bool | None) -> None:
            if ok:
                self._call_api(func, on_success, on_error, False)
            else:
                self._failed(Unauthorized("locked"), on_error)

        reason = "The session expired. Enter the password to continue."
        self.push_screen(UnlockScreen(reason, cancellable=True), callback=unlocked)

    def _failed(self, exc: ApiError, on_error: Callable[[ApiError], None] | None) -> None:
        log.warning("journal-service: %s", exc)
        if on_error is not None:
            on_error(exc)
        else:
            self.notify(str(exc), title="journal-service", severity="error", timeout=10)

    # -- shared actions --------------------------------------------------------------------

    def fetch_entry(self, entry_id: str, then: Callable[[Entry], None]) -> None:
        """Reload one entry (decrypted) into the in-memory list, then call `then`."""

        def got(entry: Entry) -> None:
            self.entries[entry.id] = entry
            then(entry)

        self.call_api(lambda: self.client.entry(entry_id), got)

    def delete_entry(self, entry_id: str, then: Callable[[], None]) -> None:
        def deleted(_result: None) -> None:
            self.entries.pop(entry_id, None)
            log.info("entry %s deleted", entry_id)
            self.notify("Entry deleted.", title="journal")
            then()

        self.call_api(lambda: self.client.delete(entry_id), deleted)
