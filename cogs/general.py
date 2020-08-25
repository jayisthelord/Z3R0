import asyncio
import datetime
import discord
import json
import logging

from discord.ext import commands

class General(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.logger = logging.getLogger('discord')

    @commands.command(usage="(language) (code)",
                      brief="Compile code")
    async def compile(self, ctx, language=None, *, code=None):
        """Compile code from a variety of programming languages, powered by <https://wandbox.org/>\n\
           **Example**
           ``>compile python print('Hello World')``"""
        
        compilers = {
                "bash": "bash",
                "c":"gcc-head-c",
                "c#":"dotnetcore-head",
                "coffeescript": "coffescript-head",
                "cpp": "gcc-head",
                "elixir": "elixir-head",
                "go": "go-head",	
                "java": "openjdk-head",
                "javascript":"nodejs-head",
                "lua": "lua-5.3.4",
                "perl": "perl-head",
                "php": "php-head",
                "python":"cpython-3.8.0",
                "ruby": "ruby-head",
                "rust": "rust-head",
                "sql": "sqlite-head",
                "swift": "swift-5.0.1",
                "typescript":"typescript-3.5.1",
                "vim-script": "vim-head"
                }
        if not language:
            await ctx.send(f"```json\n{json.dumps(compilers, indent=4)}```")
        if not code:
            await ctx.send("No code found")
            return
        try:
            compiler = compilers[language.lower()]
        except KeyError:
            await ctx.send("Language not found")
            return
        body = {
                "compiler": compiler,
                "code": code,
                "save": True
                }
        head = {
                "Content-Type":"application/json"
                }
        async with ctx.typing():
            async with self.bot.session.post("https://wandbox.org/api/compile.json", headers=head, data=json.dumps(body)) as r:
                #r = requests.post("https://wandbox.org/api/compile.json", headers=head, data=json.dumps(body))
                try:
                    response = json.loads(await r.text())
                    #await ctx.send(f"```json\n{json.dumps(response, indent=4)}```")
                    self.logger.info(f"json\n{json.dumps(response, indent=4)}")
                except json.decoder.JSONDecodeError:
                    self.logger.error(f"json\n{r.text}")
                    await ctx.send(f"```json\n{r.text}```")
                
                try:
                    embed=discord.Embed(title="Compiled code")
                    embed.add_field(name="Output", value=f'```{response["program_message"]}```', inline=False)
                    embed.add_field(name="Exit code", value=response["status"], inline=True)
                    embed.add_field(name="Link", value=f"[Permalink]({response['url']})", inline=True)
                    await ctx.send(embed=embed)
                except KeyError:
                    self.logger.error(f"json\n{json.dumps(response, indent=4)}")
                    await ctx.send(f"```json\n{json.dumps(response, indent=4)}```")

    @commands.command()
    async def source(self, ctx):
        """Show link to ziBot's source code."""
        git_link = "https://github.com/null2264/ziBot"
        await ctx.send(f"ziBot's source code: \n {git_link}")

    @commands.command(aliases=['si'])
    async def serverinfo(self, ctx):
        """Show server information."""
        embed = discord.Embed(
                title=f"About {ctx.guild.name}",
                colour=discord.Colour(0xFFFFF0)
                )
        roles = [x.mention for x in ctx.guild.roles]
        ignored_role = ["<@&645074407244562444>", "<@&745481731133669476>"]
        for i in ignored_role:
            try:
                roles.remove(i)
            except ValueError:
                print("Role not found, skipped")
        width = 3
        
        boosters = [x.mention for x in ctx.guild.premium_subscribers]

        embed.add_field(name="Owner",value=f"{ctx.guild.owner.mention}",inline=False)
        embed.add_field(name="Created on",value=f"{ctx.guild.created_at.date()}")
        embed.add_field(name="Region",value=f"``{ctx.guild.region}``")
        embed.set_thumbnail(url=ctx.guild.icon_url)
        embed.add_field(name="Verification Level",
                        value=f"{ctx.guild.verification_level}".title())
        embed.add_field(name="Channels",value="<:categories:747750884577902653>"
                                              + f" {len(ctx.guild.categories)}\n"
                                              + "<:text_channel:747744994101690408>"
                                              + f" {len(ctx.guild.text_channels)}\n"
                                              + "<:voice_channel:747745006697185333>"
                                              + f" {len(ctx.guild.voice_channels)}")
        embed.add_field(name="Members",value=f"{ctx.guild.member_count}")
        if len(boosters) < 5:
            embed.add_field(name=f"Boosters ({len(boosters)})",
                            value=",\n".join(", ".join(boosters[i:i+width]) 
                                    for i in range(0, len(boosters), width)) 
                                    if boosters 
                                    else 'No booster.')
        else:
            embed.add_field(name=f"Boosters ({len(boosters)})",
                            value=len(boosters))
        embed.add_field(name=f"Roles ({len(roles)})",
                        value=", ".join(roles))
        embed.set_footer(text=f"ID: {ctx.guild.id}")
        await ctx.send(embed=embed)

    @commands.command()
    async def info(self, ctx):
        embed = discord.Embed(
                title="About ziBot",
                description="ziBot is an open source bot, \n\
                             a fork of mcbeDiscordBot",
                colour=discord.Colour(0xFFFFF0)
                )
        embed.set_thumbnail(url=self.bot.user.avatar_url)
        embed.add_field(name="Author", value="ZiRO2264#4572")
        embed.add_field(name="Links", value="[Github](https://github.com/null2264/ziBot)")
        await ctx.send(embed=embed)

def setup(bot):
    bot.add_cog(General(bot))

