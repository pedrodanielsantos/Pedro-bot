import asyncio
import discord
from discord.ext import commands
import logging
import os

import wavelink

from config.constants import (
    MUSIC_ANNOUNCE_POLL,
    MUSIC_ANNOUNCE_TIMEOUT,
    MUSIC_FALLBACK_ATTEMPTS,
    MUSIC_IDLE_TIMEOUT,
    MUSIC_VOICE_RESUME_DELAY,
)
from db.database import get_guild_embed_color
from utils.embeds import error_embed
from utils.music import (
    active_player,
    announce_channel,
    fill_queue,
    find_replacement,
    format_track,
    pending_tracks,
    search_author,
)

logger = logging.getLogger("music")

# Voice closes where the channel is still there and playback should carry on.
# CALL_TERMINATED is the one a lobby region change produces. Wavelink only acts
# on 4014 itself and treats every other code as nothing to recover from.
RECOVERABLE_VOICE_CLOSES = frozenset({
    wavelink.DiscordVoiceCloseType.CALL_TERMINATED,
    wavelink.DiscordVoiceCloseType.SESSION_INVALID,
    wavelink.DiscordVoiceCloseType.SESSION_TIMEOUT,
    wavelink.DiscordVoiceCloseType.VOICE_SERVER_CRASHED,
})


def _extras_dict(track: wavelink.Playable) -> dict:
    """A track's extras as a plain dict, empty if it carries none."""
    try:
        return dict(track.extras)
    except (TypeError, ValueError):
        return {}


def _track_ref(track: wavelink.Playable) -> str:
    """A track's identifier for a log line, capped in length. A YouTube id is
    short, but a SoundCloud stand-in identifies itself by its full stream URL,
    which on its own runs longer than the rest of the line. Only there to
    correlate with the node's logs, and the title is alongside it either way."""
    identifier = track.identifier or "?"
    return identifier if len(identifier) <= 48 else f"{identifier[:48]}..."


def _fallback_depth(track: wavelink.Playable) -> int:
    """How many stand-ins deep a track already is, 0 for one queued directly.

    Rides on the track's extras, which Lavalink stores as userData and hands back
    on the events that track produces, so the count follows the chain rather than
    the player.
    """
    try:
        return int(_extras_dict(track).get("fallback_depth", 0))
    except (TypeError, ValueError):
        return 0


def _original(track: wavelink.Playable) -> tuple[str, str]:
    """Title and author of the track a stand-in replaces, or of the track itself.

    Set on the first stand-in and carried down the chain, so a stand-in for a
    stand-in still names what was queued.
    """
    extras = _extras_dict(track)
    if "original_title" in extras:
        return str(extras["original_title"]), str(extras.get("original_author", ""))
    return track.title, search_author(track)


def _cancel_announcement(player: wavelink.Player, track: wavelink.Playable | None = None):
    """Drops a pending "Now playing", only if it is for track when one is given."""
    pending = getattr(player, "announcement", None)
    if pending is None:
        return
    announced, task = pending
    if track is None or announced == track:
        task.cancel()
        player.announcement = None


def _pop_failure(player: wavelink.Player, track: wavelink.Playable) -> tuple[str, bool] | None:
    """The failure recorded for track as (detail, stuck), cleared either way."""
    failure = getattr(player, "track_failure", None)
    player.track_failure = None
    if failure is None or failure[0] != track:
        return None
    return failure[1], failure[2]


async def _wait_for_audio(player: wavelink.Player, track: wavelink.Playable) -> bool:
    """Whether the node starts sending track's audio.

    The position Lavalink reports is the timecode of the last frame handed to
    Discord, so it only moves once audio is actually going out. False if the
    track stops being the one playing first, or nothing arrives within
    MUSIC_ANNOUNCE_TIMEOUT, which a pause extends.
    """
    loop = asyncio.get_running_loop()
    deadline = loop.time() + MUSIC_ANNOUNCE_TIMEOUT
    while True:
        await asyncio.sleep(MUSIC_ANNOUNCE_POLL)
        if not player.connected:
            return False

        try:
            info = await player.node.fetch_player_info(player.guild.id)
        except Exception:
            # Nothing has reported the track failing, so announcing it is the
            # better guess than staying silent.
            logger.warning(f"Could not check playback of {_track_ref(track)}", exc_info=True)
            return True

        if info is None or info.track is None or info.track != track:
            return False
        if info.state.position > 0:
            return True

        if info.paused:
            deadline = loop.time() + MUSIC_ANNOUNCE_TIMEOUT
        elif loop.time() >= deadline:
            logger.debug(f"No audio from {_track_ref(track)} after {MUSIC_ANNOUNCE_TIMEOUT}s, not announcing it")
            return False


class MusicManager(commands.Cog):
    """Owns the connection to the Lavalink node and the playback lifecycle.

    The command cog in cogs/commands/music.py only issues player commands; every
    node concern (connecting, reconnecting, announcing tracks, disconnecting when
    idle) lives here so a reload of the commands never drops the node session.
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_load(self):
        # bot.py loads cogs before bot.start(), so on first startup the bot has
        # no user id yet and wavelink can't build its "User-Id" handshake header.
        # Connecting is deferred to on_ready in that case. A reload after startup
        # takes this branch instead, since on_ready won't fire again for it.
        if self.bot.is_ready():
            await self._connect_node()

    @commands.Cog.listener()
    async def on_ready(self):
        await self._connect_node()

    async def _connect_node(self):
        """Connects the pool, at most once. on_ready fires again on reconnects."""
        if wavelink.Pool.nodes:
            return

        uri = os.getenv("LAVALINK_URI")
        password = os.getenv("LAVALINK_PASSWORD")

        if not uri or not password:
            # Expected on a host where Lavalink was never installed. The music
            # commands report themselves as unavailable rather than erroring.
            logger.warning("LAVALINK_URI or LAVALINK_PASSWORD is not set, music is disabled")
            return

        node = wavelink.Node(
            uri=uri,
            password=password,
            # Lavalink keeps the session alive across a bot restart, so a crash
            # and respawn resumes playback instead of dropping the voice call.
            resume_timeout=60,
            inactive_player_timeout=MUSIC_IDLE_TIMEOUT,
        )

        try:
            # Bounded deliberately. Pool.connect() waits for the handshake to
            # succeed and retries internally, so an unreachable or misconfigured
            # node would otherwise hang this coroutine forever. Timing out is
            # harmless: the node stays registered and wavelink keeps retrying in
            # the background, it just stops blocking whoever called us.
            await asyncio.wait_for(
                wavelink.Pool.connect(nodes=[node], client=self.bot), timeout=30
            )
        except asyncio.TimeoutError:
            logger.error(
                f"Timed out connecting to the Lavalink node at {uri}. "
                "Retrying in the background, music is unavailable until it succeeds."
            )
        except Exception as e:
            # Never fatal: the bot must load with music unavailable rather than
            # failing the whole cog and leaving the extension list short.
            logger.error(f"Could not connect to the Lavalink node at {uri}: {e}")

    async def cog_unload(self):
        await wavelink.Pool.close()

    @commands.Cog.listener()
    async def on_wavelink_node_ready(self, payload: wavelink.NodeReadyEventPayload):
        logger.info(
            f"Lavalink node {payload.node.identifier} ready "
            f"(session {payload.session_id}, resumed={payload.resumed})"
        )

    @commands.Cog.listener()
    async def on_wavelink_websocket_closed(self, payload: wavelink.WebsocketClosedEventPayload):
        """Discord dropped the voice connection, e.g. after /region moved the lobby.

        Usually Discord reissues a voice server and playback carries on, so this
        waits for one player update before deciding anything. A node that came
        back reports a real ping and is left alone, since seeking a healthy
        stream only makes it stutter. One that didn't keeps its position clock
        running while sending nothing, and needs the stream restarted at the
        position it thinks it reached.
        """
        player = payload.player

        # A local close is this bot disconnecting, and the player is destroyed
        # right after, so there is nothing to report or to recover.
        if not payload.by_remote:
            logger.debug(f"Voice websocket closed locally: {payload.code.name}")
            return

        logger.warning(
            f"Voice websocket closed: {payload.code.name} ({payload.code.value}), "
            f"reason {payload.reason or 'none given'}"
        )

        if player is None or payload.code not in RECOVERABLE_VOICE_CLOSES:
            return

        # Long enough for a fresh playerUpdate, which is what refreshes the ping.
        await asyncio.sleep(MUSIC_VOICE_RESUME_DELAY)

        # Only ever false once wavelink has invalidated the player and dropped it
        # from the node, so there is nothing left here to resume.
        if not player.connected:
            logger.warning(f"Player was discarded after {payload.code.name}")
            return

        # Lavalink reports -1 until it is talking to a voice server again.
        if player.ping >= 0:
            logger.info(f"Voice came back on its own after {payload.code.name}, ping {player.ping}ms")
            return

        if player.current:
            # Read here, not before the wait, or the track jumps back by it.
            position = player.position
            await player.seek(position)
            logger.info(f"Restarted {player.current.identifier} at {position}ms after {payload.code.name}")

    @commands.Cog.listener()
    async def on_wavelink_track_start(self, payload: wavelink.TrackStartEventPayload):
        player = payload.player
        if not player:
            return

        # Lavalink sends this before the track has loaded, so a track that is
        # about to fail starts too. The announcement waits for its audio.
        _cancel_announcement(player)
        if getattr(player, "home", None) is not None:
            task = asyncio.create_task(self._announce(player, payload.track))
            player.announcement = (payload.track, task)

        # Searches the node: one track's worth per track played, which keeps a
        # long Spotify playlist from resolving all at once.
        await fill_queue(player)

    async def _announce(self, player: wavelink.Player, track: wavelink.Playable):
        """Posts "Now playing" for track once its audio is going out."""
        if not await _wait_for_audio(player, track):
            return

        channel = await announce_channel(player)
        if channel is None:
            return

        extras = _extras_dict(track)
        description = format_track(track)
        if "original_title" in extras:
            title, author = _original(track)
            original = f"{title} by {author}" if author else title
            description += f"\nOriginal unavailable: {discord.utils.escape_markdown(original)}"

        embed = discord.Embed(
            title="Now playing",
            description=description,
            color=await get_guild_embed_color(channel.guild.id),
        )
        if track.artwork:
            embed.set_thumbnail(url=track.artwork)

        # Unlike a command reply, nothing else here shows who queued it.
        # No footer once they have left the guild.
        requester_id = extras.get("requester_id")
        requester = channel.guild.get_member(requester_id) if isinstance(requester_id, int) else None
        if requester is not None:
            embed.set_footer(
                text=f"Requested by {requester.display_name}",
                icon_url=requester.display_avatar.url,
            )

        try:
            await channel.send(embed=embed)
        except discord.HTTPException:
            # A deleted or newly forbidden channel must not interrupt playback.
            pass

    @commands.Cog.listener()
    async def on_wavelink_track_end(self, payload: wavelink.TrackEndEventPayload):
        """Moves the queue on. Wavelink's autoplay is left off, since it starts the
        next track before a failed one's stand-in is found, and stops for good
        after three failures in a row."""
        player = payload.player
        if player is None:
            return

        track = payload.track
        _cancel_announcement(player, track)
        failure = _pop_failure(player, track)

        # replaced: something else was played over it. cleanup: the player is gone.
        if payload.reason not in ("finished", "stopped", "loadFailed") or not player.connected:
            return

        if payload.reason == "loadFailed" or (failure is not None and failure[1]):
            await self._recover(player, track, failure[0] if failure else "unknown error")
            return

        if failure is not None:
            # Failed after audio had started, so it was heard and is not replaced.
            logger.warning(f"{track.title!r} ({_track_ref(track)}) stopped partway: {failure[0]}")

        await self._play_next(player)

    async def _play_next(self, player: wavelink.Player):
        """Starts the next queued track, unless something is already playing."""
        if not player.connected or player.current is not None:
            return

        # In track loop mode get() hands back the loaded track, already in
        # history. Anything it pops instead is new, e.g. after /skip unloads it.
        repeat = player.queue.mode is wavelink.QueueMode.loop and player.queue.loaded is not None

        # A track that ends while the track start's fill_queue is still
        # searching finds the queue empty, which would stall playback with the
        # tail still pending. fill_queue holds a lock, so this waits on that
        # search rather than starting another.
        if not repeat and player.queue.is_empty and pending_tracks(player):
            await fill_queue(player)
            if not player.connected or player.current is not None:
                return
        try:
            track = player.queue.get()
        except wavelink.QueueEmpty:
            return
        await player.play(track, add_history=not repeat)

    @commands.Cog.listener()
    async def on_wavelink_track_exception(self, payload: wavelink.TrackExceptionEventPayload):
        """A track the node could not stream, e.g. every YouTube client refusing it."""
        # Lavalink sends the whole Java cause chain, a stack trace per client it
        # tried. Only the first line names the failure, but the rest is where each
        # client's own reason appears, so it is kept at debug level.
        message = (payload.exception.get("message") or "").strip()
        detail = message.splitlines()[0] if message else "unknown error"

        # For a playback failure the message is often only "Something broke when
        # playing the track."; the reason (an HTTP status, a decoder error) is in
        # cause. Wavelink's own line was the only other place cause appeared, and
        # that one is muted, so it has to be carried here or it is lost.
        #
        # For a load failure the two restate each other, cause being the same text
        # behind its Java exception class, so it is only appended when it adds
        # something. Both can carry the whole chain, hence first line only.
        cause = (payload.exception.get("cause") or "").strip().splitlines()
        cause = cause[0] if cause else ""
        if cause and detail not in cause:
            detail = f"{detail} ({cause})"

        logger.debug(f"Full exception for {payload.track.identifier}:\n{message}")

        player = payload.player
        if player is None or not player.connected:
            # No player left to recover in, but the failure still happened and
            # this is the only place it gets reported: the node's own line for it
            # is filtered out of the console.
            logger.warning(
                f"Could not play {payload.track.title!r} ({_track_ref(payload.track)}): {detail}, player already gone"
            )
            return

        # Left for the track end that follows, which decides what plays next and
        # logs the outcome. Both events are dispatched as tasks in the order the
        # node sent them, and this runs before any await, so it is in place first.
        player.track_failure = (payload.track, detail, False)

    @commands.Cog.listener()
    async def on_wavelink_track_stuck(self, payload: wavelink.TrackStuckEventPayload):
        """A track that stopped producing audio without reporting an error."""
        player = payload.player
        if player is None or not player.connected or player.current != payload.track:
            return
        # No track end follows this event, so the track is stopped here. Marked
        # stuck, so the end recovers it like a failed load rather than moving on.
        player.track_failure = (payload.track, "the stream stopped responding", True)
        await player.skip(force=True)

    async def _recover(self, player: wavelink.Player, track: wavelink.Playable, detail: str):
        """Plays a stand-in in place of a track that failed, or moves on without one."""
        # Or loop all would bring it back to fail again on every pass.
        if player.queue.history is not None:
            player.queue.history.remove(track)

        # Every id that has failed on this player, so a repeated search walks past
        # them to the next candidate. A stand-in is not added until it fails too,
        # since one bad result should not end the track.
        tried = getattr(player, "failed_tracks", None)
        if tried is None:
            tried = player.failed_tracks = set()
        tried.add(track.identifier)

        # How many stand-ins deep this track already is. Carried on the track
        # rather than the player because a stand-in reports a normal track start
        # before it fails, so nothing on the player survives to be counted.
        depth = _fallback_depth(track)

        replacement = None
        if depth < MUSIC_FALLBACK_ATTEMPTS:
            try:
                replacement = await find_replacement(track, exclude=tried)
            except Exception:
                logger.exception(f"Could not search for a replacement for {_track_ref(track)}")

        if replacement is not None:
            outcome = f"replacing it with {_track_ref(replacement)}"
        elif depth >= MUSIC_FALLBACK_ATTEMPTS:
            outcome = f"giving up after {depth} stand-ins"
        else:
            outcome = "no replacement found"

        # A track that recovered is routine. One that didn't is dropped from the
        # queue outright, so it reads as an error instead of another warning among
        # the warnings that led up to it.
        log = logger.warning if replacement is not None else logger.error
        log(f"Could not play {track.title!r} ({_track_ref(track)}): {detail}, {outcome}")

        if not player.connected:
            return

        title, author = _original(track)
        if replacement is not None:
            # Names the original on the stand-in's "Now playing".
            replacement.extras = {
                "original_title": title,
                "original_author": author,
                **_extras_dict(track),
                "fallback_depth": depth + 1,
            }
            if player.current is None:
                # Into history in every mode, in place of the failed track
                # taken out above, so a later queue loop still plays it.
                await player.play(replacement)
            else:
                # Something was started during the search, e.g. by /play, so the
                # stand-in plays next rather than cutting it off.
                player.queue.put_at(0, replacement)
            return

        channel = await announce_channel(player)
        if channel is not None:
            name = discord.utils.escape_markdown(title)
            try:
                await channel.send(embed=error_embed(f"Couldn't find a playable version of **{name}**, skipping."))
            except discord.HTTPException:
                pass

        # Or track loop mode hands the failed track straight back.
        player.queue.loaded = None
        await self._play_next(player)

    @commands.Cog.listener()
    async def on_wavelink_inactive_player(self, player: wavelink.Player):
        """Fired once nothing has played for MUSIC_IDLE_TIMEOUT seconds."""
        channel = await announce_channel(player)
        if channel is not None:
            try:
                await channel.send(embed=discord.Embed(
                    description=f"Left {player.channel.mention} after being idle.",
                    color=await get_guild_embed_color(channel.guild.id),
                ))
            except discord.HTTPException:
                pass

        voice_channel = player.channel
        await player.disconnect()
        logger.info(f"Left voice channel {voice_channel.id} in guild {voice_channel.guild.id} (idle timeout).")

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        """Leaves once the last human does, rather than playing to an empty channel.

        Also matters for lobbies: lobby_manager only deletes a lobby that has no
        human left in it, so a player sitting in one would keep it alive forever.
        """
        player = active_player(member.guild)
        if player is None:
            return

        # Only react to someone leaving the channel the player is actually in.
        if not before.channel or before.channel.id != player.channel.id:
            return
        if after.channel and after.channel.id == player.channel.id:
            return

        if any(not m.bot for m in player.channel.members):
            return

        voice_channel = player.channel
        await player.disconnect()
        logger.info(f"Left voice channel {voice_channel.id} in guild {voice_channel.guild.id} (channel empty).")


async def setup(bot: commands.Bot):
    await bot.add_cog(MusicManager(bot))
