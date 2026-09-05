import discord
from discord import app_commands
from discord.ext import commands
from db.database import get_guild_embed_color
from utils.paginator import TEXT_DISPLAY_LIMIT, JumpTarget, PaginatorView, chunk_text
from utils.permissions import is_visible_to

# Keyed by qualified name, whole group (e.g. "image") or single subcommand
# (e.g. "setup welcome"). A subcommand entry wins over its group's entry.
# Anything unlisted falls into DEFAULT_CATEGORY so it can't silently vanish.
COMMAND_CATEGORIES = {
    "rename": "Lobbies",
    "resize": "Lobbies",
    "region": "Lobbies",

    "dog": "Fun",
    "cat": "Fun",
    "8ball": "Fun",
    "choice": "Fun",

    "help": "Utility",
    "settings": "Utility",
    "rules": "Utility",
    "avatar": "Utility",
    "userinfo": "Utility",
    "serverinfo": "Utility",
    "stats": "Utility",
    "timestamp": "Utility",

    "image": "Image",

    "set": "Administration",
    "serverconfig": "Administration",
    "embed": "Administration",
    "autorole": "Administration",
    "setup": "Administration",
    "test": "Administration",
    "log": "Administration",
    "moderation": "Administration",
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

class HelpCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="help", description="Displays the help message with all available commands")
    async def help_command(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        pages, targets, color = await self.get_help_pages(interaction.user, interaction.guild_id)
        view = PaginatorView(
            pages,
            color,
            targets=targets,
            home_label="Help",
            home_description="Back to the category list",
            placeholder="Jump to a category...",
        )
        view.message = await interaction.followup.send(view=view)

    @staticmethod
    def _category_for(qualified_name: str) -> str:
        # Prefer an exact subcommand match, then fall back to the group name.
        if qualified_name in COMMAND_CATEGORIES:
            return COMMAND_CATEGORIES[qualified_name]
        root = qualified_name.split(" ", 1)[0]
        return COMMAND_CATEGORIES.get(root, DEFAULT_CATEGORY)

    def _collect_commands(self, user):
        """Bucket every slash command the user can see by category, keyed leaf-first."""
        categorized: dict[str, list[str]] = {}
        for cmd in self.bot.tree.walk_commands():
            if not isinstance(cmd, app_commands.Command):
                continue  # skip Group containers; their leaves are walked too
            if not is_visible_to(user, cmd):
                continue
            category = self._category_for(cmd.qualified_name)
            desc = cmd.description or "No description provided."
            line = f"**/{cmd.qualified_name}**: *{desc}*\n"
            categorized.setdefault(category, []).append(line)

        # Render known categories first (in declared order), then any extras.
        ordered = [c for c in CATEGORY_ORDER if c in categorized]
        ordered += [c for c in categorized if c not in CATEGORY_ORDER]
        return [(c, "".join(sorted(categorized[c]))) for c in ordered]

    async def get_help_pages(self, user, guild_id=None):
        color = await get_guild_embed_color(guild_id)

        collected = self._collect_commands(user)

        overview_parts = [
            "# Help",
            "Select a category below, or use the arrows to browse each one in order.",
        ]
        for category, field_value in collected:
            if not field_value:
                continue
            overview_parts.append(f"**{category}**\n{CATEGORY_DESCRIPTIONS.get(category, '')}")

        # The overview occupies page 0; category pages are appended after it,
        # so each target naturally points past it. Each category gets its own
        # page(s) -- categories never share a page with one another.
        pages = ["\n\n".join(overview_parts)]
        targets: list[JumpTarget] = []

        for category, field_value in collected:
            if not field_value:
                continue

            targets.append(JumpTarget(
                label=category,
                page=len(pages),
                description=CATEGORY_DESCRIPTIONS.get(category),
            ))
            header = f"# {category}\n"
            prefix = CATEGORY_DESCRIPTIONS.get(category, "")
            prefix_block = f"{prefix}\n\n" if prefix else ""
            for chunk in chunk_text(field_value, limit=TEXT_DISPLAY_LIMIT - len(header) - len(prefix_block)):
                pages.append(f"{header}{prefix_block}{chunk}")

        return pages, targets, color

async def setup(bot: commands.Bot):
    await bot.add_cog(HelpCog(bot))
