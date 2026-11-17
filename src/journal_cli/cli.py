"""Command line entry point.

journal-cli          the TUI: unlock, browse, search, write
journal-cli new      write one entry right away; no password (writing never needs it)
journal-cli idle     keep the container running so `podman exec` can start the TUI
journal-cli paths    show the config, log and socket locations
"""

import argparse
import os
import signal
import sys

from journal_cli import __version__
from journal_cli.identity import IDENTITY


def _idle() -> int:
    """Main process of the container: sleep until SIGTERM (`podman stop`)."""

    def stop(_signum: int, _frame: object) -> None:
        raise SystemExit(0)

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    while True:
        signal.pause()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog=IDENTITY.app_name, description=IDENTITY.description)
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    commands = parser.add_subparsers(dest="command", metavar="command")
    commands.add_parser("new", help="write a new entry right away (no password needed)")
    commands.add_parser("idle", help="keep the container running (its main process)")
    commands.add_parser("paths", help="show the config, log and socket locations")
    args = parser.parse_args(argv)

    if args.command == "idle":
        return _idle()

    # Imported here so `idle` stays small: it never loads Textual.
    from journal_cli.api import JournalClient
    from journal_cli.log_setup import configure_logging
    from journal_cli.paths import resolve_paths
    from journal_cli.settings import SettingsError, load_settings

    os.umask(0o077)
    paths = resolve_paths()
    try:
        settings = load_settings(paths)
    except SettingsError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if args.command == "paths":
        print(f"{'config file':<12} {paths.config_file}")
        print(f"{'log file':<12} {paths.log_file}")
        print(f"{'socket':<12} {settings.socket_path}")
        return 0

    paths.ensure()
    configure_logging(settings, paths)

    from journal_cli.tui.app import JournalApp

    app = JournalApp(
        JournalClient(settings.socket_path), settings, quick_entry=args.command == "new"
    )
    message = app.run()
    if message:
        print(message)
    return 0
