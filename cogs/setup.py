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
    VOICE_BITRATE,
    VOICE_VQM,
    VOICE_REGION,
)

@app_commands.default_permissions(administrator=True)
class Setup(commands.GroupCog, name="setup"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.cleanup_lobbies.start()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Gate all /setup subcommands to admins only."""
        if interaction.user.guild_permissions.administrator:
            return True
        # must respond to the interaction or it errors
        await interaction.response.send_message(
            "You must be an **administrator** to use `/setup` commands.",
            ephemeral=True
        )
        return False

    def cog_unload(self):
        self.cleanup_lobbies.cancel()

    @app_commands.command(name="lobbies", description="Setup user-creatable voice-chat lobbies.")
    @app_commands.describe(category_id="The category ID where lobby channels will be created.")
    async def lobbies(self, interaction: discord.Interaction, category_id: str):
        if not interaction.user.guild_permissions.manage_channels:
            await interaction.response.send_message("You need **Manage Channels** to run this.", ephemeral=True)
            return

        try:
            cat_id = int(category_id)
        except ValueError:
            await interaction.response.send_message("Category ID must be a number.", ephemeral=True)
            return

        category = interaction.guild.get_channel(cat_id)
        if not isinstance(category, discord.CategoryChannel):
            await interaction.response.send_message("That ID is not a category.", ephemeral=True)
            return

        # Create trigger channel
        trigger = discord.utils.get(category.voice_channels, name=NEW_LOBBY_TRIGGER)
        if trigger is None:
            trigger = await category.create_voice_channel(
            NEW_LOBBY_TRIGGER,
            position=0,
            bitrate=VOICE_BITRATE,
            video_quality_mode=discord.VideoQualityMode(VOICE_VQM),
            rtc_region=VOICE_REGION,
        )
        
        await interaction.response.send_message(
            f"Lobby system set in **{category.name}**:\n- {trigger.mention}",
            ephemeral=True
        )

    @commands.Cog.listener()
    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState
    ):
        # When a user joins the trigger channel, create a new lobby and move them.
        if after and after.channel and isinstance(after.channel, discord.VoiceChannel):
            ch = after.channel
            cat: Optional[discord.CategoryChannel] = ch.category
            if cat and ch.name == NEW_LOBBY_TRIGGER:
                # Create at bottom of category
                new_ch = await cat.create_voice_channel(
                    f"{LOBBY_EMOJI} {LOBBY_NAME}",
                    position=len(cat.channels),
                    bitrate=VOICE_BITRATE,
                    video_quality_mode=discord.VideoQualityMode(VOICE_VQM),
                    rtc_region=VOICE_REGION,
                )
                lobby_add(member.guild.id, new_ch.id)

                # Give the event loop a tick; then try to move the member.
                # (Helps with timing right after creation on some guilds.)
                await asyncio.sleep(0.1)
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
        for guild_id, channel_id in list(lobbies_all()):
            guild = self.bot.get_guild(guild_id)
            if not guild:
                lobby_delete(channel_id)
                continue

            ch = guild.get_channel(channel_id)
            if not isinstance(ch, discord.VoiceChannel):
                lobby_delete(channel_id)
                continue

            if len(ch.members) == 0:
                try:
                    await ch.delete(reason="Empty user lobby (periodic cleanup)")
                finally:
                    lobby_delete(channel_id)

    @cleanup_lobbies.before_loop
    async def before_cleanup(self):
        await self.bot.wait_until_ready()

async def setup(bot: commands.Bot):
    await bot.add_cog(Setup(bot))
