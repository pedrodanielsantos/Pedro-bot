import discord
from discord import app_commands
from discord.ext import commands
from typing import Optional

from db.database import set_embed_color
from config.constants import EMBED_COLOR
from utils.transformers import HexColorTransformer
from utils.permissions import require_permission

class Set(commands.GroupCog, group_name="set"):
    def __init__(self, bot: commands.Bot):
        super().__init__()
        self.bot = bot

    @app_commands.command(name="embedcolor", description="Set or reset the server's embed color")
    @app_commands.describe(hex_code="The hex color code (leave empty to reset)")
    async def embed_color(self, interaction: discord.Interaction, hex_code: app_commands.Transform[discord.Color, HexColorTransformer] = None):
        await require_permission(interaction, "administrator")
        if not hex_code:
            await set_embed_color(interaction.guild_id, None, interaction.user.id)
            embed = discord.Embed(description="Embed color has been reset to default.", color=discord.Color(EMBED_COLOR))
            await interaction.response.send_message(embed=embed)
            return

        # Save to Database without the #
        color = hex_code
        clean_hex = f"{color.value:06X}"
        await set_embed_color(interaction.guild_id, clean_hex, interaction.user.id)

        embed = discord.Embed(description=f"Embed color has been updated to `#{clean_hex}`.", color=color)
        await interaction.response.send_message(embed=embed)

async def setup(bot: commands.Bot):
    await bot.add_cog(Set(bot))