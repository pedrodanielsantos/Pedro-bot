import asyncio
import aiohttp
import discord
from discord import app_commands
from discord.ext import commands

# Configuration
OLLAMA_API_URL = "http://127.0.0.1:11434/api/chat"  # Default local Ollama server
OLLAMA_MODEL = "mistral:7b-instruct-q4_K_M"         # Change if you pulled a different tag
REQUEST_TIMEOUT = 120                                # seconds
MAX_DISCORD_MSG_LEN = 2000

# Optional: a short “system” instruction for consistent behavior.
SYSTEM_PROMPT = (
    "Take on the role of a small, blue, alien companion for Pedro's Discord server. "
    "Be reliable and provide clear and professional answers, using formatting when needed."
)



class Ask(commands.Cog):
    """Ask a local LLM (via Ollama) a question."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.session = None  # type: aiohttp.ClientSession

    async def cog_load(self):
        # Create a shared aiohttp session when the cog loads
        self.session = aiohttp.ClientSession()

    async def cog_unload(self):
        # Cleanly close the session on unload/shutdown
        if self.session and not self.session.closed:
            await self.session.close()

    @app_commands.checks.cooldown(1, 5.0)  # 1 use every 5 seconds per-user
    @app_commands.command(name="ask", description="Ask the local LLM (Ollama) a question.")
    async def ask(self, interaction: discord.Interaction, prompt: str):
        """Send `prompt` to the Ollama chat API and return the response."""
        await interaction.response.defer(thinking=True)

        payload = {
            "model": OLLAMA_MODEL,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
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
                        f"⚠️ Ollama error (HTTP {resp.status}): `{err_text}`"
                    )

        except aiohttp.ClientConnectorError:
            return await interaction.followup.send(
                "❌ Could not connect to Ollama at `127.0.0.1:11434`. "
                "Is the server running?\nTry: `ollama serve` (and make sure the model is pulled)."
            )
        except asyncio.TimeoutError:
            return await interaction.followup.send("⏳ The request to the model timed out. Please try again.")
        except Exception as e:
            return await interaction.followup.send(f"❌ Unexpected error: `{type(e).__name__}: {e}`")

        # Simplified extraction: expect standard Ollama /api/chat format
        message = data.get("message")
        if not isinstance(message, dict):
            return await interaction.followup.send("❌ Invalid response format from Ollama.")

        content = message.get("content", "").strip()
        if not content:
            content = "*No response from the model.*"

        # Send, chunking to fit Discord limits
        for chunk in _chunk_text(content, MAX_DISCORD_MSG_LEN):
            await interaction.followup.send(chunk)


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