"""JournalClient against a tiny HTTP server on a real Unix socket."""

import json
import socketserver
import threading
from collections.abc import Iterator
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from typing import ClassVar

import pytest

from journal_cli.api import Conflict, Invalid, JournalClient, ServiceUnavailable, Unauthorized

ENTRY = {
    "id": "0196f3a2-0000-7000-8000-000000000001",
    "entry_date": "2026-11-17",
    "written_at": "2026-11-17T23:45:00+01:00",
    "created_at": "2026-11-17T22:45:00+00:00",
    "updated_at": None,
}


class FakeService(BaseHTTPRequestHandler):
    """Records requests; answers from `responses[(method, path)] = (status, body)`."""

    responses: ClassVar[dict[tuple[str, str], tuple[int, object]]] = {}
    seen: ClassVar[list[tuple[str, str, dict[str, str], object]]] = []

    def _handle(self) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(length)) if length else None
        self.seen.append((self.command, self.path, dict(self.headers), body))
        status, answer = self.responses.get((self.command, self.path), (404, {"error": "no route"}))
        payload = b"" if answer is None else json.dumps(answer).encode()
        self.send_response(status)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    do_GET = do_POST = do_PUT = do_DELETE = _handle

    def log_message(self, *_args: object) -> None:
        pass


class UnixServer(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
    daemon_threads = True

    def get_request(self):  # type: ignore[no-untyped-def]
        request, _ = super().get_request()
        return request, ("local", 0)  # BaseHTTPRequestHandler expects a (host, port)


@pytest.fixture
def service(tmp_path: Path) -> Iterator[Path]:
    socket_path = tmp_path / "api.sock"
    FakeService.responses = {}
    FakeService.seen = []
    server = UnixServer(str(socket_path), FakeService)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield socket_path
    server.shutdown()
    server.server_close()


def test_unlock_then_session_calls_carry_the_token(service: Path):
    FakeService.responses = {
        ("POST", "/session"): (201, {"token": "t0k3n", "idle_timeout_seconds": 900}),
        ("GET", "/entries?content=true"): (
            200,
            {"entries": [ENTRY | {"body": "hi", "tags": ["a"]}]},
        ),
        ("DELETE", "/session"): (204, None),
    }
    client = JournalClient(service)
    session = client.unlock("secret password")
    assert session.idle_timeout == timedelta(minutes=15)
    assert client.unlocked

    (entry,) = client.entries(content=True)
    assert (entry.body, entry.tags) == ("hi", ("a",))
    assert entry.written_at == datetime(2026, 11, 17, 23, 45, tzinfo=timezone(timedelta(hours=1)))
    assert entry.entry_date.isoformat() == "2026-11-17"

    client.lock()
    assert not client.unlocked
    methods = [
        (method, path, headers.get("Authorization"))
        for method, path, headers, _ in FakeService.seen
    ]
    assert methods == [
        ("POST", "/session", None),  # the password goes in the body, never in a header
        ("GET", "/entries?content=true", "Bearer t0k3n"),
        ("DELETE", "/session", "Bearer t0k3n"),
    ]
    assert FakeService.seen[0][3] == {"password": "secret password"}


def test_create_sends_the_local_time_and_needs_no_session(service: Path):
    FakeService.responses = {("POST", "/entries"): (201, ENTRY)}
    started = datetime(2026, 11, 17, 23, 45, tzinfo=timezone(timedelta(hours=1)))
    JournalClient(service).create("text", ["work"], written_at=started)
    _, _, headers, body = FakeService.seen[0]
    assert "Authorization" not in headers
    assert body == {"body": "text", "tags": ["work"], "written_at": "2026-11-17T23:45:00+01:00"}


def test_session_calls_without_a_session_fail_locally(service: Path):
    with pytest.raises(Unauthorized):
        JournalClient(service).entries(content=True)
    assert FakeService.seen == []


@pytest.mark.parametrize(
    ("status", "error"),
    [(401, Unauthorized), (409, Conflict), (413, Invalid), (422, Invalid)],
)
def test_errors_carry_the_service_message(service: Path, status: int, error: type[Exception]):
    FakeService.responses = {("POST", "/password"): (status, {"error": "explained"})}
    with pytest.raises(error, match="explained"):
        JournalClient(service).change_password("a", "b")


def test_missing_socket_means_service_unavailable(tmp_path: Path):
    with pytest.raises(ServiceUnavailable, match="not running"):
        JournalClient(tmp_path / "missing.sock").health()
