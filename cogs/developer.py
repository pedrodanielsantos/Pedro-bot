import discord
from discord.ext import commands

class Developer(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_command_error(self, ctx: commands.Context, error: commands.CommandError):
        if isinstance(error, commands.CheckFailure):
            await ctx.reply("❌ You are not authorized to use this command.", delete_after=5)
        elif isinstance(error, commands.MissingRequiredArgument):
            await ctx.reply(f"❌ Missing required argument: `{error.param.name}`")
        else:
            await ctx.reply(f"❌ An error occurred: {error}")
            print(f"Error in developer command: {error}")

    async def cog_check(self, ctx: commands.Context) -> bool:
        # This method runs before any command in this cog.
        # It ensures only the bot owner can run these commands.
        return await self.bot.is_owner(ctx.author)

    @commands.command(name="reload", hidden=True)
    async def reload(self, ctx: commands.Context, cog: str):
        """
        Reloads a specific cog.
        Usage: ç!reload lobby
        """
        # Handle shorthand input (e.g., "lobby" -> "cogs.lobby")
        if not cog.startswith("cogs."):
            extension = f"cogs.{cog}"
        else:
            extension = cog

        try:
            await self.bot.reload_extension(extension)
            await ctx.reply(f"✅ Reloaded `{extension}`")
            print(f"Reloaded extension: {extension}")
        except Exception as e:
            await ctx.reply(f"❌ Failed to reload `{extension}`:\n```py\n{e}\n```")
            print(f"Failed to reload extension {extension}: {e}")

    @commands.command(name="load", hidden=True)
    async def load(self, ctx: commands.Context, cog: str):
        """
        Loads a specific cog.
        Usage: ç!load lobby
        """
        if not cog.startswith("cogs."):
            extension = f"cogs.{cog}"
        else:
            extension = cog

        try:
            await self.bot.load_extension(extension)
            await ctx.reply(f"✅ Loaded `{extension}`")
            print(f"Loaded extension: {extension}")
        except Exception as e:
            await ctx.reply(f"❌ Failed to load `{extension}`:\n```py\n{e}\n```")
            print(f"Failed to load extension {extension}: {e}")

    @commands.command(name="unload", hidden=True)
    async def unload(self, ctx: commands.Context, cog: str):
        """
        Unloads a specific cog.
        Usage: ç!unload lobby
        """
        if not cog.startswith("cogs."):
            extension = f"cogs.{cog}"
        else:
            extension = cog

        try:
            await self.bot.unload_extension(extension)
            await ctx.reply(f"✅ Unloaded `{extension}`")
            print(f"Unloaded extension: {extension}")
        except Exception as e:
            await ctx.reply(f"❌ Failed to unload `{extension}`:\n```py\n{e}\n```")
            print(f"Failed to unload extension {extension}: {e}")

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

        msg = await ctx.reply(f"Syncing command tree {target_desc}...")
        try:
            synced = await self.bot.tree.sync(guild=target)
            await msg.edit(content=f"✅ Synced {len(synced)} commands {target_desc}.")
        except Exception as e:
            await msg.edit(content=f"❌ Sync failed: {e}")
            print(f"Sync failed: {e}")

    @commands.command(name="devhelp", hidden=True)
    async def devhelp(self, ctx: commands.Context):
        """
        Shows available developer commands.
        Usage: ç!devhelp
        """
        embed = discord.Embed(title="🛠️ Developer Tools", color=discord.Color.dark_grey())
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
            print(f"Deleted message {message_id}")
        except discord.NotFound:
            await ctx.reply(f"❌ Message `{message_id}` not found.", delete_after=5)
        except discord.Forbidden:
            await ctx.reply("❌ I cannot delete that message (I can only delete my own messages in DMs).", delete_after=5)
        except Exception as e:
            await ctx.reply(f"❌ Error: {e}", delete_after=5)

async def setup(bot: commands.Bot):
    await bot.add_cog(Developer(bot))
