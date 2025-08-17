import discord
from discord import app_commands
from discord.ext import commands
from db.database import lobby_is_tracked
from config.constants import LOBBY_EMOJI, LOBBY_NAME

class Rename(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="rename", description="Rename your current user-created lobby.")
    @app_commands.describe(new_name="New name (without the 🎧 prefix)")
    async def rename(self, interaction: discord.Interaction, new_name: str):
        if not interaction.user.voice or not interaction.user.voice.channel:
            await interaction.response.send_message("You must be connected to a lobby voice channel.", ephemeral=True)
            return

        ch: discord.VoiceChannel = interaction.user.voice.channel
        if not lobby_is_tracked(ch.id):
            await interaction.response.send_message("This channel isn’t a user-created lobby.", ephemeral=True)
            return

        safe = new_name.strip()
        if safe.startswith(LOBBY_EMOJI):
            safe = safe.lstrip(LOBBY_EMOJI).strip()

        final = f"{LOBBY_EMOJI} {safe}" if safe else f"{LOBBY_EMOJI} Lobby"
        try:
            await ch.edit(name=final)
            await interaction.response.send_message(f"Lobby renamed to **{final}**.", ephemeral=True)
        except discord.HTTPException as e:
            await interaction.response.send_message(f"Failed to rename: {e}", ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(Rename(bot))