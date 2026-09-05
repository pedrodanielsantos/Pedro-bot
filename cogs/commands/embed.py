import discord
from discord import app_commands
from discord.ext import commands
import io
import json
from typing import Optional
from utils.embeds import success_embed
from utils.errors import UserError
from utils.permissions import permission_label, require_permission, visibility_gate

MESSAGE_NOT_FOUND = "That message isn't in this channel. Specify which channel it's in."
NO_CHANNEL_ACCESS = "You don't have access to that channel."

CHANNEL_PERMISSIONS = {
    "json": ("read_message_history",),
    "createjson": ("send_messages",),
    "editjson": ("read_message_history", "send_messages"),
}

@visibility_gate("manage_guild")
class Embed(commands.GroupCog, group_name="embed"):
    def __init__(self, bot: commands.Bot):
        super().__init__()
        self.bot = bot

    def _resolve_channel(
        self,
        interaction: discord.Interaction,
        channel: Optional[discord.TextChannel],
        command_name: str,
    ) -> discord.TextChannel:
        """Returns the target channel, refusing one the invoker couldn't use themselves."""
        target_channel = channel or interaction.channel
        permissions = target_channel.permissions_for(interaction.user)

        # Reports vaguely if user somehow manages to select a private channel.
        if not permissions.view_channel:
            raise UserError(NO_CHANNEL_ACCESS)

        missing = [name for name in CHANNEL_PERMISSIONS[command_name] if not getattr(permissions, name)]
        if missing:
            labels = ", ".join(f"**{permission_label(name)}**" for name in missing)
            raise UserError(f"You need {labels} in {target_channel.mention} to use this command.")

        return target_channel

    async def _resolve_message(
        self,
        interaction: discord.Interaction,
        channel: Optional[discord.TextChannel],
        message_id: str,
        command_name: str,
    ) -> discord.Message:
        try:
            msg_id = int(message_id)
        except ValueError:
            raise UserError("Invalid Message ID. Please enter a numeric ID.")

        target_channel = self._resolve_channel(interaction, channel, command_name)
        try:
            return await target_channel.fetch_message(msg_id)
        except discord.NotFound:
            raise UserError(MESSAGE_NOT_FOUND)

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
        await require_permission(interaction, "manage_guild")

        message = await self._resolve_message(interaction, channel, message_id, "json")

        if not message.embeds:
            raise UserError("The specified message does not contain an embed.")

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
        await require_permission(interaction, "manage_guild")

        target_channel = self._resolve_channel(interaction, channel, "createjson")

        embed, error = self._parse_embed_json(data)
        if error:
            raise UserError(error)

        await target_channel.send(embed=embed)
        confirm_embed = success_embed(f"Embed sent to {target_channel.mention}.")
        await interaction.response.send_message(embed=confirm_embed, ephemeral=True)

    @app_commands.command(name="editjson", description="Edit an existing embed using raw JSON")
    @app_commands.describe(message_id="ID of the message to edit", data="New JSON data for the embed", channel="Channel the message is in, if not this one")
    async def editjson(self, interaction: discord.Interaction, message_id: str, data: str, channel: Optional[discord.TextChannel] = None):
        await require_permission(interaction, "manage_guild")

        message = await self._resolve_message(interaction, channel, message_id, "editjson")

        if message.author != self.bot.user:
            raise UserError("I can only edit my own messages.")

        embed, error = self._parse_embed_json(data)
        if error:
            raise UserError(error)

        await message.edit(embed=embed)
        confirm_embed = success_embed(f"Message {message_id} updated.")
        await interaction.response.send_message(embed=confirm_embed, ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(Embed(bot))
