import discord
from discord import app_commands
from discord.ext import commands

from db.database import get_guild_embed_color, get_guild_lobby_region, get_user_lobby_region
from utils.regions import AUTOMATIC_LABEL, region_label
from utils.settings import NOT_SET

class Settings(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="settings", description="View your personal settings")
    async def settings(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        user_region = await region_label(self.bot, await get_user_lobby_region(interaction.user.id))
        if user_region:
            region_value = f"**{user_region}**"
        elif interaction.guild_id:
            # Without a personal default, lobbies fall back to the guild's.
            # See default_region_for() in utils/regions.py.
            guild_region = await region_label(self.bot, await get_guild_lobby_region(interaction.guild_id))
            region_value = f"{NOT_SET}, this server uses **{guild_region or AUTOMATIC_LABEL}**"
        else:
            region_value = NOT_SET

        lines = [f"**Default lobby region:** {region_value}"]

        color = await get_guild_embed_color(interaction.guild_id)
        embed = discord.Embed(title="Your Settings", description="\n".join(lines), color=color)
        embed.set_footer(text="These apply in every server. Change them with /region.")
        await interaction.followup.send(embed=embed, ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(Settings(bot))
