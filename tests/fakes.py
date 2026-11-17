"""An in-memory stand-in for JournalClient: same methods, same errors."""

from collections.abc import Iterable, Sequence
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta, timezone
from uuid import uuid4

from journal_cli.api import (
    Conflict,
    Entry,
    Invalid,
    NotFound,
    ServiceUnavailable,
    Session,
    Unauthorized,
)

PASSWORD = "correct horse battery staple"
OSLO = timezone(timedelta(hours=1))


def make_entry(day: str, body: str, tags: Sequence[str] = (), time: str | None = "20:00") -> Entry:
    when = datetime.fromisoformat(f"{day}T{time}:00+01:00") if time else None
    return Entry(
        id=uuid4().hex,
        entry_date=date.fromisoformat(day),
        written_at=when,
        created_at=datetime.now(UTC),
        updated_at=None,
        body=body,
        tags=tuple(tags),
    )


class FakeClient:
    def __init__(self, entries: Iterable[Entry] = (), *, initialized: bool = True) -> None:
        self.password = PASSWORD
        self.store = {entry.id: entry for entry in entries}
        self.initialized = initialized
        self.unavailable = False
        self.expire_next = False  # the next call that needs a session gets a 401
        self.created: list[Entry] = []
        self._token: str | None = None

    @property
    def unlocked(self) -> bool:
        return self._token is not None

    def unlock(self, password: str) -> Session:
        self._reachable()
        if not self.initialized:
            raise Conflict("no keypair yet; run `journal-service init`", 409)
        if password != self.password:
            raise Unauthorized("wrong password", 401)
        self._token = "token"
        return Session(token="token", idle_timeout=timedelta(minutes=15))

    def lock(self) -> None:
        self._token = None

    def forget_session(self) -> None:
        self._token = None

    def change_password(self, current: str, new: str) -> None:
        self._reachable()
        if current != self.password:
            raise Unauthorized("wrong password", 401)
        if len(new) < 12:
            raise Invalid("password must be at least 12 characters", 422)
        self.password = new

    def entries(self, *, content: bool = False) -> list[Entry]:
        if content:
            self._session()
        return sorted(self.store.values(), key=lambda e: e.sort_key)

    def entry(self, entry_id: str) -> Entry:
        self._session()
        if entry_id not in self.store:
            raise NotFound(f"no entry {entry_id}", 404)
        return self.store[entry_id]

    def create(self, body: str, tags: Sequence[str], written_at: datetime | None = None) -> Entry:
        self._reachable()
        moment = written_at or datetime.now(OSLO)
        entry = make_entry(moment.date().isoformat(), body, tags, f"{moment:%H:%M}")
        self.store[entry.id] = entry
        self.created.append(entry)
        return replace(entry, body="", tags=())  # like the service: metadata only

    def update(self, entry_id: str, body: str, tags: Sequence[str]) -> Entry:
        self._session()
        entry = replace(
            self.store[entry_id], body=body, tags=tuple(tags), updated_at=datetime.now(UTC)
        )
        self.store[entry_id] = entry
        return replace(entry, body="", tags=())

    def delete(self, entry_id: str) -> None:
        self._session()
        del self.store[entry_id]

    def _reachable(self) -> None:
        if self.unavailable:
            raise ServiceUnavailable("journal-service is not running")

    def _session(self) -> None:
        self._reachable()
        if self.expire_next:
            self.expire_next = False
            self._token = None
            raise Unauthorized("session expired or unknown; unlock again", 401)
        if self._token is None:
            raise Unauthorized("missing session token", 401)
