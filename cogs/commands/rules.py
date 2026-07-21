from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands
from config.constants import ERROR_COLOR, SUCCESS_COLOR
from db.database import get_guild_embed_color

RULES = [
    ("#1 | Be Civil", "Keep arguments off the server."),
    ("#2 | Keep It Tasteful", "Spoiler-tag anything NSFW. Gore, animal cruelty/death, and other extreme or shock content are not allowed, no exceptions."),
    ("#3 | No Hate Speech", "Racism, homophobia, transphobia, and other hate speech are not tolerated."),
]

class RulesView(discord.ui.LayoutView):
    def __init__(self, color):
        super().__init__(timeout=None)

        container = discord.ui.Container(
            discord.ui.TextDisplay("# Rules"),
            discord.ui.Separator(),
            discord.ui.Separator(visible=False),
            *[
                item
                for title, desc in RULES
                for item in (discord.ui.TextDisplay(f"**{title}**\n{desc}"), discord.ui.Separator())
            ][:-1],
            discord.ui.Separator(visible=False),
            discord.ui.Separator(),
            discord.ui.TextDisplay("-# Keep things running smoothly ❤︎"),
            accent_color=color,
        )

        self.add_item(container)

class Rules(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def _send_error(self, interaction: discord.Interaction, message: str):
        embed = discord.Embed(description=message, color=ERROR_COLOR)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="rules", description="Displays the server rules")
    @app_commands.describe(
        message_id="ID of an existing rules message to update instead of sending a new one (admin only)",
        channel="Channel the message is in, if not this one",
    )
    async def rules(
        self,
        interaction: discord.Interaction,
        message_id: Optional[str] = None,
        channel: Optional[discord.TextChannel] = None,
    ):
        color = await get_guild_embed_color(interaction.guild_id)

        if message_id is None:
            await interaction.response.send_message(view=RulesView(color))
            return

        if not (isinstance(interaction.user, discord.Member) and interaction.user.guild_permissions.administrator):
            await self._send_error(interaction, "You need Administrator permission to edit an existing rules message.")
            return

        try:
            target_id = int(message_id)
        except ValueError:
            await self._send_error(interaction, "Invalid Message ID. Please enter a numeric ID.")
            return

        target_channel = channel or interaction.channel
        try:
            message = await target_channel.fetch_message(target_id)
        except discord.NotFound:
            await self._send_error(interaction, "That message isn't in this channel. Specify which channel it's in.")
            return

        if message.author != self.bot.user:
            await self._send_error(interaction, "I can only edit my own messages.")
            return

        await message.edit(content=None, embed=None, view=RulesView(color))
        confirm_embed = discord.Embed(description=f"Rules message updated in {target_channel.mention}.", color=SUCCESS_COLOR)
        await interaction.response.send_message(embed=confirm_embed, ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(Rules(bot))
