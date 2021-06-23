import os
import tempfile
from abc import ABC, abstractmethod
from collections import OrderedDict
from contextlib import contextmanager
from typing import Any, Dict, Generic, Iterator, List, Optional, Tuple, TypeVar, Union

from encode_utils.connection import Connection

from accession.database.connection import DbSession
from accession.database.models import Run

K = TypeVar("K")
V = TypeVar("V")
T = TypeVar("T")
U = TypeVar("U", bound="PreferredDefaultFilePatch")


class LruCache(Generic[K, V]):
    """
    Helper class implementing a LRU cache using an `OrderedDict`. The Generic class it
    inherits from is purely for type checking. `K` is the type variable for the key,
    and `V` is the type variable for the value. If you try to insert mixed types, mypy
    will complain.
    """

    def __init__(self, max_size: int = 128) -> None:
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


class PreferredDefaultFilePatch:
    PROFILE_KEY = "file"

    def __init__(self, at_id: str, qc_value: Union[int, float]) -> None:
        self.at_id = at_id
        self.qc_value = qc_value

    def __eq__(self, other: "U") -> bool:  # type: ignore[override]
        return all((self.at_id == other.at_id, self.qc_value == other.qc_value))

    def get_portal_patch(self) -> Dict[str, Union[str, bool]]:
        return {
            "preferred_default": True,
            Connection.PROFILE_KEY: self.PROFILE_KEY,
            Connection.ENCID_KEY: self.at_id,
        }


class AbstractRecorder(ABC):
    @abstractmethod
    def record(self, run: Run) -> None:
        raise NotImplementedError


class Recorder(AbstractRecorder):
    def __init__(self, use_in_memory_db: bool = False) -> None:
        if use_in_memory_db:
            self.db_session = DbSession.with_in_memory_db()
        else:
            self.db_session = DbSession.with_home_dir_db_path()

    def record(self, run: Run) -> None:
        self.db_session.session.add(run)
        self.db_session.session.commit()


def string_to_number(string: str) -> Union[float, str, int]:
    if not isinstance(string, str):
        return string
    try:
        return int(string)
    except Exception:
        try:
            return float(string)
        except Exception:
            return string


def flatten(nested_input: List[Any]) -> List[Any]:
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
def impersonate_file(data: bytes) -> Iterator[str]:
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


def get_api_keys_from_env() -> Tuple[str, str]:
    """
    Extracted from encode_utils.connection.Connection
    """
    api_key = os.environ["DCC_API_KEY"]
    secret_key = os.environ["DCC_SECRET_KEY"]
    return api_key, secret_key


def get_bucket_and_key_from_s3_uri(s3_uri: str) -> Tuple[str, str]:
    path_parts = s3_uri.replace("s3://", "").split("/")
    bucket = path_parts.pop(0)
    key = "/".join(path_parts)
    return bucket, key
