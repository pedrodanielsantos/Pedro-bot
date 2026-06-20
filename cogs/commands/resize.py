import discord
from discord import app_commands
from discord.ext import commands
from typing import Optional

from db.database import lobby_is_tracked
from config.constants import SUCCESS_COLOR, ERROR_COLOR

class Resize(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="resize", description="Resize your current lobby")
    @app_commands.describe(max_users="Must be between 0 (unlimited) and 99")
    async def resize(self, interaction: discord.Interaction, max_users: int):
        await interaction.response.defer(ephemeral=True)

        if max_users < 0 or max_users > 99:
            embed = discord.Embed(description="Maximum users must be between **0** (unlimited) and **99**.", color=ERROR_COLOR)
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        if not interaction.user.voice or not interaction.user.voice.channel:
            embed = discord.Embed(description="You must be connected to a lobby voice-channel.", color=ERROR_COLOR)
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        ch: discord.VoiceChannel = interaction.user.voice.channel
        if not await lobby_is_tracked(ch.id):
            embed = discord.Embed(description="This channel isn’t a lobby voice-channel.", color=ERROR_COLOR)
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        await ch.edit(user_limit=max_users)
        label = "unlimited" if max_users == 0 else str(max_users)
        embed = discord.Embed(description=f"Lobby resized to **{label}** maximum users.", color=SUCCESS_COLOR)
        await interaction.followup.send(embed=embed, ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(Resize(bot))