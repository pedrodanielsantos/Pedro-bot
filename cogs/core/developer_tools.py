import asyncio
import logging

import aiohttp
import discord
from discord.ext import commands
import os
from db.database import get_guild_embed_color, reset_case_counter
from utils.cogs import reload_shared_modules
from utils.embeds import error_embed, success_embed

logger = logging.getLogger("dev")
WEB_DASHBOARD = "http://127.0.0.1:8000"

class DeveloperTools(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_command_error(self, ctx: commands.Context, error: commands.CommandError):
        if isinstance(error, commands.CheckFailure):
            embed = error_embed("You are not authorized to use this command.")
            await self._reply_or_dm(ctx, embed, delete_after=5)
        elif isinstance(error, commands.MissingRequiredArgument):
            embed = error_embed(f"Missing required argument: `{error.param.name}`")
            await self._reply_or_dm(ctx, embed)
        else:
            embed = error_embed(f"An error occurred: {error}")
            await self._reply_or_dm(ctx, embed)
            logger.error(f"Error in command: {error}")

    async def _reply_or_dm(self, ctx: commands.Context, embed: discord.Embed, **reply_kwargs):
        """Replies in the invoking channel, falling back to a DM if the bot can't
        send there. cog_check guarantees ctx.author is always the bot owner.
        """
        try:
            await ctx.reply(embed=embed, **reply_kwargs)
        except discord.Forbidden:
            dm_embed = discord.Embed(
                description=f"Couldn't reply in {ctx.channel.mention} (missing permissions). {embed.description}",
                color=embed.color,
            )
            try:
                await ctx.author.send(embed=dm_embed)
            except discord.Forbidden:
                logger.error(f"Could not DM the owner about a command error: {embed.description}")

    async def cog_check(self, ctx: commands.Context) -> bool:
        # Runs before every command in this cog and restricts all of them to the bot owner.
        return await self.bot.is_owner(ctx.author)

    def find_extension(self, query: str) -> str | None:
        """
        Resolves a partial cog name (e.g., 'image') to its full module path (e.g., 'cogs.commands.image').
        Searches both loaded extensions and the file system.
        """
        # Exact match against a loaded extension's full module path.
        if query in self.bot.extensions:
            return query

        # Suffix match against loaded extensions, e.g. "image" resolves to "cogs.commands.image".
        matches = [ext for ext in self.bot.extensions if ext.endswith(f".{query}")]
        if len(matches) == 1:
            return matches[0]

        # Not loaded yet (needed for 'load'), so fall back to scanning the cogs folder on disk.
        # This file lives in cogs/core/, so cogs_dir and bot_root are two levels up from here.
        current_dir = os.path.dirname(os.path.abspath(__file__))
        cogs_dir = os.path.dirname(current_dir) # y:\cogs
        bot_root = os.path.dirname(cogs_dir)    # y:\

        for root, _, files in os.walk(cogs_dir):
            for file in files:
                if file.endswith(".py") and not file.startswith("__"):
                    full_path = os.path.join(root, file)
                    rel_path = os.path.relpath(full_path, bot_root)
                    module_path = rel_path.replace(os.sep, ".")[:-3]

                    # Exact filename match, e.g. "image" matches "image.py".
                    if file == f"{query}.py":
                        return module_path
                    # Module path suffix match, e.g. "commands.image" matches "cogs.commands.image".
                    if module_path.endswith(query):
                        return module_path
        return None

    @commands.command(name="reload", hidden=True)
    async def reload(self, ctx: commands.Context, cog: str = None):
        """
        Reloads a specific cog, or all loaded cogs if none is given
        Usage: ç!reload [cog]
        """
        if cog is None:
            failed = []
            reload_shared_modules()
            for extension in list(self.bot.extensions):
                try:
                    await self.bot.reload_extension(extension)
                    logger.info(f"Reloaded: {extension}")
                except Exception as e:
                    failed.append((extension, e))
                    logger.error(f"Failed to reload extension {extension}: {e}")

            if failed:
                details = "\n".join(f"`{ext}`: {e}" for ext, e in failed)
                embed = error_embed(f"Reloaded all extensions, but {len(failed)} failed:\n```py\n{details}\n```")
                await ctx.reply(embed=embed)
            else:
                embed = success_embed(f"Reloaded all `{len(self.bot.extensions)}` extensions")
                await ctx.reply(embed=embed)
            return

        extension = self.find_extension(cog)

        if not extension:
            embed = error_embed(f"Could not find extension matching `{cog}`.")
            await ctx.reply(embed=embed)
            return

        try:
            reload_shared_modules()
            await self.bot.reload_extension(extension)
            embed = success_embed(f"Reloaded `{extension}`")
            await ctx.reply(embed=embed)
            logger.info(f"Reloaded: {extension}")
        except Exception as e:
            embed = error_embed(f"Failed to reload `{extension}`:\n```py\n{e}\n```")
            await ctx.reply(embed=embed)
            logger.error(f"Failed to reload extension {extension}: {e}")

    @commands.command(name="load", hidden=True)
    async def load(self, ctx: commands.Context, cog: str):
        """
        Loads a specific cog
        Usage: ç!load <cog>
        """
        extension = self.find_extension(cog)

        if not extension:
            embed = error_embed(f"Could not find extension matching `{cog}`.")
            await ctx.reply(embed=embed)
            return

        try:
            reload_shared_modules()
            await self.bot.load_extension(extension)
            embed = success_embed(f"Loaded `{extension}`")
            await ctx.reply(embed=embed)
            logger.info(f"Loaded: {extension}")
        except Exception as e:
            embed = error_embed(f"Failed to load `{extension}`:\n```py\n{e}\n```")
            await ctx.reply(embed=embed)
            logger.error(f"Failed to load extension {extension}: {e}")

    @commands.command(name="unload", hidden=True)
    async def unload(self, ctx: commands.Context, cog: str):
        """
        Unloads a specific cog
        Usage: ç!unload <cog>
        """
        extension = self.find_extension(cog)

        if not extension:
            embed = error_embed(f"Could not find extension matching `{cog}`.")
            await ctx.reply(embed=embed)
            return

        try:
            await self.bot.unload_extension(extension)
            embed = success_embed(f"Unloaded `{extension}`")
            await ctx.reply(embed=embed)
            logger.info(f"Unloaded: {extension}")
        except Exception as e:
            embed = error_embed(f"Failed to unload `{extension}`:\n```py\n{e}\n```")
            await ctx.reply(embed=embed)
            logger.error(f"Failed to unload extension {extension}: {e}")

    @commands.command(name="sync", hidden=True)
    async def sync(self, ctx: commands.Context, spec: str = None):
        """
        Syncs the slash command tree
        Usage: ç!sync [. | ^]
        ç!sync       globally
        ç!sync .     this guild
        ç!sync ^     clear guild
        """
        if spec == "." and ctx.guild:
            self.bot.tree.copy_global_to(guild=ctx.guild)
            target = ctx.guild
            target_desc = "to current guild"
        elif spec == "^" and ctx.guild:
            self.bot.tree.clear_commands(guild=ctx.guild)
            target = ctx.guild
            target_desc = "by clearing guild commands"
        else:
            target = None
            target_desc = "globally"

        try:
            synced = await self.bot.tree.sync(guild=target)
            embed = success_embed(f"Synced {len(synced)} commands {target_desc}.")
            await ctx.reply(embed=embed)
            logger.info(f"Synced {len(synced)} commands {target_desc}.")
        except Exception as e:
            embed = error_embed(f"Sync failed: {e}")
            await ctx.reply(embed=embed)
            logger.error(f"Sync failed: {e}")

    @commands.command(name="devtools", hidden=True)
    async def devtools(self, ctx: commands.Context):
        """
        Shows available developer commands
        Usage: ç!devtools
        """
        guild_id = ctx.guild.id if ctx.guild else None
        color = await get_guild_embed_color(guild_id)

        lines = [
            "# Developer Tools",
            "`<required>` arguments must be given. `[optional]` ones can be left out.",
            "",
        ]
        for cmd in self.get_commands():
            doc = (cmd.help or "No description provided.").strip()
            if "\nUsage:" in doc:
                summary, usage = doc.split("\nUsage:", 1)
                usage = "Usage:" + usage
            else:
                summary, usage = doc, ""
            summary = " ".join(summary.split())

            lines.append(f"**ç!{cmd.name}**: *{summary}*")
            if usage:
                lines.append(f"```{usage}```")

        embed = discord.Embed(description="\n".join(lines).rstrip(), color=color)
        await ctx.reply(embed=embed)

    @commands.command(name="deletemessage", hidden=True)
    async def deletemessage(self, ctx: commands.Context, message_id: int):
        """
        Deletes a message by ID, only works on the bot's own messages
        Usage: ç!deletemessage <message_id>
        """
        try:
            msg = await ctx.channel.fetch_message(message_id)
            await msg.delete()
            logger.info(f"Deleted message {message_id}.")
        except discord.NotFound:
            embed = error_embed(f"Message `{message_id}` not found.")
            await ctx.reply(embed=embed, delete_after=5)
        except discord.Forbidden:
            embed = error_embed("I don't have permission to delete that message.")
            await ctx.reply(embed=embed, delete_after=5)
        except Exception as e:
            embed = error_embed(f"Error: {e}")
            await ctx.reply(embed=embed, delete_after=5)

    @commands.command(name="resetcases", hidden=True)
    async def resetcases(self, ctx: commands.Context, guild_id: int = None):
        """
        Wipes moderation case history and resets the case counter for a guild, for testing purposes
        Usage: ç!resetcases [guild_id]
        """
        target_guild_id = guild_id or (ctx.guild.id if ctx.guild else None)
        if target_guild_id is None:
            embed = error_embed("No guild specified and this wasn't run in a guild.")
            await ctx.reply(embed=embed)
            return

        await reset_case_counter(target_guild_id)
        embed = success_embed(f"Wiped case history and reset the case counter for guild `{target_guild_id}`.")
        await ctx.reply(embed=embed)
        logger.info(f"Reset case counter for guild {target_guild_id}.")

    @commands.command(name="reloadweb", hidden=True)
    async def reloadweb(self, ctx: commands.Context):
        """
        Reloads the web dashboard
        Usage: ç!reloadweb
        """
        # The dashboard runs in run.py's process, so trigger its reload endpoint instead of reimplementing it here.
        try:
            timeout = aiohttp.ClientTimeout(total=5)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(f"{WEB_DASHBOARD}/web/reload") as resp:
                    resp.raise_for_status()
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            embed = error_embed(f"Failed to reach the web dashboard: {e}")
            await ctx.reply(embed=embed)
            logger.error(f"Failed to reload web dashboard: {e}")
            return

        logger.info("Triggered web dashboard reload.")
        embed = success_embed("Web dashboard reload triggered.")
        await ctx.reply(embed=embed)

async def setup(bot: commands.Bot):
    await bot.add_cog(DeveloperTools(bot))
