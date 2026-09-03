import discord
from discord import app_commands
from discord.ext import commands
from typing import Optional

from db.database import set_embed_color, set_guild_lobby_region
from config.constants import EMBED_COLOR
from utils.color import parse_hex_color
from utils.embeds import success_embed
from utils.errors import UserError
from utils.permissions import require_permission
from utils.regions import region_choices, require_region

# Hides the whole group from non-admins in the command picker. Discord only supports
# this per top-level command, so it can't differ per subcommand. It's a default a
# server can override, so each command still checks the permission itself.
@app_commands.default_permissions(administrator=True)
class Set(commands.GroupCog, group_name="set"):
    def __init__(self, bot: commands.Bot):
        super().__init__()
        self.bot = bot

    @app_commands.command(name="embedcolor", description="Set or reset the server's embed color")
    @app_commands.describe(hex_code="The hex color code (leave empty to reset)")
    async def embed_color(self, interaction: discord.Interaction, hex_code: Optional[str] = None):
        await require_permission(interaction, "administrator")
        if not hex_code:
            await set_embed_color(interaction.guild_id, None, interaction.user.id)
            embed = discord.Embed(description="Embed color has been reset to default.", color=discord.Color(EMBED_COLOR))
            await interaction.response.send_message(embed=embed)
            return

        try:
            color = parse_hex_color(hex_code)
        except ValueError as e:
            raise UserError(str(e))

        # Save to Database without the #
        clean_hex = f"{color.value:06X}"
        await set_embed_color(interaction.guild_id, clean_hex, interaction.user.id)

        embed = discord.Embed(description=f"Embed color has been updated to `#{clean_hex}`.", color=color)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="lobbyregion", description="Set or reset the voice region new lobbies are created in")
    @app_commands.describe(region="The region to use (leave empty to let Discord choose)")
    async def lobby_region(self, interaction: discord.Interaction, region: Optional[str] = None):
        await require_permission(interaction, "administrator")
        await interaction.response.defer()

        if not region:
            await set_guild_lobby_region(interaction.guild_id, None)
            embed = success_embed("Lobby region has been reset, Discord will choose it automatically.")
            await interaction.followup.send(embed=embed)
            return

        label = await require_region(self.bot, region)

        await set_guild_lobby_region(interaction.guild_id, region)
        embed = success_embed(f"New lobbies will now be created in **{label}**.")
        await interaction.followup.send(embed=embed)

    @lobby_region.autocomplete("region")
    async def lobby_region_autocomplete(self, interaction: discord.Interaction, current: str):
        return await region_choices(self.bot, current)

async def setup(bot: commands.Bot):
    await bot.add_cog(Set(bot))