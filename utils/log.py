import logging
import os
import re
import sys
from collections import deque
from logging.handlers import RotatingFileHandler

from markupsafe import Markup, escape

LOG_BUFFER = deque(maxlen=100_000)

_LOG_LINE_RE = re.compile(
    r"^\[(?P<ts>[^\]]+)\] (?P<level>[A-Z]+) (?P<logger>[^:]+): (?P<msg>.*)$",
    re.DOTALL,
)

LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs")
LOG_FILE = os.path.join(LOG_DIR, "bot.log")

_MUTED = "\x1b[38;2;114;118;125m"
_ACCENT = "\x1b[38;2;88;101;242m"
_YELLOW = "\x1b[38;2;250;166;26m"
_RED = "\x1b[38;2;237;66;69m"
_RESET = "\x1b[0m"
_BOLD = "\x1b[1m"

_LEVEL_COLORS = {
    "DEBUG": _MUTED,
    "INFO": _ACCENT,
    "WARNING": _YELLOW,
    "ERROR": _RED,
    "CRITICAL": _RED,
}


def _enable_windows_vt():
    """Turns on ANSI escape processing for the console run.py was double-clicked
    from — off by default on plain conhost, unlike Windows Terminal."""
    if sys.platform != "win32":
        return
    import ctypes

    kernel32 = ctypes.windll.kernel32
    for handle_id in (-11, -12):  # STD_OUTPUT_HANDLE, STD_ERROR_HANDLE
        handle = kernel32.GetStdHandle(handle_id)
        mode = ctypes.c_uint32()
        if not kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            continue
        kernel32.SetConsoleMode(handle, mode.value | 0x0004)  # ENABLE_VIRTUAL_TERMINAL_PROCESSING


class ColorFormatter(logging.Formatter):
    """Mirrors colorize_log_line's web console colors (log.py's timestamp/level/
    logger spans) as ANSI escapes for the terminal run.py runs in."""

    def format(self, record):
        line = super().format(record)
        match = _LOG_LINE_RE.match(line)
        if not match:
            return line

        level = match["level"]
        color = _LEVEL_COLORS.get(level, "")
        return (
            f"{_MUTED}[{match['ts']}]{_RESET} "
            f"{_BOLD}{color}{level}{_RESET} "
            f"{_MUTED}{match['logger']}:{_RESET} {match['msg']}"
        )


class BufferHandler(logging.Handler):
    """Keeps formatted log lines in memory so the web console can display them."""

    def emit(self, record):
        LOG_BUFFER.append(self.format(record))


def setup_logging(level=logging.INFO):
    fmt = logging.Formatter(
        "[%(asctime)s] %(levelname)s %(name)s: %(message)s",
        datefmt="%d/%m/%Y %H:%M:%S",
    )

    _enable_windows_vt()
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(ColorFormatter(fmt._fmt, datefmt=fmt.datefmt))

    buffer_handler = BufferHandler()
    buffer_handler.setFormatter(fmt)

    os.makedirs(LOG_DIR, exist_ok=True)
    file_handler = RotatingFileHandler(LOG_FILE, maxBytes=5_000_000, backupCount=3, encoding="utf-8")
    file_handler.setFormatter(fmt)

    root = logging.getLogger()
    root.setLevel(level)
    root.addHandler(stream_handler)
    root.addHandler(buffer_handler)
    root.addHandler(file_handler)


def tail_log_file(lines=500, chunk_size=8192):
    """Reads only the tail of the log file by scanning backward in chunks, instead
    of the whole file — matters once the file approaches its rotation size."""
    if not os.path.exists(LOG_FILE):
        return []

    with open(LOG_FILE, "rb") as f:
        f.seek(0, os.SEEK_END)
        pos = f.tell()
        data = b""
        newline_count = 0

        while pos > 0 and newline_count <= lines:
            read_size = min(chunk_size, pos)
            pos -= read_size
            f.seek(pos)
            chunk = f.read(read_size)
            data = chunk + data
            newline_count += chunk.count(b"\n")

    text = data.decode("utf-8", errors="replace")
    return text.splitlines()[-lines:]


def colorize_log_line(line: str) -> Markup:
    """Wraps a formatted log line's timestamp/level/logger in spans so the web
    console can color it the way a log-highlighter extension colors bot.log in an editor."""
    match = _LOG_LINE_RE.match(line)
    if not match:
        return Markup(escape(line))

    level = match["level"]
    return Markup(
        '<span class="log-ts">[{ts}]</span> '
        '<span class="log-level log-level-{level_class}">{level}</span> '
        '<span class="log-logger">{logger}:</span> {msg}'
    ).format(
        ts=escape(match["ts"]),
        level_class=escape(level.lower()),
        level=escape(level),
        logger=escape(match["logger"]),
        msg=escape(match["msg"]),
    )
