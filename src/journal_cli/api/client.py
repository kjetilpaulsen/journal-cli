"""HTTP over journal-service's Unix socket, using only the standard library.

One connection per request: on a local socket that costs microseconds, and it keeps the
client safe to use from the TUI's worker threads. The session token lives in this object
only (memory), never on disk.
"""

import http.client
import json
import logging
import socket
from collections.abc import Sequence
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from journal_cli.api.errors import ApiError, ServiceUnavailable, Unauthorized, error_for_status
from journal_cli.api.models import Entry, Session

log = logging.getLogger(__name__)


class _UnixHTTPConnection(http.client.HTTPConnection):
    def __init__(self, path: Path, timeout: float) -> None:
        super().__init__("localhost", timeout=timeout)
        self._path = path

    def connect(self) -> None:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(self.timeout)
        try:
            sock.connect(str(self._path))
        except BaseException:
            sock.close()
            raise
        self.sock = sock


class JournalClient:
    def __init__(self, socket_path: Path, *, timeout: float = 60.0) -> None:
        self.socket_path = socket_path
        self.timeout = timeout
        self._token: str | None = None

    @property
    def unlocked(self) -> bool:
        return self._token is not None

    # -- session -------------------------------------------------------------------------

    def health(self) -> dict[str, Any]:
        return self._request("GET", "/health")

    def unlock(self, password: str) -> Session:
        data = self._request("POST", "/session", {"password": password})
        self._token = data["token"]
        return Session(
            token=data["token"], idle_timeout=timedelta(seconds=data["idle_timeout_seconds"])
        )

    def lock(self) -> None:
        """Close the session on the service (best effort) and forget the token."""
        token, self._token = self._token, None
        if token is None:
            return
        try:
            self._request("DELETE", "/session", token=token)
        except ApiError as exc:  # the service may be gone or the session already expired
            log.info("lock: %s", exc)

    def forget_session(self) -> None:
        self._token = None

    def change_password(self, current: str, new: str) -> None:
        self._request("POST", "/password", {"current_password": current, "new_password": new})

    # -- entries -------------------------------------------------------------------------

    def entries(self, *, content: bool = False) -> list[Entry]:
        path = "/entries?content=true" if content else "/entries"
        data = self._request("GET", path, token=self._session_token() if content else None)
        return [Entry.from_json(item) for item in data["entries"]]

    def entry(self, entry_id: str) -> Entry:
        return Entry.from_json(
            self._request("GET", f"/entries/{entry_id}", token=self._session_token())
        )

    def create(self, body: str, tags: Sequence[str], written_at: datetime | None = None) -> Entry:
        """Create an entry. Needs no session: entries are encrypted to the public key."""
        payload: dict[str, Any] = {"body": body, "tags": list(tags)}
        if written_at is not None:
            payload["written_at"] = written_at.isoformat()
        return Entry.from_json(self._request("POST", "/entries", payload))

    def update(self, entry_id: str, body: str, tags: Sequence[str]) -> Entry:
        data = self._request(
            "PUT",
            f"/entries/{entry_id}",
            {"body": body, "tags": list(tags)},
            token=self._session_token(),
        )
        return Entry.from_json(data)

    def delete(self, entry_id: str) -> None:
        self._request("DELETE", f"/entries/{entry_id}", token=self._session_token())

    # -- transport -----------------------------------------------------------------------

    def _session_token(self) -> str:
        if self._token is None:
            raise Unauthorized("locked; unlock first")
        return self._token

    def _request(
        self, method: str, path: str, body: Any = None, *, token: str | None = None
    ) -> Any:
        headers = {"Accept": "application/json"}
        payload = None
        if body is not None:
            payload = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"
        if token is not None:
            headers["Authorization"] = f"Bearer {token}"

        connection = _UnixHTTPConnection(self.socket_path, self.timeout)
        try:
            connection.request(method, path, body=payload, headers=headers)
            response = connection.getresponse()
            raw = response.read()
        except (FileNotFoundError, ConnectionRefusedError) as exc:
            raise ServiceUnavailable(
                f"journal-service is not running (no socket at {self.socket_path})"
            ) from exc
        except OSError as exc:  # includes timeouts
            raise ServiceUnavailable(f"cannot reach journal-service: {exc}") from exc
        finally:
            connection.close()

        try:
            data = json.loads(raw) if raw else None
        except ValueError:
            data = None
        if response.status >= 400:
            message = data.get("error") if isinstance(data, dict) else None
            raise error_for_status(response.status)(
                message or f"HTTP {response.status}", response.status
            )
        return data
