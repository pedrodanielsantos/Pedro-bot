import discord

_HEX_DIGITS = "0123456789abcdefABCDEF"

def parse_hex_color(value: str) -> discord.Color:
    """Parses a hex color code like "#FF5733" or "FF5733" into a Color."""
    value = value.lstrip("#")

    if len(value) != 6 or not all(char in _HEX_DIGITS for char in value):
        raise ValueError("Invalid HEX color code! Use a format like `#FF5733` or `FF5733`.")

    return discord.Color(int(value, 16))
