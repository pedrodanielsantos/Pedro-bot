import discord
from discord.ext import commands
from discord import app_commands
import aiohttp
import io
from typing import Optional
from dotenv import load_dotenv
import os
import gc

# Load environment variables
load_dotenv()

# Get the API key
JEYY_API_KEY = os.getenv("JEYY_API_KEY")


class image(commands.GroupCog):
    def __init__(self, bot: commands.Bot):
        super().__init__()
        self.bot = bot
        self.session = aiohttp.ClientSession()

    async def cog_unload(self):
        print("cog_unload triggered (image)")
        if self.session and not self.session.closed:
            await self.session.close()

        gc.collect()

# ------------------------------------------------------------------------------------------- petpet Command -------------------------------------------------------------------------------------------

    @app_commands.command(
        name="petpet",
        description="Generate a patpat gif from an avatar, image URL, or attachment."
    )
    @app_commands.describe(
        user="User whose avatar to use as image.",
        url="URL to fetch image from.",
        image="Image attachment to use."
    )
    async def petpet(
        self,
        interaction: discord.Interaction,
        user: Optional[discord.User] = None,
        url: Optional[str] = None,
        image: Optional[discord.Attachment] = None
    ):

        # Ensure only one image source is provided
        image_sources = [bool(user), bool(url), bool(image)]
        if sum(image_sources) > 1:
            await interaction.response.send_message(
                "Please provide only one image source: user, URL, or attachment.",
                ephemeral=True
            )
            return

        # Ensure at least one image source is provided
        if not any(image_sources):
            await interaction.response.send_message(
                "No image specified. Please provide a user, URL, or attachment.",
                ephemeral=True
            )
            return

        # Defer the interaction response
        await interaction.response.defer(thinking=True)

        # Prepare the image URL
        image_url = None
        if user:
            image_url = user.display_avatar.url
        elif url:
            image_url = url
        elif image:
            image_url = image.url

        # Build the API request
        api_url = "https://api.jeyy.xyz/v2/image/patpat"  # Correct endpoint
        headers = {"Authorization": f"Bearer {JEYY_API_KEY}"}
        params = {"image_url": image_url}

        try:
            # Send the request to the API
            async with self.session.get(api_url, params=params, headers=headers) as response:
                if response.status != 200:
                    await interaction.followup.send(
                        f"API request failed with status code {response.status}.",
                    )
                    return

                # Read the response as binary (GIF)
                gif_data = await response.read()

                # Send the gif back to the user
                await interaction.followup.send(
                    file=discord.File(io.BytesIO(gif_data), filename="patpat.gif")
                )
        except aiohttp.ClientError as e:
            # Handle errors with the API request
            await interaction.followup.send(
                f"An error occurred while fetching the image: {e}",
            )

# ------------------------------------------------------------------------------------------- heartlocket Command -------------------------------------------------------------------------------------------

    @app_commands.command(
        name="heartlocket",
        description="Generate a heart locket image from one or two image sources."
    )
    @app_commands.describe(
        user1="First user whose avatar to use as image.",
        user2="Second user whose avatar to use as image (optional).",
        url1="First URL to fetch image from.",
        url2="Second URL to fetch image from (optional).",
        image1="First image attachment to use.",
        image2="Second image attachment to use (optional)."
    )
    async def heartlocket(
        self,
        interaction: discord.Interaction,
        user1: Optional[discord.User] = None,
        user2: Optional[discord.User] = None,
        url1: Optional[str] = None,
        url2: Optional[str] = None,
        image1: Optional[discord.Attachment] = None,
        image2: Optional[discord.Attachment] = None
    ):

        # Collect all provided inputs for image_url and image_url_2
        sources = {
            "user1": user1.display_avatar.url if user1 else None,
            "user2": user2.display_avatar.url if user2 else None,
            "url1": url1,
            "url2": url2,
            "image1": image1.url if image1 else None,
            "image2": image2.url if image2 else None,
        }

        # Separate sources into image_url and image_url_2 candidates
        image_url_candidates = [sources["user1"], sources["url1"], sources["image1"]]
        image_url_2_candidates = [sources["user2"], sources["url2"], sources["image2"]]

        # Filter out None values
        image_url_candidates = [src for src in image_url_candidates if src]
        image_url_2_candidates = [src for src in image_url_2_candidates if src]


        # Ensure at least one image source for image_url
        if not image_url_candidates:
            await interaction.response.send_message(
                "No image specified for the first image. Please provide a user, URL, or attachment.",
                ephemeral=True
            )
            return

        # Assign image_url and image_url_2
        image_url = image_url_candidates[0]  # The first valid source is used for image_url
        image_url_2 = (
            image_url_2_candidates[0]  # If a valid source exists for image_url_2
            if image_url_2_candidates
            else (image_url_candidates[1] if len(image_url_candidates) > 1 else None)  # Fallback to the second candidate from image_url sources
        )

        # Defer the interaction response
        await interaction.response.defer(thinking=True)

        # Build the API request
        api_url = "https://api.jeyy.xyz/v2/image/heart_locket"
        headers = {"Authorization": f"Bearer {JEYY_API_KEY}"}
        params = {"image_url": image_url}
        if image_url_2:
            params["image_url_2"] = image_url_2

        try:
            # Send the request to the API
            async with self.session.get(api_url, params=params, headers=headers) as response:
                if response.status != 200:
                    await interaction.followup.send(
                        f"API request failed with status code {response.status}.",
                    )
                    return

                # Read the response as binary (image file)
                img_data = await response.read()

                # Send the image back to the user
                await interaction.followup.send(
                    file=discord.File(io.BytesIO(img_data), filename="heart_locket.gif")
                )
        except aiohttp.ClientError as e:
            # Handle errors with the API request
            await interaction.followup.send(
                f"An error occurred while fetching the image: {e}",
            )

# ------------------------------------------------------------------------------------------- explode Command -------------------------------------------------------------------------------------------

    @app_commands.command(
        name="explode",
        description="Generate an exploding image effect from a user avatar, image URL, or attachment."
    )
    @app_commands.describe(
        user="User whose avatar to use as image.",
        url="URL to fetch image from.",
        image="Image attachment to use."
    )
    async def explode(
        self,
        interaction: discord.Interaction,
        user: Optional[discord.User] = None,
        url: Optional[str] = None,
        image: Optional[discord.Attachment] = None
    ):
        # Ensure only one image source is provided
        image_sources = [bool(user), bool(url), bool(image)]
        if sum(image_sources) > 1:
            await interaction.response.send_message(
                "Please provide only one image source: user, URL, or attachment.",
                ephemeral=True
            )
            return

        # Ensure at least one image source is provided
        if not any(image_sources):
            await interaction.response.send_message(
                "No image specified. Please provide a user, URL, or attachment.",
                ephemeral=True
            )
            return

        # Defer the interaction response
        await interaction.response.defer(thinking=True)

        # Prepare the image URL
        image_url = None
        if user:
            image_url = user.display_avatar.url
        elif url:
            image_url = url
        elif image:
            image_url = image.url

        # Build the API request
        api_url = "https://api.jeyy.xyz/v2/image/bomb"  # Correct endpoint
        headers = {"Authorization": f"Bearer {JEYY_API_KEY}"}
        params = {"image_url": image_url}

        try:
            # Send the request to the API
            async with self.session.get(api_url, params=params, headers=headers) as response:
                if response.status != 200:
                    await interaction.followup.send(
                        f"API request failed with status code {response.status}.",
                    )
                    return

                # Read the response as binary (image file)
                img_data = await response.read()

                # Send the image back to the user
                await interaction.followup.send(
                    file=discord.File(io.BytesIO(img_data), filename="explode.gif")
                )
        except aiohttp.ClientError as e:
            # Handle errors with the API request
            await interaction.followup.send(
                f"An error occurred while fetching the image: {e}",
            )

async def setup(bot: commands.Bot):
    await bot.add_cog(image(bot))