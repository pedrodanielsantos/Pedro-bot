"""Reads the metadata behind a Spotify link.

Spotify serves no audio, so a link is only ever metadata and the track is played
from somewhere else. Its API needs a token the bot has no way to obtain, so the
metadata comes off the embed page, which still answers anonymous callers.
"""

import asyncio
import json
import logging
import re
import ssl
from dataclasses import dataclass

import aiohttp
import certifi

from utils.music import PendingTrack

logger = logging.getLogger("music")

# Track, album and playlist links, with or without the intl-xx segment Spotify
# adds to localized shares. A trailing ?si= tracking parameter is ignored.
_URL_RE = re.compile(
    r"https?://open\.spotify\.com/(?:intl-[a-z]{2}/)?(track|album|playlist)/([A-Za-z0-9]+)"
)

# The normal player page is an app shell whose data comes from a token-gated
# endpoint. The embed page carries the entity itself, as JSON.
_EMBED_URL = "https://open.spotify.com/embed/{kind}/{identifier}"
_NEXT_DATA_RE = re.compile(
    r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', re.DOTALL
)
_TIMEOUT = aiohttp.ClientTimeout(total=10)

# Spotify's chain roots at Certainly, a CA young enough to be missing from a
# Windows store that isn't updating its roots, where older ones are cached and
# work. Verifying against certifi's bundle instead doesn't depend on the host.
_SSL = ssl.create_default_context(cafile=certifi.where())


@dataclass(frozen=True)
class SpotifyEntity:
    kind: str  # "track", "album" or "playlist"
    name: str
    artwork: str | None
    tracks: list[PendingTrack]


def parse_spotify_url(text: str) -> tuple[str, str] | None:
    """The (kind, id) of the first Spotify link in text, or None if there isn't one."""
    match = _URL_RE.search(text)
    return (match[1], match[2]) if match else None


def _clean(text: str | None) -> str:
    # Spotify joins artist names with non-breaking spaces in trackList subtitles.
    return (text or "").replace("\xa0", " ").strip()


def _artwork(entity: dict) -> str | None:
    """The largest cover image. Sizes aren't listed in a consistent order, and
    coverArt isn't populated for tracks or albums, so this is the one to read."""
    images = (entity.get("visualIdentity") or {}).get("image") or []
    if not images:
        return None
    return max(images, key=lambda image: image.get("maxWidth") or 0).get("url")


def _tracks(entity: dict) -> list[PendingTrack]:
    """The entity's tracks. A track page holds its own metadata, not a list."""
    if entity.get("type") == "track":
        names = [_clean(artist.get("name")) for artist in entity.get("artists") or []]
        return [PendingTrack(
            _clean(entity.get("name")),
            ", ".join(name for name in names if name),
            entity.get("duration") or 0,
        )]

    return [
        PendingTrack(_clean(item.get("title")), _clean(item.get("subtitle")), item.get("duration") or 0)
        for item in entity.get("trackList") or []
        if item.get("title")
    ]


async def fetch_entity(session: aiohttp.ClientSession, kind: str, identifier: str) -> SpotifyEntity | None:
    """A Spotify link's metadata, or None if it couldn't be read.

    Returns None rather than raising: every caller treats a failure the same way
    and the reason is only useful in the log. Page data going missing is the one
    failure here that can appear without anything on this side changing.
    """
    url = _EMBED_URL.format(kind=kind, identifier=identifier)

    try:
        async with session.get(url, timeout=_TIMEOUT, ssl=_SSL) as response:
            response.raise_for_status()
            html = await response.text()
    except (aiohttp.ClientError, asyncio.TimeoutError) as e:
        logger.warning(f"Could not fetch {url}: {e}")
        return None

    match = _NEXT_DATA_RE.search(html)
    if not match:
        logger.warning(f"No embedded data in {url}, Spotify changed the page")
        return None

    try:
        entity = json.loads(match[1])["props"]["pageProps"]["state"]["data"]["entity"]
    except (json.JSONDecodeError, KeyError, TypeError) as e:
        logger.warning(f"Unexpected embed data in {url}: {e!r}")
        return None

    return SpotifyEntity(
        kind=entity.get("type") or kind,
        name=_clean(entity.get("name")) or "Unknown",
        artwork=_artwork(entity),
        tracks=_tracks(entity),
    )
