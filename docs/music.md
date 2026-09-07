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
says whether any client still gets a direct URL. SoundCloud and Bandcamp are
native Lavalink sources that never touch this path, so they make a good control
test.

Not every failure is an extraction problem. A playlist can carry entries whose
underlying upload is deleted or region locked, where every client reports "This
video is not available". For those, `music_manager` re-searches the author,
minus any `- Topic` suffix naming an auto-generated channel, and the title
against `MUSIC_FALLBACK_SOURCES` (plain YouTube first, then SoundCloud),
requires the result to be within `MUSIC_FALLBACK_TOLERANCE` seconds of the
original length, and queues it in the failed track's place.

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
track fails with `Invalid status code for soundcloud stream: 404`. No Lavalink
release reads the AAC transcodings and there is no setting for it, so upgrading
does not help. Migration is per track, so duplicate uploads usually still play,
which is exactly what the retry finds. Expect that to fade as the rollout
finishes.

## Spotify links

Spotify serves no audio, so `/play` reads a link's metadata from its embed page
and searches for the same recording on `MUSIC_SEARCH_SOURCES` (YouTube Music,
YouTube, then SoundCloud), taking the first result within
`MUSIC_FALLBACK_TOLERANCE` seconds of the original length. The Spotify API needs
the app owner to hold Premium, so it is not used and LavaSrc's sources stay off.

Tracks resolve `MUSIC_PREFETCH` ahead of playback, a page of `/queue` worth, and
top up as each one starts and after `/skip` drops part of the queue, so a long
playlist costs a search per track played rather than hundreds at once. After
`MUSIC_MISS_LIMIT` misses in a row the rest is dropped.

The metadata arrives in one request, so `/queue` lists the whole playlist right
away, with the tracks it hasn't looked up yet carrying no link. `/skip` and
`/shuffle` count those positions too, rather than only the resolved ones.

The embed page returns at most `MUSIC_SPOTIFY_LIMIT` tracks for a playlist, and
carries no ISRC, so a match rests on artist, title and length.
