import discord
from discord import app_commands
from discord.ext import commands
from typing import Optional

from db.database import set_welcome_channel
from config.constants import NEW_LOBBY_TRIGGER, VOICE_VQM
from utils.embeds import success_embed
from utils.permissions import require_permission, visibility_gate
from utils.regions import guild_region

@visibility_gate("manage_channels", "administrator")
class Setup(commands.GroupCog, group_name="setup"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @staticmethod
    def _max_bitrate(guild: discord.Guild) -> int:
        return guild.bitrate_limit

    @app_commands.command(name="lobbies", description="Setup temporary voice-chat system with user-created lobbies")
    @app_commands.describe(category="The category where lobby channels will be created")
    async def lobbies(self, interaction: discord.Interaction, category: discord.CategoryChannel):
        await require_permission(interaction, "manage_channels")

        await interaction.response.defer(ephemeral=True)

        trigger = discord.utils.get(category.voice_channels, name=NEW_LOBBY_TRIGGER)
        if trigger is None:
            trigger = await category.create_voice_channel(
                NEW_LOBBY_TRIGGER,
                position=0,
                bitrate=self._max_bitrate(category.guild),
                video_quality_mode=discord.VideoQualityMode(VOICE_VQM),
                rtc_region=await guild_region(self.bot, interaction.guild_id),
            )

        embed = success_embed(f"Lobby system set in **{category.name}**:\n- {trigger.mention}")
        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="welcome", description="Setup or disable the welcome message channel")
    @app_commands.describe(channel="The channel to send welcome messages in (leave empty to disable)")
    async def welcome(self, interaction: discord.Interaction, channel: Optional[discord.TextChannel] = None):
        await require_permission(interaction, "administrator")

        if channel is None:
            await set_welcome_channel(interaction.guild_id, None)
            embed = success_embed("Welcome messages have been disabled.")
            await interaction.response.send_message(embed=embed, ephemeral=True)
        else:
            await set_welcome_channel(interaction.guild_id, channel.id)
            embed = success_embed(f"Welcome messages will now be sent in {channel.mention}.")
            await interaction.response.send_message(embed=embed, ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(Setup(bot))
