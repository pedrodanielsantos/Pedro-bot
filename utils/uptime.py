from datetime import datetime, timezone


def format_uptime(launch_time: datetime) -> str:
    delta = datetime.now(timezone.utc) - launch_time
    days, remainder = divmod(int(delta.total_seconds()), 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{days}d {hours}h {minutes}m {seconds}s"
