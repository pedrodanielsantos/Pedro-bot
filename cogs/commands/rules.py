import logging
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from db.database import (
    get_guild_embed_color, rules_get, rule_add, rule_update, rule_delete, rule_move,
    get_rules_settings, set_rules_footer, set_rules_message, set_rules_color,
)
from utils.color import parse_hex_color
from utils.embeds import success_embed
from utils.errors import UserError
from utils.permissions import require_permission, visibility_gate

logger = logging.getLogger("rules")

# Required guild permission for each /rule subcommand. Change the value here to
# regate a command, no other code needs to change.
PERMISSIONS = {
    "add": "manage_guild",
    "edit": "manage_guild",
    "delete": "manage_guild",
    "move": "manage_guild",
    "footer": "manage_guild",
    "color": "manage_guild",
    "post": "manage_guild",
}

# Discord caps a components message at 40 components and 4000 characters of
# text in total. The layout uses 2 components per rule plus up to 6 more.
MAX_RULES = 17
MESSAGE_TEXT_LIMIT = 4000

MAX_TITLE_LENGTH = 100
MAX_DESCRIPTION_LENGTH = 1000
MAX_FOOTER_LENGTH = 200

HEADER = "# Rules"


def _rule_text(number: int, rule: dict) -> str:
    return f"**#{number} | {rule['title']}**\n{rule['description']}"


def _footer_line(footer: str) -> str:
    return f"-# {footer}"


def _active_footer(settings: dict) -> Optional[str]:
    return settings["footer"] if settings["footer_enabled"] else None


def _check_fits(rules: list[dict], footer: Optional[str]):
    """Raises UserError unless the rules message would fit Discord's limits."""
    if len(rules) > MAX_RULES:
        raise UserError(f"A server can have at most **{MAX_RULES}** rules.")

    total = len(HEADER) + sum(len(_rule_text(n, rule)) for n, rule in enumerate(rules, start=1))
    if footer:
        total += len(_footer_line(footer))
    if total > MESSAGE_TEXT_LIMIT:
        raise UserError(
            f"That would make the rules message **{total}** characters long, "
            f"over Discord's limit of **{MESSAGE_TEXT_LIMIT}**. Shorten a rule first."
        )


def _resolve(value: str, rules: list[dict]) -> int:
    """Index of a picked or typed rule number like 2 or #2."""
    try:
        number = int(value.strip().lstrip("#"))
    except ValueError:
        raise UserError("Pick a rule from the list, or type its number.")
    if not 1 <= number <= len(rules):
        raise UserError(f"There's no rule **#{number}**.")
    return number - 1


class RulesView(discord.ui.LayoutView):
    def __init__(self, rules: list[dict], footer: Optional[str], color: discord.Color):
        super().__init__(timeout=None)

        items = [discord.ui.TextDisplay(HEADER), discord.ui.Separator(), discord.ui.Separator(visible=False)]
        for n, rule in enumerate(rules, start=1):
            if n > 1:
                items.append(discord.ui.Separator())
            items.append(discord.ui.TextDisplay(_rule_text(n, rule)))
        # Only reachable on the posted message, after its last rule is deleted.
        if not rules:
            items.append(discord.ui.TextDisplay("*No rules set.*"))
        if footer:
            items += [discord.ui.Separator(visible=False), discord.ui.Separator(), discord.ui.TextDisplay(_footer_line(footer))]

        self.add_item(discord.ui.Container(*items, accent_color=color))


async def build_rules_view(guild_id: int) -> RulesView:
    settings = await get_rules_settings(guild_id)
    color = discord.Color(int(settings["color"], 16)) if settings["color"] else await get_guild_embed_color(guild_id)
    return RulesView(await rules_get(guild_id), _active_footer(settings), color)


class Rules(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="rules", description="Displays the server rules")
    @app_commands.guild_only()
    async def rules(self, interaction: discord.Interaction):
        if not await rules_get(interaction.guild_id):
            raise UserError("This server has no rules yet.")
        await interaction.response.send_message(view=await build_rules_view(interaction.guild_id), ephemeral=True)


@app_commands.guild_only()
@visibility_gate(*PERMISSIONS.values())
class Rule(commands.GroupCog, group_name="rule"):
    def __init__(self, bot: commands.Bot):
        super().__init__()
        self.bot = bot

    async def _check_permission(self, interaction: discord.Interaction, command_name: str):
        await require_permission(interaction, PERMISSIONS[command_name])

    async def _refresh_posted(self, guild: discord.Guild) -> Optional[str]:
        """Edits the posted rules message to match the DB. Returns a note for the reply
        when there's nothing to edit or the edit failed."""
        settings = await get_rules_settings(guild.id)
        if not settings["message_id"]:
            return "The rules aren't posted anywhere yet, use `/rule post` to post them."

        channel = guild.get_channel_or_thread(settings["channel_id"])
        if channel is None:
            await set_rules_message(guild.id, None, None)
            return "The posted rules message's channel is gone, use `/rule post` to post them again."

        try:
            await channel.get_partial_message(settings["message_id"]).edit(view=await build_rules_view(guild.id))
        except discord.NotFound:
            await set_rules_message(guild.id, None, None)
            return "The posted rules message was deleted, use `/rule post` to post them again."
        except discord.HTTPException as e:
            logger.warning(f"Couldn't update the rules message in guild {guild.id}: {e}")
            return f"Couldn't update the posted rules message, check my permissions in {channel.mention}."
        return None

    async def _reply(self, interaction: discord.Interaction, text: str):
        """Refreshes the posted message, then confirms the change."""
        note = await self._refresh_posted(interaction.guild)
        if note:
            text += f"\n\n*{note}*"
        await interaction.followup.send(embed=success_embed(text), ephemeral=True)

    async def _rule_autocomplete(self, interaction: discord.Interaction, current: str):
        current = current.lower().lstrip("#")
        choices = []
        for n, rule in enumerate(await rules_get(interaction.guild_id), start=1):
            if current and current not in str(n) and current not in rule["title"].lower():
                continue
            # Discord rejects a choice name over 100 characters.
            name = f"#{n} | {rule['title']}"
            if len(name) > 100:
                name = name[:97] + "..."
            choices.append(app_commands.Choice(name=name, value=str(n)))
        return choices[:25]

    @app_commands.command(name="add", description="Adds a server rule")
    @app_commands.describe(
        title="Rule title, without the number",
        description="Rule text",
        position="Where to insert it, e.g. 1 for first (leave empty to add it at the end)",
    )
    async def add(
        self, interaction: discord.Interaction,
        title: app_commands.Range[str, 1, MAX_TITLE_LENGTH],
        description: app_commands.Range[str, 1, MAX_DESCRIPTION_LENGTH],
        position: Optional[app_commands.Range[int, 1, None]] = None,
    ):
        await self._check_permission(interaction, "add")
        await interaction.response.defer(ephemeral=True)

        rules = await rules_get(interaction.guild_id)
        index = len(rules) if position is None else min(position, len(rules) + 1) - 1
        planned = rules.copy()
        planned.insert(index, {"title": title, "description": description})
        _check_fits(planned, _active_footer(await get_rules_settings(interaction.guild_id)))

        await rule_add(interaction.guild_id, index + 1, title, description)
        await self._reply(interaction, f"Added rule **#{index + 1} | {title}**.")

    @app_commands.command(name="edit", description="Edits a server rule's title, description, or both")
    @app_commands.describe(
        rule="The rule to edit",
        title="New title (leave empty to keep it)",
        description="New rule text (leave empty to keep it)",
    )
    @app_commands.autocomplete(rule=_rule_autocomplete)
    async def edit(
        self, interaction: discord.Interaction, rule: str,
        title: Optional[app_commands.Range[str, 1, MAX_TITLE_LENGTH]] = None,
        description: Optional[app_commands.Range[str, 1, MAX_DESCRIPTION_LENGTH]] = None,
    ):
        await self._check_permission(interaction, "edit")
        if title is None and description is None:
            raise UserError("Give a new title, a new description, or both.")
        await interaction.response.defer(ephemeral=True)

        rules = await rules_get(interaction.guild_id)
        index = _resolve(rule, rules)
        planned = rules.copy()
        planned[index] = {
            "title": title if title is not None else rules[index]["title"],
            "description": description if description is not None else rules[index]["description"],
        }
        _check_fits(planned, _active_footer(await get_rules_settings(interaction.guild_id)))

        await rule_update(interaction.guild_id, index + 1, title, description)
        await self._reply(interaction, f"Updated rule **#{index + 1} | {planned[index]['title']}**.")

    @app_commands.command(name="delete", description="Deletes a server rule")
    @app_commands.describe(rule="The rule to delete")
    @app_commands.autocomplete(rule=_rule_autocomplete)
    async def delete(self, interaction: discord.Interaction, rule: str):
        await self._check_permission(interaction, "delete")
        await interaction.response.defer(ephemeral=True)

        rules = await rules_get(interaction.guild_id)
        index = _resolve(rule, rules)
        await rule_delete(interaction.guild_id, index + 1)
        # Full text is echoed back so the rule can be re-added.
        await self._reply(interaction, f"Deleted rule {_rule_text(index + 1, rules[index])}")

    @app_commands.command(name="move", description="Moves a server rule to another position")
    @app_commands.describe(rule="The rule to move", position="Its new number, e.g. 1 for first")
    @app_commands.autocomplete(rule=_rule_autocomplete)
    async def move(
        self, interaction: discord.Interaction, rule: str, position: app_commands.Range[int, 1, None],
    ):
        await self._check_permission(interaction, "move")
        await interaction.response.defer(ephemeral=True)

        rules = await rules_get(interaction.guild_id)
        index = _resolve(rule, rules)
        new = min(position, len(rules))
        if new == index + 1:
            raise UserError(f"That rule is already **#{new}**.")

        # A move only reorders the numbers, so the message length can't change.
        await rule_move(interaction.guild_id, index + 1, new)
        await self._reply(interaction, f"Moved **{rules[index]['title']}** from **#{index + 1}** to **#{new}**.")

    @app_commands.command(name="footer", description="Sets the rules footer text, or turns it on or off")
    @app_commands.describe(
        text="Footer text (setting it turns the footer on, unless enabled is also given)",
        enabled="Show or hide the footer, the text is kept either way",
    )
    async def footer(
        self, interaction: discord.Interaction,
        text: Optional[app_commands.Range[str, 1, MAX_FOOTER_LENGTH]] = None,
        enabled: Optional[bool] = None,
    ):
        await self._check_permission(interaction, "footer")
        if text is None and enabled is None:
            raise UserError("Give new footer text, turn it on or off, or both.")
        await interaction.response.defer(ephemeral=True)

        settings = await get_rules_settings(interaction.guild_id)
        new_text = text if text is not None else settings["footer"]
        if enabled is None:
            enabled = True if text is not None else settings["footer_enabled"]
        if enabled and not new_text:
            raise UserError("There's no footer text yet, set it with `text`.")
        if enabled:
            _check_fits(await rules_get(interaction.guild_id), new_text)

        await set_rules_footer(interaction.guild_id, new_text, enabled)
        if enabled:
            await self._reply(interaction, f"Footer is on: {new_text}")
        else:
            await self._reply(interaction, "Footer is off. Its text is kept for when it's turned back on.")

    @app_commands.command(name="color", description="Set or reset the rules message color")
    @app_commands.describe(hex_code="The hex color code (leave empty to use the server's embed color)")
    async def color(self, interaction: discord.Interaction, hex_code: Optional[str] = None):
        await self._check_permission(interaction, "color")

        if not hex_code:
            await interaction.response.defer(ephemeral=True)
            await set_rules_color(interaction.guild_id, None)
            await self._reply(interaction, "Rules color reset, it now follows the server's embed color.")
            return

        try:
            parsed = parse_hex_color(hex_code)
        except ValueError as e:
            raise UserError(str(e))

        await interaction.response.defer(ephemeral=True)
        clean_hex = f"{parsed.value:06X}"
        await set_rules_color(interaction.guild_id, clean_hex)
        await self._reply(interaction, f"Rules color set to `#{clean_hex}`.")

    @app_commands.command(name="post", description="Posts the rules message, which then updates on every rule change")
    @app_commands.describe(
        channel="Channel to post in, if not this one",
        message_id="ID of a rules message I already posted, to reuse it instead of sending a new one",
    )
    async def post(
        self, interaction: discord.Interaction,
        channel: Optional[discord.TextChannel] = None, message_id: Optional[str] = None,
    ):
        await self._check_permission(interaction, "post")
        await interaction.response.defer(ephemeral=True)

        if not await rules_get(interaction.guild_id):
            raise UserError("There are no rules to post yet, add one with `/rule add`.")

        target = channel or interaction.channel
        view = await build_rules_view(interaction.guild_id)

        if message_id is None:
            try:
                message = await target.send(view=view)
            except discord.Forbidden:
                raise UserError(f"I can't send messages in {target.mention}.")
        else:
            try:
                target_id = int(message_id)
            except ValueError:
                raise UserError("Invalid Message ID. Please enter a numeric ID.")
            try:
                message = await target.fetch_message(target_id)
            except discord.NotFound:
                raise UserError(f"That message isn't in {target.mention}. Specify which channel it's in.")
            if message.author != self.bot.user:
                raise UserError("I can only reuse my own messages.")
            await message.edit(content=None, embed=None, view=view)

        previous = await get_rules_settings(interaction.guild_id)
        await set_rules_message(interaction.guild_id, target.id, message.id)

        text = f"Rules posted at {message.jump_url}."
        if previous["message_id"] and previous["message_id"] != message.id:
            text += "\n\n*The previous rules message is no longer updated.*"
        await interaction.followup.send(embed=success_embed(text), ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Rules(bot))
    await bot.add_cog(Rule(bot))
