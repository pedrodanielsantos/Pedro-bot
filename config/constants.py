# config/constants.py

# Lobby settings
NEW_LOBBY_TRIGGER = "➕ New Lobby"
LOBBY_NAME = "Lobby"
LOBBY_EMOJI = "🎧"

# Voice channel settings
VOICE_VQM     = 2              # int value for discord.VideoQualityMode.full
VOICE_NAME_MAX_LENGTH = 100    # 100 is the maximum discord will display (tested)

# Sentinel for "let Discord pick", stored as text since rtc_region=None can't be saved.
# Regions are configured per guild with /set lobbyregion; every other id comes from
# Discord's live list (utils/regions.py).
VOICE_REGION_AUTOMATIC = "automatic"

# Embed settings
EMBED_COLOR = 0x4c4c54
EMBED_COLOR_WARNING = 0xffcc4d
SUCCESS_COLOR = 0x77b255
ERROR_COLOR = 0xdd2e44

# Music settings
MUSIC_DEFAULT_VOLUME = 60      # percent, overridable per guild with /set musicvolume
MUSIC_MAX_VOLUME = 150         # above this the Opus encoder clips audibly
MUSIC_IDLE_TIMEOUT = 300       # seconds with nothing playing before the bot disconnects
MUSIC_VOICE_RESUME_DELAY = 6   # seconds to wait out a voice drop, over Lavalink's 5s playerUpdateInterval
MUSIC_QUEUE_PAGE_SIZE = 10     # tracks per /queue page
MUSIC_AUTOCOMPLETE_LIMIT = 25  # Discord's hard cap on autocomplete choices
MUSIC_AUTOCOMPLETE_BUDGET = 3.0  # seconds Discord allows an autocomplete reply, which can't be deferred
MUSIC_AUTOCOMPLETE_MARGIN = 0.6  # seconds of that budget held back for the reply to reach Discord
MUSIC_SEARCH_CACHE = 64          # queries whose results are kept, shared by the query autocomplete and /play
MUSIC_SEARCH_CACHE_TTL = 180     # seconds a cached search stays usable

# Search prefixes tried, in order, to replace a track the node refuses to
# stream. A YouTube Music entry that fails often has a plain YouTube upload that
# doesn't, so ytsearch comes before leaving YouTube entirely.
MUSIC_FALLBACK_SOURCES = ("ytsearch", "scsearch")
MUSIC_FALLBACK_TOLERANCE = 15  # seconds a replacement may differ in length from the original
# Stand-ins tried before a track is given up on. A search only reaches this if
# every earlier stand-in also failed to play, which SoundCloud now makes routine:
# see the transcoding note in docs/music.md.
MUSIC_FALLBACK_ATTEMPTS = 3

# Words marking a different version of the same song, penalised unless the
# wanted title carries them too.
MUSIC_VERSION_MARKERS = (
    "remix", "live", "cover", "acoustic", "instrumental", "karaoke",
    "sped up", "slowed", "nightcore", "reverb", "8d", "mashup",
    "bootleg", "flip", "rework", "vip",
)
MUSIC_MATCH_FLOOR = 0.6  # fraction of the wanted title's words a candidate must carry

# Search prefixes tried, in order, for a track known only by its metadata, such
# as one from a Spotify link. ytmsearch leads because it returns songs rather
# than the covers and lyric uploads a plain YouTube search mixes in.
MUSIC_SEARCH_SOURCES = ("ytmsearch", "ytsearch", "scsearch")
# Only the track about to play, so each queued track costs one search and no
# more. Everything behind it stays unresolved in /queue until its turn comes.
MUSIC_PREFETCH = 1
MUSIC_MISS_LIMIT = 5       # unresolvable tracks in a row before the rest are dropped
MUSIC_SPOTIFY_LIMIT = 100  # tracks Spotify's embed page returns for a playlist
# Tracks taken from one Tidal album or playlist. Spotify needs no such cap: its
# embed page stops at MUSIC_SPOTIFY_LIMIT on its own. Tidal pages hold 20 each,
# so 100 is five requests, against a burst of about eight before it starts
# refusing, which is why raising this runs into the rate limit.
MUSIC_PLAYLIST_LIMIT = 100