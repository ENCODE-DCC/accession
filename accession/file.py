from abc import ABC, abstractmethod


class File(ABC):
    def __init__(self, key, name, md5sum, size, task=None, used_by_tasks=None):
        self.filename = name
        self.filekeys = [key]
        self.task = task
        self.used_by_tasks = [used_by_tasks] if used_by_tasks else []
        self.md5sum = md5sum
        self.size = size

    @property
    @abstractmethod
    def SCHEME(self):
        """
        String representing the scheme for URIs for files represented by the class.
        """
        raise NotImplementedError("Derived classes should provide their own SCHEMEs")


class GSFile(File):
    SCHEME = "gs://"
