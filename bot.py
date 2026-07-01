import discord
from discord.ext import commands
import os
from dotenv import load_dotenv
from db.database import initialize_databases, close_all_databases
import asyncio

# Load environment variables from .env file
load_dotenv()
TOKEN = os.getenv("DISCORD_BOT_TOKEN")

# Initialize bot
intents = discord.Intents.default()
intents.members = True
intents.guilds = True
intents.message_content = True
bot = commands.Bot(command_prefix="ç!", intents=intents)

# Remove default help command to replace with a custom one
bot.remove_command("help")

# Load cogs asynchronously
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
                    print(f"Loaded cog: {cog_path}")
                except commands.NoEntryPointError:
                    pass
                except Exception as e:
                    print(f"Failed to load cog {cog_path}: {e}")

@bot.event
async def on_ready():
    """Event triggered when the bot is ready."""
    print(f"{bot.user.name} is ready and connected!")
    print(f"Command prefix: {bot.command_prefix}")
    await bot.change_presence(activity=discord.CustomActivity(name="/help", state="/help"))

    # Sync slash commands
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} slash commands.")
    except Exception as e:
        print(f"Failed to sync commands: {e}")

if __name__ == "__main__":
    async def main():
        # Initialize database connections
        await initialize_databases()

        # Load cogs
        await load_cogs(bot)

        try:
            # Start the bot
            await bot.start(TOKEN)
        finally:
            # Unload all cogs to trigger cog_unload hooks
            for extension in list(bot.extensions.keys()):
                try:
                    await bot.unload_extension(extension)
                    print(f"Successfully unloaded extension: {extension}")
                except Exception as e:
                    print(f"Failed to unload extension {extension}: {e}")

            # Close all databases
            await close_all_databases()

            # Add a short delay to ensure all tasks and cleanup complete
            await asyncio.sleep(2)

            # Ensure the bot is fully closed
            if not bot.is_closed():
                await bot.close()

    # Use asyncio.run to execute the main() coroutine
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
