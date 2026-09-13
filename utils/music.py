import asyncio
import logging
import time
from collections import deque
from collections.abc import Container
from dataclasses import dataclass

import discord
import wavelink

from config.constants import (
    MUSIC_AUTOCOMPLETE_LIMIT,
    MUSIC_FALLBACK_SOURCES,
    MUSIC_FALLBACK_TOLERANCE,
    MUSIC_MISS_LIMIT,
    MUSIC_PREFETCH,
    MUSIC_SEARCH_CACHE,
    MUSIC_SEARCH_CACHE_TTL,
    MUSIC_SEARCH_SOURCES,
)
from db.database import get_music_dj_role
from utils.errors import UserError

logger = logging.getLogger("music")

# Sources that stream without a meaningful length, so a progress bar or a
# remaining-time estimate would be nonsense for them.
LIVE_LABEL = "🔴 Live"


def node_ready() -> bool:
    """Whether a Lavalink node is connected and able to take requests.

    False whenever the node is missing or still starting, which is the normal
    state on a host where Lavalink was never installed.
    """
    try:
        node = wavelink.Pool.get_node()
    except (wavelink.InvalidNodeException, RuntimeError):
        return False
    return node.status is wavelink.NodeStatus.CONNECTED


def require_node():
    """Raises UserError unless a node is connected."""
    if not node_ready():
        raise UserError("Music is temporarily unavailable, the audio node is offline.")


def active_player(guild: discord.Guild | None) -> wavelink.Player | None:
    """The guild's connected music player, if it has one.

    A guild has a single voice client, and the owner-only ç!join test connection
    occupies the same slot without being a player. Anything that isn't one reads
    here as nothing playing, so the music commands leave it alone.
    """
    player = guild.voice_client if guild else None
    if not isinstance(player, wavelink.Player) or not player.connected:
        return None
    return player


def require_voice(interaction: discord.Interaction) -> discord.VoiceChannel:
    """The voice channel the caller is in."""
    voice = getattr(interaction.user, "voice", None)
    if not voice or not voice.channel:
        raise UserError("You must be connected to a voice channel.")
    return voice.channel


def require_player(interaction: discord.Interaction) -> wavelink.Player:
    """The guild's active player, if the caller is allowed to command it.

    Being in the same channel is required so someone in another channel can't
    skip or stop what a different group is listening to.
    """
    player = active_player(interaction.guild)
    if player is None:
        raise UserError("I'm not playing anything right now.")

    voice = getattr(interaction.user, "voice", None)
    if not voice or not voice.channel or voice.channel.id != player.channel.id:
        raise UserError(f"You must be in {player.channel.mention} to use that.")

    return player


async def require_dj(interaction: discord.Interaction, player: wavelink.Player):
    """Gate on the guild's DJ role for actions that affect everyone listening.

    Open to all when no DJ role is configured. Manage Server always passes, and
    so does being the only listener, since there is nobody else to disrupt.
    """
    role_id = await get_music_dj_role(interaction.guild_id)
    if role_id is None:
        return

    permissions = getattr(interaction.user, "guild_permissions", None)
    if permissions and permissions.manage_guild:
        return

    listeners = [m for m in player.channel.members if not m.bot]
    if listeners == [interaction.user]:
        return

    if any(role.id == role_id for role in getattr(interaction.user, "roles", [])):
        return

    role = interaction.guild.get_role(role_id)
    name = role.name if role else "DJ"
    raise UserError(f"You need the **{name}** role to do that while others are listening.")


def format_track_length(milliseconds: int) -> str:
    """Formats a playback time as m:ss, or h:mm:ss past an hour.

    Separate from utils.duration.format_duration(), which renders "3m 42s"
    where music conventionally reads "3:42". Lavalink works in milliseconds.
    """
    total_seconds = max(0, milliseconds) // 1000
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)

    if hours:
        return f"{hours}:{minutes:02d}:{seconds:02d}"
    return f"{minutes}:{seconds:02d}"


def track_length(track: wavelink.Playable) -> str:
    """A track's duration, or a live marker for endless streams."""
    return LIVE_LABEL if track.is_stream else format_track_length(track.length)


def format_track(track: wavelink.Playable, *, with_author: bool = True) -> str:
    """A track as a markdown link with its author and duration."""
    # Brackets in a title would otherwise break out of the markdown link.
    title = track.title.replace("[", "(").replace("]", ")")
    line = f"[{title}]({track.uri})" if track.uri else title
    if with_author and track.author:
        line += f" by **{track.author}**"
    return f"{line} `{track_length(track)}`"


def parse_position(value: str) -> int:
    """Parses a seek position like "90", "1:30" or "1:02:15" into milliseconds.

    Deliberately not utils.duration.parse_duration: that reads "1m30s" style
    input, where a seek is conventionally typed as a timestamp.
    """
    parts = value.strip().split(":")
    if len(parts) > 3 or not all(part.strip().isdigit() for part in parts if part.strip() != ""):
        raise UserError("Invalid position. Use a timestamp like `90`, `1:30` or `1:02:15`.")

    try:
        numbers = [int(part) for part in parts]
    except ValueError:
        raise UserError("Invalid position. Use a timestamp like `90`, `1:30` or `1:02:15`.")

    # Right-aligned so "1:30" reads as minutes:seconds, not hours:minutes.
    seconds = 0
    for number in numbers:
        seconds = seconds * 60 + number
    return seconds * 1000


@dataclass(frozen=True)
class PendingTrack:
    """A track known only by its metadata, still to be found on a playable source.

    Spotify links produce these, since such a link carries no audio and every
    track has to be searched for elsewhere. Nothing here is Spotify specific, so
    another metadata-only source can queue them the same way.
    """

    title: str
    artists: str
    duration: int  # milliseconds, matching Playable.length

    # Named after the Playable attributes format_track reads, so a pending track
    # renders through it unchanged. No uri, so it shows as plain text.
    uri = None
    is_stream = False

    @property
    def author(self) -> str:
        return self.artists

    @property
    def length(self) -> int:
        return self.duration

    @property
    def query(self) -> str:
        return f"{self.artists} {self.title}".strip()


# Results of the /play and /insert query search, keyed by query. Playlists are
# left out: only URLs reach them, URLs never autocomplete, and they're the
# largest thing we'd hold.
_search_cache: dict[str, tuple[float, list]] = {}
# Running searches, so overlapping keystrokes await one request instead of several.
_search_inflight: dict[str, asyncio.Task] = {}


def _cache_key(query: str) -> str:
    return query.strip().casefold()


def cached_search(query: str) -> list | None:
    """A query's cached results, or None if never searched or aged out."""
    key = _cache_key(query)
    entry = _search_cache.get(key)
    if entry is None:
        return None
    expiry, results = entry
    if expiry <= time.monotonic():
        del _search_cache[key]
        return None
    return results


def _best_cached(key: str, match) -> list | None:
    """Results for the longest unexpired query the match accepts, as the most
    typed and so the closest to what is being asked for."""
    now = time.monotonic()
    best: tuple[str, list] | None = None
    for candidate, (expiry, results) in _search_cache.items():
        if expiry <= now or not match(candidate):
            continue
        if best is None or len(candidate) > len(best[0]):
            best = (candidate, results)
    return None if best is None else best[1]


def backspaced_search(query: str) -> list | None:
    """Results already held for a longer query this one is a prefix of.
    Backspacing is text being edited rather than a query someone means, so it's
    answered from what they were just shown instead of asking the node."""
    key = _cache_key(query)
    return _best_cached(key, lambda candidate: candidate.startswith(key))


def nearest_search(query: str) -> list | None:
    """Results for the closest query already searched, for a keystroke with no
    entry of its own. Either side may be the prefix, since this is a last resort
    once the search itself hasn't landed in time."""
    key = _cache_key(query)
    return _best_cached(key, lambda c: c.startswith(key) or key.startswith(c))


def _drop_exception(task: asyncio.Task):
    """Consumes a failure nobody stayed to await, which asyncio would warn about.
    Waiting callers still get it raised."""
    if not task.cancelled():
        task.exception()


async def _run_search(key: str, query: str) -> list:
    try:
        results = await wavelink.Playable.search(query)
    finally:
        # Dropped before caching, so a failure isn't cached and the next attempt
        # retries.
        _search_inflight.pop(key, None)

    if not isinstance(results, wavelink.Playlist):
        # Oldest first, since a dict keeps insertion order. Trimmed to what
        # either caller actually reads.
        while len(_search_cache) >= MUSIC_SEARCH_CACHE:
            del _search_cache[next(iter(_search_cache))]
        expiry = time.monotonic() + MUSIC_SEARCH_CACHE_TTL
        _search_cache[key] = (expiry, list(results[:MUSIC_AUTOCOMPLETE_LIMIT]))
    return results


async def cached_or_search(query: str):
    """Searches the node, sharing one request among callers of the same query.
    Raises whatever the search raises."""
    results = cached_search(query)
    if results is not None:
        return results

    key = _cache_key(query)
    task = _search_inflight.get(key)
    if task is None:
        task = asyncio.create_task(_run_search(key, query))
        task.add_done_callback(_drop_exception)
        _search_inflight[key] = task
    # Shielded, so a caller that gives up doesn't cancel the search for the
    # others, or for the cache entry a later keystroke wants.
    return await asyncio.shield(task)


def search_author(track: wavelink.Playable) -> str:
    """A track's author as a person would search for it.

    YouTube's auto-generated artist channels are named "Artist - Topic", and that
    suffix appears verbatim in the author of everything they host. Searching it
    back matches only the same auto-generated uploads, which are the ones that
    tend to be unplayable in the first place.
    """
    author = (track.author or "").strip()
    if author.lower().endswith(" - topic"):
        author = author[: -len(" - topic")].strip()
    return author


async def search_matching(
    query: str, length: int, sources: tuple[str, ...], *, exclude: Container[str] = ()
) -> wavelink.Playable | None:
    """The first result across sources close enough in length to be the same recording.

    Length is the cheap signal that a candidate isn't a remix, a live version or
    an hour long mix. exclude drops identifiers already known to be unplayable,
    so a repeated search walks past them to the next candidate instead of
    returning the same dead result.
    """
    if not query:
        return None

    for source in sources:
        try:
            results = await wavelink.Playable.search(query, source=source)
        except Exception:
            logger.warning(f"Search on {source} failed for {query!r}", exc_info=True)
            continue

        if isinstance(results, wavelink.Playlist):
            continue

        for candidate in results:
            if candidate.is_stream or candidate.identifier in exclude:
                continue
            if abs(candidate.length - length) <= MUSIC_FALLBACK_TOLERANCE * 1000:
                return candidate

    return None


async def find_replacement(
    track: wavelink.Playable, *, exclude: Container[str] = ()
) -> wavelink.Playable | None:
    """A stand-in for a track the node refused to stream, or None if there isn't one.

    YouTube Music playlists carry entries no client can play: removed, region
    locked, or login walled. The same recording is usually up elsewhere, so the
    author and title are re-searched against MUSIC_FALLBACK_SOURCES.

    exclude carries every identifier already tried for this track, so a stand-in
    that itself fails leads to the next candidate rather than back to a known
    dead one. It must contain the track's own id.
    """
    # A failed live stream has no fixed recording to substitute, and its length
    # is meaningless, so there is nothing to match a candidate against.
    if track.is_stream:
        return None

    query = " ".join(part for part in (search_author(track), track.title) if part).strip()
    return await search_matching(query, track.length, MUSIC_FALLBACK_SOURCES, exclude=exclude)


async def resolve_pending(track: PendingTrack) -> wavelink.Playable | None:
    """A playable source for a metadata-only track, or None if no source has it."""
    return await search_matching(track.query, track.duration, MUSIC_SEARCH_SOURCES)


def pending_tracks(player: wavelink.Player) -> deque:
    """The player's queued tail, created on first use.

    Holds PendingTrack, plus any already playable track pushed back out of the
    queue by a reorder. fill_queue passes those through without searching again.
    """
    pending = getattr(player, "pending_tracks", None)
    if pending is None:
        pending = player.pending_tracks = deque()
    return pending


def queued_tracks(player: wavelink.Player) -> list:
    """Everything queued, resolved first, then what is still to be looked up.

    What /queue numbers and every command addressing a position counts, so the
    tail of a Spotify playlist isn't treated as though it weren't queued yet.
    """
    return list(player.queue) + list(pending_tracks(player))


async def fill_queue(player: wavelink.Player) -> list[wavelink.Playable]:
    """Resolves pending tracks until MUSIC_PREFETCH of them sit in the queue.

    Called once when a link is queued and again as each track starts, so a long
    playlist costs a search or two per track played rather than hundreds up
    front. Returns what it added, in order.
    """
    pending = pending_tracks(player)
    if not pending:
        return []

    # Two track starts, or a start racing a /play, would otherwise resolve the
    # same entries twice and queue them out of order.
    lock = getattr(player, "pending_lock", None)
    if lock is None:
        lock = player.pending_lock = asyncio.Lock()

    added = []
    misses = 0
    async with lock:
        while pending and player.connected and player.queue.count < MUSIC_PREFETCH:
            track = pending.popleft()
            # Already playable, so it only has to move across: a reorder puts
            # resolved tracks back here to keep one order across both.
            if not isinstance(track, PendingTrack):
                player.queue.put(track)
                added.append(track)
                continue

            resolved = await resolve_pending(track)

            if resolved is None:
                logger.warning(f"No source had {track.query!r}, skipping it")
                misses += 1
                # A run this long means every search is failing, not that the
                # tracks are obscure. The rest is dropped rather than left
                # pending, which would strand it once playback runs out.
                if misses >= MUSIC_MISS_LIMIT:
                    logger.warning(f"Dropping {len(pending)} unresolved tracks after {misses} misses")
                    pending.clear()
                continue

            misses = 0
            player.queue.put(resolved)
            added.append(resolved)

    return added


def progress_bar(position: int, length: int, width: int = 20) -> str:
    """A text scrubber for the currently playing track."""
    if length <= 0:
        return ""
    filled = min(width - 1, int(position / length * width))
    return "─" * filled + "🔘" + "─" * (width - filled - 1)
