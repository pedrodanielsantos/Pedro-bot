"""Reads the metadata behind a Tidal link.

Tidal serves no audio here, so a link is only ever metadata and the track is
played from somewhere else. Its API needs a token with no documented way to
obtain one, so the metadata comes off the track page, which carries the
recording as schema.org JSON-LD and still answers anonymous callers.

The block also carries an ISRC, which is read past. YouTube Music does not index
the code and answers one with unrelated results, so searching it costs a request
and risks a wrong match that only the length check would catch.
"""

import asyncio
import json
import logging
import re

import aiohttp

from utils.music import PendingTrack

logger = logging.getLogger("music")

# Every link kind, with or without the /browse/ segment and the listen. or www.
# subdomain. Only a track page carries a recording, but the rest are matched so
# a caller can say so rather than searching the URL as if it were text.
# Artist links are deliberately absent: searching the name is the better answer.
_URL_RE = re.compile(
    r"https?://(?:(?:listen|www)\.)?tidal\.com/(?:browse/)?"
    r"(track|album|playlist|mix)/([A-Za-z0-9-]+)"
)

# Every variant of a track URL serves the same page, so one form is fetched.
_TRACK_URL = "https://tidal.com/browse/track/{identifier}"
_LD_JSON_RE = re.compile(r'<script type="application/ld\+json">(.*?)</script>', re.DOTALL)
# ISO 8601, as in PT3M28S. Hours appear on a long DJ set or live recording.
_DURATION_RE = re.compile(r"^PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?$")
_TIMEOUT = aiohttp.ClientTimeout(total=10)


def parse_tidal_url(text: str) -> tuple[str, str] | None:
    """The (kind, id) of the first Tidal link in text, or None if there isn't one."""
    match = _URL_RE.search(text)
    return (match[1], match[2]) if match else None


def _duration_ms(value: str | None) -> int:
    """An ISO 8601 duration in milliseconds, or 0 if it can't be read.

    0 means unknown, but search_matching reads it as a length to match and so
    rejects everything longer than its tolerance, which loses the track. The
    page has carried a duration every time it was checked, so this is the shape
    of a page change rather than a case to expect.
    """
    match = _DURATION_RE.match(value or "")
    if not match:
        return 0
    hours, minutes, seconds = (int(part or 0) for part in match.groups())
    return (hours * 3600 + minutes * 60 + seconds) * 1000


def _artists(by_artist) -> str:
    """The credited artists, joined. schema.org allows one object or a list."""
    if isinstance(by_artist, dict):
        by_artist = [by_artist]
    names = [
        (artist.get("name") or "").strip()
        for artist in by_artist or []
        if isinstance(artist, dict)
    ]
    return ", ".join(name for name in names if name)


def _recording(html: str) -> dict | None:
    """The MusicRecording block, or None if the page carries no usable one.

    The page holds more than one JSON-LD block and their order is not promised,
    so they are matched on type rather than taken by position.
    """
    for raw in _LD_JSON_RE.findall(html):
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict) and data.get("@type") == "MusicRecording":
            return data
    return None


async def fetch_track(session: aiohttp.ClientSession, identifier: str) -> PendingTrack | None:
    """A Tidal track's metadata, or None if it couldn't be read.

    Returns None rather than raising, like the Spotify reader: every caller
    treats a failure the same way and the reason is only useful in the log. A
    page that stops carrying JSON-LD is the one failure that can appear without
    anything on this side changing.
    """
    url = _TRACK_URL.format(identifier=identifier)

    try:
        async with session.get(url, timeout=_TIMEOUT) as response:
            response.raise_for_status()
            html = await response.text()
    except (aiohttp.ClientError, asyncio.TimeoutError) as e:
        # A dead or mistyped id is a 404 here, so this covers it too.
        logger.warning(f"Could not fetch {url}: {e}")
        return None

    recording = _recording(html)
    if recording is None:
        logger.warning(f"No recording data in {url}, Tidal changed the page")
        return None

    title = (recording.get("name") or "").strip()
    if not title:
        logger.warning(f"Recording data in {url} carries no title")
        return None

    return PendingTrack(
        title,
        _artists(recording.get("byArtist")),
        _duration_ms(recording.get("duration")),
    )
