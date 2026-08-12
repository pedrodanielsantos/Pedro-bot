import discord

from config.constants import ERROR_COLOR, SUCCESS_COLOR


def error_embed(description: str) -> discord.Embed:
    return discord.Embed(description=description, color=ERROR_COLOR)


def success_embed(description: str) -> discord.Embed:
    return discord.Embed(description=description, color=SUCCESS_COLOR)


async def send_error(interaction: discord.Interaction, message: str, *, ephemeral: bool = True):
    """Send a standard error embed, via followup if the interaction is already responded to/deferred."""
    embed = error_embed(message)
    if interaction.response.is_done():
        await interaction.followup.send(embed=embed, ephemeral=ephemeral)
    else:
        await interaction.response.send_message(embed=embed, ephemeral=ephemeral)
