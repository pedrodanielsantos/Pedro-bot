import discord
from discord import app_commands
from discord.ext import commands
import io
import json
from typing import Optional
from config.constants import SUCCESS_COLOR, ERROR_COLOR

MESSAGE_NOT_FOUND = "That message isn't in this channel. Specify which channel it's in."

class Embed(commands.GroupCog, group_name="embed"):
    def __init__(self, bot: commands.Bot):
        super().__init__()
        self.bot = bot

    async def _send_error(self, interaction: discord.Interaction, message: str):
        embed = discord.Embed(description=message, color=ERROR_COLOR)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    async def _resolve_message(
        self,
        interaction: discord.Interaction,
        channel: Optional[discord.TextChannel],
        message_id: str,
    ) -> Optional[discord.Message]:
        try:
            msg_id = int(message_id)
        except ValueError:
            await self._send_error(interaction, "Invalid Message ID. Please enter a numeric ID.")
            return None

        target_channel = channel or interaction.channel
        try:
            return await target_channel.fetch_message(msg_id)
        except discord.NotFound:
            await self._send_error(interaction, MESSAGE_NOT_FOUND)
            return None

    def _parse_embed_json(self, data: str) -> tuple[Optional[discord.Embed], Optional[str]]:
        try:
            embed_data = json.loads(data, strict=False)
            return discord.Embed.from_dict(embed_data), None
        except json.JSONDecodeError:
            return None, "Invalid JSON format."
        except Exception as e:
            return None, f"Invalid JSON or Embed data: {e}"

    @app_commands.command(name="json", description="Get the JSON source of an embed")
    @app_commands.describe(message_id="ID of the message containing the embed", channel="Channel the message is in, if not this one")
    async def json(self, interaction: discord.Interaction, message_id: str, channel: Optional[discord.TextChannel] = None):
        message = await self._resolve_message(interaction, channel, message_id)
        if message is None:
            return

        if not message.embeds:
            await self._send_error(interaction, "The specified message does not contain an embed.")
            return

        embed_data = message.embeds[0].to_dict()
        json_output = json.dumps(embed_data, indent=4)

        # Sent as a file to avoid the embed description length limit and code-block escaping issues.
        file = discord.File(
            io.BytesIO(json_output.encode("utf-8")),
            filename=f"{message.id}.json"
        )
        await interaction.response.send_message(file=file)

    @app_commands.command(name="createjson", description="Create an embed using raw JSON")
    @app_commands.describe(data="JSON data for the embed", channel="Channel to send the embed to, if not this one")
    async def createjson(self, interaction: discord.Interaction, data: str, channel: Optional[discord.TextChannel] = None):
        embed, error = self._parse_embed_json(data)
        if error:
            await self._send_error(interaction, error)
            return

        target_channel = channel or interaction.channel
        await target_channel.send(embed=embed)
        confirm_embed = discord.Embed(description=f"Embed sent to {target_channel.mention}.", color=SUCCESS_COLOR)
        await interaction.response.send_message(embed=confirm_embed, ephemeral=True)

    @app_commands.command(name="editjson", description="Edit an existing embed using raw JSON")
    @app_commands.describe(message_id="ID of the message to edit", data="New JSON data for the embed", channel="Channel the message is in, if not this one")
    async def editjson(self, interaction: discord.Interaction, message_id: str, data: str, channel: Optional[discord.TextChannel] = None):
        message = await self._resolve_message(interaction, channel, message_id)
        if message is None:
            return

        if message.author != self.bot.user:
            await self._send_error(interaction, "I can only edit my own messages.")
            return

        embed, error = self._parse_embed_json(data)
        if error:
            await self._send_error(interaction, error)
            return

        await message.edit(embed=embed)
        confirm_embed = discord.Embed(description=f"Message {message_id} updated.", color=SUCCESS_COLOR)
        await interaction.response.send_message(embed=confirm_embed, ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(Embed(bot))
