import discord
from discord import app_commands
from discord.ext import commands
from typing import Optional

from db.database import set_commands_log_channel, set_moderation_log_channel
from config.constants import SUCCESS_COLOR, ERROR_COLOR

@app_commands.default_permissions(administrator=True)
class Log(commands.GroupCog, group_name="log"):
    def __init__(self, bot: commands.Bot):
        super().__init__()
        self.bot = bot

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Gate all /log subcommands to admins only."""
        if interaction.user.guild_permissions.administrator:
            return True
        embed = discord.Embed(
            description="You must be an **administrator** to use `/log` commands.",
            color=ERROR_COLOR
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return False

    @app_commands.command(name="commands", description="Setup or disable the log channel for every command used")
    @app_commands.describe(channel="The channel to send command logs in (leave empty to disable)")
    async def commands_log(self, interaction: discord.Interaction, channel: Optional[discord.TextChannel] = None):
        if channel is None:
            await set_commands_log_channel(interaction.guild_id, None)
            embed = discord.Embed(description="Command logging has been disabled.", color=SUCCESS_COLOR)
        else:
            await set_commands_log_channel(interaction.guild_id, channel.id)
            embed = discord.Embed(description=f"Commands will now be logged in {channel.mention}.", color=SUCCESS_COLOR)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="moderation", description="Setup or disable the moderation log channel")
    @app_commands.describe(channel="The channel to send moderation logs in (leave empty to disable)")
    async def moderation(self, interaction: discord.Interaction, channel: Optional[discord.TextChannel] = None):
        if channel is None:
            await set_moderation_log_channel(interaction.guild_id, None)
            embed = discord.Embed(description="Moderation logging has been disabled.", color=SUCCESS_COLOR)
        else:
            await set_moderation_log_channel(interaction.guild_id, channel.id)
            embed = discord.Embed(description=f"Moderation actions will now be logged in {channel.mention}.", color=SUCCESS_COLOR)
        await interaction.response.send_message(embed=embed, ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(Log(bot))
