<div align="center">

# Pedro-bot

A Discord bot built on discord.py, with a FastAPI + htmx web dashboard.
Temporary voice lobbies, music streaming, GIF generation, autoroles,
welcome messages, command logging, and more.

![Python](https://img.shields.io/badge/Python-3.13-3776AB?logo=python&logoColor=white)
![discord.py](https://img.shields.io/badge/discord.py-5865F2?logo=discord&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white)
![htmx](https://img.shields.io/badge/htmx-3D72D7?logo=htmx&logoColor=white)
![SQLite](https://img.shields.io/badge/SQLite-003B57?logo=sqlite&logoColor=white)
![Lavalink](https://img.shields.io/badge/Lavalink-FF624B?logo=soundcloud&logoColor=white)

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
- **Music**: queue-based playback from YouTube, YouTube Music, SoundCloud and
  Bandcamp through a self-hosted Lavalink node, with Spotify links matched to a
  YouTube or SoundCloud stream, plus search autocomplete, seeking, looping and an
  optional DJ role.
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
  (load/unload/reload), slash command sync, live console. Served by the
  supervisor rather than the bot, so it stays up even if the bot crashes.

## Quick start

```bash
git clone https://github.com/pedrodanielsantos/Pedro-bot.git
cd Pedro-bot
pip install -r requirements.txt
py -3.13 scripts/setup_lavalink.py    # optional, music only
py -3.13 run.py
```

Needs Python 3.13, a [Discord bot token](https://discord.com/developers/applications)
in `.env`, and a JDK 17+ for music. Full walkthrough in [Setup](docs/setup.md).

## Documentation

| Doc | Contents |
| --- | --- |
| [Setup](docs/setup.md) | Prerequisites, installation, `.env` reference, permissions and intents, running |
| [Commands](docs/commands.md) | Every slash command, plus the owner-only developer tools |
| [Music](docs/music.md) | Lavalink architecture, node setup, YouTube extraction, Spotify links |
| [Dashboard](docs/dashboard.md) | Dashboard pages, live console, internal API |
| [Development](docs/development.md) | Project structure, doc generation, git hooks |

## License

Licensed under the [GNU AGPLv3](LICENSE). If you run a modified version of
this bot for others to use over a network, you must make your modified
source available to them.
