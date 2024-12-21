import discord
from discord import app_commands, Interaction
from discord.ext import commands
from db.database import store_user_role, remove_user_role, get_user_role

def validate_hex_code(hex_code: str) -> discord.Color:
    """Validate and convert a HEX code into a discord.Color object."""
    if not hex_code.startswith("#"):
        hex_code = f"#{hex_code}"
    if len(hex_code) != 7 or not all(c in "0123456789ABCDEFabcdef#" for c in hex_code):
        raise ValueError("Invalid HEX color code! Use a format like `#FF5733` or `FF5733`.")
    return discord.Color(int(hex_code[1:], 16))

class CustomRole(commands.GroupCog, name="customrole"):
    """Group of commands for managing custom roles."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        super().__init__()

    @app_commands.command(name="create", description="Create a custom role with a specific HEX color code.")
    @app_commands.describe(name="The name of the role.", hex_code="HEX color code for the role (e.g., #FF5733 or FF5733).")
    async def create(self, interaction: Interaction, name: str, hex_code: str):
        """Create a custom role."""
        await interaction.response.defer(ephemeral=True)

        try:
            color = validate_hex_code(hex_code)
        except ValueError as e:
            await interaction.followup.send(str(e))
            return

        guild = interaction.guild
        user = interaction.user

        # Check if user already has a custom role
        role_id = get_user_role(guild.id, user.id)
        role = guild.get_role(role_id) if role_id else None

        if role:
            # User already has a role, prevent creating a new one
            await interaction.followup.send(
                "You already have a custom role. Please use `/customrole update` to make changes "
                "or `/customrole delete` to remove your role."
            )
            return

        # Create new role
        role = await guild.create_role(name=name, color=color)

        # Place the role directly below the bot's highest role
        bot_top_role = guild.get_member(self.bot.user.id).top_role
        try:
            await guild.edit_role_positions({role: bot_top_role.position})
        except discord.Forbidden:
            await interaction.followup.send("I don't have permission to move roles. Please check my role hierarchy.")
            return

        # Assign the role to the user
        await user.add_roles(role)
        store_user_role(guild.id, user.id, role.id)
        await interaction.followup.send(f"Role **{name}** created with color **{hex_code}** and assigned to you!")

    @app_commands.command(name="update", description="Update your custom role's name or color.")
    @app_commands.describe(name="The new name for the role.", hex_code="The new HEX color code for the role.")
    async def update(self, interaction: Interaction, name: str = None, hex_code: str = None):
        """Update an existing custom role."""
        await interaction.response.defer(ephemeral=True)

        guild = interaction.guild
        user = interaction.user

        # Check if user has a custom role
        role_id = get_user_role(guild.id, user.id)
        role = guild.get_role(role_id) if role_id else None

        if not role:
            await interaction.followup.send("You don't have a custom role to update. Use `/customrole create` to create one.")
            return

        updates = {}
        if name:
            updates["name"] = name
        if hex_code:
            try:
                updates["color"] = validate_hex_code(hex_code)
            except ValueError as e:
                await interaction.followup.send(str(e))
                return

        if not updates:
            await interaction.followup.send("No updates provided. Please specify a new name or color.")
            return

        await role.edit(**updates)
        update_msg = f"Your role has been updated with the {' and '.join(f'{key} **{value}**' for key, value in updates.items())}."
        await interaction.followup.send(update_msg)

    @app_commands.command(name="delete", description="Delete your own custom role.")
    async def delete(self, interaction: Interaction):
        """Delete a user's custom role."""
        await interaction.response.defer(ephemeral=True)

        guild = interaction.guild
        user = interaction.user

        # Check if user has a custom role
        role_id = get_user_role(guild.id, user.id)
        role = guild.get_role(role_id) if role_id else None

        if role:
            await role.delete(reason="User deleted their custom role")
            remove_user_role(guild.id, user.id)
            await interaction.followup.send("Your custom role has been successfully deleted.")
        else:
            await interaction.followup.send("You do not have a custom role to delete.")

    @app_commands.command(name="deleteid", description="Delete a custom role by User ID (Admin only).")
    @app_commands.describe(user_id="The ID of the user whose role you want to delete.")
    @app_commands.checks.has_permissions(administrator=True)
    async def deleteid(self, interaction: Interaction, user_id: str):
        """Delete a custom role for a specific user (admin only)."""
        await interaction.response.defer(ephemeral=True)

        guild = interaction.guild

        try:
            user_id = int(user_id)
        except ValueError:
            await interaction.followup.send("Invalid User ID! Please provide a valid numeric User ID.")
            return

        role_id = get_user_role(guild.id, user_id)
        role = guild.get_role(role_id) if role_id else None

        if role:
            await role.delete(reason="Deleted by administrator")
            remove_user_role(guild.id, user_id)
            await interaction.followup.send(f"Role for user ID `{user_id}` has been successfully deleted.")
        else:
            await interaction.followup.send(f"No custom role found for user ID `{user_id}`.")

async def setup(bot: commands.Bot):
    """Register the CustomRole command group."""
    await bot.add_cog(CustomRole(bot))