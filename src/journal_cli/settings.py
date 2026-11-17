"""Settings from the optional TOML file at $XDG_CONFIG_HOME/journal-cli/config.toml.

Every key is optional. Unknown sections or keys are rejected so typos do not pass silently.

    [service]
    socket = "/path/to/api.sock"   # default: $XDG_RUNTIME_DIR/journal-service/api.sock

    [ui]
    theme = "gruvbox"              # any Textual theme; "ansi-dark" uses your terminal's colours
    auto_lock_minutes = 10         # lock after this long without input; 0 disables

    [logging]
    level = "INFO"                 # the log never contains entry text or passwords
"""

import tomllib
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path

from journal_cli.paths import AppPaths


class SettingsError(Exception):
    pass


_SCHEMA: dict[str, dict[str, type]] = {
    "service": {"socket": str},
    "ui": {"theme": str, "auto_lock_minutes": int},
    "logging": {"level": str},
}

_LOG_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")
DEFAULT_THEME = "gruvbox"


@dataclass(frozen=True, slots=True)
class Settings:
    socket_path: Path
    theme: str
    auto_lock: timedelta | None  # None: never lock automatically
    log_level: str


def _read_file(path: Path) -> dict[str, dict[str, object]]:
    if not path.is_file():
        return {}
    try:
        with path.open("rb") as handle:
            raw = tomllib.load(handle)
    except tomllib.TOMLDecodeError as exc:
        raise SettingsError(f"{path}: {exc}") from exc

    for section, values in raw.items():
        keys = _SCHEMA.get(section)
        if keys is None or not isinstance(values, dict):
            raise SettingsError(f"{path}: unknown section [{section}]")
        for key, value in values.items():
            expected = keys.get(key)
            if expected is None:
                raise SettingsError(f"{path}: unknown key '{key}' in [{section}]")
            if type(value) is not expected:  # exact: bool is a subclass of int
                raise SettingsError(f"{path}: {section}.{key} must be {expected.__name__}")
    return raw


def load_settings(paths: AppPaths) -> Settings:
    from textual.theme import BUILTIN_THEMES

    raw = _read_file(paths.config_file)

    def get[T](section: str, key: str, default: T) -> T:
        return raw.get(section, {}).get(key, default)  # type: ignore[return-value]

    socket = Path(get("service", "socket", str(paths.service_socket)))
    if not socket.is_absolute():
        raise SettingsError("service.socket must be an absolute path")

    theme = get("ui", "theme", DEFAULT_THEME)
    if theme not in BUILTIN_THEMES:
        raise SettingsError(f"ui.theme must be one of: {', '.join(sorted(BUILTIN_THEMES))}")

    minutes = get("ui", "auto_lock_minutes", 10)
    if minutes < 0:
        raise SettingsError("ui.auto_lock_minutes must be 0 (off) or more")

    level = get("logging", "level", "INFO").upper()
    if level not in _LOG_LEVELS:
        raise SettingsError(f"logging.level must be one of {', '.join(_LOG_LEVELS)}")

    return Settings(
        socket_path=socket,
        theme=theme,
        auto_lock=timedelta(minutes=minutes) if minutes else None,
        log_level=level,
    )
