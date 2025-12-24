import discord
from discord.ext import commands
import os
from dotenv import load_dotenv
from utils.graceful_shutdown import setup_signal_handlers
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
bot = commands.Bot(command_prefix=".", intents=intents)

# Remove default help command to replace with a custom one
bot.remove_command("help")

# Load cogs asynchronously
async def load_cogs(bot):
    COGS = [
        "cogs.customrole",
        "cogs.help",
#       "cogs.imagine",
#       "cogs.model",
        "cogs.image",
        "cogs.cat",
        "cogs.dog",
        "cogs.8ball",
        "cogs.about",
        "cogs.ping",
        "cogs.userinfo",
        "cogs.serverinfo",
        "cogs.avatar",
        "cogs.choice",
        "cogs.setup",
        "cogs.rename",
        "cogs.resize",
#       "cogs.ask"
    ]
    for cog in COGS:
        try:
            await bot.load_extension(cog)
            print(f"Loaded cog: {cog}")
        except Exception as e:
            print(f"Failed to load cog {cog}: {e}")

@bot.event
async def on_ready():
    """Event triggered when the bot is ready."""
    print(f"{bot.user.name} is ready and connected!")
    await bot.change_presence(activity=discord.Game(name=".help"))

    # Sync slash commands
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} slash commands.")
    except Exception as e:
        print(f"Failed to sync commands: {e}")

if __name__ == "__main__":
    async def main():
        # Initialize database connections
        initialize_databases()

        # Set up signal handlers for clean shutdown
        setup_signal_handlers(bot)

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
            close_all_databases()

            # Add a short delay to ensure all tasks and cleanup complete
            await asyncio.sleep(2)

            # Ensure the bot is fully closed
            if not bot.is_closed():
                await bot.close()

    # Use asyncio.run to execute the main() coroutine
    asyncio.run(main())