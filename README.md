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
  Bandcamp through a self-hosted Lavalink node, with search autocomplete, seeking,
  looping and an optional DJ role.
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

A separate **Console** page (`/console`) is a live, auto-scrolling mirror of every
supervised process's stdout/stderr (not just logged output), rendered client-side
from `logs/console.raw` so it stays visible across a crash or restart. Lavalink's
own Spring Boot lines are restated in the bot's log format on the way through, so
both processes read as one log.

## Music

Audio is streamed by [Lavalink](https://lavalink.dev/), a standalone Java node
that the bot controls over a loopback WebSocket via
[Wavelink](https://github.com/PythonistaGuild/Wavelink). The bot never touches
audio itself: it resolves and queues tracks, and Lavalink opens the voice
connection, decodes, and sends Opus.

That split is why the `PyNaCl is not installed` and `davey is not installed`
warnings at startup are harmless. They gate discord.py's own `VoiceClient`,
which encrypts and sends audio in-process. `wavelink.Player` is a bare
`VoiceProtocol` that only relays the voice session to Lavalink, and Lavalink
handles encryption, including DAVE, on its side.

### Architecture

| Piece | Role |
| --- | --- |
| `Lavalink.jar` | Standalone node on `127.0.0.1:2333`, started by `run.py` |
| [`youtube-source`](https://github.com/lavalink-devs/youtube-source) | YouTube and YouTube Music extraction, pinned to a snapshot |
| [`LavaSrc`](https://github.com/topi314/LavaSrc) | Spotify/Apple/Deezer resolution, off until credentials are set |
| [`cogs/core/music_manager.py`](cogs/core/music_manager.py) | Owns the node connection and playback lifecycle |
| [`cogs/commands/music.py`](cogs/commands/music.py) | The slash commands |
| [`utils/music.py`](utils/music.py) | Player lookup, DJ gating, track formatting, fallback search |

The node is **optional**. With `LAVALINK_DIR` unset, or the jar or `java` missing,
`run.py` logs why and skips it, the bot starts normally, and the music commands
report themselves as unavailable.

### Node setup

Needs a **JDK 17+** on the host, 21 LTS recommended. Install
[Temurin](https://adoptium.net/) on Windows, or:

```bash
sudo apt install openjdk-21-jre-headless    # Debian/Ubuntu
```

Open a new shell afterwards so `java` is on `PATH`, then:

```bash
py -3.13 scripts/setup_lavalink.py
```

That downloads `Lavalink.jar` and the LavaSrc plugin, renders `application.yml`
from [`config/lavalink/application.yml.example`](config/lavalink/application.yml.example)
with a generated password, and prints the `.env` lines to add. Re-running keeps
what's already there unless `--force` is passed. Default install dir is
`C:\lavalink` or `/opt/lavalink`, overridable with `--dir`.

> [!IMPORTANT]
> Install on **local disk**, not a network share. Lavalink writes its logs and
> plugin jars next to its own jar, and a JVM started over a share is slow to
> boot and prone to file locking problems.

Only the config template is tracked. The rendered `application.yml` holds the
real password and stays on the host, outside the repo.

### Bot permissions

The bot's role needs **View Channel**, **Connect**, **Speak**, **Send Messages**
and **Embed Links**. **Move Members** is optional and lets it join a channel that
is at its user limit. Channel and category overwrites beat role permissions, so
grant these on the category the lobbies live in.

`voice_states` is already covered by `Intents.default()` and is not privileged,
so no portal changes are needed.

### YouTube extraction

This is the part that breaks, not the infrastructure. Two settings in
`application.yml` matter:

- **`youtube-plugin` is declared as a snapshot dependency**, not shipped as a jar,
  because tagged releases lag behind YouTube's changes. Snapshot versions are
  commit hashes, listed
  [here](https://maven.lavalink.dev/snapshots/dev/lavalink/youtube/youtube-plugin/).
  Only one copy may be installed: delete any `plugins/youtube-plugin-*.jar`
  before starting.
- **All ten clients are listed**, ordered by how likely each is to return a plain
  HTTPS URL. Which ones work varies by IP and region, and a client that fails
  costs one request, so a short list risks total playback failure. `MUSIC`
  resolves `music.youtube.com` links and `ytmsearch` but does not stream, so it
  can never be the only client.

When playback fails, the error enumerates every client with its own reason, which
says whether any client still gets a direct URL. SoundCloud and Bandcamp are
native Lavalink sources that never touch this path, so they make a good control
test.

Not every failure is an extraction problem. A playlist can carry entries whose
underlying upload is deleted or region locked, where every client reports "This
video is not available". For those, `music_manager` re-searches the author and
title against `MUSIC_FALLBACK_SOURCES` (plain YouTube first, then SoundCloud),
requires the result to be within `MUSIC_FALLBACK_TOLERANCE` seconds of the
original length, and queues it in the failed track's place. Each id is only
replaced once, so an unplayable track cannot set off a chain of searches. Both
constants live in [`config/constants.py`](config/constants.py).

## Command Reference

> Generated from the cogs by `scripts/gen_readme.py`.
> Stays in sync with the bot's own `/help` command automatically.

<!-- COMMANDS:START -->

### Lobbies

| Command | Description |
| --- | --- |
| `/region` | Change your current lobby's voice region |
| `/rename` | Rename your current lobby voice-channel |
| `/resize` | Resize your current lobby |

### Music

| Command | Description |
| --- | --- |
| `/loop` | Set the loop mode |
| `/nowplaying` | Show the track currently playing |
| `/pause` | Pause playback |
| `/play` | Play a track, or add it to the queue |
| `/queue` | Show the queue |
| `/resume` | Resume playback |
| `/seek` | Jump to a position in the current track |
| `/shuffle` | Shuffle the queue |
| `/skip` | Skip the current track |
| `/stop` | Stop playback, clear the queue and leave |
| `/volume` | Set or view the playback volume |

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
| `/help` | Displays the help message with all available commands |
| `/rules` | Displays the server rules |
| `/serverinfo` | Displays server statistics |
| `/settings` | View your personal settings |
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
| `/embed createjson` | Create an embed using raw JSON |
| `/embed editjson` | Edit an existing embed using raw JSON |
| `/embed json` | Get the JSON source of an embed |
| `/log commands` | Setup or disable the log channel for every command used |
| `/log moderation` | Setup or disable the moderation log channel |
| `/moderation ban` | Bans a user from the server |
| `/moderation clearwarnings` | Clears every warning for a member |
| `/moderation kick` | Kicks a member from the server |
| `/moderation removetimeout` | Removes an active timeout from a member |
| `/moderation timeout` | Times out a member |
| `/moderation unban` | Unbans a user from the server |
| `/moderation warn` | Warns a member |
| `/moderation warnings` | Lists warnings for a member, or every member currently in the server |
| `/serverconfig` | View the server's current bot settings |
| `/set djrole` | Set or reset the role required to control music playback |
| `/set embedcolor` | Set or reset the server's embed color |
| `/set lobbyregion` | Set or reset the voice region new lobbies are created in |
| `/set musicvolume` | Set or reset the volume new players start at |
| `/setup lobbies` | Setup temporary voice-chat system with user-created lobbies |
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
- A JDK 17+ (21 LTS recommended), for the music node only. See [Music](#music).

### Installation

```bash
git clone https://github.com/pedrodanielsantos/Pedro-bot.git
cd Pedro-bot
pip install -r requirements.txt
```

For music, also install the Lavalink node once per host:

```bash
py -3.13 scripts/setup_lavalink.py
```

Skip it to run without music. See [Music](#music) for the full setup.

### Configuration

`.env` in the project root:

```env
DISCORD_BOT_TOKEN=your_discord_bot_token
JEYY_API_KEY=your_jeyy_api_key       # image manipulation commands
CAT_API_KEY=your_cat_api_key         # /cat
DOG_API_KEY=your_dog_api_key         # /dog
SYNC_ON_STARTUP=false                # optional; skip the automatic command sync on every restart
LOG_LEVEL=DEBUG                      # optional; defaults to INFO

LAVALINK_DIR=C:\lavalink             # music; where setup_lavalink.py installed the node
LAVALINK_URI=http://127.0.0.1:2333   # music; the node's address
LAVALINK_PASSWORD=your_node_password # music; must match application.yml
```

The three `LAVALINK_*` values are printed by `scripts/setup_lavalink.py`. Leave
them out to run without music.

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

`run.py` hosts the dashboard on port 8000 and supervises both child processes,
restarting them automatically on crash. Terminal output is color-coded, same as
the web console.

When configured, **Lavalink starts first** and `run.py` waits for it to accept
connections before starting the bot, so the node is listening by the time the
music cog connects. On shutdown the order reverses: the bot leaves its voice
channels before the node it streams through goes away.

Ctrl+C in `run.py`'s console, or Stop on the dashboard, shuts everything down
cleanly. `bot.py` stops on a `CTRL_BREAK_EVENT` it handles itself; Lavalink is
terminated directly, since a JVM answers Ctrl+Break with a thread dump rather
than by exiting.

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
├── run.py              # Supervisor: hosts the dashboard (:8000), starts/stops bot.py and Lavalink
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
└── scripts/            # Dev tooling (README generation, Lavalink install/diagnostics)
```

## License

Licensed under the [GNU AGPLv3](LICENSE). If you run a modified version of
this bot for others to use over a network, you must make your modified
source available to them.

## Maintaining the docs

The command table above is generated from the cogs:

```bash
py -3.13 scripts/gen_readme.py
```

A git hook (`scripts/hooks/`) runs this on every commit. When the table
changes, it stages the updated README and appends a note to the commit message,
avoiding separate "docs" commits.

> [!IMPORTANT]
> Git hooks aren't cloned or pushed, so enable them once per clone:
>
> ```bash
> git config core.hooksPath scripts/hooks
> ```
>
> Without this, commits still work, but the command table won't auto-update
> until `py -3.13 scripts/gen_readme.py` is run manually.
