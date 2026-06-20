import discord
from discord import app_commands
from discord.ext import commands
import asyncio
from typing import Optional

from db.database import lobby_is_tracked
from config.constants import LOBBY_EMOJI, VOICE_NAME_MAX_LENGTH, SUCCESS_COLOR, ERROR_COLOR

class Rename(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="rename", description="Rename your current lobby voice-channel")
    @app_commands.describe(new_name="New name for the lobby")
    async def rename(self, interaction: discord.Interaction, new_name: str):
        await interaction.response.defer(ephemeral=True)

        if not interaction.user.voice or not interaction.user.voice.channel:
            embed = discord.Embed(description="You must be connected to a lobby voice-channel.", color=ERROR_COLOR)
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        ch: discord.VoiceChannel = interaction.user.voice.channel
        if not await lobby_is_tracked(ch.id):
            embed = discord.Embed(description="This channel isn’t a lobby voice-channel.", color=ERROR_COLOR)
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        name = new_name.strip()
        final = f"{LOBBY_EMOJI} {name}"

        if len(final) > VOICE_NAME_MAX_LENGTH:
            embed = discord.Embed(description=f"Name too long ({len(final)}/{VOICE_NAME_MAX_LENGTH}).", color=ERROR_COLOR)
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        try:
            await asyncio.wait_for(ch.edit(name=final, reason=f"Lobby rename by {interaction.user}"), timeout=5.0)
            embed = discord.Embed(description=f"Lobby renamed to **{name}**.", color=SUCCESS_COLOR)
            await interaction.followup.send(embed=embed, ephemeral=True)
        except asyncio.TimeoutError:
            embed = discord.Embed(description="Rate limited. Discord limits channel renames to **2 per 10 minutes**, try again later.", color=ERROR_COLOR)
            await interaction.followup.send(embed=embed, ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(Rename(bot))