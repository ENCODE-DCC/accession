import json
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, Optional, Union

from accession.caper_helper import CaperHelper, caper_conf_exists


class Metadata(ABC):
    @property
    @abstractmethod
    def content(self):
        raise NotImplementedError


class FileMetadata(Metadata):
    def __init__(self, metadata_filepath: Union[str, Path]) -> None:
        self._metadata_filepath = metadata_filepath
        self._content: Optional[Dict[str, Any]] = None

    @property
    def content(self) -> Dict[str, Any]:
        if self._content is None:
            with open(self._metadata_filepath) as fp:
                self._content = json.load(fp)
        return self._content


class CaperMetadata(Metadata):
    def __init__(self, workflow_id_or_label: str) -> None:
        self.workflow_id_or_label = workflow_id_or_label
        self.caper_helper = CaperHelper()
        self._content: Optional[Dict[str, Any]] = None

    @property
    def content(self) -> Dict[str, Any]:
        if self._content is None:
            metadata = self.caper_helper.metadata([self.workflow_id_or_label])
            if len(metadata) != 1:
                raise ValueError("Expected one metadata JSON to be returned")
            self._content = metadata[0]
        return self._content


def metadata_factory(path_or_caper_id: str) -> Metadata:
    """
    Generates instance of FileMetadata or CaperMetadata. First assumes the input is a
    file path, if that doesn't exist it falls back to assuming it is a Caper ID or
    label if the Caper conf file exists. Raises if the metadata could not be interpreted
    as a file and the Caper conf is not present.
    """
    metadata_path = Path(path_or_caper_id)
    if metadata_path.exists():
        return FileMetadata(metadata_path)
    if caper_conf_exists():
        return CaperMetadata(path_or_caper_id)
    raise ValueError("Could not initialize metadata")
