import json
from base64 import b64encode
from collections import UserDict
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple, TypeVar, Union

from encode_utils.connection import Connection

from accession.accession_steps import FileParams

T = TypeVar("T")
U = TypeVar("U")
V = TypeVar("V", bound="EncodeFile")


class EncodeGenericObject:
    def __init__(self, portal_properties: Dict[str, Any]) -> None:
        self.portal_properties = portal_properties

    @property
    def at_id(self) -> str:
        return self.portal_properties["@id"]


class EncodeCommonMetadata(UserDict):
    """
    Class to hold common metadata shared by all posted objects. Inherits from UserDict
    so we can do things like qc.update(EncodeCommonMetadata("foo", "bar"))
    """

    def __init__(self, lab: str, award: str):
        self.data = {"lab": lab, "award": award}

    @property
    def lab(self) -> str:
        return self.data["lab"]

    @property
    def award(self) -> str:
        return self.data["award"]

    @property
    def lab_pi(self) -> str:
        return self.lab.split("/labs/")[1].split("/")[0]


class EncodeFile:
    """
    A subset of file properties is made available via @property, for convenience
    """

    ASSEMBLY = "assembly"
    GENOME_ANNOTATION = "genome_annotation"

    def __init__(self, portal_file: Dict[str, Any]):
        self._portal_file = portal_file
        self.at_id = portal_file["@id"]

    def __eq__(self, other):  # noqa: E821 # type: ignore[override]
        """
        Helpful for pytest assertions. See https://github.com/python/mypy/issues/2783
        for rationale for ignoring type.
        """
        if type(self) != type(other):
            return False
        return self.at_id == other.at_id and self.portal_file == other.portal_file

    def __str__(self):
        return self.at_id

    @property
    def portal_file(self) -> Dict[str, Any]:
        return self._portal_file

    @portal_file.setter
    def portal_file(self, value) -> None:
        new_id = value["@id"]
        if new_id != self.at_id:
            raise ValueError(
                f"Cannot update file properties, expected object with an @id of {self.at_id} but received {new_id}"
            )
        self._portal_file = value

    @property
    def accession(self) -> str:
        return self.at_id.split("/")[-2]

    @property
    def output_type(self) -> str:
        return self.portal_file["output_type"]

    @property
    def status(self) -> str:
        return self.portal_file["status"]

    @property
    def dataset(self) -> str:
        return self.portal_file["dataset"]

    @property
    def md5sum(self) -> str:
        return self.portal_file["md5sum"]

    def get(
        self, key: str, default: Optional[U] = None
    ) -> Union[Optional[T], Union[T, U]]:
        """
        Type signature here is complicated. Here we want to emulate behaviour of normal
        .get on a dict. If no default is proved, then will return an object of type T
        or None, while if a default of type U is provided, then the get will either
        return an object of type T or the default.
        """
        return self.portal_file.get(key, default)

    @property
    def step_run_id(self) -> str:
        step_run = self.portal_file.get("step_run")
        if step_run is None:
            raise ValueError(f"Could not find step run for file {self.at_id}")
        if isinstance(step_run, str):
            step_run_id = step_run
        elif isinstance(step_run, dict):
            step_run_id = step_run["@id"]
        return step_run_id

    def has_qc(self, qc_type: str) -> bool:
        """
        Checks if the portal file has a qc with the given @type, e.g. StarQualityMetric
        """
        if list(
            filter(lambda x: qc_type in x["@type"], self.portal_file["quality_metrics"])
        ):
            return True
        return False

    @staticmethod
    def filter_encode_files_by_status(
        encode_files: List[V],
        forbidden_statuses: Tuple[str, ...] = ("replaced", "revoked", "deleted"),
    ) -> List[V]:
        """
        Filter out files whose statuses are not allowed. From list of EncodeFile
        instances representing encode file objects, filter out ones whose statuses are
        not allowed.

        Args:
            encode_files (list): List containing dicts representing encode file objects.
            forbidden_statuses (list): List of statuses. If file object has one of these statuses it will be filtered out.
            Statuses that encode file can have are: uploading, upload failed, in progress, released, archived, deleted, replaced,
            revoked, content error.

        Returns:
            list: List containing the EncodeFiles whose statuses are not contained in forbidden_statuses, empty list is possible.

        Raises:
            KeyError: If some of the files do not have status (this is an indication of an error on portal).
        """
        filtered_files = [
            file for file in encode_files if file.status not in forbidden_statuses
        ]
        return filtered_files

    @staticmethod
    def from_template(
        aliases: List[str],
        assembly: str,
        common_metadata: EncodeCommonMetadata,
        dataset: str,
        derived_from: List[str],
        file_params: FileParams,
        file_size: str,
        file_md5sum: str,
        step_run_id: str,
        submitted_file_name: str,
        genome_annotation: Optional[str] = None,
        extras: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Note that extras are used to update the dictionary at the very end. This allows
        for callbacks to override properties like output_type that may have been
        specified in the template.
        """
        obj = {
            "status": "uploading",
            "aliases": aliases,
            "file_format": file_params.file_format,
            "output_type": file_params.output_type,
            "assembly": assembly,
            "dataset": dataset,
            "step_run": step_run_id,
            "derived_from": derived_from,
            "file_size": file_size,
            "md5sum": file_md5sum,
            "submitted_file_name": submitted_file_name,
        }
        if file_params.file_format_type:
            obj["file_format_type"] = file_params.file_format_type
        if genome_annotation is not None:
            obj["genome_annotation"] = genome_annotation
        if extras is not None:
            obj.update(extras)
        obj[Connection.PROFILE_KEY] = "file"
        obj.update(common_metadata)
        return obj


class EncodeAnalysis:
    """
    Class representing a nascent Analysis object. Not intended to be used to represent
    existing analyses.
    """

    PROFILE = "analysis"

    def __init__(
        self,
        files: List[EncodeFile],
        documents: List[EncodeGenericObject],
        lab_pi: str,
        workflow_id: str,
        pipeline_version: Optional[str] = None,
    ) -> None:
        """
        `documents` is a list of `EncodeGenericObject` that gives no access to the
        document internals except for the `@id`.
        """
        self.files = files
        self.aliases = self.get_aliases(lab_pi, workflow_id)
        self.documents = documents
        self.pipeline_version = pipeline_version

    def __eq__(
        self, other
    ) -> bool:  # type: ignore  # https://github.com/python/mypy/issues/2783
        """
        Helpful for pytest assertions. Should use # type: ignore[override], but flake8
        gets confused by that, raises F821.
        """
        if type(self) != type(other):
            return False
        return sorted([f.at_id for f in self.files]) == sorted(
            [f.at_id for f in other.files]
        )

    def __str__(self) -> str:
        return str([str(f) for f in self.files])

    @staticmethod
    def get_aliases(lab: str, workflow_id: str) -> List[str]:
        return [f"{lab}:{workflow_id}"]

    def get_portal_object(self) -> Dict[str, Any]:
        """
        Obtain the portal-postable dict representation of the analysis.
        """
        if self.files is None:
            raise ValueError("Cannot create payload for analysis without files")
        payload = {
            Connection.PROFILE_KEY: self.PROFILE,
            "aliases": self.aliases,
            "documents": [d.at_id for d in self.documents],
            "files": [f.at_id for f in self.files],
        }
        if self.pipeline_version is not None:
            payload["pipeline_version"] = self.pipeline_version
        return payload


class EncodeExperiment:
    INTERNAL_STATUS_KEY = "internal_status"
    INTERNAL_STATUS_POST_ACCESSIONING = "pipeline completed"

    def __init__(self, portal_experiment: Dict[str, Any]):
        self.at_id = portal_experiment["@id"]
        self.portal_properties = portal_experiment

    @property
    def assay_term_name(self) -> str:
        return self.portal_properties["assay_term_name"]

    @property
    def is_replicated(self):
        return self.get_number_of_biological_replicates() > 1

    @property
    def accession(self) -> str:
        return self.at_id.split("/")[-2]

    def get_number_of_biological_replicates(self) -> int:
        bio_reps = set(
            [
                rep.get("biological_replicate_number")
                for rep in self.portal_properties["replicates"]
            ]
        )
        return len([rep for rep in bio_reps if rep is not None])

    def get_number_of_technical_replicates(self) -> int:
        tech_reps = set(
            [
                rep.get("technical_replicate_number")
                for rep in self.portal_properties["replicates"]
            ]
        )
        return len([rep for rep in tech_reps if rep is not None])

    def get_patchable_internal_status(self):
        return {
            self.INTERNAL_STATUS_KEY: self.INTERNAL_STATUS_POST_ACCESSIONING,
            Connection.ENCID_KEY: self.at_id,
        }

    def get_patchable_analysis_object(
        self, analysis_object_at_id: str
    ) -> Dict[str, Union[str, List[str]]]:
        return {
            "analysis_objects": [analysis_object_at_id],
            Connection.ENCID_KEY: self.at_id,
            Connection.PROFILE_KEY: "experiment",
        }


class EncodeAttachment:
    def __init__(
        self,
        contents: bytes,
        filename: str,
        mime_type: Optional[str] = None,
        additional_extension: Optional[str] = None,
    ):
        """
        Filename is not technically required, but if you don't specify the attachment
        will say "file not available" when you view it on the portal, so we require one
        here.
        """
        self.contents = contents
        self.filename = filename
        self.mime_type = mime_type
        self.additional_extension = additional_extension

    @staticmethod
    def encode_attachment_data(data: bytes) -> str:
        """
        Encodes the attachment data into a b64 datastring
        input: data as bytes object
        Output: data as string, encoded as b64
        """
        return b64encode(data).decode("utf-8")

    @staticmethod
    def get_bytes_from_dict(input_dict: Dict, encoding: str = "utf-8") -> bytes:
        """
        Useful for encoding QC JSON files into bytes for posting as attachments
        """
        return json.dumps(input_dict).encode(encoding)

    def make_download_link(self, additional_extension: str) -> str:
        return self.filename.split("/")[-1] + additional_extension

    def get_portal_object(
        self, mime_type: Optional[str] = None, additional_extension: str = ""
    ) -> Dict[str, str]:
        """
        Obtain the postable representation of the attachment. If `mime_type` or
        `extension` are specified here they will override any values specified during
        instantiation. `extension` is a string that will be appended to the download
        link to trick the mime validation code in certain cases.
        """
        if mime_type is None:
            if self.mime_type is None:
                raise ValueError("Must specify mime type for attachment via __init__")
            mime_type = self.mime_type
        if self.additional_extension is not None:
            additional_extension = self.additional_extension
        attachment_object = {
            "type": mime_type,
            "download": self.make_download_link(additional_extension),
            "href": "data:{};base64,{}".format(
                mime_type, self.encode_attachment_data(self.contents)
            ),
        }
        return attachment_object


class EncodeQualityMetric:
    def __init__(self, payload: Dict[str, Any], file_id: str):
        if not file_id:
            raise ValueError(
                "No file_id specified, QC metric needs an accessioned file"
            )
        self.files = [file_id]
        self.payload = payload

    def get_portal_object(self) -> Dict[str, Any]:
        self.payload.update({"status": "in progress", "quality_metric_of": self.files})
        return self.payload


class EncodeStepRun:
    def __init__(self, portal_step_run: Dict[str, Any]):
        self.at_id = portal_step_run["@id"]
        self.portal_step_run = portal_step_run


class EncodeDocumentType(Enum):
    WorkflowMetadata = "workflow metadata"


class EncodeDocument:
    PROFILE = "document"

    def __init__(
        self,
        attachment: EncodeAttachment,
        common_metadata: EncodeCommonMetadata,
        document_type: EncodeDocumentType,
        aliases: Optional[List[str]] = None,
    ) -> None:
        """
        Instatiates a document from the appropriate metadata. Note that document_type is
        a member of an enum, see `EncodeDocumentType` for possible variants.
        """
        self.attachment = attachment
        self.common_metadata = common_metadata
        self.document_type = document_type
        self.aliases = aliases

    def get_portal_object(self) -> Dict[str, Any]:
        attachment = self.attachment.get_portal_object()
        payload = {
            Connection.PROFILE_KEY: self.PROFILE,
            "document_type": self.document_type.value,
            "attachment": attachment,
        }
        payload.update(self.common_metadata)
        if self.aliases is not None:
            payload["aliases"] = self.aliases
        return payload
