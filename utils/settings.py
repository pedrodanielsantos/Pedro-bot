import discord

# Shown wherever a setting has no stored value.
NOT_SET = "*Not set*"


def format_channel(guild: discord.Guild, channel_id: int | None) -> str:
    """A stored channel id as a mention. A channel deleted since it was configured
    still has its id shown, so the stale setting is obvious rather than silent."""
    if channel_id is None:
        return NOT_SET
    channel = guild.get_channel(channel_id)
    return channel.mention if channel else f"*Deleted channel* (`{channel_id}`)"


def format_roles(guild: discord.Guild, role_ids: list[int]) -> str:
    """Stored role ids as mentions, deleted ones included the same way."""
    if not role_ids:
        return NOT_SET
    return ", ".join(
        role.mention if (role := guild.get_role(role_id)) else f"*Deleted role* (`{role_id}`)"
        for role_id in role_ids
    )
