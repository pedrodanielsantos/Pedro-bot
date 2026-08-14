import discord
from discord import app_commands
from discord.ext import commands
from db.database import get_guild_embed_color
import random

ANSWERS = [
    "It is certain.",
    "It is decidedly so.",
    "Without a doubt.",
    "Yes, definitely.",
    "You may rely on it.",
    "As I see it, yes.",
    "Most likely.",
    "Outlook good.",
    "Yes.",
    "Signs point to yes.",
    "Reply hazy, try again.",
    "Ask again later.",
    "Better not tell you now.",
    "Cannot predict now.",
    "Concentrate and ask again.",
    "Don't count on it.",
    "My reply is no.",
    "My sources say no.",
    "Outlook not so good.",
    "Very doubtful.",
]

class EightBall(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="8ball", description="Ask the magic 8-ball a question")
    async def eight_ball(self, interaction: discord.Interaction, question: str):
        """Responds to a user's question with a random answer."""
        answer = random.choice(ANSWERS)

        color = await get_guild_embed_color(interaction.guild_id)

        embed = discord.Embed(
            title="🎱 Magic 8-Ball",
            description=f"**Question:** {question}\n**Answer:** {answer}",
            color=color
        )

        await interaction.response.send_message(embed=embed)

async def setup(bot: commands.Bot):
    await bot.add_cog(EightBall(bot))