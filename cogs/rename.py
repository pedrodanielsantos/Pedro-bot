import discord
from discord import app_commands
from discord.ext import commands
from db.database import lobby_is_tracked
from config.constants import LOBBY_EMOJI, LOBBY_NAME, LOBBY_NAME_MAX_LENGTH

class Rename(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="rename", description="Rename your current lobby.")
    @app_commands.describe(new_name="New name for the lobby.")
    async def rename(self, interaction: discord.Interaction, new_name: str):
        
        await interaction.response.defer(ephemeral=True)

        if not interaction.user.voice or not interaction.user.voice.channel:
            await interaction.response.send_message("You must be connected to a lobby.", ephemeral=True)
            return

        ch: discord.VoiceChannel = interaction.user.voice.channel
        if not lobby_is_tracked(ch.id):
            await interaction.response.send_message("This channel isn’t a user-created lobby.", ephemeral=True)
            return

        name = new_name.strip()
        final = f"{LOBBY_EMOJI} {name}"

        if len(final) > LOBBY_NAME_MAX_LENGTH:
            await interaction.followup.send(
                f"Name too long ({len(final)}/{LOBBY_NAME_MAX_LENGTH}).", ephemeral=True
            )
            return
        
        try:
            await ch.edit(name=final, reason=f"Lobby rename by {interaction.user}")
            await interaction.followup.send(f"Lobby renamed to **{name}**.", ephemeral=True)

        except discord.HTTPException as e:
            # Proper rate-limit surface (HTTP 429)
            if getattr(e, "status", None) == 429:
                retry_after_hdr = None
                try:
                    retry_after_hdr = e.response.headers.get("Retry-After")
                except Exception:
                    pass

                if retry_after_hdr:
                    retry_after = float(retry_after_hdr)
                    await interaction.followup.send(
                        f"Rate limited. Please try again in ~{retry_after:.1f}s.",
                        ephemeral=True
                    )
                else:
                    await interaction.followup.send(
                        "Rate limited. Please wait a moment and try again.",
                        ephemeral=True
                    )
                return

            if isinstance(e, discord.Forbidden):
                await interaction.followup.send("I don’t have permission to rename this channel.", ephemeral=True)
            else:
                await interaction.followup.send(f"Failed to rename: {e}", ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(Rename(bot))