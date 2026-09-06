import discord
from discord import app_commands
from discord.ext import commands
from typing import Optional

from db.database import set_embed_color, set_guild_lobby_region, set_music_dj_role, set_music_volume
from config.constants import EMBED_COLOR, MUSIC_DEFAULT_VOLUME, MUSIC_MAX_VOLUME
from utils.color import parse_hex_color
from utils.embeds import success_embed
from utils.errors import UserError
from utils.permissions import require_permission, visibility_gate
from utils.regions import region_choices, require_region

@visibility_gate("administrator")
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

    @app_commands.command(name="djrole", description="Set or reset the role required to control music playback")
    @app_commands.describe(role="The DJ role (leave empty to let everyone control playback)")
    async def dj_role(self, interaction: discord.Interaction, role: Optional[discord.Role] = None):
        await require_permission(interaction, "administrator")

        if not role:
            await set_music_dj_role(interaction.guild_id, None)
            embed = success_embed("DJ role has been reset, everyone can control playback.")
            await interaction.response.send_message(embed=embed)
            return

        await set_music_dj_role(interaction.guild_id, role.id)
        # The gate only applies while others are listening, so say so rather than
        # implying it locks the commands outright.
        embed = success_embed(
            f"{role.mention} is now the DJ role. Members without it can still control "
            "playback when nobody else is listening."
        )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="musicvolume", description="Set or reset the volume new players start at")
    @app_commands.describe(percent=f"1 to {MUSIC_MAX_VOLUME} (leave empty to reset to {MUSIC_DEFAULT_VOLUME})")
    async def music_volume(self, interaction: discord.Interaction, percent: Optional[int] = None):
        await require_permission(interaction, "administrator")

        if percent is None:
            await set_music_volume(interaction.guild_id, None)
            embed = success_embed(f"Starting volume has been reset to **{MUSIC_DEFAULT_VOLUME}%**.")
            await interaction.response.send_message(embed=embed)
            return

        if not 1 <= percent <= MUSIC_MAX_VOLUME:
            raise UserError(f"Volume must be between 1 and {MUSIC_MAX_VOLUME}.")

        await set_music_volume(interaction.guild_id, percent)
        embed = success_embed(f"New players will start at **{percent}%** volume.")
        await interaction.response.send_message(embed=embed)

async def setup(bot: commands.Bot):
    await bot.add_cog(Set(bot))