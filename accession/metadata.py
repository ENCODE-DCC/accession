import json
import re
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, TextIO, Union

import WDL
from caper.caper_labels import CaperLabels

from accession.caper_helper import CaperHelper, caper_conf_exists
from accession.encode_models import EncodeAttachment


class MetadataPreprocessor(ABC):
    @abstractmethod
    def process(self, metadata: Dict[str, Any]) -> Dict[str, Any]:
        raise NotImplementedError


class Metadata(ABC):
    UNNECESSARY_WORKFLOW_LABELS = (
        "caper-backend",
        "caper-user",
        "cromwell-workflow-id",
    )

    @abstractmethod
    def __init__(
        self, preprocessors: Optional[Iterable[MetadataPreprocessor]] = None
    ) -> None:
        self._original_content: Optional[Dict[str, Any]] = None
        self._content: Optional[Dict[str, Any]] = None
        self._preprocessors = preprocessors

    @property
    @abstractmethod
    def original_content(self) -> Dict[str, Any]:
        raise NotImplementedError

    @property
    def workflow_id(self) -> str:
        return self.content["id"]

    @property
    def backend_name(self) -> str:
        return self.labels[CaperLabels.KEY_CAPER_BACKEND]

    @property
    def labels(self) -> Dict[str, str]:
        return self.content["labels"]

    @property
    def content(self) -> Dict[str, Any]:
        if self._content is None:
            content = self.original_content
            if self._preprocessors is not None:
                for preprocessor in self._preprocessors:
                    new_content = preprocessor.process(content)
                    content = new_content
            self._content = content
        return self._content

    @property
    def workflow(self) -> str:
        return self.content["submittedFiles"]["workflow"]

    def get_filename(self, prefix: str = "") -> str:
        """
        Construct an artificial filename for the metadata JSON. We do this because it
        could be possible in the future that the metadata is not actually in a file, for
        instance if we pull them directly from Caper.
        """
        delimited_prefix = f"{prefix}_" if prefix else ""
        return f"{delimited_prefix}{self.workflow_id}_metadata.json"

    def get_as_attachment(self, filename_prefix: str = "") -> EncodeAttachment:
        """
        Get the representation of the attachment on the portal
        """
        metadata_bytes = EncodeAttachment.get_bytes_from_dict(self.original_content)
        attachment = EncodeAttachment(
            metadata_bytes,
            self.get_filename(prefix=filename_prefix),
            mime_type="application/json",
        )
        return attachment

    def get_parsed_workflow(self) -> WDL.Tree.Document:
        return WDL.parse_document(self.workflow)

    def get_pipeline_version_using_regex(self) -> str:
        match = re.search(r"version: \"(?P<version>\d+.\d+.\d+)", self.workflow)
        if match is None:
            raise ValueError("Couldn't determine pipeline version via regex")
        return match.group("version")

    def get_filtered_labels(self) -> Dict[str, str]:
        """
        Filters out labels that are either fairly constant, irrelevant, or redundant.
        """
        return {
            k: v
            for k, v in self.labels.items()
            if k not in self.UNNECESSARY_WORKFLOW_LABELS
        }


class FileMetadata(Metadata):
    def __init__(
        self,
        metadata_filepath: Union[str, Path],
        preprocessors: Optional[Iterable[MetadataPreprocessor]] = None,
    ) -> None:
        self._metadata_filepath = metadata_filepath
        super().__init__(preprocessors=preprocessors)

    @property
    def original_content(self) -> Dict[str, Any]:
        if self._content is None:
            with open(self._metadata_filepath) as fp:
                self._content = json.load(fp)
        return self._content


class CaperMetadata(Metadata):
    def __init__(
        self,
        workflow_id_or_label: str,
        preprocessors: Optional[Iterable[MetadataPreprocessor]] = None,
    ) -> None:
        self.workflow_id_or_label = workflow_id_or_label
        self.caper_helper = CaperHelper()
        super().__init__(preprocessors=preprocessors)

    @property
    def original_content(self) -> Dict[str, Any]:
        if self._content is None:
            metadata = self.caper_helper.metadata([self.workflow_id_or_label])
            if len(metadata) != 1:
                raise ValueError("Expected one metadata JSON to be returned")
            self._content = metadata[0]
        return self._content


def metadata_factory(
    path_or_caper_id: str,
    preprocessors: Optional[Iterable[MetadataPreprocessor]] = None,
) -> Metadata:
    """
    Generates instance of FileMetadata or CaperMetadata. First assumes the input is a
    file path, if that doesn't exist it falls back to assuming it is a Caper ID or
    label if the Caper conf file exists. Raises if the metadata could not be interpreted
    as a file and the Caper conf is not present.
    """
    metadata_path = Path(path_or_caper_id)
    if metadata_path.exists():
        return FileMetadata(metadata_path, preprocessors=preprocessors)
    if caper_conf_exists():
        return CaperMetadata(path_or_caper_id, preprocessors=preprocessors)
    raise ValueError("Could not initialize metadata")


def parse_metadata_list(metadata_list_fp: TextIO) -> List[str]:
    """
    Parsed the given list of metadata paths/Caper IDs. Caper labels cannot have spaces
    so we assume that multiple entries present on a line is an error. Empty lines are
    skipped.
    """
    parsed = []
    for i, line in enumerate(metadata_list_fp):
        split = line.strip().split()
        if len(split) > 1:
            raise ValueError(
                f"Invalid metadata list, found multiple entries in line {i + 1}"
            )
        if len(split) == 0:
            continue
        parsed.append(split[0])
    if not parsed:
        raise ValueError("Metadata list is empty")
    return parsed
