from contextlib import suppress as does_not_raise
from pathlib import Path

import pytest

from accession.analysis import Analysis
from accession.metadata import FileMetadata
from accession.task import Task


@pytest.fixture
def analysis(mock_gc_backend):
    analysis = Analysis(
        FileMetadata("foo"), backend=mock_gc_backend, auto_populate=False
    )
    return analysis


class StubMetadata:
    content = {
        "workflowRoot": "gs://foo/bar",
        "calls": {
            "wf.a": [
                {"executionStatus": "RetryableFailure"},
                {"executionStatus": "Done", "inputs": {}, "outputs": {}},
            ]
        },
    }


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


def test_make_tasks_does_not_add_failed_tasks(mocker, mock_gc_backend):
    mocker.patch("accession.analysis.Analysis.get_or_make_files")
    metadata = StubMetadata()
    analysis = Analysis(metadata, backend=mock_gc_backend)
    result = analysis.make_tasks()
    assert len(result) == 1


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


def test_analysis_get_or_make_files_simple_structure(mocker, analysis):
    mocker.patch.object(analysis, "get_or_make_file", return_value="bar")
    outputs = {
        "one_percent_footprints_bigbed": "gs://foo/footprints.fps.0.01.bb",
        "pe_fastqs": ["gs://foo/ENCFF123ABC.fastq.gz", "gs://foo/ENCFF456ABC.fastq.gz"],
    }
    result = analysis.get_or_make_files(outputs)
    assert len(result) == 3
    analysis.get_or_make_file.assert_any_call(
        "one_percent_footprints_bigbed", "gs://foo/footprints.fps.0.01.bb", None, None
    )
    analysis.get_or_make_file.assert_any_call(
        "pe_fastqs", "gs://foo/ENCFF123ABC.fastq.gz", None, None
    )
    analysis.get_or_make_file.assert_any_call(
        "pe_fastqs", "gs://foo/ENCFF456ABC.fastq.gz", None, None
    )


def test_analysis_get_or_make_files_flattens_nested_dicts(mocker, analysis):
    mocker.patch.object(analysis, "get_or_make_file", return_value="bar")
    outputs = {
        "analysis": {
            "one_percent_footprints_bigbed": "gs://foo/footprints.fps.0.01.bb",
            "replicate": {
                "read_length": 76,
                "number": 1,
                "se_fastqs": None,
                "pe_fastqs": [
                    {
                        "R1": "gs://foo/ENCFF123ABC.fastq.gz",
                        "R2": "gs://foo/ENCFF456ABC.fastq.gz",
                    }
                ],
                "adapters": [{"sequence_R1": "ATGC"}],
            },
        }
    }
    result = analysis.get_or_make_files(outputs)
    assert len(result) == 3
    analysis.get_or_make_file.assert_any_call(
        "analysis.one_percent_footprints_bigbed",
        "gs://foo/footprints.fps.0.01.bb",
        None,
        None,
    )
    analysis.get_or_make_file.assert_any_call(
        "analysis.replicate.pe_fastqs", "gs://foo/ENCFF123ABC.fastq.gz", None, None
    )
    analysis.get_or_make_file.assert_any_call(
        "analysis.replicate.pe_fastqs", "gs://foo/ENCFF456ABC.fastq.gz", None, None
    )


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
    expected = "2099edd0-0399-46ba-941c-abdcea355c1c"
    assert normal_analysis.workflow_id == expected


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
                    "executionStatus": "Done",
                    "dockerImageUsed": "arch:latest",
                    "inputs": {"bam": "gs://foo/bar/ENCFF295YVN.nodup.bam"},
                    "outputs": {
                        "ta": "gs://foo/bar/call-bam2ta/shard-0/glob-35/ENCFF295YVN.nodup.tagAlign.gz"
                    },
                },
                {
                    "executionStatus": "Done",
                    "dockerImageUsed": "arch:latest",
                    "inputs": {"bam": "gs://foo/bar/ENCFF279HDE.nodup.bam"},
                    "outputs": {
                        "ta": "gs://foo/bar/call-bam2ta/shard-1/glob-35/ENCFF279HDE.nodup.tagAlign.gz"
                    },
                },
            ],
            "chip.macs2_signal_track": [
                {
                    "executionStatus": "Done",
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
                    "executionStatus": "Done",
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
            inputs=True,
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


def test_search_down_no_output_files_does_not_raise(mocker):
    """
    Regression test related to PIP-1163. If the current file being searched does not
    have any output files, then the _search_down should not throw an error in the call
    to reduce(), and instead yield nothing.
    """
    mocker.patch(
        "builtins.open", mocker.mock_open(read_data='{"workflowRoot": "gs://foo/bar"}')
    )
    analysis = Analysis(FileMetadata("foo"), auto_populate=False, backend="")
    no_outputs_task = Task("foo", {"inputs": {"bar": "gs://baz"}, "outputs": {}})
    result = list(analysis._search_down(no_outputs_task, "searching_for", "a_file"))
    assert result == []


@pytest.fixture
def empty_analysis(mock_gc_backend, metadata_json_path):  # noqa: F811
    empty = Analysis(
        FileMetadata(metadata_json_path), auto_populate=False, backend=mock_gc_backend
    )
    return empty
