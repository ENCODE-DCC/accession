from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:
    # Needed to avoid circular import at runtime
    # https://mypy.readthedocs.io/en/stable/common_issues.html#import-cycles
    from accession.file import File


class Task:
    """
    The dockerImageUsed key in the task metadata can sometimes be missing if there was a cache hit.
    In that event, the dockerImage will fail back to the docker key in the task runtimeAttributes.
    The RHS of the or statement will guarantee a KeyError if no docker image is found.  Unlike
    dockerImageUsedThis key does not include the image SHA, but rather the image tag. See
    https://github.com/broadinstitute/cromwell/issues/4001
    """

    def __init__(self, task_name: str, task: Dict[str, Any]) -> None:
        self.task_name = task_name
        self.input_files: List[File] = []
        self.output_files: List[File] = []
        self.inputs: Dict[str, Any] = task["inputs"]
        self.outputs: Dict[str, Any] = task["outputs"]
        self.docker_image: Optional[str] = task.get("dockerImageUsed") or task.get(
            "runtimeAttributes", {}
        ).get("docker")
