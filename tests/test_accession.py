import builtins
from contextlib import suppress as does_not_raise
from typing import Dict, List

import pytest
from pytest_mock.plugin import MockFixture
from requests import Response

from accession.accession import (
    Accession,
    AccessionBulkRna,
    AccessionMicroRna,
    _get_long_read_rna_steps_json_name_prefix_from_metadata,
    accession_factory,
)
from accession.accession_steps import AccessionStep, DerivedFromFile
from accession.encode_models import EncodeExperiment, EncodeFile, EncodeGenericObject
from accession.file import GSFile
from accession.metadata import FileMetadata
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


@pytest.fixture
def matching_md5_record():
    record = MatchingMd5Record(
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
    return record


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
    experiment = EncodeExperiment({"@id": "/experiments/foo/"})
    mocker.patch.object(mock_accession.conn, "get", experiment.portal_properties)
    assert mock_accession.experiment.at_id == experiment.at_id


@pytest.mark.docker
@pytest.mark.filesystem
def test_get_encode_file_matching_md5_of_blob(mirna_accessioner):
    fastq = mirna_accessioner.analysis.raw_fastqs[0]
    portal_file = mirna_accessioner.get_encode_file_matching_md5_of_blob(fastq)
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
    mocker.patch.object(mock_accession.conn, "search", return_value=returned_files)
    gs_file = GSFile(key="bam", name="gs://bam/a.bam", md5sum="123", size=456)
    result = mock_accession.get_all_encode_files_matching_md5_of_blob(gs_file)
    assert result == expected


def test_get_all_encode_files_matching_md5_of_blob_cache_hit(mocker, mock_accession):
    mocker.patch.object(mock_accession.conn, "search")
    returned_files = [{"@id": "foo"}]
    gs_file = GSFile(key="bam", name="gs://bam/a.bam", md5sum="123", size=456)
    mock_accession.search_cache.insert("123", returned_files)
    result = mock_accession.get_all_encode_files_matching_md5_of_blob(gs_file)
    assert not mock_accession.conn.search.mock_calls
    assert result == [EncodeFile(returned_files[0])]


def test_get_all_encode_files_matching_md5_of_blob_cache_hit_no_results_returns_none(
    mocker, mock_accession
):
    mocker.patch.object(mock_accession.conn, "search")
    returned_files = []
    gs_file = GSFile(key="bam", name="gs://bam/a.bam", md5sum="123", size=456)
    mock_accession.search_cache.insert("123", returned_files)
    result = mock_accession.get_all_encode_files_matching_md5_of_blob(gs_file)
    assert not mock_accession.conn.search.mock_calls
    assert result is None


def test_filter_derived_from_files_by_workflow_inputs(mocker, mock_accession):
    mocker.patch.object(
        mock_accession.analysis,
        "metadata",
        new_callable=mocker.PropertyMock(
            return_value={"inputs": {"foo": ["gs://bar/baz"]}}
        ),
    )
    ancestor = DerivedFromFile(
        {
            "workflow_inputs_to_match": ["foo"],
            "derived_from_filekey": "foo",
            "derived_from_task": "task",
        }
    )
    file_to_match = GSFile(key="foo", name="gs://bar/baz", md5sum="123", size=456)
    file_to_ignore = GSFile(key="baz", name="gs://bar/qux", md5sum="123", size=456)
    derived_from_files = [file_to_match, file_to_ignore]
    result = mock_accession._filter_derived_from_files_by_workflow_inputs(
        derived_from_files, ancestor
    )
    assert result == [file_to_match]


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


def test_accession_post_document(mocker, mock_accession, encode_document):
    mocker.patch.object(encode_document, "get_portal_object", return_value={})
    mocker.patch.object(mock_accession.conn, "post", return_value=({"@id": "bar"}, 200))
    result = mock_accession.post_document(encode_document)
    assert result.at_id == "bar"


def test_accession_post_document_log_on_alias_conflict(
    mocker, mock_accession, encode_document
):
    mocker.patch.object(encode_document, "get_portal_object", return_value={})
    mocker.patch.object(mock_accession.conn, "post", return_value=({"@id": "baz"}, 409))
    mocker.patch.object(mock_accession.logger, "warning")
    mock_accession.post_document(encode_document)
    mock_accession.logger.warning.assert_called_once()


def test_accession_post_analysis(mocker, mock_accession):
    mocker.patch.object(mock_accession.conn, "post", return_value=({}, 200))
    mocker.patch.object(
        mock_accession.analysis.metadata, "get_as_attachment", create=True
    )
    mocker.patch.object(
        mock_accession,
        "post_document",
        return_value=EncodeGenericObject({"@id": "doc"}),
    )
    mocker.patch.object(
        mock_accession, "new_files", [EncodeFile({"@id": "/files/foo/"})]
    )
    mock_accession.post_analysis()
    assert mock_accession.conn.post.mock_calls[0][1][0] == {
        "_profile": "analysis",
        "files": ["/files/foo/"],
        "aliases": ["encode-processing-pipeline:123"],
        "documents": ["doc"],
    }


def test_accession_post_analysis_log_on_alias_conflict(mocker, mock_accession):
    mocker.patch.object(mock_accession.conn, "post", return_value=({"@id": "bar"}, 409))
    mocker.patch.object(
        mock_accession.analysis.metadata, "get_as_attachment", create=True
    )
    mocker.patch.object(
        mock_accession,
        "post_document",
        return_value=EncodeGenericObject({"@id": "doc"}),
    )
    mocker.patch.object(mock_accession.logger, "warning")
    mocker.patch.object(mock_accession, "new_files", [EncodeFile({"@id": "/files/1/"})])
    mock_accession.post_analysis()
    mock_accession.logger.warning.assert_called_once()


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
        mirna_accessioner.get_encode_file_matching_md5_of_blob(file).get("accession")
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
        mirna_accessioner.get_encode_file_matching_md5_of_blob(file).get("accession")
        for file in raw_fastq_inputs
    ]
    derived_from_files = bowtie_step.wdl_files[0].derived_from_files
    ancestors = mirna_accessioner.get_derived_from_all(bam, derived_from_files)
    ancestor_accessions = [ancestor.split("/")[-2] for ancestor in ancestors]
    assert len(ancestor_accessions) == 3
    assert len(accession_ids) == len(ancestor_accessions)
    assert set(accession_ids) == set(ancestor_accessions)


@pytest.mark.parametrize(
    "file_size_bytes,expected",
    [
        (1, 8_388_608),
        (10_000 * 8_388_608, 8_388_608),
        (100e9, 16_777_216),
        (200e9, 25_165_824),
    ],
)
def test_accession_calculate_multipart_chunksize(
    mock_accession, file_size_bytes, expected
):
    result = mock_accession._calculate_multipart_chunksize(file_size_bytes)
    assert result == expected


def mock_post_step_run(payload, *args, **kwargs):
    payload.update({"@id": "foo", "@type": ["AnalysisStepRun"]})
    return (payload, 200)


@pytest.mark.docker
@pytest.mark.filesystem
def test_get_or_make_step_run(mocker, mirna_accessioner):
    mocker.patch.object(mirna_accessioner.conn, "post", mock_post_step_run)
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


@pytest.mark.parametrize(
    "kwargs", [{"dry_run": True}, {"dry_run": True, "force": True}]
)
def test_accession_steps_matches_dry_run(
    caplog, mocker, mock_accession, matching_md5_record, kwargs
):
    """
    Dry run shouldn't accession anything and has precendence over `force`
    """
    mocker.patch.object(mock_accession, "_get_dry_run_matches", return_value=[])
    mocker.patch.object(mock_accession, "accession_step")
    mock_accession.accession_steps(**kwargs)
    assert "Dry run finished" in caplog.text
    mock_accession.accession_step.assert_not_called()


def test_accession_steps_matches_no_force(
    caplog, mocker, mock_accession, matching_md5_record
):
    mocker.patch.object(
        mock_accession, "_get_dry_run_matches", return_value=[matching_md5_record]
    )
    mocker.patch.object(mock_accession, "accession_step")
    mock_accession.accession_steps(force=False)
    assert "stopping accessioning" in caplog.text
    mock_accession.accession_step.assert_not_called()


def test_accession_steps_matches_with_force(
    caplog, mocker, mock_accession, matching_md5_record
):
    mocker.patch.object(
        mock_accession, "_get_dry_run_matches", return_value=[matching_md5_record]
    )
    mocker.patch.object(mock_accession, "accession_step")
    mocker.patch.object(mock_accession, "post_analysis")
    mock_accession.accession_steps(force=True)
    assert "continuing accessioning" in caplog.text
    mock_accession.accession_step.assert_called()


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
        ("bulk_rna", does_not_raise(), AccessionBulkRna),
        ("not_valid", pytest.raises(RuntimeError), None),
    ],
)
def test_accession_factory(
    tmp_path,
    mocker,
    mock_gc_backend,
    server_name,
    pipeline_type,
    condition,
    accessioner_class,
):
    """
    The Connection class actually tries to make connections to the server within its
    __init__, so need to mock out.
    """
    metadata_file = tmp_path / "metadata.json"
    metadata_file.touch()
    mocker.patch(
        "builtins.open",
        mocker.mock_open(read_data='{"workflowRoot": "gs://foo/bar", "calls": {}}'),
    )
    mocker.patch("accession.accession.Connection")
    with condition:
        accessioner = accession_factory(
            pipeline_type,
            str(metadata_file),
            server_name,
            "baz",
            "qux",
            backend=mock_gc_backend,
            no_log_file=True,
        )
        assert isinstance(accessioner, accessioner_class)


@pytest.mark.parametrize(
    "spikeins,expected",
    [
        ([], "long_read_rna_no_spikeins"),
        (["foo"], "long_read_rna_one_spikein"),
        (["foo", "bar"], "long_read_rna_two_or_more_spikeins"),
    ],
)
def test_get_long_read_rna_steps_json_name_prefix_from_metadata(
    tmp_path, mocker, spikeins, expected
):
    mocker.patch(
        "accession.metadata.FileMetadata.content",
        new_callable=mocker.PropertyMock(
            return_value={
                "workflowRoot": "gs://foo/bar",
                "calls": {},
                "inputs": {"spikeins": spikeins},
            }
        ),
    )
    metadata = FileMetadata("foo")
    result = _get_long_read_rna_steps_json_name_prefix_from_metadata(metadata)
    assert result == expected
