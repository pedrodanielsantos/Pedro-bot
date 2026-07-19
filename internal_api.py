import logging
import os

import uvicorn
from fastapi import FastAPI, Body

from utils.cogs import discover_cog_paths
from utils.uptime import format_uptime

COGS_DIR = os.path.join(os.path.dirname(__file__), "cogs")

logger = logging.getLogger("internal_api")


def create_internal_app(bot):
    app = FastAPI(docs_url=None, redoc_url=None)

    @app.get("/status")
    async def status():
        ready = bot.is_ready()
        return {
            "ready": ready,
            "bot_name": bot.user.name if bot.user else None,
            "bot_avatar_url": str(bot.user.display_avatar.url) if bot.user else None,
            "latency_ms": round(bot.latency * 1000) if ready else None,
            "guild_count": len(bot.guilds) if ready else None,
            "uptime": format_uptime(bot.launch_time),
        }

    @app.get("/cogs")
    async def cogs():
        all_paths = sorted(set(discover_cog_paths(COGS_DIR)) | set(bot.extensions.keys()))
        return {"cogs": [{"extension": path, "loaded": path in bot.extensions} for path in all_paths]}

    @app.get("/guilds")
    async def guilds():
        return {
            "guilds": sorted(
                [{"name": g.name, "id": g.id, "members": g.member_count} for g in bot.guilds],
                key=lambda g: g["name"].lower(),
            )
        }

    @app.post("/cogs/reload/{extension:path}")
    async def reload_cog(extension: str):
        error = None
        try:
            await bot.reload_extension(extension)
            logger.info(f"Reloaded: {extension}")
        except Exception as e:
            error = str(e)
            logger.error(f"Failed to reload extension {extension}: {e}")
        return {"extension": extension, "loaded": extension in bot.extensions, "error": error}

    @app.post("/cogs/unload/{extension:path}")
    async def unload_cog(extension: str):
        error = None
        try:
            await bot.unload_extension(extension)
            logger.info(f"Unloaded: {extension}")
        except Exception as e:
            error = str(e)
            logger.error(f"Failed to unload extension {extension}: {e}")
        return {"extension": extension, "loaded": extension in bot.extensions, "error": error}

    @app.post("/cogs/load/{extension:path}")
    async def load_cog(extension: str):
        error = None
        try:
            await bot.load_extension(extension)
            logger.info(f"Loaded: {extension}")
        except Exception as e:
            error = str(e)
            logger.error(f"Failed to load extension {extension}: {e}")
        return {"extension": extension, "loaded": extension in bot.extensions, "error": error}

    @app.post("/cogs/bulk/reload")
    async def bulk_reload_cogs(cogs: list[str] = Body(embed=True)):
        rows = []
        for extension in cogs:
            error = None
            try:
                await bot.reload_extension(extension)
                logger.info(f"Reloaded: {extension}")
            except Exception as e:
                error = str(e)
                logger.error(f"Failed to reload extension {extension}: {e}")
            rows.append({"extension": extension, "loaded": extension in bot.extensions, "error": error})
        return {"rows": rows}

    @app.post("/cogs/bulk/unload")
    async def bulk_unload_cogs(cogs: list[str] = Body(embed=True)):
        rows = []
        for extension in cogs:
            if extension not in bot.extensions:
                continue
            error = None
            try:
                await bot.unload_extension(extension)
                logger.info(f"Unloaded: {extension}")
            except Exception as e:
                error = str(e)
                logger.error(f"Failed to unload extension {extension}: {e}")
            rows.append({"extension": extension, "loaded": extension in bot.extensions, "error": error})
        return {"rows": rows}

    @app.post("/cogs/bulk/load")
    async def bulk_load_cogs(cogs: list[str] = Body(embed=True)):
        rows = []
        for extension in cogs:
            if extension in bot.extensions:
                continue
            error = None
            try:
                await bot.load_extension(extension)
                logger.info(f"Loaded: {extension}")
            except Exception as e:
                error = str(e)
                logger.error(f"Failed to load extension {extension}: {e}")
            rows.append({"extension": extension, "loaded": extension in bot.extensions, "error": error})
        return {"rows": rows}

    @app.post("/commands/sync")
    async def sync_commands():
        error = None
        count = None
        try:
            synced = await bot.tree.sync()
            count = len(synced)
            logger.info(f"Synced {count} slash commands.")
        except Exception as e:
            error = str(e)
            logger.error(f"Failed to sync commands: {e}")
        return {"count": count, "error": error}

    return app


async def start(bot):
    app = create_internal_app(bot)
    config = uvicorn.Config(app, host="127.0.0.1", port=8001, log_level="warning")
    server = uvicorn.Server(config)
    await server.serve()
