import discord

from utils.errors import UserError


async def require_permission(interaction: discord.Interaction, permission: str):
    """Raises UserError unless interaction.user has the given guild permission."""
    guild_permissions = getattr(interaction.user, "guild_permissions", None)
    if guild_permissions and getattr(guild_permissions, permission):
        return

    label = permission.replace("_", " ").title()
    raise UserError(f"You need the **{label}** permission to use this command.")
