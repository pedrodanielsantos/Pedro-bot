import discord
from discord import app_commands
from discord.ext import commands
import asyncio
from typing import Optional

from config.constants import LOBBY_EMOJI, VOICE_NAME_MAX_LENGTH
from utils.mixins import LobbyMixin
from utils.embeds import success_embed
from utils.errors import UserError

class Rename(LobbyMixin, commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="rename", description="Rename your current lobby voice-channel")
    @app_commands.describe(new_name="New name for the lobby")
    async def rename(self, interaction: discord.Interaction, new_name: str):
        await interaction.response.defer(ephemeral=True)

        channel = await self._get_lobby_channel(interaction)

        name = new_name.strip()
        final = f"{LOBBY_EMOJI} {name}"

        if len(final) > VOICE_NAME_MAX_LENGTH:
            raise UserError(f"Name too long ({len(final)}/{VOICE_NAME_MAX_LENGTH}).")

        try:
            await asyncio.wait_for(channel.edit(name=final, reason=f"Lobby rename by {interaction.user}"), timeout=5.0)
            embed = success_embed(f"Lobby renamed to **{name}**.")
            await interaction.followup.send(embed=embed, ephemeral=True)
        except asyncio.TimeoutError:
            raise UserError("Rate limited. Discord limits channel renames to **2 per 10 minutes**, try again later.")

async def setup(bot: commands.Bot):
    await bot.add_cog(Rename(bot))