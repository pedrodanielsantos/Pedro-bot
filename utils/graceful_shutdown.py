import asyncio
import signal

def setup_signal_handlers(bot):
    def shutdown(signal_received, frame):
        print("Gracefully shutting down...")

        # Shutdown the bot asynchronously
        asyncio.create_task(bot.close())  # Directly schedule bot.close()

        print("Shutdown process initiated.")

    # Handle Ctrl+C (SIGINT)
    signal.signal(signal.SIGINT, shutdown)

    # Handle Ctrl+Break (SIGBREAK) - Windows only
    if hasattr(signal, "SIGBREAK"):
        signal.signal(signal.SIGBREAK, shutdown)

    # Handle SIGTERM (e.g., when killed by task manager or process manager)
    signal.signal(signal.SIGTERM, shutdown)