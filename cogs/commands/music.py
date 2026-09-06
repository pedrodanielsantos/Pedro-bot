import discord
from discord import app_commands
from discord.ext import commands
import logging
from typing import Optional

import wavelink

from config.constants import (
    MUSIC_AUTOCOMPLETE_LIMIT,
    MUSIC_DEFAULT_VOLUME,
    MUSIC_MAX_VOLUME,
    MUSIC_QUEUE_PAGE_SIZE,
)
from db.database import get_guild_embed_color, get_music_volume
from utils.embeds import success_embed
from utils.errors import UserError
from utils.music import (
    format_track,
    format_track_length,
    parse_position,
    progress_bar,
    require_dj,
    require_node,
    require_player,
    require_voice,
    track_length,
)
from utils.paginator import PaginatorView

logger = logging.getLogger("music")

# Minimum characters before /play autocomplete queries the node. Autocomplete
# fires on every keystroke, and a search per character would hammer YouTube for
# results nobody is going to pick.
AUTOCOMPLETE_MIN_LENGTH = 3

LOOP_MODES = {
    "off": wavelink.QueueMode.normal,
    "track": wavelink.QueueMode.loop,
    "queue": wavelink.QueueMode.loop_all,
}


class Music(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _ensure_player(self, interaction: discord.Interaction) -> wavelink.Player:
        """The guild's player, connecting to the caller's channel if needed."""
        channel = require_voice(interaction)
        player: wavelink.Player | None = interaction.guild.voice_client

        if player and player.connected:
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
    @app_commands.describe(query="A search term, or a YouTube, YouTube Music, SoundCloud or Bandcamp link")
    async def play(self, interaction: discord.Interaction, query: str):
        require_node()
        await interaction.response.defer()

        player = await self._ensure_player(interaction)
        # Where "Now playing" and idle notices go, set on every /play so the
        # announcements follow the channel actually being used.
        player.home = interaction.channel

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

        color = await get_guild_embed_color(interaction.guild_id)

        if isinstance(results, wavelink.Playlist):
            added = player.queue.put(results)
            embed = discord.Embed(
                title="Playlist queued",
                description=f"**{results.name}**\n{added} track{'s' if added != 1 else ''} added.",
                color=color,
            )
        else:
            track = results[0]
            player.queue.put(track)
            embed = discord.Embed(
                title="Queued",
                description=format_track(track),
                color=color,
            )
            if track.artwork:
                embed.set_thumbnail(url=track.artwork)

        # The manager cog announces the track itself once playback starts, so
        # nothing is echoed here beyond the queue confirmation.
        if not player.playing:
            await player.play(player.queue.get())

        await interaction.followup.send(embed=embed)

    @play.autocomplete("query")
    async def play_autocomplete(self, interaction: discord.Interaction, current: str):
        if len(current) < AUTOCOMPLETE_MIN_LENGTH or not current.strip():
            return []
        # A pasted link is already exact, so there is nothing to suggest.
        if current.startswith(("http://", "https://")):
            return []

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
        return choices

    @app_commands.command(name="skip", description="Skip the current track")
    async def skip(self, interaction: discord.Interaction):
        player = require_player(interaction)
        await require_dj(interaction, player)

        if not player.current:
            raise UserError("Nothing is playing.")

        skipped = player.current
        await player.skip(force=True)
        await interaction.response.send_message(
            embed=success_embed(f"Skipped {format_track(skipped, with_author=False)}")
        )

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

        if player.queue.count < 2:
            raise UserError("There aren't enough tracks queued to shuffle.")

        player.queue.shuffle()
        await interaction.response.send_message(
            embed=success_embed(f"Shuffled **{player.queue.count}** tracks.")
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

    @app_commands.command(name="nowplaying", description="Show the track currently playing")
    async def nowplaying(self, interaction: discord.Interaction):
        player: wavelink.Player | None = interaction.guild.voice_client
        if not player or not player.connected or not player.current:
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
        if player.queue.count:
            footer += f" - {player.queue.count} track{'s' if player.queue.count != 1 else ''} queued"
        embed.set_footer(text=footer)

        await interaction.followup.send(embed=embed)

    @app_commands.command(name="queue", description="Show the queue")
    async def queue(self, interaction: discord.Interaction):
        player: wavelink.Player | None = interaction.guild.voice_client
        if not player or not player.connected:
            raise UserError("I'm not playing anything right now.")

        await interaction.response.defer()

        header = ""
        if player.current:
            header = f"**Now playing**\n{format_track(player.current)}\n\n"

        if player.queue.is_empty:
            pages = [f"{header}**Up next**\nThe queue is empty."]
        else:
            tracks = list(player.queue)
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
