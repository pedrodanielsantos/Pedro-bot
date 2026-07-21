import asyncio
import logging
import signal
import subprocess
import sys

import web
from utils.log import setup_logging

setup_logging()
logger = logging.getLogger("run")


class BotSupervisor:
    """Owns the bot.py child process: spawns it, watches it, and decides whether
    a dead child gets restarted (crash) or left alone (clean exit / user stop)."""

    def __init__(self):
        self.process = None
        self.status = "stopped"  # stopped | stopping | running | crashed_retrying
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

    async def _spawn(self):
        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0
        logger.info("Starting bot...")
        self.process = await asyncio.create_subprocess_exec(
            sys.executable, "bot.py", creationflags=creationflags,
        )
        self.status = "running"
        asyncio.create_task(self._watch(self.process))

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
    supervisor = BotSupervisor()
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


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Stopped.")
