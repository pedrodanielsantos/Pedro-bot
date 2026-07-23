<div align="center">

# Pedro-bot

A Discord bot built on discord.py, with a FastAPI + htmx web dashboard.
Temporary voice lobbies, GIF generation, autoroles, welcome messages,
command logging, and more.

![Python](https://img.shields.io/badge/Python-3.13-3776AB?logo=python&logoColor=white)
![discord.py](https://img.shields.io/badge/discord.py-5865F2?logo=discord&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white)
![htmx](https://img.shields.io/badge/htmx-3D72D7?logo=htmx&logoColor=white)
![SQLite](https://img.shields.io/badge/SQLite-003B57?logo=sqlite&logoColor=white)

</div>

---

## Overview

Slash-command bot built on [discord.py](https://discordpy.readthedocs.io/). Features
are split into self-contained **cogs**, auto-discovered from `cogs/`. Ships with a
**web dashboard** (FastAPI + htmx) for monitoring the bot and hot-reloading cogs
without a restart.

## Features

- **Temporary voice lobbies**: joining a trigger channel spins up a voice channel
  the member can rename and resize, cleaned up automatically when empty.
- **GIF generation**: 25 effects (petpet, heart lock, explode, glitch, etc.)
  applied to an avatar, URL, or attachment via the Jeyy API.
- **Autoroles & welcome messages**: auto-assign roles to new members, greet them
  in a configurable channel.
- **Server customization**: per-guild embed colors and server rules.
- **Fun & utility**: random cat/dog images, magic 8-ball, random choice,
  avatar/user/server info, raw-JSON embed builder.
- **Command logging**: logs every slash command used, with invoking user,
  options, and channel, to a configurable channel.
- **Web dashboard**: status, latency, uptime, guild list, cog manager
  (load/unload/reload), slash command sync, live console. Runs as its own
  process with a Start/Stop control, so it stays up even if the bot crashes.

## Dashboard

Runs at **http://localhost:8000**, hosted by `run.py` as its own always-on
process, separate from the bot. Shows real-time status, latency, uptime, and
guild count, with **Start/Stop/Reload** control, a **Cog Manager**, and a **Sync**
button for slash commands.

A separate **Console** page (`/console`) shows a live, auto-scrolling, color-coded
view of the bot's logs, read from `logs/bot.log` so it stays visible across a
crash or restart.

## Command Reference

> Generated from the cogs by `scripts/gen_readme.py`.
> Stays in sync with the bot's own `/help` command automatically.

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
| `/help` | Displays the help message with all available commands |
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

<!-- COMMANDS:END -->

### Developer Commands

Bot-owner-only, `ç!`-prefixed commands ([`cogs/core/developer_tools.py`](cogs/core/developer_tools.py)),
hidden from `/help` and excluded from the table above. Not part of the generated docs.

| Command | Description |
| --- | --- |
| `ç!reload [cog]` | Reload a specific cog, or all loaded cogs if none is given |
| `ç!load <cog>` | Load a specific cog |
| `ç!unload <cog>` | Unload a specific cog |
| `ç!sync [. \| ^]` | Sync slash commands (globally, to the current guild, or clear guild commands) |
| `ç!devtools` | List all developer commands |
| `ç!deletemessage <id>` | Delete one of the bot's own messages by ID |
| `ç!reloadweb` | Reload the web dashboard without restarting the bot |

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

`.env` in the project root:

```env
DISCORD_BOT_TOKEN=your_discord_bot_token
JEYY_API_KEY=your_jeyy_api_key       # image manipulation commands
CAT_API_KEY=your_cat_api_key         # /cat
DOG_API_KEY=your_dog_api_key         # /dog
SYNC_ON_STARTUP=false                # optional; skip the automatic command sync on every restart
```

Non-secret defaults (lobby names, voice region, embed colors, etc.) live in
[`config/constants.py`](config/constants.py).

`SYNC_ON_STARTUP` defaults to `true`, syncing slash commands once per process
on `on_ready`. Set it to `false` to skip that and avoid Discord's rate limits
when restarting often. Sync manually anytime with the dashboard's **Sync**
button or `ç!sync`.

### Running

```bash
py -3.13 run.py
```

`run.py` hosts the dashboard on port 8000 and supervises `bot.py` as a child
process, restarting it automatically on crash. Terminal output is color-coded,
same as the web console.

Ctrl+C in `run.py`'s console, or Stop on the dashboard, shuts the bot down cleanly.

`bot.py` also exposes a small internal API on **127.0.0.1:8001** that the
dashboard uses for live bot data (status, guilds, cogs, command sync); reachable
only from `run.py`'s process.

For debugging without auto-restart on crash (or running the bot without the
dashboard in front of it):

```bash
py -3.13 bot.py
```

## Project Structure

```
Pedro-bot/
├── bot.py              # Entry point: loads cogs, starts the bot and internal API
├── internal_api.py     # Localhost-only API (127.0.0.1:8001), feeds live bot data to web.py
├── web.py              # FastAPI dashboard: status, guilds, cog manager, command sync, console
├── run.py              # Supervisor: hosts the dashboard (:8000), starts/stops/restarts bot.py
├── logs/               # Rotating bot.log, read by the Console page
├── cogs/
│   ├── commands/       # Slash commands
│   └── core/           # Error handling, dev tools, shared mixins
├── config/             # Constants and configuration
├── db/                 # SQLite storage (aiosqlite)
├── utils/              # Runtime helpers
├── templates/          # Jinja2 templates for the dashboard
└── scripts/            # Dev tooling (e.g. README generation)
```

## Maintaining the docs

The command table above is generated from the cogs:

```bash
py -3.13 scripts/gen_readme.py
```

A git hook (`scripts/hooks/`) runs this on every commit. When the table
changes, it stages the updated README and appends a note to the commit message,
avoiding separate "docs" commits.

> [!IMPORTANT]
> **Run once per machine.** Git hooks aren't cloned or pushed, so on every
> machine (desktop, laptop, fresh clone) enable them once:
>
> ```bash
> git config core.hooksPath scripts/hooks
> ```
>
> Without this, commits still work, but the command table won't auto-update on
> that machine until `py -3.13 scripts/gen_readme.py` is run manually.
