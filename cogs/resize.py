import discord
from discord import app_commands
from discord.ext import commands
from typing import Optional

from db.database import lobby_is_tracked

class Resize(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _handle_http_exception(self, interaction: discord.Interaction, e: discord.HTTPException, action: str, forbidden_msg: Optional[str] = None):
        if e.status == 429:
            retry_after = None
            try:
                retry_after = float(e.response.headers.get("Retry-After"))
            except (ValueError, TypeError, AttributeError):
                pass

            if retry_after:
                await interaction.followup.send(f"Rate limited. Please try again in ~{retry_after:.1f}s.", ephemeral=True)
            else:
                await interaction.followup.send("Rate limited. Please wait a moment and try again.", ephemeral=True)
            return

        if isinstance(e, discord.Forbidden):
            msg = forbidden_msg or f"I don’t have permission to {action}."
            await interaction.followup.send(msg, ephemeral=True)
            return

        await interaction.followup.send(f"Failed to {action}: {e}", ephemeral=True)

    @app_commands.command(name="resize", description="Resize your current lobby.")
    @app_commands.describe(max_users="Must be between 0 (unlimited) and 99.")
    async def resize(self, interaction: discord.Interaction, max_users: int):
        await interaction.response.defer(ephemeral=True)

        if max_users < 0 or max_users > 99:
            await interaction.followup.send("Maximum users must be between **0** (unlimited) and **99**.", ephemeral=True)
            return

        if not interaction.user.voice or not interaction.user.voice.channel:
            await interaction.followup.send("You must be connected to a lobby voice-channel.", ephemeral=True)
            return

        ch: discord.VoiceChannel = interaction.user.voice.channel
        if not await lobby_is_tracked(ch.id):
            await interaction.followup.send("This channel isn’t a lobby voice-channel.", ephemeral=True)
            return

        try:
            await ch.edit(user_limit=max_users)
            label = "unlimited" if max_users == 0 else str(max_users)
            await interaction.followup.send(f"Lobby resized to **{label}** maximum users.", ephemeral=True)
        except discord.HTTPException as e:
            await self._handle_http_exception(interaction, e, "resize lobby")

async def setup(bot: commands.Bot):
    await bot.add_cog(Resize(bot))