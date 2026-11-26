import discord
from discord.ext import commands, tasks
import logging

from db.database import lobby_add, lobby_delete, lobbies_all, lobby_is_tracked
from config.constants import NEW_LOBBY_TRIGGER, LOBBY_NAME, LOBBY_EMOJI, VOICE_VQM
from utils.regions import default_region_for

logger = logging.getLogger("lobbies")

class LobbyManager(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Members with a lobby being created, and lobbies whose owner isn't moved in yet.
        self._creating: set[int] = set()
        self._pending: set[int] = set()

    async def cog_load(self):
        if not self.cleanup_lobbies.is_running():
            self.cleanup_lobbies.start()

    def cog_unload(self):
        self.cleanup_lobbies.cancel()

    @staticmethod
    def _max_bitrate(guild: discord.Guild) -> int:
        return guild.bitrate_limit

    @staticmethod
    def _is_empty(channel: discord.VoiceChannel) -> bool:
        """Whether a lobby has no human left in it.

        Bots are excluded deliberately: the music player sits in the channel it
        is streaming to, and counting it would keep every lobby it ever joined
        alive forever. _delete_lobby has it leave first.
        """
        return not any(not member.bot for member in channel.members)

    async def _delete_lobby(self, channel: discord.VoiceChannel, reason: str):
        """Deletes a lobby and its row, letting a player in it announce and leave
        first. The row is kept if Discord refuses, so periodic cleanup retries."""
        music = self.bot.get_cog("MusicManager")
        if music is not None:
            try:
                await music.leave_empty(channel)
            except Exception:
                # The lobby still goes, deleting it disconnects the player anyway.
                logger.exception(f"Music player failed to leave lobby {channel.id}")

        try:
            await channel.delete(reason=reason)
        except discord.NotFound:
            pass  # Already gone, e.g. deleted by the other cleanup path.
        except discord.HTTPException as e:
            logger.warning(f"Failed to delete lobby {channel.id} in guild {channel.guild.id}: {e}")
            return
        await lobby_delete(channel.id)

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        # Check if a user left a voice channel
        if before.channel and (not after.channel or before.channel.id != after.channel.id):
            if self._is_empty(before.channel) and await lobby_is_tracked(before.channel.id):
                await self._delete_lobby(before.channel, "Empty user lobby")

        # Mute, deafen and camera changes keep the same channel, so only a move in counts.
        joined = after.channel
        if joined and before.channel and before.channel.id == joined.id:
            joined = None
        if isinstance(joined, discord.VoiceChannel) and joined.category and joined.name == NEW_LOBBY_TRIGGER:
            if member.id in self._creating:
                return
            self._creating.add(member.id)
            try:
                await self._create_lobby(member, joined)
            finally:
                self._creating.discard(member.id)

    async def _create_lobby(self, member: discord.Member, trigger: discord.VoiceChannel):
        cat = trigger.category
        try:
            new_ch = await cat.create_voice_channel(
                f"{LOBBY_EMOJI} {LOBBY_NAME}",
                # Below every voice channel in the category, so positions never collide.
                position=max((c.position for c in cat.voice_channels), default=-1) + 1,
                bitrate=self._max_bitrate(cat.guild),
                video_quality_mode=discord.VideoQualityMode(VOICE_VQM),
                rtc_region=await default_region_for(self.bot, member.guild.id, member.id),
            )
        except discord.HTTPException as e:
            # The user is left in the trigger channel with no feedback either way,
            # so log it; raising here would only surface as a listener traceback.
            logger.error(f"Failed to create a lobby in guild {member.guild.id}: {e}")
            return

        self._pending.add(new_ch.id)
        try:
            await lobby_add(member.guild.id, new_ch.id)

            # They may have left or switched channels while the lobby was being made.
            if member.voice and member.voice.channel and member.voice.channel.id == trigger.id:
                try:
                    await member.move_to(new_ch, reason="Auto-created user lobby")
                    return
                except discord.HTTPException:
                    pass  # Left voice between the check and the move.

            await self._delete_lobby(new_ch, "Lobby owner left before the move")
        finally:
            self._pending.discard(new_ch.id)

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

            # Created, but its owner isn't moved in yet.
            if ch.id in self._pending:
                continue

            if self._is_empty(ch):
                await self._delete_lobby(ch, "Empty user lobby (periodic cleanup)")

async def setup(bot: commands.Bot):
    await bot.add_cog(LobbyManager(bot))
