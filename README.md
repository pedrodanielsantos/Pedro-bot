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
  commands with Discord, and a live console view of the bot's logs.

## Dashboard

Runs alongside the bot at **http://localhost:8000**. It shows real-time status,
latency, uptime and guild count, and provides a **Cog Manager** for hot-reloading
extensions without restarting the bot. A **Sync Commands** button lets you push
slash command changes to Discord on demand, without restarting the bot.

A separate **Console** page (`/console`) shows a live, auto-scrolling view of the
bot's logs, shared across every module that logs (bot, web, db, cogs), so the same
view works whether you're debugging startup, a cog reload, or a command error.

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
```

Non-secret defaults (lobby names, voice region, embed colors, etc.) live in
[`config/constants.py`](config/constants.py).

### Running

```bash
py -3.13 run.py
```

`run.py` automatically restarts `bot.py` if it crashes, waiting 5 seconds between
attempts. To stop the bot, just press **Ctrl+C**. It shuts down gracefully
(unloading cogs, closing DB connections), and since that counts as a clean exit,
`run.py` knows not to restart it.

If you're debugging and don't want crashes to auto-restart, run the bot directly:

```bash
py -3.13 bot.py
```

## Project Structure

```
Pedro-bot/
├── bot.py              # Entry point: loads cogs, starts bot + dashboard
├── web.py              # FastAPI dashboard (status, guilds, cog manager, command sync, console)
├── run.py              # Auto-restart wrapper
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
