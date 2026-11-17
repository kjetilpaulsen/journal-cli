"""XDG base directories, resolved exactly like journal-service does.

    config   $XDG_CONFIG_HOME/journal-cli          config.toml (optional)
    state    $XDG_STATE_HOME/journal-cli           logs/
    socket   $XDG_RUNTIME_DIR/journal-service/api.sock   (journal-service's socket)

journal-cli keeps nothing else on disk: decrypted text only ever lives in memory.
"""

import os
from dataclasses import dataclass
from pathlib import Path

from journal_cli.identity import IDENTITY, AppIdentity

DIR_MODE = 0o700


def _xdg_home(env_var: str, default: Path) -> Path:
    value = os.environ.get(env_var, "")
    if value and os.path.isabs(value):
        return Path(value)
    return default


@dataclass(frozen=True, slots=True)
class AppPaths:
    config_dir: Path
    state_dir: Path
    service_socket: Path

    @property
    def config_file(self) -> Path:
        return self.config_dir / "config.toml"

    @property
    def log_dir(self) -> Path:
        return self.state_dir / "logs"

    @property
    def log_file(self) -> Path:
        return self.log_dir / "journal_cli.log"

    def ensure(self) -> None:
        """Create missing directories as 0700. Existing directories are left as they are."""
        for directory in (self.config_dir, self.state_dir, self.log_dir):
            directory.mkdir(mode=DIR_MODE, parents=True, exist_ok=True)


def resolve_paths(identity: AppIdentity = IDENTITY) -> AppPaths:
    home = Path.home()
    config_home = _xdg_home("XDG_CONFIG_HOME", home / ".config")
    state_home = _xdg_home("XDG_STATE_HOME", home / ".local" / "state")

    runtime_home = os.environ.get("XDG_RUNTIME_DIR", "")
    if runtime_home and os.path.isabs(runtime_home):
        socket = Path(runtime_home) / identity.service_name / "api.sock"
    else:
        # journal-service's own fallback when XDG_RUNTIME_DIR is unset
        socket = state_home / identity.service_name / "run" / "api.sock"

    return AppPaths(
        config_dir=config_home / identity.app_name,
        state_dir=state_home / identity.app_name,
        service_socket=socket,
    )
