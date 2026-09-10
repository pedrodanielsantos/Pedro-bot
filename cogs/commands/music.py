import asyncio
import discord
from discord import app_commands
from discord.ext import commands
import logging
import random
from typing import Optional

import wavelink

from config.constants import (
    MUSIC_AUTOCOMPLETE_CACHE,
    MUSIC_AUTOCOMPLETE_DEBOUNCE,
    MUSIC_AUTOCOMPLETE_LIMIT,
    MUSIC_DEFAULT_VOLUME,
    MUSIC_MAX_VOLUME,
    MUSIC_QUEUE_PAGE_SIZE,
    MUSIC_SPOTIFY_LIMIT,
)
from db.database import get_guild_embed_color, get_music_volume
from utils.embeds import success_embed
from utils.errors import UserError
from utils.mixins import SessionMixin
from utils.music import (
    active_player,
    fill_queue,
    format_track,
    format_track_length,
    parse_position,
    pending_tracks,
    progress_bar,
    queued_tracks,
    require_dj,
    require_node,
    require_player,
    require_voice,
    resolve_pending,
    track_length,
)
from utils.paginator import PaginatorView
from utils.parsing import parse_number_spec
from utils.spotify import fetch_entity, parse_spotify_url

logger = logging.getLogger("music")

# Minimum characters before /play autocomplete queries the node, under which
# there is nothing specific enough to suggest.
AUTOCOMPLETE_MIN_LENGTH = 3

LOOP_MODES = {
    "off": wavelink.QueueMode.normal,
    "track": wavelink.QueueMode.loop,
    "queue": wavelink.QueueMode.loop_all,
}


class Music(SessionMixin, commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # The newest autocomplete keystroke per user, so earlier ones can tell
        # they have been superseded. Holds one small token per typist at most.
        self._autocomplete_tokens: dict[int, object] = {}
        # The last query each user was shown results for, with those results,
        # so backspacing through it doesn't ask the node again. Capped at
        # MUSIC_AUTOCOMPLETE_CACHE users.
        self._autocomplete_results: dict[int, tuple[str, list]] = {}

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
            raise UserError(f"Could not join {channel.mention}: {e}")

        # Queue playback without recommendations. AutoPlayMode.enabled would keep
        # inventing tracks after the queue empties, which is surprising by default.
        player.autoplay = wavelink.AutoPlayMode.partial

        volume = await get_music_volume(interaction.guild_id)
        await player.set_volume(volume if volume is not None else MUSIC_DEFAULT_VOLUME)

        return player

    @app_commands.command(name="play", description="Play a track, or add it to the queue")
    @app_commands.describe(
        query="A search term, or a Spotify, YouTube, YouTube Music, SoundCloud or Bandcamp link"
    )
    async def play(self, interaction: discord.Interaction, query: str):
        require_node()
        await interaction.response.defer()

        player = await self._ensure_player(interaction)
        # Where "Now playing" and idle notices go, set on every /play so the
        # announcements follow the channel actually being used.
        player.home = interaction.channel

        color = await get_guild_embed_color(interaction.guild_id)
        spotify = parse_spotify_url(query)
        if spotify is not None:
            embed = await self._queue_spotify(player, *spotify, color=color)
        else:
            embed = await self._queue_search(player, query, color)

        # The manager cog announces the track itself once playback starts, so
        # nothing is echoed here beyond the queue confirmation.
        if not player.playing:
            await player.play(player.queue.get())

        await interaction.followup.send(embed=embed)

    @app_commands.command(name="insert", description="Add a track to the front of the queue")
    @app_commands.describe(
        query="A search term, or a Spotify, YouTube, YouTube Music, SoundCloud or Bandcamp link"
    )
    async def insert(self, interaction: discord.Interaction, query: str):
        require_node()
        await interaction.response.defer()

        player = await self._ensure_player(interaction)
        # With nothing queued this is exactly what /play does, so gating it would
        # be stricter than /play for the same result. Cutting ahead of tracks
        # other people queued is the part that needs the role.
        if player.playing or queued_tracks(player):
            await require_dj(interaction, player)

        player.home = interaction.channel

        color = await get_guild_embed_color(interaction.guild_id)
        spotify = parse_spotify_url(query)
        if spotify is not None:
            embed = await self._queue_spotify(player, *spotify, color=color, front=True)
        else:
            embed = await self._queue_search(player, query, color, front=True)

        if not player.playing:
            await player.play(player.queue.get())

        await interaction.followup.send(embed=embed)

    @insert.autocomplete("query")
    async def insert_autocomplete(self, interaction: discord.Interaction, current: str):
        return await self._query_autocomplete(interaction, current)

    async def _queue_search(
        self, player: wavelink.Player, query: str, color: int, *, front: bool = False
    ) -> discord.Embed:
        """Queues whatever the node resolves a query or link to."""
        try:
            # No source given, so wavelink's default applies: a bare query becomes
            # a YouTube Music search, which returns songs rather than the videos,
            # covers and lyric uploads a plain YouTube search mixes in. A URL is
            # resolved directly and ignores the default.
            results = await wavelink.Playable.search(query)
        except wavelink.LavalinkLoadException as e:
            raise UserError(f"Could not load that: {e.error or 'the source refused the request'}")

        if not results:
            raise UserError(f"No results for `{query[:100]}`.")

        if isinstance(results, wavelink.Playlist):
            if front:
                # Ascending indices, so the playlist keeps its own order while
                # sitting ahead of everything already queued.
                for offset, track in enumerate(results.tracks):
                    player.queue.put_at(offset, track)
                added = len(results.tracks)
            else:
                added = player.queue.put(results)
            return discord.Embed(
                title="Playlist up next" if front else "Playlist queued",
                description=f"**{results.name}**\n{added} track{'s' if added != 1 else ''} added.",
                color=color,
            )

        track = results[0]
        if front:
            player.queue.put_at(0, track)
        else:
            player.queue.put(track)
        embed = discord.Embed(
            title="Playing next" if front else "Queued",
            description=format_track(track),
            color=color,
        )
        if track.artwork:
            embed.set_thumbnail(url=track.artwork)
        return embed

    async def _queue_spotify(
        self, player: wavelink.Player, kind: str, identifier: str, *, color: int, front: bool = False
    ) -> discord.Embed:
        """Queues a Spotify link, which carries metadata the node can't stream."""
        # An album or playlist is resolved a few tracks at a time as the queue
        # drains, which only ever appends. Inserting one would mean resolving all
        # of it up front, so the link is refused rather than played out of order.
        # Checked before the fetch, since the URL already says which kind it is.
        if front and kind != "track":
            raise UserError(f"I can only insert a single track. Use `/play` for a Spotify {kind}.")

        entity = await fetch_entity(self.session, kind, identifier)
        if entity is None:
            raise UserError("Couldn't read that Spotify link. Searching by name still works.")
        if not entity.tracks:
            raise UserError("That Spotify link has no tracks.")

        if front:
            # Resolved directly rather than through the pending queue, which
            # fill_queue would append to the back.
            resolved = await resolve_pending(entity.tracks[0])
            if resolved is None:
                raise UserError(f"Couldn't find a playable version of **{entity.name}**.")

            player.queue.put_at(0, resolved)
            embed = discord.Embed(
                title="Playing next", description=format_track(resolved), color=color
            )
            if resolved.artwork:
                embed.set_thumbnail(url=resolved.artwork)
            return embed

        pending_tracks(player).extend(entity.tracks)

        # Only enough to start playing is resolved here. The rest follows as the
        # queue drains, from the manager cog's track start handler.
        added = await fill_queue(player)
        if not added and not player.playing and player.queue.is_empty:
            raise UserError(f"Couldn't find a playable version of anything in **{entity.name}**.")

        if entity.kind == "track" and added:
            embed = discord.Embed(title="Queued", description=format_track(added[0]), color=color)
            if added[0].artwork:
                embed.set_thumbnail(url=added[0].artwork)
            return embed

        count = len(entity.tracks)
        description = f"**{entity.name}**\n{count} track{'s' if count != 1 else ''} added."
        if count == MUSIC_SPOTIFY_LIMIT:
            description += f"\nSpotify lists at most {MUSIC_SPOTIFY_LIMIT}, so a longer one is cut short."
        embed = discord.Embed(
            title=f"{entity.kind.capitalize()} queued", description=description, color=color
        )
        if entity.artwork:
            embed.set_thumbnail(url=entity.artwork)
        return embed

    @play.autocomplete("query")
    async def play_autocomplete(self, interaction: discord.Interaction, current: str):
        return await self._query_autocomplete(interaction, current)

    async def _query_autocomplete(self, interaction: discord.Interaction, current: str):
        """Track suggestions for /play and /insert, which take the same query."""
        # Dropping the token cancels a keystroke still waiting to search, so
        # deleting the query doesn't leave one to fire for text that is gone.
        user_id = interaction.user.id
        if len(current) < AUTOCOMPLETE_MIN_LENGTH or not current.strip():
            self._autocomplete_tokens.pop(user_id, None)
            if not current:
                self._autocomplete_results.pop(user_id, None)
            return []
        # A pasted link is already exact, so there is nothing to suggest.
        if current.startswith(("http://", "https://")):
            self._autocomplete_tokens.pop(user_id, None)
            return []

        # Backspacing leaves a prefix of what was already searched, which is
        # text being edited rather than a query someone means. What they were
        # already shown is served again instead, since one backspace is a poor
        # reason to ask the node anything. Typing forward is never a prefix of
        # the last search, so it falls through and searches.
        searched, previous = self._autocomplete_results.get(user_id, (None, None))
        if searched is not None and searched.startswith(current):
            self._autocomplete_tokens.pop(user_id, None)
            return previous

        # Discord fires this as you type, roughly once a second, and searching
        # each one would hammer YouTube for results the next keystroke discards.
        # Only the last of a burst is still current after the wait, so only it
        # searches.
        token = object()
        self._autocomplete_tokens[user_id] = token
        await asyncio.sleep(MUSIC_AUTOCOMPLETE_DEBOUNCE)
        if self._autocomplete_tokens.get(user_id) is not token:
            return []
        # Dropped once claimed, so the map doesn't keep an entry per user seen.
        self._autocomplete_tokens.pop(user_id, None)

        try:
            results = await wavelink.Playable.search(current)
        except Exception:
            # Autocomplete has no error surface, so a node hiccup shows as no
            # suggestions rather than a failed interaction.
            return []

        if isinstance(results, wavelink.Playlist):
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

        # Capped, or a long lived bot keeps a result set per user who ever
        # typed one. Oldest first, since a dict keeps insertion order.
        while len(self._autocomplete_results) >= MUSIC_AUTOCOMPLETE_CACHE:
            del self._autocomplete_results[next(iter(self._autocomplete_results))]
        self._autocomplete_results[user_id] = (current, choices)
        return choices

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
            await interaction.response.send_message(
                embed=success_embed(f"Skipped {format_track(skipped, with_author=False)}")
            )
            return

        # Positions count everything queued, numbered as /queue prints them, so
        # the track playing is skipped by leaving this empty rather than by
        # asking for position 0.
        resolved = list(player.queue)
        pending = pending_tracks(player)
        tail = list(pending)
        tracks = resolved + tail
        if not tracks:
            raise UserError("The queue is empty, so there's nothing in it to skip.")

        try:
            positions = parse_number_spec(
                position, noun="queue position", maximum=len(tracks)
            )
        except ValueError as e:
            raise UserError(str(e))

        removed = [tracks[index - 1] for index in positions]

        # Both rebuilt rather than deleted in place, where every removal would
        # shift the positions after it. Nothing is awaited, so neither is
        # observed half rebuilt. A track fill_queue is resolving right now has
        # already left the deque, so skipping it does nothing.
        dropping = set(positions)
        # Left alone when only the tail is affected, so dropping a track nowhere
        # near the queue doesn't disturb what loop mode is tracking.
        if positions[0] <= len(resolved):
            player.queue.clear()
            for index, track in enumerate(resolved, 1):
                if index not in dropping:
                    player.queue.put(track)

        keeping = [
            track for offset, track in enumerate(tail)
            if len(resolved) + offset + 1 not in dropping
        ]
        pending.clear()
        pending.extend(keeping)

        if len(removed) == 1:
            description = f"Skipped {format_track(removed[0], with_author=False)}"
        else:
            # Capped at a page's worth, or a long range would overflow the embed.
            listed = removed[:MUSIC_QUEUE_PAGE_SIZE]
            lines = "\n".join(f"- {format_track(track, with_author=False)}" for track in listed)
            description = f"Skipped **{len(removed)}** queued tracks.\n{lines}"
            if len(removed) > len(listed):
                description += f"\n- and {len(removed) - len(listed)} more"

        await interaction.response.send_message(embed=success_embed(description))

        # Skipping the resolved stretch leaves the queue short, or empty. Nothing
        # else refills it: with autoplay partial an empty queue never starts a
        # track, so no track start arrives to do it and the tail is stranded.
        # Last, since it searches, and the reply shouldn't wait on it.
        await fill_queue(player)

    @skip.autocomplete("position")
    async def skip_autocomplete(self, interaction: discord.Interaction, current: str):
        player = active_player(interaction.guild)
        if player is None:
            return []

        current = current.strip()
        # A range or list is typed by hand, and there is no single position to
        # suggest for one.
        if current and not current.isdigit():
            return []

        choices = []
        for index, track in enumerate(queued_tracks(player), 1):
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

    @app_commands.command(name="pause", description="Pause playback")
    async def pause(self, interaction: discord.Interaction):
        player = require_player(interaction)
        await require_dj(interaction, player)

        if player.paused:
            raise UserError("Playback is already paused.")
        if not player.current:
            raise UserError("Nothing is playing.")

        await player.pause(True)
        await interaction.response.send_message(embed=success_embed("Paused."))

    @app_commands.command(name="resume", description="Resume playback")
    async def resume(self, interaction: discord.Interaction):
        player = require_player(interaction)
        await require_dj(interaction, player)

        if not player.paused:
            raise UserError("Playback isn't paused.")

        await player.pause(False)
        await interaction.response.send_message(embed=success_embed("Resumed."))

    @app_commands.command(name="stop", description="Stop playback, clear the queue and leave")
    async def stop(self, interaction: discord.Interaction):
        player = require_player(interaction)
        await require_dj(interaction, player)

        player.queue.clear()
        pending_tracks(player).clear()
        await player.disconnect()
        await interaction.response.send_message(embed=success_embed("Stopped and cleared the queue."))

    @app_commands.command(name="volume", description="Set or view the playback volume")
    @app_commands.describe(percent=f"1 to {MUSIC_MAX_VOLUME} (leave empty to view the current volume)")
    async def volume(self, interaction: discord.Interaction, percent: Optional[int] = None):
        player = require_player(interaction)

        if percent is None:
            await interaction.response.send_message(
                embed=success_embed(f"Volume is at **{player.volume}%**.")
            )
            return

        await require_dj(interaction, player)
        if not 1 <= percent <= MUSIC_MAX_VOLUME:
            raise UserError(f"Volume must be between 1 and {MUSIC_MAX_VOLUME}.")

        await player.set_volume(percent)
        await interaction.response.send_message(embed=success_embed(f"Volume set to **{percent}%**."))

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
        await interaction.response.send_message(
            embed=success_embed(f"Jumped to `{position}`.")
        )

    @app_commands.command(name="shuffle", description="Shuffle the queue")
    async def shuffle(self, interaction: discord.Interaction):
        player = require_player(interaction)
        await require_dj(interaction, player)

        tracks = queued_tracks(player)
        if len(tracks) < 2:
            raise UserError("There aren't enough tracks queued to shuffle.")

        pending = pending_tracks(player)
        if not pending:
            player.queue.shuffle()
            await interaction.response.send_message(
                embed=success_embed(f"Shuffled **{len(tracks)}** tracks.")
            )
            return

        # fill_queue searches, so this can outlast the three seconds Discord
        # allows for a first response.
        await interaction.response.defer()

        # Everything goes to the tail so a resolved track can land anywhere in
        # the new order, not just in the stretch already resolved. fill_queue
        # pulls the head back, and only searches for what is still pending.
        random.shuffle(tracks)
        player.queue.clear()
        pending.clear()
        pending.extend(tracks)
        await fill_queue(player)

        await interaction.followup.send(
            embed=success_embed(f"Shuffled **{len(tracks)}** tracks.")
        )

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

        player.queue.mode = LOOP_MODES[mode.value]
        await interaction.response.send_message(
            embed=success_embed(f"Loop mode set to **{mode.name}**.")
        )

    @app_commands.command(name="playing", description="Show the track currently playing")
    async def playing(self, interaction: discord.Interaction):
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

        footer = f"Volume {player.volume}%"
        if player.paused:
            footer += " - paused"
        queued = len(queued_tracks(player))
        if queued:
            footer += f" - {queued} track{'s' if queued != 1 else ''} queued"
        embed.set_footer(text=footer)

        await interaction.followup.send(embed=embed)

    @app_commands.command(name="queue", description="Show the queue")
    async def queue(self, interaction: discord.Interaction):
        player = active_player(interaction.guild)
        if player is None:
            raise UserError("I'm not playing anything right now.")

        await interaction.response.defer()

        header = ""
        if player.current:
            header = f"**Now playing**\n{format_track(player.current)}\n\n"

        tracks = queued_tracks(player)

        if not tracks:
            pages = [f"{header}**Up next**\nThe queue is empty."]
        else:
            pages = []
            for start in range(0, len(tracks), MUSIC_QUEUE_PAGE_SIZE):
                chunk = tracks[start:start + MUSIC_QUEUE_PAGE_SIZE]
                lines = [
                    f"`{start + offset + 1}.` {format_track(track)}"
                    for offset, track in enumerate(chunk)
                ]
                # The header repeats on every page so a page reads on its own.
                pages.append(f"{header}**Up next** ({len(tracks)} total)\n" + "\n".join(lines))

        color = await get_guild_embed_color(interaction.guild_id)
        view = PaginatorView(pages, color)
        view.message = await interaction.followup.send(view=view)


async def setup(bot: commands.Bot):
    await bot.add_cog(Music(bot))
