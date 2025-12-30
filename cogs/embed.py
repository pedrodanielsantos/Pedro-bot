import discord
from discord import app_commands
from discord.ext import commands
import json
from config.constants import EMBED_COLOR
from db.database import get_embed_color

class Embed(commands.GroupCog, name="embed"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        super().__init__()

    @app_commands.command(name="source", description="Get the JSON source of an embed.")
    @app_commands.describe(message_id="The ID of the message containing the embed.")
    async def source(self, interaction: discord.Interaction, message_id: str):
        try:
            msg_id = int(message_id)
        except ValueError:
            await interaction.response.send_message("Invalid Message ID. Please enter a numeric ID.", ephemeral=True)
            return

        if not interaction.channel:
            await interaction.response.send_message("Cannot fetch messages in this context.", ephemeral=True)
            return

        try:
            message = await interaction.channel.fetch_message(msg_id)
        except discord.NotFound:
            await interaction.response.send_message("Message not found in this channel.", ephemeral=True)
            return
        except discord.Forbidden:
            await interaction.response.send_message("I don't have permission to read messages in this channel.", ephemeral=True)
            return
        except discord.HTTPException:
            await interaction.response.send_message("Failed to fetch the message.", ephemeral=True)
            return

        if not message.embeds:
            await interaction.response.send_message("The specified message does not contain an embed.", ephemeral=True)
            return

        # Parse the first embed into JSON
        embed_data = message.embeds[0].to_dict()
        json_output = json.dumps(embed_data, indent=4)

        # Determine the embed color
        db_color = get_embed_color(interaction.guild_id)
        if db_color:
            color = discord.Color(int(db_color, 16))
        else:
            color = discord.Color(EMBED_COLOR)

        # Create the response embed
        embed = discord.Embed(
            title="Embed Source",
            description=f"```json\n{json_output}\n```",
            color=color
        )

        await interaction.response.send_message(embed=embed)

async def setup(bot: commands.Bot):
    await bot.add_cog(Embed(bot))