import asyncio
import discord
import json
import prettify_exceptions
import pytz
import sys
import traceback


from discord.ext import commands


class ErrorHandler(commands.Cog):
    """Handle errors."""

    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_command_error(self, ctx, error):
        # This prevents any commands with local handlers being handled here in on_command_error.
        if hasattr(ctx.command, "on_error"):
            return

        # This prevents any cogs with an overwritten cog_command_error being handled here.
        cog = ctx.cog
        if cog:
            if cog._get_overridden_method(cog.cog_command_error) is not None:
                return

        # Allows us to check for original exceptions raised and sent to CommandInvokeError.
        # If nothing is found. We keep the exception passed to on_command_error.
        error = getattr(error, "original", error)

        if isinstance(error, pytz.exceptions.UnknownTimeZoneError):
            ctx.command.reset_cooldown(ctx)
            return await ctx.reply(
                "That's not a valid timezone. You can look them up at https://kevinnovak.github.io/Time-Zone-Picker/"
            )

        if isinstance(error, commands.CommandNotFound):
            return

        if isinstance(error, commands.CommandOnCooldown):
            bot_msg = await ctx.send(
                f"{ctx.author.mention}, you have to wait {round(error.retry_after, 2)} seconds before using this again"
            )
            await asyncio.sleep(round(error.retry_after))
            return await bot_msg.delete()

        # Give details about the error
        _traceback = "".join(
            prettify_exceptions.DefaultFormatter().format_exception(
                type(error), error, error.__traceback__
            )
        )
        self.bot.logger.error(f"Something went wrong! error: {error}\n{_traceback}")
        # --- Without prettify
        # print(
        #     "Ignoring exception in command {}:".format(ctx.command), file=sys.stderr
        # )
        # print(_traceback, file=sys.stderr)
        # ---

        # Send embed that when user react with greenTick bot will send it to bot owner or issue channel
        dest = (
            self.bot.get_channel(self.bot.issueChannel)
            or self.bot.get_user(self.bot.master[0])
        )
        destName = dest if isinstance(dest, discord.User) else dest.guild
        # Embed things
        desc = (
            "The command was unsuccessful because of this reason:\n```{}```\n".format(error)
            + "React with <:greenTick:767209095090274325> to report the error to {}".format(destName)
        )
        e = discord.Embed(
            title="Something went wrong!",
            description=desc,
            colour=discord.Colour(0x2F3136),
        )
        e.set_footer(text="Waiting for answer...", icon_url=ctx.author.avatar_url)
        msg = await ctx.send(embed=e)
        await msg.add_reaction("<:greenTick:767209095090274325>")

        def check(reaction, user):
            # Check if user want to report the error message
            return (
                user == ctx.author
                and str(reaction.emoji) == "<:greenTick:767209095090274325>"
            )

        try:
            reaction, user = await self.bot.wait_for(
                "reaction_add", timeout=60.0, check=check
            )
        except asyncio.TimeoutError:
            e.set_footer(
                text="You were too late to answer.", icon_url=ctx.author.avatar_url
            )
            await msg.edit(embed=e)
            await msg.clear_reactions()
        else:
            e_owner = discord.Embed(
                title="Something went wrong!",
                description=f"An error occured:\n```{error}```",
                colour=discord.Colour(0x2F3136),
            )
            e_owner.add_field(name="Executor", value=ctx.author)
            e_owner.add_field(name="Message", value=ctx.message.content)
            await dest.send(embed=e_owner)
            e.set_footer(
                text="Error has been reported to {}".format(destName),
                icon_url=ctx.author.avatar_url,
            )
            await msg.edit(embed=e)
            await msg.clear_reactions()

        return


def setup(bot):
    bot.add_cog(ErrorHandler(bot))
