import discord
from discord import app_commands
from discord.ext import commands
from typing import Optional

from db.database import set_commands_log_channel, set_moderation_log_channel
from utils.embeds import success_embed
from utils.permissions import require_permission, visibility_gate

@visibility_gate("administrator")
class Log(commands.GroupCog, group_name="log"):
    def __init__(self, bot: commands.Bot):
        super().__init__()
        self.bot = bot

    @app_commands.command(name="commands", description="Setup or disable the log channel for every command used")
    @app_commands.describe(channel="The channel to send command logs in (leave empty to disable)")
    async def commands_log(self, interaction: discord.Interaction, channel: Optional[discord.TextChannel] = None):
        await require_permission(interaction, "administrator")
        if channel is None:
            await set_commands_log_channel(interaction.guild_id, None)
            embed = success_embed("Command logging has been disabled.")
        else:
            await set_commands_log_channel(interaction.guild_id, channel.id)
            embed = success_embed(f"Commands will now be logged in {channel.mention}.")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="moderation", description="Setup or disable the moderation log channel")
    @app_commands.describe(channel="The channel to send moderation logs in (leave empty to disable)")
    async def moderation(self, interaction: discord.Interaction, channel: Optional[discord.TextChannel] = None):
        await require_permission(interaction, "administrator")
        if channel is None:
            await set_moderation_log_channel(interaction.guild_id, None)
            embed = success_embed("Moderation logging has been disabled.")
        else:
            await set_moderation_log_channel(interaction.guild_id, channel.id)
            embed = success_embed(f"Moderation actions will now be logged in {channel.mention}.")
        await interaction.response.send_message(embed=embed, ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(Log(bot))
