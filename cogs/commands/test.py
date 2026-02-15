import discord
from discord import app_commands
from discord.ext import commands

class Test(commands.GroupCog, group_name="test"):
    def __init__(self, bot: commands.Bot):
        super().__init__()
        self.bot = bot

    @app_commands.command(name="welcome", description="Simulate a member joining to test the welcome message.")
    async def welcome(self, interaction: discord.Interaction):
        if not interaction.guild:
            await interaction.response.send_message("This command can only be used in a server.", ephemeral=True)
            return

        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("You need **Administrator** permission to use this command.", ephemeral=True)
            return

        setup_cog = self.bot.get_cog("Setup")
        if not setup_cog:
            await interaction.response.send_message("❌ Setup cog is not loaded.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        
        # Simulate the bot joining by calling the listener directly
        await setup_cog.on_member_join(interaction.guild.me)
        
        await interaction.followup.send("✅ Simulated `on_member_join` event with the bot as the member.", ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(Test(bot))
