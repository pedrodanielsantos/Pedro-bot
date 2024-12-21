import discord
from discord import app_commands
from discord.ext import commands

class ServerInfo(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="serverinfo", description="Displays server statistics.")
    async def serverinfo(self, interaction: discord.Interaction):
        """Shows server information."""
        guild = interaction.guild
        fields = [
            ("Server Name", guild.name, True),
            ("Server ID", guild.id, True),
            ("Owner", str(guild.owner), True),
            ("Member Count", guild.member_count, True),
            ("Text Channels", len(guild.text_channels), True),
            ("Voice Channels", len(guild.voice_channels), True),
            ("Roles", len(guild.roles), True),
            ("Created On", guild.created_at.strftime('%Y-%m-%d %H:%M:%S'), False)
        ]

        embed = discord.Embed(title="Server Info", color=discord.Color.from_str("#1e1f22"))
        embed.set_thumbnail(url=guild.icon.url if guild.icon else None)

        for name, value, inline in fields:
            embed.add_field(name=name, value=value, inline=inline)

        await interaction.response.send_message(embed=embed)

async def setup(bot):
    await bot.add_cog(ServerInfo(bot))