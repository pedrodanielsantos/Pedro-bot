from typing import Optional

import aiohttp
import discord

from db.database import lobby_is_tracked
from config.constants import ERROR_COLOR


class SessionMixin:
    async def cog_load(self):
        self.session = aiohttp.ClientSession()

    async def cog_unload(self):
        if self.session and not self.session.closed:
            await self.session.close()


class LobbyMixin:
    async def _send_error(self, interaction: discord.Interaction, message: str):
        embed = discord.Embed(description=message, color=ERROR_COLOR)
        await interaction.followup.send(embed=embed, ephemeral=True)

    async def _get_lobby_channel(self, interaction: discord.Interaction) -> Optional[discord.VoiceChannel]:
        if not interaction.user.voice or not interaction.user.voice.channel:
            await self._send_error(interaction, "You must be connected to a lobby voice-channel.")
            return None

        ch = interaction.user.voice.channel
        if not await lobby_is_tracked(ch.id):
            await self._send_error(interaction, "This channel isn’t a lobby voice-channel.")
            return None

        return ch
