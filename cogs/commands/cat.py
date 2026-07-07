import os
import discord
from discord.ext import commands
from discord import app_commands
from dotenv import load_dotenv
from config.constants import ERROR_COLOR
from cogs.core.mixins import SessionMixin

load_dotenv()
CAT_API_KEY = os.getenv("CAT_API_KEY")


class Cat(SessionMixin, commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="cat", description="Fetch a random cat image")
    async def fetch_cat(self, interaction: discord.Interaction):
        api_url = "https://api.thecatapi.com/v1/images/search"
        headers = {"x-api-key": CAT_API_KEY}

        await interaction.response.defer(thinking=True)
        async with self.session.get(api_url, headers=headers) as response:
            response.raise_for_status()

            data = await response.json()
            if data:
                image_url = data[0]["url"]
                await interaction.followup.send(image_url)
            else:
                embed = discord.Embed(description="No image found.", color=ERROR_COLOR)
                await interaction.followup.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(Cat(bot))