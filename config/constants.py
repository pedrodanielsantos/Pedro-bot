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
MUSIC_QUEUE_PAGE_SIZE = 10     # tracks per /queue page
MUSIC_AUTOCOMPLETE_LIMIT = 25  # Discord's hard cap on autocomplete choices

# Search prefixes tried, in order, to replace a track the node refuses to
# stream. A YouTube Music entry that fails often has a plain YouTube upload that
# doesn't, so ytsearch comes before leaving YouTube entirely.
MUSIC_FALLBACK_SOURCES = ("ytsearch", "scsearch")
MUSIC_FALLBACK_TOLERANCE = 15  # seconds a replacement may differ in length from the original

# Search prefixes tried, in order, for a track known only by its metadata, such
# as one from a Spotify link. ytmsearch leads because it returns songs rather
# than the covers and lyric uploads a plain YouTube search mixes in.
MUSIC_SEARCH_SOURCES = ("ytmsearch", "ytsearch", "scsearch")
MUSIC_PREFETCH = 3         # metadata-only tracks resolved ahead of the one playing
MUSIC_MISS_LIMIT = 5       # unresolvable tracks in a row before the rest are dropped
MUSIC_SPOTIFY_LIMIT = 100  # tracks Spotify's embed page returns for a playlist