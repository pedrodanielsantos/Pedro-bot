import discord
from discord import app_commands
from discord.ext import commands
from db.database import get_guild_embed_color, add_autorole, remove_autorole, get_autoroles
from utils.embeds import success_embed
from utils.errors import UserError
from utils.permissions import require_permission, visibility_gate

@visibility_gate("manage_roles")
class Autorole(commands.GroupCog, group_name="autorole"):
    def __init__(self, bot: commands.Bot):
        super().__init__()
        self.bot = bot

    async def get_color(self, guild_id: int) -> discord.Color:
        """Helper method to fetch the server's configured embed color."""
        return await get_guild_embed_color(guild_id)

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        """Automatically assigns configured autoroles to new members."""
        if member.bot:
            return
            
        role_ids = await get_autoroles(member.guild.id)
        if not role_ids:
            return
            
        roles_to_add = []
        for role_id in role_ids:
            role = member.guild.get_role(role_id)
            if role:
                roles_to_add.append(role)
                
        if roles_to_add:
            try:
                await member.add_roles(*roles_to_add, reason="Autorole")
            except discord.HTTPException:
                pass

    @app_commands.command(name="add", description="Adds a role to be automatically given to new members")
    @app_commands.describe(role="The role to add to the autorole list")
    async def add(self, interaction: discord.Interaction, role: discord.Role):
        """Adds an autorole to the database."""
        await require_permission(interaction, "manage_roles")
        await add_autorole(interaction.guild_id, role.id)

        embed = success_embed(f"Successfully added {role.mention} to the autorole list.")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="remove", description="Removes a role from the autorole list")
    @app_commands.describe(role="The role to remove from the autorole list")
    async def remove(self, interaction: discord.Interaction, role: discord.Role):
        """Removes an autorole from the database."""
        await require_permission(interaction, "manage_roles")
        await remove_autorole(interaction.guild_id, role.id)

        embed = success_embed(f"Successfully removed {role.mention} from the autorole list.")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="list", description="Lists all currently configured autoroles")
    async def list(self, interaction: discord.Interaction):
        """Lists all configured autoroles for the guild."""
        await require_permission(interaction, "manage_roles")
        role_ids = await get_autoroles(interaction.guild_id)
        color = await self.get_color(interaction.guild_id)

        # Handle case where no roles are configured
        if not role_ids:
            raise UserError("There are currently no autoroles configured for this server.")

        # Format the role IDs into pingable mentions for readability
        roles_formatted = "\n".join([f"• <@&{role_id}>" for role_id in role_ids])
        
        embed = discord.Embed(
            title="Configured Autoroles",
            description=roles_formatted,
            color=color
        )
        await interaction.response.send_message(embed=embed)

async def setup(bot: commands.Bot):
    await bot.add_cog(Autorole(bot))