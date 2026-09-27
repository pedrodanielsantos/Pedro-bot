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
from `logs/console.raw` so it stays visible across a crash or restart. Lavalink's
own Spring Boot lines are restated in the bot's log format on the way through, so
both processes read as one log.

## Internal API

`bot.py` exposes a small internal API on **127.0.0.1:8001** that the dashboard
uses for live bot data (status, guilds, cogs, command sync). It binds loopback
only, so it is reachable from the host and not from the network.
