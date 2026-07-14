import discord
from discord import app_commands
from discord.ext import commands
from db.database import get_guild_embed_color
from utils.uptime import format_uptime

class Stats(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="stats", description="Shows technical information about the bot")
    async def stats(self, interaction: discord.Interaction):
        """Displays technical information about the bot."""
        uptime_str = format_uptime(self.bot.launch_time)

        server_count = len(self.bot.guilds)
        member_count = sum(g.member_count for g in self.bot.guilds if g.member_count)
        shard_count = self.bot.shard_count or 1

        color = await get_guild_embed_color(interaction.guild_id)

        embed = discord.Embed(
            title="Statistics",
            color=color
        )
        embed.add_field(name="🌎 Servers", value=f"`{server_count}`", inline=True)
        embed.add_field(name="👥 Members", value=f"`{member_count}`", inline=True)
        channel_count = sum(len(guild.channels) for guild in self.bot.guilds)
        embed.add_field(name="💬 Channels", value=f"`{channel_count}`", inline=True)
        latency = round(self.bot.latency * 1000)
        embed.add_field(name="💠 Shards", value=f"`{shard_count}`", inline=True)
        embed.add_field(name="📶 Latency", value=f"`{latency}ms`", inline=True)
        embed.add_field(name="⏱️ Uptime", value=f"`{uptime_str}`", inline=True)

        await interaction.response.send_message(embed=embed)

async def setup(bot: commands.Bot):
    await bot.add_cog(Stats(bot))