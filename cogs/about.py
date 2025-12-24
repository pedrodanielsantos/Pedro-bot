import discord
from discord import app_commands
from discord.ext import commands
import psutil
from datetime import datetime
import platform
from config.constants import EMBED_COLOR
from db.database import get_embed_color

class About(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.start_time = datetime.utcnow()

    @app_commands.command(name="about", description="Shows technical information about the bot.")
    async def about(self, interaction: discord.Interaction):
        """Displays technical information about the bot."""
        stats = [
            ("Servers", len(self.bot.guilds)),
            ("Total Members", sum(g.member_count for g in self.bot.guilds if g.member_count)),
            ("Text Channels", sum(len(g.text_channels) for g in self.bot.guilds)),
            ("Voice Channels", sum(len(g.voice_channels) for g in self.bot.guilds)),
            ("Total Channels", sum(len(g.text_channels) + len(g.voice_channels) for g in self.bot.guilds)),
            ("Shards", self.bot.shard_count or 1),
            ("RAM Usage", f"{psutil.Process().memory_info().rss / 1024**2:.2f} MB"),
            ("CPU Usage", f"{psutil.cpu_percent(interval=1):.2f}%"),
            ("Uptime", str(datetime.utcnow() - self.start_time).split(".")[0]),
            ("Python Version", platform.python_version()),
            ("discord.py Version", discord.__version__),
            ("System", f"{platform.system()} {platform.release()}")
        ]

        db_color = get_embed_color(interaction.guild_id)
        if db_color:
            color = discord.Color(int(db_color, 16))
        else:
            color = discord.Color(EMBED_COLOR)

        embed = discord.Embed(
            title="About the Bot",
            color=color
            )
        for name, value in stats:
            embed.add_field(name=name, value=value, inline=True)

        await interaction.response.send_message(embed=embed)

async def setup(bot):
    await bot.add_cog(About(bot))