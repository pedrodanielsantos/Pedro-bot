import discord
from discord import app_commands
from discord.ext import commands
from db.database import lobby_is_tracked

class Resize(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="resize", description="Set max users for your current user-created lobby.")
    @app_commands.describe(max_users="0 for unlimited (Discord max typically 99)")
    async def resize(self, interaction: discord.Interaction, max_users: int):
        if max_users < 0 or max_users > 99:
            await interaction.response.send_message("Max users must be between **0** and **99**.", ephemeral=True)
            return

        if not interaction.user.voice or not interaction.user.voice.channel:
            await interaction.response.send_message("You must be connected to a lobby voice channel.", ephemeral=True)
            return

        ch: discord.VoiceChannel = interaction.user.voice.channel
        if not lobby_is_tracked(ch.id):
            await interaction.response.send_message("This channel isn’t a user-created lobby.", ephemeral=True)
            return

        try:
            await ch.edit(user_limit=max_users)
            label = "unlimited" if max_users == 0 else str(max_users)
            await interaction.response.send_message(f"Lobby size set to **{label}**.", ephemeral=True)
        except discord.HTTPException as e:
            await interaction.response.send_message(f"Failed to resize: {e}", ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(Resize(bot))