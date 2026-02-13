import discord
from discord import app_commands

class HexColorTransformer(app_commands.Transformer):
    async def transform(self, interaction: discord.Interaction, value: str) -> discord.Color:
        if not value.startswith("#"):
            value = f"#{value}"
        
        if len(value) != 7 or not all(c in "0123456789ABCDEFabcdef#" for c in value):
            raise ValueError("Invalid HEX color code! Use a format like `#FF5733` or `FF5733`.")
            
        return discord.Color(int(value[1:], 16))