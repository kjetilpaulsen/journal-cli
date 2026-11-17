"""Search queries for the entry list.

    2026-11         date prefix: entries whose date starts with it (several: any of them)
    #work           tag prefix: entries with a tag starting with "work" (several: all of them)
    meeting         word: in the text or a tag, case-insensitive (several: all of them)
    "long walk"     quotes keep a phrase together

Everything runs on decrypted entries in memory; nothing is sent to the service.
"""

import re
import shlex
from dataclasses import dataclass

from journal_cli.api.models import Entry

_DATE = re.compile(r"\d{4}(-\d{0,2}){0,2}")


@dataclass(frozen=True, slots=True)
class Query:
    dates: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()
    words: tuple[str, ...] = ()

    def __bool__(self) -> bool:
        return bool(self.dates or self.tags or self.words)


def parse_query(text: str) -> Query:
    try:
        tokens = shlex.split(text)
    except ValueError:  # an unbalanced quote while still typing
        tokens = text.split()
    dates: list[str] = []
    tags: list[str] = []
    words: list[str] = []
    for token in tokens:
        if token.startswith("#"):
            if tag := token[1:].casefold():
                tags.append(tag)
        elif _DATE.fullmatch(token):
            dates.append(token)
        elif token:
            words.append(token.casefold())
    return Query(tuple(dates), tuple(tags), tuple(words))


def matches(query: Query, entry: Entry) -> bool:
    if query.dates and not any(entry.entry_date.isoformat().startswith(d) for d in query.dates):
        return False
    tags = [tag.casefold() for tag in entry.tags]
    if not all(any(tag.startswith(wanted) for tag in tags) for wanted in query.tags):
        return False
    text = entry.body.casefold()
    return all(word in text or any(word in tag for tag in tags) for word in query.words)
