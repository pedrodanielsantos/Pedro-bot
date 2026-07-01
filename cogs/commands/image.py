import discord
from discord.ext import commands
from discord import app_commands
import io
from typing import Optional
from dotenv import load_dotenv
import os
from config.constants import ERROR_COLOR
from cogs.core.mixins import SessionMixin

load_dotenv()

JEYY_API_KEY = os.getenv("JEYY_API_KEY")
JEYY_BASE_URL = "https://api.jeyy.xyz/v2/image"


class image(SessionMixin, commands.GroupCog, group_name="image"):
    def __init__(self, bot: commands.Bot):
        super().__init__()
        self.bot = bot

    def _resolve_single_source(
        self,
        user: Optional[discord.User],
        url: Optional[str],
        attachment: Optional[discord.Attachment],
    ) -> tuple[Optional[str], Optional[str]]:
        sources = [bool(user), bool(url), bool(attachment)]
        if sum(sources) > 1:
            return None, "Please provide only one image source: user, URL, or attachment."
        if not any(sources):
            return None, "No image specified. Please provide a user, URL, or attachment."
        if user:
            return user.display_avatar.url, None
        if url:
            return url, None
        return attachment.url, None

    async def _fetch_jeyy(
        self,
        interaction: discord.Interaction,
        endpoint: str,
        params: dict,
        filename: str,
    ) -> None:
        headers = {"Authorization": f"Bearer {JEYY_API_KEY}"}
        async with self.session.get(
            f"{JEYY_BASE_URL}/{endpoint}", params=params, headers=headers
        ) as response:
            response.raise_for_status()
            data = await response.read()
        await interaction.followup.send(file=discord.File(io.BytesIO(data), filename=filename))

    @app_commands.command(
        name="petpet",
        description="Generate a patpat gif from an avatar, image URL, or attachment"
    )
    @app_commands.describe(
        user="User whose avatar to use as image",
        url="URL to fetch image from",
        image="Image attachment to use"
    )
    async def petpet(
        self,
        interaction: discord.Interaction,
        user: Optional[discord.User] = None,
        url: Optional[str] = None,
        image: Optional[discord.Attachment] = None,
    ):
        image_url, error = self._resolve_single_source(user, url, image)
        if error:
            await interaction.response.send_message(
                embed=discord.Embed(description=error, color=ERROR_COLOR), ephemeral=True
            )
            return

        await interaction.response.defer(thinking=True)
        await self._fetch_jeyy(interaction, "patpat", {"image_url": image_url}, "patpat.gif")

    @app_commands.command(
        name="heartlocket",
        description="Generate a heart locket image from one or two image sources"
    )
    @app_commands.describe(
        user1="A user whose avatar to include",
        user2="Another user whose avatar to include",
        url1="An image URL to include",
        url2="Another image URL to include",
        image1="An image attachment to include",
        image2="Another image attachment to include"
    )
    async def heartlocket(
        self,
        interaction: discord.Interaction,
        user1: Optional[discord.User] = None,
        user2: Optional[discord.User] = None,
        url1: Optional[str] = None,
        url2: Optional[str] = None,
        image1: Optional[discord.Attachment] = None,
        image2: Optional[discord.Attachment] = None,
    ):
        resolved = [
            src for src in [
                user1.display_avatar.url if user1 else None,
                user2.display_avatar.url if user2 else None,
                url1,
                url2,
                image1.url if image1 else None,
                image2.url if image2 else None,
            ] if src
        ]

        if not resolved:
            await interaction.response.send_message(
                embed=discord.Embed(description="No image specified. Please provide at least one image source.", color=ERROR_COLOR),
                ephemeral=True,
            )
            return

        if len(resolved) > 2:
            await interaction.response.send_message(
                embed=discord.Embed(description="Please provide at most two image sources.", color=ERROR_COLOR),
                ephemeral=True,
            )
            return

        await interaction.response.defer(thinking=True)
        params: dict = {"image_url": resolved[0]}
        if len(resolved) == 2:
            params["image_url_2"] = resolved[1]
        await self._fetch_jeyy(interaction, "heart_locket", params, "heart_locket.gif")

    @app_commands.command(
        name="explode",
        description="Generate an exploding image effect from a user avatar, image URL, or attachment"
    )
    @app_commands.describe(
        user="User whose avatar to use as image",
        url="URL to fetch image from",
        image="Image attachment to use"
    )
    async def explode(
        self,
        interaction: discord.Interaction,
        user: Optional[discord.User] = None,
        url: Optional[str] = None,
        image: Optional[discord.Attachment] = None,
    ):
        image_url, error = self._resolve_single_source(user, url, image)
        if error:
            await interaction.response.send_message(
                embed=discord.Embed(description=error, color=ERROR_COLOR), ephemeral=True
            )
            return

        await interaction.response.defer(thinking=True)
        await self._fetch_jeyy(interaction, "bomb", {"image_url": image_url}, "explode.gif")


async def setup(bot: commands.Bot):
    await bot.add_cog(image(bot))
