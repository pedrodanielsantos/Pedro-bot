import discord
from discord.ext import commands
from discord import app_commands
from imagine_models import models  # Import your models dictionary
import sqlite3

# Connect to the SQLite database
models_db_conn = sqlite3.connect("imagine_models.db")
models_db_cursor = models_db_conn.cursor()


class ModelSelectView(discord.ui.View):
    def __init__(self, models):
        super().__init__(timeout=60)
        self.models = models
        self.message = None

        # Create a button for each model
        for index, (key, model) in enumerate(models.items(), start=1):
            emoji = f"{index}\u20e3"
            button = discord.ui.Button(label=model["name"], emoji=emoji, custom_id=key, style=discord.ButtonStyle.primary)
            button.callback = self.make_button_callback(key)
            self.add_item(button)

    def make_button_callback(self, model_key):
        async def callback(interaction: discord.Interaction):
            # Save the selected model to the database
            models_db_cursor.execute(
                "INSERT OR REPLACE INTO user_models (user_id, model_name) VALUES (?, ?)",
                (interaction.user.id, model_key)
            )
            models_db_conn.commit()

            # Notify the user of their selection
            selected_model_name = self.models[model_key]["name"]
            await interaction.response.send_message(
                f"You've selected the model: **{selected_model_name}**!", ephemeral=True
            )

            # Disable the buttons after selection
            if self.message:
                for item in self.children:
                    item.disabled = True
                await self.message.edit(view=self)

        return callback

    async def on_timeout(self):
        if self.message:
            for item in self.children:
                item.disabled = True
            await self.message.edit(view=self)


class ModelCog(commands.GroupCog, name="model"):
    """Group of commands for managing and viewing Stable Diffusion models."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="select", description="Select a Stable Diffusion model.")
    async def select(self, interaction: discord.Interaction):
        """Display the model selection interface."""
        # Fetch user's currently selected model from the database
        models_db_cursor.execute("SELECT model_name FROM user_models WHERE user_id = ?", (interaction.user.id,))
        result = models_db_cursor.fetchone()
        current_model_key = result[0] if result else "default"
        current_model_name = models[current_model_key]["name"]

        # Create an embed for model selection
        embed = discord.Embed(
            title="Model Selection",
            description=f"**Currently Selected Model:** {current_model_name}\n\nClick a button to select a model.",
            color=discord.Color.blue(),
        )
        for index, (key, model) in enumerate(models.items(), start=1):
            emoji = f"{index}\u20e3"
            embed.add_field(name=f"{emoji} {model['name']}", value="", inline=False)

        # Create the view with buttons
        view = ModelSelectView(models)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
        view.message = await interaction.original_response()

    @app_commands.command(name="info", description="View details about Stable Diffusion models.")
    async def info(self, interaction: discord.Interaction):
        """Display information about available models."""
        # Fetch user's currently selected model from the database
        models_db_cursor.execute("SELECT model_name FROM user_models WHERE user_id = ?", (interaction.user.id,))
        result = models_db_cursor.fetchone()
        current_model_key = result[0] if result else "default"
        current_model_name = models[current_model_key]["name"]

        # Create embed for model information
        embed = discord.Embed(
            title="Stable Diffusion Models Information",
            description=f"**Currently Selected Model:** {current_model_name}\n\nDetails about available models:",
            color=discord.Color.green(),
        )
        for key, model in models.items():
            embed.add_field(
                name=model["name"],
                value=(f"**Checkpoint:** {model['checkpoint']}\n"
                       f"**Clip Skip:** {model['clip_skip']}\n"
                       f"**Sampler:** {model['sampler']}\n"
                       f"**Scheduler:** {model['scheduler']}\n"
                       f"**CFG Scale:** {model['cfg_scale']}\n"
                       f"**Steps:** {model['steps']}\n"
                       f"**Width:** {model['width']}\n"
                       f"**Height:** {model['height']}"),
                inline=False
            )

        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    """Register the Model command group."""
    await bot.add_cog(ModelCog(bot))