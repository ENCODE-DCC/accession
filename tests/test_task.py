from accession.task import Task


def test_task_init(metadata_json, analysis):
    task = metadata_json['calls']['atac.bam2ta'][0]
    new_task = Task('bam2ta', task, analysis)
    assert new_task.inputs == task['inputs']
    assert new_task.outputs == task['outputs']
    assert new_task.task_name == 'bam2ta'
    assert new_task.docker_image == task['dockerImageUsed']
    assert new_task.analysis is analysis
