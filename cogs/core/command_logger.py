import discord
from discord.ext import commands

from db.database import get_log_channel
from config.constants import EMBED_COLOR

class CommandLogger(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.bot.tree.interaction_check = self.log_interaction

    async def log_interaction(self, interaction: discord.Interaction) -> bool:
        if interaction.command is None or interaction.guild is None:
            return True

        log_channel_id = await get_log_channel(interaction.guild_id)
        if not log_channel_id:
            return True

        log_channel = interaction.guild.get_channel(log_channel_id)
        if log_channel is None:
            return True

        options = interaction.namespace.__dict__
        options_str = ", ".join(f"{option_name}: {option_value}" for option_name, option_value in options.items()) if options else None

        description = f"**/{interaction.command.qualified_name}** used by {interaction.user.mention} in {interaction.channel.mention}"
        if options_str:
            description += f"\n{options_str}"

        embed = discord.Embed(description=description, color=EMBED_COLOR)
        embed.set_footer(text=f"User ID: {interaction.user.id}")

        try:
            await log_channel.send(embed=embed)
        except (discord.Forbidden, discord.HTTPException):
            pass

        return True

async def setup(bot: commands.Bot):
    await bot.add_cog(CommandLogger(bot))
