import discord
from discord import app_commands
from discord.ext import commands
from config.constants import SUCCESS_COLOR, ERROR_COLOR

class Test(commands.GroupCog, group_name="test"):
    def __init__(self, bot: commands.Bot):
        super().__init__()
        self.bot = bot

    @app_commands.command(name="welcome", description="Simulate a member joining to test the welcome message")
    async def welcome(self, interaction: discord.Interaction):
        if not interaction.guild:
            embed = discord.Embed(description="This command can only be used in a server.", color=ERROR_COLOR)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        if not interaction.user.guild_permissions.administrator:
            embed = discord.Embed(description="You need **Administrator** permission to use this command.", color=ERROR_COLOR)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        setup_cog = self.bot.get_cog("Setup")
        if not setup_cog:
            embed = discord.Embed(description="Setup cog is not loaded.", color=ERROR_COLOR)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        # Simulate the bot joining by calling the listener directly
        await setup_cog.on_member_join(interaction.guild.me)

        embed = discord.Embed(description="Simulated `on_member_join` event with the bot as the member.", color=SUCCESS_COLOR)
        await interaction.followup.send(embed=embed, ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(Test(bot))
