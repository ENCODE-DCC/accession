import builtins
from contextlib import suppress as does_not_raise
from typing import Dict, List

import pytest
from pytest_mock.plugin import MockFixture
from requests import Response

from accession.accession import (
    Accession,
    AccessionBulkRna,
    AccessionLongReadRna,
    AccessionMicroRna,
    accession_factory,
)
from accession.accession_steps import AccessionStep
from accession.encode_models import EncodeExperiment, EncodeFile
from accession.file import GSFile
from accession.preflight import MatchingMd5Record
from accession.task import Task


class FakeConnection:
    def __init__(self, dcc_url, response=None):
        self._dcc_url = dcc_url
        self._response = response

    @property
    def dcc_url(self):
        return self._dcc_url

    def get(self, query):
        return self._response


@pytest.fixture
def mirna_accessioner(accessioner_factory, mirna_replicated_metadata_path):
    factory = accessioner_factory(
        metadata_file=mirna_replicated_metadata_path, assay_name="mirna"
    )
    accessioner, _ = next(factory)
    return accessioner


@pytest.fixture
def mock_encode_file() -> Dict[str, List[int]]:
    return {"biological_replicates": [1, 2]}


@pytest.fixture
def ok_response():
    r = Response()
    r.status_code = 200
    return r


def test_accession_genome_annotation(mock_accession):
    assert super(AccessionMicroRna, mock_accession).genome_annotation is None


def test_logger(mocker, capsys, mock_accession):
    """
    The log message by default includes a non-deterministic timestamp, so check only the
    last part of the log message. Also checks that no log files were written.
    """
    mocker.patch("builtins.open", mocker.mock_open())
    mock_accession.logger.info("foo")
    captured = capsys.readouterr()
    message_no_timestamp = captured.out.split()[-3:]
    assert message_no_timestamp == ["accession.accession", "INFO", "foo"]
    assert not builtins.open.mock_calls


def test_accession_experiment_fastqs_not_on_portal(
    mocker, mock_accession_not_patched, mock_file
):
    """
    @properties must be patched before instantiation
    """
    mocker.patch.object(
        mock_accession_not_patched,
        "get_encode_file_matching_md5_of_blob",
        return_value=None,
    )
    with pytest.raises(ValueError):
        foo = mock_accession_not_patched.experiment  # noqa: F841


def test_accession_experiment(mocker, mock_accession):
    mocker.patch.object(
        mock_accession,
        "get_encode_file_matching_md5_of_blob",
        EncodeFile({"@id": "baz", "dataset": "foo"}),
    )
    experiment = EncodeExperiment({"@id": "foo"})
    mocker.patch.object(mock_accession.conn, "get", experiment.portal_properties)
    assert mock_accession.experiment.at_id == experiment.at_id


@pytest.mark.docker
@pytest.mark.filesystem
def test_get_encode_file_matching_md5_of_blob(mirna_accessioner):
    fastq = mirna_accessioner.analysis.raw_fastqs[0]
    portal_file = mirna_accessioner.get_encode_file_matching_md5_of_blob(fastq.filename)
    assert portal_file.get("fastq_signature")


@pytest.mark.parametrize(
    "returned_files,expected",
    [
        (
            [
                EncodeFile({"@id": "/files/foo/", "status": "revoked"}),
                EncodeFile({"@id": "/files/bar/", "status": "released"}),
            ],
            EncodeFile({"@id": "/files/bar/", "status": "released"}),
        ),
        ([EncodeFile({"@id": "/files/foo/", "status": "revoked"})], None),
        (None, None),
    ],
)
def test_get_encode_file_matching_md5_of_blob_unit(
    mocker, mock_accession, returned_files, expected
):
    mocker.patch.object(mock_accession.backend, "md5sum", return_value="123")
    mocker.patch.object(
        mock_accession,
        "get_all_encode_files_matching_md5_of_blob",
        return_value=returned_files,
    )
    mocker.patch.object(
        mock_accession.conn,
        "get",
        lambda _: {"@id": "/files/bar/", "status": "released"},
    )
    gs_file = GSFile(key="bam", name="gs://bam/a.bam", md5sum="123", size=456)
    result = mock_accession.get_encode_file_matching_md5_of_blob(gs_file)
    assert result == expected


@pytest.mark.parametrize(
    "returned_files,expected",
    [([{"@id": "/files/abc/"}], [EncodeFile({"@id": "/files/abc/"})]), ([], None)],
)
def test_get_all_encode_files_matching_md5_of_blob(
    mocker, mock_accession, returned_files, expected
):
    mocker.patch.object(mock_accession.backend, "md5sum", return_value="123")
    mocker.patch.object(mock_accession.conn, "search", return_value=returned_files)
    gs_file = GSFile(key="bam", name="gs://bam/a.bam", md5sum="123", size=456)
    result = mock_accession.get_all_encode_files_matching_md5_of_blob(gs_file)
    assert result == expected


def test_make_file_matching_md5_record_no_matches_returns_none(
    mocker, mock_accession, mock_file
):
    mocker.patch.object(
        mock_accession, "get_all_encode_files_matching_md5_of_blob", return_value=None
    )
    result = mock_accession.make_file_matching_md5_record(mock_file)
    assert result is None


def test_make_file_matching_md5_record_matches_does_not_return_none(
    mocker, mock_accession, mock_file
):
    mocker.patch.object(
        mock_accession,
        "get_all_encode_files_matching_md5_of_blob",
        return_value=[EncodeFile({"@id": "foo"})],
    )
    mock_accession.make_file_matching_md5_record(mock_file)
    assert mock_accession.preflight_helper.make_file_matching_md5_record.mock_calls


def test_accession_patch_experiment_analyses(mock_accession):
    mock_accession.new_files = [EncodeFile({"@id": "/files/foo/"})]
    mock_accession.patch_experiment_analyses()
    assert mock_accession.conn.patch.mock_calls[0][1][0] == {
        "_enc_id": "foo",
        "analyses": [{"files": ["/files/foo/"]}],
    }
    assert mock_accession.conn.patch.mock_calls[0][2]["extend_array_values"] is True


def test_accession_patch_experiment_analyses_noop_when_analysis_already_exists(
    capsys, mock_accession
):
    mock_accession.new_files = [EncodeFile({"@id": "/files/1/"})]
    mock_accession.patch_experiment_analyses()
    captured = capsys.readouterr()
    assert captured.out.endswith(
        (
            "Will not patch analyses for experiment foo, found analysis ['/files/1/'] "
            "matching the current set of accessioned files ['/files/1/']\n"
        )
    )
    assert not mock_accession.conn.patch.mock_calls


@pytest.mark.docker
@pytest.mark.filesystem
def test_raw_files_accessioned(mirna_accessioner):
    assert mirna_accessioner.raw_files_accessioned()


@pytest.mark.docker
@pytest.mark.filesystem
def test_assembly(mirna_accessioner):
    assert mirna_accessioner.assembly == "mm10"


@pytest.mark.docker
@pytest.mark.filesystem
def test_genome_annotation(mirna_accessioner):
    assert mirna_accessioner.genome_annotation == "M21"


@pytest.mark.docker
@pytest.mark.skip(
    reason="Elasticsearch is not reliable, produces inconsistent results."
)
@pytest.mark.filesystem
def test_get_derived_from(mirna_accessioner):
    bowtie_step = mirna_accessioner.steps.content[0]
    analysis = mirna_accessioner.analysis
    task = analysis.get_tasks(bowtie_step.wdl_task_name)[0]
    bam = [file for file in task.output_files if "bam" in file.filekeys][0]
    raw_fastq_inputs = list(set(mirna_accessioner.raw_fastq_inputs(bam)))
    accession_ids = [
        mirna_accessioner.get_encode_file_matching_md5_of_blob(file.filename).get(
            "accession"
        )
        for file in raw_fastq_inputs
    ]
    params = bowtie_step.wdl_files[0].derived_from_files[0]
    ancestors = mirna_accessioner.get_derived_from(bam, params)
    ancestor_accessions = [ancestor.split("/")[-2] for ancestor in ancestors]
    assert len(ancestor_accessions) == 3
    assert len(accession_ids) == len(ancestor_accessions)
    assert set(accession_ids) == set(ancestor_accessions)


@pytest.mark.docker
@pytest.mark.skip(
    reason="Elasticsearch is not reliable, produces inconsistent results."
)
@pytest.mark.filesystem
def test_get_derived_from_all(mirna_accessioner):
    bowtie_step = mirna_accessioner.steps.content[0]
    analysis = mirna_accessioner.analysis
    task = analysis.get_tasks(bowtie_step.wdl_task_name)[0]
    bam = [file for file in task.output_files if "bam" in file.filekeys][0]
    raw_fastq_inputs = list(set(mirna_accessioner.raw_fastq_inputs(bam)))
    accession_ids = [
        mirna_accessioner.get_encode_file_matching_md5_of_blob(file.filename).get(
            "accession"
        )
        for file in raw_fastq_inputs
    ]
    derived_from_files = bowtie_step.wdl_files[0].derived_from_files
    ancestors = mirna_accessioner.get_derived_from_all(bam, derived_from_files)
    ancestor_accessions = [ancestor.split("/")[-2] for ancestor in ancestors]
    assert len(ancestor_accessions) == 3
    assert len(accession_ids) == len(ancestor_accessions)
    assert set(accession_ids) == set(ancestor_accessions)


def mock_post_step_run(payload):
    payload.update({"@id": "foo", "@type": ["AnalysisStepRun"]})
    return payload


@pytest.mark.docker
@pytest.mark.filesystem
def test_get_or_make_step_run(mocker, mirna_accessioner):
    mocker.patch.object(mirna_accessioner.conn, "post", mock_post_step_run)
    mocker.patch.object(mirna_accessioner, "log_if_exists", autospec=True)
    bowtie_step = mirna_accessioner.steps.content[0]
    step_run = mirna_accessioner.get_or_make_step_run(bowtie_step)
    assert "AnalysisStepRun" in step_run.portal_step_run.get("@type")
    step_version = step_run.portal_step_run.get("analysis_step_version")
    assert bowtie_step.step_version == step_version


@pytest.mark.docker
@pytest.mark.filesystem
def test_accession_file(mirna_accessioner):
    bowtie_step = mirna_accessioner.steps.content[0]
    analysis = mirna_accessioner.analysis
    task = analysis.get_tasks(bowtie_step.wdl_task_name)[0]
    bam = [file for file in task.output_files if "bam" in file.filekeys][0]
    step_run = mirna_accessioner.get_or_make_step_run(bowtie_step)
    file_params = bowtie_step.wdl_files[0]
    obj = mirna_accessioner.make_file_obj(bam, file_params, step_run)
    encode_file = mirna_accessioner.accession_file(obj, bam)
    assert encode_file.get("accession")
    assert encode_file.get("status") == "uploading"
    assert encode_file.get("submitted_file_name") == bam.filename


@pytest.mark.docker
@pytest.mark.filesystem
def test_make_file_obj(mirna_accessioner):
    bowtie_step = mirna_accessioner.steps.content[0]
    analysis = mirna_accessioner.analysis
    task = analysis.get_tasks(bowtie_step.wdl_task_name)[0]
    bam = [file for file in task.output_files if "bam" in file.filekeys][0]
    step_run = mirna_accessioner.get_or_make_step_run(bowtie_step)
    file_params = bowtie_step.wdl_files[0]
    obj = mirna_accessioner.make_file_obj(bam, file_params, step_run)
    assert obj.get("md5sum") and obj.get("file_size")
    assert len(obj.get("derived_from")) == 3


def test_accession_steps_dry_run(mocker: MockFixture, mock_accession: Accession):
    task_name = "my_task"
    file_name = "gs://bam/a.bam"
    filekey = "bam"
    task = Task(task_name, {"inputs": {}, "outputs": {filekey: file_name}})
    task.output_files = [
        GSFile(key=filekey, name=file_name, md5sum="123", size=456, task=task)
    ]
    mocker.patch.object(mock_accession.backend, "md5sum", return_value="123")
    mocker.patch.object(mock_accession.analysis, "get_tasks", return_value=[task])
    mocker.patch.object(
        mock_accession.preflight_helper,
        "make_file_matching_md5_record",
        return_value=MatchingMd5Record(
            "gs://file/a",
            [
                EncodeFile(
                    {
                        "@id": "/files/ENCFFABC123/",
                        "status": "released",
                        "dataset": "ENCSRCBA321",
                    }
                )
            ],
        ),
    )
    single_step_params = AccessionStep(
        {
            "dcc_step_run": "1",
            "dcc_step_version": "1-0",
            "wdl_files": [
                {
                    "derived_from_files": [],
                    "file_format": "bam",
                    "filekey": "bam",
                    "output_type": "alignments",
                    "quality_metrics": [],
                }
            ],
            "wdl_task_name": task_name,
        }
    )
    results = mock_accession.accession_step(single_step_params, dry_run=True)
    assert results == [
        MatchingMd5Record(
            "gs://file/a",
            [
                EncodeFile(
                    {
                        "@id": "/files/ENCFFABC123/",
                        "status": "released",
                        "dataset": "ENCSRCBA321",
                    }
                )
            ],
        )
    ]


def test_accession_init(mock_accession: Accession, lab: str, award: str) -> None:
    assert mock_accession.common_metadata.lab == lab
    assert mock_accession.common_metadata.award == award
    assert all(
        (
            mock_accession.analysis,
            mock_accession.backend,
            mock_accession.conn,
            mock_accession.steps,
        )
    )


@pytest.mark.parametrize(
    "pipeline_type,condition,accessioner_class",
    [
        ("mirna", does_not_raise(), AccessionMicroRna),
        ("long_read_rna", does_not_raise(), AccessionLongReadRna),
        ("bulk_rna", does_not_raise(), AccessionBulkRna),
        ("not_valid", pytest.raises(RuntimeError), None),
    ],
)
def test_accession_factory(
    mocker, mock_gc_backend, server_name, pipeline_type, condition, accessioner_class
):
    """
    The Connection class actually tries to make connections to the server within its
    __init__, so need to mock out.
    """
    mocker.patch(
        "builtins.open",
        mocker.mock_open(read_data='{"workflowRoot": "gs://foo/bar", "calls": {}}'),
    )
    mocker.patch("accession.accession.Connection")
    with condition:
        accessioner = accession_factory(
            pipeline_type,
            "metadata.json",
            server_name,
            "baz",
            "qux",
            backend=mock_gc_backend,
            no_log_file=True,
        )
        assert isinstance(accessioner, accessioner_class)
