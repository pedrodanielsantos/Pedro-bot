# Development

## Project structure

```
Pedro-bot/
├── bot.py              # Entry point: loads cogs, starts the bot and internal API
├── internal_api.py     # Localhost-only API (127.0.0.1:8001), feeds live bot data to web.py
├── web.py              # FastAPI dashboard: status, guilds, cog manager, command sync, console
├── run.py              # Supervisor: hosts the dashboard (:8000), starts/stops bot.py and Lavalink
├── docs/               # This documentation
├── logs/               # Rotating bot.log, plus console.raw, the Console page's source
├── cogs/
│   ├── commands/       # Slash commands
│   └── core/           # Error handling, dev tools, music node, shared mixins
├── config/
│   ├── constants.py    # Module-level constants and default values
│   └── lavalink/       # Tracked application.yml template for the music node
├── db/                 # SQLite storage (aiosqlite)
├── utils/              # Runtime helpers
├── templates/          # Jinja2 templates for the dashboard
├── static/             # Served at /static; vendored browser libraries
└── scripts/            # Dev tooling (README generation, Lavalink install/diagnostics)
```

Features are self-contained cogs, auto-discovered from `cogs/`. Adding a file
there is enough to register it; the dashboard's Cog Manager can load, unload and
reload each one without restarting the bot.

## Maintaining the docs

The command table in [Commands](commands.md) is generated from the cogs:

```bash
py -3.13 scripts/gen_readme.py
```

It parses every cog for its slash commands, and reads the categories and their
order from `cogs/commands/help.py`, so the docs and the in-Discord `/help` stay
in sync from one source.

A git hook (`scripts/hooks/`) runs this on every commit. When the table changes,
it stages the updated file and appends a note to the commit message, avoiding
separate "docs" commits.

> [!IMPORTANT]
> Git hooks aren't cloned or pushed, so enable them once per clone:
>
> ```bash
> git config core.hooksPath scripts/hooks
> ```
>
> Without this, commits still work, but the command table won't auto-update
> until `py -3.13 scripts/gen_readme.py` is run manually.

## Vendored browser libraries

The dashboard serves htmx and ansi_up from `static/vendor/` rather than a CDN,
so it still works with no internet and so an upstream release can't change what
runs without a commit. Versions are pinned in `utils/vendor.py`.

On startup, `run.py` checks npm in the background and logs a line in the console
when a newer release exists. Nothing updates on its own. To take one:

```bash
py -3.13 scripts/update_vendor.py
```

Bump the version in `utils/vendor.py` first. The filename carries the version,
so the new file lands alongside the old one, which the script names for you to
delete in the same commit.

Each library's upstream license is fetched next to it and must stay there.
ansi_up is MIT, whose notice has to travel with the code, and its built file
carries none of its own. htmx is 0BSD and requires nothing, but is kept the same
way. Both are permissive and compatible with this project's AGPL-3.0.
