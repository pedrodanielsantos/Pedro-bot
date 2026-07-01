import time

import uvicorn
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

templates = Jinja2Templates(directory="templates")
_start_time = time.time()


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
        return HTMLResponse("")

    @app.post("/cogs/reload/{extension:path}", response_class=HTMLResponse)
    async def reload_cog(request: Request, extension: str):
        error = None
        try:
            await bot.reload_extension(extension)
            print(f"[Web] Reloaded extension: {extension}")
        except Exception as e:
            error = str(e)
            print(f"[Web] Failed to reload extension {extension}: {e}")
        return templates.TemplateResponse(request=request, name="partials/cog_row.html", context={
            "extension": extension,
            "error": error,
        })

    @app.post("/cogs/unload/{extension:path}", response_class=HTMLResponse)
    async def unload_cog(extension: str):
        try:
            await bot.unload_extension(extension)
            print(f"[Web] Unloaded extension: {extension}")
        except Exception as e:
            print(f"[Web] Failed to unload extension {extension}: {e}")
        return HTMLResponse("")

    @app.post("/cogs/load")
    async def load_cog(extension: str = Form(...)):
        try:
            await bot.load_extension(extension)
            print(f"[Web] Loaded extension: {extension}")
        except Exception as e:
            print(f"[Web] Failed to load extension {extension}: {e}")
        return RedirectResponse("/", status_code=303)

    return app


async def start(bot):
    app = create_app(bot)
    config = uvicorn.Config(app, host="0.0.0.0", port=8000, log_level="warning")
    server = uvicorn.Server(config)
    bot._web_server = server
    await server.serve()
    bot._web_server = None
