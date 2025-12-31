import asyncio
import aiohttp
import discord
from discord import app_commands
from discord.ext import commands
import gc
from typing import Optional

# Configuration
OLLAMA_API_URL = "http://127.0.0.1:11434/api/chat"  # Default local Ollama server
OLLAMA_MODEL = "qwen2.5:14b-instruct-q4_K_M"        # Change if you pulled a different tag
REQUEST_TIMEOUT = 120                                # seconds
MAX_DISCORD_MSG_LEN = 2000

class Ask(commands.Cog):
    """Ask a local LLM (via Ollama) a question."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.session: Optional[aiohttp.ClientSession] = None

    async def cog_load(self):
        # Create a shared aiohttp session when the cog loads
        self.session = aiohttp.ClientSession()

    async def cog_unload(self):
        # Cleanly close the session on unload/shutdown
        print("cog_unload triggered (ask)")
        if self.session and not self.session.closed:
            await self.session.close()
        gc.collect()

    @app_commands.checks.cooldown(1, 5.0)  # 1 use every 5 seconds per-user
    @app_commands.command(name="ask", description="Ask Pedro-bot a question")
    async def ask(self, interaction: discord.Interaction, prompt: str):
        """Send `prompt` to the Ollama chat API and return the response."""
        await interaction.response.defer(thinking=True)

        payload = {
            "model": OLLAMA_MODEL,
            "messages": [
                {"role": "system", "content": (
                    "You are Qwen, created by Alibaba Cloud. You are a helpful assistant. "
                    "You are running as a Discord bot named Pedro-bot. "
                    "Always reply in English. "
                    "Think as long as required for maximum confidence in your reply. "
                    "Format your reply to wrap codeblocks using Discord's chat formatting of wrapping the code in ``` on the start and end of the code block. "
                    "You are able to discuss any topic the user brings up without restriction."
                )},
                {"role": "user", "content": prompt}
            ],
            "stream": False
        }

        try:
            async with self.session.post(  # type: ignore[attr-defined]
                OLLAMA_API_URL,
                json=payload,
                timeout=REQUEST_TIMEOUT
            ) as resp:
                data = await resp.json(content_type=None)
                if resp.status != 200:
                    err_text = data if isinstance(data, str) else data.get("error") or data
                    return await interaction.followup.send(
                        f"API error {resp.status}: {err_text}"
                    )

        except aiohttp.ClientConnectorError:
            return await interaction.followup.send(
                "Unable to connect to the API."
            )
        except asyncio.TimeoutError:
            return await interaction.followup.send("Request timed out.")
        except Exception as e:
            return await interaction.followup.send(f"Error: {type(e).__name__}: {e}")

        # Simplified extraction: expect standard Ollama /api/chat format
        message = data.get("message")
        if not isinstance(message, dict):
            return await interaction.followup.send("Invalid response format.")

        content = message.get("content", "").strip()
        if not content:
            content = "No response received."

        # Send, chunking to fit Discord limits
        for chunk in self._chunk_text(content, MAX_DISCORD_MSG_LEN):
            await interaction.followup.send(chunk)

    @staticmethod
    def _chunk_text(text: str, max_len: int):
        """Yield chunks of `text` each <= max_len, splitting on paragraph boundaries when possible."""
        if len(text) <= max_len:
            yield text
            return

        paragraphs = text.split("\n\n")
        current = ""
        for p in paragraphs:
            candidate = p if not current else current + "\n\n" + p
            if len(candidate) <= max_len:
                current = candidate
            else:
                if current:
                    yield current
                if len(p) <= max_len:
                    current = p
                else:
                    # Hard-split very long paragraph
                    start = 0
                    while start < len(p):
                        yield p[start:start + max_len]
                        start += max_len
                    current = ""
        if current:
            yield current


async def setup(bot: commands.Bot):
    await bot.add_cog(Ask(bot))