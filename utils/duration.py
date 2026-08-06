import re
from datetime import timedelta

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
