"""Client for the journal-service HTTP API on its Unix socket."""

from journal_cli.api.client import JournalClient
from journal_cli.api.errors import (
    ApiError,
    Conflict,
    Invalid,
    NotFound,
    ServiceUnavailable,
    Unauthorized,
)
from journal_cli.api.models import Entry, Session

__all__ = [
    "ApiError",
    "Conflict",
    "Entry",
    "Invalid",
    "JournalClient",
    "NotFound",
    "ServiceUnavailable",
    "Session",
    "Unauthorized",
]
