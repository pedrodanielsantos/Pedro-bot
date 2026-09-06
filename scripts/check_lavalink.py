"""Diagnoses the bot's connection to the Lavalink node.

Run on the host that runs the bot:

    python scripts/check_lavalink.py

Checks the same things wavelink does, in order, printing full tracebacks where
wavelink only logs the exception's message. It exists because a failed handshake
surfaces in the bot log as an empty string, which says nothing about the cause.
"""

import asyncio
import os
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import aiohttp
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

URI = os.getenv("LAVALINK_URI")
PASSWORD = os.getenv("LAVALINK_PASSWORD")

# Any snowflake works, the node only echoes it back. Avoids needing a login.
FAKE_USER_ID = "123456789012345678"


def versions():
    print("Versions:")
    print(f"  python   {sys.version.split()[0]}")
    print(f"  aiohttp  {aiohttp.__version__}")
    for name in ("wavelink", "discord"):
        try:
            module = __import__(name)
            print(f"  {name:8} {getattr(module, '__version__', '?')}")
        except Exception as e:
            print(f"  {name:8} NOT IMPORTABLE ({e})")


async def check_rest(session: aiohttp.ClientSession):
    print("\nREST /v4/info:")
    try:
        async with session.get(f"{URI}/v4/info", headers={"Authorization": PASSWORD}) as resp:
            body = await resp.text()
            print(f"  status {resp.status}")
            if resp.status == 401:
                print("  -> LAVALINK_PASSWORD does not match application.yml")
            elif resp.status == 200:
                print(f"  ok, node responded with {len(body)} bytes")
            else:
                print(f"  body: {body[:400]}")
    except Exception:
        print("  request raised:")
        traceback.print_exc()


async def check_websocket(session: aiohttp.ClientSession):
    """The step that is actually failing for the bot."""
    ws_uri = URI.replace("http://", "ws://").replace("https://", "wss://") + "/v4/websocket"
    headers = {
        "Authorization": PASSWORD,
        "User-Id": FAKE_USER_ID,
        "Client-Name": "check_lavalink/1.0",
    }

    print(f"\nWebsocket {ws_uri}:")
    try:
        async with session.ws_connect(ws_uri, headers=headers) as ws:
            print("  connected")
            message = await asyncio.wait_for(ws.receive(), timeout=10)
            print(f"  first frame: {str(message.data)[:300]}")
    except Exception as e:
        print(f"  raised {type(e).__module__}.{type(e).__name__}: {e!r}")
        print("  full traceback:")
        traceback.print_exc()


async def main():
    if not URI or not PASSWORD:
        raise SystemExit("LAVALINK_URI or LAVALINK_PASSWORD is missing from .env")

    versions()
    print(f"\nTarget: {URI}")
    print(f"Password length: {len(PASSWORD)} characters")

    async with aiohttp.ClientSession() as session:
        await check_rest(session)
        await check_websocket(session)


if __name__ == "__main__":
    asyncio.run(main())
