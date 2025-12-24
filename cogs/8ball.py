import discord
from discord import app_commands
from discord.ext import commands
from config.constants import EMBED_COLOR
from db.database import get_embed_color
import random

class EightBall(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.answers = [
            "Yes, definitely.",
            "Without a doubt.",
            "As I see it, yes.",
            "Most likely.",
            "Ask again later.",
            "Cannot predict now.",
            "Don't count on it.",
            "My reply is no.",
            "Very doubtful.",
            "It’s not looking good."
        ]

    @app_commands.command(name="8ball", description="Ask the magic 8-ball a question!")
    async def eight_ball(self, interaction: discord.Interaction, question: str):
        """Responds to a user's question with a random answer."""
        # Randomly select an answer
        answer = random.choice(self.answers)

        db_color = get_embed_color(interaction.guild_id)
        if db_color:
            color = discord.Color(int(db_color, 16))
        else:
            color = discord.Color(EMBED_COLOR)

        # Create the embed
        embed = discord.Embed(
            title="🎱 Magic 8-Ball",
            description=f"**Question:** {question}\n**Answer:** {answer}",
            color=color
        )

        # Send the embed response
        await interaction.response.send_message(embed=embed)

async def setup(bot):
    await bot.add_cog(EightBall(bot))