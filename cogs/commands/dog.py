import os
import discord
from discord.ext import commands
from discord import app_commands
from dotenv import load_dotenv
from config.constants import ERROR_COLOR
from cogs.core.mixins import SessionMixin

load_dotenv()
DOG_API_KEY = os.getenv("DOG_API_KEY")


class Dog(SessionMixin, commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="dog", description="Fetch a random dog image")
    async def fetch_dog(self, interaction: discord.Interaction):
        api_url = "https://api.thedogapi.com/v1/images/search"
        headers = {"x-api-key": DOG_API_KEY}

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
    await bot.add_cog(Dog(bot))