import discord
from discord import app_commands
from discord.ext import commands

from config.constants import VOICE_REGION_AUTOMATIC
from db.database import set_user_lobby_region
from utils.mixins import LobbyMixin
from utils.embeds import success_embed
from utils.errors import UserError
from utils.regions import voice_regions

AUTOCOMPLETE_LIMIT = 25

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

        # Autocomplete is a suggestion, not a constraint: anything can be typed in.
        regions = await voice_regions(self.bot)
        if not regions:
            raise UserError("Couldn't reach Discord for the region list. Please try again in a moment.")
        if region not in regions:
            typed = discord.utils.escape_markdown(region[:50])
            raise UserError(f"**{typed}** isn't a voice region. Pick one from the list.")

        rtc_region = None if region == VOICE_REGION_AUTOMATIC else region
        await channel.edit(rtc_region=rtc_region, reason=f"Lobby region change by {interaction.user}")

        message = f"Lobby region set to **{regions[region]}**."
        if save_default:
            await set_user_lobby_region(interaction.user.id, region)
            message += "\nSaved as your default for new lobbies."

        await interaction.followup.send(embed=success_embed(message), ephemeral=True)

    @region.autocomplete("region")
    async def region_autocomplete(self, interaction: discord.Interaction, current: str):
        regions = await voice_regions(self.bot)
        query = current.lower()
        return [
            app_commands.Choice(name=label, value=region_id)
            for region_id, label in regions.items()
            if query in label.lower() or query in region_id
        ][:AUTOCOMPLETE_LIMIT]

async def setup(bot: commands.Bot):
    await bot.add_cog(Region(bot))
