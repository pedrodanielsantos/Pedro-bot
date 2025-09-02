import discord
from discord.ext import commands
from config.constants import EMBED_COLOR

class HelpCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="help")
    async def help_command(self, ctx):
        pages = self.get_help_pages()
        view = self.create_help_view()
        await ctx.send(embed=pages[0], view=view)

    def get_help_pages(self):
        return [
            discord.Embed(
                title="Help (1/2)",
                description="Welcome to the bot's help section!",
                color=discord.Color(EMBED_COLOR),
            )
            .add_field(
                name="Command Syntax",
                value=(
                    "**Slash Commands**: Start with `/` and must be typed without a prefix.\n"
                    "**Prefix Commands**: Start with a `.` (e.g., `.help`)."
                ),
            )
            .add_field(
                name="General Commands",
                value=("**.help**: Display this help message."),
                inline=False
            )
            .add_field(
                name="Image Generation",
                value=(
                    "**/imagine**: Generate an image using Stable Diffusion.\n"
                    "**/model select**: Choose a Stable Diffusion model.\n"
                    "**/model info**: View detailed information about Stable Diffusion models."
                ),
                inline=False,
            )
            .add_field(
                name="Image Manipulation",
                value=(
                    "**/image petpet**: Generate a petpet GIF from an image source.\n"
                    "**/image heartlocket**: Generate a heart locket GIF from one or two image sources.\n"
                    "**/image explode**: Generate an exploding GIF from an image source."
                ),
                inline=False,
            )
            .set_footer(text="Page 1 of 2"),

            discord.Embed(
                title="Help (2/2)",
                description="Welcome to the bot's help section!",
                color=discord.Color(EMBED_COLOR),
            )
            .add_field(
                name="Custom Roles",
                value=(
                    "**/customrole create**: Create a custom role with a specific HEX color code.\n"
                    "**/customrole delete**: Delete your custom role.\n"
                    "**/customrole deleteid**: (Admin Only) Delete a custom role by User ID.\n"
                    "**/customrole update**: Update your custom roles name or color."
                ),
                inline=False,
            )
            .add_field(
                name="Random Fun",
                value=(
                    "**/cat**: Display a random image of a cat.\n"
                    "**/dog**: Display a random image of a dog.\n"
                    "**/8ball**: Ask the magic 8-ball a question.\n"
                    "**/choice**: Chooses randomly from the given options (Max. 10 options)."
                ),
                inline=False,
            )
            .add_field(
                name="Utility",
                value=(
                    "**/ping**: Checks the bot's latency.\n"
                    "**/avatar**: Displays the avatar of a user.\n"
                    "**/userinfo**: Displays information about a user.\n"
                    "**/serverinfo**: Displays server statistics."
                ),
                inline=False,
            )
            .set_footer(text="Page 2 of 2"),
        ]

    def create_help_view(self):
        view = discord.ui.View()
        buttons = [
            {"label": "<<", "style": discord.ButtonStyle.secondary, "custom_id": "help:first"},
            {"label": "<", "style": discord.ButtonStyle.secondary, "custom_id": "help:previous"},
            {"label": ">", "style": discord.ButtonStyle.secondary, "custom_id": "help:next"},
            {"label": ">>", "style": discord.ButtonStyle.secondary, "custom_id": "help:last"},
        ]
        for button in buttons:
            view.add_item(discord.ui.Button(**button))
        return view

    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction):
        if interaction.type == discord.InteractionType.component:
            custom_id = interaction.data.get("custom_id", "")
            if custom_id.startswith("help:"):
                await self.handle_help_interaction(interaction, custom_id)

    async def handle_help_interaction(self, interaction: discord.Interaction, custom_id: str):
        pages = self.get_help_pages()
        current_page = self.extract_page_number(interaction.message.embeds[0].footer.text)
        if custom_id == "help:first":
            new_page = 1
        elif custom_id == "help:previous":
            new_page = max(1, current_page - 1)
        elif custom_id == "help:next":
            new_page = min(len(pages), current_page + 1)
        elif custom_id == "help:last":
            new_page = len(pages)
        else:
            return  # Unknown custom_id; do nothing

        new_embed = pages[new_page - 1]
        await interaction.response.edit_message(embed=new_embed)

    def extract_page_number(self, footer_text: str) -> int:
        # Assumes footer text is in the format "Page X of Y"
        try:
            return int(footer_text.split()[1])
        except (IndexError, ValueError):
            return 1  # Default to page 1 if parsing fails

async def setup(bot):
    await bot.add_cog(HelpCog(bot))