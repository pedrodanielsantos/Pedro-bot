import discord
from discord.ext import commands
import logging
import os
import signal
import sys
from datetime import datetime, timezone
from dotenv import load_dotenv
from db.database import initialize_databases, close_all_databases
from utils.log import setup_logging
from utils.cogs import discover_cog_paths
from utils.uptime import format_uptime
import asyncio
import internal_api

_shutdown_event = None

if sys.platform == "win32":
    # run.py spawns this process in its own console process group so it can send
    # CTRL_BREAK_EVENT for a graceful stop without also signalling the parent.
    # Python's default handler for SIGBREAK just kills the process, so trigger the
    # clean-shutdown path in main() instead. This handler can fire deep inside
    # uvicorn's own signal handling (it re-raises via signal.raise_signal so outer
    # code sees it too), so it must not raise an exception here directly — doing so
    # previously confused asyncio's task bookkeeping ("Task exception was never
    # retrieved"). Setting an Event is safe from a signal handler since Python signal
    # handlers always run on the main thread, same as the event loop.
    def _handle_sigbreak(signum, frame):
        if _shutdown_event is not None:
            _shutdown_event.set()

    signal.signal(signal.SIGBREAK, _handle_sigbreak)

load_dotenv()
TOKEN = os.getenv("DISCORD_BOT_TOKEN")
if not TOKEN:
    raise SystemExit("DISCORD_BOT_TOKEN is not set. Add it to your .env file")

setup_logging()
logger = logging.getLogger("bot")

intents = discord.Intents.default()
intents.members = True
intents.guilds = True
intents.message_content = True
bot = commands.Bot(command_prefix="ç!", intents=intents)
bot.launch_time = datetime.now(timezone.utc)

# A custom /help command is loaded from cogs, so the built-in one is removed to avoid a name clash.
bot.remove_command("help")

async def load_cogs(bot):
    cogs_dir = os.path.join(os.path.dirname(__file__), "cogs")
    for cog_path in discover_cog_paths(cogs_dir):
        try:
            await bot.load_extension(cog_path)
            logger.info(f"Loaded: {cog_path}")
        except commands.NoEntryPointError:
            pass
        except Exception as e:
            logger.error(f"Failed to load cog {cog_path}: {e}")

has_synced = False
has_greeted = False

@bot.event
async def on_ready():
    global has_synced, has_greeted

    # on_ready can fire again after a reconnect; only banner the first one so
    # a flaky connection doesn't spam the console with repeated startup blocks.
    if not has_greeted:
        logger.info("=" * 56)
        logger.info(f"{bot.user.name} online and ready with devtools prefix {bot.command_prefix}")
        logger.info("=" * 56)
        has_greeted = True
    else:
        logger.info(f"{bot.user.name} reconnected")

    await bot.change_presence(activity=discord.CustomActivity(name="/help", state="/help"))

    # on_ready can fire again after a reconnect, so this only syncs once per process.
    # Use ç!sync (developer_tools.py) or the dashboard's Sync button to force a resync.
    # Set SYNC_ON_STARTUP=false in .env to skip this entirely, e.g. during restart testing
    # where every crash/restart would otherwise trigger a fresh command sync.
    sync_on_startup = os.getenv("SYNC_ON_STARTUP", "true").lower() != "false"
    if sync_on_startup and not has_synced:
        try:
            synced = await bot.tree.sync()
            logger.info(f"Synced {len(synced)} slash commands")
            has_synced = True
        except Exception as e:
            logger.error(f"Failed to sync commands: {e}")

if __name__ == "__main__":
    async def main():
        global _shutdown_event
        await initialize_databases()
        await load_cogs(bot)

        _shutdown_event = asyncio.Event()
        bot_task = asyncio.create_task(bot.start(TOKEN))
        api_task = asyncio.create_task(internal_api.start(bot))
        shutdown_task = asyncio.create_task(_shutdown_event.wait())

        try:
            done, pending = await asyncio.wait(
                {bot_task, api_task, shutdown_task}, return_when=asyncio.FIRST_COMPLETED,
            )
            for task in pending:
                task.cancel()
            if pending:
                await asyncio.gather(*pending, return_exceptions=True)
            for task in done:
                if task is shutdown_task:
                    continue
                exc = task.exception()
                if exc:
                    raise exc
        finally:
            # Unloading each extension explicitly ensures cog_unload hooks run before exit.
            for extension in list(bot.extensions.keys()):
                try:
                    await bot.unload_extension(extension)
                    logger.info(f"Unloaded: {extension}")
                except Exception as e:
                    logger.error(f"Failed to unload extension {extension}: {e}")

            await close_all_databases()

            # Gives any straggling background tasks a moment to finish before the process exits.
            await asyncio.sleep(2)

            if not bot.is_closed():
                await bot.close()

            logger.info("=" * 56)
            logger.info(f"Bot shut down cleanly after running for {format_uptime(bot.launch_time)}")
            logger.info("=" * 56)

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
