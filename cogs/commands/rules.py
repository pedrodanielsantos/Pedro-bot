import discord
from discord.ext import commands
from config.constants import EMBED_COLOR
from db.database import get_embed_color

class RulesCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.hybrid_command(name="rules", description="Displays the server rules.")
    async def rules(self, ctx: commands.Context):
        padding = "‎"
        rules_text = (
            f"{padding}\n**#1 Be Civil** | Keep arguments off the server\n\n"
            "**#2 Relatively SFW** | Use spoiler tags when necessary\n\n"
            f"**#3 No Hate Speech** | For the love of all that is good, please\n{padding}"
        )

        db_color = await get_embed_color(ctx.guild.id if ctx.guild else None)
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
                url="https://copyparty.pedros.tools/Discord/Pedro's/Pedros_Optimized.gif"
            )
            .set_footer(text="Just do your best to keep things running smoothly ❤︎")
        )
        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(RulesCog(bot))