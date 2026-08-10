import discord
from discord import app_commands
from discord.ext import commands
from typing import Optional

from db.database import set_welcome_channel
from config.constants import NEW_LOBBY_TRIGGER, VOICE_VQM, VOICE_REGION, SUCCESS_COLOR, ERROR_COLOR

class Setup(commands.GroupCog, group_name="setup"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

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

async def setup(bot: commands.Bot):
    await bot.add_cog(Setup(bot))
