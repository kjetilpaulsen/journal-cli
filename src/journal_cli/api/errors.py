"""Errors raised by the client, one per kind of failure the TUI handles differently."""


class ApiError(Exception):
    def __init__(self, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


class ServiceUnavailable(ApiError):
    """The socket is missing, refuses connections or does not answer."""


class Unauthorized(ApiError):
    """401: wrong password, or the session expired (journal-service locks after idling)."""


class NotFound(ApiError):
    """404."""


class Conflict(ApiError):
    """409: e.g. journal-service has no password yet (`journal-service init`)."""


class Invalid(ApiError):
    """413/422: the service rejected the input; the message says why."""


def error_for_status(status: int) -> type[ApiError]:
    return {401: Unauthorized, 404: NotFound, 409: Conflict, 413: Invalid, 422: Invalid}.get(
        status, ApiError
    )
