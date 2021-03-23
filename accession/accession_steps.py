import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Union


class AccessionStep:
    """
    Model of a step performed during accessioning. Corresponds to a single step in the
    accession steps json's accession.steps array.
    """

    def __init__(self, step_params: Dict[str, Any]):
        self.step_run: str = step_params["dcc_step_run"]
        self.step_version: str = step_params["dcc_step_version"]
        self.wdl_task_name: str = step_params["wdl_task_name"]
        self.requires_replication: bool = step_params.get("requires_replication", False)
        self.wdl_files: List[FileParams] = [
            FileParams(i) for i in step_params["wdl_files"]
        ]


class AccessionSteps:
    def __init__(self, path_to_accession_step_json: Union[str, Path]):
        self.path = path_to_accession_step_json
        self._steps: Optional[Dict[str, Any]] = None
        self._content: Optional[List[AccessionStep]] = None

    @property
    def steps(self) -> Dict[str, Any]:
        """
        Corresponds to the entire accession steps JSON, not just the accession.steps
        """
        if self._steps is None:
            with open(self.path) as fp:
                self._steps = json.load(fp)
        return self._steps

    @property
    def content(self) -> List[AccessionStep]:
        if self._content is None:
            new_content = []
            for step in self.steps["accession.steps"]:
                new_content.append(AccessionStep(step))
            self._content = new_content
        return self._content

    @property
    def raw_fastqs_keys(self) -> Optional[List[str]]:
        return self.steps.get("raw_fastqs_keys")

    @property
    def raw_fastqs_can_have_task(self) -> bool:
        return self.steps.get("raw_fastqs_can_have_task", False)


class DerivedFromFile:
    def __init__(self, derived_from_file: Dict[str, Any]) -> None:
        """
        Use `"search_down": true` to search down the task heirarchy for derived_from
        files. This is used by ATAC, where we need the filtered bam to be derived from
        the reference annotation files, but they aren't anywhere upstream of the bam.

        `workflow_inputs_to_match` can be used to indicate that only files with
        filenames matching the workflow input keys given should be considered.

        `only_search_current_analysis` will only consider direct ancestors in the WDL
        call graph when generating the `derived_from`
        """
        self.allow_empty: bool = derived_from_file.get("allow_empty", False)
        self.derived_from_filekey: str = derived_from_file["derived_from_filekey"]
        self.derived_from_inputs: bool = derived_from_file.get(
            "derived_from_inputs", False
        )
        self.derived_from_task: str = derived_from_file["derived_from_task"]
        self.derived_from_output_type: Optional[str] = derived_from_file.get(
            "derived_from_output_type"
        )
        self.disallow_tasks: List[str] = derived_from_file.get("disallow_tasks", [])
        self.should_search_down: bool = derived_from_file.get(
            "should_search_down", False
        )
        workflow_inputs_to_match = derived_from_file.get("workflow_inputs_to_match", [])
        if not isinstance(workflow_inputs_to_match, list):
            raise ValueError("`workflow_inputs_to_match` must be an array")
        self.workflow_inputs_to_match: List[str] = workflow_inputs_to_match
        self.only_search_current_analysis: bool = derived_from_file.get(
            "only_search_current_analysis", False
        )


class FileParams:
    """
    Represents the spec for the file to accession as defined in the template
    """

    def __init__(self, file_params: Dict[str, Any]):
        self.filekey: str = file_params["filekey"]
        self.file_format: str = file_params["file_format"]
        self.output_type: str = file_params["output_type"]
        self.derived_from_files: List[DerivedFromFile] = [
            DerivedFromFile(i) for i in file_params["derived_from_files"]
        ]
        self.file_format_type: Optional[str] = file_params.get("file_format_type")
        self.callbacks: List[str] = file_params.get("callbacks", [])
        self.quality_metrics: List[str] = file_params.get("quality_metrics", [])
        self.maybe_preferred_default = file_params.get("maybe_preferred_default", False)
