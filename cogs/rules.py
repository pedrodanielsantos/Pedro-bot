import discord
from discord import app_commands
from discord.ext import commands
from config.constants import EMBED_COLOR
from db.database import get_embed_color

class RulesCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="rules", description="Displays the server rules.")
    async def rules(self, interaction: discord.Interaction):
        padding = "‎"
        rules_text = (
            f"{padding}\n**#1 Be Civil** | Keep arguments off the server\n\n"
            "**#2 Relatively SFW** | Use spoiler tags when necessary\n\n"
            f"**#3 No Hate Speech** | For the love of all that is good, please\n{padding}"
        )

        db_color = get_embed_color(interaction.guild_id)
        if db_color:
            color = discord.Color(int(db_color, 16))
        else:
            color = discord.Color(EMBED_COLOR)

        embed = (
            discord.Embed(
                title="📃 Rules",
                description=rules_text,
                color=color,
            )
            .set_thumbnail(
                url="https://images-ext-1.discordapp.net/external/hyWJXvXXf5k0chNZQ8XEUHEOrJlcj_mp-3Fy9UOmw5w/%3Fsize%3D512/https/cdn.discordapp.com/icons/1240063556217733141/a_121769f1e144b606ca9001a4b10d9566.gif"
            )
            .set_footer(text="Just do your best to keep things running smoothly ❤︎")
        )
        await interaction.response.send_message(embed=embed)

async def setup(bot):
    await bot.add_cog(RulesCog(bot))