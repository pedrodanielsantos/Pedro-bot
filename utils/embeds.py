import discord

from config.constants import ERROR_COLOR, SUCCESS_COLOR
from db.database import get_guild_embed_color


def error_embed(description: str) -> discord.Embed:
    return discord.Embed(description=description, color=ERROR_COLOR)


def success_embed(description: str) -> discord.Embed:
    return discord.Embed(description=description, color=SUCCESS_COLOR)


async def guild_embed(guild_id: int, description: str) -> discord.Embed:
    """A plain embed in the guild's configured color."""
    return discord.Embed(description=description, color=await get_guild_embed_color(guild_id))


async def send_error(interaction: discord.Interaction, message: str, *, ephemeral: bool = True):
    """Send a standard error embed, via followup if the interaction is already responded to/deferred."""
    embed = error_embed(message)
    try:
        if interaction.response.is_done():
            await interaction.followup.send(embed=embed, ephemeral=ephemeral)
        else:
            await interaction.response.send_message(embed=embed, ephemeral=ephemeral)
    except discord.HTTPException:
        # This is the error handler's last step, so it must not raise: a failure
        # here logs a second traceback pointing at the reporting rather than at
        # whatever actually failed. Usually an interaction expired past Discord's
        # three second window and can no longer be replied to at all.
        pass
