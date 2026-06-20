import discord
from discord import app_commands
from discord.ext import commands
from config.constants import EMBED_COLOR
from db.database import get_embed_color

COG_GROUPS = {
    "General": ["HelpCog", "Rules"],
    "Settings": ["Set"],
    "Lobbies": ["Setup", "Rename", "Resize"],
    "Image Manipulation": ["image"],
    "Random Fun": ["Dog", "Cat", "EightBall", "Choice"],
    "Utility": ["Ping", "Avatar", "UserInfo", "ServerInfo", "Stats", "embed"]
}

class HelpView(discord.ui.View):
    def __init__(self, pages):
        super().__init__(timeout=None)
        self.pages = pages
        self.current_page = 0
        self.update_buttons()

    def update_buttons(self):
        self.first_page.disabled = (self.current_page == 0)
        self.prev_page.disabled = (self.current_page == 0)
        self.next_page.disabled = (self.current_page == len(self.pages) - 1)
        self.last_page.disabled = (self.current_page == len(self.pages) - 1)

    @discord.ui.button(label="<<", style=discord.ButtonStyle.secondary)
    async def first_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_page = 0
        self.update_buttons()
        await interaction.response.edit_message(embed=self.pages[self.current_page], view=self)

    @discord.ui.button(label="<", style=discord.ButtonStyle.secondary)
    async def prev_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_page = max(0, self.current_page - 1)
        self.update_buttons()
        await interaction.response.edit_message(embed=self.pages[self.current_page], view=self)

    @discord.ui.button(label=">", style=discord.ButtonStyle.secondary)
    async def next_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_page = min(len(self.pages) - 1, self.current_page + 1)
        self.update_buttons()
        await interaction.response.edit_message(embed=self.pages[self.current_page], view=self)

    @discord.ui.button(label=">>", style=discord.ButtonStyle.secondary)
    async def last_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_page = len(self.pages) - 1
        self.update_buttons()
        await interaction.response.edit_message(embed=self.pages[self.current_page], view=self)

class HelpCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="help", description="Displays the help message with all available commands")
    async def help_command(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        pages = await self.get_help_pages(interaction.guild_id)
        view = HelpView(pages)
        await interaction.followup.send(embed=pages[0], view=view)

    async def get_help_pages(self, guild_id=None):
        db_color = await get_embed_color(guild_id) if guild_id else None
        if db_color:
            color = discord.Color(int(db_color, 16))
        else:
            color = discord.Color(EMBED_COLOR)

        pages = []
        current_embed = discord.Embed(
            title="Help",
            description="Welcome to the bot's help section!",
            color=color,
        )

        for category, cog_names in COG_GROUPS.items():
            field_value = ""
            for cog_name in cog_names:
                cog = self.bot.get_cog(cog_name)
                if cog:
                    if isinstance(cog, commands.GroupCog):
                        root_group = cog.app_command
                        for sub in root_group.commands:
                            desc = sub.description or "No description provided."
                            full_name = f"{root_group.name} {sub.name}"
                            field_value += f"**/{full_name}**: {desc}\n"
                    else:
                        for cmd in cog.get_app_commands():
                            if isinstance(cmd, app_commands.Group):
                                for sub in cmd.commands:
                                    desc = sub.description or "No description provided."
                                    full_name = f"{cmd.name} {sub.name}"
                                    field_value += f"**/{full_name}**: {desc}\n"
                            else:
                                desc = cmd.description or "No description provided."
                                field_value += f"**/{cmd.name}**: {desc}\n"

                        # Also check for hybrid commands (which are stored as text commands)
                        for cmd in cog.get_commands():
                            if isinstance(cmd, commands.HybridCommand):
                                desc = cmd.description or "No description provided."
                                field_value += f"**/{cmd.name}**: {desc}\n"
            
            if field_value:
                # Calculate current size to check against Discord limits (6000 chars total, 25 fields)
                current_size = len(current_embed.title or "") + len(current_embed.description or "")
                for f in current_embed.fields:
                    current_size += len(f.name) + len(f.value)
                
                # If adding this field exceeds safe limit (5000) or field count (25), start new page
                if (current_size + len(category) + len(field_value) > 5000) or (len(current_embed.fields) >= 25):
                    pages.append(current_embed)
                    current_embed = discord.Embed(
                        title="Help",
                        description="Welcome to the bot's help section!",
                        color=color,
                    )
                
                current_embed.add_field(name=category, value=field_value, inline=False)

        pages.append(current_embed)

        total_pages = len(pages)
        for i, page in enumerate(pages):
            page.set_footer(text=f"Page {i + 1} of {total_pages}")

        return pages

async def setup(bot):
    await bot.add_cog(HelpCog(bot))