import discord
from discord import app_commands
from discord.ext import commands

@app_commands.default_permissions(administrator=True)
class Setup(commands.GroupCog, name="setup"):
    def __init__(self, bot: commands.Bot):
        super().__init__()
        self.bot = bot

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Gate all /setup subcommands to admins only."""
        if interaction.user.guild_permissions.administrator:
            return True
        # must respond to the interaction or it errors
        await interaction.response.send_message(
            "You must be an **administrator** to use `/setup` commands.",
            ephemeral=True
        )
        return False

async def setup(bot: commands.Bot):
    await bot.add_cog(Setup(bot))
