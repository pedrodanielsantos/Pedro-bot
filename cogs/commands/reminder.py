import asyncio
import logging
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import discord
from discord import app_commands
from discord.ext import commands

from db.database import (
    get_guild_embed_color, reminder_add, reminder_get, reminders_for_user, reminder_count,
    reminder_next_due, reminders_due, reminder_reschedule, reminder_set_repeat,
    reminder_delete, reminders_clear,
)
from utils.confirm import ConfirmView
from utils.duration import format_duration, format_duration_long
from utils.embeds import guild_embed
from utils.errors import UserError
from utils.paginator import TEXT_DISPLAY_LIMIT, PaginatorView, chunk_text
from utils.text import plural
from utils.timeinput import UNIT_CHOICES, parse_local_datetime, parse_zone, timezone_autocomplete

logger = logging.getLogger("reminder")

# Per user per guild. Matches Discord's 25 autocomplete choices, so
# the reminder pickers can always list every reminder.
MAX_REMINDERS = 25
MAX_CONTENT_LENGTH = 1000
MAX_AHEAD = timedelta(days=5 * 365)

# Longest single scheduler sleep. Bounds how long a wall clock change goes unnoticed.
MAX_SLEEP = 3600
RETRY_DELAY = 30

# A reminder sent this many seconds or more past due is marked as late.
LATE_THRESHOLD = 60

CLEAR_PROMPT_TIMEOUT = 60

IN_UNIT_CHOICES = [app_commands.Choice(name="Seconds", value="seconds"), *UNIT_CHOICES]


def _next_due(reminder: dict, after: int) -> int:
    """First occurrence of a repeating reminder strictly after the given timestamp.

    Whole-day intervals on /reminder at reminders step in the stored timezone's
    wall time, so a daily reminder keeps its local time across DST changes.
    Missed occurrences are skipped, not replayed.
    """
    interval = reminder["repeat_interval"]
    due = reminder["due_at"]
    skipped = max(0, (after - due) // interval)

    if reminder["timezone"] and interval % 86400 == 0:
        step = timedelta(seconds=interval)
        local = datetime.fromtimestamp(due, ZoneInfo(reminder["timezone"])) + step * skipped
        while local.timestamp() <= after:
            local += step
        return int(local.timestamp())

    due += skipped * interval
    while due <= after:
        due += interval
    return due


def _now() -> int:
    # Rounded, not floored, so a 10s reminder set at x.9 isn't stored 0.9s early.
    return round(time.time())


def _remaining(reminder: dict) -> str:
    return format_duration(timedelta(seconds=max(0, reminder["due_at"] - _now())))


def _short(text: str, limit: int) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[:limit - 3] + "..."


def _repeat_label(reminder: dict) -> str:
    label = f"every **{format_duration(timedelta(seconds=reminder['repeat_interval']))}**"
    if reminder["timezone"] and reminder["repeat_interval"] % 86400 == 0:
        label += f" ({reminder['timezone']} time)"
    return label


async def _reminder_embed(reminder: dict, lead: str, notes: list[str] = ()) -> discord.Embed:
    """Lead line, content, then any notes, in the guild's embed color."""
    lines = [lead, reminder["content"]]
    if notes:
        lines += ["", *notes]
    return await guild_embed(reminder["guild_id"], "\n".join(lines))


async def _upcoming_embed(reminder: dict, verb: str) -> discord.Embed:
    """Pending reminder, as shown on creation ("set for") and by /reminder when ("is due").

    Remaining time is fixed at build time, since a relative tag rounds to one unit.
    """
    notes = [f"*Repeats {_repeat_label(reminder)}.*"] if reminder["repeat_interval"] else []
    lead = f"Reminder **#{reminder['id']}** {verb} <t:{reminder['due_at']}:F> (in {_remaining(reminder)})."
    return await _reminder_embed(reminder, lead, notes)


class ClearRemindersView(ConfirmView):
    def __init__(self, guild_id: int, user_id: int, count: int):
        super().__init__(
            "Clear reminders",
            f"Delete all **{count}** of your {plural(count, 'reminder')} in this server?",
            confirm_label="Clear",
            cancel_label="Cancel",
            expired_outcome="Prompt expired, no reminders were deleted.",
            timeout=CLEAR_PROMPT_TIMEOUT,
        )
        self.guild_id = guild_id
        self.user_id = user_id

    async def on_confirm(self, interaction: discord.Interaction):
        # Claimed before the first await, so a double click can't run it twice.
        self.resolved = True
        deleted = await reminders_clear(self.guild_id, self.user_id)
        self.resolve(f"Deleted **{deleted}** {plural(deleted, 'reminder')}.")
        await interaction.response.edit_message(view=self)

    async def on_cancel(self, interaction: discord.Interaction):
        self.resolve("Cancelled, your reminders were kept.")
        await interaction.response.edit_message(view=self)


@app_commands.guild_only()
class Reminder(commands.GroupCog, group_name="reminder"):
    def __init__(self, bot: commands.Bot):
        super().__init__()
        self.bot = bot
        self._wake = asyncio.Event()
        self._task: asyncio.Task | None = None

    async def cog_load(self):
        self._task = asyncio.create_task(self._run_scheduler())

    def cog_unload(self):
        if self._task:
            self._task.cancel()

    # Scheduler

    async def _run_scheduler(self):
        # is_ready() is safe before login, unlike wait_until_ready().
        while not self.bot.is_ready():
            await asyncio.sleep(1)

        while True:
            try:
                await self._tick()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception(f"Reminder scheduler failed, retrying in {RETRY_DELAY}s")
                await asyncio.sleep(RETRY_DELAY)

    async def _tick(self):
        """Sleeps until the earliest reminder is due, or until woken by a new one."""
        # Cleared before the query, so a wake set after it isn't lost.
        self._wake.clear()
        next_due = await reminder_next_due()

        if next_due is None:
            await self._wake.wait()
            return

        delay = next_due - time.time()
        if delay > 0:
            try:
                await asyncio.wait_for(self._wake.wait(), timeout=min(delay, MAX_SLEEP))
            except asyncio.TimeoutError:
                pass
            return

        for reminder in await reminders_due(int(time.time())):
            # Isolated per row, so one failure doesn't hold back the rest.
            try:
                await self._fire(reminder)
            except Exception:
                logger.exception(f"Failed to fire reminder {reminder['id']}")

    def _wake_scheduler(self):
        self._wake.set()

    async def _fire(self, reminder: dict):
        now = int(time.time())
        late = now - reminder["due_at"] >= LATE_THRESHOLD

        # Rescheduled or deleted before sending, so a failed send can't refire in a loop.
        # A missing row was deleted by its owner after reminders_due() read it.
        next_due = None
        if reminder["repeat_interval"]:
            next_due = _next_due(reminder, now)
            if not await reminder_reschedule(reminder["id"], next_due):
                return
        elif not await reminder_delete(reminder["id"]):
            return

        notes = []
        if late:
            notes.append(f"*Due <t:{reminder['due_at']}:R>, sent late while I was offline.*")
        if next_due:
            notes.append(f"*Repeats {_repeat_label(reminder)}, next <t:{next_due}:R>.*")
        ago = format_duration_long(timedelta(seconds=max(1, now - reminder["created_at"])))
        content = reminder["content"]
        # No added period when the text already ends in punctuation.
        end = "" if content.endswith((".", "!", "?")) else "."
        lines = [f'{ago[0].upper()}{ago[1:]} ago you asked to be reminded of "{content}{end}"']
        if notes:
            lines += ["", *notes]
        embed = discord.Embed(
            title=f"Reminder #{reminder['id']}", description="\n".join(lines),
            color=await get_guild_embed_color(reminder["guild_id"]),
        )

        if not await self._send_dm(reminder, embed):
            await self._send_in_channel(reminder, embed)

    async def _send_dm(self, reminder: dict, embed: discord.Embed) -> bool:
        try:
            user = self.bot.get_user(reminder["user_id"]) or await self.bot.fetch_user(reminder["user_id"])
            await user.send(embed=embed)
            return True
        except discord.HTTPException as e:
            logger.info(f"Reminder {reminder['id']} couldn't DM user {reminder['user_id']}, trying its channel: {e}")
            return False

    async def _send_in_channel(self, reminder: dict, embed: discord.Embed):
        """Fallback for closed DMs: posts where the reminder was set, pinging only its owner."""
        channel = self.bot.get_channel(reminder["channel_id"])
        try:
            if channel is None:
                channel = await self.bot.fetch_channel(reminder["channel_id"])
            await channel.send(
                content=f"<@{reminder['user_id']}>",
                embed=embed,
                allowed_mentions=discord.AllowedMentions(
                    everyone=False, roles=False, users=[discord.Object(reminder["user_id"])],
                ),
            )
        except discord.HTTPException as e:
            logger.warning(f"Reminder {reminder['id']} couldn't be delivered to user {reminder['user_id']}: {e}")

    # Commands

    async def _create(
        self, interaction: discord.Interaction, content: str, due_at: int,
        *, timezone: str | None = None,
    ):
        if await reminder_count(interaction.guild_id, interaction.user.id) >= MAX_REMINDERS:
            raise UserError(f"You already have **{MAX_REMINDERS}** reminders in this server. Delete one first.")

        reminder_id = await reminder_add(
            interaction.user.id, interaction.guild_id, interaction.channel_id,
            content, due_at, timezone,
        )
        self._wake_scheduler()

        reminder = await reminder_get(reminder_id, interaction.guild_id, interaction.user.id)
        embed = await _upcoming_embed(reminder, "set for")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="at", description="Set a reminder for a specific date and time")
    @app_commands.describe(
        about="What to remind you about",
        date="Date as YYYY-MM-DD",
        time="Time as HH:MM or HH:MM:SS (24h)",
        timezone="Your IANA timezone, e.g. Europe/Lisbon",
    )
    @app_commands.autocomplete(timezone=timezone_autocomplete)
    async def at(
        self, interaction: discord.Interaction,
        about: app_commands.Range[str, 1, MAX_CONTENT_LENGTH], date: str, time: str, timezone: str,
    ):
        try:
            zone = parse_zone(timezone)
            moment = parse_local_datetime(date, time, zone)
        except ValueError as e:
            raise UserError(str(e))

        due_at = int(moment.timestamp())
        now = discord.utils.utcnow()
        if moment <= now:
            raise UserError(f"<t:{due_at}:F> is in the past.")
        if moment - now > MAX_AHEAD:
            raise UserError(f"Reminders can be set at most **{MAX_AHEAD.days // 365}** years ahead.")

        await self._create(interaction, about, due_at, timezone=zone.key)

    @app_commands.command(name="in", description="Set a reminder for an amount of time from now")
    @app_commands.describe(about="What to remind you about", amount="How many units from now", unit="Unit of time")
    @app_commands.choices(unit=IN_UNIT_CHOICES)
    async def in_(
        self, interaction: discord.Interaction,
        about: app_commands.Range[str, 1, MAX_CONTENT_LENGTH], amount: app_commands.Range[int, 1, None], unit: str,
    ):
        try:
            delta = timedelta(**{unit: amount})
        except OverflowError:
            delta = None
        if delta is None or delta > MAX_AHEAD:
            raise UserError(f"Reminders can be set at most **{MAX_AHEAD.days // 365}** years ahead.")

        await self._create(interaction, about, _now() + int(delta.total_seconds()))

    @app_commands.command(name="list", description="List your reminders in this server")
    async def list_(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        reminders = await reminders_for_user(interaction.guild_id, interaction.user.id)
        if not reminders:
            raise UserError("You have no reminders in this server.")

        entries = []
        for reminder in reminders:
            entry = f"**#{reminder['id']}** <t:{reminder['due_at']}:F> (<t:{reminder['due_at']}:R>)\n"
            if reminder["repeat_interval"]:
                entry += f"Repeats {_repeat_label(reminder)}\n"
            entry += f"{_short(reminder['content'], 200)}\n\n"
            entries.append(entry)

        header = f"# Reminders\n**{len(reminders)}**/{MAX_REMINDERS} in this server.\n\n"
        pages = [header + chunk for chunk in chunk_text("".join(entries), TEXT_DISPLAY_LIMIT - len(header))]
        view = PaginatorView(pages, await get_guild_embed_color(interaction.guild_id))
        view.message = await interaction.followup.send(view=view, ephemeral=True)

    async def _reminder_autocomplete(self, interaction: discord.Interaction, current: str):
        current = current.lower().lstrip("#")
        choices = []
        for reminder in await reminders_for_user(interaction.guild_id, interaction.user.id):
            if current and current not in str(reminder["id"]) and current not in reminder["content"].lower():
                continue
            prefix = f"#{reminder['id']} (in {_remaining(reminder)}) "
            # Discord rejects a choice name over 100 characters.
            name = prefix + _short(reminder["content"], 100 - len(prefix))
            choices.append(app_commands.Choice(name=name, value=str(reminder["id"])))
        return choices[:25]

    async def _get_owned(self, interaction: discord.Interaction, value: str) -> dict:
        """Resolves a picked or typed ID like 12 or #12 to the caller's reminder."""
        try:
            reminder_id = int(value.strip().lstrip("#"))
        except ValueError:
            raise UserError("Pick a reminder from the list, or type its ID.")
        reminder = await reminder_get(reminder_id, interaction.guild_id, interaction.user.id)
        if reminder is None:
            raise UserError(f"You have no reminder **#{reminder_id}** in this server.")
        return reminder

    @app_commands.command(name="when", description="Show one of your reminders")
    @app_commands.describe(reminder="The reminder to show")
    @app_commands.autocomplete(reminder=_reminder_autocomplete)
    async def when(self, interaction: discord.Interaction, reminder: str):
        found = await self._get_owned(interaction, reminder)
        embed = await _upcoming_embed(found, "is due")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="delete", description="Delete one of your reminders")
    @app_commands.describe(reminder="The reminder to delete")
    @app_commands.autocomplete(reminder=_reminder_autocomplete)
    async def delete(self, interaction: discord.Interaction, reminder: str):
        found = await self._get_owned(interaction, reminder)
        await reminder_delete(found["id"], interaction.guild_id, interaction.user.id)
        embed = await guild_embed(interaction.guild_id, f"Deleted reminder **#{found['id']}**.\n{_short(found['content'], 200)}")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="clear", description="Delete all your reminders in this server")
    async def clear(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        count = await reminder_count(interaction.guild_id, interaction.user.id)
        if count == 0:
            raise UserError("You have no reminders in this server.")

        view = ClearRemindersView(interaction.guild_id, interaction.user.id, count)
        view.message = await interaction.followup.send(view=view, ephemeral=True)

    @app_commands.command(name="repeat", description="Make one of your reminders repeat")
    @app_commands.describe(
        reminder="The reminder to repeat",
        amount="How many units between repeats",
        unit="Unit of time",
    )
    @app_commands.choices(unit=UNIT_CHOICES)
    @app_commands.autocomplete(reminder=_reminder_autocomplete)
    async def repeat(
        self, interaction: discord.Interaction, reminder: str,
        amount: app_commands.Range[int, 1, None], unit: str,
    ):
        found = await self._get_owned(interaction, reminder)

        try:
            interval = timedelta(**{unit: amount})
        except OverflowError:
            interval = None
        if interval is None or interval > MAX_AHEAD:
            raise UserError(f"Repeat interval can be at most **{MAX_AHEAD.days // 365}** years.")

        found["repeat_interval"] = int(interval.total_seconds())
        await reminder_set_repeat(found["id"], found["repeat_interval"])
        embed = await guild_embed(
            interaction.guild_id,
            f"Reminder **#{found['id']}** now repeats {_repeat_label(found)}, "
            f"starting <t:{found['due_at']}:F>.",
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Reminder(bot))
