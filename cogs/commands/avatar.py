import discord
from discord import app_commands
from discord.ext import commands
from db.database import get_guild_embed_color

class Avatar(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="avatar", description="Displays the avatar of a user")
    async def avatar(self, interaction: discord.Interaction, member: discord.Member = None):
        """Shows the avatar of the user."""
        member = member or interaction.user  # Default to the command user if no member is mentioned
        color = await get_guild_embed_color(interaction.guild_id)

        embed = discord.Embed(
            title=f"{member}'s Avatar",
            color=color
            )
        embed.set_image(url=member.avatar.url)
        await interaction.response.send_message(embed=embed)

async def setup(bot):
    await bot.add_cog(Avatar(bot))