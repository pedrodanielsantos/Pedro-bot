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
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from utils.cogs import discover_cog_paths
from utils.log import colorize_log_line, tail_log_file

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
        # sock_connect is the important cap here: when nothing is listening on the
        # internal API, the TCP connect attempt should fail almost instantly — but
        # if it instead hangs (observed on the Windows host), the plain `total`
        # timeout meant every offline page load ate the full multi-second timeout.
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

    @app.get("/", response_class=HTMLResponse)
    async def dashboard(request: Request):
        status = await _status()
        ready = bool(status.get("ready"))

        if ready:
            cogs_data = await _internal_get("/cogs")
            cogs = cogs_data["cogs"] if cogs_data else []
        else:
            # Walks the cogs directory and reads every file to check for a setup()
            # entrypoint — real disk I/O, so keep it off the event loop.
            paths = await asyncio.to_thread(discover_cog_paths, COGS_DIR)
            cogs = [{"extension": path, "loaded": False} for path in sorted(paths)]

        return templates.TemplateResponse(request=request, name="dashboard.html", context={
            "bot_name": status.get("bot_name") or "Bot",
            "bot_avatar_url": status.get("bot_avatar_url"),
            "is_ready": ready,
            "latency": status.get("latency_ms"),
            "guild_count": status.get("guild_count"),
            "uptime": status.get("uptime") or "—",
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

    @app.post("/cogs/reload/{extension:path}", response_class=HTMLResponse)
    async def reload_cog(request: Request, extension: str):
        result = await _internal_post(f"/cogs/reload/{extension}")
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
        rows = result["rows"] if result else [
            {"extension": extension, "loaded": False, "error": "Bot is offline"} for extension in cogs
        ]
        return templates.TemplateResponse(request=request, name="partials/cog_rows_oob.html", context={
            "rows": rows,
        })

    @app.post("/cogs/bulk/load", response_class=HTMLResponse)
    async def bulk_load_cogs(request: Request, cogs: list[str] = Form(...)):
        result = await _internal_post("/cogs/bulk/load", json={"cogs": cogs})
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
    async def bot_status_partial(request: Request):
        status = await _status()
        ready = bool(status.get("ready"))
        return templates.TemplateResponse(request=request, name="partials/bot_control.html", context={
            "is_ready": ready,
            "status": supervisor.status,
            # This route is only ever reached via the poll that fires while not-ready, so a
            # ready=True result here is by definition the first observation of it coming back up.
            "just_restarted": ready and supervisor.status == "running",
        })

    @app.get("/bot/status/clear", response_class=HTMLResponse)
    async def bot_status_clear():
        return HTMLResponse("")

    @app.get("/console", response_class=HTMLResponse)
    async def console(request: Request):
        status = await _status()
        logs = await asyncio.to_thread(tail_log_file)
        return templates.TemplateResponse(request=request, name="console.html", context={
            "bot_name": status.get("bot_name") or "Bot",
            "bot_avatar_url": status.get("bot_avatar_url"),
            "is_ready": bool(status.get("ready")),
            "logs": logs,
            "supervisor_status": supervisor.status,
        })

    @app.get("/console/logs", response_class=HTMLResponse)
    async def console_logs(request: Request):
        logs = await asyncio.to_thread(tail_log_file)
        return templates.TemplateResponse(request=request, name="partials/console_log.html", context={
            "logs": logs,
        })

    @app.post("/web/reload", response_class=HTMLResponse)
    async def reload_web(request: Request):
        since = web_state.web_epoch

        async def _reload():
            server = web_state.web_server
            if server:
                server.should_exit = True
                for _ in range(100):
                    if web_state.web_server is None:
                        break
                    await asyncio.sleep(0.1)
                else:
                    logger.warning("Old web server did not shut down in time; reloading anyway.")

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
    web_state.web_epoch += 1
    await server.serve()
    web_state.web_server = None
