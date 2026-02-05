import discord
from discord import app_commands
from discord.ext import commands
from typing import Optional

from db.database import set_embed_color
from config.constants import EMBED_COLOR

def validate_hex_code(hex_code: str) -> discord.Color:
    """Validate and convert a HEX code into a discord.Color object."""
    if not hex_code.startswith("#"):
        hex_code = f"#{hex_code}"
    if len(hex_code) != 7 or not all(c in "0123456789ABCDEFabcdef#" for c in hex_code):
        raise ValueError("Invalid HEX color code! Use a format like `#FF5733` or `FF5733`.")
    return discord.Color(int(hex_code[1:], 16))

@app_commands.default_permissions(administrator=True)
class Set(commands.GroupCog, group_name="set"):
    def __init__(self, bot: commands.Bot):
        super().__init__()
        self.bot = bot

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Gate all /set subcommands to admins only."""
        if interaction.user.guild_permissions.administrator:
            return True
        # must respond to the interaction or it errors
        await interaction.response.send_message(
            "You must be an **administrator** to use `/set` commands.",
            ephemeral=True
        )
        return False

    @app_commands.command(name="embedcolor", description="Set or reset the server's embed color.")
    @app_commands.describe(hex_code="The hex color code (e.g. #FF0000). Input the command without argument to reset.")
    async def embed_color(self, interaction: discord.Interaction, hex_code: Optional[str] = None):
        if not hex_code:
            await set_embed_color(interaction.guild_id, None, interaction.user.id)
            embed = discord.Embed(description="✅ Embed color has been reset to default.", color=discord.Color(EMBED_COLOR))
            await interaction.response.send_message(embed=embed)
            return

        try:
            color = validate_hex_code(hex_code)
        except ValueError as e:
            await interaction.response.send_message(f"❌ {e}", ephemeral=True)
            return

        # Save to Database without the #
        clean_hex = hex_code.lstrip("#")
        await set_embed_color(interaction.guild_id, clean_hex, interaction.user.id)

        embed = discord.Embed(description=f"✅ Embed color has been updated to `#{clean_hex}`.", color=color)
        await interaction.response.send_message(embed=embed)

async def setup(bot: commands.Bot):
    await bot.add_cog(Set(bot))