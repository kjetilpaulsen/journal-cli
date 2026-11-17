"""Screens: unlock, entry list, viewer, editor, and the small dialogs."""

from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from journal_cli.tui.app import JournalApp


class AppAccess:
    """Typed access to the running JournalApp from a screen."""

    @property
    def journal(self) -> JournalApp:
        return cast("JournalApp", self.app)  # type: ignore[attr-defined]
