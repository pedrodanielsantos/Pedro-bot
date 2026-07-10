import discord
from discord import app_commands
from discord.ext import commands
from db.database import get_guild_embed_color

# Commands are categorized by their qualified name. A key may be a whole
# group (e.g. "image") or a single subcommand (e.g. "setup welcome"); the
# more specific subcommand entry wins over its group's entry. Anything not
# listed here falls into DEFAULT_CATEGORY so it can never silently vanish.
COMMAND_CATEGORIES = {
    # General
    "help": "General",
    "rules": "General",
    # Settings
    "set": "Settings",
    "autorole": "Settings",
    "setup welcome": "Settings",
    # Lobbies
    "setup lobbies": "Lobbies",
    "rename": "Lobbies",
    "resize": "Lobbies",
    # Image Manipulation
    "image": "Image Manipulation",
    # Random Fun
    "dog": "Random Fun",
    "cat": "Random Fun",
    "8ball": "Random Fun",
    "choice": "Random Fun",
    # Utility
    "ping": "Utility",
    "avatar": "Utility",
    "userinfo": "Utility",
    "serverinfo": "Utility",
    "stats": "Utility",
    "embed": "Utility",
}

# Order in which categories are rendered. Categories produced at runtime but
# not listed here (including DEFAULT_CATEGORY) are appended afterwards.
CATEGORY_ORDER = [
    "General",
    "Settings",
    "Lobbies",
    "Image Manipulation",
    "Random Fun",
    "Utility",
]

DEFAULT_CATEGORY = "Other"

class CategorySelect(discord.ui.Select):
    def __init__(self, category_starts: dict[str, int]):
        self.category_starts = category_starts
        options = [
            discord.SelectOption(label=category, value=category)
            for category in category_starts
        ]
        super().__init__(placeholder="Jump to a category...", options=options)

    async def callback(self, interaction: discord.Interaction):
        view: HelpView = self.view
        view.current_page = self.category_starts[self.values[0]]
        view.update_buttons()
        await interaction.response.edit_message(embed=view.pages[view.current_page], view=view)

class HelpView(discord.ui.View):
    def __init__(self, pages, category_starts: dict[str, int]):
        super().__init__(timeout=None)
        self.pages = pages
        self.current_page = 0
        if category_starts:
            self.add_item(CategorySelect(category_starts))
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
        pages, category_starts = await self.get_help_pages(interaction.guild_id)
        view = HelpView(pages, category_starts)
        await interaction.followup.send(embed=pages[0], view=view)

    @staticmethod
    def _category_for(qualified_name: str) -> str:
        # Prefer an exact subcommand match, then fall back to the group name.
        if qualified_name in COMMAND_CATEGORIES:
            return COMMAND_CATEGORIES[qualified_name]
        root = qualified_name.split(" ", 1)[0]
        return COMMAND_CATEGORIES.get(root, DEFAULT_CATEGORY)

    def _collect_commands(self):
        """Bucket every registered slash command by category, keyed leaf-first."""
        categorized: dict[str, list[str]] = {}
        for cmd in self.bot.tree.walk_commands():
            if not isinstance(cmd, app_commands.Command):
                continue  # skip Group containers; their leaves are walked too
            category = self._category_for(cmd.qualified_name)
            desc = cmd.description or "No description provided."
            line = f"**/{cmd.qualified_name}**: {desc}\n"
            categorized.setdefault(category, []).append(line)

        # Render known categories first (in declared order), then any extras.
        ordered = [c for c in CATEGORY_ORDER if c in categorized]
        ordered += [c for c in categorized if c not in CATEGORY_ORDER]
        return [(c, "".join(sorted(categorized[c]))) for c in ordered]

    @staticmethod
    def _chunk_field_value(text: str, limit: int = 1024) -> list[str]:
        """Split a field value into pieces that fit Discord's per-field character limit."""
        chunks = []
        current = ""
        for line in text.splitlines(keepends=True):
            if current and len(current) + len(line) > limit:
                chunks.append(current)
                current = ""
            current += line
        if current:
            chunks.append(current)
        return chunks

    async def get_help_pages(self, guild_id=None):
        color = await get_guild_embed_color(guild_id)

        pages = []
        category_starts: dict[str, int] = {}
        current_embed = discord.Embed(title="Help", color=color)

        for category, field_value in self._collect_commands():
            if not field_value:
                continue

            for i, chunk in enumerate(self._chunk_field_value(field_value)):
                if i > 0:
                    # Continuation of an oversized category: always give it a fresh page.
                    pages.append(current_embed)
                    current_embed = discord.Embed(title="Help", color=color)
                else:
                    # Calculate current size to check against Discord limits (6000 chars total, 25 fields)
                    current_size = len(current_embed.title or "") + len(current_embed.description or "")
                    for f in current_embed.fields:
                        current_size += len(f.name) + len(f.value)

                    # If adding this field exceeds safe limit (5000) or field count (25), start new page
                    if (current_size + len(category) + len(chunk) > 5000) or (len(current_embed.fields) >= 25):
                        pages.append(current_embed)
                        current_embed = discord.Embed(title="Help", color=color)

                    category_starts.setdefault(category, len(pages))

                current_embed.add_field(name=category, value=chunk, inline=False)

        pages.append(current_embed)

        total_pages = len(pages)
        for i, page in enumerate(pages):
            page.set_footer(text=f"Page {i + 1} of {total_pages}")

        return pages, category_starts

async def setup(bot):
    await bot.add_cog(HelpCog(bot))
