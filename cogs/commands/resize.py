import asyncio
import logging
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from db.database import lobby_get_lockdown, lobby_set_lockdown, lobby_lockdowns
from utils.confirm import ConfirmView
from utils.embeds import guild_embed, success_embed
from utils.errors import UserError
from utils.mixins import LobbyMixin

logger = logging.getLogger("resize")

# Lockdown states stored per lobby. PENDING holds the limit until the lobby
# fills, LOCKED shrinks the limit to the member count on every leave.
LOCKDOWN_OFF = 0
LOCKDOWN_PENDING = 1
LOCKDOWN_LOCKED = 2

# Seconds a lobby must stay full before lockdown locks, so a join and
# immediate leave doesn't lock it.
LOCKDOWN_ARM_DELAY = 10

LOCKDOWN_PROMPT_TIMEOUT = 60


def _limit_label(max_users: int) -> str:
    return "unlimited" if max_users == 0 else str(max_users)


def _is_full(channel: discord.VoiceChannel) -> bool:
    # Counts bots too, as Discord's user limit does.
    return channel.user_limit > 0 and len(channel.members) >= channel.user_limit


class LockdownPromptView(ConfirmView):
    """Asks whether a resize of a lobby in lockdown keeps lockdown on."""

    def __init__(self, cog: "Resize", channel: discord.VoiceChannel, max_users: int):
        super().__init__(
            "This lobby is in lockdown mode.",
            f"Keep lockdown on for the new limit of **{max_users}**?",
            confirm_label="Keep lockdown",
            cancel_label="Turn off",
            expired_outcome="Prompt expired, the lobby was not resized.",
            timeout=LOCKDOWN_PROMPT_TIMEOUT,
        )
        self.cog = cog
        self.channel = channel
        self.max_users = max_users

    async def _apply(self, interaction: discord.Interaction, lockdown: bool):
        # Claimed before the first API call, so a double click can't apply it twice.
        self.resolved = True
        await interaction.response.defer()
        try:
            # Keeping lockdown isn't news to the lobby, only turning it off is announced.
            await self.cog._apply_resize(
                self.channel, self.max_users, lockdown, interaction.user, announce_on=not lockdown,
            )
        except discord.NotFound:
            self.resolve("Resize failed: the lobby no longer exists.")
        except discord.Forbidden:
            self.resolve("Resize failed: I don't have permission to edit this lobby.")
        except discord.HTTPException as e:
            logger.warning(f"Resize of lobby {self.channel.id} failed: {e}")
            self.resolve("Resize failed: Discord returned an error, the lobby was not resized.")
        else:
            state = "stays on" if lockdown else "turned off"
            self.resolve(f"Lobby resized to **{self.max_users}** maximum users, lockdown {state}.")
        await interaction.edit_original_response(view=self)

    async def on_confirm(self, interaction: discord.Interaction):
        await self._apply(interaction, True)

    async def on_cancel(self, interaction: discord.Interaction):
        await self._apply(interaction, False)


class Resize(LobbyMixin, commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Serializes lockdown state changes and limit edits per lobby.
        self._locks: dict[int, asyncio.Lock] = {}
        self._arm_tasks: dict[int, asyncio.Task] = {}

    def cog_unload(self):
        for task in self._arm_tasks.values():
            task.cancel()

    def _lock(self, channel_id: int) -> asyncio.Lock:
        return self._locks.setdefault(channel_id, asyncio.Lock())

    def _cancel_arm(self, channel_id: int):
        task = self._arm_tasks.pop(channel_id, None)
        if task:
            task.cancel()

    def _schedule_arm(self, channel: discord.VoiceChannel):
        if channel.id not in self._arm_tasks:
            self._arm_tasks[channel.id] = asyncio.create_task(self._arm_after_delay(channel.id))

    async def _arm_after_delay(self, channel_id: int):
        try:
            await asyncio.sleep(LOCKDOWN_ARM_DELAY)
            async with self._lock(channel_id):
                channel = self.bot.get_channel(channel_id)
                if not isinstance(channel, discord.VoiceChannel) or not _is_full(channel):
                    return
                if await lobby_get_lockdown(channel_id) != LOCKDOWN_PENDING:
                    return
                await lobby_set_lockdown(channel_id, LOCKDOWN_LOCKED)
        finally:
            if self._arm_tasks.get(channel_id) is asyncio.current_task():
                del self._arm_tasks[channel_id]
        await self._announce_locked(channel)

    async def _announce(self, channel: discord.VoiceChannel, text: str):
        """Posts in the lobby's text chat. Sent outside the lock so a slow send doesn't hold up shrinks."""
        try:
            await channel.send(embed=await guild_embed(channel.guild.id, text))
        except discord.HTTPException as e:
            logger.warning(f"Lockdown announcement in lobby {channel.id} failed: {e}")

    async def _announce_locked(self, channel: discord.VoiceChannel):
        await self._announce(channel, "Lockdown is on. Nobody new can join, and the limit drops each time someone leaves.")

    async def _shrink(self, channel: discord.VoiceChannel):
        """Drops a locked lobby's limit to its member count. Caller holds the lock."""
        count = len(channel.members)
        # Empty lobbies are deleted by the lobby manager. A cached limit of 0 right
        # after a resize is stale, not unlimited, so it still shrinks.
        if count == 0 or 0 < channel.user_limit <= count:
            return
        try:
            await channel.edit(user_limit=count, reason="Lobby lockdown")
        except discord.NotFound:
            pass
        except discord.HTTPException as e:
            logger.warning(f"Lockdown shrink of lobby {channel.id} failed: {e}")

    async def _apply_resize(
        self, channel: discord.VoiceChannel, max_users: int, lockdown: bool, user: discord.abc.User,
        *, announce_on: bool = True,
    ):
        """announce_on=False skips the armed and locked announcements, the off one always posts."""
        async with self._lock(channel.id):
            self._cancel_arm(channel.id)
            previous = await lobby_get_lockdown(channel.id)
            await channel.edit(user_limit=max_users)
            # Checked against max_users, the cached user_limit may not be updated yet.
            # A resize that already fills the lobby locks at once, there is no join to wait out.
            if not lockdown:
                state = LOCKDOWN_OFF
            elif len(channel.members) >= max_users:
                state = LOCKDOWN_LOCKED
            else:
                state = LOCKDOWN_PENDING
            await lobby_set_lockdown(channel.id, state)

        if state != LOCKDOWN_OFF and not announce_on:
            return
        if state == LOCKDOWN_PENDING:
            await self._announce(
                channel,
                f"{user.mention} armed lockdown. Once the lobby has **{max_users}** members "
                f"for **{LOCKDOWN_ARM_DELAY}** seconds, it locks.",
            )
        elif state == LOCKDOWN_LOCKED:
            await self._announce_locked(channel)
        elif previous != LOCKDOWN_OFF:
            await self._announce(channel, f"{user.mention} turned lockdown off.")

    @app_commands.command(name="resize", description="Resize your current lobby")
    @app_commands.describe(
        max_users="Must be between 0 (unlimited) and 99",
        lockdown="Hold the limit until the lobby fills, then lower it each time someone leaves",
    )
    async def resize(self, interaction: discord.Interaction, max_users: int, lockdown: Optional[bool] = None):
        await interaction.response.defer(ephemeral=True)

        if max_users < 0 or max_users > 99:
            raise UserError("Maximum users must be between **0** (unlimited) and **99**.")
        if lockdown and max_users == 0:
            raise UserError("Lockdown needs a limit, an **unlimited** lobby never fills.")

        channel = await self._get_lobby_channel(interaction)
        current = await lobby_get_lockdown(channel.id)

        if lockdown is None and current != LOCKDOWN_OFF and max_users != 0:
            view = LockdownPromptView(self, channel, max_users)
            view.message = await interaction.followup.send(view=view, ephemeral=True)
            return

        await self._apply_resize(channel, max_users, bool(lockdown), interaction.user)

        description = f"Lobby resized to **{_limit_label(max_users)}** maximum users."
        if lockdown:
            description += " Lockdown enabled."
        elif current != LOCKDOWN_OFF:
            description += " Lockdown disabled."
        await interaction.followup.send(embed=success_embed(description), ephemeral=True)

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        if before.channel == after.channel:
            return

        if isinstance(before.channel, discord.VoiceChannel):
            channel = before.channel
            async with self._lock(channel.id):
                state = await lobby_get_lockdown(channel.id)
                if state == LOCKDOWN_LOCKED:
                    await self._shrink(channel)
                elif state == LOCKDOWN_PENDING and not _is_full(channel):
                    self._cancel_arm(channel.id)

        if isinstance(after.channel, discord.VoiceChannel):
            channel = after.channel
            async with self._lock(channel.id):
                if _is_full(channel) and await lobby_get_lockdown(channel.id) == LOCKDOWN_PENDING:
                    self._schedule_arm(channel)

    @commands.Cog.listener()
    async def on_ready(self):
        # Catches up on voice events missed while disconnected or restarting.
        for channel_id, state in await lobby_lockdowns():
            channel = self.bot.get_channel(channel_id)
            if not isinstance(channel, discord.VoiceChannel):
                continue
            async with self._lock(channel_id):
                if state == LOCKDOWN_LOCKED:
                    await self._shrink(channel)
                elif _is_full(channel):
                    self._schedule_arm(channel)

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel):
        self._cancel_arm(channel.id)
        self._locks.pop(channel.id, None)


async def setup(bot: commands.Bot):
    await bot.add_cog(Resize(bot))
