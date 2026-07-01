<div align="center">

# Pedro-bot

A modular Discord bot with a live web dashboard — temporary voice lobbies,
image manipulation, autoroles, welcome messages, and more.

![Python](https://img.shields.io/badge/Python-3.13-3776AB?logo=python&logoColor=white)
![discord.py](https://img.shields.io/badge/discord.py-5865F2?logo=discord&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white)
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

- **Temporary voice lobbies** — members join a trigger channel to spin up their
  own voice channel, which they can rename and resize, and which is cleaned up
  automatically when empty.
- **Image manipulation** — patpet, heart-locket, and explode effects from an
  avatar, URL, or attachment (via the Jeyy API).
- **Autoroles & welcome messages** — automatically assign roles to new members
  and greet them in a configurable channel.
- **Server customization** — per-guild embed colors and server rules.
- **Fun & utility** — random cat/dog images, magic 8-ball, random choice,
  avatar/user/server info, and a raw-JSON embed builder.
- **Live web dashboard** — status, latency, uptime, guild list, and a cog
  manager to load / unload / reload extensions on the fly.

## Dashboard

Runs alongside the bot at **http://localhost:8000**. It shows real-time status,
latency, uptime and guild count, and provides a **Cog Manager** for hot-reloading
extensions without restarting the bot.

## Command Reference

> This section is generated from the cogs by `scripts/gen_readme.py` — do not edit
> it by hand. It stays in sync with the bot's own `/help` command automatically.

<!-- COMMANDS:START -->

### General

| Command | Description |
| --- | --- |
| `/help` | Displays the help message with all available commands |
| `/rules` | Displays the server rules |

### Settings

| Command | Description |
| --- | --- |
| `/autorole add` | Adds a role to be automatically given to new members |
| `/autorole list` | Lists all currently configured autoroles |
| `/autorole remove` | Removes a role from the autorole list |
| `/set embedcolor` | Set or reset the server's embed color |
| `/setup welcome` | Setup or disable the welcome message channel |

### Lobbies

| Command | Description |
| --- | --- |
| `/rename` | Rename your current lobby voice-channel |
| `/resize` | Resize your current lobby |
| `/setup lobbies` | Setup temporary voice-chat system with user-created lobbies |

### Image Manipulation

| Command | Description |
| --- | --- |
| `/image ace` | Generate an Ace Attorney style dialogue image |
| `/image billboard` | Generate a billboard image effect from a user avatar, image URL, or attachment |
| `/image bonk` | Generate a bonk gif from an avatar, image URL, or attachment |
| `/image burn` | Generate a burning image effect from a user avatar, image URL, or attachment |
| `/image cow` | Generate a cow image effect from a user avatar, image URL, or attachment |
| `/image cube` | Generate a spinning cube image effect from a user avatar, image URL, or attachment |
| `/image earthquake` | Generate a shaking earthquake image effect from a user avatar, image URL, or attachment |
| `/image explode` | Generate an exploding image effect from a user avatar, image URL, or attachment |
| `/image flag` | Generate a waving flag image effect from a user avatar, image URL, or attachment |
| `/image flush` | Generate a flushing toilet image effect from a user avatar, image URL, or attachment |
| `/image glitch` | Generate a glitch image effect from a user avatar, image URL, or attachment |
| `/image heartlocket` | Generate a heart locket image from one or two image sources |
| `/image hearts` | Generate a hearts image effect from a user avatar, image URL, or attachment |
| `/image laundry` | Generate a laundry image effect from a user avatar, image URL, or attachment |
| `/image math` | Generate an equations image effect from a user avatar, image URL, or attachment |
| `/image matrix` | Generate a Matrix-style digital rain image effect from a user avatar, image URL, or attachment |
| `/image petpet` | Generate a patpat gif from an avatar, image URL, or attachment |
| `/image print` | Generate a printing image effect from a user avatar, image URL, or attachment |
| `/image pyramid` | Generate a pyramid image effect from a user avatar, image URL, or attachment |
| `/image rain` | Generate a falling rain image effect from a user avatar, image URL, or attachment |
| `/image sensitive` | Overlay a sensitive content warning on a user avatar, image URL, or attachment |
| `/image sphere` | Generate a spinning globe image effect from a user avatar, image URL, or attachment |
| `/image spin` | Generate a spinning image effect from a user avatar, image URL, or attachment |
| `/image stereo` | Generate a stereo image effect from a user avatar, image URL, or attachment |
| `/image stretch` | Generate a stretch image effect from a user avatar, image URL, or attachment |

### Random Fun

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
| `/serverinfo` | Displays server statistics |
| `/stats` | Shows technical information about the bot |
| `/userinfo` | Displays information about a user |

### Other

| Command | Description |
| --- | --- |
| `/test welcome` | Simulate a member joining to test the welcome message |

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
run.bat          # Windows — auto-restarts on crash
```

Or directly:

```bash
py -3.13 run.py  # wrapper that restarts the bot if it exits
python bot.py    # run the bot once, no auto-restart
```

## Project Structure

```
Pedro-bot/
├── bot.py              # Entry point: loads cogs, starts bot + dashboard
├── web.py              # FastAPI dashboard (status, guilds, cog manager)
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
commit message — no separate "docs" commits.

> [!IMPORTANT]
> **Run once per machine.** Git hooks are not cloned or pushed, so on every
> machine you work from (desktop, laptop, a fresh clone) you must enable them once:
>
> ```bash
> git config core.hooksPath scripts/hooks
> ```
>
> Without this, commits still work — the command table just won't auto-update on
> that machine until you run `py -3.13 scripts/gen_readme.py` manually.
