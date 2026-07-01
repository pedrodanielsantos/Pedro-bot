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

COMMON_IMAGE_DESCRIBE = {
    "user": "User whose avatar to use as image",
    "url": "URL to fetch image from",
    "image": "Image attachment to use",
}

# (command name, jeyy endpoint, output filename, description)
SIMPLE_EFFECTS: list[tuple[str, str, str, str]] = [
    ("petpet", "patpat", "patpat.gif", "Pat an image"),
    ("explode", "bomb", "explode.gif", "Blow up an image"),
    ("bonk", "bonks", "bonk.gif", "Bonk an image"),
    ("burn", "burn", "burn.gif", "Set an image on fire"),
    ("cow", "cow", "cow.gif", "Turn an image into a cow"),
    ("cube", "cube", "cube.gif", "Spin an image on a cube"),
    ("flush", "flush", "flush.gif", "Flush an image down a toilet"),
    ("math", "equations", "math.gif", "Cover an image in equations"),
    ("flag", "flag", "flag.gif", "Wave an image like a flag"),
    ("sphere", "globe", "sphere.gif", "Wrap an image around a spinning globe"),
    ("pyramid", "pyramid", "pyramid.gif", "Turn an image into a pyramid"),
    ("spin", "spin", "spin.gif", "Spin an image"),
    ("stereo", "stereo", "stereo.gif", "Split an image into a stereo effect"),
    ("stretch", "stretch", "stretch.gif", "Stretch an image"),
    ("rain", "rain", "rain.gif", "Make it rain with an image"),
    ("laundry", "laundry", "laundry.gif", "Toss an image in the laundry"),
    ("print", "print", "print.gif", "Print out an image"),
    ("matrix", "matrix", "matrix.gif", "Turn an image into the Matrix"),
    ("sensitive", "sensitive", "sensitive.gif", "Slap a sensitive content warning on an image"),
    ("billboard", "billboard", "billboard.gif", "Put an image on a billboard"),
]


def _make_simple_effect(name: str, endpoint: str, filename: str, description: str):
    async def callback(
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
        await self._fetch_jeyy(interaction, endpoint, {"image_url": image_url}, filename)

    callback.__name__ = name
    callback.__qualname__ = f"image.{name}"
    command = app_commands.command(name=name, description=description)(callback)
    return app_commands.describe(**COMMON_IMAGE_DESCRIBE)(command)


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

    for _name, _endpoint, _filename, _description in SIMPLE_EFFECTS:
        locals()[_name] = _make_simple_effect(_name, _endpoint, _filename, _description)
    del _name, _endpoint, _filename, _description

    @app_commands.command(
        name="heartlocket",
        description="Put one or two images in a heart locket"
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
        name="ace",
        description="Make an Ace Attorney dialogue image"
    )
    @app_commands.describe(
        name="Character name",
        side="Either attorney or prosecutor",
        text="Dialogue text (max 240 characters)"
    )
    @app_commands.choices(
        side=[
            app_commands.Choice(name="Attorney", value="attorney"),
            app_commands.Choice(name="Prosecutor", value="prosecutor"),
        ]
    )
    async def ace(
        self,
        interaction: discord.Interaction,
        name: str,
        side: app_commands.Choice[str],
        text: str,
    ):
        if len(text) > 240:
            await interaction.response.send_message(
                embed=discord.Embed(description="Text must be at most 240 characters.", color=ERROR_COLOR),
                ephemeral=True,
            )
            return

        await interaction.response.defer(thinking=True)
        await self._fetch_jeyy(
            interaction,
            "ace",
            {"name": name, "side": side.value, "text": text},
            "ace.gif",
        )

    @app_commands.command(
        name="glitch",
        description="Glitch an image"
    )
    @app_commands.describe(
        level="Intensity of the effect (1-10, default 3)",
        **COMMON_IMAGE_DESCRIBE,
    )
    async def glitch(
        self,
        interaction: discord.Interaction,
        user: Optional[discord.User] = None,
        url: Optional[str] = None,
        image: Optional[discord.Attachment] = None,
        level: Optional[app_commands.Range[int, 1, 10]] = 3,
    ):
        image_url, error = self._resolve_single_source(user, url, image)
        if error:
            await interaction.response.send_message(
                embed=discord.Embed(description=error, color=ERROR_COLOR), ephemeral=True
            )
            return

        await interaction.response.defer(thinking=True)
        await self._fetch_jeyy(
            interaction, "glitch", {"image_url": image_url, "level": level}, "glitch.gif"
        )

    @app_commands.command(
        name="hearts",
        description="Cover an image in hearts"
    )
    @app_commands.describe(
        rainbow="Apply rainbow coloring (default False)",
        **COMMON_IMAGE_DESCRIBE,
    )
    async def hearts(
        self,
        interaction: discord.Interaction,
        user: Optional[discord.User] = None,
        url: Optional[str] = None,
        image: Optional[discord.Attachment] = None,
        rainbow: Optional[bool] = False,
    ):
        image_url, error = self._resolve_single_source(user, url, image)
        if error:
            await interaction.response.send_message(
                embed=discord.Embed(description=error, color=ERROR_COLOR), ephemeral=True
            )
            return

        await interaction.response.defer(thinking=True)
        await self._fetch_jeyy(
            interaction,
            "hearts",
            {"image_url": image_url, "rainbow": str(rainbow).lower()},
            "hearts.gif",
        )

    @app_commands.command(
        name="earthquake",
        description="Shake an image like an earthquake"
    )
    @app_commands.describe(
        level="Intensity of the effect (1-10, default 3)",
        **COMMON_IMAGE_DESCRIBE,
    )
    async def earthquake(
        self,
        interaction: discord.Interaction,
        user: Optional[discord.User] = None,
        url: Optional[str] = None,
        image: Optional[discord.Attachment] = None,
        level: Optional[app_commands.Range[int, 1, 10]] = 3,
    ):
        image_url, error = self._resolve_single_source(user, url, image)
        if error:
            await interaction.response.send_message(
                embed=discord.Embed(description=error, color=ERROR_COLOR), ephemeral=True
            )
            return

        await interaction.response.defer(thinking=True)
        await self._fetch_jeyy(
            interaction, "earthquake", {"image_url": image_url, "level": level}, "earthquake.gif"
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(image(bot))
