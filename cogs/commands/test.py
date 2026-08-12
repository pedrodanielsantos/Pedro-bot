import discord
from discord import app_commands
from discord.ext import commands
from utils.embeds import success_embed
from utils.errors import UserError
from utils.permissions import require_permission

class Test(commands.GroupCog, group_name="test"):
    def __init__(self, bot: commands.Bot):
        super().__init__()
        self.bot = bot

    @app_commands.command(name="welcome", description="Simulate a member joining to test the welcome message")
    async def welcome(self, interaction: discord.Interaction):
        if not interaction.guild:
            raise UserError("This command can only be used in a server.")

        await require_permission(interaction, "administrator")

        greeter_cog = self.bot.get_cog("WelcomeGreeter")
        if not greeter_cog:
            raise UserError("WelcomeGreeter cog is not loaded.")

        await interaction.response.defer(ephemeral=True)

        # Bypass the on_member_join bot-guard since this is an explicit test invocation
        await greeter_cog._send_welcome(interaction.guild.me)

        embed = success_embed("Simulated `on_member_join` event with the bot as the member.")
        await interaction.followup.send(embed=embed, ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(Test(bot))
