import asyncio
import importlib
import logging

import discord
from discord.ext import commands
import os
from config.constants import SUCCESS_COLOR, ERROR_COLOR
import web as web_module

logger = logging.getLogger("dev")

class DeveloperTools(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_command_error(self, ctx: commands.Context, error: commands.CommandError):
        if isinstance(error, commands.CheckFailure):
            embed = discord.Embed(description="You are not authorized to use this command.", color=ERROR_COLOR)
            await ctx.reply(embed=embed, delete_after=5)
        elif isinstance(error, commands.MissingRequiredArgument):
            embed = discord.Embed(description=f"Missing required argument: `{error.param.name}`", color=ERROR_COLOR)
            await ctx.reply(embed=embed)
        else:
            embed = discord.Embed(description=f"An error occurred: {error}", color=ERROR_COLOR)
            await ctx.reply(embed=embed)
            logger.error(f"Error in command: {error}")

    async def cog_check(self, ctx: commands.Context) -> bool:
        # This method runs before any command in this cog.
        # It ensures only the bot owner can run these commands.
        return await self.bot.is_owner(ctx.author)

    def find_extension(self, query: str) -> str | None:
        """
        Resolves a partial cog name (e.g., 'image') to its full module path (e.g., 'cogs.commands.image').
        Searches both loaded extensions and the file system.
        """
        # 1. Check if it's a direct match in loaded extensions
        if query in self.bot.extensions:
            return query

        # 2. Check if it's a suffix match in loaded extensions (e.g. "image" -> "cogs.commands.image")
        matches = [ext for ext in self.bot.extensions if ext.endswith(f".{query}")]
        if len(matches) == 1:
            return matches[0]

        # 3. Search the filesystem (useful for 'load' command where extension isn't loaded yet)
        # Current file is in cogs/core/, so we go up two levels to find the 'cogs' root
        current_dir = os.path.dirname(os.path.abspath(__file__))
        cogs_dir = os.path.dirname(current_dir) # y:\cogs
        bot_root = os.path.dirname(cogs_dir)    # y:\

        for root, _, files in os.walk(cogs_dir):
            for file in files:
                if file.endswith(".py") and not file.startswith("__"):
                    full_path = os.path.join(root, file)
                    rel_path = os.path.relpath(full_path, bot_root)
                    module_path = rel_path.replace(os.sep, ".")[:-3]

                    # Check for exact filename match (e.g. "image" matches "image.py")
                    if file == f"{query}.py":
                        return module_path
                    # Check for module path suffix match (e.g. "commands.image" matches "cogs.commands.image")
                    if module_path.endswith(query):
                        return module_path
        return None

    @commands.command(name="reload", hidden=True)
    async def reload(self, ctx: commands.Context, cog: str = None):
        """
        Reloads a specific cog, or all loaded cogs if none is given.
        Usage: ç!reload lobby
               ç!reload
        """
        if cog is None:
            failed = []
            for extension in list(self.bot.extensions):
                try:
                    await self.bot.reload_extension(extension)
                    logger.info(f"Reloaded extension: {extension}")
                except Exception as e:
                    failed.append((extension, e))
                    logger.error(f"Failed to reload extension {extension}: {e}")

            if failed:
                details = "\n".join(f"`{ext}`: {e}" for ext, e in failed)
                embed = discord.Embed(description=f"Reloaded all extensions, but {len(failed)} failed:\n```py\n{details}\n```", color=ERROR_COLOR)
                await ctx.reply(embed=embed)
            else:
                embed = discord.Embed(description=f"Reloaded all `{len(self.bot.extensions)}` extensions", color=SUCCESS_COLOR)
                await ctx.reply(embed=embed)
            return

        extension = self.find_extension(cog)

        if not extension:
            embed = discord.Embed(description=f"Could not find extension matching `{cog}`.", color=ERROR_COLOR)
            await ctx.reply(embed=embed)
            return

        try:
            await self.bot.reload_extension(extension)
            embed = discord.Embed(description=f"Reloaded `{extension}`", color=SUCCESS_COLOR)
            await ctx.reply(embed=embed)
            logger.info(f"Reloaded extension: {extension}")
        except Exception as e:
            embed = discord.Embed(description=f"Failed to reload `{extension}`:\n```py\n{e}\n```", color=ERROR_COLOR)
            await ctx.reply(embed=embed)
            logger.error(f"Failed to reload extension {extension}: {e}")

    @commands.command(name="load", hidden=True)
    async def load(self, ctx: commands.Context, cog: str):
        """
        Loads a specific cog.
        Usage: ç!load lobby
        """
        extension = self.find_extension(cog)

        if not extension:
            embed = discord.Embed(description=f"Could not find extension matching `{cog}`.", color=ERROR_COLOR)
            await ctx.reply(embed=embed)
            return

        try:
            await self.bot.load_extension(extension)
            embed = discord.Embed(description=f"Loaded `{extension}`", color=SUCCESS_COLOR)
            await ctx.reply(embed=embed)
            logger.info(f"Loaded extension: {extension}")
        except Exception as e:
            embed = discord.Embed(description=f"Failed to load `{extension}`:\n```py\n{e}\n```", color=ERROR_COLOR)
            await ctx.reply(embed=embed)
            logger.error(f"Failed to load extension {extension}: {e}")

    @commands.command(name="unload", hidden=True)
    async def unload(self, ctx: commands.Context, cog: str):
        """
        Unloads a specific cog.
        Usage: ç!unload lobby
        """
        extension = self.find_extension(cog)

        if not extension:
            embed = discord.Embed(description=f"Could not find extension matching `{cog}`.", color=ERROR_COLOR)
            await ctx.reply(embed=embed)
            return

        try:
            await self.bot.unload_extension(extension)
            embed = discord.Embed(description=f"Unloaded `{extension}`", color=SUCCESS_COLOR)
            await ctx.reply(embed=embed)
            logger.info(f"Unloaded extension: {extension}")
        except Exception as e:
            embed = discord.Embed(description=f"Failed to unload `{extension}`:\n```py\n{e}\n```", color=ERROR_COLOR)
            await ctx.reply(embed=embed)
            logger.error(f"Failed to unload extension {extension}: {e}")

    @commands.command(name="sync", hidden=True)
    async def sync(self, ctx: commands.Context, spec: str = None):
        """
        Syncs the slash command tree.
        Usage:
        ç!sync       -> Global sync
        ç!sync .     -> Sync to current guild (instant)
        ç!sync ^     -> Clear commands from current guild
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
            embed = discord.Embed(description=f"Synced {len(synced)} commands {target_desc}.", color=SUCCESS_COLOR)
            await ctx.reply(embed=embed)
            logger.info(f"Synced {len(synced)} commands {target_desc}.")
        except Exception as e:
            embed = discord.Embed(description=f"Sync failed: {e}", color=ERROR_COLOR)
            await ctx.reply(embed=embed)
            logger.error(f"Sync failed: {e}")

    @commands.command(name="devhelp", hidden=True)
    async def devhelp(self, ctx: commands.Context):
        """
        Shows available developer commands.
        Usage: ç!devhelp
        """
        embed = discord.Embed(title="Developer Tools", color=discord.Color(0x33cbbe))
        for cmd in self.get_commands():
            desc = cmd.help or "No description provided."
            embed.add_field(name=f"ç!{cmd.name}", value=f"```{desc}```", inline=False)
        await ctx.reply(embed=embed)

    @commands.command(name="deletemessage", hidden=True)
    async def deletemessage(self, ctx: commands.Context, message_id: int):
        """
        Deletes a specific message by ID.
        Usage: ç!deletemessage 123456789
        """
        try:
            msg = await ctx.channel.fetch_message(message_id)
            await msg.delete()
            logger.info(f"Deleted message {message_id}.")
        except discord.NotFound:
            embed = discord.Embed(description=f"Message `{message_id}` not found.", color=ERROR_COLOR)
            await ctx.reply(embed=embed, delete_after=5)
        except discord.Forbidden:
            embed = discord.Embed(description="I don't have permission to delete that message.", color=ERROR_COLOR)
            await ctx.reply(embed=embed, delete_after=5)
        except Exception as e:
            embed = discord.Embed(description=f"Error: {e}", color=ERROR_COLOR)
            await ctx.reply(embed=embed, delete_after=5)

    @commands.command(name="reloadweb", hidden=True)
    async def reloadweb(self, ctx: commands.Context):
        """
        Reloads the web dashboard without restarting the bot.
        Usage: ç!reloadweb
        """
        server = getattr(self.bot, '_web_server', None)
        if server:
            server.should_exit = True
            for _ in range(30):
                if getattr(self.bot, '_web_server', None) is None:
                    break
                await asyncio.sleep(0.1)

        importlib.reload(web_module)
        asyncio.create_task(web_module.start(self.bot))
        logger.info("Reloaded web dashboard.")

        embed = discord.Embed(description="Web dashboard reloaded.", color=SUCCESS_COLOR)
        await ctx.reply(embed=embed)

async def setup(bot: commands.Bot):
    await bot.add_cog(DeveloperTools(bot))
