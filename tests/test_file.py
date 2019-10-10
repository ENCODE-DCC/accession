from accession.file import GSFile
from accession.task import Task


def test_gcfile_init(metadata_json, analysis):
    task = metadata_json["calls"]["atac.bam2ta"][0]
    new_task = Task("bam2ta", task, analysis)
    filekey = "ta"
    filename = new_task.outputs[filekey]
    md5sum = analysis.backend.md5sum(filename)
    size = analysis.backend.size(filename)
    new_file = GSFile(filekey, filename, md5sum, size, new_task)
    assert new_file.filename == filename
    assert filekey in new_file.filekeys
    assert new_file.md5sum == md5sum
    assert new_file.size == size
    assert new_file.task is new_task
