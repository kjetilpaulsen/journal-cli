"""How entries are shown: dates, times, tags."""

import re

from journal_cli.api.models import Entry

WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


def weekday(entry: Entry) -> str:
    return WEEKDAYS[entry.entry_date.weekday()]


def clock(entry: Entry) -> str:
    """Wall-clock time where it was written, e.g. 23:45; empty for date-only entries."""
    return f"{entry.written_at:%H:%M}" if entry.written_at else ""


def describe(entry: Entry) -> str:
    """Short label, e.g. 'Tue 2026-11-17 19:46'."""
    return " ".join(
        part for part in (weekday(entry), entry.entry_date.isoformat(), clock(entry)) if part
    )


def tags_text(tags: tuple[str, ...]) -> str:
    return " ".join(f"#{tag}" for tag in tags)


def parse_tags(text: str) -> list[str]:
    """'work, #idea  home' -> ['work', 'idea', 'home']."""
    return [tag.lstrip("#") for tag in re.split(r"[,\s]+", text) if tag.lstrip("#")]


def truncate(text: str, width: int) -> str:
    return text if len(text) <= width else text[: max(0, width - 1)] + "…"
