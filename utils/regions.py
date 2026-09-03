import asyncio
import logging

from discord.ext import commands
from discord.http import Route

from config.constants import VOICE_REGION, VOICE_REGION_AUTOMATIC
from db.database import get_user_lobby_region

logger = logging.getLogger("regions")

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

        if VOICE_REGION != VOICE_REGION_AUTOMATIC and VOICE_REGION not in fetched:
            logger.warning(f"VOICE_REGION {VOICE_REGION!r} is not a region Discord offers")

        # Discord returns these in no useful order; sort by label so autocomplete is
        # stable, with automatic pinned first.
        ordered = dict(sorted(fetched.items(), key=lambda item: item[1]))
        regions = {VOICE_REGION_AUTOMATIC: AUTOMATIC_LABEL, **ordered}
        logger.info(f"Cached {len(fetched)} voice regions from Discord")
        setattr(bot, _CACHE_ATTR, regions)
        return regions


async def default_region_for(bot: commands.Bot, user_id: int) -> str | None:
    """rtc_region for a lobby this user is creating: their saved default, else
    VOICE_REGION. None means Discord picks."""
    region = await get_user_lobby_region(user_id) or VOICE_REGION
    if region == VOICE_REGION_AUTOMATIC:
        return None

    # Discord retires regions, and VOICE_REGION is hand-written; either can leave a
    # value that would make channel creation fail. Only checked when the live list
    # is available, since an empty one means unknown rather than invalid.
    regions = await voice_regions(bot)
    if regions and region not in regions:
        logger.warning(f"Unknown voice region {region!r}, creating the lobby as automatic")
        return None

    return region
