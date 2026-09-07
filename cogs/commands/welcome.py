import io
import discord
from discord import app_commands
from discord.ext import commands
from typing import Optional

from db.database import get_welcome_channel, get_guild_embed_color, set_welcome_channel
from utils.embeds import success_embed
from utils.errors import UserError
from utils.permissions import require_permission, visibility_gate

@visibility_gate("administrator")
class Welcome(commands.GroupCog, group_name="welcome"):
    def __init__(self, bot: commands.Bot):
        super().__init__()
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

    @app_commands.command(name="channel", description="Set or disable the welcome message channel")
    @app_commands.describe(channel="The channel to send welcome messages in (leave empty to disable)")
    async def channel(self, interaction: discord.Interaction, channel: Optional[discord.TextChannel] = None):
        await require_permission(interaction, "administrator")

        if channel is None:
            await set_welcome_channel(interaction.guild_id, None)
            embed = success_embed("Welcome messages have been disabled.")
        else:
            await set_welcome_channel(interaction.guild_id, channel.id)
            embed = success_embed(f"Welcome messages will now be sent in {channel.mention}.")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="test", description="Simulate a member joining to test the welcome message")
    async def test(self, interaction: discord.Interaction):
        if not interaction.guild:
            raise UserError("This command can only be used in a server.")

        await require_permission(interaction, "administrator")

        await interaction.response.defer(ephemeral=True)

        # Bypass the on_member_join bot-guard since this is an explicit test invocation
        await self._send_welcome(interaction.guild.me)

        embed = success_embed("Simulated `on_member_join` event with the bot as the member.")
        await interaction.followup.send(embed=embed, ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(Welcome(bot))
