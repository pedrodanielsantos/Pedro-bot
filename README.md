<div align="center">

# Pedro-bot

A modular Discord bot with a live web dashboard, featuring temporary voice
lobbies, GIF generation, autoroles, welcome messages, command logging,
and more.

![Python](https://img.shields.io/badge/Python-3.13-3776AB?logo=python&logoColor=white)
![discord.py](https://img.shields.io/badge/discord.py-5865F2?logo=discord&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white)
![htmx](https://img.shields.io/badge/htmx-3D72D7?logo=htmx&logoColor=white)
![SQLite](https://img.shields.io/badge/SQLite-003B57?logo=sqlite&logoColor=white)

</div>

---

## Overview

Pedro-bot is a slash-command Discord bot built on [discord.py](https://discordpy.readthedocs.io/).
Features are split into self-contained **cogs** that are auto-discovered from the
`cogs/` folder, so adding functionality is as simple as dropping in a new file.
It ships with a lightweight **web dashboard** (FastAPI + htmx) for monitoring the
bot and hot-reloading cogs without a restart.

## Features

- **Temporary voice lobbies**: members join a trigger channel to spin up their
  own voice channel, which they can rename and resize, and which is cleaned up
  automatically when empty.
- **GIF generation**: over 20 effects (petpet, heart lock, explode, glitch,
  and more) applied to an avatar, URL, or attachment via the Jeyy API.
- **Autoroles & welcome messages**: automatically assign roles to new members
  and greet them in a configurable channel.
- **Server customization**: per-guild embed colors and server rules.
- **Fun & utility**: random cat/dog images, magic 8-ball, random choice,
  avatar/user/server info, and a raw-JSON embed builder.
- **Command logging**: log every slash command used in a server to a
  configurable channel, with the invoking user, options, and channel.
- **Live web dashboard**: status, latency, uptime, guild list, a cog
  manager to load / unload / reload extensions on the fly, sync slash
  commands with Discord, and a live console view of the bot's logs. Runs as
  its own process, so it stays online (with a Start/Stop control) even if
  the bot itself crashes or is stopped.

## Dashboard

Runs at **http://localhost:8000**, hosted by `run.py` as its own always-on
process, separate from the bot itself, so the dashboard stays reachable even if
the bot crashes or is stopped. It shows real-time status, latency, uptime and
guild count, a **Start/Stop** control for the bot process, a **Cog Manager** for
hot-reloading extensions, and a **Sync Commands** button to push slash command
changes to Discord, all without restarting the bot. Cog management, guild list,
and command sync only work while the bot is actually online; while it's offline
the dashboard shows an Offline status and a Start button instead.

A separate **Console** page (`/console`) shows a live, auto-scrolling view of the
bot's logs, read from `logs/bot.log` so it stays visible even across a crash or
restart, whether you're debugging startup, a cog reload, or a command error.

## Command Reference

> This section is generated from the cogs by `scripts/gen_readme.py`, so don't edit
> it by hand. It stays in sync with the bot's own `/help` command automatically.

<!-- COMMANDS:START -->

### Lobbies

| Command | Description |
| --- | --- |
| `/rename` | Rename your current lobby voice-channel |
| `/resize` | Resize your current lobby |

### Fun

| Command | Description |
| --- | --- |
| `/8ball` | Ask the magic 8-ball a question |
| `/cat` | Fetch a random cat image |
| `/choice` | Chooses randomly from the given options (separated by commas) |
| `/dog` | Fetch a random dog image |

### Utility

| Command | Description |
| --- | --- |
| `/avatar` | Displays the avatar of a user |
| `/embed createjson` | Create an embed using raw JSON |
| `/embed editjson` | Edit an existing embed using raw JSON |
| `/embed json` | Get the JSON source of an embed |
| `/rules` | Displays the server rules |
| `/serverinfo` | Displays server statistics |
| `/stats` | Shows technical information about the bot |
| `/timestamp at` | Generate a timestamp tag for a specific date and time |
| `/timestamp in` | Generate a timestamp tag relative to now |
| `/userinfo` | Displays information about a user |

### Image

| Command | Description |
| --- | --- |
| `/image ace` | Make an Ace Attorney dialogue image |
| `/image billboard` | Put an image on a billboard |
| `/image bonk` | Bonk an image |
| `/image burn` | Set an image on fire |
| `/image cow` | Turn an image into a cow |
| `/image cube` | Spin an image on a cube |
| `/image earthquake` | Shake an image like an earthquake |
| `/image explode` | Blow up an image |
| `/image flag` | Wave an image like a flag |
| `/image flush` | Flush an image down a toilet |
| `/image glitch` | Glitch an image |
| `/image heartlocket` | Put one or two images in a heart locket |
| `/image hearts` | Cover an image in hearts |
| `/image laundry` | Toss an image in the laundry |
| `/image math` | Cover an image in equations |
| `/image matrix` | Turn an image into the Matrix |
| `/image petpet` | Pat an image |
| `/image print` | Print out an image |
| `/image pyramid` | Turn an image into a pyramid |
| `/image rain` | Make it rain with an image |
| `/image sensitive` | Slap a sensitive content warning on an image |
| `/image sphere` | Wrap an image around a spinning globe |
| `/image spin` | Spin an image |
| `/image stereo` | Split an image into a stereo effect |
| `/image stretch` | Stretch an image |

### Administration

| Command | Description |
| --- | --- |
| `/autorole add` | Adds a role to be automatically given to new members |
| `/autorole list` | Lists all currently configured autoroles |
| `/autorole remove` | Removes a role from the autorole list |
| `/set embedcolor` | Set or reset the server's embed color |
| `/setup lobbies` | Setup temporary voice-chat system with user-created lobbies |
| `/setup logs` | Setup or disable the command log channel |
| `/setup welcome` | Setup or disable the welcome message channel |
| `/test welcome` | Simulate a member joining to test the welcome message |

### Other

| Command | Description |
| --- | --- |
| `/help` | Displays the help message with all available commands |

<!-- COMMANDS:END -->

## Getting Started

### Prerequisites

- Python 3.13
- A [Discord bot token](https://discord.com/developers/applications)

### Installation

```bash
git clone https://github.com/pedrodanielsantos/Pedro-bot.git
cd Pedro-bot
pip install -r requirements.txt
```

### Configuration

Create a `.env` file in the project root:

```env
DISCORD_BOT_TOKEN=your_discord_bot_token
JEYY_API_KEY=your_jeyy_api_key       # image manipulation commands
CAT_API_KEY=your_cat_api_key         # /cat
DOG_API_KEY=your_dog_api_key         # /dog
SYNC_ON_STARTUP=false                # optional; skip the automatic command sync on every restart
```

Non-secret defaults (lobby names, voice region, embed colors, etc.) live in
[`config/constants.py`](config/constants.py).

`SYNC_ON_STARTUP` defaults to `true`. The bot normally syncs slash commands once
per process on `on_ready`, which means every restart re-syncs, so set this to
`false` if you're restarting frequently (e.g. testing the dashboard's Start/Stop
controls) and want to avoid hitting Discord's rate limits. You can still sync
manually at any time with the dashboard's **Sync Commands** button or `ç!sync`.

### Running

```bash
py -3.13 run.py
```

`run.py` is the process you actually keep running (e.g. via a service manager on
a server). It hosts the dashboard on port 8000 and supervises `bot.py` as a
child process, restarting it automatically if it crashes (waiting 5 seconds
between attempts). You can also start/stop the bot from the dashboard itself; a
manual stop is a clean shutdown (unloading cogs, closing DB connections) and
won't trigger an auto-restart.

To stop everything, press **Ctrl+C** in `run.py`'s console. It stops the bot
cleanly first, then exits.

`bot.py` also exposes a small internal API on **127.0.0.1:8001** that the
dashboard uses to fetch live bot data (status, guilds, cogs, command sync) and
that only `run.py`'s process can reach. It isn't meant to be exposed publicly,
so if you're putting the dashboard behind a reverse proxy or tunnel, only forward
port 8000.

If you're debugging and don't want crashes to auto-restart (or want the bot
running without the dashboard in front of it), run the bot directly:

```bash
py -3.13 bot.py
```

## Project Structure

```
Pedro-bot/
├── bot.py              # Entry point: loads cogs, starts the bot + internal API
├── internal_api.py     # Localhost-only API (127.0.0.1:8001) exposing live bot data to web.py
├── web.py              # FastAPI dashboard (proxies to internal_api.py; status, guilds, cog manager, command sync, console)
├── run.py              # Supervisor: hosts the dashboard (:8000) and starts/stops/restarts bot.py
├── logs/               # Rotating bot.log, read by the Console page
├── cogs/
│   ├── commands/       # User-facing slash commands
│   └── core/           # Error handling, dev tools, shared mixins
├── config/             # Constants and configuration
├── db/                 # SQLite storage (aiosqlite)
├── utils/              # Runtime helpers imported by the bot
├── templates/          # Jinja2 templates for the dashboard
└── scripts/            # Dev tooling (e.g. README generation)
```

## Maintaining the docs

The command table above is generated from the cogs. Regenerate it with:

```bash
py -3.13 scripts/gen_readme.py
```

A git hook (`scripts/hooks/`) can run this automatically on every commit. When
the table changes, the hook stages the updated README and appends a note to your
commit message, so you won't end up with separate "docs" commits.

> [!IMPORTANT]
> **Run once per machine.** Git hooks are not cloned or pushed, so on every
> machine you work from (desktop, laptop, a fresh clone) you must enable them once:
>
> ```bash
> git config core.hooksPath scripts/hooks
> ```
>
> Without this, commits still work, but the command table just won't auto-update
> on that machine until you run `py -3.13 scripts/gen_readme.py` manually.
