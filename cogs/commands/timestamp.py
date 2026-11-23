import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime, timedelta, timezone
from db.database import get_guild_embed_color
from utils.chrono import UNIT_CHOICES, parse_local_datetime, parse_zone, timezone_autocomplete
from utils.errors import UserError

STYLE_CHOICES = [
    app_commands.Choice(name="11/21/2024 (d)", value="d"),
    app_commands.Choice(name="November 21, 2024 (D)", value="D"),
    app_commands.Choice(name="18:36 (t)", value="t"),
    app_commands.Choice(name="18:36:34 (T)", value="T"),
    app_commands.Choice(name="November 21, 2024 18:36 (f)", value="f"),
    app_commands.Choice(name="Thursday, November 21, 2024 18:36 (F)", value="F"),
    app_commands.Choice(name="in 3 hours (R)", value="R"),
]

class TimestampResultView(discord.ui.LayoutView):
    def __init__(self, tag: str, color):
        super().__init__(timeout=None)
        self.add_item(discord.ui.Container(
            discord.ui.TextDisplay(f"{tag}\n`{tag}`"),
            accent_color=color,
        ))

class Timestamp(commands.GroupCog, group_name="timestamp"):
    def __init__(self, bot: commands.Bot):
        super().__init__()
        self.bot = bot

    async def _reply_with_tag(self, interaction: discord.Interaction, epoch: int, style: str):
        tag = f"<t:{epoch}:{style}>"
        color = await get_guild_embed_color(interaction.guild_id)
        await interaction.response.send_message(view=TimestampResultView(tag, color))

    @app_commands.command(name="at", description="Generate a timestamp tag for a specific date and time")
    @app_commands.describe(
        date="Date as YYYY-MM-DD",
        time="Time as HH:MM or HH:MM:SS (24h)",
        timezone="Your IANA timezone, e.g. Europe/Lisbon",
        style="Display style",
    )
    @app_commands.choices(style=STYLE_CHOICES)
    @app_commands.autocomplete(timezone=timezone_autocomplete)
    async def at(self, interaction: discord.Interaction, date: str, time: str, timezone: str, style: str):
        try:
            moment = parse_local_datetime(date, time, parse_zone(timezone))
        except ValueError as e:
            raise UserError(str(e))

        epoch = int(moment.timestamp())
        await self._reply_with_tag(interaction, epoch, style)

    @app_commands.command(name="in", description="Generate a timestamp tag relative to now")
    @app_commands.describe(amount="How many units from now", unit="Unit of time", style="Display style")
    @app_commands.choices(unit=UNIT_CHOICES, style=STYLE_CHOICES)
    async def in_(self, interaction: discord.Interaction, amount: app_commands.Range[int, 1, None], unit: str, style: str = "R"):
        epoch = int((datetime.now(timezone.utc) + timedelta(**{unit: amount})).timestamp())
        await self._reply_with_tag(interaction, epoch, style)

async def setup(bot: commands.Bot):
    await bot.add_cog(Timestamp(bot))
