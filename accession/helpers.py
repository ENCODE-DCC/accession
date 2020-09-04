import os
import tempfile
from collections import OrderedDict
from contextlib import contextmanager
from typing import Any, Generic, List, Optional, TypeVar

K = TypeVar("K")
V = TypeVar("V")


class LruCache(Generic[K, V]):
    """
    Helper class implementing a LRU cache using an `OrderedDict`. The Generic class it
    inherits from is purely for type checking. `K` is the type variable for the key,
    and `V` is the type variable for the value. If you try to insert mixed types, mypy
    will complain.
    """

    def __init__(self, max_size: int = 128):
        """
        `max_size` is an upper bound on the maximum size of the cache. When the cache is
        at this size, insertions will result in eviction of the oldest values in the
        cache.
        """
        self.max_size = max_size
        self.data: OrderedDict[K, V] = OrderedDict()

    def get(self, key: K) -> Optional[V]:
        """
        Get the value in the cache corresponding to the the key. Has the side effect of
        moving the key to the end of the cache to indicate it was recently used.
        """
        value = self.data.get(key)
        if value is not None:
            self.data.move_to_end(key)
        return value

    def insert(self, key: K, value: V) -> None:
        """
        Add an item to the cache. If the cache is at capacity then the oldest value will
        be cleared from the cache. If the key is already in the cache, the the value
        will be updated with the new value, and the item will moved to the end.
        """
        if len(self.data) == self.max_size:
            self.data.popitem(last=False)
        self.data[key] = value

    def invalidate(self, key: K) -> None:
        """
        Delete a given key from the cache. Not currently used in the production code
        but could be useful in the future, so will keep for now.
        """
        if key in self.data.keys():
            del self.data[key]


def string_to_number(string: str):
    if not isinstance(string, str):
        return string
    try:
        return int(string)
    except Exception:
        try:
            return float(string)
        except Exception:
            return string


def flatten(nested_input: List[Any]):
    """Flattens a nested list.
    Args:
        input_list: A (possibly) nested list.
    Returns:
        A flattened list, preserving order.
    """

    if not nested_input:
        return []
    if isinstance(nested_input[0], list):
        return flatten(nested_input[0]) + flatten(nested_input[1:])
    else:
        return nested_input[:1] + flatten(nested_input[1:])


@contextmanager
def impersonate_file(data):
    """With this contextmanager one can use bytes or string as if it is a file.
    Usage:
        with impersonate_file(bytes_data) as filepath:
            function_expecting_file(filepath)
    """
    temporary_file = tempfile.NamedTemporaryFile(delete=False)
    temporary_file.write(data)
    temporary_file.close()
    try:
        yield temporary_file.name
    finally:
        os.unlink(temporary_file.name)
