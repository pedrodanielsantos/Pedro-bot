# Music

Audio is streamed by [Lavalink](https://lavalink.dev/), a standalone Java node
that the bot controls over a loopback WebSocket via
[Wavelink](https://github.com/PythonistaGuild/Wavelink). The bot never touches
audio itself: it resolves and queues tracks, and Lavalink opens the voice
connection, decodes, and sends Opus.

That split is why the `PyNaCl is not installed` and `davey is not installed`
warnings at startup are harmless. They gate discord.py's own `VoiceClient`,
which encrypts and sends audio in-process. `wavelink.Player` is a bare
`VoiceProtocol` that only relays the voice session to Lavalink, and Lavalink
handles encryption, including DAVE, on its side.

## Architecture

| Piece | Role |
| --- | --- |
| `Lavalink.jar` | Standalone node on `127.0.0.1:2333`, started by `run.py` |
| [`youtube-source`](https://github.com/lavalink-devs/youtube-source) | YouTube and YouTube Music extraction, pinned to a snapshot |
| [`LavaSrc`](https://github.com/topi314/LavaSrc) | Installed but all sources off, see [Spotify links](#spotify-links) |
| [`cogs/core/music_manager.py`](../cogs/core/music_manager.py) | Owns the node connection and playback lifecycle |
| [`cogs/commands/music.py`](../cogs/commands/music.py) | The slash commands |
| [`utils/music.py`](../utils/music.py) | Player lookup, DJ gating, track formatting, track search |
| [`utils/spotify.py`](../utils/spotify.py) | Spotify link parsing and metadata |

The node is **optional**. With `LAVALINK_DIR` unset, or `Lavalink.jar`,
`application.yml` or `java` missing, `run.py` logs which one and skips the node,
the bot starts normally, and the music commands report themselves as
unavailable.

## Node setup

Needs a **JDK 17+** on the host, 21 LTS recommended. Install
[Temurin](https://adoptium.net/) on Windows, or:

```bash
sudo apt install openjdk-21-jre-headless    # Debian/Ubuntu
```

Open a new shell afterwards so `java` is on `PATH`, then:

```bash
py -3.13 scripts/setup_lavalink.py
```

That downloads `Lavalink.jar` and the LavaSrc plugin, renders `application.yml`
from [`config/lavalink/application.yml.example`](../config/lavalink/application.yml.example)
with a generated password, and prints the `.env` lines to add. Re-running keeps
what's already there unless `--force` is passed. Default install dir is
`C:\lavalink` or `/opt/lavalink`, overridable with `--dir`.

> [!IMPORTANT]
> Pick a directory the bot's user can write to. Lavalink writes its logs and
> plugin jars next to its own jar, so a read-only or locked-down location fails
> at startup.

Only the config template is tracked. The rendered `application.yml` holds the
real password and stays on the host, outside the repo.

## YouTube extraction

This is the part that breaks, not the infrastructure. Two settings in
`application.yml` matter:

- **`youtube-plugin` is declared as a snapshot dependency**, not shipped as a jar,
  because tagged releases lag behind YouTube's changes. Snapshot versions are
  commit hashes, listed
  [here](https://maven.lavalink.dev/snapshots/dev/lavalink/youtube/youtube-plugin/).
  Only one copy may be installed: delete any `plugins/youtube-plugin-*.jar`
  before starting.
- **All ten clients are listed**, ordered by how likely each is to return a plain
  HTTPS URL. Which ones work varies by IP and region, and a client that fails
  costs one request, so a short list risks total playback failure. `MUSIC`
  resolves `music.youtube.com` links and `ytmsearch` but does not stream, so it
  can never be the only client.

When playback fails, the error enumerates every client with its own reason, which
says whether any client still gets a direct URL. That enumeration is a full Java
stack trace per client, and three programs print it: the node, Wavelink, and the
bot. Only the bot's own summary reaches the console; the other two are filtered
out by `_QUIET_NODE_LOGGERS` in [`run.py`](../run.py) and
`quiet_duplicate_loggers()` in [`utils/log.py`](../utils/log.py). Set
`LOG_LEVEL=DEBUG` in `.env` to get the per-client reasons back, which is the
point of this section, so expect to do that when diagnosing extraction.

What stays at `INFO` is one line per failed track: **`WARNING`** when a stand-in
took its place, **`ERROR`** when the track was lost outright. The node's own
`logs/` keep the full trace either way.

The exception's `severity` is not worth branching on: a login-walled video
reports `suspicious` and a dead stand-in reports `fault`, while `common` does not
appear at all, so it separates nothing a reader cares about.

SoundCloud and Bandcamp are native Lavalink sources that never touch this path,
so they make a good control test.

Not every failure is an extraction problem. A playlist can carry entries whose
underlying upload is deleted or region locked, where every client reports "This
video is not available". For those, `music_manager` re-searches the author,
minus any `- Topic` suffix naming an auto-generated channel, and the title
against `MUSIC_FALLBACK_SOURCES` (plain YouTube first, then SoundCloud),
requires the result to be within `MUSIC_FALLBACK_TOLERANCE` seconds of the
original length, and queues the best match in the failed track's place.

Length alone picks the wrong song, since a cover, a live take or a sped up edit
runs about as long as the original and any of them can outrank it in a source's
results. So candidates inside that window are scored instead: what share of the
wanted title's words a candidate carries, minus the artist's own words since the
author is scored separately and an upload titled "Artist - Song" would otherwise
count it twice, which must reach `MUSIC_MATCH_FLOOR`,
then the author and how close the length is as tiebreakers, minus a penalty for
each of `MUSIC_VERSION_MARKERS` it carries that the wanted title does not. The
penalty outweighs the tiebreakers, so a marked version only wins when nothing
else matched, and a remix asked for by name keeps its marker unpenalised. A
source is only left behind once nothing in it clears the floor, which keeps the
common case at one search.

A stand-in can fail too, so the search repeats with every identifier already
tried excluded, up to `MUSIC_FALLBACK_ATTEMPTS` deep. That depth rides on the
track's `extras`, which Lavalink stores as `userData` and returns on its events:
a stand-in announces a normal track start before failing, so a counter on the
player would be reset by the very track it counts. The exclusion set only grows,
so a chain terminates. Constants live in
[`config/constants.py`](../config/constants.py).

That retry matters most for SoundCloud, which is
[dropping MP3 and Opus transcodings](https://developers.soundcloud.com/blog/api-streaming-urls/)
for AAC HLS. Lavaplayer only selects `hls` and `progressive`, so a migrated
track fails with `Invalid status code for soundcloud stream: 404`. That string
arrives as the exception's `cause`; its `message` is only the generic "Something
broke when playing the track.", which is why `music_manager` appends the cause in
parentheses rather than logging the message alone. No Lavalink release reads the
AAC transcodings and there is no setting for it, so upgrading does not help.
Migration is per track, so duplicate uploads usually still play, which is exactly
what the retry finds. Expect that to fade as the rollout finishes.

## Track suggestions

`/play` and `/insert` can suggest tracks while a query is typed, which is off
unless `MUSIC_AUTOCOMPLETE=true` is set in `.env`. Discord decides when to ask:
its docs only promise suggestions "as they type" and name no interval, so a
query typed slowly or in pauses might be searched several times over, where the
same query sent costs one search.

The flag is read at import and decides whether the callbacks are registered, so
it reaches Discord as part of the synced command rather than being read per
interaction. Changing it needs a restart and a sync.

What softens that is the cache: `MUSIC_SEARCH_CACHE` queries for
`MUSIC_SEARCH_CACHE_TTL` seconds, shared with `/play` so a query sent as typed
isn't searched again. Backspacing is served from it, since a shorter query is a
prefix of one already searched, while typing forward isn't and so searches.
Queries shorter than `AUTOCOMPLETE_MIN_LENGTH` in
[`cogs/commands/music.py`](../cogs/commands/music.py) and pasted links never
search at all.

Picking a suggestion sends the track's URI rather than the text, so the node
resolves it directly instead of searching. A track with no URI, or one over
Discord's 100 character limit for a choice value, sends its label instead, which
is searched like any other query.

## Spotify links

Spotify serves no audio, so `/play` reads a link's metadata from its embed page
and searches for the same recording on `MUSIC_SEARCH_SOURCES` (YouTube Music,
YouTube, then SoundCloud), scored the same way a stand-in is. The Spotify API needs
the app owner to hold Premium, so it is not used and LavaSrc's sources stay off.

Tracks resolve `MUSIC_PREFETCH` ahead of playback, only the one about to play,
and top up as each one starts and after `/skip` drops part of the queue, so a
long playlist costs a search per track played rather than hundreds at once.
After `MUSIC_MISS_LIMIT` misses in a row the rest is dropped.

The metadata arrives in one request, so `/queue` lists the whole playlist right
away, with the tracks it hasn't looked up yet carrying no link. `/skip` and
`/shuffle` count those positions too, rather than only the resolved ones.

The embed page returns at most `MUSIC_SPOTIFY_LIMIT` tracks for a playlist, and
carries no ISRC, so a match rests on artist, title and length.
