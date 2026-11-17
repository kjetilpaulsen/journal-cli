"""Values exchanged with journal-service."""

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any


@dataclass(frozen=True, slots=True)
class Session:
    token: str
    idle_timeout: timedelta


@dataclass(frozen=True, slots=True)
class Entry:
    id: str
    entry_date: date
    written_at: datetime | None  # in the writer's own UTC offset; None for date-only entries
    created_at: datetime
    updated_at: datetime | None
    body: str = ""  # empty unless the entry was fetched decrypted
    tags: tuple[str, ...] = ()

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> Entry:
        return cls(
            id=data["id"],
            entry_date=date.fromisoformat(data["entry_date"]),
            written_at=_timestamp(data.get("written_at")),
            created_at=datetime.fromisoformat(data["created_at"]),
            updated_at=_timestamp(data.get("updated_at")),
            body=data.get("body", ""),
            tags=tuple(data.get("tags", ())),
        )

    @property
    def sort_key(self) -> tuple[date, datetime, datetime]:
        # Date-only entries sort before timed ones on the same day, like journal-service does.
        return (
            self.entry_date,
            self.written_at or datetime.min.replace(tzinfo=self.created_at.tzinfo),
            self.created_at,
        )

    @property
    def first_line(self) -> str:
        return next((line.strip() for line in self.body.splitlines() if line.strip()), "")


def _timestamp(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None
