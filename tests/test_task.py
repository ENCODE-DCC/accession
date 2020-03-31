import pytest

from accession.task import Task


@pytest.mark.filesystem
def test_task_init(metadata_json):  # noqa: F811
    task = metadata_json["calls"]["atac.bam2ta"][0]
    new_task = Task("bam2ta", task)
    assert new_task.inputs == task["inputs"]
    assert new_task.outputs == task["outputs"]
    assert new_task.task_name == "bam2ta"
    assert new_task.docker_image == task["dockerImageUsed"]
