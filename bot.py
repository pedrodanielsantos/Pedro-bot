import discord
from discord.ext import commands
import logging
import os
from dotenv import load_dotenv
from db.database import initialize_databases, close_all_databases
from utils.log import setup_logging
import asyncio
import web

load_dotenv()
TOKEN = os.getenv("DISCORD_BOT_TOKEN")
if not TOKEN:
    raise SystemExit("DISCORD_BOT_TOKEN is not set. Add it to your .env file.")

setup_logging()
logger = logging.getLogger("bot")

intents = discord.Intents.default()
intents.members = True
intents.guilds = True
intents.message_content = True
bot = commands.Bot(command_prefix="ç!", intents=intents)

# A custom /help command is loaded from cogs, so the built-in one is removed to avoid a name clash.
bot.remove_command("help")

async def load_cogs(bot):
    cogs_dir = os.path.join(os.path.dirname(__file__), "cogs")
    for root, dirs, files in os.walk(cogs_dir):
        for filename in files:
            if filename.endswith(".py") and not filename.startswith("__"):
                relative_path = os.path.relpath(root, cogs_dir)
                if relative_path == ".":
                    cog_path = f"cogs.{filename[:-3]}"
                else:
                    cog_path = f"cogs.{relative_path.replace(os.sep, '.')}.{filename[:-3]}"

                try:
                    await bot.load_extension(cog_path)
                    logger.info(f"Loaded cog: {cog_path}")
                except commands.NoEntryPointError:
                    pass
                except Exception as e:
                    logger.error(f"Failed to load cog {cog_path}: {e}")

has_synced = False

@bot.event
async def on_ready():
    global has_synced

    logger.info(f"{bot.user.name} is ready and connected!")
    logger.info(f"Command prefix: {bot.command_prefix}")
    await bot.change_presence(activity=discord.CustomActivity(name="/help", state="/help"))

    # on_ready can fire again after a reconnect, so this only syncs once per process.
    # Use ç!sync (developer_tools.py) to force a resync without restarting.
    if not has_synced:
        try:
            synced = await bot.tree.sync()
            logger.info(f"Synced {len(synced)} slash commands.")
            has_synced = True
        except Exception as e:
            logger.error(f"Failed to sync commands: {e}")

if __name__ == "__main__":
    async def main():
        await initialize_databases()
        await load_cogs(bot)

        try:
            await asyncio.gather(bot.start(TOKEN), web.start(bot))
        finally:
            # Unloading each extension explicitly ensures cog_unload hooks run before exit.
            for extension in list(bot.extensions.keys()):
                try:
                    await bot.unload_extension(extension)
                    logger.info(f"Successfully unloaded extension: {extension}")
                except Exception as e:
                    logger.error(f"Failed to unload extension {extension}: {e}")

            await close_all_databases()

            # Gives any straggling background tasks a moment to finish before the process exits.
            await asyncio.sleep(2)

            if not bot.is_closed():
                await bot.close()

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
