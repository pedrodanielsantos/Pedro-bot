import os
import discord
from discord.ext import commands
from discord import app_commands
import aiohttp
import gc
from dotenv import load_dotenv

# Load environment variables
load_dotenv()
CAT_API_KEY = os.getenv("CAT_API_KEY")


class Cat(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.session = aiohttp.ClientSession()

    async def cog_unload(self):
        print("cog_unload triggered (cat)")
        if self.session and not self.session.closed:
            await self.session.close()
            
        gc.collect()

    @app_commands.command(name="cat", description="Fetch a random cat image.")
    async def fetch_cat(self, interaction: discord.Interaction):
        api_url = "https://api.thecatapi.com/v1/images/search"
        headers = {"x-api-key": CAT_API_KEY}

        await interaction.response.defer(thinking=True)
        try:
            async with self.session.get(api_url, headers=headers) as response:
                if response.status != 200:
                    await interaction.followup.send(
                        f"API request failed with status code {response.status}."
                    )
                    return

                data = await response.json()
                if data:
                    image_url = data[0]["url"]
                    await interaction.followup.send(image_url)
                else:
                    await interaction.followup.send("No image found.")
        except aiohttp.ClientError as e:
            await interaction.followup.send(f"An error occurred: {e}")


async def setup(bot: commands.Bot):
    await bot.add_cog(Cat(bot))