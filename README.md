# journal-cli

Terminal frontend for journal-service. It's a [Textual](https://textual.textualize.io) TUI:
type the password, browse and search your entries, and write new ones. It talks to
journal-service over its Unix socket and keeps nothing on disk: decrypted text lives in
memory only, for as long as the session is unlocked.

```
journal          # password, then the list
journal new      # straight into a new entry, no password (writing never needs it)
```

## Keys

**List**

| key | |
|---|---|
| `⏎` | open the selected entry |
| `n` | new entry |
| `e` / `d` | edit / delete the selected entry (delete asks first) |
| `/` | search (see below); `⏎` keeps the filter, `esc` clears it |
| `j` `k` `g` `G` | down, up, first, last (arrows and PgUp/PgDn work too) |
| `p` | change the password |
| `l` | lock: forget the session and decrypted entries, ask for the password again |
| `r` | reload from journal-service |
| `q` / `ctrl+q` | quit (closes the session) |

**Editor:** plain multi-line editing, no modes. `⏎` is a line break. Backspace, `ctrl+w`
(delete word), `ctrl+u` (delete to line start), `ctrl+z` / `ctrl+y` (undo/redo) all work.
`tab` switches between the text and the tags field (`work, idea`).

| key | |
|---|---|
| `ctrl+d` | save. An empty entry is not saved, just closed. |
| `ctrl+x` | cancel. Asks first if there is text. |
| `esc` | nothing, so a vim reflex can't cost you a draft |

A new entry is stamped with the moment you *started* writing. An entry begun at 23:50 and
saved at 00:10 still belongs to the day it was started.

**Viewer:** `e` edit, `d` delete, `j`/`k` scroll, `esc`/`q` back.

**Search** filters as you type:

| query | matches |
|---|---|
| `2026-11` | entries whose date starts with it (several dates: any of them) |
| `#work` | entries with a tag starting with "work" (several tags: all of them) |
| `walk fjord` | entries containing every word, in the text or the tags, ignoring case |
| `"long walk"` | the exact phrase |

Terms combine: `#work 2026-11 meeting`.

## Setup (Arch, rootless Podman)

journal-service must be set up first (its README). Then, in this repo:

```bash
podman build -t journal-cli .
install -Dm644 deploy/journal-cli.container ~/.config/containers/systemd/journal-cli.container
systemctl --user daemon-reload
systemctl --user start journal-cli
install -Dm755 bin/journal ~/.local/bin/journal
journal
```

The container just idles (`journal-cli idle`, ~20 MB). `journal` runs
`podman exec -it journal-cli journal-cli` inside it, so opening the TUI is a process
start, not a container boot. It starts the unit first if it isn't running.

The container has no network, a read-only root and no capabilities. Its only link to
journal-service is the service's socket directory, `$XDG_RUNTIME_DIR/journal-service/`,
bind-mounted in. Both containers map their uid 10001 to your host user, so the 0600
socket works across them.

## Design notes

- **Textual** instead of curses: proper Unicode editing (æøå), a real multi-line editor
  with undo, a key bar generated from the bindings, and a headless test harness. It also
  writes escape codes itself instead of reading terminfo, so `tmux-256color` or `alacritty`
  in `$TERM` works inside a slim container. The cost is about 9 pure-Python packages (Rich,
  markdown-it, Pygments, …); prompt_toolkit would be the lean alternative at 2.
- **Unlock once, auto-lock.** The password opens a journal-service session. After 10
  minutes without input (configurable) the TUI locks itself and drops the decrypted
  entries. It never does this over an unsaved draft. If the service's own session expired
  meanwhile, the TUI asks for the password and retries what you were doing.
- **Search is local.** After unlocking, the TUI fetches all entries decrypted in one request
  (`GET /entries?content=true`), so filtering is instant and nothing about a search
  reaches the service.
- **Nothing is lost on errors.** If saving fails (for example journal-service is down), the
  editor stays open with your text.

## Configuration (optional)

`~/.config/journal-cli/config.toml`:

```toml
[ui]
theme = "gruvbox"          # any Textual theme; "ansi-dark" uses your terminal's own colours
auto_lock_minutes = 10     # 0 turns auto-lock off

[service]
socket = "/path/to/api.sock"   # default: $XDG_RUNTIME_DIR/journal-service/api.sock

[logging]
level = "INFO"             # ~/.local/state/journal-cli/logs/; never contains entry text
```

## Development

```bash
uv sync
uv run pytest              # TUI scenarios run headless against an in-memory fake
uv run ruff check && uv run ruff format --check
uv run journal-cli         # outside the container: talks to the same socket
```

`uv run journal-cli paths` shows which config, log and socket it resolved.
