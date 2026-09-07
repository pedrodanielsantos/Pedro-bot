import discord
from discord import app_commands
from discord.ext import commands

from config.constants import NEW_LOBBY_TRIGGER, VOICE_VQM
from utils.embeds import success_embed
from utils.permissions import require_permission, visibility_gate
from utils.regions import guild_region

@visibility_gate("manage_channels")
class Setup(commands.GroupCog, group_name="setup"):
    def __init__(self, bot: commands.Bot):
        super().__init__()
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

async def setup(bot: commands.Bot):
    await bot.add_cog(Setup(bot))
