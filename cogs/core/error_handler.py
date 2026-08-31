import discord
from discord import app_commands
from discord.ext import commands
import logging
import asyncio
import aiohttp
from utils.embeds import send_error
from utils.errors import UserError

logger = logging.getLogger("errors")

class ErrorHandler(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Register the global error handler for the application command tree
        self.bot.tree.on_error = self.on_app_command_error

    async def cog_unload(self):
        # Unregister the handler when the cog is unloaded
        self.bot.tree.on_error = None

    @commands.Cog.listener()
    async def on_command_error(self, ctx, error):
        # Any message starting with the prefix that isn't a real command lands here; ignore.
        if isinstance(error, commands.CommandNotFound):
            return
        raise error

    async def on_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        # Unwrap CommandInvokeError (errors that happen inside the command function)
        if isinstance(error, app_commands.CommandInvokeError):
            error = error.original

        # Expected, user-facing validation failures raised deliberately by commands: never logged as a bug.
        if isinstance(error, UserError):
            message = str(error)
        # Discord still lists commands from an unloaded cog until the tree is re-synced.
        elif isinstance(error, app_commands.CommandNotFound):
            full_name = " ".join([*error.parents, error.name])
            logger.warning(f"/{full_name} invoked but not in the tree (cog unloaded?)")
            message = f"`/{full_name}` is currently unavailable. Please try again later."
        # Handle Transformer Errors (Validation failures like invalid Hex codes)
        elif isinstance(error, app_commands.TransformerError):
            # The original ValueError is stored in error.__cause__
            message = f"{error.__cause__}" if error.__cause__ else "Invalid input provided."
        elif isinstance(error, discord.Forbidden):
            message = "I do not have permission to perform this action."
        elif isinstance(error, discord.NotFound):
            message = "The target resource was not found."
        elif isinstance(error, asyncio.TimeoutError):
            message = "Operation timed out."
        elif isinstance(error, aiohttp.ClientResponseError):
            message = f"API request failed with status code {error.status}."
        elif isinstance(error, aiohttp.ClientError):
            message = f"An error occurred while contacting the API: {error}"
        elif isinstance(error, discord.HTTPException):
            if error.status == 429:
                message = "Rate limited. Please wait a moment and try again."
                retry_after = error.response.headers.get("Retry-After") if error.response else None
                if retry_after:
                    try:
                        message = f"Rate limited. Please try again in ~{float(retry_after):.1f}s."
                    except ValueError:
                        pass
            else:
                message = f"HTTP Error: {error.status}"
        else:
            # Log unexpected errors to console so you can debug them
            logger.error(f"Ignoring exception in command {interaction.command}:", exc_info=error)
            message = f"An unexpected error occurred: {error}"

        await send_error(interaction, message)

async def setup(bot: commands.Bot):
    await bot.add_cog(ErrorHandler(bot))