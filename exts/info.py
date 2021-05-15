import discord
import time


from .utils.infoQuote import *
from discord.ext import commands


class Info(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(aliases=["bi", "about"])
    async def botinfo(self, ctx):
        """Information about me."""
        e = discord.Embed(
            title="About me",
            timestamp=ctx.message.created_at,
            colour=discord.Colour(0xFFFFF0),
        )
        e.add_field(name="Version", value="3.0.O `overhaul`")
        await ctx.send(embed=e)

    @commands.command()
    async def test(self, ctx):
        """Nothing, just a test."""
        return await ctx.send(info("Test\nTest", title="Warning") + " Hello World!")

    @commands.command(aliases=["p"])
    async def ping(self, ctx):
        """Tell the ping of the bot to the discord servers."""
        start = time.perf_counter()
        e = discord.Embed(
            title="Pong!",
            timestamp=ctx.message.created_at,
            colour=discord.Colour(0xFFFFF0),
        )
        e.add_field(name="<a:loading:776255339716673566> | Websocket", value=f"{round(self.bot.latency*1000)}ms")
        e.set_footer(
            text="Requested by {}".format(str(ctx.author))
        )
        msg = await ctx.send(embed=e)
        end = time.perf_counter()
        msg_ping = (end - start) * 1000
        e.add_field(name="<a:typing:785053882664878100> | Typing", value=f"{round(msg_ping)}ms", inline=False)
        await msg.edit(embed=e)

def setup(bot):
    bot.add_cog(Info(bot))