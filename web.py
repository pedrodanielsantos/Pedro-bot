import asyncio
import importlib
import logging
import os
import subprocess
import sys

import aiohttp
import discord
import uvicorn
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.templating import Jinja2Templates

from utils.cogs import discover_cog_paths
from utils.log import colorize_log_line, log_file_size, tail_log_file, tail_log_lines

COGS_DIR = os.path.join(os.path.dirname(__file__), "cogs")
INTERNAL_API = "http://127.0.0.1:8001"

templates = Jinja2Templates(directory="templates")
templates.env.globals["discord_version"] = discord.__version__
templates.env.filters["colorize_log"] = colorize_log_line


def _commit_hash() -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, check=True, timeout=5,
        )
        return result.stdout.strip()
    except (subprocess.SubprocessError, OSError):
        return None


templates.env.globals["commit_hash"] = _commit_hash()
logger = logging.getLogger("web")


def _log_task_exception(task):
    if task.cancelled():
        return
    exc = task.exception()
    if exc:
        logger.error("Web server task failed", exc_info=exc)


async def _internal_get(path: str):
    try:
        # sock_connect is the important limit here. If nothing is listening, the connect
        # should fail almost instantly. On Windows it can hang instead, and the plain
        # total timeout let every offline page load wait out the full multi-second timeout.
        timeout = aiohttp.ClientTimeout(total=2, sock_connect=0.5)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(f"{INTERNAL_API}{path}") as resp:
                if resp.status != 200:
                    return None
                return await resp.json()
    except (aiohttp.ClientError, asyncio.TimeoutError):
        return None


async def _internal_post(path: str, json=None):
    try:
        timeout = aiohttp.ClientTimeout(total=5, sock_connect=0.5)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(f"{INTERNAL_API}{path}", json=json) as resp:
                if resp.status != 200:
                    return None
                return await resp.json()
    except (aiohttp.ClientError, asyncio.TimeoutError):
        return None


def create_app(supervisor, web_state):
    app = FastAPI(docs_url=None, redoc_url=None)

    async def _status():
        data = await _internal_get("/status")
        return data or {}

    async def _cogs():
        # Based on whether the internal API answers, not bot.is_ready(). bot.py loads
        # cogs before connecting to Discord, so extensions can be loaded already while
        # is_ready() is still false. /cogs reads bot.extensions directly and works
        # either way, so we get accurate state instead of showing "unloaded" too early.
        cogs_data = await _internal_get("/cogs")
        if cogs_data:
            return cogs_data["cogs"]
        # No response means bot.py isn't running. Walk the cogs directory and check
        # each file for a setup() entrypoint instead. Real disk I/O, keep off the event loop.
        paths = await asyncio.to_thread(discover_cog_paths, COGS_DIR)
        return [{"extension": path, "loaded": False} for path in sorted(paths)]

    @app.get("/", response_class=HTMLResponse)
    async def dashboard(request: Request):
        status = await _status()
        ready = bool(status.get("ready"))
        cogs = await _cogs()

        return templates.TemplateResponse(request=request, name="dashboard.html", context={
            "bot_name": status.get("bot_name") or "Bot",
            "bot_avatar_url": status.get("bot_avatar_url"),
            "is_ready": ready,
            "latency": status.get("latency_ms"),
            "guild_count": status.get("guild_count"),
            "uptime": status.get("uptime") or "—",
            "launch_time": status.get("launch_time"),
            "cogs": cogs,
            "supervisor_status": supervisor.status,
        })

    @app.get("/guilds", response_class=HTMLResponse)
    async def guild_list(request: Request):
        data = await _internal_get("/guilds")
        return templates.TemplateResponse(request=request, name="partials/guild_list.html", context={
            "guilds": data["guilds"] if data else [],
        })

    @app.get("/guilds/clear", response_class=HTMLResponse)
    async def guild_list_clear():
        return HTMLResponse(
            '<button id="guild-toggle" class="btn" hx-swap-oob="true" '
            'hx-get="/guilds" hx-target="#guild-list" hx-swap="innerHTML">'
            "View</button>"
        )

    @app.get("/cogs/refresh", response_class=HTMLResponse)
    async def cogs_refresh(request: Request):
        # Called on a ready flip, a control flip, or another tab's cog change.
        # Replaces the whole table instead of patching rows one by one.
        cogs = await _cogs()
        return templates.TemplateResponse(request=request, name="partials/cog_rows.html", context={
            "rows": [
                {"extension": cog["extension"], "loaded": cog["loaded"], "error": None, "just_reloaded": False}
                for cog in cogs
            ],
        })

    @app.post("/cogs/reload/{extension:path}", response_class=HTMLResponse)
    async def reload_cog(request: Request, extension: str):
        result = await _internal_post(f"/cogs/reload/{extension}")
        web_state.cogs_epoch += 1
        error = result.get("error") if result else "Bot is offline"
        return templates.TemplateResponse(request=request, name="partials/cog_row.html", context={
            "extension": extension,
            "loaded": True,
            "error": error,
            "just_reloaded": error is None,
        })

    @app.get("/cogs/badge/clear", response_class=HTMLResponse)
    async def cog_badge_clear():
        return HTMLResponse("")

    @app.post("/cogs/unload/{extension:path}", response_class=HTMLResponse)
    async def unload_cog(request: Request, extension: str):
        result = await _internal_post(f"/cogs/unload/{extension}")
        web_state.cogs_epoch += 1
        loaded = bool(result and result.get("loaded"))
        error = result.get("error") if result else "Bot is offline"
        return templates.TemplateResponse(request=request, name="partials/cog_row.html", context={
            "extension": extension,
            "loaded": loaded,
            "error": error,
        })

    @app.post("/cogs/load/{extension:path}", response_class=HTMLResponse)
    async def load_cog_row(request: Request, extension: str):
        result = await _internal_post(f"/cogs/load/{extension}")
        web_state.cogs_epoch += 1
        loaded = bool(result and result.get("loaded"))
        error = result.get("error") if result else "Bot is offline"
        return templates.TemplateResponse(request=request, name="partials/cog_row.html", context={
            "extension": extension,
            "loaded": loaded,
            "error": error,
        })

    @app.post("/cogs/bulk/reload", response_class=HTMLResponse)
    async def bulk_reload_cogs(request: Request, cogs: list[str] = Form(...)):
        result = await _internal_post("/cogs/bulk/reload", json={"cogs": cogs})
        web_state.cogs_epoch += 1
        rows = result["rows"] if result else [
            {"extension": extension, "loaded": False, "error": "Bot is offline"} for extension in cogs
        ]
        for row in rows:
            row["just_reloaded"] = row.get("error") is None
        return templates.TemplateResponse(request=request, name="partials/cog_rows_oob.html", context={
            "rows": rows,
        })

    @app.post("/cogs/bulk/unload", response_class=HTMLResponse)
    async def bulk_unload_cogs(request: Request, cogs: list[str] = Form(...)):
        result = await _internal_post("/cogs/bulk/unload", json={"cogs": cogs})
        web_state.cogs_epoch += 1
        rows = result["rows"] if result else [
            {"extension": extension, "loaded": False, "error": "Bot is offline"} for extension in cogs
        ]
        return templates.TemplateResponse(request=request, name="partials/cog_rows_oob.html", context={
            "rows": rows,
        })

    @app.post("/cogs/bulk/load", response_class=HTMLResponse)
    async def bulk_load_cogs(request: Request, cogs: list[str] = Form(...)):
        result = await _internal_post("/cogs/bulk/load", json={"cogs": cogs})
        web_state.cogs_epoch += 1
        rows = result["rows"] if result else [
            {"extension": extension, "loaded": False, "error": "Bot is offline"} for extension in cogs
        ]
        return templates.TemplateResponse(request=request, name="partials/cog_rows_oob.html", context={
            "rows": rows,
        })

    @app.post("/commands/sync", response_class=HTMLResponse)
    async def sync_commands(request: Request):
        result = await _internal_post("/commands/sync")
        count = result.get("count") if result else None
        error = result.get("error") if result else "Bot is offline"
        return templates.TemplateResponse(request=request, name="partials/sync_result.html", context={
            "count": count,
            "error": error,
        })

    @app.post("/bot/start", response_class=HTMLResponse)
    async def bot_start(request: Request):
        await supervisor.start()
        return templates.TemplateResponse(request=request, name="partials/bot_control.html", context={
            "is_ready": False,
            "status": supervisor.status,
        })

    @app.post("/bot/stop", response_class=HTMLResponse)
    async def bot_stop(request: Request):
        await supervisor.stop()
        return templates.TemplateResponse(request=request, name="partials/bot_control.html", context={
            "is_ready": False,
            "status": supervisor.status,
        })

    @app.get("/bot/status", response_class=HTMLResponse)
    async def bot_status_partial(request: Request, announce: bool = False):
        status = await _status()
        ready = bool(status.get("ready"))
        return templates.TemplateResponse(request=request, name="partials/bot_control.html", context={
            "is_ready": ready,
            "status": supervisor.status,
            # announce=true only comes from the self-poll below, which only runs while
            # not ready, so a ready result there really is the first time we've seen it
            # come back. Without this flag, the SSE refresh on every reconnect would
            # show the "Started" badge every time.
            "just_restarted": announce and ready and supervisor.status == "running",
        })

    @app.get("/bot/status/clear", response_class=HTMLResponse)
    async def bot_status_clear():
        return HTMLResponse("")

    @app.get("/status/stream")
    async def status_stream(request: Request):
        server = web_state.web_server

        async def event_stream():
            # supervisor.status lives here, not on the bot, so the internal API's stream
            # can't carry it. Check it at each relayed event boundary instead of polling
            # separately, so an idle tab still learns when another tab starts or stops the bot.
            last_status = None
            last_cogs_epoch = web_state.cogs_epoch

            def status_event():
                nonlocal last_status
                if supervisor.status == last_status:
                    return ""
                last_status = supervisor.status
                return f"event: control\ndata: {last_status}\n\n"

            def cogs_event():
                nonlocal last_cogs_epoch
                if web_state.cogs_epoch == last_cogs_epoch:
                    return ""
                last_cogs_epoch = web_state.cogs_epoch
                return f"event: cogs\ndata: {last_cogs_epoch}\n\n"

            try:
                timeout = aiohttp.ClientTimeout(total=None, sock_connect=0.5)
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.get(f"{INTERNAL_API}/status/stream") as resp:
                        # A blank line ends an SSE event, so the next line starts a new one.
                        # Only inject our own events there, never mid-event, or both get corrupted.
                        at_boundary = True
                        async for line in resp.content:
                            # Also stop when this server wants to shut down, e.g. for /web/reload,
                            # not just on client disconnect. Otherwise this stream never ends,
                            # graceful shutdown blocks forever, and we're forced into a risky port rebind.
                            if await request.is_disconnected() or (server and server.should_exit):
                                return
                            if at_boundary:
                                yield status_event()
                                yield cogs_event()
                            yield line.decode("utf-8")
                            at_boundary = line in (b"\n", b"\r\n")
                # If we get here, the internal stream ended on its own, e.g. the bot process
                # died, instead of us returning above. Tell the browser now instead of
                # waiting for a reconnect that would arrive after the fact.
            except (aiohttp.ClientError, asyncio.TimeoutError):
                pass

            # Only reached if the internal API stream ended or never connected,
            # meaning the bot isn't reachable right now.
            yield status_event()
            yield 'event: ready\ndata: {"ready": false, "launch_time": null}\n\n'
            yield "data: \n\n"

        return StreamingResponse(event_stream(), media_type="text/event-stream", headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        })

    @app.get("/console", response_class=HTMLResponse)
    async def console(request: Request):
        status = await _status()
        # Read the size first, then the tail, so the live stream's resume point can
        # never be ahead of what the static render actually shows.
        log_pos = await asyncio.to_thread(log_file_size)
        logs = await asyncio.to_thread(tail_log_file)
        return templates.TemplateResponse(request=request, name="console.html", context={
            "bot_name": status.get("bot_name") or "Bot",
            "bot_avatar_url": status.get("bot_avatar_url"),
            "is_ready": bool(status.get("ready")),
            "logs": logs,
            "log_pos": log_pos,
            "supervisor_status": supervisor.status,
        })

    @app.get("/console/logs/stream")
    async def console_logs_stream(request: Request):
        server = web_state.web_server
        # EventSource remembers the last "id:" it saw and resends it as this header on
        # every reconnect, so we can resume the tail instead of jumping to "now" and
        # dropping whatever was logged in the gap. The very first connection has no id
        # to send yet, so console.html passes one as a query param instead, seeded from
        # the byte offset its own static render already covers.
        last_id = request.headers.get("last-event-id") or request.query_params.get("last_id")
        start_pos = int(last_id) if last_id and last_id.isdigit() else None

        async def event_stream():
            async for pos, line in tail_log_lines(start_pos=start_pos):
                if await request.is_disconnected() or (server and server.should_exit):
                    break
                if line is None:
                    yield ": keepalive\n\n"
                else:
                    yield f"id: {pos}\ndata: {colorize_log_line(line)}\n\n"

        return StreamingResponse(event_stream(), media_type="text/event-stream", headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        })

    @app.post("/web/reload", response_class=HTMLResponse)
    async def reload_web(request: Request):
        since = web_state.web_epoch

        async def _reload():
            # A second reload fired while this one is still tearing down the old server
            # would touch web_state.web_server at the same time. Queue behind any
            # in-flight reload instead of racing it.
            async with web_state.reload_lock:
                server = web_state.web_server
                if server:
                    server.should_exit = True
                    for i in range(100):
                        if web_state.web_server is None:
                            logger.info(f"Old web server shut down cleanly after {i * 0.1:.1f}s.")
                            break
                        await asyncio.sleep(0.1)
                    else:
                        # Starting a new server now would race the still-bound old one for
                        # port 8000, and losing that race would orphan the old server for good:
                        # web_state.web_server is our only handle on it, and overwriting it here
                        # means nothing could ever call should_exit on it again. Bail out and
                        # leave the reference in place so the next reload attempt waits on it instead.
                        logger.error("Old web server did not shut down in time; aborting reload.")
                        return

                web_module = sys.modules[__name__]
                importlib.reload(web_module)
                new_task = asyncio.create_task(web_module.start(supervisor, web_state))
                new_task.add_done_callback(_log_task_exception)
                logger.info("Reloaded web dashboard.")

        asyncio.create_task(_reload())
        return templates.TemplateResponse(request=request, name="partials/web_reload_result.html", context={
            "since": since,
        })

    @app.get("/web/reload/status", response_class=HTMLResponse)
    async def reload_web_status(request: Request, since: int = 0):
        if web_state.web_epoch > since:
            return templates.TemplateResponse(request=request, name="partials/web_reload_done.html", context={})
        return templates.TemplateResponse(request=request, name="partials/web_reload_result.html", context={
            "since": since,
        })

    @app.get("/web/reload/clear", response_class=HTMLResponse)
    async def reload_web_clear():
        return HTMLResponse('<span id="web-reload-status"></span>')

    return app


async def start(supervisor, web_state):
    app = create_app(supervisor, web_state)
    config = uvicorn.Config(app, host="0.0.0.0", port=8000, log_level="warning")
    server = uvicorn.Server(config)
    web_state.web_server = server

    # Run serve() as a task and poll server.started (set by uvicorn right after a
    # successful bind) instead of awaiting it directly, so web_epoch only advances once
    # the new server is actually live. Otherwise the reload banner could report success
    # the instant a bind is attempted, even if it fails a moment later.
    serve_task = asyncio.create_task(server.serve())
    try:
        while not server.started and not serve_task.done():
            await asyncio.sleep(0.05)

        if not server.started:
            await serve_task  # re-raises the bind failure as SystemExit
            return

        web_state.web_epoch += 1
        epoch = web_state.web_epoch
        logger.info(f"Web server (epoch {epoch}) started.")
        await serve_task
        logger.info(f"Web server (epoch {epoch}) stopped.")
    except SystemExit:
        # uvicorn reacts to a failed bind (e.g. the old server hasn't released the port
        # yet) with sys.exit(1). SystemExit is a BaseException, so asyncio won't swallow
        # it like a normal task error. Left unguarded, it would escape this background
        # task and take the whole run.py process down with it.
        logger.error("Web server failed to start: port 8000 still in use.")
    finally:
        web_state.web_server = None
