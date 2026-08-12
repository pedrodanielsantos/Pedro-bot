import logging
from datetime import timedelta
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands, tasks

from db.database import (
    get_guild_embed_color, get_moderation_log_channel,
    next_case_number, add_mod_case,
    temp_ban_add, temp_ban_remove, temp_bans_due,
    add_warning, get_warnings, count_warnings, get_all_warnings, clear_warnings,
)
from utils.duration import parse_duration
from config.constants import SUCCESS_COLOR, ERROR_COLOR

logger = logging.getLogger("moderation")

# Required guild permission for each subcommand. Change the value here to
# regate a command, no other code needs to change.
PERMISSIONS = {
    "ban": "administrator",
    "unban": "administrator",
    "kick": "administrator",
    "timeout": "moderate_members",
    "removetimeout": "moderate_members",
    "warn": "moderate_members",
    "warnings": "moderate_members",
    "clearwarnings": "administrator",
}

MAX_TIMEOUT_DURATION = timedelta(days=28)
WARN_TIMEOUT_DURATION = timedelta(hours=24)
WARN_TIMEOUT_THRESHOLD = 2
WARN_BAN_THRESHOLD = 3

class Moderation(commands.GroupCog, group_name="moderation"):
    def __init__(self, bot: commands.Bot):
        super().__init__()
        self.bot = bot

    async def cog_load(self):
        if not self.check_temp_bans.is_running():
            self.check_temp_bans.start()

    def cog_unload(self):
        self.check_temp_bans.cancel()

    async def _check_permission(self, interaction: discord.Interaction, command_name: str) -> bool:
        required = PERMISSIONS[command_name]
        if getattr(interaction.user.guild_permissions, required):
            return True

        label = required.replace("_", " ").title()
        embed = discord.Embed(description=f"You need the **{label}** permission to use this command.", color=ERROR_COLOR)
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return False

    async def _send_error(self, interaction: discord.Interaction, message: str, deferred: bool = False):
        embed = discord.Embed(description=message, color=ERROR_COLOR)
        if deferred:
            await interaction.followup.send(embed=embed, ephemeral=True)
        else:
            await interaction.response.send_message(embed=embed, ephemeral=True)

    async def _log_case(
        self, guild: discord.Guild, action: str, target_id: int,
        moderator_id: int, reason: str, duration: Optional[str],
    ) -> int:
        case_number = await next_case_number(guild.id)
        await add_mod_case(guild.id, case_number, action, target_id, moderator_id, reason, duration)

        channel_id = await get_moderation_log_channel(guild.id)
        if not channel_id:
            return case_number

        channel = guild.get_channel(channel_id)
        if not channel:
            return case_number

        color = await get_guild_embed_color(guild.id)
        embed = discord.Embed(title=f"{action} | Case #{case_number}", color=color)
        embed.add_field(name="Offender", value=f"<@{target_id}>", inline=False)
        embed.add_field(name="Reason", value=reason, inline=False)
        if duration:
            embed.add_field(name="Duration", value=duration, inline=False)
        embed.add_field(name="Responsible Moderator", value=f"<@{moderator_id}>", inline=False)
        embed.timestamp = discord.utils.utcnow()
        embed.set_footer(text=f"User ID: {target_id}")

        try:
            await channel.send(embed=embed)
        except (discord.Forbidden, discord.HTTPException):
            pass

        return case_number

    @app_commands.command(name="ban", description="Bans a user from the server")
    @app_commands.describe(
        user_id="The ID of the user to ban",
        reason="Reason for the ban",
        duration="How long the ban should last, e.g. 30m, 12h, 7d (leave empty for a permanent ban)",
    )
    async def ban(self, interaction: discord.Interaction, user_id: str, reason: str, duration: Optional[str] = None):
        if not await self._check_permission(interaction, "ban"):
            return

        try:
            target_id = int(user_id)
        except ValueError:
            return await self._send_error(interaction, "Invalid user ID. Please enter a numeric Discord user ID.")

        parsed_duration = None
        if duration is not None:
            try:
                parsed_duration = parse_duration(duration)
            except ValueError as e:
                return await self._send_error(interaction, str(e))

        await interaction.response.defer(ephemeral=True)

        try:
            await interaction.guild.ban(discord.Object(id=target_id), reason=reason, delete_message_seconds=0)
        except discord.NotFound:
            return await self._send_error(interaction, "That user doesn't exist.", deferred=True)
        except discord.Forbidden:
            return await self._send_error(interaction, "I don't have permission to ban that user.", deferred=True)

        if parsed_duration:
            unban_at = int((discord.utils.utcnow() + parsed_duration).timestamp())
            case_number = await self._log_case(interaction.guild, "Ban", target_id, interaction.user.id, reason, duration)
            await temp_ban_add(interaction.guild_id, target_id, unban_at, case_number)
            description = f"Banned <@{target_id}> (`{target_id}`) for `{duration}`."
        else:
            await self._log_case(interaction.guild, "Ban", target_id, interaction.user.id, reason, None)
            description = f"Banned <@{target_id}> (`{target_id}`)."

        embed = discord.Embed(description=description, color=SUCCESS_COLOR)
        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="unban", description="Unbans a user from the server")
    @app_commands.describe(user_id="The ID of the user to unban", reason="Reason for the unban")
    async def unban(self, interaction: discord.Interaction, user_id: str, reason: str):
        if not await self._check_permission(interaction, "unban"):
            return

        try:
            target_id = int(user_id)
        except ValueError:
            return await self._send_error(interaction, "Invalid user ID. Please enter a numeric Discord user ID.")

        await interaction.response.defer(ephemeral=True)

        try:
            await interaction.guild.unban(discord.Object(id=target_id), reason=reason)
        except discord.NotFound:
            return await self._send_error(interaction, "That user isn't banned.", deferred=True)
        except discord.Forbidden:
            return await self._send_error(interaction, "I don't have permission to unban that user.", deferred=True)

        await temp_ban_remove(interaction.guild_id, target_id)
        await self._log_case(interaction.guild, "Unban", target_id, interaction.user.id, reason, None)

        embed = discord.Embed(description=f"Unbanned <@{target_id}> (`{target_id}`).", color=SUCCESS_COLOR)
        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="kick", description="Kicks a member from the server")
    @app_commands.describe(member="The member to kick", reason="Reason for the kick")
    async def kick(self, interaction: discord.Interaction, member: discord.Member, reason: str):
        if not await self._check_permission(interaction, "kick"):
            return

        await interaction.response.defer(ephemeral=True)

        try:
            await member.kick(reason=reason)
        except discord.Forbidden:
            return await self._send_error(interaction, "I don't have permission to kick that member.", deferred=True)

        await self._log_case(interaction.guild, "Kick", member.id, interaction.user.id, reason, None)

        embed = discord.Embed(description=f"Kicked {member.mention} (`{member.id}`).", color=SUCCESS_COLOR)
        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="timeout", description="Times out a member")
    @app_commands.describe(
        member="The member to time out",
        reason="Reason for the timeout",
        duration="How long to time out for, e.g. 10m, 1h, 7d (max 28 days)",
    )
    async def timeout(self, interaction: discord.Interaction, member: discord.Member, reason: str, duration: str):
        if not await self._check_permission(interaction, "timeout"):
            return

        try:
            parsed_duration = parse_duration(duration)
        except ValueError as e:
            return await self._send_error(interaction, str(e))

        if parsed_duration > MAX_TIMEOUT_DURATION:
            return await self._send_error(interaction, "Timeout duration cannot exceed 28 days.")

        await interaction.response.defer(ephemeral=True)

        try:
            await member.timeout(parsed_duration, reason=reason)
        except discord.Forbidden:
            return await self._send_error(interaction, "I don't have permission to time out that member.", deferred=True)

        await self._log_case(interaction.guild, "Timeout", member.id, interaction.user.id, reason, duration)

        embed = discord.Embed(description=f"Timed out {member.mention} (`{member.id}`) for `{duration}`.", color=SUCCESS_COLOR)
        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="removetimeout", description="Removes an active timeout from a member")
    @app_commands.describe(member="The member to remove the timeout from", reason="Reason for removing the timeout")
    async def removetimeout(self, interaction: discord.Interaction, member: discord.Member, reason: str):
        if not await self._check_permission(interaction, "removetimeout"):
            return

        await interaction.response.defer(ephemeral=True)

        try:
            await member.timeout(None, reason=reason)
        except discord.Forbidden:
            return await self._send_error(interaction, "I don't have permission to remove that member's timeout.", deferred=True)

        await self._log_case(interaction.guild, "Timeout Removed", member.id, interaction.user.id, reason, None)

        embed = discord.Embed(description=f"Removed timeout from {member.mention} (`{member.id}`).", color=SUCCESS_COLOR)
        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="warn", description="Warns a member")
    @app_commands.describe(member="The member to warn", reason="Reason for the warning")
    async def warn(self, interaction: discord.Interaction, member: discord.Member, reason: str):
        if not await self._check_permission(interaction, "warn"):
            return

        await interaction.response.defer(ephemeral=True)

        case_number = await self._log_case(interaction.guild, "Warn", member.id, interaction.user.id, reason, None)
        await add_warning(interaction.guild_id, case_number, member.id, interaction.user.id, reason)
        count = await count_warnings(interaction.guild_id, member.id)

        description = f"Warned {member.mention} (`{member.id}`). This is warning **#{count}**."

        if count == WARN_TIMEOUT_THRESHOLD:
            try:
                await member.timeout(WARN_TIMEOUT_DURATION, reason="Auto: 2nd warning")
                await self._log_case(interaction.guild, "Timeout", member.id, self.bot.user.id, "Auto: 2nd warning", "24h")
                description += "\nAuto-escalation: member has been **timed out for 24h**."
            except discord.Forbidden:
                description += "\nAuto-escalation failed: I don't have permission to time out that member."
        elif count >= WARN_BAN_THRESHOLD:
            try:
                await member.ban(reason="Auto: 3rd warning", delete_message_seconds=0)
                await self._log_case(interaction.guild, "Ban", member.id, self.bot.user.id, "Auto: 3rd warning", None)
                description += "\nAuto-escalation: member has been **banned**."
            except discord.Forbidden:
                description += "\nAuto-escalation failed: I don't have permission to ban that member."

        embed = discord.Embed(description=description, color=SUCCESS_COLOR)
        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="warnings", description="Lists warnings for a member, or every member currently in the server")
    @app_commands.describe(member="Leave empty to list warnings for every member currently in the server")
    async def warnings(self, interaction: discord.Interaction, member: Optional[discord.Member] = None):
        if not await self._check_permission(interaction, "warnings"):
            return

        await interaction.response.defer(ephemeral=True)

        if member is not None:
            rows = await get_warnings(interaction.guild_id, member.id)
            if not rows:
                return await self._send_error(interaction, f"{member.mention} has no warnings.", deferred=True)

            lines = [f"`#{case}` <t:{created_at}:R> by <@{mod_id}>: {reason}" for case, mod_id, reason, created_at in rows]
            embed = discord.Embed(
                title=f"Warnings for {member}",
                description="\n".join(lines),
                color=await get_guild_embed_color(interaction.guild_id),
            )
            return await interaction.followup.send(embed=embed, ephemeral=True)

        rows = await get_all_warnings(interaction.guild_id)
        member_ids = {m.id for m in interaction.guild.members}

        grouped: dict[int, list] = {}
        for case, target_id, mod_id, reason, created_at in rows:
            if target_id not in member_ids:
                continue
            grouped.setdefault(target_id, []).append((case, mod_id, reason, created_at))

        if not grouped:
            return await self._send_error(interaction, "No members currently in the server have any warnings.", deferred=True)

        lines = [f"<@{target_id}>: **{len(entries)}** warning(s)" for target_id, entries in grouped.items()]
        embed = discord.Embed(
            title="Warnings",
            description="\n".join(lines),
            color=await get_guild_embed_color(interaction.guild_id),
        )
        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="clearwarnings", description="Clears every warning for a member")
    @app_commands.describe(member="The member whose warnings should be cleared")
    async def clearwarnings(self, interaction: discord.Interaction, member: discord.Member):
        if not await self._check_permission(interaction, "clearwarnings"):
            return

        await interaction.response.defer(ephemeral=True)

        count = await count_warnings(interaction.guild_id, member.id)
        if count == 0:
            return await self._send_error(interaction, f"{member.mention} has no warnings to clear.", deferred=True)

        await clear_warnings(interaction.guild_id, member.id)
        await self._log_case(interaction.guild, "Warnings Cleared", member.id, interaction.user.id, f"Cleared {count} warning(s)", None)

        embed = discord.Embed(description=f"Cleared **{count}** warning(s) for {member.mention}.", color=SUCCESS_COLOR)
        await interaction.followup.send(embed=embed, ephemeral=True)

    @tasks.loop(seconds=60)
    async def check_temp_bans(self):
        # Guards against ticking before the guild cache is populated: is_ready()
        # is a plain attribute check, safe even before login (unlike
        # wait_until_ready(), which would raise if called this early during
        # the very first cog_load, since bot.start() hasn't run yet at that point).
        if not self.bot.is_ready():
            return

        now_ts = int(discord.utils.utcnow().timestamp())
        for guild_id, user_id, case_number in await temp_bans_due(now_ts):
            # Isolated per row: tasks.loop only auto-retries on network errors, so any
            # other unhandled exception here would kill the loop permanently and silently.
            try:
                await temp_ban_remove(guild_id, user_id)

                guild = self.bot.get_guild(guild_id)
                if not guild:
                    continue

                try:
                    await guild.unban(discord.Object(id=user_id), reason="Temporary ban expired")
                except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                    continue

                await self._log_case(guild, "Unban", user_id, self.bot.user.id, "Temporary ban expired", None)
            except Exception:
                logger.exception(f"Failed to process expired temp ban for user {user_id} in guild {guild_id}")

    @check_temp_bans.error
    async def check_temp_bans_error(self, error: BaseException):
        logger.exception("check_temp_bans loop crashed", exc_info=error)

async def setup(bot: commands.Bot):
    await bot.add_cog(Moderation(bot))
