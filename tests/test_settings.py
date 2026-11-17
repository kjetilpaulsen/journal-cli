from datetime import timedelta
from pathlib import Path

import pytest

from journal_cli.paths import resolve_paths
from journal_cli.settings import SettingsError, load_settings


@pytest.fixture
def paths(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    for var in ("XDG_CONFIG_HOME", "XDG_STATE_HOME"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("XDG_RUNTIME_DIR", "/run/user/1000")
    resolved = resolve_paths()
    resolved.ensure()
    return resolved


def test_defaults_point_at_the_service_socket(paths, tmp_path):
    assert paths.config_file == tmp_path / ".config" / "journal-cli" / "config.toml"
    assert (
        paths.log_file == tmp_path / ".local" / "state" / "journal-cli" / "logs" / "journal_cli.log"
    )
    settings = load_settings(paths)
    assert settings.socket_path == Path("/run/user/1000/journal-service/api.sock")
    assert settings.theme == "gruvbox"
    assert settings.auto_lock == timedelta(minutes=10)


def test_without_runtime_dir_use_the_services_fallback(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("XDG_RUNTIME_DIR", raising=False)
    monkeypatch.delenv("XDG_STATE_HOME", raising=False)
    assert resolve_paths().service_socket == (
        tmp_path / ".local" / "state" / "journal-service" / "run" / "api.sock"
    )


def test_config_file(paths):
    paths.config_file.write_text('[ui]\ntheme = "nord"\nauto_lock_minutes = 0\n')
    settings = load_settings(paths)
    assert (settings.theme, settings.auto_lock) == ("nord", None)


@pytest.mark.parametrize(
    "content",
    [
        '[ui]\ntheme = "no-such-theme"\n',
        "[ui]\nauto_lock = 5\n",
        "[ui]\nauto_lock_minutes = -1\n",
        "[ui]\nauto_lock_minutes = true\n",
        '[service]\nsocket = "relative.sock"\n',
        "[colours]\n",
    ],
)
def test_config_mistakes_are_reported(paths, content):
    paths.config_file.write_text(content)
    with pytest.raises(SettingsError):
        load_settings(paths)
