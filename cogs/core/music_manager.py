import asyncio
import discord
from discord.ext import commands
import logging
import os

import wavelink

from config.constants import EMBED_COLOR_WARNING, MUSIC_IDLE_TIMEOUT
from db.database import get_guild_embed_color
from utils.music import fill_queue, find_replacement, format_track

logger = logging.getLogger("music")


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
    async def on_wavelink_track_start(self, payload: wavelink.TrackStartEventPayload):
        player = payload.player
        if not player:
            return

        channel = getattr(player, "home", None)
        if channel is not None:
            track = payload.track
            color = await get_guild_embed_color(channel.guild.id)
            embed = discord.Embed(
                title="Now playing",
                description=format_track(track),
                color=color,
            )
            if track.artwork:
                embed.set_thumbnail(url=track.artwork)
            if track.recommended:
                embed.set_footer(text="Autoplayed recommendation")

            try:
                await channel.send(embed=embed)
            except discord.HTTPException:
                # A deleted or newly forbidden channel must not interrupt playback.
                pass

        # Last, since it searches the node: one track's worth per track played,
        # which keeps a long Spotify playlist from resolving all at once. The
        # announcement above shouldn't wait on it.
        await fill_queue(player)

    @commands.Cog.listener()
    async def on_wavelink_track_exception(self, payload: wavelink.TrackExceptionEventPayload):
        """A track the node could not stream, e.g. every YouTube client refusing it."""
        # Lavalink sends the whole Java cause chain, a stack trace per client it
        # tried. Only the first line names the failure, but the rest is where each
        # client's own reason appears, so it is kept at debug level.
        message = (payload.exception.get("message") or "").strip()
        detail = message.splitlines()[0] if message else "unknown error"
        logger.debug(f"Full exception for {payload.track.identifier}:\n{message}")

        # Lavalink already ended the track, so wavelink's autoplay has moved on
        # by itself. Only the replacement and the notice are added here.
        await self._replace_failed(payload.player, payload.track, detail)

    @commands.Cog.listener()
    async def on_wavelink_track_stuck(self, payload: wavelink.TrackStuckEventPayload):
        """A track that stopped producing audio without reporting an error."""
        # No track end follows this event, so nothing advances the queue on its
        # own and the track has to be skipped explicitly.
        await self._replace_failed(
            payload.player, payload.track, "the stream stopped responding", skip=True
        )

    async def _replace_failed(self, player: wavelink.Player | None, track: wavelink.Playable, detail: str, *, skip: bool = False):
        """Queues a stand-in for a track that failed, and says so in the channel."""
        if player is None or not player.connected:
            return

        # Every id gets at most one replacement attempt, and a stand-in is
        # registered before it plays, so a run of unplayable results terminates
        # instead of searching for a replacement for the replacement.
        tried = getattr(player, "failed_tracks", None)
        if tried is None:
            tried = player.failed_tracks = set()

        replacement = None
        if track.identifier not in tried:
            tried.add(track.identifier)
            try:
                replacement = await find_replacement(track)
            except Exception:
                logger.exception(f"Could not search for a replacement for {track.identifier}")

        outcome = f"replacing it with {replacement.identifier}" if replacement else "no replacement found"
        logger.warning(f"Could not play {track.title!r} ({track.identifier}): {detail}, {outcome}")

        if replacement is not None:
            tried.add(replacement.identifier)
            # The queue has already advanced by the time the search returns, so
            # the stand-in goes to the front and plays next rather than in place.
            player.queue.put_at(0, replacement)

        # Sent before playback starts, so it lands ahead of the "Now playing"
        # the stand-in triggers rather than after it.
        channel = getattr(player, "home", None)
        if channel is not None:
            description = f"Couldn't play {format_track(track)}."
            description += f"\nPlaying {format_track(replacement)} instead." if replacement else "\nSkipping it."
            try:
                await channel.send(embed=discord.Embed(description=description, color=EMBED_COLOR_WARNING))
            except discord.HTTPException:
                pass

        if skip:
            await player.skip(force=True)
        elif replacement is not None and not player.playing:
            # Nothing followed the failed track, or autoplay gave up after three
            # consecutive failures, so the stand-in has to be started here.
            try:
                await player.play(player.queue.get())
            except wavelink.QueueEmpty:
                pass

    @commands.Cog.listener()
    async def on_wavelink_inactive_player(self, player: wavelink.Player):
        """Fired once nothing has played for MUSIC_IDLE_TIMEOUT seconds."""
        channel = getattr(player, "home", None)
        if channel is not None:
            try:
                await channel.send(embed=discord.Embed(
                    description=f"Left {player.channel.mention} after being idle.",
                    color=await get_guild_embed_color(channel.guild.id),
                ))
            except discord.HTTPException:
                pass

        await player.disconnect()

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        """Leaves once the last human does, rather than playing to an empty channel.

        Also matters for lobbies: lobby_manager only deletes a lobby that has no
        human left in it, so a player sitting in one would keep it alive forever.
        """
        player: wavelink.Player | None = member.guild.voice_client
        if not player or not player.connected:
            return

        # Only react to someone leaving the channel the player is actually in.
        if not before.channel or before.channel.id != player.channel.id:
            return
        if after.channel and after.channel.id == player.channel.id:
            return

        if any(not m.bot for m in player.channel.members):
            return

        await player.disconnect()


async def setup(bot: commands.Bot):
    await bot.add_cog(MusicManager(bot))
