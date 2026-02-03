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
    VOICE_NAME_MAX_LENGTH,
)

class Lobby(commands.GroupCog, group_name="lobby"):
    def __init__(self, bot: commands.Bot):
        super().__init__()
        self.bot = bot
        self.cleanup_lobbies.start()

    @staticmethod
    def _max_bitrate(guild: discord.Guild) -> int:
        # discord.py exposes the bitrate limit directly
        return guild.bitrate_limit

    async def _handle_http_exception(self, interaction: discord.Interaction, e: discord.HTTPException, action: str, forbidden_msg: Optional[str] = None):
        if e.status == 429:
            retry_after = None
            try:
                retry_after = float(e.response.headers.get("Retry-After"))
            except (ValueError, TypeError, AttributeError):
                pass

            if retry_after:
                await interaction.followup.send(f"Rate limited. Please try again in ~{retry_after:.1f}s.", ephemeral=True)
            else:
                await interaction.followup.send("Rate limited. Please wait a moment and try again.", ephemeral=True)
            return

        if isinstance(e, discord.Forbidden):
            msg = forbidden_msg or f"I don’t have permission to {action}."
            await interaction.followup.send(msg, ephemeral=True)
            return

        await interaction.followup.send(f"Failed to {action}: {e}", ephemeral=True)

    def cog_unload(self):
        self.cleanup_lobbies.cancel()

    @app_commands.command(name="setup", description="Setup temporary voice-chat system with user-created lobbies.")
    @app_commands.describe(category="The category where lobby channels will be created.")
    async def setup(self, interaction: discord.Interaction, category: discord.CategoryChannel):
        if not interaction.user.guild_permissions.manage_channels:
            await interaction.response.send_message("You need **Manage Channels** permission to run this command.", ephemeral=True)
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

        except discord.HTTPException as e:
            await self._handle_http_exception(interaction, e, "setup lobby voice-chat system", "I’m missing **Manage Channels** permission in that category.")

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

        try:
            await ch.edit(user_limit=max_users)
            label = "unlimited" if max_users == 0 else str(max_users)
            await interaction.followup.send(f"Lobby resized to **{label}** maximum users.", ephemeral=True)
        except discord.HTTPException as e:
            await self._handle_http_exception(interaction, e, "resize lobby")

    @app_commands.command(name="rename", description="Rename your current lobby voice-channel.")
    @app_commands.describe(new_name="New name for the lobby.")
    async def rename(self, interaction: discord.Interaction, new_name: str):
        
        await interaction.response.defer(ephemeral=True)

        if not interaction.user.voice or not interaction.user.voice.channel:
            await interaction.followup.send("You must be connected to a lobby voice-channel.", ephemeral=True)
            return

        ch: discord.VoiceChannel = interaction.user.voice.channel
        if not await lobby_is_tracked(ch.id):
            await interaction.followup.send("This channel isn’t a lobby voice-channel.", ephemeral=True)
            return

        name = new_name.strip()
        final = f"{LOBBY_EMOJI} {name}"

        if len(final) > VOICE_NAME_MAX_LENGTH:
            await interaction.followup.send(
                f"Name too long ({len(final)}/{VOICE_NAME_MAX_LENGTH}).", ephemeral=True
            )
            return
        
        try:
            await ch.edit(name=final, reason=f"Lobby rename by {interaction.user}")
            await interaction.followup.send(f"Lobby renamed to **{name}**.", ephemeral=True)

        except discord.HTTPException as e:
            await self._handle_http_exception(interaction, e, "rename lobby")

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
    await bot.add_cog(Lobby(bot))
