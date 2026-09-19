"""Reads the metadata behind a Tidal link.

Tidal serves no audio here, so a link is only ever metadata and the track is
played from somewhere else. There are two ways to read it:

- The official API, used when TIDAL_CLIENT_ID and TIDAL_CLIENT_SECRET are set.
  It is the only way to read an album or playlist, and it reads a track too.
- The track page's schema.org JSON-LD, which answers anonymous callers and so
  keeps single tracks working with nothing configured. It carries no track list,
  so it cannot stand in for the API on a collection.

Both carry an ISRC, which is read past. YouTube Music does not index the code and
answers one with unrelated results, so searching it costs a request and risks a
wrong match that only the length check would catch.
"""

import asyncio
import json
import logging
import os
import re
import time
from dataclasses import dataclass

import aiohttp
from dotenv import load_dotenv

from config.constants import MUSIC_PLAYLIST_LIMIT
from utils.music import PendingTrack

load_dotenv()

logger = logging.getLogger("music")

# Every link kind, with or without the /browse/ segment and the listen. or www.
# subdomain. A mix is matched despite having no endpoint behind it, so the
# caller can name the kind rather than search the URL as if it were text.
# Artist links are deliberately absent: no one recording sits behind one, so it
# falls through to the ordinary search rather than being refused.
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


# The official API, from here down.

_API = "https://openapi.tidal.com/v2"
_AUTH_URL = "https://auth.tidal.com/v1/oauth2/token"
_CLIENT_ID = os.getenv("TIDAL_CLIENT_ID")
_CLIENT_SECRET = os.getenv("TIDAL_CLIENT_SECRET")

# Nothing here needs a country: only title, artists and length are read, and the
# track is played from somewhere else, so where it is licensed doesn't apply.
_ALBUM_PAGE = "/albums/{identifier}?include=items,items.artists,coverArt"
_PLAYLIST_PAGE = "/playlists/{identifier}?include=items,items.artists,coverArt"
_TRACK_PAGE = "/tracks/{identifier}?include=artists"
# What a paged link has to carry to stay useful, since the cursor URL the API
# returns asks for the items alone. The cover art came with the first page.
_PAGE_INCLUDE = "&include=items,items.artists"

# Past a burst of about eight the API refuses, and the only thing the refusal
# says is Retry-After, so one wait and one retry is the whole strategy. A second
# refusal means someone else is using the budget and the command gives up.
_RETRY_AFTER_CAP = 10  # seconds, so a long one fails the command instead of hanging

_token: str | None = None
_token_expiry = 0.0
_token_lock = asyncio.Lock()


@dataclass(frozen=True)
class TidalCollection:
    name: str
    total: int  # tracks the collection holds, which may exceed what was taken
    tracks: list[PendingTrack]
    artwork: str | None


def api_configured() -> bool:
    """Whether both credentials are set, which is what albums and playlists need."""
    return bool(_CLIENT_ID and _CLIENT_SECRET)


async def _access_token(session: aiohttp.ClientSession) -> str | None:
    """A client credentials token, minted once and reused until it expires.

    Held under a lock so a burst of commands shares one token rather than each
    minting its own, the same reason the search cache shares one request.
    """
    global _token, _token_expiry

    if not api_configured():
        return None

    async with _token_lock:
        if _token and time.monotonic() < _token_expiry:
            return _token

        try:
            async with session.post(
                _AUTH_URL,
                data={"grant_type": "client_credentials"},
                auth=aiohttp.BasicAuth(_CLIENT_ID, _CLIENT_SECRET),
                timeout=_TIMEOUT,
            ) as response:
                response.raise_for_status()
                payload = await response.json()
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            logger.warning(f"Could not get a Tidal token: {e}")
            return None

        _token = payload.get("access_token")
        # A minute short of the stated life, so a token can't expire in flight.
        _token_expiry = time.monotonic() + max(payload.get("expires_in", 0) - 60, 0)
        return _token


def _drop_token() -> None:
    """Forgets the cached token, so the next call mints a fresh one."""
    global _token, _token_expiry
    _token, _token_expiry = None, 0.0


async def _api_get(session: aiohttp.ClientSession, path: str) -> dict | None:
    """One API document, or None if it couldn't be read."""
    for attempt in (1, 2):
        token = await _access_token(session)
        if token is None:
            return None

        try:
            async with session.get(
                f"{_API}{path}",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/vnd.api+json",
                },
                timeout=_TIMEOUT,
            ) as response:
                if response.status == 429 and attempt == 1:
                    delay = response.headers.get("Retry-After")
                    delay = int(delay) if delay and delay.isdigit() else 4
                    if delay > _RETRY_AFTER_CAP:
                        logger.warning(f"Tidal asked for {delay}s, giving up on {path}")
                        return None
                    logger.info(f"Tidal rate limited, waiting {delay}s")
                    await asyncio.sleep(delay)
                    continue

                # A token can stop being accepted before it expires, if the
                # secret is rotated or the token is revoked. Dropping the
                # cached one mints a fresh one on the retry, rather than
                # failing every request until the old one would have expired.
                if response.status == 401 and attempt == 1:
                    _drop_token()
                    continue

                response.raise_for_status()
                # The API answers as application/vnd.api+json, which aiohttp
                # won't decode on its own.
                return await response.json(content_type=None)
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            logger.warning(f"Tidal API request for {path} failed: {e}")
            return None

    return None


def _artist_names(payload: dict) -> dict[str, str]:
    """Artist id to name, for every artist the document brought along."""
    return {
        item["id"]: (item.get("attributes") or {}).get("name") or ""
        for item in payload.get("included") or []
        if item.get("type") == "artists" and item.get("id")
    }


def _track_of(resource: dict, artists: dict[str, str]) -> PendingTrack | None:
    """One track resource as a PendingTrack, or None if it carries no title."""
    attributes = resource.get("attributes") or {}
    title = (attributes.get("title") or "").strip()
    if not title:
        return None

    credited = ((resource.get("relationships") or {}).get("artists") or {}).get("data") or []
    names = [artists.get(entry.get("id"), "") for entry in credited]
    return PendingTrack(
        title,
        ", ".join(name for name in names if name),
        _duration_ms(attributes.get("duration")),
    )


def _page_tracks(payload: dict) -> list[PendingTrack]:
    """A page's tracks, in the order the collection lists them.

    The included resources arrive in no useful order, so the relationship is
    what's walked and included is only the lookup. A playlist may also hold
    videos, which have no recording to search for and are passed over.
    """
    data = payload.get("data")
    if isinstance(data, dict):
        # A collection document, where the items sit under the relationship.
        order = ((data.get("relationships") or {}).get("items") or {}).get("data") or []
    else:
        order = data or []

    resources = {
        item["id"]: item
        for item in payload.get("included") or []
        if item.get("type") == "tracks" and item.get("id")
    }
    artists = _artist_names(payload)

    tracks = []
    for entry in order:
        if entry.get("type") != "tracks":
            continue
        resource = resources.get(entry.get("id"))
        if resource is None:
            continue
        track = _track_of(resource, artists)
        if track is not None:
            tracks.append(track)
    return tracks


def _cover_art(payload: dict) -> str | None:
    """The collection's largest cover image, or None if it has none.

    The relationship names which artwork is the cover, since a document can
    carry others. Sizes come in no promised order, so the widest is picked
    rather than the first, the same as the Spotify reader does.
    """
    artworks = {
        item["id"]: item
        for item in payload.get("included") or []
        if item.get("type") == "artworks" and item.get("id")
    }
    if not artworks:
        return None

    relationship = ((payload["data"].get("relationships") or {}).get("coverArt") or {})
    for entry in relationship.get("data") or []:
        resource = artworks.get(entry.get("id"))
        if resource is None:
            continue
        files = (resource.get("attributes") or {}).get("files") or []
        if files:
            return max(files, key=lambda f: (f.get("meta") or {}).get("width") or 0).get("href")
    return None


def _next_path(payload: dict) -> str | None:
    """The next page's path, or None at the end of the collection."""
    data = payload.get("data")
    if isinstance(data, dict):
        links = ((data.get("relationships") or {}).get("items") or {}).get("links") or {}
    else:
        links = payload.get("links") or {}
    return links.get("next")


async def fetch_track_api(
    session: aiohttp.ClientSession, identifier: str
) -> PendingTrack | None:
    """A track's metadata from the API, or None if it couldn't be read."""
    payload = await _api_get(session, _TRACK_PAGE.format(identifier=identifier))
    if not payload or not isinstance(payload.get("data"), dict):
        return None
    return _track_of(payload["data"], _artist_names(payload))


async def fetch_collection(
    session: aiohttp.ClientSession, kind: str, identifier: str
) -> TidalCollection | None:
    """An album or playlist's tracks, or None if it couldn't be read.

    Pages hold 20 and the cursor has to be followed one at a time, so this stops
    at MUSIC_PLAYLIST_LIMIT rather than walking a collection of any size. The
    total is reported separately, so the caller can say what was left behind.
    """
    template = _ALBUM_PAGE if kind == "album" else _PLAYLIST_PAGE
    payload = await _api_get(session, template.format(identifier=identifier))
    if not payload or not isinstance(payload.get("data"), dict):
        return None

    attributes = payload["data"].get("attributes") or {}
    # Albums title themselves, playlists name themselves.
    name = (attributes.get("title") or attributes.get("name") or "").strip() or "Unknown"
    # Playlists count videos separately, and those aren't queued.
    total = attributes.get("numberOfTrackItems")
    if total is None:
        total = attributes.get("numberOfItems") or 0

    # Read before paging, since only the first page is asked for the cover.
    artwork = _cover_art(payload)
    tracks = _page_tracks(payload)
    path = _next_path(payload)
    while path and len(tracks) < MUSIC_PLAYLIST_LIMIT:
        payload = await _api_get(session, path + _PAGE_INCLUDE)
        if not payload:
            # Whatever was read still plays, so a page that fails mid-collection
            # shortens it rather than losing the command.
            logger.warning(f"Tidal {kind} {identifier} stopped paging at {len(tracks)} tracks")
            break
        tracks += _page_tracks(payload)
        path = _next_path(payload)

    if tracks and not any(track.artists for track in tracks):
        # items.artists is undocumented, so it going quiet is a real possibility.
        # A title alone still searches, just less precisely, so this is logged
        # rather than treated as a failure.
        logger.warning(f"No artists in the Tidal response for {kind} {identifier}")

    return TidalCollection(
        name, max(total, len(tracks)), tracks[:MUSIC_PLAYLIST_LIMIT], artwork
    )
