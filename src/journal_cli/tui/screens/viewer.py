"""Reading one entry."""

from typing import ClassVar

from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import VerticalScroll
from textual.screen import Screen
from textual.widgets import Footer, Static

from journal_cli.api import Entry
from journal_cli.tui.format import tags_text
from journal_cli.tui.screens import AppAccess
from journal_cli.tui.screens.dialogs import ConfirmScreen
from journal_cli.tui.screens.editor import EditorScreen


def _heading(entry: Entry) -> str:
    when = f"{entry.entry_date:%A %d %B %Y}"
    if entry.written_at:
        when += f", {entry.written_at:%H:%M}"
    tags = tags_text(entry.tags)
    return f"{when}\n{tags}" if tags else when


class ViewerScreen(AppAccess, Screen[None]):
    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("escape,q", "back", "Back", key_display="esc"),
        Binding("e", "edit", "Edit"),
        Binding("d", "delete", "Delete"),
        Binding("j", "scroll(1)", show=False),
        Binding("k", "scroll(-1)", show=False),
        Binding("g", "jump(False)", show=False),
        Binding("G", "jump(True)", show=False),
    ]

    def __init__(self, entry: Entry) -> None:
        super().__init__()
        self.entry = entry

    def compose(self) -> ComposeResult:
        yield Footer(show_command_palette=False)
        yield Static(_heading(self.entry), id="viewer-heading", markup=False)
        with VerticalScroll(id="viewer-scroll"):
            yield Static(self.entry.body, id="viewer-body", markup=False)

    def on_mount(self) -> None:
        self.query_one(VerticalScroll).focus()

    def show(self, entry: Entry) -> None:
        self.entry = entry
        self.query_one("#viewer-heading", Static).update(_heading(entry))
        self.query_one("#viewer-body", Static).update(entry.body)

    def action_back(self) -> None:
        self.dismiss(None)

    def action_scroll(self, lines: int) -> None:
        self.query_one(VerticalScroll).scroll_relative(y=lines, animate=False)

    def action_jump(self, to_end: bool) -> None:
        scroll = self.query_one(VerticalScroll)
        if to_end:
            scroll.scroll_end(animate=False)
        else:
            scroll.scroll_home(animate=False)

    def action_edit(self) -> None:
        def edited(saved: Entry | None) -> None:
            if saved is not None:
                self.journal.fetch_entry(saved.id, self.show)

        self.app.push_screen(EditorScreen(self.entry), callback=edited)

    def action_delete(self) -> None:
        def answer(yes: bool | None) -> None:
            if yes:
                self.journal.delete_entry(self.entry.id, lambda: self.dismiss(None))

        self.app.push_screen(
            ConfirmScreen("Delete this entry? This cannot be undone."), callback=answer
        )
