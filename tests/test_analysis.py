from contextlib import suppress as does_not_raise
from pathlib import Path

import pytest

from accession.analysis import Analysis, MetaData
from accession.task import Task


def test_invalid_metadata_raises():
    """
    Trying to create an Analysis from invalid JSON should raise an error.
    """
    current_dir = Path(__file__).resolve()
    metadata_json = current_dir.parent / "data" / "invalid_metadata.json"
    with pytest.raises(Exception):
        Analysis(metadata_json)


@pytest.mark.filesystem
def test_make_tasks(empty_analysis):
    assert len(empty_analysis.files) == 0
    empty_analysis.tasks = empty_analysis.make_tasks()
    assert len(empty_analysis.files) == 208
    assert len(empty_analysis.tasks) == 38


@pytest.mark.filesystem
def test_make_task(normal_analysis):
    inputs = {"foo": "gs://foo/foo"}
    outputs = {"baz": "gs://foo/baz"}
    docker_image = "ms-dos/latest"
    task = {"inputs": inputs, "outputs": outputs, "dockerImageUsed": docker_image}
    task_name = "atac.my_task"
    new_task = normal_analysis.make_task(task_name, task)
    assert new_task.task_name == "my_task"
    assert new_task.inputs == inputs
    assert new_task.outputs == outputs
    assert new_task.docker_image == docker_image


@pytest.mark.filesystem
def test_get_or_make_file_empty_analysis(empty_analysis):
    assert len(empty_analysis.files) == 0
    task = {"inputs": {}, "outputs": {}, "dockerImageUsed": ""}
    empty_task = Task("bam2ta", task)
    # Make a file when it doesn't exist
    filekey = "ta"
    filename = (
        "gs://encode-pipeline-test-runs/atac/2099edd0-0399-46ba-941c-abdcea355c1c/call-"
        "bam2ta/shard-0/glob-199637d3015dccbe277f621a18be9eb4/ENCFF599TJR.merged.nodup."
        "tn5.tagAlign.gz"
    )
    empty_analysis.get_or_make_file(filekey, filename, empty_task)
    assert len(empty_analysis.files) == 1
    assert empty_analysis.files[0].filename == filename
    # Get file if it exists, don't make a duplicate
    empty_analysis.get_or_make_file(filekey, filename, empty_task)
    assert len(empty_analysis.files) == 1


@pytest.mark.filesystem
def test_get_or_make_file_normal_analysis(normal_analysis):
    assert len(normal_analysis.files) == 208


@pytest.mark.filesystem
def test_workflow_id(normal_analysis):
    expected = "cromwell-2099edd0-0399-46ba-941c-abdcea355c1c"
    assert normal_analysis.workflow_id == expected


@pytest.mark.filesystem
def test_outputs_whitelist(normal_analysis):
    prefix = (
        "gs://encode-pipeline-test-runs/atac/2099edd0-0399-46ba-941c-abdcea355c1c/call-"
        "qc_report/"
    )
    expected = [
        f"{prefix}glob-3440f922973abb7a616aaf203e0db08b/qc.json",
        f"{prefix}glob-eae855c82d0f7e2185388856e7b2cc7b/qc.html",
    ]
    assert normal_analysis.outputs_whitelist == expected


@pytest.mark.filesystem
def test_inputs_whitelist(normal_analysis):
    prefix = "gs://atac-seq-accessioning-samples/ENCSR609OHJ/"
    expected = [
        f"{prefix}rep_1/ENCFF599TJR.fastq.gz",
        f"{prefix}rep_1/ENCFF176IZG.fastq.gz",
        f"{prefix}rep_2/ENCFF957VLH.fastq.gz",
        f"{prefix}rep_2/ENCFF999IJT.fastq.gz",
        "gs://encode-pipeline-genome-data/mm10_google.tsv",
    ]
    assert normal_analysis.inputs_whitelist == expected


@pytest.mark.filesystem
def test_get_files(normal_analysis):
    files = normal_analysis.get_files(filekey="ta")
    assert len(files) == 9
    assert all(["ta" in file.filekeys for file in files])
    filename = files[0].filename
    files2 = normal_analysis.get_files(filename=filename)
    assert filename == files2[0].filename
    assert len(files2) == 1


def test_get_tasks(normal_analysis):
    tasks = normal_analysis.get_tasks("bam2ta")
    tasks2 = normal_analysis.get_tasks("qc_report")
    assert len(tasks) == 2
    assert all([task.task_name == "bam2ta" for task in tasks])
    assert len(tasks2) == 1
    assert tasks2[0].task_name == "qc_report"


@pytest.mark.filesystem
def test_search_up(normal_analysis):
    task = normal_analysis.get_tasks("qc_report")[0]
    files = normal_analysis.search_up(task, "bam2ta", "ta")
    assert len(files) == 2
    assert "ta" in files[0].filekeys
    task2 = normal_analysis.get_tasks("bam2ta")[0]
    files2 = normal_analysis.search_up(task2, "trim_adapter", "fastqs", inputs=True)
    assert len(files2) == 2
    task3 = normal_analysis.get_tasks("ataqc")[0]
    files3 = normal_analysis.search_up(task3, "trim_adapter", "fastqs", inputs=True)
    # Notice how tree nodes widen the search scope
    assert len(files3) == 4


@pytest.mark.parametrize(
    "condition,disallow_tasks,expected",
    [
        (does_not_raise(), ("choose_ctl"), ["gs://foo/bar/ENCFF295YVN.nodup.bam"]),
        (
            does_not_raise(),
            (),
            [
                "gs://foo/bar/ENCFF295YVN.nodup.bam",
                "gs://foo/bar/ENCFF279HDE.nodup.bam",
            ],
        ),
        (pytest.raises(ValueError), ("bam2ta"), []),
    ],
)
def test_search_up_disallow_tasks(
    mock_metadata, mock_gc_backend, condition, disallow_tasks, expected
):
    metadata = {
        "workflowRoot": "gs://foo/bar/",
        "calls": {
            "chip.bam2ta": [
                {
                    "dockerImageUsed": "arch:latest",
                    "inputs": {"bam": "gs://foo/bar/ENCFF295YVN.nodup.bam"},
                    "outputs": {
                        "ta": "gs://foo/bar/call-bam2ta/shard-0/glob-35/ENCFF295YVN.nodup.tagAlign.gz"
                    },
                },
                {
                    "dockerImageUsed": "arch:latest",
                    "inputs": {"bam": "gs://foo/bar/ENCFF279HDE.nodup.bam"},
                    "outputs": {
                        "ta": "gs://foo/bar/call-bam2ta/shard-1/glob-35/ENCFF279HDE.nodup.tagAlign.gz"
                    },
                },
            ],
            "chip.macs2_signal_track": [
                {
                    "dockerImageUsed": "arch:latest",
                    "inputs": {
                        "tas": [
                            "gs://foo/bar/call-bam2ta/shard-0/glob-35/ENCFF295YVN.nodup.tagAlign.gz",
                            "gs://foo/bar/call-choose_ctl/glob-99/ctl_for_rep1.tagAlign.gz",
                        ]
                    },
                    "outputs": {
                        "fc_bw": "gs://foo/bar/call-macs2_signal_track/shard-0/glob-10/ENCFF295YVN.bigwig",
                        "pval_bw": "gs://foo/bar/call-macs2_signal_track/shard-0/glob-89/ENCFF295YVN.bigwig",
                    },
                }
            ],
            "chip.choose_ctl": [
                {
                    "dockerImageUsed": "arch:latest",
                    "inputs": {
                        "tas": [
                            "gs://foo/bar/call-bam2ta/shard-0/glob-35/ENCFF295YVN.nodup.tagAlign.gz",
                            "gs://foo/bar/call-bam2ta/shard-1/glob-35/ENCFF279HDE.nodup.tagAlign.gz",
                        ]
                    },
                    "outputs": {
                        "chosen_ctl_tas": [
                            "gs://foo/bar/call-choose_ctl/glob-99/ctl_for_rep1.tagAlign.gz",
                            "gs://foo/bar/call-choose_ctl/glob-99/ctl_for_rep2.tagAlign.gz",
                        ]
                    },
                }
            ],
        },
    }
    mock_metadata.content = metadata
    analysis = Analysis(mock_metadata, backend=mock_gc_backend)
    start_task = analysis.get_tasks("macs2_signal_track")[0]
    with condition:
        results = analysis.search_up(
            start_task=start_task,
            task_name="bam2ta",
            filekey="bam",
            inputs="true",
            disallow_tasks=disallow_tasks,
        )
        result = [i.filename for i in results]
        assert sorted(result) == sorted(expected)


@pytest.mark.filesystem
def test_search_down(normal_analysis):
    task = normal_analysis.get_tasks("bam2ta")[0]
    files = normal_analysis.search_down(task, "ataqc", "html")
    assert len(files) == 2
    assert "html" in files[0].filekeys
    files2 = normal_analysis.search_down(task, "qc_report", "report")
    assert len(files2) == 1
    assert "report" in files2[0].filekeys


@pytest.fixture
def empty_analysis(mock_gc_backend, metadata_json_path):  # noqa: F811
    empty = Analysis(
        MetaData(metadata_json_path), auto_populate=False, backend=mock_gc_backend
    )
    return empty
