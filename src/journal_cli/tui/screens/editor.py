"""Writing and editing entries.

Plain multi-line editing: Enter is a line break, Backspace, Ctrl+W (delete word), Ctrl+U
(delete to line start), Ctrl+Z/Ctrl+Y (undo/redo). No modes. Ctrl+D saves, Ctrl+X cancels
(and asks first if there is text). Escape does nothing, so a reflexive vim Escape is harmless.
"""

import logging
from datetime import datetime
from typing import ClassVar

from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Horizontal
from textual.screen import Screen
from textual.widgets import Footer, Input, Static, TextArea

from journal_cli.api import ApiError, Entry
from journal_cli.tui.format import describe, parse_tags
from journal_cli.tui.screens import AppAccess
from journal_cli.tui.screens.dialogs import ConfirmScreen

log = logging.getLogger(__name__)


class EditorScreen(AppAccess, Screen[Entry | None]):
    """Dismisses with the saved entry, or None when cancelled or empty."""

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("ctrl+d", "save", "Save", key_display="^d", priority=True),
        Binding("ctrl+x", "cancel", "Cancel", key_display="^x", priority=True),
    ]

    def __init__(self, entry: Entry | None = None) -> None:
        super().__init__()
        self.entry = entry
        # A new entry is stamped with the moment you started writing, not when you saved.
        self.started_at = datetime.now().astimezone().replace(microsecond=0)
        self._original = (entry.body, ", ".join(entry.tags)) if entry else ("", "")
        self._saving = False

    def compose(self) -> ComposeResult:
        yield Footer(show_command_palette=False)
        yield Static(self._title(), id="editor-title")
        yield TextArea(
            self._original[0],
            id="editor-body",
            soft_wrap=True,
            highlight_cursor_line=False,
            placeholder="Write…  (ctrl+d saves, ctrl+x cancels, tab moves to the tags)",
        )
        with Horizontal(id="editor-tags-row"):
            yield Static("tags", id="editor-tags-label")
            yield Input(
                self._original[1],
                placeholder="work, idea   (optional · tab switches between text and tags)",
                id="editor-tags",
                compact=True,
            )

    def on_mount(self) -> None:
        body = self.query_one(TextArea)
        body.focus()
        body.move_cursor(body.document.end)

    @property
    def dirty(self) -> bool:
        current = (self.query_one(TextArea).text, self.query_one("#editor-tags", Input).value)
        return current != self._original

    def _title(self, note: str = "") -> str:
        if self.entry is None:
            title = f"New entry · {self.started_at:%a %Y-%m-%d %H:%M}"
        else:
            title = f"Editing {describe(self.entry)}"
        return f"{title}   {note}" if note else title

    def on_input_submitted(self, event: Input.Submitted) -> None:
        event.stop()  # Enter in the tags field goes back to the text
        self.query_one(TextArea).focus()

    def action_save(self) -> None:
        if self._saving:
            return
        body = self.query_one(TextArea).text
        if not body.strip():
            self.app.notify("Empty entry: nothing saved.", title="journal")
            self.dismiss(None)
            return
        tags = parse_tags(self.query_one("#editor-tags", Input).value)

        client = self.journal.client
        if self.entry is None:
            started_at = self.started_at

            def save() -> Entry:
                return client.create(body, tags, written_at=started_at)
        else:
            entry_id = self.entry.id

            def save() -> Entry:
                return client.update(entry_id, body, tags)

        self._saving = True
        self.query_one("#editor-title", Static).update(self._title("saving…"))
        self.journal.call_api(save, self._saved, on_error=self._failed)

    def _saved(self, entry: Entry) -> None:
        log.info("entry %s saved", entry.id)
        self.dismiss(entry)

    def _failed(self, exc: ApiError) -> None:
        # Keep the editor and its text: nothing is lost when the service is unreachable.
        self._saving = False
        self.query_one("#editor-title", Static).update(self._title())
        self.app.notify(f"Not saved: {exc}", title="journal", severity="error", timeout=10)

    def action_cancel(self) -> None:
        if not self.dirty:
            self.dismiss(None)
            return
        question = "Discard this entry?" if self.entry is None else "Discard your changes?"

        def answer(discard: bool | None) -> None:
            if discard:
                self.dismiss(None)

        self.app.push_screen(ConfirmScreen(question), callback=answer)
