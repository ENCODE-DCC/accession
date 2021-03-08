from abc import ABC, abstractmethod
from typing import Optional

from google.cloud import storage

from accession.file import File, GSFile, LocalFile
from accession.task import Task


class Backend(ABC):
    """
    The backends are very minimal, mostly just creating instances of the appropriate
    `File` subclass.
    """

    @property
    @abstractmethod
    def CAPER_NAME(self) -> str:
        """
        The name Caper uses to refer to the backend.
        """
        raise NotImplementedError

    @abstractmethod
    def make_file(
        self,
        key: str,
        filename: str,
        task: Optional[Task] = None,
        used_by_task: Optional[Task] = None,
    ) -> File:
        raise NotImplementedError

    @abstractmethod
    def is_valid_uri(self, uri: str) -> bool:
        raise NotImplementedError


class GCBackend(Backend):
    """
    Backend for interacting with Google Cloud Storage (GCS)
    """

    CAPER_NAME = "gcp"

    def __init__(self) -> None:
        self._client = None

    @property
    def client(self) -> storage.Client:
        if self._client is None:
            self._client = storage.Client()
        return self._client

    def make_file(
        self,
        key: str,
        filename: str,
        task: Optional[Task] = None,
        used_by_task: Optional[Task] = None,
    ) -> GSFile:
        blob = GSFile(
            key=key,
            name=filename,
            task=task,
            used_by_task=used_by_task,
            client=self.client,
        )
        return blob

    def is_valid_uri(self, uri: str) -> bool:
        return uri.startswith(GSFile.SCHEME)


class LocalBackend(Backend):
    """
    Backend that creates instances of LocalFile for accessioning local workflows.
    """

    # For some reason local backend name is capitalized in Cromwell `Local`
    CAPER_NAME = "Local"

    def make_file(
        self,
        key: str,
        filename: str,
        task: Optional[Task] = None,
        used_by_task: Optional[Task] = None,
    ) -> LocalFile:
        blob = LocalFile(key=key, name=filename, task=task, used_by_task=used_by_task)
        return blob

    def is_valid_uri(self, uri: str) -> bool:
        """
        There is not a way to distinguish between String and File types from metadata
        alone for local files.
        """
        return True


def backend_factory(backend_name: str) -> Backend:
    if backend_name == LocalBackend.CAPER_NAME:
        return LocalBackend()
    elif backend_name == GCBackend.CAPER_NAME:
        return GCBackend()
    elif backend_name == "sge":
        return LocalBackend()
    else:
        raise ValueError(f"Backend {backend_name} is not supported")
