"""
This Source Code Form is subject to the terms of the Mozilla Public
License, v. 2.0. If a copy of the MPL was not distributed with this
file, You can obtain one at http://mozilla.org/MPL/2.0/.
"""
from random import randrange

import discord
from discord.ext import commands

from core.embed import ZEmbed
from core.enums import Emojis
from core.menus import ZMenuPagesView
from core.mixin import CogMixin
from utils.api import graphql

from ._flags import AnimeSearchFlags
from ._pages import AnimeSearchPageSource


class ReadMore(discord.ui.Button):
    async def callback(self, interaction: discord.Interaction):
        view: ZMenuPagesView = self.view
        page = await view._source.get_page(view.currentPage)  # type: ignore
        synopsis = view._source.sendSynopsis(page)  # type: ignore
        e = ZEmbed(description=synopsis)
        await interaction.response.send_message(embed=e, ephemeral=True)


class AniList(commands.Cog, CogMixin):
    """Cog about Anime and Manga."""

    icon = "<:AniList:872771143797440533>"

    def __init__(self, bot):
        super().__init__(bot)
        self.anilist = graphql.GraphQL(
            "https://graphql.anilist.co", session=self.bot.session
        )

    @commands.group(
        aliases=("ani",),
        brief="Get information about anime",
    )
    async def anime(self, ctx):
        pass

    @anime.command(
        name="search",
        aliases=("s", "find", "?", "info"),
        brief="Search for an anime with AniList",
    )
    async def animeSearch(self, ctx, *, arguments: AnimeSearchFlags):
        name, parsed = arguments

        if not name:
            return await ctx.error("You need to specify the name!")

        kwargs = {
            "name": name,
            "page": 1,
            "perPage": 10,
        }
        if parsed.format_:
            kwargs["format"] = parsed.format_.strip().upper().replace(" ", "_")

        query = await self.anilist.queryPost(
            """
            query(
                $name: String
                $format: MediaFormat
                $page: Int
                $perPage: Int=5
            ) {
                Page(perPage:$perPage, page:$page) {
                    pageInfo{hasNextPage, currentPage, lastPage}
                    media(search:$name, type:ANIME, format:$format){
                        id,
                        format,
                        title {
                            romaji,
                            english
                        },
                        episodes,
                        duration,
                        status,
                        startDate {
                            year,
                            month,
                            day
                        },
                        endDate {
                            year,
                            month,
                            day
                        },
                        genres,
                        coverImage {
                            large
                        },
                        bannerImage,
                        description,
                        averageScore,
                        studios { nodes { name } },
                        seasonYear,
                        externalLinks {
                            site,
                            url
                        },
                        isAdult
                    }
                }
            }
            """,
            **kwargs,
        )
        aniData = query["data"]["Page"]["media"]
        menu = ZMenuPagesView(ctx, source=AnimeSearchPageSource(ctx, aniData))
        menu.add_item(ReadMore(emoji=Emojis.info))
        await menu.start()

    @commands.command(brief="Get random anime")
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def findanime(self, ctx):
        query = await self.anilist.queryPost(
            """
            {
                Page(perPage:1) {
                    pageInfo {
                        lastPage
                    }
                    media(type: ANIME, format_in:[MOVIE, TV, TV_SHORT]) {
                        id
                    }
                }
            }
            """
        )
        lastPage = query["data"]["Page"]["pageInfo"]["lastPage"]
        query = await self.anilist.queryPost(
            """
            query ($random: Int) {
                Page(page: $random, perPage: 1) {
                    pageInfo {
                        total
                    }
                    media(type: ANIME, isAdult: false, status_not: NOT_YET_RELEASED) {
                        id,
                        title { userPreferred },
                        siteUrl
                    }
                }
            }
            """,
            random=randrange(1, lastPage),
        )
        mediaData = query["data"]["Page"]["media"][0]
        id = mediaData["id"]
        e = ZEmbed.default(
            ctx, title=mediaData["title"]["userPreferred"], url=mediaData["siteUrl"]
        ).set_image(url=f"https://img.anili.st/media/{id}")
        await ctx.try_reply(embed=e)
