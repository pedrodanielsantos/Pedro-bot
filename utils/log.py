import asyncio
import logging
import os
import re
import sys
import threading
from collections import deque
from logging.handlers import RotatingFileHandler

LOG_BUFFER = deque(maxlen=100_000)

_LOG_LINE_RE = re.compile(
    r"^\[(?P<ts>[^\]]+)\] (?P<level>[A-Z]+) (?P<logger>[^:]+): (?P<msg>.*)$",
    re.DOTALL,
)

LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs")
LOG_FILE = os.path.join(LOG_DIR, "bot.log")
CONSOLE_RAW_FILE = os.path.join(LOG_DIR, "console.raw")
CONSOLE_RAW_MAX_BYTES = 5_000_000

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
    """Formats log lines with ANSI color escapes for the terminal."""

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


class RawConsoleSink:
    """Writer for logs/console.raw, the raw stdout/stderr tee for the web console's
    live view. Separate from bot.log. Truncates on construction and past max_bytes."""

    def __init__(self, path=CONSOLE_RAW_FILE, max_bytes=CONSOLE_RAW_MAX_BYTES):
        self.max_bytes = max_bytes
        self._lock = threading.Lock()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self._fh = open(path, "wb", buffering=0)
        self._size = 0

    def write(self, data: bytes):
        if not data:
            return
        with self._lock:
            if self._size + len(data) > self.max_bytes:
                self._fh.seek(0)
                self._fh.truncate(0)
                self._size = 0
            self._fh.write(data)
            self._size += len(data)

    def close(self):
        with self._lock:
            self._fh.close()


def _install_excepthooks():
    """Routes exceptions that reach the top of the process (main thread or a raw
    thread) into the logger instead of only the terminal. Doesn't affect asyncio task
    exceptions, which already go through logging.getLogger("asyncio") by default."""
    uncaught = logging.getLogger("uncaught")

    def _on_exception(exc_type, exc_value, exc_tb):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_tb)
            return
        uncaught.critical("Uncaught exception", exc_info=(exc_type, exc_value, exc_tb))

    def _on_thread_exception(args):
        if issubclass(args.exc_type, SystemExit):
            return  # matches default threading.excepthook: sys.exit() in a thread isn't a crash
        uncaught.critical(
            f"Uncaught exception in thread {args.thread.name}",
            exc_info=(args.exc_type, args.exc_value, args.exc_traceback),
        )

    sys.excepthook = _on_exception
    threading.excepthook = _on_thread_exception


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

    _install_excepthooks()


def quiet_uvicorn_logging():
    """Pair with uvicorn.Config(log_config=None), which lets uvicorn's loggers
    propagate to root instead of uvicorn's default private, non-propagating stderr
    handler. Mutes the resulting per-request uvicorn.access noise."""
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)


def log_file_size(path=LOG_FILE) -> int:
    """Current size of the log file, used as the initial resume point for a live
    tail so it starts exactly where a static render of tail_log_file() left off,
    instead of jumping to "now" and risking a gap for whatever gets logged in
    between."""
    return os.path.getsize(path) if os.path.exists(path) else 0


def tail_log_file(path=LOG_FILE, lines=500, chunk_size=8192):
    """Reads only the tail of the log file by scanning backward in chunks, instead
    of the whole file. Matters once the file approaches its rotation size."""
    if not os.path.exists(path):
        return []

    with open(path, "rb") as f:
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


async def tail_log_lines(path=LOG_FILE, poll_interval=0.5, start_pos=None):
    """Yields (pos, line) as the log file grows, or (pos, None) on an idle poll. pos
    is the byte offset just after the most recently consumed line, so a
    reconnecting SSE client can resume from there via Last-Event-ID instead of
    jumping to "now" and silently missing whatever was logged while it was
    disconnected. Tails the file (not LOG_BUFFER) since bot.py is a separate
    process from web.py's. Reopens on rotation/truncation, detected by the file
    shrinking."""
    while not os.path.exists(path):
        yield None, None
        await asyncio.sleep(poll_interval)

    f = open(path, "rb")
    size = os.path.getsize(path)
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
                size = os.path.getsize(path)
            except OSError:
                yield buf_pos + len(buf), None
                continue

            pos = f.tell()
            if size < pos:
                f.close()
                f = open(path, "rb")
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
