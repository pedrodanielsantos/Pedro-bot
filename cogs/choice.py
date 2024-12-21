import discord
from discord import app_commands
from discord.ext import commands
import random

class Choice(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(
        name="choice",
        description="Chooses randomly from the given options."
    )
    async def choice(
        self, 
        interaction: discord.Interaction,
        option1: str, 
        option2: str,
        option3: str = None, 
        option4: str = None, 
        option5: str = None, 
        option6: str = None, 
        option7: str = None, 
        option8: str = None, 
        option9: str = None, 
        option10: str = None
    ):
        """
        Randomly selects one of the provided options.
        - Requires at least two options.
        - Supports up to 10 options total.
        """
        # Gather all non-None options into a list
        all_options = [option for option in [option1, option2, option3, option4, option5, option6, option7, option8, option9, option10] if option]
        
        # Select a random option
        selected = random.choice(all_options)

        # Create an embed to display the result
        embed = discord.Embed(
            title="Random Choice",
            color=discord.Color.from_str("#1e1f22"),
            description=f"Out of the provided options, the choice is:\n**{selected}**"
        )
        embed.add_field(name="Options Provided", value=", ".join(all_options), inline=False)

        await interaction.response.send_message(embed=embed)

async def setup(bot):
    await bot.add_cog(Choice(bot))