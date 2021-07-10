from __future__ import annotations
from typing import Any, Tuple, Dict, Iterable, List


import time


# https://github.com/Rapptz/RoboDanny/blob/rewrite/cogs/utils/cache.py#L22-L43
class ExpiringDict(dict):
    """Subclassed dict for expiring cache"""

    def __init__(self, items: dict = {}, maxAgeSeconds: int = 3600) -> None:
        self.maxAgeSeconds: int = maxAgeSeconds  # (Default: 3600 seconds (1 hour))
        curTime: float = time.monotonic()
        super().__init__({k: (v, curTime) for k, v in items.items()})

    def verifyCache(self) -> None:
        curTime: float = time.monotonic()
        toRemove: list = [
            k for (k, (v, t)) in self.items() if curTime > (t + self.maxAgeSeconds)
        ]
        for k in toRemove:
            del self[k]

    def __contains__(self, key: Any) -> bool:
        self.verifyCache()
        return super().__contains__(key)

    def __getitem__(self, key: Any) -> Any:
        self.verifyCache()
        return super().__getitem__(key)[0]

    def get(self, key: Any, fallback: Any = None) -> Any:
        try:
            return self.__getitem__(key)
        except KeyError:
            return fallback

    def getRaw(self, key: Any) -> Tuple[Any]:
        self.verifyCache()
        return super().__getitem__(key)

    def __setitem__(self, key: Any, value: Any) -> None:
        self.verifyCache()
        return super().__setitem__(key, (value, time.monotonic()))


class CacheError(Exception):
    def __init__(self, message):
        super().__init__(message)


class CacheUniqueViolation(CacheError):
    def __init__(self):
        super().__init__("Unique Value Violation")


class CacheListFull(CacheError):
    def __init__(self):
        super().__init__("Cache list is already full!")


class CacheProperty:
    """Base Class for Cache Property"""

    def __init__(self, unique: bool = False, ttl: int = 0) -> None:
        self.unique: bool = unique  # Only unique value can be added/appended
        self._items: Dict[str, Any] = {} if ttl < 1 else ExpiringDict(maxAgeSeconds=ttl)

    def __repr__(self) -> str:
        return f"<CacheProperty: {self._items}>"

    @property
    def items(self) -> dict:
        return self._items

    def add(self, key: str, value: Any) -> CacheListProperty:
        key: str = str(key)

        if self.unique and key in self._items:
            raise CacheUniqueViolation

        self._items[key] = value

        return self

    def __getitem__(self, key: str) -> Any:
        key = str(key)

        return self._items[key]

    def get(self, key: str, fallback: Any = None) -> Any:
        try:
            return self.__getitem__(key)
        except KeyError:
            return fallback


class CacheListProperty(CacheProperty):
    """Cache List Property with Optional "unique" toggle"""

    def __init__(
        self,
        unique: bool = False,
        ttl: int = 0,
        blacklist: Iterable = [],
        limit: int = 0,
    ) -> None:
        """
        Usage
        -----
        >>> cache = Cache().add(cls=CacheListProperty, unique=True).append(0, ">")
        >>> cache.prefix.append(1, ">")
        >>> cache.prefix.append(0, ">")
        Traceback (most recent call last):
          File ".../cache.py", line 126, in <module>
            cache.prefix.append(0, ">")
          File ".../cache.py", line 97, in add
            raise CacheUniqueViolation
        __main__.CacheUniqueViolation: Unique Value Violation
        ...
        """
        super().__init__(unique=unique, ttl=ttl)
        self.blacklist: Iterable = blacklist
        self.limit: int = limit

    def add(self, key: str, value: Any) -> CacheListProperty:
        # TODO: Move Iterable handler to `extend()` function
        key: str = str(key)
        items = self._items.get(key, [])

        if not isinstance(value, int) and not value:
            self._items[key] = []
            raise ValueError("value can't be empty")

        if (
            self.limit
            and len(items)
            + (1 if isinstance(value, str) or isinstance(value, int) else len(value))
            > self.limit
        ):
            raise CacheListFull

        if self.unique:
            if isinstance(value, Iterable) and not isinstance(value, str):
                value = [
                    v for v in set(value) if v not in items or v not in self.blacklist
                ]
                if not value:
                    raise CacheUniqueViolation
            else:
                if value in items:
                    raise CacheUniqueViolation

        if value in self.blacklist:
            raise CacheError(f"'{value}' is blacklisted")

        try:
            if isinstance(value, Iterable) and not isinstance(value, str):
                self._items[key].extend(value)
            else:
                self._items[key].append(value)
        except KeyError:
            self._items[key] = (
                [value]
                if isinstance(value, str) or isinstance(value, int)
                else list(value)
            )

        return self

    # Alias add as append
    append = add

    def remove(self, key: str, value: Any) -> CacheListProperty:
        key: str = str(key)
        items = self._items.get(key, [])

        if not items:
            raise IndexError("List is empty!")

        try:
            self._items[key].remove(value)
        except ValueError:
            raise ValueError(f"'{value}' not in the list")

        return self


class Cache:
    """Cache manager"""

    def __init__(self):
        self._property: List[str] = list()

    @property
    def property(self) -> List:
        return self._property

    def __repr__(self) -> str:
        return "<Properties: {}>".format(set(self._property))

    def add(self, name: str, *, cls: Any = CacheProperty, **kwargs) -> CacheProperty:
        name = str(name)

        self._property.append(name)
        setattr(self, name, cls(**kwargs))
        return getattr(self, name)


if __name__ == "__main__":
    cache = Cache()
    cache.add("prefix", cls=CacheListProperty, unique=True, limit=15).add(0, 0)
    # for i in range(16):
    cache.prefix.remove(0, ">")
    # cache.add("test", unique=True).add(0, "test").add(1, "test")
    print(cache.prefix)
    # print(cache.prefix.get(0))
    # cache.prefix.append(0, ">")
