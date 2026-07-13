import asyncio
import importlib
import logging
import sys
import time

import uvicorn
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from utils.log import LOG_BUFFER

templates = Jinja2Templates(directory="templates")
_start_time = time.time()
logger = logging.getLogger("web")


def _uptime() -> str:
    delta = int(time.time() - _start_time)
    hours, remainder = divmod(delta, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours}h {minutes}m {seconds}s"


def create_app(bot):
    app = FastAPI(docs_url=None, redoc_url=None)

    @app.get("/", response_class=HTMLResponse)
    async def dashboard(request: Request):
        ready = bot.is_ready()
        return templates.TemplateResponse(request=request, name="dashboard.html", context={
            "bot_name": bot.user.name if bot.user else "Bot",
            "bot_avatar_url": str(bot.user.display_avatar.url) if bot.user else None,
            "is_ready": ready,
            "latency": round(bot.latency * 1000) if ready else None,
            "guild_count": len(bot.guilds) if ready else None,
            "uptime": _uptime(),
            "extensions": sorted(bot.extensions.keys()),
        })

    @app.get("/guilds", response_class=HTMLResponse)
    async def guild_list(request: Request):
        guilds = sorted(
            [{"name": g.name, "id": g.id, "members": g.member_count} for g in bot.guilds],
            key=lambda g: g["name"].lower(),
        )
        return templates.TemplateResponse(request=request, name="partials/guild_list.html", context={
            "guilds": guilds,
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
        error = None
        try:
            await bot.reload_extension(extension)
            logger.info(f"Reloaded extension: {extension}")
        except Exception as e:
            error = str(e)
            logger.error(f"Failed to reload extension {extension}: {e}")
        return templates.TemplateResponse(request=request, name="partials/cog_row.html", context={
            "extension": extension,
            "loaded": True,
            "error": error,
        })

    @app.post("/cogs/unload/{extension:path}", response_class=HTMLResponse)
    async def unload_cog(request: Request, extension: str):
        error = None
        try:
            await bot.unload_extension(extension)
            logger.info(f"Unloaded extension: {extension}")
        except Exception as e:
            error = str(e)
            logger.error(f"Failed to unload extension {extension}: {e}")
        return templates.TemplateResponse(request=request, name="partials/cog_row.html", context={
            "extension": extension,
            "loaded": False,
            "error": error,
        })

    @app.post("/cogs/load/{extension:path}", response_class=HTMLResponse)
    async def load_cog_row(request: Request, extension: str):
        error = None
        try:
            await bot.load_extension(extension)
            logger.info(f"Loaded extension: {extension}")
        except Exception as e:
            error = str(e)
            logger.error(f"Failed to load extension {extension}: {e}")
        return templates.TemplateResponse(request=request, name="partials/cog_row.html", context={
            "extension": extension,
            "loaded": error is None,
            "error": error,
        })

    @app.post("/cogs/load")
    async def load_cog(extension: str = Form(...)):
        try:
            await bot.load_extension(extension)
            logger.info(f"Loaded extension: {extension}")
        except Exception as e:
            logger.error(f"Failed to load extension {extension}: {e}")
        return RedirectResponse("/", status_code=303)

    @app.post("/commands/sync", response_class=HTMLResponse)
    async def sync_commands(request: Request):
        error = None
        count = None
        try:
            synced = await bot.tree.sync()
            count = len(synced)
            logger.info(f"Synced {count} slash commands.")
        except Exception as e:
            error = str(e)
            logger.error(f"Failed to sync commands: {e}")
        return templates.TemplateResponse(request=request, name="partials/sync_result.html", context={
            "count": count,
            "error": error,
        })

    @app.get("/console", response_class=HTMLResponse)
    async def console(request: Request):
        ready = bot.is_ready()
        return templates.TemplateResponse(request=request, name="console.html", context={
            "bot_name": bot.user.name if bot.user else "Bot",
            "bot_avatar_url": str(bot.user.display_avatar.url) if bot.user else None,
            "is_ready": ready,
            "logs": list(LOG_BUFFER),
        })

    @app.get("/console/logs", response_class=HTMLResponse)
    async def console_logs(request: Request):
        return templates.TemplateResponse(request=request, name="partials/console_log.html", context={
            "logs": list(LOG_BUFFER),
        })

    @app.post("/web/reload", response_class=HTMLResponse)
    async def reload_web(request: Request):
        since = getattr(bot, "_web_epoch", 0)

        async def _reload():
            server = getattr(bot, "_web_server", None)
            if server:
                server.should_exit = True
                for _ in range(30):
                    if getattr(bot, "_web_server", None) is None:
                        break
                    await asyncio.sleep(0.1)

            web_module = sys.modules[__name__]
            importlib.reload(web_module)
            asyncio.create_task(web_module.start(bot))
            logger.info("Reloaded web dashboard.")

        asyncio.create_task(_reload())
        return templates.TemplateResponse(request=request, name="partials/web_reload_result.html", context={
            "since": since,
        })

    @app.get("/web/reload/status", response_class=HTMLResponse)
    async def reload_web_status(request: Request, since: int = 0):
        if getattr(bot, "_web_epoch", 0) > since:
            return templates.TemplateResponse(request=request, name="partials/web_reload_done.html", context={})
        return templates.TemplateResponse(request=request, name="partials/web_reload_result.html", context={
            "since": since,
        })

    @app.get("/web/reload/clear", response_class=HTMLResponse)
    async def reload_web_clear():
        return HTMLResponse('<span id="web-reload-status"></span>')

    return app


async def start(bot):
    app = create_app(bot)
    config = uvicorn.Config(app, host="0.0.0.0", port=8000, log_level="warning")
    server = uvicorn.Server(config)
    bot._web_server = server
    bot._web_epoch = getattr(bot, "_web_epoch", 0) + 1
    await server.serve()
    bot._web_server = None
