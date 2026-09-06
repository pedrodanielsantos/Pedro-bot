import logging

import discord
import wavelink

from config.constants import MUSIC_FALLBACK_SOURCES, MUSIC_FALLBACK_TOLERANCE
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
    player: wavelink.Player | None = interaction.guild.voice_client
    if not player or not player.connected:
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


async def find_replacement(track: wavelink.Playable) -> wavelink.Playable | None:
    """A stand-in for a track the node refused to stream, or None if there isn't one.

    YouTube Music playlists carry entries no client can play: removed, region
    locked, or login walled. The same recording is usually up elsewhere, so the
    author and title are re-searched against MUSIC_FALLBACK_SOURCES.
    """
    # A failed live stream has no fixed recording to substitute, and its length
    # is meaningless, so there is nothing to match a candidate against.
    if track.is_stream:
        return None

    query = " ".join(part for part in (track.author, track.title) if part).strip()
    if not query:
        return None

    for source in MUSIC_FALLBACK_SOURCES:
        try:
            results = await wavelink.Playable.search(query, source=source)
        except Exception:
            logger.warning(f"Fallback search on {source} failed for {query!r}", exc_info=True)
            continue

        if isinstance(results, wavelink.Playlist):
            continue

        for candidate in results:
            # Same id means the same unplayable item, just found again.
            if candidate.identifier == track.identifier or candidate.is_stream:
                continue
            # Length is the cheap signal that a result is the same recording
            # rather than a remix, a live version or an hour long mix.
            if abs(candidate.length - track.length) <= MUSIC_FALLBACK_TOLERANCE * 1000:
                return candidate

    return None


def progress_bar(position: int, length: int, width: int = 20) -> str:
    """A text scrubber for the currently playing track."""
    if length <= 0:
        return ""
    filled = min(width - 1, int(position / length * width))
    return "─" * filled + "🔘" + "─" * (width - filled - 1)
