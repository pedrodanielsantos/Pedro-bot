import re
from datetime import timedelta

from utils.text import plural

_UNITS = {
    "s": "seconds",
    "m": "minutes",
    "h": "hours",
    "d": "days",
    "w": "weeks",
}

_PATTERN = re.compile(r"(\d+)\s*([smhdw])", re.IGNORECASE)

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
