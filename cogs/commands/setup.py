import io
import discord
from discord import app_commands
from discord.ext import commands, tasks
from typing import Optional

from db.database import (
    lobby_add, lobby_delete, lobbies_all, lobby_is_tracked,
    set_welcome_channel, get_welcome_channel, get_guild_embed_color,
    set_log_channel
)
from config.constants import (
    NEW_LOBBY_TRIGGER,
    LOBBY_NAME,
    LOBBY_EMOJI,
    VOICE_VQM,
    VOICE_REGION,
    SUCCESS_COLOR,
    ERROR_COLOR,
)

class Setup(commands.GroupCog, group_name="setup"):
    def __init__(self, bot: commands.Bot):
        super().__init__()
        self.bot = bot

    def cog_unload(self):
        self.cleanup_lobbies.cancel()

    @staticmethod
    def _max_bitrate(guild: discord.Guild) -> int:
        return guild.bitrate_limit

    @app_commands.command(name="lobbies", description="Setup temporary voice-chat system with user-created lobbies")
    @app_commands.describe(category="The category where lobby channels will be created")
    async def lobbies(self, interaction: discord.Interaction, category: discord.CategoryChannel):
        if not interaction.user.guild_permissions.manage_channels:
            embed = discord.Embed(description="You need **Manage Channels** permission to use this command.", color=ERROR_COLOR)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        trigger = discord.utils.get(category.voice_channels, name=NEW_LOBBY_TRIGGER)
        if trigger is None:
            trigger = await category.create_voice_channel(
                NEW_LOBBY_TRIGGER,
                position=0,
                bitrate=self._max_bitrate(category.guild),
                video_quality_mode=discord.VideoQualityMode(VOICE_VQM),
                rtc_region=VOICE_REGION,
            )

        embed = discord.Embed(
            description=f"Lobby system set in **{category.name}**:\n- {trigger.mention}",
            color=SUCCESS_COLOR
        )
        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="welcome", description="Setup or disable the welcome message channel")
    @app_commands.describe(channel="The channel to send welcome messages in (leave empty to disable)")
    async def welcome(self, interaction: discord.Interaction, channel: Optional[discord.TextChannel] = None):
        if not interaction.user.guild_permissions.administrator:
            embed = discord.Embed(description="You need **Administrator** permission to use this command.", color=ERROR_COLOR)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        if channel is None:
            await set_welcome_channel(interaction.guild_id, None)
            embed = discord.Embed(description="Welcome messages have been disabled.", color=SUCCESS_COLOR)
            await interaction.response.send_message(embed=embed, ephemeral=True)
        else:
            await set_welcome_channel(interaction.guild_id, channel.id)
            embed = discord.Embed(description=f"Welcome messages will now be sent in {channel.mention}.", color=SUCCESS_COLOR)
            await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="logs", description="Setup or disable the command log channel")
    @app_commands.describe(channel="The channel to send command logs in (leave empty to disable)")
    async def logs(self, interaction: discord.Interaction, channel: Optional[discord.TextChannel] = None):
        if not interaction.user.guild_permissions.administrator:
            embed = discord.Embed(description="You need **Administrator** permission to use this command.", color=ERROR_COLOR)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        if channel is None:
            await set_log_channel(interaction.guild_id, None)
            embed = discord.Embed(description="Command logging has been disabled.", color=SUCCESS_COLOR)
            await interaction.response.send_message(embed=embed, ephemeral=True)
        else:
            await set_log_channel(interaction.guild_id, channel.id)
            embed = discord.Embed(description=f"Commands will now be logged in {channel.mention}.", color=SUCCESS_COLOR)
            await interaction.response.send_message(embed=embed, ephemeral=True)

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        channel_id = await get_welcome_channel(member.guild.id)
        if not channel_id:
            return

        channel = member.guild.get_channel(channel_id)
        if not channel:
            return

        color = await get_guild_embed_color(member.guild.id)

        description = (
            f"Welcome to {member.guild.name} {member.mention}!\n\n"
            "Check out https://discord.com/channels/1240063556217733141/1240063556289040449 and <id:customize>."
        )

        ext = "gif" if member.display_avatar.is_animated() else "png"
        author_icon_name = f"author_icon.{ext}"
        thumbnail_name = f"thumbnail.{ext}"

        embed = discord.Embed(description=description, color=color)
        embed.set_author(name=member.display_name, icon_url=f"attachment://{author_icon_name}")
        embed.set_thumbnail(url=f"attachment://{thumbnail_name}")

        try:
            author_icon_bytes = await member.display_avatar.with_size(128).read()
            thumbnail_bytes = await member.display_avatar.with_size(1024).read()
        except discord.HTTPException:
            return

        files = [
            discord.File(io.BytesIO(author_icon_bytes), filename=author_icon_name),
            discord.File(io.BytesIO(thumbnail_bytes), filename=thumbnail_name),
        ]

        try:
            await channel.send(embed=embed, files=files)
        except (discord.Forbidden, discord.HTTPException):
            pass

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
                    pass
                except discord.HTTPException:
                    pass

    @tasks.loop(seconds=60)
    async def cleanup_lobbies(self):
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

    @commands.Cog.listener()
    async def on_ready(self):
        if not self.cleanup_lobbies.is_running():
            self.cleanup_lobbies.start()

async def setup(bot: commands.Bot):
    await bot.add_cog(Setup(bot))
