"""Reads a YouTube playlist through the YouTube Data API.

Used when YOUTUBE_API_KEY is set. The node reads a playlist a page at a time
and stops at youtubePlaylistLoadLimit pages, so a long one arrives cut short.
The API lists the whole playlist, and each track is then loaded from the node
by its own link as its turn comes.
"""

import asyncio
import logging
import os
import re
import ssl
from dataclasses import dataclass
from urllib.parse import parse_qs, urlsplit

import aiohttp
import certifi
from dotenv import load_dotenv

from config.constants import MUSIC_YOUTUBE_LIMIT
from utils.music.playback import PendingTrack

load_dotenv()

logger = logging.getLogger("music")

_API = "https://www.googleapis.com/youtube/v3"
_HOSTS = ("youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com", "youtu.be")
# Left to the node: radios and mixes, and the lists utils/music/playback.py also reads past.
_NODE_LISTS = ("RD", "LL", "WL", "LM")
_PAGE_SIZE = 50  # the most either endpoint returns per request
_CONCURRENCY = 5  # duration requests in flight at once
# ISO 8601, as in PT3M28S. Days appear on a recording over 24 hours.
_DURATION_RE = re.compile(r"^P(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?)?$")
_TIMEOUT = aiohttp.ClientTimeout(total=10)

# certifi's bundle, as utils/music/spotify.py uses, so the host's store isn't relied on.
_SSL = ssl.create_default_context(cafile=certifi.where())


@dataclass(frozen=True)
class YoutubePlaylist:
    name: str
    total: int  # entries the playlist reports, unavailable ones included
    tracks: list[PendingTrack]
    artwork: str | None


def youtube_configured() -> bool:
    return bool(os.getenv("YOUTUBE_API_KEY"))


def parse_youtube_playlist(text: str) -> tuple[str, bool] | None:
    """The (playlist id, is YouTube Music) of a YouTube link carrying a list the
    API can read, or None."""
    parts = urlsplit(text.strip())
    if parts.scheme not in ("http", "https") or parts.hostname not in _HOSTS:
        return None

    lists = parse_qs(parts.query).get("list")
    if not lists or lists[0].startswith(_NODE_LISTS):
        return None
    return lists[0], parts.hostname == "music.youtube.com"


def _duration_ms(value: str | None) -> int:
    """An ISO 8601 duration in milliseconds, or 0 if it can't be read."""
    match = _DURATION_RE.match(value or "")
    if not match:
        return 0
    days, hours, minutes, seconds = (int(part or 0) for part in match.groups())
    return (((days * 24 + hours) * 60 + minutes) * 60 + seconds) * 1000


def _artwork(snippet: dict) -> str | None:
    """The widest thumbnail, since the sizes offered vary by video."""
    thumbnails = (snippet.get("thumbnails") or {}).values()
    if not thumbnails:
        return None
    return max(thumbnails, key=lambda image: image.get("width") or 0).get("url")


async def _get(session: aiohttp.ClientSession, path: str, params: dict) -> dict | None:
    """One API response, or None if the request failed."""
    try:
        async with session.get(
            f"{_API}/{path}",
            params=params,
            # Sent as a header, so the key never lands in a logged URL.
            headers={"X-Goog-Api-Key": os.getenv("YOUTUBE_API_KEY") or ""},
            timeout=_TIMEOUT,
            ssl=_SSL,
        ) as response:
            payload = await response.json(content_type=None)
            if response.status != 200:
                errors = ((payload or {}).get("error") or {}).get("errors") or [{}]
                logger.warning(
                    f"YouTube API {path} answered {response.status}: {errors[0].get('reason')}"
                )
                return None
            return payload
    except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as e:
        logger.warning(f"YouTube API request for {path} failed: {e}")
        return None


async def _durations(session: aiohttp.ClientSession, video_ids: list[str]) -> dict[str, int]:
    """Video id to length in milliseconds. The playlist listing carries none."""
    limit = asyncio.Semaphore(_CONCURRENCY)

    async def chunk(ids: list[str]) -> dict[str, int]:
        async with limit:
            payload = await _get(
                session, "videos", {"part": "contentDetails", "id": ",".join(ids)}
            )
        return {
            item["id"]: _duration_ms((item.get("contentDetails") or {}).get("duration"))
            for item in (payload or {}).get("items") or []
            if item.get("id")
        }

    chunks = await asyncio.gather(*(
        chunk(video_ids[start:start + _PAGE_SIZE])
        for start in range(0, len(video_ids), _PAGE_SIZE)
    ))
    return {video_id: length for found in chunks for video_id, length in found.items()}


async def fetch_playlist(
    session: aiohttp.ClientSession, playlist_id: str, *, music: bool = False
) -> YoutubePlaylist | None:
    """A playlist's tracks, or None if it couldn't be read.

    Returns None rather than raising, so the caller can hand the link to the
    node instead. Stops at MUSIC_YOUTUBE_LIMIT, with the playlist's own count
    reported separately so the caller can say what was left behind.

    music links each track to music.youtube.com, which utils/music/playback.py loads
    with the YouTube Music listing's artist and art.
    """
    header = await _get(session, "playlists", {"part": "snippet", "id": playlist_id})
    if not header or not header.get("items"):
        return None
    snippet = header["items"][0].get("snippet") or {}
    name = (snippet.get("title") or "").strip() or "Unknown"

    host = "music.youtube.com" if music else "www.youtube.com"
    entries: list[tuple[str, str, str]] = []  # video id, title, channel
    total = 0
    token = None
    while len(entries) < MUSIC_YOUTUBE_LIMIT:
        params = {"part": "snippet", "playlistId": playlist_id, "maxResults": _PAGE_SIZE}
        if token:
            params["pageToken"] = token
        page = await _get(session, "playlistItems", params)
        if not page:
            if not entries:
                return None
            # Whatever was read still plays, so a page that fails shortens the
            # playlist rather than losing the command.
            logger.warning(f"YouTube playlist {playlist_id} stopped paging at {len(entries)} tracks")
            break

        total = (page.get("pageInfo") or {}).get("totalResults") or total
        for item in page.get("items") or []:
            item_snippet = item.get("snippet") or {}
            video_id = (item_snippet.get("resourceId") or {}).get("videoId")
            channel = item_snippet.get("videoOwnerChannelTitle")
            title = (item_snippet.get("title") or "").strip()
            # A deleted or private video is listed without its channel.
            if not video_id or not channel or not title:
                continue
            # Auto-generated artist channels are named "Artist - Topic".
            if channel.lower().endswith(" - topic"):
                channel = channel[: -len(" - topic")]
            entries.append((video_id, title, channel.strip()))

        token = page.get("nextPageToken")
        if not token:
            break

    entries = entries[:MUSIC_YOUTUBE_LIMIT]
    lengths = await _durations(session, [video_id for video_id, _, _ in entries])
    tracks = [
        PendingTrack(
            title,
            channel,
            lengths.get(video_id, 0),
            link=f"https://{host}/watch?v={video_id}",
        )
        for video_id, title, channel in entries
    ]
    return YoutubePlaylist(name, max(total, len(tracks)), tracks, _artwork(snippet))
