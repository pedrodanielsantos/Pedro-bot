import discord
from discord.ext import commands
from discord import app_commands
import aiohttp
import base64
import io
import json
import asyncio
from typing import Optional
from imagine_models import models
import sqlite3
import gc

# Define an asyncio queue for image generation jobs
image_queue = asyncio.Queue()

# Connect to the SQLite database
models_db_conn = sqlite3.connect("imagine_models.db")
models_db_cursor = models_db_conn.cursor()

class ImageControlView(discord.ui.View):
    def __init__(self, user_id: int, interaction: discord.Interaction, payload: dict):
        super().__init__(timeout=None)
        self.user_id = user_id
        self.interaction = interaction
        self.payload = payload

    @discord.ui.button(emoji="🔄", style=discord.ButtonStyle.primary, custom_id="regenerate")
    async def regenerate(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("You cannot use this button.", ephemeral=True)
            return

        # Check global queue limit
        if image_queue.qsize() >= 10:
            await interaction.response.send_message(
                f"Sorry {interaction.user.mention}, the queue is currently full. Please try again later.", ephemeral=True
            )
            return

        # Check per-user queue limit
        user_jobs = sum(1 for job in image_queue._queue if job[0].user.id == interaction.user.id)
        if user_jobs >= 2:
            await interaction.response.send_message(
                f"Sorry {interaction.user.mention}, you already have 2 jobs in the queue. Please wait for one to complete.",
                ephemeral=True
            )
            return

        # Re-enqueue the same payload with a random seed
        new_payload = self.payload.copy()
        new_payload["seed"] = -1  # Reset to random seed
        new_payload.pop("subseed", None)  # Remove subseed if present
        new_payload.pop("subseed_strength", None)  # Remove subseed strength if present
        user_mention = interaction.user.mention

        # Calculate queue position
        position = image_queue.qsize() + 1
        await image_queue.put((interaction, new_payload, user_mention))
        await interaction.response.send_message(
            f"**{self.payload['prompt']}** (re-roll) by {user_mention} added to queue (Position #{position})", ephemeral=False
        )

    @discord.ui.button(emoji="🔀", style=discord.ButtonStyle.primary, custom_id="variations")
    async def variations(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("You cannot use this button.", ephemeral=True)
            return

        # Check global queue limit
        if image_queue.qsize() >= 10:
            await interaction.response.send_message(
                f"Sorry {interaction.user.mention}, the queue is currently full. Please try again later.", ephemeral=True
            )
            return

        # Check per-user queue limit
        user_jobs = sum(1 for job in image_queue._queue if job[0].user.id == interaction.user.id)
        if user_jobs >= 2:
            await interaction.response.send_message(
                f"Sorry {interaction.user.mention}, you already have 2 jobs in the queue. Please wait for one to complete.",
                ephemeral=True
            )
            return

        # Generate a random subseed for variation
        new_payload = self.payload.copy()
        new_payload["subseed"] = -1
        new_payload["subseed_strength"] = 0.3  # Variation strength
        user_mention = interaction.user.mention

        # Calculate queue position
        position = image_queue.qsize() + 1
        await image_queue.put((interaction, new_payload, user_mention))
        await interaction.response.send_message(
            f"**{self.payload['prompt']}** (variation) by {user_mention} added to queue (Position #{position})", ephemeral=False
        )

    @discord.ui.button(emoji="🗑️", style=discord.ButtonStyle.danger, custom_id="delete")
    async def delete(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("You cannot use this button.", ephemeral=True)
            return

        # Delete the message
        try:
            await interaction.message.delete()
            await interaction.response.send_message("Image successfully deleted.", ephemeral=True)
        except discord.HTTPException:
            await interaction.response.send_message("Failed to delete the image.", ephemeral=True)

class ImagineCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.task = None  # Background task
        self.session = None  # Aiohttp ClientSession

    async def cog_load(self):
        self.session = aiohttp.ClientSession()
        self.task = asyncio.create_task(self.process_image_queue())

    async def cog_unload(self):
        print("cog_unload triggered (imagine)")
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass

        if self.session and not self.session.closed:
            await self.session.close()

        gc.collect()

    async def process_image_queue(self):
        while True:
            interaction, payload, user_mention = await image_queue.get()

            try:
                async with self.session.post("http://127.0.0.1:7860/sdapi/v1/txt2img", json=payload) as response:
                    if response.status != 200:
                        await interaction.channel.send(
                            f"An error occurred while generating the image for {user_mention}: {response.status}"
                        )
                        image_queue.task_done()
                        continue

                    result = await response.json()

                    # Decode Base64 image
                    image_data = result["images"][0]
                    image_bytes = discord.File(io.BytesIO(base64.b64decode(image_data)), filename="generated_image.png")

                    # Extract seed and model name
                    seed_used = json.loads(result.get("info", "{}")).get("seed", "N/A")
                    checkpoint_key = payload["override_settings"]["sd_model_checkpoint"]
                    model_name = next(
                        (model["name"] for model in models.values() if model["checkpoint"] == checkpoint_key),
                        "Unknown Model"
                    )

                    # Update the payload with the actual seed
                    payload["seed"] = seed_used

                    # Check if the image is a variation
                    is_variation = "subseed" in payload

                    # Create embed for result
                    embed = discord.Embed(
                        title="",
                        description="",
                    )
                    embed.add_field(name="Prompt", value=f"```{payload['prompt']}```", inline=False)
                    if payload["negative_prompt"]:
                        embed.add_field(name="Negative Prompt", value=f"```{payload['negative_prompt']}```", inline=False)
                    embed.add_field(name="Model", value=f"{model_name}", inline=True)
                    embed.add_field(name="Seed", value=f"{seed_used}", inline=True)

                    # Add footer if it's a variation
                    if is_variation:
                        embed.set_footer(text="Note: seeds won't imagine accurately from variations ⚠︎")

                    # Add the control buttons
                    view = ImageControlView(user_id=interaction.user.id, interaction=interaction, payload=payload)

                    await interaction.channel.send(content=user_mention, file=image_bytes, embed=embed, view=view)

            except aiohttp.ClientError as e:
                await interaction.channel.send(f"An error occurred while generating the image for {user_mention}: {e}")
            except KeyError:
                await interaction.channel.send(f"Failed to retrieve the image for {user_mention}.")
            finally:
                image_queue.task_done()

    @app_commands.command(name="imagine", description="Generate an image using Stable Diffusion.")
    @app_commands.describe(
        prompt="A description of what you want to generate.",
        negative_prompt="Optional: Things you want to exclude from the image.",
        steps="Optional: Number of inference steps (max: 50).",
        cfg_scale="Optional: Classifier-Free Guidance scale.",
        width="Optional: Image width (max: 2048).",
        height="Optional: Image height (max: 2048).",
        seed="Optional: Seed for generation (default: -1 for random)."
    )
    async def imagine(
        self,
        interaction: discord.Interaction,
        prompt: str,
        negative_prompt: Optional[str] = None,
        steps: Optional[int] = None,
        cfg_scale: Optional[float] = None,
        width: Optional[int] = None,
        height: Optional[int] = None,
        seed: Optional[int] = None,
    ):
        await interaction.response.defer(ephemeral=False)

        # Restrict use to NSFW channels only
        if not (isinstance(interaction.channel, discord.TextChannel) and interaction.channel.is_nsfw()):
            embed = discord.Embed(
                title="⚠️ NSFW Restriction",
                description="This bot can generate NSFW content. For safety reasons, the `/imagine` command can only be used in channels marked as NSFW.",
                color=discord.Color.orange()
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        # Global queue limit
        if image_queue.qsize() >= 10:
            await interaction.followup.send(
                f"Sorry {interaction.user.mention}, the queue is currently full. Please try again later."
            )
            return

        # Per-user queue limit
        user_jobs = sum(1 for job in image_queue._queue if job[0].user.id == interaction.user.id)
        if user_jobs >= 2:
            await interaction.followup.send(
                f"Sorry {interaction.user.mention}, you already have 2 jobs in the queue. Please wait for one to complete."
            )
            return

        # Fetch user's selected model from the database
        models_db_cursor.execute("SELECT model_name FROM user_models WHERE user_id = ?", (interaction.user.id,))
        result = models_db_cursor.fetchone()
        model_name = result[0] if result else "default"
        model_config = models[model_name]

        # Dynamically fetch defaults from the model
        steps = steps if steps is not None else model_config["steps"]
        cfg_scale = cfg_scale if cfg_scale is not None else model_config["cfg_scale"]
        width = width if width is not None else model_config["width"]
        height = height if height is not None else model_config["height"]
        seed = seed if seed is not None else -1
        negative_prompt = negative_prompt if negative_prompt is not None else ""

        # Cap the steps and dimensions
        steps = min(steps, 50)
        width = min(width, 2048)
        height = min(height, 2048)

        # Prepare payload for API request
        payload = {
            "prompt": prompt,
            "negative_prompt": negative_prompt,
            "steps": steps,
            "sampler_name": model_config["sampler"],
            "scheduler": model_config["scheduler"],
            "cfg_scale": cfg_scale,
            "seed": seed,
            "width": width,
            "height": height,
            "batch_size": 1,
            "n_iter": 1,
            "override_settings": {
                "sd_model_checkpoint": model_config["checkpoint"],
                "CLIP_stop_at_last_layers": model_config["clip_skip"]
            }
        }

        # Enqueue the request
        user_mention = interaction.user.mention
        position = image_queue.qsize() + 1
        await image_queue.put((interaction, payload, user_mention))

        # Notify user
        await interaction.followup.send(f"**{prompt}** by {user_mention} added to queue (Position #{position})")


async def setup(bot: commands.Bot):
    await bot.add_cog(ImagineCog(bot))