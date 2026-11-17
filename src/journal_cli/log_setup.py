"""Logging to a rotating file in the state dir. The terminal belongs to the TUI.

Never log entry bodies, tags, passwords or session tokens.
"""

import logging
from logging.handlers import RotatingFileHandler

from journal_cli.paths import AppPaths
from journal_cli.settings import Settings


def configure_logging(settings: Settings, paths: AppPaths) -> None:
    paths.log_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    handler = RotatingFileHandler(
        paths.log_file, maxBytes=1024 * 1024, backupCount=3, encoding="utf-8"
    )
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s %(levelname)-8s %(name)s: %(message)s", datefmt="%Y-%m-%dT%H:%M:%S%z"
        )
    )
    root = logging.getLogger()
    for old in root.handlers[:]:
        root.removeHandler(old)
        old.close()
    root.addHandler(handler)
    root.setLevel(settings.log_level)
