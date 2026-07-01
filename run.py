import subprocess
import sys
import time
import signal
from datetime import datetime


def ts():
    return datetime.now().strftime("%d/%m/%Y %H:%M:%S")


while True:
    print(f"[{ts()}] Starting bot...")

    signal.signal(signal.SIGINT, signal.SIG_IGN)
    result = subprocess.run([sys.executable, "bot.py"])
    signal.signal(signal.SIGINT, signal.default_int_handler)

    print(f"\n[{ts()}] Bot stopped (exit code {result.returncode}). Restarting in 5 seconds... (Ctrl+C to stop)")

    try:
        time.sleep(5)
    except KeyboardInterrupt:
        print(f"\n[{ts()}] Stopped.")
        break
