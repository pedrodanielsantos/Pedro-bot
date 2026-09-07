# Setup

Everything needed to get the bot running. For the music node's own setup, see
[Music](music.md).

## Prerequisites

- Python 3.13
- A [Discord bot token](https://discord.com/developers/applications)
- A JDK 17+ (21 LTS recommended), for the music node only. See [Music](music.md).

## Installation

```bash
git clone https://github.com/pedrodanielsantos/Pedro-bot.git
cd Pedro-bot
pip install -r requirements.txt
```

For music, also install the Lavalink node once per host:

```bash
py -3.13 scripts/setup_lavalink.py
```

Skip it to run without music. See [Music](music.md) for the full setup.

## Configuration

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
[`config/constants.py`](../config/constants.py).

`SYNC_ON_STARTUP` defaults to `true`, syncing slash commands once per process
on `on_ready`. Set it to `false` to skip that and avoid Discord's rate limits
when restarting often. Sync manually anytime with the dashboard's **Sync**
button or `ç!sync`.

## Bot permissions

The bot's role needs **View Channel**, **Connect**, **Speak**, **Send Messages**
and **Embed Links**. **Move Members** is optional and lets it join a channel that
is at its user limit. Channel and category overwrites beat role permissions, so
grant these on the category the lobbies live in.

## Intents

[`bot.py`](../bot.py) requests members, guilds and message content on top of
`Intents.default()`. Two of those are **privileged** and must be enabled on the
application's Bot page in the Developer Portal, or the bot fails to log in:

- **Server Members Intent**, for autoroles and welcome messages.
- **Message Content Intent**, for the `ç!` developer commands.

Presence Intent is not used. `voice_states` comes with `Intents.default()` and
is not privileged, so the lobby and music features need nothing extra.

## Running

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

For debugging without auto-restart on crash (or running the bot without the
dashboard in front of it):

```bash
py -3.13 bot.py
```
