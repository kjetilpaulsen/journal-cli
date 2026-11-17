"""The main screen: a menu bar of keys, the list of entries, search, and a status line."""

from typing import ClassVar

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.events import Resize
from textual.screen import Screen
from textual.widgets import DataTable, Footer, Input, Static

from journal_cli.api import Entry
from journal_cli.tui.format import clock, describe, tags_text, truncate, weekday
from journal_cli.tui.screens import AppAccess
from journal_cli.tui.screens.dialogs import ConfirmScreen, PasswordScreen
from journal_cli.tui.screens.editor import EditorScreen
from journal_cli.tui.screens.viewer import ViewerScreen
from journal_cli.tui.search import matches, parse_query

SEARCH_HELP = 'search: words   #tag   2026-11   "a phrase"'


class EntryTable(DataTable[str | Text]):
    """The list, with Enter labelled in the menu bar."""

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("enter", "select_cursor", "Open", key_display="⏎"),
    ]


class EntriesScreen(AppAccess, Screen[None]):
    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("n", "new", "New"),
        Binding("e", "edit", "Edit"),
        Binding("d", "delete", "Delete"),
        Binding("slash", "search", "Search", key_display="/"),
        Binding("p", "password", "Password"),
        Binding("l", "app.lock", "Lock"),
        Binding("r", "reload", "Reload"),
        Binding("q", "app.quit", "Quit"),
        Binding("j", "move(1)", show=False),
        Binding("k", "move(-1)", show=False),
        Binding("g", "jump(False)", show=False),
        Binding("G", "jump(True)", show=False),
        Binding("escape", "clear_search", "Clear search", key_display="esc"),
    ]

    def compose(self) -> ComposeResult:
        yield Footer(show_command_palette=False)
        yield EntryTable(id="entries", cursor_type="row", zebra_stripes=True)
        yield Input(placeholder=SEARCH_HELP, id="search", compact=True)
        yield Static("", id="status")

    def on_mount(self) -> None:
        table = self.query_one(DataTable)
        for label, key in (
            ("Date", "date"),
            ("Day", "day"),
            ("Time", "time"),
            ("Tags", "tags"),
            ("Entry", "text"),
        ):
            table.add_column(label, key=key)
        table.focus()
        self.reload()

    # -- data ------------------------------------------------------------------------------

    def action_reload(self) -> None:
        self.reload()

    def reload(self, select: str | None = None) -> None:
        self._status("Loading entries…")

        def loaded(entries: list[Entry]) -> None:
            self.journal.entries = {entry.id: entry for entry in entries}
            self.show_entries(select)

        self.journal.call_api(lambda: self.journal.client.entries(content=True), loaded)

    def show_entries(self, select: str | None = None) -> None:
        table = self.query_one(DataTable)
        select = select or self._selected_id()
        query = parse_query(self.query_one("#search", Input).value)
        everything = sorted(self.journal.entries.values(), key=lambda e: e.sort_key, reverse=True)
        shown = [entry for entry in everything if matches(query, entry)] if query else everything

        table.clear()
        text_width = max(20, self.size.width - 50)
        for entry in shown:
            table.add_row(
                entry.entry_date.isoformat(),
                weekday(entry),
                clock(entry),
                Text(truncate(tags_text(entry.tags), 24), style="italic"),
                truncate(entry.first_line, text_width),
                key=entry.id,
            )
        ids = [entry.id for entry in shown]
        if select in ids:
            table.move_cursor(row=ids.index(select), animate=False)

        total = len(everything)
        if query:
            self._status(f"{len(shown)} of {total} entries match")
        else:
            self._status(f"{total} entr{'y' if total == 1 else 'ies'}")

    def on_resize(self, _event: Resize) -> None:
        if self.journal.entries:
            self.show_entries()

    def _selected(self) -> Entry | None:
        entry_id = self._selected_id()
        return self.journal.entries.get(entry_id) if entry_id else None

    def _selected_id(self) -> str | None:
        table = self.query_one(DataTable)
        if not table.row_count:
            return None
        return table.coordinate_to_cell_key(table.cursor_coordinate).row_key.value

    def _status(self, text: str) -> None:
        self.query_one("#status", Static).update(text)

    # -- actions ---------------------------------------------------------------------------

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        event.stop()
        self.action_open()

    def action_open(self) -> None:  # also reached through EntryTable's Enter
        entry = self._selected()
        if entry is not None:
            self.app.push_screen(ViewerScreen(entry), callback=lambda _: self.show_entries())

    def action_new(self) -> None:
        self.app.push_screen(EditorScreen(), callback=self._after_edit)

    def action_edit(self) -> None:
        entry = self._selected()
        if entry is not None:
            self.app.push_screen(EditorScreen(entry), callback=self._after_edit)

    def _after_edit(self, saved: Entry | None) -> None:
        if saved is not None:
            self.journal.fetch_entry(saved.id, lambda entry: self.show_entries(select=entry.id))

    def action_delete(self) -> None:
        entry = self._selected()
        if entry is None:
            return

        def answer(yes: bool | None) -> None:
            if yes:
                self.journal.delete_entry(entry.id, self.show_entries)

        self.app.push_screen(
            ConfirmScreen(f"Delete the entry from {describe(entry)}?"), callback=answer
        )

    def action_password(self) -> None:
        self.app.push_screen(PasswordScreen())

    def action_move(self, rows: int) -> None:
        table = self.query_one(DataTable)
        if rows > 0:
            table.action_cursor_down()
        else:
            table.action_cursor_up()

    def action_jump(self, to_end: bool) -> None:
        table = self.query_one(DataTable)
        if table.row_count:
            table.move_cursor(row=table.row_count - 1 if to_end else 0, animate=False)

    # -- search ----------------------------------------------------------------------------

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        if action == "clear_search":  # only offered while a search is open
            return self.query_one("#search", Input).has_class("active")
        return True

    def action_search(self) -> None:
        search = self.query_one("#search", Input)
        search.add_class("active")
        search.focus()
        self.refresh_bindings()

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "search":
            self.show_entries()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "search":
            event.stop()
            if not event.value:
                event.input.remove_class("active")
                self.refresh_bindings()
            self.query_one(DataTable).focus()

    def action_clear_search(self) -> None:
        search = self.query_one("#search", Input)
        if search.value or search.has_class("active"):
            search.value = ""
            search.remove_class("active")
            self.refresh_bindings()
            self.query_one(DataTable).focus()
            self.show_entries()
