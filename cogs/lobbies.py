import asyncio
import discord
from discord import app_commands
from discord.ext import commands, tasks
from typing import Optional

from db.database import lobby_add, lobby_delete, lobbies_all, lobby_is_tracked

from config.constants import (
    NEW_LOBBY_TRIGGER,
    LOBBY_NAME,
    LOBBY_EMOJI,
    VOICE_VQM,
    VOICE_REGION,
)

@app_commands.default_permissions(administrator=True)
class Lobbies(commands.GroupCog, group_name="lobbies"):
    def __init__(self, bot: commands.Bot):
        super().__init__()
        self.bot = bot
        self.cleanup_lobbies.start()

    @staticmethod
    def _max_bitrate(guild: discord.Guild) -> int:
        # discord.py exposes the bitrate limit directly
        return guild.bitrate_limit

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Gate all /lobbies subcommands to admins only."""
        if interaction.user.guild_permissions.administrator:
            return True
        # must respond to the interaction or it errors
        await interaction.response.send_message(
            "You must be an **administrator** to use `/lobbies` commands.",
            ephemeral=True
        )
        return False

    def cog_unload(self):
        self.cleanup_lobbies.cancel()

    @app_commands.command(name="setup", description="Setup temporary lobby voice-chat system.")
    @app_commands.describe(category="The category where lobby channels will be created.")
    async def setup(self, interaction: discord.Interaction, category: discord.CategoryChannel):
        if not interaction.user.guild_permissions.manage_channels:
            await interaction.response.send_message("You need **Manage Channels** to run this.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        try:
            trigger = discord.utils.get(category.voice_channels, name=NEW_LOBBY_TRIGGER)
            if trigger is None:
                trigger = await category.create_voice_channel(
                    NEW_LOBBY_TRIGGER,
                    position=0,
                    bitrate=self._max_bitrate(category.guild),
                    video_quality_mode=discord.VideoQualityMode(VOICE_VQM),
                    rtc_region=VOICE_REGION,
                )

            await interaction.followup.send(
                f"Lobby system set in **{category.name}**:\n- {trigger.mention}",
                ephemeral=True
            )

        except discord.Forbidden:
            await interaction.followup.send(
                "I’m missing **Manage Channels** in that category.", ephemeral=True
            )
        except discord.HTTPException as e:
            if getattr(e, "status", None) == 429:
                retry_after = None
                try:
                    retry_after_hdr = e.response.headers.get("Retry-After")
                    if retry_after_hdr:
                        retry_after = float(retry_after_hdr)
                except Exception:
                    pass
                if retry_after is not None:
                    await interaction.followup.send(
                        f"Rate limited. Try again in ~{retry_after:.1f}s.", ephemeral=True
                    )
                else:
                    await interaction.followup.send(
                        "Rate limited. Please wait a moment and try again.", ephemeral=True
                    )
            else:
                await interaction.followup.send(f"Failed to set up lobbies: {e}", ephemeral=True)

    @commands.Cog.listener()
    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState
    ):
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
                # Create at bottom of category
                new_ch = await cat.create_voice_channel(
                    f"{LOBBY_EMOJI} {LOBBY_NAME}",
                    position=len(cat.channels),
                    bitrate=self._max_bitrate(cat.guild),
                    video_quality_mode=discord.VideoQualityMode(VOICE_VQM),
                    rtc_region=VOICE_REGION,
                )
                await lobby_add(member.guild.id, new_ch.id)

                try:
                    await member.move_to(new_ch, reason="Auto-created user lobby")
                except discord.Forbidden:
                    # Bot lacks Move Members permission
                    pass
                except discord.HTTPException:
                    pass

    @tasks.loop(seconds=60)
    async def cleanup_lobbies(self):
        """Every minute: delete any tracked lobby that is empty.
           Also cleans up stale DB rows for missing channels/guilds."""
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

    @cleanup_lobbies.before_loop
    async def before_cleanup(self):
        await self.bot.wait_until_ready()

async def setup(bot: commands.Bot):
    # Load the Lobbies cog
    await bot.add_cog(Lobbies(bot))
