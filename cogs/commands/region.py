import discord
from discord import app_commands
from discord.ext import commands

from db.database import set_user_lobby_region
from utils.mixins import LobbyMixin
from utils.embeds import success_embed
from utils.regions import region_choices, require_region, resolve_region

class Region(LobbyMixin, commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="region", description="Change your current lobby's voice region")
    @app_commands.describe(
        region="Voice region to route the lobby through",
        save_default="Also use this region for every lobby you create from now on",
    )
    async def region(self, interaction: discord.Interaction, region: str, save_default: bool = False):
        await interaction.response.defer(ephemeral=True)

        channel = await self._get_lobby_channel(interaction)

        label = await require_region(self.bot, region)

        # Validated above, so this only translates the automatic sentinel.
        rtc_region = await resolve_region(self.bot, region)
        await channel.edit(rtc_region=rtc_region, reason=f"Lobby region change by {interaction.user}")

        message = f"Lobby region set to **{label}**."
        if save_default:
            await set_user_lobby_region(interaction.user.id, region)
            message += "\nSaved as your default for new lobbies."

        await interaction.followup.send(embed=success_embed(message), ephemeral=True)

    @region.autocomplete("region")
    async def region_autocomplete(self, interaction: discord.Interaction, current: str):
        return await region_choices(self.bot, current)

async def setup(bot: commands.Bot):
    await bot.add_cog(Region(bot))
