import asyncio
import logging

import discord
from discord import app_commands
from discord.ext import commands
from discord.http import Route

from config.constants import VOICE_REGION_AUTOMATIC
from db.database import get_guild_lobby_region, get_user_lobby_region
from utils.errors import UserError

logger = logging.getLogger("regions")

# Discord accepts at most 25 autocomplete suggestions per response.
AUTOCOMPLETE_LIMIT = 25

# Cached on the bot, not at module level: reload_shared_modules() re-imports every
# utils.* module on a cog reload, which would drop module-level state.
_CACHE_ATTR = "_voice_regions"
_LOCK_ATTR = "_voice_regions_lock"

AUTOMATIC_LABEL = "Automatic"


async def _fetch(bot: commands.Bot) -> dict[str, str]:
    """GET /voice/regions. discord.py 2.7 removed its own helpers for this route."""
    data = await bot.http.request(Route("GET", "/voice/regions"))
    return {
        region["id"]: region["name"]
        for region in data
        if not region.get("deprecated") and not region.get("custom")
    }


async def voice_regions(bot: commands.Bot) -> dict[str, str]:
    """Region id -> display name, automatic first. Fetched once, then cached.

    Returns an empty dict if Discord can't be reached, meaning "unknown", not
    "none exist". Callers must not treat that as a region being invalid.
    """
    cached = getattr(bot, _CACHE_ATTR, None)
    if cached is not None:
        return cached

    lock = getattr(bot, _LOCK_ATTR, None)
    if lock is None:
        lock = asyncio.Lock()
        setattr(bot, _LOCK_ATTR, lock)

    async with lock:
        # Another caller may have populated the cache while this one waited.
        cached = getattr(bot, _CACHE_ATTR, None)
        if cached is not None:
            return cached

        try:
            fetched = await _fetch(bot)
        except Exception as e:
            # Nothing is cached, so the next call retries.
            logger.error(f"Failed to fetch voice regions: {e}")
            return {}

        # Discord returns these in no useful order; sort by label so autocomplete is
        # stable, with automatic pinned first.
        ordered = dict(sorted(fetched.items(), key=lambda item: item[1]))
        regions = {VOICE_REGION_AUTOMATIC: AUTOMATIC_LABEL, **ordered}
        logger.info(f"Cached {len(fetched)} voice regions from Discord")
        setattr(bot, _CACHE_ATTR, regions)
        return regions


async def region_choices(bot: commands.Bot, current: str) -> list[app_commands.Choice[str]]:
    """Autocomplete suggestions matching `current` against either label or id."""
    regions = await voice_regions(bot)
    query = current.lower()
    return [
        app_commands.Choice(name=label, value=region_id)
        for region_id, label in regions.items()
        if query in label.lower() or query in region_id
    ][:AUTOCOMPLETE_LIMIT]


async def require_region(bot: commands.Bot, region: str) -> str:
    """Checks a submitted region against the live list, returning its display label.
    Autocomplete only suggests, so commands can still receive anything."""
    regions = await voice_regions(bot)
    if not regions:
        raise UserError("Couldn't reach Discord for the region list. Please try again in a moment.")
    if region not in regions:
        typed = discord.utils.escape_markdown(region[:50])
        raise UserError(f"**{typed}** isn't a voice region. Pick one from the list.")
    return regions[region]


async def region_label(bot: commands.Bot, region: str | None) -> str | None:
    """Display name for a stored region id, for read-only views. None stays None.
    Falls back to the raw id when the live list is unavailable or the region has
    been retired, since a stored value is worth showing either way."""
    if not region:
        return None
    regions = await voice_regions(bot)
    return regions.get(region, region)


async def resolve_region(bot: commands.Bot, region: str | None) -> str | None:
    """Turns a stored region id into an rtc_region. None means Discord picks,
    which is also what an unset or retired region falls back to."""
    if not region or region == VOICE_REGION_AUTOMATIC:
        return None

    # Discord retires regions, so a value saved months ago can stop being valid and
    # would fail channel creation. Only checked when the live list is available,
    # since an empty one means unknown rather than invalid.
    regions = await voice_regions(bot)
    if regions and region not in regions:
        logger.warning(f"Unknown voice region {region!r}, falling back to automatic")
        return None

    return region


async def guild_region(bot: commands.Bot, guild_id: int) -> str | None:
    """rtc_region for this guild's lobby channels, set by /set lobbyregion."""
    return await resolve_region(bot, await get_guild_lobby_region(guild_id))


async def default_region_for(bot: commands.Bot, guild_id: int, user_id: int) -> str | None:
    """rtc_region for a lobby this user is creating: their own default, else the guild's."""
    region = await get_user_lobby_region(user_id) or await get_guild_lobby_region(guild_id)
    return await resolve_region(bot, region)
