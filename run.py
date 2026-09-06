import asyncio
import logging
import os
import shutil
import signal
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv

import web
from utils.log import RawConsoleSink, setup_logging

# run.py needs LAVALINK_* to decide whether to supervise a node. bot.py loads
# this again in its own process, which is a no-op the second time.
load_dotenv()


class _TeeStream:
    """Wraps stdout/stderr: writes go to the original stream and to the raw
    console sink. Replaces sys.stdout/sys.stderr wholesale so print(), logging,
    and traceback output all pass through it."""

    def __init__(self, original, sink):
        self._original = original
        self._sink = sink

    def write(self, s):
        n = self._original.write(s)
        self._original.flush()
        self._sink.write(s.encode("utf-8", errors="replace"))
        return n

    def flush(self):
        self._original.flush()

    def __getattr__(self, name):
        return getattr(self._original, name)


_console_sink = RawConsoleSink()  # creates/truncates logs/console.raw
_real_stdout = sys.stdout  # pre-wrap, used by the bot.py output pump
sys.stdout = _TeeStream(sys.stdout, _console_sink)
sys.stderr = _TeeStream(sys.stderr, _console_sink)

# Must install the tee before setup_logging(): logging.StreamHandler() snapshots
# sys.stderr at construction, so installing the tee later would bypass it.
setup_logging(os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger("run")


class ProcessSupervisor:
    """Owns a child process: spawns it, watches it, and decides whether a dead
    child gets restarted (crash) or left alone (clean exit / user stop).

    Subclasses supply the command to run and how the child prefers to be stopped.
    """

    # Used in log lines, e.g. "Starting bot...".
    label = "process"

    # Windows only. True for children that install their own SIGBREAK handler and
    # shut down cleanly on it. A JVM does not: CTRL_BREAK_EVENT makes it print a
    # thread dump and keep running, so Lavalink leaves this False.
    stops_on_ctrl_break = False

    def __init__(self, sink, host_stdout):
        self.process = None
        self.status = "stopped"  # stopped | stopping | running | crashed_retrying
        self.sink = sink
        self.host_stdout = host_stdout
        self._lock = asyncio.Lock()

    def command(self) -> list[str]:
        raise NotImplementedError

    def cwd(self) -> str | None:
        return None

    def env(self) -> dict:
        return dict(os.environ)

    async def start(self):
        async with self._lock:
            if self.status in ("running", "crashed_retrying"):
                return False
            await self._spawn()
            return True

    async def stop(self):
        async with self._lock:
            proc = self.process
            if proc is None or proc.returncode is not None:
                self.status = "stopped"
                self.process = None
                return False
            # Set before _terminate, not after. Other tabs should see "stopping"
            # during the graceful shutdown instead of "stopped" too early.
            self.status = "stopping"
            await self._terminate(proc)
            self.status = "stopped"
            self.process = None
            return True

    async def restart(self):
        await self.stop()
        await self.start()

    async def _spawn(self):
        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0
        logger.info(f"Starting {self.label}...")
        self.process = await asyncio.create_subprocess_exec(
            *self.command(), creationflags=creationflags, env=self.env(), cwd=self.cwd(),
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
        )
        self.status = "running"
        asyncio.create_task(self._pump_output(self.process))
        asyncio.create_task(self._watch(self.process))

    async def _terminate(self, proc):
        if sys.platform == "win32" and self.stops_on_ctrl_break:
            # The child is spawned in its own process group specifically so it can
            # be signalled independently of run.py's own console/Ctrl+C handling.
            proc.send_signal(signal.CTRL_BREAK_EVENT)
        else:
            proc.terminate()
        try:
            await asyncio.wait_for(proc.wait(), timeout=15)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()

    async def _pump_output(self, proc):
        """Forwards the child's merged stdout+stderr to the real host stdout and
        to the raw console sink. Reads in chunks, not lines, to preserve \\r bytes."""
        try:
            while True:
                chunk = await proc.stdout.read(4096)
                if not chunk:
                    break
                self.host_stdout.buffer.write(chunk)
                self.host_stdout.buffer.flush()
                self.sink.write(chunk)
        except Exception:
            logger.exception(f"Error pumping {self.label} output")

    async def _watch(self, proc):
        returncode = await proc.wait()
        if self.process is not proc:
            # Superseded by a newer spawn, e.g. stop+start raced the watcher. Ignore.
            return

        if self.status in ("stopped", "stopping"):
            # stop() is already handling this same proc via the same proc.wait().
            # Let it own the status transition instead of racing it here.
            self.process = None
            return

        if returncode == 0:
            logger.info(f"{self.label.capitalize()} stopped cleanly (exit code 0). Not restarting.")
            self.status = "stopped"
            self.process = None
            return

        logger.warning(f"{self.label.capitalize()} stopped (exit code {returncode}). Restarting in 5 seconds...")
        self.status = "crashed_retrying"
        self.process = None
        await asyncio.sleep(5)
        async with self._lock:
            if self.status == "crashed_retrying":
                await self._spawn()


class BotSupervisor(ProcessSupervisor):
    label = "bot"
    stops_on_ctrl_break = True

    def command(self):
        return [sys.executable, "bot.py"]

    def env(self):
        # Piped (not a real console) means PEP 528's UTF-8-for-console default no
        # longer applies; force UTF-8 explicitly to match what the sink expects.
        return {**os.environ, "PYTHONIOENCODING": "utf-8"}


class LavalinkSupervisor(ProcessSupervisor):
    """Runs the Lavalink node the music cogs connect to.

    Optional: with no LAVALINK_DIR configured, or the jar not installed there,
    the node is simply never started and the music commands report themselves as
    unavailable. The rest of the bot is unaffected.
    """

    label = "lavalink"

    def __init__(self, sink, host_stdout):
        super().__init__(sink, host_stdout)
        directory = os.getenv("LAVALINK_DIR")
        self.directory = Path(directory).expanduser() if directory else None

        # The readiness probe targets whatever LAVALINK_URI points at, so changing
        # the port in application.yml and .env doesn't leave it polling the old one.
        parsed = urlparse(os.getenv("LAVALINK_URI") or "http://127.0.0.1:2333")
        self.host = parsed.hostname or "127.0.0.1"
        self.port = parsed.port or 2333

    @property
    def jar(self) -> Path | None:
        return self.directory / "Lavalink.jar" if self.directory else None

    def unavailable_reason(self) -> str | None:
        """Why the node can't be started, or None if it can."""
        if not self.directory:
            return "LAVALINK_DIR is not set"
        if not self.jar.is_file():
            return f"no Lavalink.jar in {self.directory}"
        if not (self.directory / "application.yml").is_file():
            return f"no application.yml in {self.directory}"
        if not shutil.which("java"):
            return "java is not on PATH"
        return None

    def command(self):
        # -Xmx caps the heap so a long uptime can't let the JVM balloon on a box
        # that is also running the bot and the dashboard.
        return [shutil.which("java"), "-Xmx512M", "-jar", str(self.jar)]

    def cwd(self):
        # Lavalink resolves application.yml, plugins/ and logs/ relative to cwd.
        return str(self.directory)

    async def wait_until_ready(self, timeout: float = 90):
        """Blocks until the node accepts connections, so the bot doesn't come up
        swinging at a port that isn't listening yet. Returns whether it did."""
        deadline = asyncio.get_running_loop().time() + timeout
        while asyncio.get_running_loop().time() < deadline:
            if self.status not in ("running", "crashed_retrying"):
                return False
            try:
                _, writer = await asyncio.open_connection(self.host, self.port)
                writer.close()
                await writer.wait_closed()
                logger.info("Lavalink is accepting connections")
                return True
            except OSError:
                await asyncio.sleep(1)
        logger.warning(f"Lavalink did not become ready within {timeout:.0f}s, starting the bot anyway")
        return False


class WebState:
    """Hot-reload bookkeeping for web.py's uvicorn server, kept outside the
    web module itself since /web/reload replaces the module via importlib.reload."""

    def __init__(self):
        self.web_server = None
        self.web_epoch = 0
        # Serializes /web/reload attempts so a double-click can't race two
        # concurrent reloads against each other and each other's server refs.
        self.reload_lock = asyncio.Lock()
        # Bumped on every cog load/unload/reload so other tabs notice and refresh.
        self.cogs_epoch = 0
        # Transient badges are stored as deadlines, not rendered flags, so their
        # lifetime survives the surrounding region being re-rendered.
        self.cog_badges = {}  # extension -> (deadline, error or None)
        self.last_sync = None  # (deadline, count, error)
        self.started_deadline = None
        self.bot_was_ready = None  # None until first observed
        # Set by main(), not read yet. Groundwork for a Lavalink status row on the
        # dashboard alongside the bot's. Carried on the state rather than added to
        # web.start()'s signature, which /web/reload also calls.
        self.lavalink = None


async def main():
    supervisor = BotSupervisor(_console_sink, _real_stdout)
    lavalink = LavalinkSupervisor(_console_sink, _real_stdout)
    web_state = WebState()
    web_state.lavalink = lavalink

    # Started before the bot so the node is listening by the time the music cog
    # tries to connect. A missing or unconfigured install is not fatal.
    reason = lavalink.unavailable_reason()
    if reason:
        logger.warning(f"Lavalink not started ({reason}). Music commands will be unavailable.")
    else:
        await lavalink.start()
        await lavalink.wait_until_ready()

    await supervisor.start()

    # Backgrounded, not awaited directly: /web/reload tears this task down and starts
    # a fresh one in its place, and that must not end run.py's own lifetime.
    web_task = asyncio.create_task(web.start(supervisor, web_state))
    web_task.add_done_callback(web._log_task_exception)

    try:
        await asyncio.Future()  # run until interrupted (Ctrl+C / CTRL_BREAK_EVENT)
    finally:
        # Bot first: it should leave its voice channels before the node it is
        # streaming through goes away.
        await supervisor.stop()
        await lavalink.stop()
        _console_sink.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Stopped.")
