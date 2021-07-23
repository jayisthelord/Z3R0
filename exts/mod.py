"""
This Source Code Form is subject to the terms of the Mozilla Public
License, v. 2.0. If a copy of the MPL was not distributed with this
file, You can obtain one at http://mozilla.org/MPL/2.0/.
"""

import discord
import humanize


from core import checks
from core.converter import TimeAndArgument, BannedMember
from core.mixin import CogMixin
from discord.ext import commands
from exts.timer import Timer, TimerData
from exts.utils.format import ZEmbed, formatDateTime
from exts.utils.other import utcnow, ArgumentParser, ArgumentError
from typing import Union


class HierarchyError(Exception):
    def __init__(self, message: str = None):
        super().__init__(
            message
            or "My top role is lower than the target's top role in the hierarchy!"
        )


class Moderation(commands.Cog, CogMixin):
    """Moderation commands."""

    icon = "🛠️"

    async def cog_check(self, ctx):
        if not ctx.guild:
            return False
        return await checks.isMod(ctx)

    async def checkHierarchy(self, ctx, user, action: str = None):
        """Check hierarchy stuff"""
        errMsg = None

        if user.id == ctx.bot.user.id:
            errMsg = "Nice try."
        elif user == ctx.guild.owner:
            errMsg = "You can't {} guild owner!".format(action or "do this action to")
        else:
            # compare author and bot's top role vs target's top role
            try:
                if ctx.me.top_role <= user.top_role:
                    errMsg = (
                        "{}'s top role is higher than mine in the hierarchy!".format(
                            user
                        )
                    )
            except:
                # probably instance of discord.User
                pass

            try:
                if (
                    ctx.author != ctx.guild.owner  # guild owner doesn't need this check
                    and ctx.author.top_role <= user.top_role
                ):
                    errMsg = (
                        "{}'s top role is higher than yours in the hierarchy!".format(
                            user
                        )
                    )
            except:
                # probably instance of discord.User
                pass

        # errMsg will always None unless check fails
        if errMsg is not None:
            raise HierarchyError(errMsg)

        return True

    async def doModeration(self, ctx, user, time: TimerData, action: str, **kwargs):
        """Ban function, self-explanatory"""
        actions = {
            "ban": self.doBan,
            "mute": self.doMute,
            "kick": self.doKick,
        }

        defaultReason = "No reason."

        timer: Timer = self.bot.get_cog("Timer")
        if not timer:
            # Incase Timer cog not loaded yet.
            return await ctx.error(
                "Sorry, this command is currently not available. Please try again later"
            )

        try:
            check = await self.checkHierarchy(ctx, user, action)
        except HierarchyError as exc:
            return await ctx.error(str(exc))

        # Try getting necessary variables
        try:
            reason = time.arg or defaultReason
            delta = time.delta
            time = time.when
        except AttributeError:
            reason = kwargs.pop("reason", defaultReason) or defaultReason

        desc = "**Reason**: {}".format(reason)
        guildAndTime = ctx.guild.name
        if time is not None:
            desc += "\n**Duration**: {} ({})".format(delta, formatDateTime(time))
            guildAndTime += " until " + formatDateTime(time)

        DMMsg = {
            "ban": "You have been banned from {}. Reason: {}",
            "mute": "You have been muted from {}. Reason: {}",
            "kick": "You have been kicked from {}. Reason: {}",
        }

        try:
            await user.send(DMMsg[action].format(guildAndTime, reason))
            desc += "\n**DM**: User notified with a direct message."
        except (AttributeError, discord.HTTPException):
            # Failed to send DM
            desc += "\n**DM**: Failed to notify user."

        # Do the action
        try:
            await (actions[action])(
                ctx,
                user,
                reason="[{} (ID: {})]: {}".format(ctx.author, ctx.author.id, reason),
                **kwargs,
            )
        except discord.Forbidden:
            return await ctx.try_reply("I don't have permission to ban a user!")

        if time is not None:
            # Temporary ban
            await timer.createTimer(
                time,
                action,
                ctx.guild.id,
                ctx.author.id,
                user.id,
                created=utcnow(),
                owner=ctx.bot.user.id,
            )

        titles = {
            "ban": "Banned {}",
            "mute": "Muted {}",
            "kick": "Kicked {}",
        }

        e = ZEmbed.success(
            title=titles[action].format(user),
            description=desc,
        )
        await ctx.send(embed=e)

    @commands.group(
        usage="(user) [limit] [reason]",
        brief="Ban a user, with optional time limit",
        description=(
            "Ban a user, with optional time limit.\n\n Will delete user's "
            "message, use `save` subcommand to ban a user without deleting their "
            "message"
        ),
        extras=dict(
            example=(
                "ban @User#0000 4y absolutely no reason",
                "ban @User#0000 scam",
                "ban @User#0000 1 minutes",
            )
        ),
        invoke_without_command=True,
    )
    @checks.mod_or_permissions(ban_members=True)
    async def ban(
        self,
        ctx,
        user: Union[discord.Member, discord.User],
        *,
        time: TimeAndArgument = None,
    ):
        await self.doModeration(ctx, user, time, "ban")

    @ban.command(
        usage="(user) [limit] [reason]",
        brief="Ban a user, with time limit without deleting their message",
        description=(
            "Ban a user, with optional time limit without deleting their message"
        ),
        extras=dict(
            example=(
                "ban save @User#0000 30m bye",
                "ban save @User#0000 annoying",
                "ban save @User#0000 1 minutes",
            )
        ),
    )
    async def save(
        self,
        ctx,
        user: Union[discord.Member, discord.User],
        *,
        time: TimeAndArgument = None,
    ):
        await self.doModeration(ctx, user, time, "ban", saveMsg=True)

    @commands.command(
        brief="Unban a member",
        extras=dict(example=("unban @Someone Wrong person", "unban @Someone")),
    )
    async def unban(self, ctx, member: BannedMember, *, reason: str = "No reason."):
        await ctx.guild.unban(member.user, reason=reason)
        e = ZEmbed.success(
            title="Unbanned {}".format(member.user),
        )
        await ctx.try_reply(embed=e)

    async def doBan(self, ctx, user: discord.User, /, reason: str, **kwargs):
        saveMsg = kwargs.pop("saveMsg", False)

        await ctx.guild.ban(
            user,
            reason=reason,
            delete_message_days=0 if saveMsg else 1,
        )

    @commands.Cog.listener()
    async def on_ban_timer_complete(self, timer: TimerData):
        """Automatically unban."""
        guildId, modId, userId = timer.args
        await self.bot.wait_until_ready()

        guild = self.bot.get_guild(guildId)
        if not guild:
            return

        try:
            moderator = guild.get_member(modId) or await guild.fetch_member(modId)
        except discord.HTTPException:
            moderator = None

        modTemplate = "{} (ID: {})"
        if not moderator:
            try:
                moderator = self.bot.fetch_user(modId)
            except:
                moderator = "Mod ID {}".format(modId)

        moderator = modTemplate.format(moderator, modId)

        try:
            await guild.unban(
                discord.Object(id=userId),
                reason="Automatically unban from timer on {} by {}".format(
                    formatDateTime(timer.createdAt), moderator
                ),
            )
        except discord.NotFound:
            # unbanned manually
            return

    @commands.group(
        brief="Mute a member",
        invoke_without_command=True,
        extras=dict(
            example=(
                "mute @Someone 3h spam",
                "mute @Someone 1d",
                "mute @Someone Annoying",
            ),
        ),
    )
    @checks.mod_or_permissions(manage_messages=True)
    async def mute(
        self,
        ctx,
        user: discord.Member,
        *,
        time: TimeAndArgument = None,
    ):
        await self.doModeration(ctx, user, time, "mute")

    @mute.command(
        name="create",
        aliases=("set",),
        brief="Create or set muted role for mute command",
        extras=dict(
            example=(
                "mute create",
                "mute create Muted",
                "mute set @mute",
            )
        ),
        usage="[role name]",
    )
    async def muteCreate(self, ctx, name: Union[discord.Role, str] = "Muted"):
        await ctx.try_invoke(
            "role create" if isinstance(name, str) else "role set",
            arguments=f"{getattr(name, 'id', name)} type: muted",
        )

    @commands.command(brief="Unmute a member")
    @checks.mod_or_permissions(manage_messages=True)
    async def unmute(self, ctx, member: discord.Member, *, reason: str = "No reason."):
        muteRoleId = await self.bot.getGuildConfig(
            ctx.guild.id, "mutedRole", "guildRoles"
        )
        await member.remove_roles(discord.Object(id=muteRoleId), reason=reason)
        e = ZEmbed.success(
            title="Unmuted {}".format(member),
        )
        await ctx.try_reply(embed=e)

    async def doMute(self, ctx, member: discord.Member, /, reason: str, **kwargs):
        muteRoleId = await self.bot.getGuildConfig(
            ctx.guild.id, "mutedRole", "guildRoles"
        )
        await member.add_roles(discord.Object(id=muteRoleId), reason=reason)

    @commands.Cog.listener()
    async def on_mute_timer_complete(self, timer: TimerData):
        """Automatically unmute."""
        guildId, modId, userId = timer.args
        await self.bot.wait_until_ready()

        guild = self.bot.get_guild(guildId)
        if not guild:
            return

        try:
            moderator = guild.get_member(modId) or await guild.fetch_member(modId)
        except discord.HTTPException:
            moderator = None

        modTemplate = "{} (ID: {})"
        if not moderator:
            try:
                moderator = self.bot.fetch_user(modId)
            except:
                moderator = "Mod ID {}".format(modId)

        moderator = modTemplate.format(moderator, modId)

        member = guild.get_member(userId)
        muteRoleId = await self.bot.getGuildConfig(guild.id, "mutedRole", "guildRoles")
        role = discord.Object(id=muteRoleId)
        await member.remove_roles(
            role,
            reason="Automatically unmuted from timer on {} by {}".format(
                formatDateTime(timer.createdAt), moderator
            ),
        )

    @commands.command(
        brief="Kick a member",
        extras=dict(
            example=(
                "kick @Someone seeking attention",
                "kick @Someone",
            ),
        ),
    )
    @checks.mod_or_permissions(kick_members=True)
    async def kick(
        self,
        ctx,
        user: discord.Member,
        *,
        reason: str = None,
    ):
        await self.doModeration(ctx, user, None, "kick", reason=reason)

    async def doKick(self, ctx, member: discord.Member, /, reason: str, **kwargs):
        await member.kick(reason=reason)

    @commands.command(
        brief="Announce something",
        extras=dict(
            example=(
                "announce Hello World!",
                "announce target: everyone msg: Totally important message",
                "announce Exclusive announcement for @role target: @role ch: #test",
            ),
            flags={
                ("channel", "ch",): (
                    "Announcement destination (use Announcement channel "
                    "by default set by `announcement @role` command)"
                ),
                "target": "Ping target (everyone, here, or @role)",
                ("message", "msg"): "Edit/extend announcement message",
            },
        ),
        usage="(message) [options]",
    )
    async def announce(self, ctx, *, arguments: str):
        parsed = await self.parseAnnouncement(arguments)
        annCh = parsed.channel
        if not annCh:
            annCh = await self.bot.getGuildConfig(
                ctx.guild.id, "announcementCh", "guildChannels"
            )
            annCh = ctx.guild.get_channel(annCh)
        else:
            annCh: discord.TextChannel = await commands.TextChannelConverter().convert(
                ctx, annCh
            )

        target = " ".join(parsed.target)
        if target.endswith("everyone") or target.endswith("here"):
            target = f"@{target}"
        else:
            target = await commands.RoleConverter().convert(ctx, target)

        await self.doAnnouncement(ctx, " ".join(parsed.message), target, annCh)

    async def parseAnnouncement(self, arguments: str):
        parser = ArgumentParser(allow_abbrev=False)
        parser.add_argument("--target", nargs="+")
        parser.add_argument("--channel", aliases=("--ch",))
        parser.add_argument("message", action="extend", nargs="*")
        parser.add_argument("--message", aliases=("--msg",), action="extend", nargs="+")

        parsed, _ = await parser.parse_known_from_string(arguments)

        if not parsed.message:
            raise ArgumentError("Missing announcement message")

        return parsed

    async def doAnnouncement(
        self, ctx, announcement, target, dest: discord.TextChannel
    ):
        content = str(getattr(target, "mention", target))
        content += f"\n{announcement}"
        await dest.send(content)

    @commands.command(
        brief="Clear the chat",
        usage="(amount of message)",
        hidden=True,
    )
    @checks.mod_or_permissions(manage_messages=True)
    async def clearchat(self, ctx, num):
        try:
            num = int(num)
        except ValueError:
            return await ctx.send(f"{num} is not a valid number!")

        e = ZEmbed.loading(title="Deleting messages...")

        msg = await ctx.send(embed=e)

        def isLoading(m):
            return m != msg

        try:
            deleted_msg = await ctx.message.channel.purge(
                limit=num + 1,
                check=isLoading,
                before=None,
                after=None,
                around=None,
                oldest_first=False,
                bulk=True,
            )
        except Forbidden:
            return await ctx.error("The bot doesn't have `Manage Messages` permission!", title="Missing Permission")

        msg_num = max(len(deleted_msg), 0)

        if msg_num == 0:
            resp = "Deleted `0 message` 😔 "
            # resp = "Deleted `0 message` 🙄  \n (I can't delete messages "\
            # "older than 2 weeks due to discord limitations)"
        else:
            resp = "Deleted `{} message{}` ✨ ".format(
                msg_num, "" if msg_num < 2 else "s"
            )

        e = ZEmbed.default(ctx, title=resp)

        await msg.edit(embed=e)


def setup(bot):
    bot.add_cog(Moderation(bot))
