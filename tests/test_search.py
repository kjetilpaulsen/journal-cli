import pytest

from journal_cli.tui.format import parse_tags
from journal_cli.tui.search import Query, matches, parse_query

from .fakes import make_entry

ENTRY = make_entry("2026-11-17", "Met Ola at the café.\nLong walk afterwards.", ["work", "Friends"])


def test_parse_query():
    assert parse_query('2026-11 #work walk "long walk"') == Query(
        dates=("2026-11",), tags=("work",), words=("walk", "long walk")
    )
    assert parse_query('"unbalanced') == Query(words=('"unbalanced',))
    assert not parse_query("  #  ")


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("", True),
        ("2026", True),
        ("2026-1", True),  # prefix while typing 2026-11
        ("2026-11-17", True),
        ("2025 2026", True),  # any of several dates
        ("2026-10", False),
        ("#work", True),
        ("#fri", True),  # tag prefix, case-insensitive
        ("#work #friends", True),  # all tags
        ("#work #home", False),
        ("café walk", True),  # all words, case-insensitive
        ("CAFÉ", True),
        ("friends", True),  # plain words also match tags
        ('"long walk"', True),
        ('"walk long"', False),
        ("ola #work 2026-11", True),
        ("ola #home", False),
    ],
)
def test_matches(text: str, expected: bool):
    assert matches(parse_query(text), ENTRY) is expected


def test_parse_tags():
    assert parse_tags("work, #idea  home,,") == ["work", "idea", "home"]
    assert parse_tags("  ") == []
