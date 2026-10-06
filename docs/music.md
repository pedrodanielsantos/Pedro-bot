# Music

Audio is streamed by [Lavalink](https://lavalink.dev/), a standalone Java node
that the bot controls over a loopback WebSocket via
[Wavelink](https://github.com/PythonistaGuild/Wavelink). The bot resolves and
queues tracks. Lavalink opens the voice connection, decodes, and sends Opus.

That split is why the `PyNaCl is not installed` and `davey is not installed`
startup warnings are harmless. They gate discord.py's own `VoiceClient`, which
sends audio in-process. `wavelink.Player` only relays the voice session, and
Lavalink handles encryption, DAVE included.

## Architecture

| Piece | Role |
| --- | --- |
| `Lavalink.jar` | Standalone node on `127.0.0.1:2333`, started by `run.py` |
| [`youtube-source`](https://github.com/lavalink-devs/youtube-source) | YouTube and YouTube Music extraction, pinned to a snapshot |
| [`LavaSrc`](https://github.com/topi314/LavaSrc) | Installed but all sources off, see [Spotify links](#spotify-links) and [Tidal links](#tidal-links) |
| [`cogs/core/music_manager.py`](../cogs/core/music_manager.py) | Owns the node connection and playback lifecycle |
| [`cogs/commands/music.py`](../cogs/commands/music.py) | The slash commands |
| [`utils/music.py`](../utils/music.py) | Player lookup, DJ gating, announce channel, track formatting, track search and its cache |
| [`utils/spotify.py`](../utils/spotify.py) | Spotify link parsing and metadata |
| [`utils/tidal.py`](../utils/tidal.py) | Tidal link parsing and metadata, via the API or the page |

The node is **optional**. If `LAVALINK_DIR` is unset, or `Lavalink.jar`,
`application.yml` or `java` is missing, `run.py` logs which and skips the node.
The bot starts normally and the music commands report themselves as unavailable.

Constants named below live in [`config/constants.py`](../config/constants.py)
unless stated otherwise.

## Node setup

Needs **Java 17+** on the host, 21 LTS recommended. A JRE is enough. Install
[Temurin](https://adoptium.net/) on Windows, or:

```bash
sudo apt install openjdk-21-jre-headless    # Debian/Ubuntu
```

Open a new shell so `java` is on `PATH`, then:

```bash
py -3.13 scripts/setup_lavalink.py
```

This downloads `Lavalink.jar` and the LavaSrc plugin, renders `application.yml`
from [`config/lavalink/application.yml.example`](../config/lavalink/application.yml.example)
with a generated password, and prints the `.env` lines to add. Re-running keeps
existing files unless `--force` is passed. The install dir defaults to
`\lavalink` on the system drive or `/opt/lavalink`, and `--dir` overrides it.

> [!IMPORTANT]
> Pick a directory the bot's user can write to. Lavalink writes its logs and
> plugin jars next to its own jar, so a read-only location fails at startup.

Only the template is tracked. The rendered `application.yml` holds the real
password and stays on the host.

## YouTube extraction

This is the part that breaks, not the infrastructure. Two settings in
`application.yml` matter:

- **`youtube-plugin` is a snapshot dependency**, not a shipped jar, because
  tagged releases lag behind YouTube's changes. Snapshot versions are commit
  hashes, listed
  [here](https://maven.lavalink.dev/snapshots/dev/lavalink/youtube/youtube-plugin/).
  Only one copy may be installed: delete any `plugins/youtube-plugin-*.jar`
  before starting.
- **Every client but `ANDROID` is listed**, ordered by how likely each is to
  return a plain HTTPS URL. Which ones work varies by IP and region, and a
  failing client costs one request, so a short list risks losing playback
  entirely. `ANDROID` is left out because the plugin reports it broken, with no
  known fix, on every start. `MUSIC` only serves `ytmsearch`: it loads no links,
  `music.youtube.com` ones included, and doesn't stream, so it can never be the
  only client.

SoundCloud and Bandcamp are native Lavalink sources that never touch this path,
so they make a good control test.

### Diagnosing failures

A failed load lists every client with its own reason, which shows whether any
client still gets a direct URL. Each reason is a full Java stack trace, printed
by the node, Wavelink and the bot. Only the bot's one-line summary reaches the
console: the other two are filtered by `_QUIET_NODE_LOGGERS` in
[`run.py`](../run.py) and `quiet_duplicate_loggers()` in
[`utils/log.py`](../utils/log.py). Set `LOG_LEVEL=DEBUG` in `.env` to get the
per-client reasons back. The node's own `logs/` keep the full trace either way.

At `INFO`, each failed track gets one line:

| Level | Meaning |
| --- | --- |
| `WARNING` | A stand-in took its place, or it failed after its audio had started |
| `ERROR` | It was lost outright |

The exception's `severity` isn't worth branching on: a login-walled video
reports `suspicious`, a dead stand-in reports `fault`, and `common` does not
appear at all.

### Signature ciphers

YouTube hands some clients a stream URL with a scrambled signature. The function
that unscrambles it sits in the player's `base.js`, which the plugin downloads
and searches by pattern, since the script is minified and its names aren't
stable. When the pattern no longer matches, this is logged at `ERROR`:

```
lavalink.LocalSignatureCipherManager: Problematic YouTube player script
/s/player/<hash>/player_embed.vflset/<locale>/base.js detected
(issue detected with script: must find sig function). Dumped to <temp file>
```

- **No one client causes it.** `CipherManager.getPlayerScript()` always fetches
  `https://www.youtube.com/embed/` and takes the `jsUrl` that page advertises,
  whatever client asked, and the result is cached and shared. Removing clients
  doesn't change which script is parsed, and `player_embed` in the path names
  YouTube's page, not the `WEBEMBEDDED` client.
- **Nor does the locale.** It is YouTube localizing that page for the node. Two
  locale builds of one player differ only in translated text and where the
  minifier wrapped the lines.
- **Playback usually survives it.** `ANDROID_MUSIC`, `ANDROID_VR` and `IOS` set
  `requirePlayerScript()` to false, the first two by extending `Android`, and a
  format can carry no signature at all, so a client that needs no deciphering
  plays normally. The line returns whenever the cached script is refreshed and
  still doesn't match.

If deciphering becomes load-bearing, because the clients that need no signature
stop returning direct URLs, the fix is a remote cipher server. Setting
`plugins.youtube.remoteCipher` (`url`, `password`, `userAgent`) swaps
`LocalSignatureCipherManager` for `RemoteCipherManager`, which posts the
signature to a service that executes the player script instead of pattern
matching it. [yt-cipher](https://github.com/kikkia/yt-cipher) is the one upstream
recommends, self-hosted or via its public instance. Check the script variant
first: yt-cipher documents that only the `IAS` variants consistently work, and
the URL above is the embed variant.

## Failed tracks

Not every failure is an extraction problem. A playlist can hold entries whose
upload is deleted or region locked, where every client reports "This video is
not available". `music_manager` plays a stand-in in their place.

### Finding a stand-in

The author, minus any `- Topic` suffix naming an auto-generated channel, and the
title are searched on `MUSIC_FALLBACK_SOURCES` (plain YouTube, then SoundCloud).
A candidate must be within `MUSIC_FALLBACK_TOLERANCE` seconds of the original's
length, but length alone picks the wrong song: a cover, a live take or a sped up
edit runs about as long and can outrank the original. So candidates in that
window are then:

1. **Ruled out** if they carry any of `MUSIC_VERSION_MARKERS` that the wanted
   title doesn't. A remix or a cover is a different recording, and skipping the
   track beats playing one. A remix asked for by name carries its own marker, so
   other remixes stay eligible for it.
2. **Scored** on the share of the wanted title's words they carry, which must
   reach `MUSIC_MATCH_FLOOR`. The artist's words are left out of it, since the
   author is scored separately and an "Artist - Song" upload would count them
   twice.
3. **Ranked** by that share, with the author and closeness of length as
   tiebreakers.

A source is only left behind once nothing in it clears the floor, which keeps
the common case at one search.

### Retrying

A stand-in can fail too, so the search repeats with every identifier already
tried excluded, up to `MUSIC_FALLBACK_ATTEMPTS` deep. The exclusion set only
grows, so a chain terminates. The depth rides on the track's `extras`, which
Lavalink stores as `userData` and returns on its events. A counter on the player
would not work: a stand-in reports a normal track start before failing, which
would reset it.

This matters most for SoundCloud, which is
[dropping MP3 and Opus transcodings](https://developers.soundcloud.com/blog/api-streaming-urls/)
for AAC HLS. Lavaplayer only selects `hls` and `progressive`, so a migrated
track fails with `Invalid status code for soundcloud stream: 404`, and no
Lavalink release or setting changes that. Migration is per track, so a duplicate
upload usually still plays, which is what the retry finds.

That 404 arrives as the exception's `cause`, while its `message` is only the
generic "Something broke when playing the track.", so `music_manager` appends
the cause in parentheses.

### Advancing the queue

Wavelink's autoplay is off (`AutoPlayMode.disabled`), and `music_manager` starts
the next track from `on_wavelink_track_end` instead. Autoplay moves on as soon
as a track ends, so a stand-in could only play after whatever had already
started. It also stops for good after three failed loads in a row, since its
error count is checked before it is reset.

A failed load arrives as a `TrackExceptionEvent` followed by a `TrackEndEvent`
with reason `loadFailed`. The exception handler only records the error on the
player. The end handler reads it and plays a stand-in straight away, or the next
queued track when there is none. A `TrackStuckEvent` takes the same path: the
track is marked stuck and skipped, and its end is treated as a failed load.

## Announcements

Three messages are posted without a command asking for them, all from
`music_manager`:

| Message | When |
| --- | --- |
| Now playing | Once a track's audio starts, see [Now playing](#now-playing) |
| Couldn't find a playable version of X, skipping. | A failed track has no stand-in |
| Left #channel after being idle. | Nothing has played for `MUSIC_IDLE_TIMEOUT` seconds |

Leaving because the voice channel emptied is silent.

### Where they go

`announce_channel()` in [`utils/music.py`](../utils/music.py) picks the channel
each time one is sent:

1. The guild's music channel, set with `/set musicchannel`.
2. Otherwise `player.home`, the channel `/play` or `/insert` last ran in. Both
   set it before searching, so a `/play` that finds nothing still moves it, but
   an `/insert` refused by the DJ role doesn't. No other command touches it, and
   it is dropped with the player on disconnect.

Being read per message, a music channel set, changed or reset mid-session
applies from the next announcement. One deleted since it was set falls back to
`player.home`, and `/serverconfig` shows it as deleted.

### Now playing

Lavaplayer dispatches `TrackStartEvent` before the track is loaded, so a track
about to fail starts like any other. The announcement waits for audio instead,
polling the node's player state every `MUSIC_ANNOUNCE_POLL` seconds until the
reported position moves past 0. That position is the timecode of the last frame
handed to Discord, so it only moves once the track is audible. A track that ends
first, or has no audio after `MUSIC_ANNOUNCE_TIMEOUT` seconds (extended while
paused), is not announced.

The announcement's footer names who queued the track, from a `requester_id` in
its `extras`. `with_requester()` in [`utils/music.py`](../utils/music.py) sets
it on a copy, since search results are cached and shared. Spotify and Tidal
tracks left pending carry it on their `PendingTrack` until `fill_queue` resolves
them. A requester who has since left the guild gets no footer.

A stand-in's announcement adds a line naming the track it replaces. The
original's title and author ride on the stand-in's `extras` next to its fallback
depth and requester, so a stand-in for a stand-in still names what was queued.

### Command replies

Commands work in any channel. With a music channel set, the ones that change
playback (`/play`, `/insert`, `/skip`, `/pause`, `/resume`, `/stop`,
`/shuffle`, `/loop`, `/seek`, and `/volume` with a value) reply privately when
run elsewhere, and post a public copy in the music channel. Run inside it, or
with none set, they reply publicly in place. `/queue`, `/playing` and `/volume`
without a value only report, so they always reply in place.

The copy names the caller in a "Requested by" footer, since a message the bot
sends itself has none of the "used /command" header Discord puts on a reply.

Music replies and announcements use the server's embed color, through
`guild_embed()` in [`utils/embeds.py`](../utils/embeds.py) for plain replies.
None use `success_embed`'s green, so in a channel full of them only errors
stand out, in red. `/set djrole`, `/set musicvolume` and `/set musicchannel` are
server configuration, so they keep success green like `/set lobbyregion`.

Whether a reply is ephemeral is fixed by the first response, so `/play`,
`/insert` and `/shuffle` read the setting before deferring. Errors after that
defer follow it.

## Track suggestions

`/play` and `/insert` can suggest tracks while a query is typed, which is off
unless `MUSIC_AUTOCOMPLETE=true` is set in `.env`. The flag is read at import and
decides whether the callbacks are registered, so it reaches Discord with the
synced command. Changing it needs a restart and a sync.

Discord decides when to ask. Its docs only promise suggestions "as they type"
and name no interval, so a query typed slowly might be searched several times,
where sending it costs one search. The cache softens that: it holds
`MUSIC_SEARCH_CACHE` queries for `MUSIC_SEARCH_CACHE_TTL` seconds, shared with
`/play`, so a query sent as typed isn't searched again. Backspacing is served
from it, since a shorter query is a prefix of one already searched. Typing
forward isn't, so it searches. A search that outruns Discord's three seconds
keeps going to fill the cache, and the closest cached query is suggested
meanwhile. Queries shorter than `AUTOCOMPLETE_MIN_LENGTH` (in
[`cogs/commands/music.py`](../cogs/commands/music.py)) and pasted links never
search at all.

Picking a suggestion sends the track's URI rather than its label. While the
search that suggested it is cached, `/play` takes the track from there without
asking the node. Otherwise the URI is loaded directly, and a YouTube Music
result's URI is a plain `youtube.com` link, which loads with the video's channel
and thumbnail (see [YouTube Music links](#youtube-music-links)). A track with no
URI, or one over Discord's 100 character limit for a choice value, sends its
label instead, which is searched like any other query.

## YouTube Music links

youtube-source loads every YouTube link, whatever its host, through the video
endpoint. That credits the uploading channel, such as an auto-generated
`Artist - Topic` one, and gives the video's 16:9 thumbnail. Only a YouTube Music
search result credits the artist and carries the album art, and the `MUSIC`
client only searches.

So a single-track `music.youtube.com/watch` link is first searched on YouTube
Music by its video id. The result is used only if it has that same id, so it is
the same upload either way. A hit takes the link load's place. A miss falls back
to it, which costs a second request. Each hit or miss is logged at `DEBUG`, and
the result is cached under the link like any other query.

A link carrying a list loads as a playlist or radio and is left to do that,
except `LL`, `WL` and `LM`. Those need a signed-in account, so youtube-source
ignores them and loads the video alone.

## Spotify links

Spotify serves no audio, so `/play` reads a link's metadata from its embed page
and searches for the same recording on `MUSIC_SEARCH_SOURCES` (YouTube Music,
YouTube, then SoundCloud), scored the same way a stand-in is. The Spotify API
needs the app owner to hold Premium, so it is not used and LavaSrc's sources
stay off.

Only `MUSIC_PREFETCH` tracks are resolved ahead of playback, topped up as each
one starts and after `/skip` drops part of the queue, so a long playlist costs a
search per track played rather than hundreds at once. After `MUSIC_MISS_LIMIT`
misses in a row the rest is dropped.

The metadata arrives in one request, so `/queue` lists the whole playlist right
away, with tracks not yet looked up carrying no link. `/skip` and `/shuffle`
count those positions too.

The embed page returns at most `MUSIC_SPOTIFY_LIMIT` tracks for a playlist and
carries no ISRC, so a match rests on artist, title and length.

`/insert` takes a track link but refuses an album or playlist, which only ever
resolves onto the back of the queue. Inserting one would mean resolving all of
it up front.

## Tidal links

Handled the same way and for the same reason: Tidal serves no audio here, so
`/play` reads the metadata and finds the recording elsewhere. LavaSrc's Tidal
source needs an undocumented token and throws at startup without one, so it
stays off and [`utils/tidal.py`](../utils/tidal.py) reads Tidal directly.

`listen.tidal.com`, `www.tidal.com` and `tidal.com` all match, with `/browse/`
optional. An artist link is deliberately not matched: there is no one recording
behind it, so it falls through to the ordinary search.

Which reader runs depends on whether `TIDAL_CLIENT_ID` and `TIDAL_CLIENT_SECRET`
are set:

| Link | With credentials | Without |
| --- | --- | --- |
| Track | API | Track page |
| Album, playlist | API | Refused, with a message saying why |
| Mix | Refused, no endpoint exists for one | Refused |

### The API

An app registered at [developer.tidal.com](https://developer.tidal.com) is free
and needs no paid account. Its client credentials mint a four hour token, cached
and shared between commands, and dropped early if it stops being accepted, so a
rotated secret costs one request rather than every request until it expires. The
catalogue needs no scopes: album, playlist and track reads all sit at the
`THIRD_PARTY` tier that self-serve registration grants. No country is sent,
since only title, artists and length are read.

One request returns the collection, its cover art, its first 20 tracks with
their artists, and a cursor for the next 20. `include=items,items.artists` pulls
the artists along, where otherwise each track would cost a request. Only `items`
is documented, so if the nested form stops working the tracks arrive without
artists and are searched on title alone, which is logged.

Past a burst of about eight, requests are refused with a `429` carrying
`Retry-After`, and no headers advertise the budget. One wait and one retry is
the whole strategy: a second refusal means something else is using the budget,
and the command gives up rather than holding the interaction open.

### Why collections stop at 100

`MUSIC_PLAYLIST_LIMIT` caps what one link contributes. Pages hold 20 and the
cursor has to be followed one at a time, so 100 tracks is five requests and
about a second, while a 10,000 track playlist would be 500 requests and run
straight into the rate limit.

Everything is read up front rather than a page at a time, because `/queue`,
`/skip` and `/shuffle` all work from [`queued_tracks`](../utils/music.py).
Paging lazily would leave them acting on whatever happened to be loaded, so a
shuffle would reorder the first 20 and leave the rest in order. Within the cap,
a Tidal collection behaves exactly like a Spotify one, except that its count is
exact: where Spotify can only hint that it was cut short, a Tidal collection
says which 100 of how many were taken.

A playlist may also hold videos. They carry no recording to search for, so they
are skipped, and the total comes from `numberOfTrackItems` rather than
`numberOfItems` so the two agree.

### Without credentials

A track page embeds the recording as schema.org JSON-LD, which answers anonymous
callers and carries the title, artists and duration. The page holds more than
one such block in no promised order, so the one typed `MusicRecording` is
picked. Its cover art is read past: the embed shows the resolved track's own,
as for a Spotify track.

This is the fallback rather than the default because the API is the sanctioned
route, is versioned, and doesn't depend on a page keeping its markup. It stays
because it needs nothing configured, so track links work on a fresh clone. An
album or playlist page carries no track list, so it cannot stand in there.

### The ISRC is ignored

Both readers carry an ISRC, which names the exact recording and so looks like a
better key than the title. No source here indexes it: YouTube Music answers a
code with unrelated results and plain YouTube with none, so searching it costs a
request and finds nothing. Scoring such a result on title would defeat the
point of the code, and not scoring it leaves only the length check between a
wrong track and the queue. So it is read past, and a pending track costs one
search whichever link it came from.
