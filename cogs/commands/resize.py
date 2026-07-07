import discord
from discord import app_commands
from discord.ext import commands
from typing import Optional

from config.constants import SUCCESS_COLOR
from cogs.core.mixins import LobbyMixin

class Resize(LobbyMixin, commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="resize", description="Resize your current lobby")
    @app_commands.describe(max_users="Must be between 0 (unlimited) and 99")
    async def resize(self, interaction: discord.Interaction, max_users: int):
        await interaction.response.defer(ephemeral=True)

        if max_users < 0 or max_users > 99:
            await self._send_error(interaction, "Maximum users must be between **0** (unlimited) and **99**.")
            return

        channel = await self._get_lobby_channel(interaction)
        if channel is None:
            return

        await channel.edit(user_limit=max_users)
        label = "unlimited" if max_users == 0 else str(max_users)
        embed = discord.Embed(description=f"Lobby resized to **{label}** maximum users.", color=SUCCESS_COLOR)
        await interaction.followup.send(embed=embed, ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(Resize(bot))