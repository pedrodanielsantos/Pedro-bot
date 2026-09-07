# Dashboard

Runs at **http://localhost:8000**, served by `run.py` itself rather than by the
bot. Shows real-time status, latency, uptime, and guild count, with
**Start/Stop/Reload** control over the bot process, a **Cog Manager**, and a
**Sync** button for slash commands.

Because the supervisor hosts it and the bot runs as a separate child process,
the dashboard stays up when the bot crashes or is stopped, which is what gives
you a Start button to bring it back.

> [!WARNING]
> The dashboard binds `0.0.0.0:8000` and has no authentication. Anyone who can
> reach that port can stop the bot and reload cogs, so keep it behind a firewall
> or bind it to loopback in [`web.py`](../web.py) if the host is exposed.

## Console

A separate **Console** page (`/console`) is a live, auto-scrolling mirror of every
supervised process's stdout/stderr (not just logged output), rendered client-side
from `logs/console.raw` so it stays visible across a crash or restart. Lavalink's
own Spring Boot lines are restated in the bot's log format on the way through, so
both processes read as one log.

## Internal API

`bot.py` exposes a small internal API on **127.0.0.1:8001** that the dashboard
uses for live bot data (status, guilds, cogs, command sync). It binds loopback
only, so it is reachable from the host and not from the network.
