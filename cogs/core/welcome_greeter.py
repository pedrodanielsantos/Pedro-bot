import io
import discord
from discord.ext import commands

from db.database import get_welcome_channel, get_guild_embed_color

class WelcomeGreeter(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        if member.bot:
            return
        await self._send_welcome(member)

    async def _send_welcome(self, member: discord.Member):
        channel_id = await get_welcome_channel(member.guild.id)
        if not channel_id:
            return

        channel = member.guild.get_channel(channel_id)
        if not channel:
            return

        color = await get_guild_embed_color(member.guild.id)

        description = (
            f"Welcome to {member.guild.name} {member.mention}!\n\n"
            "Check out https://discord.com/channels/1240063556217733141/1240063556289040449 and <id:customize>."
        )

        ext = "gif" if member.display_avatar.is_animated() else "png"
        author_icon_name = f"author_icon.{ext}"
        thumbnail_name = f"thumbnail.{ext}"

        embed = discord.Embed(description=description, color=color)
        embed.set_author(name=member.name, icon_url=f"attachment://{author_icon_name}")
        embed.set_thumbnail(url=f"attachment://{thumbnail_name}")

        try:
            author_icon_bytes = await member.display_avatar.with_size(128).read()
            thumbnail_bytes = await member.display_avatar.with_size(1024).read()
        except discord.HTTPException:
            return

        files = [
            discord.File(io.BytesIO(author_icon_bytes), filename=author_icon_name),
            discord.File(io.BytesIO(thumbnail_bytes), filename=thumbnail_name),
        ]

        try:
            await channel.send(embed=embed, files=files)
        except (discord.Forbidden, discord.HTTPException):
            pass

async def setup(bot: commands.Bot):
    await bot.add_cog(WelcomeGreeter(bot))
