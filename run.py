import asyncio
import logging
import os
import signal
import subprocess
import sys

import web
from utils.log import RawConsoleSink, setup_logging


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
setup_logging()
logger = logging.getLogger("run")


class BotSupervisor:
    """Owns the bot.py child process: spawns it, watches it, and decides whether
    a dead child gets restarted (crash) or left alone (clean exit / user stop)."""

    def __init__(self, sink, host_stdout):
        self.process = None
        self.status = "stopped"  # stopped | stopping | running | crashed_retrying
        self.sink = sink
        self.host_stdout = host_stdout
        self._lock = asyncio.Lock()

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
            await _terminate(proc)
            self.status = "stopped"
            self.process = None
            return True

    async def restart(self):
        await self.stop()
        await self.start()

    async def _spawn(self):
        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0
        logger.info("Starting bot...")
        # Piped (not a real console) means PEP 528's UTF-8-for-console default no
        # longer applies; force UTF-8 explicitly to match what the sink expects.
        env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
        self.process = await asyncio.create_subprocess_exec(
            sys.executable, "bot.py", creationflags=creationflags, env=env,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
        )
        self.status = "running"
        asyncio.create_task(self._pump_output(self.process))
        asyncio.create_task(self._watch(self.process))

    async def _pump_output(self, proc):
        """Forwards bot.py's merged stdout+stderr to the real host stdout and to
        the raw console sink. Reads in chunks, not lines, to preserve \\r bytes."""
        try:
            while True:
                chunk = await proc.stdout.read(4096)
                if not chunk:
                    break
                self.host_stdout.buffer.write(chunk)
                self.host_stdout.buffer.flush()
                self.sink.write(chunk)
        except Exception:
            logger.exception("Error pumping bot.py output")

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
            logger.info("Bot stopped cleanly (exit code 0). Not restarting.")
            self.status = "stopped"
            self.process = None
            return

        logger.warning(f"Bot stopped (exit code {returncode}). Restarting in 5 seconds...")
        self.status = "crashed_retrying"
        self.process = None
        await asyncio.sleep(5)
        async with self._lock:
            if self.status == "crashed_retrying":
                await self._spawn()


async def _terminate(proc):
    if sys.platform == "win32":
        # bot.py is spawned in its own process group specifically so it can be
        # signalled independently of run.py's own console/Ctrl+C handling.
        proc.send_signal(signal.CTRL_BREAK_EVENT)
    else:
        proc.terminate()
    try:
        await asyncio.wait_for(proc.wait(), timeout=15)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()


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


async def main():
    supervisor = BotSupervisor(_console_sink, _real_stdout)
    web_state = WebState()
    await supervisor.start()

    # Backgrounded, not awaited directly: /web/reload tears this task down and starts
    # a fresh one in its place, and that must not end run.py's own lifetime.
    web_task = asyncio.create_task(web.start(supervisor, web_state))
    web_task.add_done_callback(web._log_task_exception)

    try:
        await asyncio.Future()  # run until interrupted (Ctrl+C / CTRL_BREAK_EVENT)
    finally:
        await supervisor.stop()
        _console_sink.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Stopped.")
