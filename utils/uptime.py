from datetime import datetime, timezone


def format_uptime(launch_time: datetime) -> str:
    delta = datetime.now(timezone.utc) - launch_time
    days, remainder = divmod(int(delta.total_seconds()), 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, seconds = divmod(remainder, 60)
    parts = [(days, "d"), (hours, "h"), (minutes, "m"), (seconds, "s")]
    # Drops the units still at zero; the guard keeps seconds when they all are.
    while len(parts) > 1 and parts[0][0] == 0:
        parts.pop(0)
    return " ".join(f"{value}{symbol}" for value, symbol in parts)
