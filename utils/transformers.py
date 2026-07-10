import discord
from discord import app_commands

class HexColorTransformer(app_commands.Transformer):
    async def transform(self, interaction: discord.Interaction, value: str) -> discord.Color:
        value = value.lstrip("#")

        if len(value) != 6 or not all(char in "0123456789ABCDEFabcdef" for char in value):
            raise ValueError("Invalid HEX color code! Use a format like `#FF5733` or `FF5733`.")

        return discord.Color(int(value, 16))