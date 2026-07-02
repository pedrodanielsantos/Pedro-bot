import discord
from discord import app_commands
from discord.ext import commands
from config.constants import EMBED_COLOR
from db.database import get_embed_color

class ServerInfo(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="serverinfo", description="Displays server statistics")
    async def serverinfo(self, interaction: discord.Interaction):
        """Shows server information."""
        guild = interaction.guild
        fields = [
            ("Name", guild.name, True),
            ("ID", guild.id, True),
            ("Members", guild.member_count, True),
            ("Text Channels", len(guild.text_channels), True),
            ("Voice Channels", len(guild.voice_channels), True),
            ("Roles", len(guild.roles) - 1, True),
            ("Created", guild.created_at.strftime('%Y-%m-%d %H:%M:%S'), True),
            ("Owner", str(guild.owner), True)
        ]

        db_color = await get_embed_color(interaction.guild_id)
        if db_color:
            color = discord.Color(int(db_color, 16))
        else:
            color = discord.Color(EMBED_COLOR)

        embed = discord.Embed(
            title="Server Info",
            color=color
            )
        embed.set_thumbnail(url=guild.icon.url if guild.icon else None)

        for name, value, inline in fields:
            embed.add_field(name=name, value=value, inline=inline)

        await interaction.response.send_message(embed=embed)

async def setup(bot):
    await bot.add_cog(ServerInfo(bot))