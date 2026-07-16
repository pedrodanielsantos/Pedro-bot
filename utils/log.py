import logging
import os
from collections import deque
from logging.handlers import RotatingFileHandler

LOG_BUFFER = deque(maxlen=100_000)

LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs")
LOG_FILE = os.path.join(LOG_DIR, "bot.log")


class BufferHandler(logging.Handler):
    """Keeps formatted log lines in memory so the web console can display them."""

    def emit(self, record):
        LOG_BUFFER.append(self.format(record))


def setup_logging(level=logging.INFO):
    fmt = logging.Formatter(
        "[%(asctime)s] %(levelname)s %(name)s: %(message)s",
        datefmt="%d/%m/%Y %H:%M:%S",
    )

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(fmt)

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
