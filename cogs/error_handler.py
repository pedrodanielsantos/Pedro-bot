import discord
from discord import app_commands
from discord.ext import commands
import traceback
import asyncio

class ErrorHandler(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Register the global error handler for the application command tree
        self.bot.tree.on_error = self.on_app_command_error

    async def cog_unload(self):
        # Unregister the handler when the cog is unloaded
        self.bot.tree.on_error = None

    async def on_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        # Unwrap CommandInvokeError (errors that happen inside the command function)
        if isinstance(error, app_commands.CommandInvokeError):
            error = error.original

        # Handle Transformer Errors (Validation failures like invalid Hex codes)
        if isinstance(error, app_commands.TransformerError):
            # The original ValueError is stored in error.__cause__
            message = f"❌ {error.__cause__}" if error.__cause__ else "❌ Invalid input provided."
        elif isinstance(error, discord.Forbidden):
            message = "❌ I do not have permission to perform this action. Please check my roles and channel permissions."
        elif isinstance(error, discord.NotFound):
            message = "❌ The target resource was not found."
        elif isinstance(error, asyncio.TimeoutError):
            message = "❌ Operation timed out."
        elif isinstance(error, discord.HTTPException):
            if error.status == 429:
                retry_after = error.response.headers.get("Retry-After")
                if retry_after:
                    try:
                        retry_float = float(retry_after)
                        message = f"❌ Rate limited. Please try again in ~{retry_float:.1f}s."
                    except ValueError:
                        message = "❌ Rate limited. Please wait a moment and try again."
                else:
                    message = "❌ Rate limited. Please wait a moment and try again."
            else:
                message = f"❌ HTTP Error: {error.status}"
        else:
            # Log unexpected errors to console so you can debug them
            print(f"Ignoring exception in command {interaction.command}:")
            traceback.print_exception(type(error), error, error.__traceback__)
            message = f"❌ An unexpected error occurred: {error}"

        # Send the error message to the user
        if not interaction.response.is_done():
            await interaction.response.send_message(message, ephemeral=True)
        else:
            await interaction.followup.send(message, ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(ErrorHandler(bot))