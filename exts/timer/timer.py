"""
This Source Code Form is subject to the terms of the Mozilla Public
License, v. 2.0. If a copy of the MPL was not distributed with this
file, You can obtain one at http://mozilla.org/MPL/2.0/.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import json
from contextlib import suppress
from typing import TYPE_CHECKING, Optional

import discord
import pytz
from discord.ext import commands

from core.converter import TimeAndArgument
from core.embed import ZEmbed
from core.mixin import CogMixin
from utils import dbQuery
from utils.format import formatDateTime, formatDiscordDT
from utils.other import utcnow


if TYPE_CHECKING:
    from core.bot import ziBot


class TimerData:
    __slots__ = (
        "id",
        "event",
        "args",
        "kwargs",
        "extra",
        "expires",
        "createdAt",
        "owner",
    )

    def __init__(self, data):
        self.id = data[0]
        self.event = data[1]
        self.args: list = []
        self.kwargs: dict = {}
        try:
            self.extra = json.loads(data[2])
            self.args = self.extra.pop("args", [])
            self.kwargs = self.extra.pop("kwargs", {})
        except TypeError:
            self.extra = data[2]
        self.expires = dt.datetime.fromtimestamp(data[3], dt.timezone.utc)
        self.createdAt = dt.datetime.fromtimestamp(data[4], dt.timezone.utc)
        self.owner = data[5]

    @classmethod
    def temporary(cls, expires, created, event, owner, args, kwargs):
        return cls(
            [None, event, {"args": args, "kwargs": kwargs}, expires, created, owner]
        )


class Timer(commands.Cog, CogMixin):
    """Time-related commands."""

    icon = "🕑"
    cc = True

    def __init__(self, bot: ziBot) -> None:
        super().__init__(bot)

        self.haveData = asyncio.Event(loop=bot.loop)
        self._currentTimer: Optional[TimerData] = None
        self.bot.loop.create_task(self.asyncInit())

    async def asyncInit(self) -> None:
        async with self.bot.db.transaction():
            await self.bot.db.execute(dbQuery.createTimerTable)
        self.task = self.bot.loop.create_task(self.dispatchTimers())

    def cog_unload(self) -> None:
        task = getattr(self, "task", None)
        if task:
            task.cancel()

    def restartTimer(self) -> None:
        self.task.cancel()
        self.task = self.bot.loop.create_task(self.dispatchTimers())

    async def getActiveTimer(self, days: int = 7) -> Optional[TimerData]:
        data = await self.bot.db.fetch_one(
            """
                SELECT * FROM timer
                WHERE
                    expires < :interval
                ORDER BY
                    expires ASC
            """,
            values={"interval": (utcnow() + dt.timedelta(days=days)).timestamp()},
        )
        return TimerData(data) if data else None

    async def waitForActiveTimer(self, days: int = 7) -> Optional[TimerData]:
        timer: Optional[TimerData] = await self.getActiveTimer(days=days)
        if timer is not None:
            self.haveData.set()
            return timer

        self.haveData.clear()
        self._currentTimer: Optional[TimerData] = None
        await self.haveData.wait()
        return await self.getActiveTimer(days=days)

    async def callTimer(self, timer: TimerData) -> None:
        # delete the timer
        async with self.bot.db.transaction():
            await self.bot.db.execute(
                "DELETE FROM timer WHERE timer.id=:id", values={"id": timer.id}
            )

        # dispatch the event
        eventName = f"{timer.event}_timer_complete"
        self.bot.dispatch(eventName, timer)

    async def dispatchTimers(self) -> None:
        try:
            while not self.bot.is_closed():
                timer = self._currentTimer = await self.waitForActiveTimer(days=40)
                now = utcnow()

                if timer.expires >= now:  # type: ignore # Already waited for active timer
                    sleepAmount = (timer.expires - now).total_seconds()  # type: ignore
                    await asyncio.sleep(sleepAmount)

                await self.callTimer(timer)  # type: ignore
        except asyncio.CancelledError:
            raise
        except (OSError, discord.ConnectionClosed):
            self.restartTimer()

    async def createTimer(self, *args, **kwargs) -> TimerData:
        when, event, *args = args

        now = kwargs.pop("created", utcnow())
        owner = kwargs.pop("owner", None)

        whenTs = when.timestamp()
        nowTs = now.timestamp()

        timer: TimerData = TimerData.temporary(
            event=event,
            args=args,
            kwargs=kwargs,
            expires=whenTs,
            created=nowTs,
            owner=owner,
        )
        delta = (when - now).total_seconds()

        query = """
            INSERT INTO timer (event, extra, expires, created, owner)
            VALUES (:event, :extra, :expires, :created, :owner)
        """
        values = {
            "event": event,
            "extra": json.dumps({"args": args, "kwargs": kwargs}),
            "expires": whenTs,
            "created": nowTs,
            "owner": owner,
        }
        async with self.db.transaction():
            timer.id = await self.db.execute(query, values=values)

        if delta <= (86400 * 40):  # 40 days
            self.haveData.set()

        if self._currentTimer and when < self._currentTimer.expires:
            # cancel the task and re-run it
            self.restartTimer()

        return timer

    @commands.command(
        aliases=["timer", "remind"],
        brief="Reminds you about something after certain amount of time",
    )
    @commands.cooldown(2, 5, commands.BucketType.user)
    async def reminder(self, ctx, *, argument: TimeAndArgument) -> discord.Message:
        now = utcnow()
        when = argument.when
        message = argument.arg or "Reminder"
        if not when:
            return await ctx.try_reply("Invalid time.")

        await self.createTimer(
            when,
            "reminder",
            ctx.channel.id,
            message,
            messageId=ctx.message.id,
            created=now,
            owner=ctx.author.id,
        )

        return await ctx.try_reply(
            "In {}, {}".format(
                argument.delta,
                message,
            )
        )

    @commands.command(brief="Get current time")
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def time(self, ctx, timezone: str = None) -> None:
        tz = None
        if timezone:
            with suppress(pytz.UnknownTimeZoneError):
                tz = pytz.timezone(timezone)

        dt = utcnow()
        if tz:
            dt = dt.astimezone(tz)

        # TODO: Add timezone
        e = discord.Embed(
            title="Current Time",
            description=formatDateTime(dt),
            colour=self.bot.colour,
        )
        e.set_footer(text="Timezone coming soon\u2122!")
        await ctx.try_reply(embed=e)

    @commands.Cog.listener("on_reminder_timer_complete")
    async def onReminderTimerComplete(self, timer: TimerData) -> None:
        channelId, message = timer.args
        authorId = timer.owner

        try:
            channel = self.bot.get_channel(channelId) or (
                await self.bot.fetch_channel(channelId)
            )
        except discord.HTTPException:
            return

        guildId = (
            channel.guild.id if isinstance(channel, discord.TextChannel) else "@me"
        )
        messageId = timer.kwargs.get("messageId")
        msgUrl = f"https://discord.com/channels/{guildId}/{channelId}/{messageId}"

        e = ZEmbed(
            description="[<:upArrow:862301023749406760> Jump to Source]({})".format(
                msgUrl
            ),
        )

        await channel.send(
            "<@{}>, {}: {}".format(
                authorId,
                formatDiscordDT(timer.createdAt, "R"),
                discord.utils.escape_mentions(message),
            ),
            embed=e,
        )