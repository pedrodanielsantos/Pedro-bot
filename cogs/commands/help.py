import discord
from discord import app_commands
from discord.ext import commands
from db.database import get_guild_embed_color

# Keyed by qualified name, whole group (e.g. "image") or single subcommand
# (e.g. "setup welcome"). A subcommand entry wins over its group's entry.
# Anything unlisted falls into DEFAULT_CATEGORY so it can't silently vanish.
COMMAND_CATEGORIES = {
    "rename": "Lobbies",
    "resize": "Lobbies",

    "dog": "Fun",
    "cat": "Fun",
    "8ball": "Fun",
    "choice": "Fun",

    "rules": "Utility",
    "avatar": "Utility",
    "userinfo": "Utility",
    "serverinfo": "Utility",
    "stats": "Utility",
    "embed": "Utility",

    "image": "Image",

    "set": "Administration",
    "autorole": "Administration",
    "setup": "Administration",
    "test": "Administration",
}

# Render order; categories not listed here (including DEFAULT_CATEGORY) are appended after.
CATEGORY_ORDER = [
    "Lobbies",
    "Fun",
    "Utility",
    "Image",
    "Administration",
]

DEFAULT_CATEGORY = "Other"

CATEGORY_DESCRIPTIONS = {
    "Lobbies": "Manage your own temporary voice lobby",
    "Fun": "Random novelty commands",
    "Utility": "Info and utility commands",
    "Image": "Apply effects to images and create GIFs",
    "Administration": "Server configuration commands",
    DEFAULT_CATEGORY: "Uncategorized commands",
}

HOME_VALUE = "__home__"

class CategorySelect(discord.ui.Select):
    def __init__(self, category_starts: dict[str, int]):
        self.category_starts = category_starts
        super().__init__(placeholder="Jump to a category...", options=self._build_options(on_overview=True), row=0)

    def _build_options(self, on_overview: bool) -> list[discord.SelectOption]:
        options = []
        if not on_overview:
            options.append(discord.SelectOption(label="Help", description="Back to the category list", value=HOME_VALUE))
        options += [
            discord.SelectOption(label=category, description=CATEGORY_DESCRIPTIONS.get(category), value=category)
            for category in self.category_starts
        ]
        return options

    def refresh(self, on_overview: bool):
        self.options = self._build_options(on_overview)

    async def callback(self, interaction: discord.Interaction):
        view: HelpView = self.view
        value = self.values[0]
        view.current_page = 0 if value == HOME_VALUE else self.category_starts[value]
        view.update_buttons()
        await interaction.response.edit_message(embed=view.pages[view.current_page], view=view)

class HelpView(discord.ui.View):
    def __init__(self, pages, category_starts: dict[str, int]):
        super().__init__(timeout=180)
        self.pages = pages
        self.current_page = 0
        self.message: discord.WebhookMessage | None = None
        self.category_select = CategorySelect(category_starts) if category_starts else None
        if self.category_select:
            self.add_item(self.category_select)
        self.update_buttons()

    async def on_timeout(self):
        if self.message:
            try:
                await self.message.delete()
            except discord.HTTPException:
                pass

    def update_buttons(self):
        self.first_page.disabled = (self.current_page == 0)
        self.prev_page.disabled = (self.current_page == 0)
        self.next_page.disabled = (self.current_page == len(self.pages) - 1)
        self.last_page.disabled = (self.current_page == len(self.pages) - 1)
        if self.category_select:
            self.category_select.refresh(on_overview=(self.current_page == 0))

    @discord.ui.button(label="<<", style=discord.ButtonStyle.secondary, row=1)
    async def first_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_page = 0
        self.update_buttons()
        await interaction.response.edit_message(embed=self.pages[self.current_page], view=self)

    @discord.ui.button(label="<", style=discord.ButtonStyle.secondary, row=1)
    async def prev_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_page = max(0, self.current_page - 1)
        self.update_buttons()
        await interaction.response.edit_message(embed=self.pages[self.current_page], view=self)

    @discord.ui.button(label=">", style=discord.ButtonStyle.secondary, row=1)
    async def next_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_page = min(len(self.pages) - 1, self.current_page + 1)
        self.update_buttons()
        await interaction.response.edit_message(embed=self.pages[self.current_page], view=self)

    @discord.ui.button(label=">>", style=discord.ButtonStyle.secondary, row=1)
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
        view.message = await interaction.followup.send(embed=pages[0], view=view)

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
            if cmd.qualified_name == "help":
                continue  # the help command doesn't need to list itself
            category = self._category_for(cmd.qualified_name)
            desc = cmd.description or "No description provided."
            line = f"**/{cmd.qualified_name}**: *{desc}*\n"
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

        collected = self._collect_commands()

        overview = discord.Embed(
            title="Help",
            description="Select a category below, or use the arrows to browse each one in order.",
            color=color,
        )
        for category, field_value in collected:
            if not field_value:
                continue
            overview.add_field(
                name=category,
                value=CATEGORY_DESCRIPTIONS.get(category, "​"),
                inline=False,
            )

        # The overview occupies page 0; category pages are appended after it,
        # so category_starts naturally points past it. Each category gets its
        # own page(s) -- categories never share a page with one another.
        pages = [overview]
        category_starts: dict[str, int] = {}

        for category, field_value in collected:
            if not field_value:
                continue

            category_starts[category] = len(pages)
            prefix = CATEGORY_DESCRIPTIONS.get(category, "")
            prefix_block = f"{prefix}\n\n" if prefix else ""
            for chunk in self._chunk_field_value(field_value, limit=4096 - len(prefix_block)):
                pages.append(discord.Embed(
                    title=category,
                    description=f"{prefix_block}{chunk}",
                    color=color,
                ))

        total_pages = len(pages)
        for i, page in enumerate(pages):
            page.set_footer(text=f"Page {i + 1} of {total_pages}")

        return pages, category_starts

async def setup(bot):
    await bot.add_cog(HelpCog(bot))
