import re
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo, available_timezones

import discord
from discord import app_commands

from utils.text import plural

ALL_TIMEZONES = sorted(available_timezones())

UNIT_CHOICES = [
    app_commands.Choice(name="Minutes", value="minutes"),
    app_commands.Choice(name="Hours", value="hours"),
    app_commands.Choice(name="Days", value="days"),
    app_commands.Choice(name="Weeks", value="weeks"),
]

_UNITS = {
    "s": "seconds",
    "m": "minutes",
    "h": "hours",
    "d": "days",
    "w": "weeks",
}

_PATTERN = re.compile(r"(\d+)\s*([smhdw])", re.IGNORECASE)


# Dates and timezones

async def timezone_autocomplete(interaction: discord.Interaction, current: str):
    current = current.lower()
    matches = [tz for tz in ALL_TIMEZONES if current in tz.lower()]
    return [app_commands.Choice(name=tz, value=tz) for tz in matches[:25]]


def parse_zone(timezone: str) -> ZoneInfo:
    """Raises ValueError for a name that isn't an IANA timezone."""
    try:
        return ZoneInfo(timezone)
    except (ValueError, KeyError):
        raise ValueError("Unknown timezone. Pick one from the autocomplete list.")


def parse_local_datetime(date: str, time: str, zone: ZoneInfo) -> datetime:
    """Parses YYYY-MM-DD and HH:MM[:SS] as wall time in zone. Raises ValueError."""
    for time_format in ("%H:%M:%S", "%H:%M"):
        try:
            naive = datetime.strptime(f"{date} {time}", f"%Y-%m-%d {time_format}")
        except ValueError:
            continue
        return naive.replace(tzinfo=zone)
    raise ValueError("Invalid date/time. Use YYYY-MM-DD for the date and HH:MM or HH:MM:SS (24h) for the time.")


# Durations

def parse_duration(value: str) -> timedelta:
    """Parses a duration string like "10m", "2h", "1d12h" into a timedelta."""
    matches = _PATTERN.findall(value.strip())
    if not matches or _PATTERN.sub("", value.strip()):
        raise ValueError("Invalid duration. Use a combination like `10m`, `2h`, `7d` or `1w`.")

    kwargs = {}
    for amount, unit in matches:
        key = _UNITS[unit.lower()]
        kwargs[key] = kwargs.get(key, 0) + int(amount)

    delta = timedelta(**kwargs)
    if delta <= timedelta(0):
        raise ValueError("Duration must be greater than zero.")
    return delta


def format_duration_long(delta: timedelta) -> str:
    """Formats a timedelta in words, e.g. "1 day, 2 hours and 5 seconds"."""
    total_seconds = int(delta.total_seconds())
    weeks, remainder = divmod(total_seconds, 604800)
    days, remainder = divmod(remainder, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, seconds = divmod(remainder, 60)

    parts = []
    for amount, unit in ((weeks, "week"), (days, "day"), (hours, "hour"), (minutes, "minute"), (seconds, "second")):
        if amount:
            parts.append(f"{amount} {plural(amount, unit)}")

    if not parts:
        return "0 seconds"
    if len(parts) == 1:
        return parts[0]
    return f"{', '.join(parts[:-1])} and {parts[-1]}"


def format_duration(delta: timedelta) -> str:
    """Formats a timedelta back into a compact duration string, e.g. "1d 2h"."""
    total_seconds = int(delta.total_seconds())
    weeks, remainder = divmod(total_seconds, 604800)
    days, remainder = divmod(remainder, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, seconds = divmod(remainder, 60)

    parts = []
    for amount, unit in ((weeks, "w"), (days, "d"), (hours, "h"), (minutes, "m"), (seconds, "s")):
        if amount:
            parts.append(f"{amount}{unit}")

    return " ".join(parts) if parts else "0s"


# Uptime

def format_uptime(launch_time: datetime) -> str:
    delta = datetime.now(UTC) - launch_time
    days, remainder = divmod(int(delta.total_seconds()), 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, seconds = divmod(remainder, 60)
    parts = [(days, "d"), (hours, "h"), (minutes, "m"), (seconds, "s")]
    # Drops the units still at zero; the guard keeps seconds when they all are.
    while len(parts) > 1 and parts[0][0] == 0:
        parts.pop(0)
    return " ".join(f"{value}{symbol}" for value, symbol in parts)
