import asyncio
import discord
from discord import app_commands
from discord.ext import commands
import logging
import os
import random
from typing import Optional

import wavelink

from config.constants import (
    MUSIC_AUTOCOMPLETE_BUDGET,
    MUSIC_AUTOCOMPLETE_LIMIT,
    MUSIC_AUTOCOMPLETE_MARGIN,
    MUSIC_DEFAULT_VOLUME,
    MUSIC_MAX_VOLUME,
    MUSIC_QUEUE_PAGE_SIZE,
    MUSIC_SPOTIFY_LIMIT,
)
from db.database import get_guild_embed_color, get_music_volume
from utils.embeds import guild_embed
from utils.errors import UserError
from utils.mixins import SessionMixin
from utils.music import (
    TrackQueue,
    active_player,
    backspaced_search,
    cached_or_search,
    cached_search,
    fill_queue,
    format_numbered,
    format_track,
    format_track_length,
    music_channel,
    nearest_search,
    number_span,
    parse_position,
    play_next,
    progress_bar,
    require_dj,
    require_node,
    require_player,
    require_voice,
    resolve_pending,
    track_length,
    track_queue,
    with_requester,
)
from utils.paginator import PaginatorView
from utils.parsing import parse_number_spec
from utils.spotify import fetch_entity, parse_spotify_url
from utils.tidal import (
    api_configured,
    fetch_collection,
    fetch_track,
    fetch_track_api,
    parse_tidal_url,
)

logger = logging.getLogger("music")

# Minimum characters before /play autocomplete queries the node, under which
# there is nothing specific enough to suggest.
AUTOCOMPLETE_MIN_LENGTH = 3

# Track suggestions, off unless the host asks for them. Read at import because
# the suggestions are part of the command Discord syncs, not a runtime choice.
MUSIC_AUTOCOMPLETE = os.getenv("MUSIC_AUTOCOMPLETE", "false").lower() == "true"

LOOP_MODES = {
    "off": wavelink.QueueMode.normal,
    "track": wavelink.QueueMode.loop,
    "queue": wavelink.QueueMode.loop_all,
}


class Music(SessionMixin, commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _ensure_player(self, interaction: discord.Interaction) -> wavelink.Player:
        """The guild's player, connecting to the caller's channel if needed."""
        channel = require_voice(interaction)
        player = active_player(interaction.guild)

        if player is not None:
            if player.channel.id != channel.id:
                raise UserError(f"I'm already playing in {player.channel.mention}.")
            return player

        permissions = channel.permissions_for(interaction.guild.me)
        if not permissions.connect or not permissions.speak:
            raise UserError(f"I need permission to connect and speak in {channel.mention}.")

        try:
            player = await channel.connect(cls=wavelink.Player, self_deaf=True)
        except discord.ClientException as e:
            logger.error(f"Failed to join voice channel {channel.id}: {e}")
            raise UserError(f"Could not join {channel.mention}: {e}")

        logger.info(f"Joined voice channel {channel.id} in guild {interaction.guild_id}.")

        # music_manager advances the queue itself, so a failed track's stand-in
        # plays in its place. Any other mode would also start the next track.
        player.autoplay = wavelink.AutoPlayMode.disabled

        volume = await get_music_volume(interaction.guild_id)
        await player.set_volume(volume if volume is not None else MUSIC_DEFAULT_VOLUME)

        return player

    async def _elsewhere(self, interaction: discord.Interaction) -> discord.abc.Messageable | None:
        """The music channel, if the command was run outside it. Read before any
        defer, since a deferred reply can't change whether it is ephemeral."""
        channel = await music_channel(interaction.guild)
        if channel is None or channel.id == interaction.channel_id:
            return None
        return channel

    async def _reply(
        self,
        interaction: discord.Interaction,
        embed: discord.Embed,
        channel: discord.abc.Messageable | None,
    ):
        """Replies in place, or privately with a public copy in the music channel,
        so a change made from elsewhere is still seen by everyone listening."""
        private = channel is not None
        if interaction.response.is_done():
            await interaction.followup.send(embed=embed, ephemeral=private)
        else:
            await interaction.response.send_message(embed=embed, ephemeral=private)

        if channel is None:
            return

        public = embed.copy()
        public.set_footer(
            text=f"Requested by {interaction.user.display_name}",
            icon_url=interaction.user.display_avatar.url,
        )
        try:
            await channel.send(embed=public)
        except discord.HTTPException as e:
            # The caller already has their reply, so this only goes unseen.
            logger.warning(f"Could not post to music channel {channel.id} in guild {interaction.guild_id}: {e}")

    @app_commands.command(name="play", description="Play a track, or add it to the queue")
    @app_commands.describe(
        query="A search term, or a Spotify, Tidal, YouTube, YouTube Music, SoundCloud or Bandcamp link"
    )
    async def play(self, interaction: discord.Interaction, query: str):
        require_node()
        elsewhere = await self._elsewhere(interaction)
        await interaction.response.defer(ephemeral=elsewhere is not None)

        player = await self._ensure_player(interaction)
        # Where "Now playing" and idle notices go when no music channel is set,
        # updated on every /play so they follow the channel actually being used.
        player.home = interaction.channel

        color = await get_guild_embed_color(interaction.guild_id)
        embed = await self._queue_query(player, query, color, requester=interaction.user.id)

        # The manager cog announces the track itself once playback starts, so
        # nothing is echoed here beyond the queue confirmation.
        await play_next(player)

        await self._reply(interaction, embed, elsewhere)

    @app_commands.command(name="insert", description="Add a track to the front of the queue")
    @app_commands.describe(
        query="A search term, or a Spotify, Tidal, YouTube, YouTube Music, SoundCloud or Bandcamp link"
    )
    async def insert(self, interaction: discord.Interaction, query: str):
        require_node()
        elsewhere = await self._elsewhere(interaction)
        await interaction.response.defer(ephemeral=elsewhere is not None)

        player = await self._ensure_player(interaction)
        # With nothing queued this is exactly what /play does, so gating it would
        # be stricter than /play for the same result. Cutting ahead of tracks
        # other people queued is the part that needs the role.
        if player.playing or track_queue(player).upcoming:
            await require_dj(interaction, player)

        player.home = interaction.channel

        color = await get_guild_embed_color(interaction.guild_id)
        embed = await self._queue_query(
            player, query, color, requester=interaction.user.id, front=True
        )

        await play_next(player)

        await self._reply(interaction, embed, elsewhere)

    async def _queue_query(
        self, player: wavelink.Player, query: str, color: int, *, requester: int, front: bool = False
    ) -> discord.Embed:
        """Queues a query, routing the links the node resolves no audio for."""
        spotify = parse_spotify_url(query)
        if spotify is not None:
            return await self._queue_spotify(
                player, *spotify, color=color, requester=requester, front=front
            )

        tidal = parse_tidal_url(query)
        if tidal is not None:
            return await self._queue_tidal(
                player, *tidal, color=color, requester=requester, front=front
            )

        return await self._queue_search(player, query, color, requester=requester, front=front)

    async def _queue_search(
        self, player: wavelink.Player, query: str, color: int, *, requester: int, front: bool = False
    ) -> discord.Embed:
        """Queues whatever the node resolves a query or link to."""
        try:
            # No source given, so wavelink's default applies: a bare query becomes
            # a YouTube Music search, which returns songs rather than the videos,
            # covers and lyric uploads a plain YouTube search mixes in. A URL is
            # resolved directly and ignores the default, except a YouTube Music
            # track link, which is searched by its id first.
            # Cached, so text the autocomplete just searched isn't searched again.
            results = await cached_or_search(query)
        except wavelink.LavalinkLoadException as e:
            raise UserError(f"Could not load that: {e.error or 'the source refused the request'}")

        if not results:
            raise UserError(f"No results for `{query[:100]}`.")

        if isinstance(results, wavelink.Playlist):
            tracks = [with_requester(track, requester) for track in results.tracks]
            first = track_queue(player).add(tracks, front=front)
            added = len(tracks)
            return discord.Embed(
                title="Playlist up next" if front else "Playlist queued",
                description=(
                    f"`{number_span(first, added)}.` **{results.name}**\n"
                    f"{added} track{'s' if added != 1 else ''} added."
                ),
                color=color,
            )

        track = with_requester(results[0], requester)
        first = track_queue(player).add([track], front=front)
        embed = discord.Embed(
            title="Playing next" if front else "Queued",
            description=format_numbered(first, track),
            color=color,
        )
        if track.artwork:
            embed.set_thumbnail(url=track.artwork)
        return embed

    async def _queue_spotify(
        self,
        player: wavelink.Player,
        kind: str,
        identifier: str,
        *,
        color: int,
        requester: int,
        front: bool = False,
    ) -> discord.Embed:
        """Queues a Spotify link, which carries metadata the node can't stream."""
        entity = await fetch_entity(self.session, kind, identifier)
        if entity is None:
            raise UserError("Couldn't read that Spotify link. Searching by name still works.")
        if not entity.tracks:
            raise UserError("That Spotify link has no tracks.")

        if entity.kind == "track":
            # One track, so it is resolved here like a Tidal one rather than
            # through the pending queue, which exists to spread a long playlist
            # out. The reply then names the track that was actually found.
            resolved = await resolve_pending(entity.tracks[0])
            if resolved is None:
                raise UserError(f"Couldn't find a playable version of **{entity.name}**.")

            resolved = with_requester(resolved, requester)
            first = track_queue(player).add([resolved], front=front)
            embed = discord.Embed(
                title="Playing next" if front else "Queued",
                description=format_numbered(first, resolved),
                color=color,
            )
            if resolved.artwork:
                embed.set_thumbnail(url=resolved.artwork)
            return embed

        queue = track_queue(player)
        first = queue.add_batch([with_requester(track, requester) for track in entity.tracks], front=front)

        # Only enough to start playing is resolved here. The rest follows as the
        # queue drains, from the manager cog's track start handler.
        await fill_queue(player)
        if not player.playing and queue.next_index() is None:
            raise UserError(f"Couldn't find a playable version of anything in **{entity.name}**.")

        count = len(entity.tracks)
        description = (
            f"`{number_span(first, count)}.` **{entity.name}**\n"
            f"{count} track{'s' if count != 1 else ''} added."
        )
        if count == MUSIC_SPOTIFY_LIMIT:
            description += f"\nSpotify lists at most {MUSIC_SPOTIFY_LIMIT}, so a longer one is cut short."
        embed = discord.Embed(
            title=f"{entity.kind.capitalize()} {'up next' if front else 'queued'}",
            description=description,
            color=color,
        )
        if entity.artwork:
            embed.set_thumbnail(url=entity.artwork)
        return embed

    async def _queue_tidal(
        self,
        player: wavelink.Player,
        kind: str,
        identifier: str,
        *,
        color: int,
        requester: int,
        front: bool = False,
    ) -> discord.Embed:
        """Queues a Tidal link, which carries metadata the node can't stream."""
        # A mix is a Tidal-side radio with no public endpoint behind it, so
        # there is nothing to read whether the API is configured or not.
        if kind == "mix":
            raise UserError("I can't read Tidal mixes. Searching by name still works.")

        if kind != "track":
            return await self._queue_tidal_collection(
                player, kind, identifier, color=color, requester=requester, front=front
            )

        # The API reads a track too, and is the sanctioned route, so the page is
        # only read when there are no credentials to use.
        if api_configured():
            pending = await fetch_track_api(self.session, identifier)
        else:
            pending = await fetch_track(self.session, identifier)
        if pending is None:
            raise UserError("Couldn't read that Tidal link. Searching by name still works.")

        # One track, so it is resolved here either way rather than through the
        # pending queue, which exists to spread a long playlist out.
        resolved = await resolve_pending(pending)
        if resolved is None:
            raise UserError(f"Couldn't find a playable version of **{pending.title}**.")

        resolved = with_requester(resolved, requester)
        first = track_queue(player).add([resolved], front=front)

        embed = discord.Embed(
            title="Playing next" if front else "Queued",
            description=format_numbered(first, resolved),
            color=color,
        )
        if resolved.artwork:
            embed.set_thumbnail(url=resolved.artwork)
        return embed

    async def _queue_tidal_collection(
        self,
        player: wavelink.Player,
        kind: str,
        identifier: str,
        *,
        color: int,
        requester: int,
        front: bool = False,
    ) -> discord.Embed:
        """Queues a Tidal album or playlist, which only the API can list."""
        if not api_configured():
            raise UserError(
                f"I need Tidal API credentials to read a {kind}. Single tracks and "
                "searching by name work without them."
            )

        collection = await fetch_collection(self.session, kind, identifier)
        if collection is None:
            raise UserError(f"Couldn't read that Tidal {kind}. Searching by name still works.")
        if not collection.tracks:
            raise UserError(f"That Tidal {kind} has no tracks.")

        queue = track_queue(player)
        first = queue.add_batch([with_requester(track, requester) for track in collection.tracks], front=front)

        await fill_queue(player)
        if not player.playing and queue.next_index() is None:
            raise UserError(
                f"Couldn't find a playable version of anything in **{collection.name}**."
            )

        count = len(collection.tracks)
        description = (
            f"`{number_span(first, count)}.` **{collection.name}**\n"
            f"{count} track{'s' if count != 1 else ''} added."
        )
        if collection.total > count:
            # Unlike Spotify, the real length is known, so it is named rather
            # than hinted at.
            description += f"\nThe first {count} of {collection.total}, which is as many as I take."
        embed = discord.Embed(
            title=f"{kind.capitalize()} {'up next' if front else 'queued'}",
            description=description,
            color=color,
        )
        if collection.artwork:
            embed.set_thumbnail(url=collection.artwork)
        return embed

    async def _query_autocomplete(self, interaction: discord.Interaction, current: str):
        """Track suggestions for /play and /insert, which take the same query."""
        if len(current.strip()) < AUTOCOMPLETE_MIN_LENGTH:
            return []
        # A pasted link is already exact, so there is nothing to suggest.
        if current.startswith(("http://", "https://")):
            return []

        results = cached_search(current)
        if results is None:
            # Typing forward is never a prefix of a longer search, so it falls
            # through and searches. Backspacing is, and is served from the cache.
            results = backspaced_search(current)
        if results is None:
            # An autocomplete can't be deferred, so the node gets what's left of
            # Discord's 3 seconds and no more. A timeout isn't a failure: the
            # search runs on and fills the cache for a later keystroke.
            elapsed = (discord.utils.utcnow() - interaction.created_at).total_seconds()
            budget = MUSIC_AUTOCOMPLETE_BUDGET - elapsed - MUSIC_AUTOCOMPLETE_MARGIN
            if budget > 0:
                try:
                    results = await asyncio.wait_for(cached_or_search(current), budget)
                except asyncio.TimeoutError:
                    # Expected under load, and the search still fills the cache,
                    # so it's only worth a line when chasing latency.
                    logger.debug(f"Autocomplete for {current!r} outran its {budget:.1f}s budget")
                    results = None
                except Exception:
                    # No error surface here, so a node failure shows as no
                    # suggestions rather than a failed interaction. Logged, or
                    # it's invisible.
                    logger.warning(f"Autocomplete search failed for {current!r}", exc_info=True)
                    results = None
            # Beats an empty list while the real search is still on its way.
            if results is None:
                results = nearest_search(current)

        if results is None or isinstance(results, wavelink.Playlist):
            return []

        choices = []
        for track in results[:MUSIC_AUTOCOMPLETE_LIMIT]:
            label = f"{track.title} - {track.author}"
            # Discord rejects a choice name over 100 characters.
            if len(label) > 100:
                label = label[:97] + "..."
            # The URI resolves to this exact track, where the label would just be
            # re-searched. Falls back to the label for a source without one.
            value = track.uri if track.uri and len(track.uri) <= 100 else label
            choices.append(app_commands.Choice(name=label, value=value))
        return choices

    if MUSIC_AUTOCOMPLETE:
        # Discord shows its suggestion box for any option registered here, empty
        # or not, so registering is the switch, not what the callback returns.
        play.autocomplete("query")(_query_autocomplete)
        insert.autocomplete("query")(_query_autocomplete)

    @app_commands.command(
        name="skip", description="Skip the current track, or drop tracks from the queue"
    )
    @app_commands.describe(
        position="A queue position, range or list like 3, 2-5 or 1,4,7-9 (leave empty to skip what's playing)"
    )
    async def skip(self, interaction: discord.Interaction, position: Optional[str] = None):
        player = require_player(interaction)
        await require_dj(interaction, player)

        if position is None:
            if not player.current:
                raise UserError("Nothing is playing.")

            skipped = player.current
            await player.skip(force=True)
            await self._reply(
                interaction,
                await guild_embed(interaction.guild_id, f"Skipped {format_track(skipped, with_author=False)}"),
                await self._elsewhere(interaction),
            )
            return

        # Numbers as /queue prints them. The track playing can be named too, but
        # nothing before it, which has already played.
        queue = track_queue(player)
        number = queue.cursor + 1 if player.current else queue.cursor + 2
        if number > len(queue.tracks):
            raise UserError("The queue is empty, so there's nothing in it to skip.")

        try:
            positions = parse_number_spec(
                position, noun="queue position", maximum=len(queue.tracks)
            )
        except ValueError as e:
            raise UserError(str(e))

        if positions[0] < number:
            raise UserError(f"Track {positions[0]} has already played.")

        removed = [queue.tracks[index - 1] for index in positions]

        # Rebuilt rather than deleted in place, where every removal would shift
        # the positions after it.
        dropping = set(positions)
        queue.set_upcoming([
            track for index, track in enumerate(queue.upcoming, queue.cursor + 2)
            if index not in dropping
        ])
        # Only stopped, so it keeps its number like any other played track.
        if player.current and queue.cursor + 1 in dropping:
            await player.skip(force=True)

        if len(removed) == 1:
            description = f"Skipped {format_track(removed[0], with_author=False)}"
        else:
            # Capped at a page's worth, or a long range would overflow the embed.
            listed = removed[:MUSIC_QUEUE_PAGE_SIZE]
            lines = "\n".join(f"- {format_track(track, with_author=False)}" for track in listed)
            description = f"Skipped **{len(removed)}** tracks.\n{lines}"
            if len(removed) > len(listed):
                description += f"\n- and {len(removed) - len(listed)} more"

        await self._reply(interaction, await guild_embed(interaction.guild_id, description), await self._elsewhere(interaction))

        # Dropping the next track can leave a pending one next instead.
        # Last, since it searches, and the reply shouldn't wait on it.
        await fill_queue(player)

    def _position_choices(self, queue: TrackQueue, start: int, current: str) -> list:
        """Autocomplete for a queue position, listing tracks from index start."""
        current = current.strip()
        # A range or list is typed by hand, and there is no single position to
        # suggest for one.
        if current and not current.isdigit():
            return []

        choices = []
        for index, track in enumerate(queue.tracks[start:], start + 1):
            if current and not str(index).startswith(current):
                continue

            label = f"{index}. {track.title} - {track.author}"
            # Discord rejects a choice name over 100 characters.
            if len(label) > 100:
                label = label[:97] + "..."
            choices.append(app_commands.Choice(name=label, value=str(index)))

            if len(choices) >= MUSIC_AUTOCOMPLETE_LIMIT:
                break
        return choices

    @skip.autocomplete("position")
    async def skip_autocomplete(self, interaction: discord.Interaction, current: str):
        player = active_player(interaction.guild)
        if player is None:
            return []

        queue = track_queue(player)
        start = queue.cursor if player.current else queue.cursor + 1
        return self._position_choices(queue, start, current)

    @app_commands.command(name="move", description="Move queued tracks to another position")
    @app_commands.describe(
        position="A queue position, range or list like 3, 2-5 or 1,4,7-9",
        to="The position they move to, in order from there",
    )
    async def move(self, interaction: discord.Interaction, position: str, to: int):
        player = require_player(interaction)
        await require_dj(interaction, player)

        queue = track_queue(player)
        upcoming = queue.upcoming
        if not upcoming:
            raise UserError("The queue is empty, so there's nothing in it to move.")

        try:
            positions = parse_number_spec(
                position, noun="queue position", maximum=len(queue.tracks)
            )
        except ValueError as e:
            raise UserError(str(e))

        # Only what hasn't started can move, on either side of the move.
        lowest = queue.cursor + 2
        if positions[0] < lowest:
            raise UserError(f"Track {positions[0]} has already started, so it can't be moved.")

        highest = len(queue.tracks) - len(positions) + 1
        if not lowest <= to <= highest:
            raise UserError(f"That can only go from position {lowest} to {highest}.")

        span = number_span(to, len(positions))
        if positions == list(range(to, to + len(positions))):
            raise UserError(f"That's already at position {span}.")

        moving = [queue.tracks[index - 1] for index in positions]
        dropping = set(positions)
        order = [
            track for index, track in enumerate(upcoming, lowest)
            if index not in dropping
        ]
        order[to - lowest:to - lowest] = moving
        queue.set_upcoming(order)

        if len(moving) == 1:
            description = f"Moved {format_track(moving[0], with_author=False)} to position **{span}**."
        else:
            description = f"Moved **{len(moving)}** tracks to positions **{span}**."

        await self._reply(interaction, await guild_embed(interaction.guild_id, description), await self._elsewhere(interaction))

        # A pending track can now be next.
        # Last, since it searches, and the reply shouldn't wait on it.
        await fill_queue(player)

    @move.autocomplete("position")
    async def move_autocomplete(self, interaction: discord.Interaction, current: str):
        player = active_player(interaction.guild)
        if player is None:
            return []

        queue = track_queue(player)
        return self._position_choices(queue, queue.cursor + 1, current)

    @app_commands.command(name="pause", description="Pause playback")
    async def pause(self, interaction: discord.Interaction):
        player = require_player(interaction)
        await require_dj(interaction, player)

        if player.paused:
            raise UserError("Playback is already paused.")
        if not player.current:
            raise UserError("Nothing is playing.")

        await player.pause(True)
        await self._reply(interaction, await guild_embed(interaction.guild_id, "Paused."), await self._elsewhere(interaction))

    @app_commands.command(name="resume", description="Resume playback")
    async def resume(self, interaction: discord.Interaction):
        player = require_player(interaction)
        await require_dj(interaction, player)

        if not player.paused:
            raise UserError("Playback isn't paused.")

        await player.pause(False)
        await self._reply(interaction, await guild_embed(interaction.guild_id, "Resumed."), await self._elsewhere(interaction))

    @app_commands.command(name="stop", description="Stop playback, clear the queue and leave")
    async def stop(self, interaction: discord.Interaction):
        player = require_player(interaction)
        await require_dj(interaction, player)

        track_queue(player).clear()
        channel = player.channel
        await player.disconnect()
        await self._reply(
            interaction,
            await guild_embed(interaction.guild_id, "Stopped and cleared the queue."),
            await self._elsewhere(interaction),
        )
        logger.info(f"Left voice channel {channel.id} in guild {interaction.guild_id}.")

    @app_commands.command(name="volume", description="Set or view the playback volume")
    @app_commands.describe(percent=f"1 to {MUSIC_MAX_VOLUME} (leave empty to view the current volume)")
    async def volume(self, interaction: discord.Interaction, percent: Optional[int] = None):
        player = require_player(interaction)

        if percent is None:
            await interaction.response.send_message(
                embed=await guild_embed(interaction.guild_id, f"Volume is at **{player.volume}%**.")
            )
            return

        await require_dj(interaction, player)
        if not 1 <= percent <= MUSIC_MAX_VOLUME:
            raise UserError(f"Volume must be between 1 and {MUSIC_MAX_VOLUME}.")

        await player.set_volume(percent)
        await self._reply(
            interaction,
            await guild_embed(interaction.guild_id, f"Volume set to **{percent}%**."),
            await self._elsewhere(interaction),
        )

    @app_commands.command(name="seek", description="Jump to a position in the current track")
    @app_commands.describe(position="A timestamp like 90, 1:30 or 1:02:15")
    async def seek(self, interaction: discord.Interaction, position: str):
        player = require_player(interaction)
        await require_dj(interaction, player)

        if not player.current:
            raise UserError("Nothing is playing.")
        if player.current.is_stream:
            raise UserError("You can't seek within a live stream.")

        milliseconds = parse_position(position)
        if milliseconds > player.current.length:
            raise UserError(f"That's past the end of the track (`{track_length(player.current)}`).")

        await player.seek(milliseconds)
        await self._reply(
            interaction,
            await guild_embed(interaction.guild_id, f"Jumped to `{position}`."),
            await self._elsewhere(interaction),
        )

    @app_commands.command(name="shuffle", description="Shuffle the queue")
    async def shuffle(self, interaction: discord.Interaction):
        player = require_player(interaction)
        await require_dj(interaction, player)

        queue = track_queue(player)
        tracks = queue.upcoming
        if len(tracks) < 2:
            raise UserError("There aren't enough tracks queued to shuffle.")

        random.shuffle(tracks)
        queue.set_upcoming(tracks)

        await self._reply(
            interaction,
            await guild_embed(interaction.guild_id, f"Shuffled **{len(tracks)}** tracks."),
            await self._elsewhere(interaction),
        )

        # A pending track can now be next.
        # Last, since it searches, and the reply shouldn't wait on it.
        await fill_queue(player)

    @app_commands.command(name="loop", description="Set the loop mode")
    @app_commands.describe(mode="What to repeat")
    @app_commands.choices(mode=[
        app_commands.Choice(name="Off", value="off"),
        app_commands.Choice(name="Current track", value="track"),
        app_commands.Choice(name="Whole queue", value="queue"),
    ])
    async def loop(self, interaction: discord.Interaction, mode: app_commands.Choice[str]):
        player = require_player(interaction)
        await require_dj(interaction, player)

        track_queue(player).mode = LOOP_MODES[mode.value]
        await self._reply(
            interaction,
            await guild_embed(interaction.guild_id, f"Loop mode set to **{mode.name}**."),
            await self._elsewhere(interaction),
        )

    @app_commands.command(name="nowplaying", description="Show the track currently playing")
    async def nowplaying(self, interaction: discord.Interaction):
        player = active_player(interaction.guild)
        if player is None or not player.current:
            raise UserError("Nothing is playing.")

        # Deferred before the database read, which is otherwise done inside the
        # three seconds Discord allows for a first response.
        await interaction.response.defer()

        track = player.current
        color = await get_guild_embed_color(interaction.guild_id)
        embed = discord.Embed(title="Now playing", description=format_track(track), color=color)

        if not track.is_stream:
            bar = progress_bar(player.position, track.length)
            embed.add_field(
                name="Progress",
                value=f"`{format_track_length(player.position)}` {bar} `{track_length(track)}`",
                inline=False,
            )

        if track.artwork:
            embed.set_thumbnail(url=track.artwork)

        queue = track_queue(player)
        footer = f"Track {queue.cursor + 1} of {len(queue.tracks)} - Volume {player.volume}%"
        if player.paused:
            footer += " - paused"
        embed.set_footer(text=footer)

        await interaction.followup.send(embed=embed)

    @app_commands.command(name="queue", description="Show the queue")
    async def queue(self, interaction: discord.Interaction):
        player = active_player(interaction.guild)
        if player is None:
            raise UserError("I'm not playing anything right now.")

        await interaction.response.defer()

        queue = track_queue(player)
        header = ""
        if player.current:
            header = f"**Now playing**\n{format_numbered(queue.cursor + 1, player.current)}\n\n"

        def page(title: str, start: int, end: int) -> str:
            lines = [
                format_numbered(index + 1, queue.tracks[index])
                for index in range(start, end)
            ]
            # The header repeats on every page so a page reads on its own.
            return f"{header}{title}\n" + "\n".join(lines)

        # Split at the current track, so the page opened on is what's playing and
        # what follows it. Played pages count back from it, so the one before
        # holds the most recent and only the very first can run short.
        played = queue.cursor if player.current else queue.cursor + 1
        pages = [
            page(f"**Played** ({played})", max(0, end - MUSIC_QUEUE_PAGE_SIZE), end)
            for end in range(played, 0, -MUSIC_QUEUE_PAGE_SIZE)
        ][::-1]
        start_page = len(pages)

        first = queue.cursor + 1
        left = len(queue.tracks) - first
        if not left:
            pages.append(f"{header}**Up next**\nThe queue is empty.")
        for start in range(first, len(queue.tracks), MUSIC_QUEUE_PAGE_SIZE):
            end = min(start + MUSIC_QUEUE_PAGE_SIZE, len(queue.tracks))
            pages.append(page(f"**Up next** ({left} left)", start, end))

        color = await get_guild_embed_color(interaction.guild_id)
        view = PaginatorView(pages, color, start_page=start_page)
        view.message = await interaction.followup.send(view=view)


async def setup(bot: commands.Bot):
    await bot.add_cog(Music(bot))
