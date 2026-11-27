import logging
import re
import sys
import threading

_LOG_LINE_RE = re.compile(
    r"^\[(?P<ts>[^\]]+)\] (?P<level>[A-Z]+) (?P<logger>[^:]+): (?P<msg>.*)$",
    re.DOTALL,
)

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


def color_log_line(ts: str, level: str, logger_name: str, msg: str) -> str:
    """The colored console form of a log line. Shared by the formatter below and
    by run.py, which rewrites child processes that log in their own format into
    this one so the console reads as a single log."""
    color = _LEVEL_COLORS.get(level, "")
    return (
        f"{_MUTED}[{ts}]{_RESET} "
        f"{_BOLD}{color}{level}{_RESET} "
        f"{_MUTED}{logger_name}:{_RESET} {msg}"
    )


class ColorFormatter(logging.Formatter):
    """Formats log lines with ANSI color escapes for the terminal."""

    def format(self, record):
        line = super().format(record)
        match = _LOG_LINE_RE.match(line)
        if not match:
            return line
        return color_log_line(match["ts"], match["level"], match["logger"], match["msg"])


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
    """Logs to stderr only. Under run.py that reaches the log files: its own stderr
    through the tee, bot.py's through the pipe run.py pumps."""
    # Accepts a level name so LOG_LEVEL can be set in .env. An unknown one falls
    # back to INFO rather than failing startup over a typo.
    if isinstance(level, str):
        level = logging.getLevelNamesMapping().get(level.upper(), logging.INFO)

    _enable_windows_vt()
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(ColorFormatter(
        "[%(asctime)s] %(levelname)s %(name)s: %(message)s",
        datefmt="%d/%m/%Y %H:%M:%S",
    ))

    root = logging.getLogger()
    root.setLevel(level)
    root.addHandler(stream_handler)

    _install_excepthooks()


def quiet_duplicate_loggers():
    """Mutes third-party loggers that restate an event the bot already reports
    itself, so one failure produces one line instead of three.

    wavelink logs every TrackExceptionEvent at ERROR with Lavalink's whole Java
    cause chain, which for a YouTube load failure it prints twice over, once as
    the message and again as the cause. It does this before dispatching the event
    to MusicManager.on_wavelink_track_exception, which reports the same failure in
    one line naming the track and what it did about it. The dispatch does not go
    through this logger, so muting it changes no behaviour.

    Skipped at DEBUG, where the full chain is what you're asking for.
    """
    if logging.getLogger().isEnabledFor(logging.DEBUG):
        return
    logging.getLogger("TrackException").setLevel(logging.CRITICAL)


def quiet_uvicorn_logging():
    """Pair with uvicorn.Config(log_config=None), which lets uvicorn's loggers
    propagate to root instead of uvicorn's default private, non-propagating stderr
    handler. Mutes the resulting per-request uvicorn.access noise."""
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)

