import pytest

from accession.file import GSFile
from accession.task import Task


@pytest.mark.filesystem
def test_gcfile_init(metadata_json, normal_analysis):
    task = metadata_json["calls"]["atac.bam2ta"][0]
    new_task = Task("bam2ta", task)
    filekey = "ta"
    filename = new_task.outputs[filekey]
    new_file = GSFile(filekey, filename, "123", "345", new_task)
    assert new_file.filename == filename
    assert filekey in new_file.filekeys
    assert new_file.task is new_task
    assert new_file.SCHEME == "gs://"
