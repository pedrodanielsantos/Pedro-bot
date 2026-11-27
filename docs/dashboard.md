# Dashboard

Runs at **http://localhost:8000**, served by `run.py` itself rather than by the
bot. Shows real-time status, latency, uptime, and guild count, with
**Start/Stop/Reload** control over the bot process, a **Cog Manager**, and a
**Sync** button for slash commands.

Because the supervisor hosts it and the bot runs as a separate child process,
the dashboard stays up when the bot crashes or is stopped, which is what gives
you a Start button to bring it back.

It binds `127.0.0.1:8000`, so it is reachable from the host only. Set
`WEB_HOST=0.0.0.0` in `.env` to serve it on the network.

> [!WARNING]
> There is no authentication. Anyone who can reach the port can stop the bot,
> reload cogs and read the console, so only widen `WEB_HOST` on a network you
> trust, and keep the port behind a firewall.

## Console

A separate **Console** page (`/console`) is a live, auto-scrolling mirror of every
supervised process's stdout/stderr (not just logged output), rendered client-side
from the log files below so it stays visible across a bot crash or restart. Lavalink's
own Spring Boot lines are restated in the bot's log format on the way through, so
both processes read as one log.

Scrolling to the top loads older history, back through earlier days, with a
separator at each day boundary. While following the live tail the page keeps the
last 10,000 lines; older ones load back in when scrolled to. The download button
in the header lists each day's log as plain text.

## Log files

`run.py` is the only writer. It keeps the raw stream, ANSI colors included, one
file per day:

```
logs/console/console.2026-11-27.0.raw
```

Restarts continue the day's file, marked by a `run.py started` line. A finished
day is gzipped (`.raw.gz`), and a day past 20 MB continues in part `.1`, `.2` and
so on. Days older than 90 days are deleted, then the oldest until the log fits
2 GB. The limits are set at the top of `utils/runtime/console_log.py`.

Downloads from the Console page strip the colors. To read a file with them,
`zcat console.2026-11-26.0.raw.gz | less -R`.

`bot.py` logs to stderr only, which `run.py` captures, so running `bot.py` on its
own writes no log files.

## Internal API

`bot.py` exposes a small internal API on **127.0.0.1:8001** that the dashboard
uses for live bot data (status, guilds, cogs, command sync). It binds loopback
only, so it is reachable from the host and not from the network.
