"""
GraphQL-based API Wrapper.
"""

import aiohttp


class GraphQL:
    """
    Example:
        # Somewhere (maybe __init__)
        self.graphql = GraphQL("https://graphql.anilist.co")

        # Querying stuff (POST method)
        self.graphql.queryPost(
            '''
                query($id:Int){
                    Media(id:$id, type:ANIME){
                        id
                        format
                        title { romaji }
                        coverImage { large }
                        isAdult
                    }
                }
            ''',
            id=25,
        )
    """
    def __init__(self, baseUrl: str, **kwargs):
        self.baseUrl = baseUrl
        self.session = kwargs.pop("session", aiohttp.ClientSession())

    async def query(self, query, method: str = "POST", **kwargs):
        async with getattr(self.session, method.lower())(
            self.baseUrl, json={"query": query, "variables": kwargs}
        ) as req:
            return await req.json()

    async def queryPost(self, query, **kwargs):
        return await self.query(query, method="POST", **kwargs)

    async def queryGet(self, query, **kwargs):
        return await self.query(query, method="GET", **kwargs)


if __name__ == "__main__":
    """For testing."""
    import asyncio

    loop = asyncio.get_event_loop()
    print(
        loop.run_until_complete(
            GraphQL("https://graphql.anilist.co").queryPost(
                """
                    query($id:Int){
                        Media(id:$id, type:ANIME){
                            id
                            format
                            title { romaji }
                            coverImage { large }
                            isAdult
                        }
                    }
                """,
                id=25,
            )
        )
    )