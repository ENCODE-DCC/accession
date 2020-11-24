import hashlib
import json
from abc import ABC, abstractmethod
from base64 import b64decode
from pathlib import Path
from typing import Any, Dict, Optional

from google.cloud.storage.blob import Blob
from google.cloud.storage.client import Client

from accession.task import Task


class File(ABC):
    """
    Abstract base class defining the interface for different concrete file classes to
    implement.
    """

    @abstractmethod
    def __init__(
        self,
        key: str,
        name: str,
        task: Optional[Task] = None,
        used_by_task: Optional[Task] = None,
    ) -> None:
        self.filename = name
        self.filekeys = [key]
        self.task = task
        self.used_by_tasks = [used_by_task] if used_by_task else []

    @property
    @abstractmethod
    def md5sum(self) -> str:
        raise NotImplementedError

    @property
    @abstractmethod
    def size(self) -> int:
        raise NotImplementedError

    @abstractmethod
    def get_uri_without_scheme(self) -> str:
        """
        String representing the scheme for URIs for files represented by the class.
        """
        raise NotImplementedError("Derived classes should provide their own SCHEMEs")

    @abstractmethod
    def read(self, num_bytes: Optional[int] = None) -> bytes:
        raise NotImplementedError

    @abstractmethod
    def read_bytes(self) -> bytes:
        raise NotImplementedError

    @abstractmethod
    def read_json(self) -> Dict[str, Any]:
        raise NotImplementedError

    def get_task(self) -> Task:
        """
        Either gets the `File`'s task or raises a ValueError.
        """
        task = self.task
        if task is None:
            raise ValueError("No task found")
        return task

    def get_filename_for_encode_alias(self) -> str:
        return self.get_uri_without_scheme().replace("/", "-")


class GSFile(File):
    """
    Wrapper around GCS blob class to better map to portal metadata and provide a read()
    interface for in-memory transfer to s3
    """

    SCHEME = "gs://"

    def __init__(
        self,
        key: str,
        name: str,
        task: Optional[Task] = None,
        used_by_task: Optional[Task] = None,
        client: Optional[Client] = None,
    ) -> None:
        """
        Initializes self.pos to 0 for keeping track of number of bytes read from file.
        """
        super().__init__(key, name, task, used_by_task)
        self.pos = 0
        self._blob: Optional[Blob] = None
        self._client: Optional[Client] = client

    @property
    def blob(self) -> Blob:
        if self._blob is None:
            blob = Blob.from_string(self.filename, client=self.client)
            blob.reload()
            self._blob = blob
        return self._blob

    @property
    def client(self) -> Client:
        if self._client is None:
            client = Client()
            self._client = client
        return self._client

    @property
    def md5sum(self) -> str:
        """
        Returns md5sum of the file in hex. Need to wrap around gcloud API's md5sums,
        which are returned as base64, to match ENCODE portal md5sums.
        """
        return self.b64_to_hex(self.blob.md5_hash)

    @property
    def size(self) -> int:
        return self.blob.size

    @staticmethod
    def b64_to_hex(value: str) -> str:
        return b64decode(value).hex()

    def get_uri_without_scheme(self) -> str:
        return f"{self.blob.bucket.name}/{self.blob.name}"

    def read(self, num_bytes: Optional[int] = None) -> bytes:
        """
        `Blob.download_as_string()` takes `start` and `end` kwargs to specify a byte
        range. These are 0-indexed and inclusive of endpoints. If the position is
        greater than or equal to the size of the object then we treat that as EOF and
        return an empty byte string `b''`. As per Python convention, when read() is
        called with no read size then the remainder of the file is returned.

        See https://googleapis.dev/python/storage/latest/blobs.html#google.cloud.Blob.download_as_string
        """
        if self.pos >= self.size:
            read_bytes = b""
        else:
            if num_bytes is None:
                read_bytes = self.blob.download_as_string(start=self.pos)
                self.pos += len(read_bytes)
            else:
                read_bytes = self.blob.download_as_string(
                    start=self.pos, end=self.pos + num_bytes - 1
                )
                self.pos += num_bytes
        return read_bytes

    def read_bytes(self) -> bytes:
        """
        Downloads file as bytes. We bypass the `read` interface so we don't mess with
        `self.pos`.
        """
        return self.blob.download_as_string()

    def read_json(self) -> Dict[str, Any]:
        """
        Read file and convert to JSON
        """
        return json.loads(self.read_bytes().decode())


class LocalFile(File):
    MD5_CHUNKSIZE = 8192

    def __init__(
        self,
        key: str,
        name: str,
        task: Optional[Task] = None,
        used_by_task: Optional[Task] = None,
    ) -> None:
        """
        Initializes self.pos to 0 for keeping track of number of bytes read from file.
        """
        super().__init__(key, name, task, used_by_task)
        self.pos = 0
        self._md5sum: Optional[str] = None
        self._size: Optional[int] = None

    @property
    def md5sum(self) -> str:
        if self._md5sum is None:
            md5_hash = hashlib.md5()
            with open(self.filename, "rb") as f:
                for chunk in iter(lambda: f.read(self.MD5_CHUNKSIZE), b""):
                    md5_hash.update(chunk)
            self._md5sum = md5_hash.hexdigest()
        return self._md5sum

    @property
    def size(self) -> int:
        if self._size is None:
            self._size = Path(self.filename).stat().st_size
        return self._size

    def get_uri_without_scheme(self) -> str:
        return self.filename

    def read(self, num_bytes: Optional[int] = None) -> bytes:
        if self.pos >= self.size:
            return b""

        with open(self.filename, "rb") as f:
            f.seek(self.pos)
            if num_bytes is None:
                read_bytes = f.read()
                self.pos += len(read_bytes)
            else:
                read_bytes = f.read(num_bytes)
                self.pos += num_bytes
        return read_bytes

    def read_bytes(self) -> bytes:
        """
        Downloads file as bytes. We bypass the `read` interface so we don't mess with
        `self.pos`.
        """
        with open(self.filename, "rb") as f:
            return f.read()

    def read_json(self) -> Dict[str, Any]:
        """
        Read file and convert to JSON
        """
        return json.loads(self.read_bytes().decode())
