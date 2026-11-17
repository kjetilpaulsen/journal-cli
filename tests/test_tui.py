import asyncio
from collections.abc import Awaitable, Callable
from contextlib import suppress
from datetime import timedelta
from pathlib import Path

from textual.pilot import Pilot
from textual.widgets import DataTable, Input, Static, TextArea
from textual.worker import WorkerCancelled

from journal_cli.settings import Settings
from journal_cli.tui.app import JournalApp
from journal_cli.tui.screens.dialogs import ConfirmScreen, PasswordScreen
from journal_cli.tui.screens.editor import EditorScreen
from journal_cli.tui.screens.entries import EntriesScreen
from journal_cli.tui.screens.unlock import UnlockScreen
from journal_cli.tui.screens.viewer import ViewerScreen

from .fakes import PASSWORD, FakeClient, make_entry

SETTINGS = Settings(
    socket_path=Path("/nonexistent/api.sock"),
    theme="gruvbox",
    auto_lock=timedelta(minutes=10),
    log_level="INFO",
)

type Scenario = Callable[[Pilot, JournalApp], Awaitable[None]]


def run(client: FakeClient, scenario: Scenario, *, quick_entry: bool = False) -> JournalApp:
    app = JournalApp(client, SETTINGS, quick_entry=quick_entry)  # type: ignore[arg-type]

    async def main() -> None:
        async with app.run_test(size=(110, 30)) as pilot:
            await settle(pilot)
            await scenario(pilot, app)

    asyncio.run(main())
    return app


async def settle(pilot: Pilot) -> None:
    """Let worker threads finish and the UI catch up."""
    for _ in range(3):
        # A screen that dismisses itself cancels its own (already finished) worker.
        with suppress(WorkerCancelled):
            await pilot.app.workers.wait_for_complete()
        await pilot.pause()


async def type_text(pilot: Pilot, text: str) -> None:
    for char in text:
        await pilot.press({"\n": "enter", " ": "space"}.get(char, char))


async def unlock(pilot: Pilot, password: str = PASSWORD) -> None:
    await type_text(pilot, password)
    await pilot.press("enter")
    await settle(pilot)


def rows(app: JournalApp) -> list[str]:
    table = app.screen.query_one(DataTable)
    return [str(table.get_row_at(i)[4]) for i in range(table.row_count)]


def sample() -> FakeClient:
    return FakeClient(
        [
            make_entry("2026-11-17", "Set up journal-service today.\nIt works.", ["work", "setup"]),
            make_entry("2026-11-10", "Long walk by the fjord.", ["outdoors"]),
            make_entry("2019-03-04", "An imported entry.", (), time=None),
        ]
    )


def test_password_first_then_list_newest_first():
    async def scenario(pilot: Pilot, app: JournalApp) -> None:
        assert isinstance(app.screen, UnlockScreen)
        await unlock(pilot, "not the password")
        assert isinstance(app.screen, UnlockScreen)
        assert "Wrong password" in str(app.screen.query_one("#unlock-status", Static).content)
        await unlock(pilot)
        assert isinstance(app.screen, EntriesScreen)
        assert rows(app) == [
            "Set up journal-service today.",
            "Long walk by the fjord.",
            "An imported entry.",
        ]

    run(sample(), scenario)


def test_new_entry_with_line_breaks_and_tags():
    client = sample()

    async def scenario(pilot: Pilot, app: JournalApp) -> None:
        await unlock(pilot)
        await pilot.press("n")
        assert isinstance(app.screen, EditorScreen)
        await type_text(pilot, "First line\nsecond lime")
        await pilot.press("backspace", "backspace", "n", "e")  # fix the typo
        await pilot.press("tab")
        await type_text(pilot, "work, #idea")
        await pilot.press("ctrl+d")
        await settle(pilot)
        assert isinstance(app.screen, EntriesScreen)

    run(client, scenario)
    (saved,) = client.created
    assert saved.body == "First line\nsecond line"
    assert saved.tags == ("work", "idea")
    assert saved.written_at is not None


def test_empty_entry_is_not_saved():
    client = sample()

    async def scenario(pilot: Pilot, app: JournalApp) -> None:
        await unlock(pilot)
        await pilot.press("n")
        await type_text(pilot, "  \n ")
        await pilot.press("ctrl+d")
        await settle(pilot)
        assert isinstance(app.screen, EntriesScreen)

    run(client, scenario)
    assert client.created == []


def test_cancel_asks_before_discarding_and_escape_is_harmless():
    client = sample()

    async def scenario(pilot: Pilot, app: JournalApp) -> None:
        await unlock(pilot)
        await pilot.press("n")
        await type_text(pilot, "a draft")
        await pilot.press("escape")  # vim reflex: nothing happens
        assert isinstance(app.screen, EditorScreen)
        await pilot.press("ctrl+x")
        assert isinstance(app.screen, ConfirmScreen)
        await pilot.press("n")  # keep writing
        assert app.screen.query_one(TextArea).text == "a draft"
        await pilot.press("ctrl+x", "y")
        await settle(pilot)
        assert isinstance(app.screen, EntriesScreen)

    run(client, scenario)
    assert client.created == []


def test_failed_save_keeps_the_text():
    client = sample()

    async def scenario(pilot: Pilot, app: JournalApp) -> None:
        await unlock(pilot)
        await pilot.press("n")
        await type_text(pilot, "precious words")
        client.unavailable = True
        await pilot.press("ctrl+d")
        await settle(pilot)
        assert isinstance(app.screen, EditorScreen)
        assert app.screen.query_one(TextArea).text == "precious words"
        client.unavailable = False
        await pilot.press("ctrl+d")
        await settle(pilot)
        assert isinstance(app.screen, EntriesScreen)

    run(client, scenario)
    assert [e.body for e in client.created] == ["precious words"]


def test_search_by_date_tag_and_text():
    async def scenario(pilot: Pilot, app: JournalApp) -> None:
        await unlock(pilot)
        await pilot.press("slash")
        await type_text(pilot, "#out")
        assert rows(app) == ["Long walk by the fjord."]
        await pilot.press(*["backspace"] * 4)
        await type_text(pilot, "2019")
        assert rows(app) == ["An imported entry."]
        await pilot.press(*["backspace"] * 4)
        await type_text(pilot, "journal works")  # all words, anywhere in the text
        assert rows(app) == ["Set up journal-service today."]
        await pilot.press("enter")  # keep the filter, back to the list
        assert isinstance(app.focused, DataTable)
        await pilot.press("escape")  # clear it
        assert len(rows(app)) == 3

    run(sample(), scenario)


def test_typing_in_search_does_not_trigger_shortcuts():
    async def scenario(pilot: Pilot, app: JournalApp) -> None:
        await unlock(pilot)
        await pilot.press("slash")
        await type_text(pilot, "nqdl")
        assert isinstance(app.screen, EntriesScreen)
        assert app.screen.query_one("#search", Input).value == "nqdl"

    run(sample(), scenario)


def test_view_edit_and_delete():
    client = sample()

    async def scenario(pilot: Pilot, app: JournalApp) -> None:
        await unlock(pilot)
        await pilot.press("j", "enter")  # second entry
        assert isinstance(app.screen, ViewerScreen)
        assert app.screen.entry.body == "Long walk by the fjord."
        await pilot.press("e")
        await pilot.press("end")
        await type_text(pilot, " Cold.")
        await pilot.press("ctrl+d")
        await settle(pilot)
        assert isinstance(app.screen, ViewerScreen)
        assert app.screen.entry.body == "Long walk by the fjord. Cold."
        await pilot.press("d", "y")
        await settle(pilot)
        assert isinstance(app.screen, EntriesScreen)
        assert len(rows(app)) == 2

    run(client, scenario)
    assert len(client.store) == 2


def test_lock_and_auto_lock():
    async def scenario(pilot: Pilot, app: JournalApp) -> None:
        await unlock(pilot)
        await pilot.press("l")
        assert isinstance(app.screen, UnlockScreen)
        assert app.entries == {}
        await unlock(pilot)
        app.last_input -= 11 * 60
        app.lock_if_idle()
        await settle(pilot)
        assert isinstance(app.screen, UnlockScreen)
        assert "10 minutes" in str(app.screen.query_one("#unlock-status", Static).content)

    run(sample(), scenario)


def test_auto_lock_never_discards_a_draft():
    async def scenario(pilot: Pilot, app: JournalApp) -> None:
        await unlock(pilot)
        await pilot.press("n")
        await type_text(pilot, "half a thought")
        app.last_input -= 60 * 60
        app.lock_if_idle()
        await settle(pilot)
        assert isinstance(app.screen, EditorScreen)

    run(sample(), scenario)


def test_expired_session_asks_for_the_password_and_retries():
    client = sample()

    async def scenario(pilot: Pilot, app: JournalApp) -> None:
        await unlock(pilot)
        await pilot.press("e")
        await pilot.press("end")
        await type_text(pilot, " Edited.")
        client.expire_next = True
        await pilot.press("ctrl+d")
        await settle(pilot)
        assert isinstance(app.screen, UnlockScreen)
        await unlock(pilot)
        assert isinstance(app.screen, EntriesScreen)

    run(client, scenario)
    assert any(e.body.endswith("Edited.") for e in client.store.values())


def test_change_password():
    client = sample()
    new = "a much better passphrase"

    async def scenario(pilot: Pilot, app: JournalApp) -> None:
        await unlock(pilot)
        await pilot.press("p")
        assert isinstance(app.screen, PasswordScreen)
        for value in ("wrong current pw", new, new):
            await type_text(pilot, value)
            await pilot.press("enter")
        await settle(pilot)
        status = str(app.screen.query_one("#password-status", Static).content)
        assert "current password is wrong" in status
        for value in (PASSWORD, new, new):
            await type_text(pilot, value)
            await pilot.press("enter")
        await settle(pilot)
        assert isinstance(app.screen, EntriesScreen)

    run(client, scenario)
    assert client.password == new


def test_quick_entry_needs_no_password():
    client = sample()

    async def scenario(pilot: Pilot, app: JournalApp) -> None:
        assert isinstance(app.screen, EditorScreen)
        await type_text(pilot, "Written in seconds.")
        await pilot.press("ctrl+d")
        await settle(pilot)

    app = run(client, scenario, quick_entry=True)
    assert [e.body for e in client.created] == ["Written in seconds."]
    assert app.return_value is not None and app.return_value.startswith("Saved the entry for")
    assert not client.unlocked


def test_quit_with_a_draft_asks_first():
    async def scenario(pilot: Pilot, app: JournalApp) -> None:
        await unlock(pilot)
        await pilot.press("n")
        await type_text(pilot, "unsaved")
        await pilot.press("ctrl+q")
        assert isinstance(app.screen, ConfirmScreen)
        await pilot.press("n")
        assert isinstance(app.screen, EditorScreen)

    run(sample(), scenario)


def test_service_down_and_not_initialized_are_explained():
    down = FakeClient()
    down.unavailable = True

    async def unreachable(pilot: Pilot, app: JournalApp) -> None:
        await unlock(pilot)
        assert "not running" in str(app.screen.query_one("#unlock-status", Static).content)

    run(down, unreachable)

    async def no_password_yet(pilot: Pilot, app: JournalApp) -> None:
        await unlock(pilot)
        assert "journal-service init" in str(app.screen.query_one("#unlock-status", Static).content)

    run(FakeClient(initialized=False), no_password_yet)
