import discord
from discord import app_commands
from discord.ext import commands
from config.constants import ERROR_COLOR
from db.database import get_guild_embed_color

class UserInfo(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="userinfo", description="Displays information about a user")
    @app_commands.describe(
        member="A member of this server",
        user_id="The user ID to look up"
    )
    async def userinfo(self, interaction: discord.Interaction, member: discord.Member = None, user_id: str = None):
        """Shows user information."""
        is_member = False

        if member:
            target = member
            is_member = True
        elif user_id:
            try:
                uid = int(user_id)
            except ValueError:
                embed = discord.Embed(description="That doesn't look like a valid user ID.", color=ERROR_COLOR)
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return

            guild_member = interaction.guild.get_member(uid) if interaction.guild else None
            if guild_member:
                target = guild_member
                is_member = True
            else:
                try:
                    target = await self.bot.fetch_user(uid)
                except discord.NotFound:
                    embed = discord.Embed(description="No user found with that ID.", color=ERROR_COLOR)
                    await interaction.response.send_message(embed=embed, ephemeral=True)
                    return
                except discord.HTTPException:
                    embed = discord.Embed(description="Failed to fetch that user's information.", color=ERROR_COLOR)
                    await interaction.response.send_message(embed=embed, ephemeral=True)
                    return
        else:
            target = interaction.user
            is_member = isinstance(target, discord.Member)

        fields = [
            ("Username", str(target), True),
            ("ID", target.id, True),
            ("Account Created", target.created_at.strftime('%Y-%m-%d %H:%M:%S'), False),
        ]
        if is_member and target.joined_at:
            fields.append(("Joined Server", target.joined_at.strftime('%Y-%m-%d %H:%M:%S'), False))

        color = await get_guild_embed_color(interaction.guild_id)

        embed = discord.Embed(
            title="User Info",
            color=color
            )
        embed.set_thumbnail(url=target.display_avatar.url)

        for name, value, inline in fields:
            embed.add_field(name=name, value=value, inline=inline)

        if not is_member:
            embed.set_footer(text="This user is not a member of this server.")

        await interaction.response.send_message(embed=embed)

async def setup(bot: commands.Bot):
    await bot.add_cog(UserInfo(bot))