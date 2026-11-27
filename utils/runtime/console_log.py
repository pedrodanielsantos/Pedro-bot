"""The console log: one file per day, gzipped once the day is over.

run.py's ConsoleSink is the only writer. It keeps the raw stream, ANSI colors
included, as logs/console/console.2026-11-27.0.raw. Downloads strip the colors
on the way out.

A day's file is a "part"; a day that outgrows MAX_PART_BYTES continues in part .1,
.2 and so on. Every part but the one being written is gzipped in place (.raw.gz).
Parts older than RETENTION_DAYS are deleted, then the oldest until the log fits
TOTAL_SIZE_CAP.

A cursor is a bookmark into a log, "<part id>:<byte offset>", e.g.
"2026-11-27.0:51426". Offsets count uncompressed bytes, so a cursor stays valid
after its part is gzipped. Parts are never truncated or renamed, so a cursor
stays valid until retention deletes its part.
"""

import asyncio
import datetime as dt
import gzip
import logging
import os
import re
import shutil
import struct
import threading
from typing import NamedTuple

from utils.runtime.log import color_log_line

LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "logs")

RETENTION_DAYS = 90
TOTAL_SIZE_CAP = 2 * 1024**3
# Caps a runaway day (an error loop) per part, and so the memory a read of a
# gzipped part takes, since those are decompressed whole.
MAX_PART_BYTES = 20_000_000

logger = logging.getLogger("logs")

# CSI (colors, cursor moves), OSC (titles, links), and the two-byte escapes.
_ANSI_RE = re.compile(rb"\x1b(?:\[[0-?]*[ -/]*[@-~]|\][^\x07\x1b]*(?:\x07|\x1b\\)|[@-Z\\-_])")
_CURSOR_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})\.(\d+):(\d+)$")
_DAY_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class Part(NamedTuple):
    day: dt.date
    index: int
    path: str
    compressed: bool

    @property
    def id(self) -> str:
        return f"{self.day.isoformat()}.{self.index}"


class DailyLog:
    """Names and lists the parts of one log."""

    def __init__(self, directory: str, prefix: str, ext: str):
        self.directory = directory
        self.prefix = prefix
        self.ext = ext
        self._name_re = re.compile(
            rf"^{re.escape(prefix)}\.(\d{{4}}-\d{{2}}-\d{{2}})\.(\d+){re.escape(ext)}(\.gz)?$"
        )

    def path(self, day: dt.date, index: int) -> str:
        return os.path.join(self.directory, f"{self.prefix}.{day.isoformat()}.{index}{self.ext}")

    def parts(self) -> list[Part]:
        """Oldest first. A part present both plain and gzipped is listed as plain:
        that only happens when deleting the plain copy failed after the gzip was
        complete, so the two hold the same bytes."""
        found = {}
        try:
            with os.scandir(self.directory) as entries:
                for entry in entries:
                    match = self._name_re.match(entry.name)
                    if not match:
                        continue
                    try:
                        day = dt.date.fromisoformat(match[1])
                    except ValueError:
                        continue
                    key = (day, int(match[2]))
                    compressed = bool(match[3])
                    if key not in found or not compressed:
                        found[key] = Part(day, key[1], entry.path, compressed)
        except FileNotFoundError:
            return []
        return [found[key] for key in sorted(found)]

    def find(self, part_id: str) -> Part | None:
        return next((p for p in self.parts() if p.id == part_id), None)


CONSOLE_LOG = DailyLog(os.path.join(LOG_DIR, "console"), "console", ".raw")


def _display_bytes(line: bytes) -> bytes:
    """What a terminal leaves of a line: a \\r redraw keeps only the last draw."""
    return line.rstrip(b"\r").rsplit(b"\r", 1)[-1]


def _display(line: bytes) -> str:
    return _display_bytes(line).decode("utf-8", errors="replace")


class _PlainLines:
    """Turns the raw stream into plain-text lines, as a terminal would show them,
    for downloads. Line-buffered, so an escape sequence split across two chunks
    is still stripped whole."""

    # A line with no newline yet is flushed past this, so it can't grow unbounded.
    MAX_PENDING = 1_000_000

    def __init__(self):
        self._pending = b""

    def feed(self, data: bytes) -> bytes:
        *lines, self._pending = (self._pending + data).split(b"\n")
        # A progress bar redraws with \r and may never end its line; only the
        # last draw survives _display_bytes() anyway.
        cut = self._pending.rfind(b"\r", 0, len(self._pending) - 1)
        if cut > 0:
            self._pending = self._pending[cut:]
        if len(self._pending) > self.MAX_PENDING:
            lines.append(self._pending)
            self._pending = b""
        return b"".join(_ANSI_RE.sub(b"", _display_bytes(line)) + b"\n" for line in lines)

    def flush(self) -> bytes:
        rest, self._pending = self._pending, b""
        return _ANSI_RE.sub(b"", _display_bytes(rest)) + b"\n" if rest else b""


class _PartWriter:
    """Appends to a log's current part, moving to a new one when the day changes
    or the part would pass max_bytes."""

    def __init__(self, log: DailyLog, max_bytes: int):
        self.log = log
        self.max_bytes = max_bytes
        self.day = None
        self.index = None
        self.path = None
        self._fh = None
        self._size = 0

    def open(self, day: dt.date):
        """Continues the day's last part, so restarts add to one file per day."""
        os.makedirs(self.log.directory, exist_ok=True)
        todays = [p for p in self.log.parts() if p.day == day]
        index = 0
        if todays:
            last = todays[-1]
            full = last.compressed or os.path.getsize(last.path) >= self.max_bytes
            index = last.index + 1 if full else last.index
        self._switch(day, index)

    def _switch(self, day: dt.date, index: int):
        if self._fh:
            self._fh.close()
        self.day = day
        self.index = index
        self.path = self.log.path(day, index)
        self._fh = open(self.path, "ab", buffering=0)
        self._size = os.path.getsize(self.path)

    def ends_mid_line(self) -> bool:
        if not self._size:
            return False
        with open(self.path, "rb") as f:
            f.seek(-1, os.SEEK_END)
            return f.read(1) != b"\n"

    def write(self, data: bytes, today: dt.date) -> bool:
        """Returns whether this moved to a new part."""
        moved = False
        if self.day != today:
            self.open(today)
            moved = True
        elif self._size and self._size + len(data) > self.max_bytes:
            self._switch(today, self.index + 1)
            moved = True
        self._fh.write(data)
        self._size += len(data)
        return moved

    def close(self):
        if self._fh:
            self._fh.close()


class ConsoleSink:
    """The log's single writer. Fed by run.py's stdout/stderr tee and by the
    output pumps of the processes it supervises."""

    def __init__(self, max_part_bytes: int = MAX_PART_BYTES):
        self._lock = threading.Lock()
        self._housekeeping_lock = threading.Lock()
        self._writer = _PartWriter(CONSOLE_LOG, max_part_bytes)
        self._closed = False
        self._housekeeping_requested = False

        self._writer.open(dt.date.today())
        # A crash can leave the last line unfinished; the marker starts its own.
        if self._writer.ends_mid_line():
            self.write(b"\n")
        stamp = dt.datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        self.write(f"{color_log_line(stamp, 'INFO', 'run', 'run.py started')}\n".encode("utf-8"))
        self._start_housekeeping()

    def write(self, data: bytes):
        if not data:
            return
        with self._lock:
            # Closed means shutdown: output printed after close() still reaches the
            # terminal through the tee, it just isn't kept.
            if self._closed:
                return
            moved = self._writer.write(data, dt.date.today())
        if moved:
            self._start_housekeeping()

    def close(self):
        with self._lock:
            self._writer.close()
            self._closed = True

    def _start_housekeeping(self):
        # A daemon thread: gzipping a big part must not hold up the writer, and an
        # unfinished one is simply redone on the next start.
        threading.Thread(target=self._housekeep, name="log-housekeeping", daemon=True).start()

    def _housekeep(self):
        # A request while a pass runs makes it go again, since the part that just
        # finished may have been listed as active.
        self._housekeeping_requested = True
        if not self._housekeeping_lock.acquire(blocking=False):
            return
        try:
            while self._housekeeping_requested:
                self._housekeeping_requested = False
                housekeep(CONSOLE_LOG, self._active_path)
        except Exception:
            logger.exception("Log housekeeping failed")
        finally:
            self._housekeeping_lock.release()

    def _active_path(self) -> str:
        with self._lock:
            return self._writer.path


def _remove(path: str) -> bool:
    """Whether the file is gone. On Windows a reader holding it open stops the
    delete; the next pass retries."""
    try:
        os.remove(path)
    except FileNotFoundError:
        pass
    except OSError:
        return False
    return True


def _compress(part: Part) -> bool:
    gz_path = f"{part.path}.gz"
    if not os.path.exists(gz_path):
        # Written under a temporary name and moved into place, so a .gz that
        # exists is always complete.
        tmp_path = f"{gz_path}.tmp"
        with open(part.path, "rb") as src, gzip.open(tmp_path, "wb") as dst:
            shutil.copyfileobj(src, dst, 1024 * 1024)
        os.replace(tmp_path, gz_path)
    return _remove(part.path)


def housekeep(log: DailyLog, active_path, today: dt.date | None = None):
    """Gzips every part but the active one, then applies retention. active_path
    is called per part, since the writer can move on while this runs."""
    today = today or dt.date.today()
    compressed = 0
    for part in log.parts():
        if not part.compressed and part.path != active_path():
            try:
                compressed += _compress(part)
            except OSError as e:
                logger.warning(f"Could not compress {os.path.basename(part.path)}: {e}")

    cutoff = today - dt.timedelta(days=RETENTION_DAYS)
    parts = log.parts()
    sizes = {}
    for part in parts:
        try:
            sizes[part.path] = os.path.getsize(part.path)
        except OSError:
            sizes[part.path] = 0
    total = sum(sizes.values())
    deleted = 0
    for part in parts:
        if part.path == active_path():
            continue
        if part.day >= cutoff and total <= TOTAL_SIZE_CAP:
            # Oldest first, so nothing after this needs deleting either.
            break
        plain = os.path.splitext(part.path)[0] if part.compressed else part.path
        if _remove(f"{plain}.gz") and _remove(plain):
            total -= sizes[part.path]
            deleted += 1

    if compressed or deleted:
        logger.info(f"Log housekeeping: compressed {compressed}, deleted {deleted} part(s)")


# Reading. Everything below is for web.py, which reads the files the sink writes.

_gz_cache: dict[str, tuple[float, bytes]] = {}
_gz_lock = threading.Lock()
_GZ_CACHE_ENTRIES = 2


def _decompressed(path: str) -> bytes:
    """A gzipped part read whole. Paging back through history reads a part from
    the end, which gzip can't seek to, so the last two are kept in memory."""
    mtime = os.path.getmtime(path)
    with _gz_lock:
        hit = _gz_cache.get(path)
        if hit and hit[0] == mtime:
            return hit[1]
    with gzip.open(path, "rb") as f:
        data = f.read()
    with _gz_lock:
        _gz_cache[path] = (mtime, data)
        while len(_gz_cache) > _GZ_CACHE_ENTRIES:
            _gz_cache.pop(next(iter(_gz_cache)))
    return data


class _Reader:
    """Byte access to a part, plain or gzipped. Follows a part from its plain file
    to its .gz when housekeeping compresses it mid-read."""

    def __init__(self, log: DailyLog, part: Part):
        self.log = log
        self.part = part

    def _retry(self, fn):
        try:
            return fn(self.part)
        except FileNotFoundError:
            refreshed = self.log.find(self.part.id)
            if refreshed is None:
                raise
            self.part = refreshed
            return fn(self.part)

    def size(self) -> int:
        return self._retry(lambda p: len(_decompressed(p.path)) if p.compressed else os.path.getsize(p.path))

    def read(self, start: int, end: int) -> bytes:
        def read(p):
            if p.compressed:
                return _decompressed(p.path)[start:end]
            with open(p.path, "rb") as f:
                f.seek(start)
                return f.read(end - start)
        return self._retry(read)


def _lines_before(reader: _Reader, end: int, limit: int, finished: bool):
    """Up to limit lines ending at byte end, oldest first, as (offset, bytes), and
    whether the part holds more before them. A trailing line with no newline is
    included only if the part is finished, since the writer may still be adding to it."""
    data = b""
    pos = end
    while pos > 0 and data.count(b"\n") <= limit:
        step = min(64 * 1024, pos)
        pos -= step
        data = reader.read(pos, pos + step) + data

    pieces = data.split(b"\n")
    tail = pieces.pop()  # after the last newline: b"" or an unfinished line
    offsets = []
    offset = pos
    for piece in pieces:
        offsets.append((offset, piece))
        offset += len(piece) + 1
    if tail and finished:
        offsets.append((offset, tail))
    # Unless the read reached the start, its first piece may begin mid-line.
    if pos > 0 and offsets:
        offsets.pop(0)
    found = offsets[-limit:]
    return found, bool(found) and found[0][0] > 0


def _collect(log: DailyLog, parts: list[Part], index: int, end: int, limit: int, finished: bool):
    lines = []
    more = False
    while index >= 0:
        part = parts[index]
        reader = _Reader(log, part)
        found, more_here = _lines_before(reader, end, limit - len(lines), finished)
        lines[:0] = [[f"{reader.part.id}:{offset}", _display(raw)] for offset, raw in found]
        if len(lines) >= limit:
            more = more_here or index > 0
            break
        index -= 1
        if index >= 0:
            end = _Reader(log, parts[index]).size()
            finished = True
    return lines, more


def read_tail(log: DailyLog, limit: int = 500) -> dict:
    """The last lines of a log, for the Console page's first render. "end" is the
    cursor the live stream resumes from; "more" whether there is older history."""
    parts = log.parts()
    if not parts:
        return {"lines": [], "more": False, "end": None}
    newest = parts[-1]
    reader = _Reader(log, newest)
    size = reader.size()
    # Stops at the last newline: an unfinished line arrives whole through the stream.
    end = size - len(reader.read(max(0, size - 64 * 1024), size).rsplit(b"\n", 1)[-1]) if size else 0
    lines, more = _collect(log, parts, len(parts) - 1, end, limit, finished=False)
    return {"lines": lines, "more": more, "end": f"{newest.id}:{end}"}


def read_before(log: DailyLog, cursor: str, limit: int = 500) -> dict:
    """The lines before a cursor, crossing into earlier parts and days."""
    parsed = _parse_cursor(cursor)
    parts = log.parts()
    index = next((i for i, p in enumerate(parts) if parsed and p.id == parsed[0]), None)
    if index is None:
        return {"lines": [], "more": False}
    lines, more = _collect(log, parts, index, parsed[1], limit, finished=False)
    return {"lines": lines, "more": more}


def _parse_cursor(cursor: str | None) -> tuple[str, int] | None:
    match = _CURSOR_RE.match(cursor or "")
    return (f"{match[1]}.{match[2]}", int(match[3])) if match else None


async def follow(log: DailyLog, cursor: str | None, poll_interval: float = 0.5):
    """Yields (start, end, text) for each new line from cursor on, or (None, end,
    None) on an idle poll. start and end are the cursors before and after the line.
    Moves on to the next part once one exists and this one is read to the end.

    Opens the file per poll instead of holding it, so housekeeping can delete a
    part on Windows once it has been gzipped."""
    parsed = _parse_cursor(cursor)
    reader = None
    offset = 0
    while reader is None:
        parts = log.parts()
        part = next((p for p in parts if parsed and p.id == parsed[0]), None)
        if part and parsed[1] <= _Reader(log, part).size():
            reader, offset = _Reader(log, part), parsed[1]
        elif parts:
            # No usable cursor: start at "now".
            reader = _Reader(log, parts[-1])
            offset = reader.size()
        else:
            yield None, None, None
            await asyncio.sleep(poll_interval)

    pending = b""
    line_start = offset  # where the pending, unfinished line begins
    while True:
        await asyncio.sleep(poll_interval)
        try:
            size = reader.size()
        except FileNotFoundError:
            # Deleted by retention under the reader; carry on from the newest part.
            parts = log.parts()
            if parts:
                reader = _Reader(log, parts[-1])
                offset = line_start = reader.size()
                pending = b""
            continue

        if size > offset:
            pending += reader.read(offset, size)
            offset = size
            *complete, pending = pending.split(b"\n")
            for raw in complete:
                start = f"{reader.part.id}:{line_start}"
                line_start += len(raw) + 1
                yield start, f"{reader.part.id}:{line_start}", _display(raw)
            if complete:
                continue

        later = [p for p in log.parts() if (p.day, p.index) > (reader.part.day, reader.part.index)]
        if later:
            if pending:
                start = f"{reader.part.id}:{line_start}"
                yield start, f"{reader.part.id}:{offset}", _display(pending)
            reader, offset, pending, line_start = _Reader(log, later[0]), 0, b"", 0
            continue
        yield None, f"{reader.part.id}:{line_start}", None


# Downloads: plain text, a whole day at a time.

def _part_size(part: Part) -> int:
    """Uncompressed size. A gzip trailer stores it in its last four bytes (modulo
    2^32, which MAX_PART_BYTES stays well under)."""
    if not part.compressed:
        return os.path.getsize(part.path)
    with open(part.path, "rb") as f:
        f.seek(-4, os.SEEK_END)
        return struct.unpack("<I", f.read(4))[0]


def list_days(log: DailyLog) -> list[tuple[dt.date, int]]:
    """(day, uncompressed bytes), newest first. Counts the raw bytes, color codes
    included, so a day's plain-text download is somewhat smaller."""
    sizes: dict[dt.date, int] = {}
    for part in log.parts():
        try:
            sizes[part.day] = sizes.get(part.day, 0) + _part_size(part)
        except OSError:
            continue
    return sorted(sizes.items(), reverse=True)


def parse_day(value: str) -> dt.date | None:
    if not _DAY_RE.match(value):
        return None
    try:
        return dt.date.fromisoformat(value)
    except ValueError:
        return None


def iter_day_plain(log: DailyLog, day: dt.date, chunk_size: int = 64 * 1024):
    """A day's parts in order as plain text, decompressed and stripped of colors
    as they're read."""
    plain = _PlainLines()
    for part in (p for p in log.parts() if p.day == day):
        try:
            f = gzip.open(part.path, "rb") if part.compressed else open(part.path, "rb")
        except FileNotFoundError:
            # Compressed between listing and opening.
            part = log.find(part.id)
            if part is None:
                continue
            f = gzip.open(part.path, "rb")
        with f:
            while chunk := f.read(chunk_size):
                if text := plain.feed(chunk):
                    yield text
    if rest := plain.flush():
        yield rest
