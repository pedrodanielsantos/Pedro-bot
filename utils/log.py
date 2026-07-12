import logging
from collections import deque

LOG_BUFFER = deque(maxlen=100_000)


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

    root = logging.getLogger()
    root.setLevel(level)
    root.addHandler(stream_handler)
    root.addHandler(buffer_handler)
