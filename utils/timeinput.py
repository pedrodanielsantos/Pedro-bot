from datetime import datetime
from zoneinfo import ZoneInfo, available_timezones

import discord
from discord import app_commands

ALL_TIMEZONES = sorted(available_timezones())

UNIT_CHOICES = [
    app_commands.Choice(name="Minutes", value="minutes"),
    app_commands.Choice(name="Hours", value="hours"),
    app_commands.Choice(name="Days", value="days"),
    app_commands.Choice(name="Weeks", value="weeks"),
]


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
