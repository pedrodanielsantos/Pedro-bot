import discord
from discord import app_commands
from discord.ext import commands
from typing import Optional

from db.database import lobby_is_tracked

class Resize(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

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

        await ch.edit(user_limit=max_users)
        label = "unlimited" if max_users == 0 else str(max_users)
        await interaction.followup.send(f"Lobby resized to **{label}** maximum users.", ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(Resize(bot))