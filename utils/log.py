import asyncio
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
    """Windows conhost doesn't render ANSI colors unless this is set."""
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
    """Same colors as colorize_log_line, as ANSI escapes for the terminal."""

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


def log_file_size() -> int:
    """Current size of bot.log, used as the initial resume point for a live tail so
    it starts exactly where a static render of tail_log_file() left off, instead of
    jumping to "now" and risking a gap for whatever gets logged in between."""
    return os.path.getsize(LOG_FILE) if os.path.exists(LOG_FILE) else 0


def tail_log_file(lines=500, chunk_size=8192):
    """Reads only the tail of the log file by scanning backward in chunks, instead
    of the whole file. Matters once the file approaches its rotation size."""
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


async def tail_log_lines(poll_interval=0.5, start_pos=None):
    """Yields (pos, line) as bot.log grows, or (pos, None) on an idle poll. pos is
    the byte offset just after the most recently consumed line, so a reconnecting
    SSE client can resume from there via Last-Event-ID instead of jumping to "now"
    and silently missing whatever was logged while it was disconnected.
    Tails the file (not LOG_BUFFER) since bot.py is a separate process from
    web.py's. Reopens on rotation, detected by the file shrinking."""
    while not os.path.exists(LOG_FILE):
        yield None, None
        await asyncio.sleep(poll_interval)

    f = open(LOG_FILE, "rb")
    size = os.path.getsize(LOG_FILE)
    # A stale offset from before a rotation could point past the new file's end,
    # or into a stale earlier generation entirely. Safest fallback is "now".
    if start_pos is None or start_pos > size:
        f.seek(0, os.SEEK_END)
    else:
        f.seek(start_pos)
    buf = b""
    buf_pos = f.tell()

    try:
        while True:
            await asyncio.sleep(poll_interval)
            try:
                size = os.path.getsize(LOG_FILE)
            except OSError:
                yield buf_pos + len(buf), None
                continue

            pos = f.tell()
            if size < pos:
                f.close()
                f = open(LOG_FILE, "rb")
                pos = 0
                buf = b""
                buf_pos = 0

            if size <= pos:
                yield buf_pos + len(buf), None
                continue

            f.seek(pos)
            buf += f.read(size - pos)
            *complete, buf = buf.split(b"\n")

            if not complete:
                yield buf_pos + len(buf), None
            for raw_line in complete:
                buf_pos += len(raw_line) + 1
                text = raw_line.decode("utf-8", errors="replace").rstrip("\r")
                if text:
                    yield buf_pos, text
    finally:
        f.close()


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
