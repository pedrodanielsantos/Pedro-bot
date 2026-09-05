import discord
from discord import app_commands
from discord.ext import commands

from db.database import get_autoroles, get_guild_embed_color, get_guild_settings
from config.constants import EMBED_COLOR
from utils.permissions import require_permission, visibility_gate
from utils.regions import AUTOMATIC_LABEL, region_label
from utils.settings import format_channel, format_roles

class ServerConfig(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # Gated on the command, not the class: a class-level gate only takes effect
    # on a GroupCog, so on a plain Cog it would silently do nothing.
    @app_commands.command(name="serverconfig", description="View the server's current bot settings")
    @visibility_gate("administrator")
    async def serverconfig(self, interaction: discord.Interaction):
        await require_permission(interaction, "administrator")
        await interaction.response.defer(ephemeral=True)

        settings = await get_guild_settings(interaction.guild_id)
        autoroles = await get_autoroles(interaction.guild_id)
        lobby_label = await region_label(self.bot, settings["lobby_region"])
        embed_color = settings["embed_color"]
        guild = interaction.guild

        # Unset values name the effective default rather than reading as missing,
        # since both fall back to something rather than being disabled.
        lines = [
            f"**Embed color:** `#{embed_color}`" if embed_color else f"**Embed color:** `#{EMBED_COLOR:06X}` (default)",
            f"**Lobby region:** {lobby_label or f'{AUTOMATIC_LABEL} (default)'}",
            f"**Welcome channel:** {format_channel(guild, settings['welcome_channel_id'])}",
            f"**Commands log:** {format_channel(guild, settings['commands_log_channel_id'])}",
            f"**Moderation log:** {format_channel(guild, settings['moderation_log_channel_id'])}",
            f"**Autoroles:** {format_roles(guild, autoroles)}",
        ]

        color = await get_guild_embed_color(interaction.guild_id)
        embed = discord.Embed(title="Server Config", description="\n".join(lines), color=color)
        embed.set_footer(text="Change these with /set, /log, /setup and /autorole.")
        await interaction.followup.send(embed=embed, ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(ServerConfig(bot))
