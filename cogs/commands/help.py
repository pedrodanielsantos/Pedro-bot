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
    "timestamp": "Utility",

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
        super().__init__(placeholder="Jump to a category...", options=self._build_options(on_overview=True))

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
        target = 0 if value == HOME_VALUE else self.category_starts[value]
        await view.go_to_page(interaction, target)

class HelpView(discord.ui.LayoutView):
    def __init__(self, pages: list[str], category_starts: dict[str, int], color):
        super().__init__(timeout=180)
        self.pages = pages
        self.current_page = 0
        self.message: discord.WebhookMessage | None = None

        self.text_display = discord.ui.TextDisplay(pages[0])

        self.first_page = discord.ui.Button(label="<<", style=discord.ButtonStyle.secondary)
        self.first_page.callback = self._first_page
        self.prev_page = discord.ui.Button(label="<", style=discord.ButtonStyle.secondary)
        self.prev_page.callback = self._prev_page
        self.page_indicator = discord.ui.Button(style=discord.ButtonStyle.secondary, disabled=True)
        self.next_page = discord.ui.Button(label=">", style=discord.ButtonStyle.secondary)
        self.next_page.callback = self._next_page
        self.last_page = discord.ui.Button(label=">>", style=discord.ButtonStyle.secondary)
        self.last_page.callback = self._last_page
        nav_row = discord.ui.ActionRow(
            self.first_page, self.prev_page, self.page_indicator, self.next_page, self.last_page
        )

        # Everything lives in one Container so the select and buttons render
        # attached to the text, inside the same accent-colored box.
        self.container = discord.ui.Container(self.text_display, accent_color=color)

        self.category_select = CategorySelect(category_starts) if category_starts else None
        if self.category_select:
            self.container.add_item(discord.ui.ActionRow(self.category_select))

        self.container.add_item(nav_row)

        self.add_item(self.container)
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
        self.page_indicator.label = f"Page {self.current_page + 1}/{len(self.pages)}"
        if self.category_select:
            self.category_select.refresh(on_overview=(self.current_page == 0))

    async def go_to_page(self, interaction: discord.Interaction, page: int):
        self.current_page = page
        self.text_display.content = self.pages[self.current_page]
        self.update_buttons()
        await interaction.response.edit_message(view=self)

    async def _first_page(self, interaction: discord.Interaction):
        await self.go_to_page(interaction, 0)

    async def _prev_page(self, interaction: discord.Interaction):
        await self.go_to_page(interaction, max(0, self.current_page - 1))

    async def _next_page(self, interaction: discord.Interaction):
        await self.go_to_page(interaction, min(len(self.pages) - 1, self.current_page + 1))

    async def _last_page(self, interaction: discord.Interaction):
        await self.go_to_page(interaction, len(self.pages) - 1)

class HelpCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="help", description="Displays the help message with all available commands")
    async def help_command(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        pages, category_starts, color = await self.get_help_pages(interaction.guild_id)
        view = HelpView(pages, category_starts, color)
        view.message = await interaction.followup.send(view=view)

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
    def _chunk_text(text: str, limit: int) -> list[str]:
        """Split text into pieces that fit Discord's per-TextDisplay character limit."""
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

        overview_parts = [
            "# Help",
            "Select a category below, or use the arrows to browse each one in order.",
        ]
        for category, field_value in collected:
            if not field_value:
                continue
            overview_parts.append(f"**{category}**\n{CATEGORY_DESCRIPTIONS.get(category, '')}")

        # The overview occupies page 0; category pages are appended after it,
        # so category_starts naturally points past it. Each category gets its
        # own page(s) -- categories never share a page with one another.
        pages = ["\n\n".join(overview_parts)]
        category_starts: dict[str, int] = {}

        for category, field_value in collected:
            if not field_value:
                continue

            category_starts[category] = len(pages)
            header = f"# {category}\n"
            prefix = CATEGORY_DESCRIPTIONS.get(category, "")
            prefix_block = f"{prefix}\n\n" if prefix else ""
            for chunk in self._chunk_text(field_value, limit=4000 - len(header) - len(prefix_block)):
                pages.append(f"{header}{prefix_block}{chunk}")

        return pages, category_starts, color

async def setup(bot):
    await bot.add_cog(HelpCog(bot))
