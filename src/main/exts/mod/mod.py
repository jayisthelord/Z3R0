"""
This Source Code Form is subject to the terms of the Mozilla Public
License, v. 2.0. If a copy of the MPL was not distributed with this
file, You can obtain one at http://mozilla.org/MPL/2.0/.
"""

from contextlib import suppress
from typing import Optional, Union

import discord
from discord.ext import commands

from ...core import checks, db
from ...core.converter import BannedMember, Hierarchy, MemberOrUser, TimeAndArgument
from ...core.data import CacheUniqueViolation
from ...core.embed import ZEmbed
from ...core.errors import MissingMuteRole
from ...core.menus import ZMenuPagesView
from ...core.mixin import CogMixin
from ...exts.admin._flags import RoleCreateFlags, RoleSetFlags
from ...exts.timer.timer import Timer, TimerData
from ...utils import doCaselog, getGuildRole, setGuildRole, utcnow
from ...utils.format import formatDateTime
from ._flags import AnnouncementFlags
from ._pages import CaseListSource


# TODO: Slash/Context Menu
class Moderation(commands.Cog, CogMixin):
    """Moderation commands."""

    icon = "🛠️"

    async def cog_check(self, ctx):
        return ctx.guild is not None

    async def doModeration(self, ctx, user, _time: Optional[TimeAndArgument], action: str, **kwargs):
        """Ban function, self-explanatory"""
        actions = {
            "ban": self.doBan,
            "unban": self.doUnban,
            "mute": self.doMute,
            "unmute": self.doUnmute,
            "kick": self.doKick,
        }

        defaultReason = "No reason."

        timer: Optional[Timer] = self.bot.get_cog("Timer")  # type: ignore
        if not timer:
            # Incase Timer cog not loaded yet.
            return await ctx.error("Sorry, this command is currently not available. Please try again later")

        time = None
        delta = None

        # Try getting necessary variables
        try:
            reason = _time.arg or defaultReason  # type: ignore # handled by try-except
            delta = _time.delta  # type: ignore
            time = _time.when  # type: ignore
        except AttributeError:
            reason = kwargs.pop("reason", defaultReason) or defaultReason

        desc = "**Reason**: {}".format(reason)
        guildAndTime = ctx.guild.name
        if time is not None:
            desc += "\n**Duration**: {} ({})".format(delta, formatDateTime(time))
            guildAndTime += " until " + formatDateTime(time)

        silent = kwargs.pop("silent", False)  # Silent = don't DM

        if not silent:
            DMMsgs = {
                "ban": "banned",
                "unban": "unbanned",
                "mute": "muted",
                "unmute": "unmuted",
            }
            DMMsg = DMMsgs.get(action, action + "ed")

            DMFmt = f"You have been {DMMsg}" + " from {}. reason: {}"

            try:
                await user.send(DMFmt.format(guildAndTime, reason))
                desc += "\n**DM**: User notified with a direct message."
            except (AttributeError, discord.HTTPException):
                # Failed to send DM
                desc += "\n**DM**: Failed to notify user."

        caseNum = await doCaselog(
            self.bot,
            guildId=ctx.guild.id,
            type=action,
            modId=ctx.author.id,
            targetId=user.id,
            reason=reason,
        )
        if caseNum:
            desc += "\n**Case**: #{}".format(caseNum)

        # Do the action
        try:
            await (actions[action])(
                ctx,
                user,
                reason="[{} (ID: {}) #{}]: {}".format(ctx.author, ctx.author.id, caseNum, reason),
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
            "ban": "Banned",
            "unban": "Unbanned",
            "mute": "Muted",
            "unmute": "Unmuted",
        }
        formattedTitle = f"{titles.get(action, action + 'ed')} {user}"

        e = ZEmbed.success(
            title=formattedTitle,
            description=desc,
        )
        await ctx.send(embed=e)

    @commands.group(
        usage="(member) [limit] [reason]",
        description="Ban a member, with optional time limit",
        help=(
            ".\n\nWill delete the member's messages! Use `save` subcommand to ban a user without deleting their "
            "message. So instead of `>ban @User#0000` you do `>ban save @User#0000`"
            "\nNo unit time limit is no longer supported, you must specify the unit! e.g. 30min, 3s, 3 years, etc"
        ),
        extras=dict(
            example=(
                "ban @User#0000 4y absolutely no reason",
                "ban @User#0000 scam",
                "ban @User#0000 1 minutes",
            ),
            perms={
                "bot": "Ban Members",
                "user": "Ban Members",
            },
        ),
        invoke_without_command=True,
    )
    @commands.bot_has_guild_permissions(ban_members=True)
    @checks.mod_or_permissions(ban_members=True)
    async def ban(
        self,
        ctx,
        user: Hierarchy(action="ban"),  # type: ignore
        *,
        time: TimeAndArgument = None,
    ):
        await self.doModeration(ctx, user, time, "ban")

    @ban.command(
        usage="(member) [limit] [reason]",
        description="Ban a member, with optional time limit without deleting their message",
        help=(
            "\n\nJust like ban, but doesn't delete the member's messages"
            "\nNo unit time limit is no longer supported, you **MUST** specify the unit! e.g. 30min, 3s, 3 years, etc"
        ),
        extras=dict(
            example=(
                "ban save @User#0000 30m bye",
                "ban save @User#0000 annoying",
                "ban save @User#0000 1 minutes",
            ),
            perms={
                "bot": "Ban Members",
                "user": "Ban Members",
            },
        ),
    )
    async def save(
        self,
        ctx,
        user: Hierarchy(action="ban"),  # type: ignore
        *,
        time: TimeAndArgument = None,
    ):
        await self.doModeration(ctx, user, time, "ban", saveMsg=True)

    @commands.command(
        description="Unban a user",
        extras=dict(
            example=("unban @Someone Wrong person", "unban @Someone"),
            perms={
                "bot": "Ban Members",
                "user": "Ban Members",
            },
        ),
    )
    @checks.mod_or_permissions(ban_members=True)
    async def unban(self, ctx, member: BannedMember, *, reason: str = "No reason"):
        await self.doModeration(ctx, member.user, None, "unban", reason=reason)

    async def doBan(self, ctx, user: discord.User, /, reason: str, **kwargs):
        saveMsg = kwargs.pop("saveMsg", False)

        await ctx.guild.ban(
            user,
            reason=reason,
            delete_message_days=0 if saveMsg else 1,
        )

    async def doUnban(self, ctx, user: discord.User, /, reason: str, **_):
        await ctx.guild.unban(user, reason=reason)

    @commands.Cog.listener("on_ban_timer_complete")
    async def onBanTimerComplete(self, timer: TimerData):
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
            except BaseException:
                moderator = "Mod ID {}".format(modId)

        moderator = modTemplate.format(moderator, modId)

        try:
            await guild.unban(
                discord.Object(id=userId),
                reason="Automatically unban from timer on {} by {}".format(formatDateTime(timer.createdAt), moderator),
            )
        except discord.NotFound:
            # unbanned manually
            return

    @commands.group(
        description="Mute a member",
        invoke_without_command=True,
        extras=dict(
            example=(
                "mute @Someone 3h spam",
                "mute @Someone 1d",
                "mute @Someone Annoying",
            ),
            perms={
                "bot": "Manage Roles",
                "user": "Manage Messages",
            },
        ),
    )
    @commands.bot_has_guild_permissions(manage_roles=True)
    @checks.mod_or_permissions(manage_messages=True)
    async def mute(
        self,
        ctx,
        user: Hierarchy(commands.MemberConverter, action="mute"),  # type: ignore
        *,
        time: TimeAndArgument = None,
    ):
        mutedRoleId = await getGuildRole(ctx.bot, ctx.guild.id, "mutedRole")
        if not mutedRoleId:
            raise MissingMuteRole(ctx.clean_prefix) from None

        if user._roles.has(mutedRoleId):
            return await ctx.error(f"{user.mention} is already muted!")

        await self.doModeration(ctx, user, time, "mute", prefix=ctx.clean_prefix, mutedRoleId=mutedRoleId)

    async def doMute(self, _n, member: discord.Member, /, reason: str, **kwargs):
        mutedRoleId = kwargs.get("mutedRoleId", 0)
        try:
            await member.add_roles(discord.Object(id=mutedRoleId), reason=reason)
        except TypeError:
            pass

    @mute.command(
        name="create",
        aliases=("set",),
        description="Create or set muted role for mute command",
        extras=dict(
            example=(
                "mute create",
                "mute create Muted",
                "mute set @mute",
            ),
            perms={
                "bot": "Manage Roles",
                "user": "Administrator",
            },
        ),
        usage="[role name]",
    )
    async def muteCreate(self, ctx, name: Union[discord.Role, str] = "Muted"):
        cmd = "create" if isinstance(name, str) else "set"
        argString = f"role: {getattr(name, 'id', name)} type: muted"

        if cmd == "create":
            argument = await RoleCreateFlags.convert(ctx, arguments=argString)
        else:
            argument = await RoleSetFlags.convert(ctx, arguments=argString)

        await ctx.try_invoke(
            f"role {cmd}",
            arguments=argument,
        )

    @commands.command(
        description="Unmute a member",
        extras=dict(
            perms={
                "bot": "Ban Members",
                "user": "Ban Members",
            },
        ),
    )
    @commands.bot_has_guild_permissions(manage_messages=True)
    @checks.mod_or_permissions(manage_messages=True)
    async def unmute(self, ctx, member: MemberOrUser, *, reason: str = "No reason"):
        guildId = ctx.guild.id
        mutedRoleId = await getGuildRole(self.bot, guildId, "mutedRole")
        if not mutedRoleId:
            raise MissingMuteRole(ctx.clean_prefix) from None

        if not member._roles.has(mutedRoleId):
            return await ctx.error(f"{member.mention} is not muted!")

        await self.doModeration(ctx, member, None, action="unmute", reason=reason, mutedRoleId=mutedRoleId)

    async def doUnmute(self, _n, member: discord.Member, /, reason: str, **kwargs):
        mutedRoleId = kwargs.get("mutedRoleId", 0)
        role = discord.Object(id=mutedRoleId)
        try:
            await member.remove_roles(role, reason=reason)
        except (discord.HTTPException, AttributeError):
            # Failed to remove role, just remove it manually
            await self.manageMuted(member, False, role)

    @commands.Cog.listener("on_member_update")
    async def onMemberUpdate(self, before: discord.Member, after: discord.Member):
        # Used to manage muted members
        if before.roles == after.roles:
            return

        guildId = after.guild.id
        mutedRoleId = await getGuildRole(self.bot, guildId, "mutedRole")
        if not mutedRoleId:
            return

        beforeHas = before._roles.has(mutedRoleId)
        afterHas = after._roles.has(mutedRoleId)

        if beforeHas == afterHas:
            return

        await self.manageMuted(after, afterHas, discord.Object(id=mutedRoleId))

    @commands.Cog.listener("on_guild_role_delete")
    async def onMutedRoleDeleted(self, role):
        mutedRoleId = await getGuildRole(self.bot, role.guild.id, "mutedRole")
        if not mutedRoleId or mutedRoleId != role.id:
            return

        await setGuildRole(self.bot, role.guild.id, "mutedRole", None)

    @commands.Cog.listener("on_mute_timer_complete")
    async def onMuteTimerComplete(self, timer: TimerData):
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
            except BaseException:
                moderator = "Mod ID {}".format(modId)

        moderator = modTemplate.format(moderator, modId)

        member = guild.get_member(userId)
        mutedRoleId = await getGuildRole(self.bot, guild.id, "mutedRole")
        if not mutedRoleId:
            return await self.manageMuted(member, False, None)

        role = discord.Object(id=mutedRoleId)

        try:
            await member.remove_roles(
                role,
                reason="Automatically unmuted from timer on {} by {}".format(formatDateTime(timer.createdAt), moderator),
            )
        except (discord.NotFound, discord.HTTPException, AttributeError):
            # incase mute role got removed or member left the server
            await self.manageMuted(member, False, role)

    async def getMutedMembers(self, guildId: int):
        # Getting muted members from db/cache
        # Will cache db results automatically
        if (mutedMembers := self.bot.cache.guildMutes.get(guildId)) is None:  # type: ignore
            dbMutes = await db.GuildMutes.filter(guild_id=guildId)

            try:
                mutedMembers = [m.mutedId for m in dbMutes]
                self.bot.cache.guildMutes.extend(guildId, mutedMembers)  # type: ignore
            except ValueError:
                mutedMembers = []
        return mutedMembers

    async def manageMuted(
        self,
        member: discord.Member,
        mode: bool,
        mutedRole: Union[discord.Role, discord.Object],
    ):
        """Manage muted members, for anti mute evasion

        mode: False = Deletion, True = Insertion"""

        memberId = member.id
        guildId = member.guild.id

        await self.getMutedMembers(guildId)

        if mode is False:
            # Remove member from mutedMembers list
            try:
                self.bot.cache.guildMutes.remove(guildId, memberId)  # type: ignore
            except IndexError:
                # It's not in the list so we'll just return
                return

            await db.GuildMutes.filter(guild_id=guildId, mutedId=memberId).delete()

            self.bot.dispatch("member_unmuted", member, mutedRole)

        elif mode is True:
            # Add member to mutedMembers list
            try:
                self.bot.cache.guildMutes.add(guildId, memberId)  # type: ignore
            except CacheUniqueViolation:
                # Already in the list
                return

            await db.GuildMutes.create(guild_id=guildId, mutedId=memberId)

            self.bot.dispatch("member_muted", member, mutedRole)

    @commands.Cog.listener("on_member_join")
    async def handleMuteEvasion(self, member: discord.Member):
        """Handle mute evaders"""
        mutedMembers = await self.getMutedMembers(member.guild.id)
        if not mutedMembers:
            return

        if member.id not in mutedMembers:
            # Not muted
            return

        with suppress(MissingMuteRole):
            # Attempt to remute mute evader
            mutedRoleId = await getGuildRole(self.bot, member.guild.id, "mutedRole")
            await self.doMute(None, member, "Mute evasion", mutedRoleId=mutedRoleId)

    # https://github.com/Rapptz/RoboDanny/blob/0992171592f1b92ad74fe2eb5cf2efe1e9a51be8/bot.py#L226-L281
    async def resolveMemberIds(self, guild, member_ids):
        """Bulk resolves member IDs to member instances, if possible.
        Members that can't be resolved are discarded from the list.
        This is done lazily using an asynchronous iterator.
        Note that the order of the resolved members is not the same as the input.
        Parameters
        -----------
        guild: Guild
            The guild to resolve from.
        member_ids: Iterable[int]
            An iterable of member IDs.
        Yields
        --------
        Member
            The resolved members.
        """

        needs_resolution = []
        for member_id in member_ids:
            member = guild.get_member(member_id)
            if member is not None:
                yield member
            else:
                needs_resolution.append(member_id)

        total_need_resolution = len(needs_resolution)
        if total_need_resolution == 0:
            pass
        elif total_need_resolution >= 1:
            shard = self.get_shard(guild.shard_id)
            if shard.is_ws_ratelimited():
                try:
                    member = await guild.fetch_member(needs_resolution[0])
                except discord.HTTPException:
                    pass
                else:
                    yield member
            else:
                members = await guild.query_members(limit=1, user_ids=needs_resolution, cache=True)
                if members:
                    yield members[0]
        elif total_need_resolution <= 100:
            # Only a single resolution call needed here
            resolved = await guild.query_members(limit=100, user_ids=needs_resolution, cache=True)
            for member in resolved:
                yield member
        else:
            # We need to chunk these in bits of 100...
            for index in range(0, total_need_resolution, 100):
                to_resolve = needs_resolution[index : index + 100]
                members = await guild.query_members(limit=100, user_ids=to_resolve, cache=True)
                for member in members:
                    yield member

    @commands.Cog.listener("on_muted_role_changed")
    async def onMutedRoleChanged(self, guild: discord.Guild, role: discord.Role):
        """Handle mute role changed"""
        mutedMembers = await self.getMutedMembers(guild.id)
        if mutedMembers:
            reason = "Merging mute roles"
            async for member in self.resolveMemberIds(guild, mutedMembers):
                if not member._roles.has(role.id):
                    try:
                        await member.add_roles(role, reason=reason)
                    except discord.HTTPException:
                        pass

    @commands.command(
        description="Kick a member",
        extras=dict(
            example=(
                "kick @Someone seeking attention",
                "kick @Someone",
            ),
            perms={
                "bot": "Kick Members",
                "user": "Kick Members",
            },
        ),
    )
    @commands.bot_has_guild_permissions(kick_members=True)
    @checks.mod_or_permissions(kick_members=True)
    async def kick(
        self,
        ctx,
        user: Hierarchy(commands.MemberConverter, action="kick"),  # type: ignore
        *,
        reason: str = None,
    ):
        await self.doModeration(ctx, user, None, "kick", reason=reason)

    async def doKick(self, ctx, member: discord.Member, /, reason: str, **kwargs):
        await member.kick(reason=reason)

    @commands.command(
        description="Announce something",
        extras=dict(
            example=(
                "announce Hello World!",
                "announce Totally important announcement target: everyone",
                "announce Exclusive announcement for @role target: @role ch: #test",
            ),
            flags={
                (
                    "channel",
                    "ch",
                ): ("Announcement destination (use Announcement channel " "by default set by `announcement @role` command)"),
                "target": "Ping target (everyone, here, or @role)",
            },
        ),
        usage="(message) [options]",
    )
    @checks.mod_or_permissions(manage_messages=True)
    async def announce(self, ctx, *, arguments: AnnouncementFlags):
        message, parsed = arguments
        annCh = parsed.channel
        if not annCh:
            annCh = await self.bot.getGuildConfig(ctx.guild.id, "announcementCh", "GuildChannels")
            annCh = ctx.guild.get_channel(annCh)
            if not annCh:
                return await ctx.error("No announcement channel found!")

        target = parsed.target
        if isinstance(target, str):
            target = parsed.target.lstrip("@")
            if target.endswith("everyone") or target.endswith("here"):
                target = f"@{target}"

        await self.doAnnouncement(ctx, message, target, annCh)

    async def doAnnouncement(self, ctx, announcement, target, dest: discord.TextChannel):
        content = str(getattr(target, "mention", target))
        content += f"\n{announcement}"
        await dest.send(content)

    @commands.command(
        description="Clear the chat",
        usage="(amount of message)",
        extras=dict(
            perms={
                "bot": "Manage Messages",
                "user": "Manage Messages",
            },
        ),
    )
    @commands.bot_has_guild_permissions(manage_messages=True)
    @checks.mod_or_permissions(manage_messages=True)
    async def clearchat(self, ctx, num):
        try:
            num = int(num)
        except ValueError:
            return await ctx.send(f"{num} is not a valid number!")

        e = ZEmbed.loading(title="Deleting messages...")

        msg = await ctx.send(embed=e)

        try:
            deleted_msg = await ctx.message.channel.purge(
                limit=num,
                before=ctx.message,
                after=None,
                around=None,
                oldest_first=False,
                bulk=True,
            )
        except discord.Forbidden:
            return await ctx.error(
                "The bot doesn't have `Manage Messages` permission!",
                title="Missing Permission",
            )

        msg_num = max(len(deleted_msg), 0)

        if msg_num == 0:
            resp = "Deleted `0 message` 😔 "
        else:
            resp = "Deleted `{} message{}` ✨ ".format(msg_num, "" if msg_num < 2 else "s")

        e = ZEmbed.default(ctx, title=resp)

        await msg.edit(embed=e)

    @commands.command(aliases=("cases",), description="Get moderator's cases")
    @checks.mod_or_permissions(manage_messages=True)
    async def caselogs(self, ctx, moderator: discord.Member = None):
        moderator = moderator or ctx.author
        modCases = await db.CaseLog.filter(guild_id=ctx.guild.id, modId=moderator.id)
        if not modCases:
            return await ctx.error(
                f"{moderator.display_name} doesn't have any cases",
                title="No cases found",
            )

        menu = ZMenuPagesView(ctx, source=CaseListSource(moderator, modCases))
        await menu.start()
