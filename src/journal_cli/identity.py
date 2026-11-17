"""Static identity of the application."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AppIdentity:
    app_name: str  # used for the XDG directory names
    description: str
    service_name: str  # the backend whose socket we connect to


IDENTITY = AppIdentity(
    app_name="journal-cli",
    description="Terminal frontend for journal-service",
    service_name="journal-service",
)
