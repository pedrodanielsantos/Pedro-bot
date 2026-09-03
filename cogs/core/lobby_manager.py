import discord
from discord.ext import commands, tasks
import logging
from typing import Optional

from db.database import lobby_add, lobby_delete, lobbies_all, lobby_is_tracked
from config.constants import NEW_LOBBY_TRIGGER, LOBBY_NAME, LOBBY_EMOJI, VOICE_VQM
from utils.regions import default_region_for

logger = logging.getLogger("lobbies")

class LobbyManager(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_load(self):
        if not self.cleanup_lobbies.is_running():
            self.cleanup_lobbies.start()

    def cog_unload(self):
        self.cleanup_lobbies.cancel()

    @staticmethod
    def _max_bitrate(guild: discord.Guild) -> int:
        return guild.bitrate_limit

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        # Check if a user left a voice channel
        if before.channel and (not after.channel or before.channel.id != after.channel.id):
            if len(before.channel.members) == 0:
                if await lobby_is_tracked(before.channel.id):
                    try:
                        await before.channel.delete(reason="Empty user lobby")
                    except (discord.NotFound, discord.HTTPException):
                        pass
                    finally:
                        await lobby_delete(before.channel.id)

        # When a user joins the trigger channel, create a new lobby and move them.
        if after and after.channel and isinstance(after.channel, discord.VoiceChannel):
            ch = after.channel
            cat: Optional[discord.CategoryChannel] = ch.category
            if cat and ch.name == NEW_LOBBY_TRIGGER:
                try:
                    new_ch = await cat.create_voice_channel(
                        f"{LOBBY_EMOJI} {LOBBY_NAME}",
                        position=len(cat.channels),
                        bitrate=self._max_bitrate(cat.guild),
                        video_quality_mode=discord.VideoQualityMode(VOICE_VQM),
                        rtc_region=await default_region_for(self.bot, member.guild.id, member.id),
                    )
                except discord.HTTPException as e:
                    # The user is left in the trigger channel with no feedback either way,
                    # so log it; raising here would only surface as a listener traceback.
                    logger.error(f"Failed to create a lobby in guild {member.guild.id}: {e}")
                    return

                await lobby_add(member.guild.id, new_ch.id)

                try:
                    await member.move_to(new_ch, reason="Auto-created user lobby")
                except discord.Forbidden:
                    pass
                except discord.HTTPException:
                    pass

    @tasks.loop(seconds=60)
    async def cleanup_lobbies(self):
        # Guards against ticking before the guild cache is populated: is_ready()
        # is a plain attribute check, safe even before login (unlike
        # wait_until_ready(), which would raise if called this early during
        # the very first cog_load, since bot.start() hasn't run yet at that point).
        if not self.bot.is_ready():
            return

        for guild_id, channel_id in await lobbies_all():
            guild = self.bot.get_guild(guild_id)
            if not guild:
                await lobby_delete(channel_id)
                continue

            ch = guild.get_channel(channel_id)
            if not isinstance(ch, discord.VoiceChannel):
                await lobby_delete(channel_id)
                continue

            if len(ch.members) == 0:
                try:
                    await ch.delete(reason="Empty user lobby (periodic cleanup)")
                finally:
                    await lobby_delete(channel_id)

async def setup(bot: commands.Bot):
    await bot.add_cog(LobbyManager(bot))
