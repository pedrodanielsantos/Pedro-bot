# config/constants.py

# Lobby settings
NEW_LOBBY_TRIGGER = "➕ New Lobby"
LOBBY_NAME = "Lobby"
LOBBY_EMOJI = "🎧"

# Voice channel settings
VOICE_VQM     = 2              # int value for discord.VideoQualityMode.full
VOICE_REGION  = "rotterdam"    # Region override
VOICE_NAME_MAX_LENGTH = 100    # 100 is the maximum discord will display (tested)

# Sentinel for "let Discord pick", stored as text since rtc_region=None can't be saved.
# Every other region id comes from Discord's live list (utils/regions.py).
VOICE_REGION_AUTOMATIC = "automatic"

# Embed settings
EMBED_COLOR = 0x4c4c54
EMBED_COLOR_WARNING = 0xffcc4d
SUCCESS_COLOR = 0x77b255
ERROR_COLOR = 0xdd2e44