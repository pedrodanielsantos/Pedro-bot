import discord
from discord import app_commands
from discord.ext import commands
from config.constants import EMBED_COLOR

class UserInfo(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="userinfo", description="Displays information about a user.")
    async def userinfo(self, interaction: discord.Interaction, member: discord.Member = None):
        """Shows user information."""
        member = member or interaction.user  # Default to the command user if no member is mentioned
        fields = [
            ("Username", str(member), True),
            ("ID", member.id, True),
            ("Account Created", member.created_at.strftime('%Y-%m-%d %H:%M:%S'), False),
            ("Joined Server", member.joined_at.strftime('%Y-%m-%d %H:%M:%S'), False)
        ]

        embed = discord.Embed(
            title="User Info",
            color=discord.Color(EMBED_COLOR)
            )
        embed.set_thumbnail(url=member.avatar.url)

        for name, value, inline in fields:
            embed.add_field(name=name, value=value, inline=inline)

        await interaction.response.send_message(embed=embed)

async def setup(bot):
    await bot.add_cog(UserInfo(bot))