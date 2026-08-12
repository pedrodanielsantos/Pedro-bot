import aiohttp
import discord

from db.database import lobby_is_tracked
from utils.errors import UserError


class SessionMixin:
    async def cog_load(self):
        self.session = aiohttp.ClientSession()

    async def cog_unload(self):
        if self.session and not self.session.closed:
            await self.session.close()


class LobbyMixin:
    async def _get_lobby_channel(self, interaction: discord.Interaction) -> discord.VoiceChannel:
        if not interaction.user.voice or not interaction.user.voice.channel:
            raise UserError("You must be connected to a lobby voice-channel.")

        ch = interaction.user.voice.channel
        if not await lobby_is_tracked(ch.id):
            raise UserError("This channel isn’t a lobby voice-channel.")

        return ch
