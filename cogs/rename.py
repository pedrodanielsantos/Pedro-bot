import discord
from discord import app_commands
from discord.ext import commands
import asyncio
from typing import Optional

from db.database import lobby_is_tracked
from config.constants import LOBBY_EMOJI, VOICE_NAME_MAX_LENGTH

class Rename(commands.Cog):
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

    @app_commands.command(name="rename", description="Rename your current lobby voice-channel.")
    @app_commands.describe(new_name="New name for the lobby.")
    async def rename(self, interaction: discord.Interaction, new_name: str):
        await interaction.response.defer(ephemeral=True)

        if not interaction.user.voice or not interaction.user.voice.channel:
            await interaction.followup.send("You must be connected to a lobby voice-channel.", ephemeral=True)
            return

        ch: discord.VoiceChannel = interaction.user.voice.channel
        if not await lobby_is_tracked(ch.id):
            await interaction.followup.send("This channel isn’t a lobby voice-channel.", ephemeral=True)
            return

        name = new_name.strip()
        final = f"{LOBBY_EMOJI} {name}"

        if len(final) > VOICE_NAME_MAX_LENGTH:
            await interaction.followup.send(f"Name too long ({len(final)}/{VOICE_NAME_MAX_LENGTH}).", ephemeral=True)
            return
        
        try:
            await asyncio.wait_for(ch.edit(name=final, reason=f"Lobby rename by {interaction.user}"), timeout=5.0)
            await interaction.followup.send(f"Lobby renamed to **{name}**.", ephemeral=True)
        except asyncio.TimeoutError:
            await interaction.followup.send("Rate limited. Discord limits channel renames to **2 per 10 minutes**, try again later.", ephemeral=True)
        except discord.HTTPException as e:
            await self._handle_http_exception(interaction, e, "rename lobby")

async def setup(bot: commands.Bot):
    await bot.add_cog(Rename(bot))