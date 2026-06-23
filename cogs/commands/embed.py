import discord
from discord import app_commands
from discord.ext import commands
import json
from config.constants import EMBED_COLOR, SUCCESS_COLOR, ERROR_COLOR
from db.database import get_embed_color

class Embed(commands.GroupCog, group_name="embed"):
    def __init__(self, bot: commands.Bot):
        super().__init__()
        self.bot = bot

    @app_commands.command(name="json", description="Get the JSON source of an embed")
    @app_commands.describe(message_id="The ID of the message containing the embed.", channel="The channel the message is in (optional).")
    async def json(self, interaction: discord.Interaction, message_id: str, channel: discord.TextChannel = None):
        try:
            msg_id = int(message_id)
        except ValueError:
            embed = discord.Embed(description="Invalid Message ID. Please enter a numeric ID.", color=ERROR_COLOR)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        target_channel = channel or interaction.channel
        message = await target_channel.fetch_message(msg_id)

        if not message.embeds:
            embed = discord.Embed(description="The specified message does not contain an embed.", color=ERROR_COLOR)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        # Parse the first embed into JSON
        embed_data = message.embeds[0].to_dict()
        json_output = json.dumps(embed_data, indent=4)

        # Determine the embed color
        db_color = await get_embed_color(interaction.guild_id)
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

    @app_commands.command(name="createjson", description="Create an embed using raw JSON")
    @app_commands.describe(data="The JSON data for the embed.", channel="The channel to send the embed to (optional)")
    async def createjson(self, interaction: discord.Interaction, data: str, channel: discord.TextChannel = None):
        try:
            embed_data = json.loads(data)
            embed = discord.Embed.from_dict(embed_data)
        except json.JSONDecodeError:
            embed = discord.Embed(description="Invalid JSON format.", color=ERROR_COLOR)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        except Exception as e:
            embed = discord.Embed(description=f"Error creating embed: {e}", color=ERROR_COLOR)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        target_channel = channel or interaction.channel
        
        await target_channel.send(embed=embed)
        confirm_embed = discord.Embed(description=f"Embed sent to {target_channel.mention}.", color=SUCCESS_COLOR)
        await interaction.response.send_message(embed=confirm_embed, ephemeral=True)

    @app_commands.command(name="editjson", description="Edit an existing embed using raw JSON")
    @app_commands.describe(message_id="The ID of the message to edit", data="The new JSON data for the embed", channel="The channel the message is in (optional)")
    async def editjson(self, interaction: discord.Interaction, message_id: str, data: str, channel: discord.TextChannel = None):
        try:
            msg_id = int(message_id)
        except ValueError:
            embed = discord.Embed(description="Invalid Message ID. Please enter a numeric ID.", color=ERROR_COLOR)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        target_channel = channel or interaction.channel
        
        message = await target_channel.fetch_message(msg_id)

        if message.author != self.bot.user:
            embed = discord.Embed(description="I can only edit my own messages.", color=ERROR_COLOR)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        try:
            embed_data = json.loads(data)
            embed = discord.Embed.from_dict(embed_data)
        except Exception as e:
            embed = discord.Embed(description=f"Invalid JSON or Embed data: {e}", color=ERROR_COLOR)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        await message.edit(embed=embed)
        confirm_embed = discord.Embed(description=f"Message {message_id} updated.", color=SUCCESS_COLOR)
        await interaction.response.send_message(embed=confirm_embed, ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(Embed(bot))