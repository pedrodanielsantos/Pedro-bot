import discord
from discord import app_commands
from discord.ext import commands
from config.constants import EMBED_COLOR
from db.database import get_embed_color
import random

class Choice(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(
        name="choice",
        description="Chooses randomly from the given options (separated by commas)."
    )
    @app_commands.describe(options="The options to choose from, separated by commas.")
    async def choice(
        self, 
        interaction: discord.Interaction,
        options: str
    ):
        """
        Randomly selects one of the provided options.
        - Separate options with commas.
        """
        # Split by comma and strip whitespace
        all_options = [opt.strip() for opt in options.split(",") if opt.strip()]

        if len(all_options) < 2:
            await interaction.response.send_message("Please provide at least two options separated by commas.", ephemeral=True)
            return
        
        # Select a random option
        selected = random.choice(all_options)

        db_color = await get_embed_color(interaction.guild_id)
        if db_color:
            color = discord.Color(int(db_color, 16))
        else:
            color = discord.Color(EMBED_COLOR)

        # Create an embed to display the result
        embed = discord.Embed(
            title="Random Choice",
            description=f"Out of the provided options, the choice is:\n**{selected}**",
            color=color
        )

        options_str = ", ".join(all_options)
        if len(options_str) > 1024:
            options_str = options_str[:1021] + "..."
        embed.add_field(name="Options Provided", value=options_str, inline=False)

        await interaction.response.send_message(embed=embed)

async def setup(bot):
    await bot.add_cog(Choice(bot))