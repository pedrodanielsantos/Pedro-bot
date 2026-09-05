from typing import Optional

import discord
from discord import app_commands

from utils.errors import UserError

# Guild permissions used to gate commands, ordered from least to most privileged.
PRIVILEGE_ORDER = (
    "moderate_members",
    "manage_roles",
    "manage_channels",
    "manage_guild",
    "administrator",
)

# Permissions whose API name doesn't match the label Discord shows in role
# settings. Anything else is title-cased and already matches.
PERMISSION_LABELS = {
    "moderate_members": "Timeout Members",
    "manage_guild": "Manage Server",
}


def permission_label(permission: str) -> str:
    """The name a member sees on the permission in role and channel settings."""
    return PERMISSION_LABELS.get(permission, permission.replace("_", " ").title())


async def require_permission(interaction: discord.Interaction, permission: str):
    """Raises UserError unless interaction.user has the given guild permission."""
    guild_permissions = getattr(interaction.user, "guild_permissions", None)
    if guild_permissions and getattr(guild_permissions, permission):
        return

    raise UserError(f"You need the **{permission_label(permission)}** permission to use this command.")


def visibility_gate(*permissions: str):
    """Hides a command from members who can't use it, in the command picker and
    in /help. Discord only supports this per top-level command, so a group is
    gated by its least privileged subcommand and every command still checks its
    own permission at runtime. It's a default a server can override."""
    weakest = min(permissions, key=PRIVILEGE_ORDER.index)
    return app_commands.default_permissions(**{weakest: True})


def required_permissions(command: app_commands.Command) -> Optional[discord.Permissions]:
    """The gate applied to a command, taken from its group when it has none itself."""
    node = command
    while node is not None:
        if node.default_permissions is not None:
            return node.default_permissions
        node = node.parent
    return None


def is_visible_to(user, command: app_commands.Command) -> bool:
    """Whether a member passes a command's gate. Mirrors the command picker,
    except for per-server overrides, which the bot can't read."""
    required = required_permissions(command)
    if required is None:
        return True

    guild_permissions = getattr(user, "guild_permissions", None)
    return guild_permissions is not None and guild_permissions.is_superset(required)
