import json
from pathlib import Path
from types import GeneratorType
from typing import Dict, List
from unittest.mock import PropertyMock

import attr
import pytest
from pytest_mock.plugin import MockFixture
from requests import Response

from accession.accession import Accession, AccessionSteps
from accession.analysis import Analysis, MetaData

from .fixtures import MockGCBackend


@attr.s(auto_attribs=True)
class MockFile:
    filename: str
    size: int
    md5sum: str


@pytest.fixture
def mirna_accessioner(accessioner_factory):
    factory = accessioner_factory(
        metadata_file="mirna_replicated_metadata.json", assay_name="mirna"
    )
    accessioner, _ = next(factory)
    return accessioner


@pytest.mark.docker
@pytest.mark.filesystem
def test_get_encode_file_matching_md5_of_blob(mirna_accessioner):
    fastq = mirna_accessioner.analysis.raw_fastqs[0]
    portal_file = mirna_accessioner.get_encode_file_matching_md5_of_blob(fastq.filename)
    assert portal_file.get("fastq_signature")


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


@pytest.fixture
def ok_response():
    r = Response()
    r.status_code = 200
    return r


class FakeConnection:
    def __init__(self, dcc_url, response=None):
        self._dcc_url = dcc_url
        self._response = response

    @property
    def dcc_url(self):
        return self._dcc_url

    def get(self, query):
        return self._response


def test_get_number_of_biological_replicates(
    ok_response, mock_metadata, mock_gc_backend
):
    x = AccessionSteps("path")
    analysis = Analysis(mock_metadata, backend=mock_gc_backend)
    connection = FakeConnection(
        "https://www.zencodeproject.borg",
        response={
            "replicates": [
                {"biological_replicate_number": 1},
                {"biological_replicate_number": 2},
            ]
        },
    )
    y = Accession(x, analysis, connection, "lab", "award")
    y._dataset = "my_dataset"
    assert y.get_number_of_biological_replicates() == 2


@pytest.mark.docker
@pytest.mark.skip(
    reason="Elasticsearch is not reliable, produces inconsistent results."
)
@pytest.mark.filesystem
def test_get_derived_from(mirna_accessioner):
    bowtie_step = mirna_accessioner.steps.content[0]
    analysis = mirna_accessioner.analysis
    task = analysis.get_tasks(bowtie_step["wdl_task_name"])[0]
    bam = [file for file in task.output_files if "bam" in file.filekeys][0]
    raw_fastq_inputs = list(set(mirna_accessioner.raw_fastq_inputs(bam)))
    accession_ids = [
        mirna_accessioner.get_encode_file_matching_md5_of_blob(file.filename).get(
            "accession"
        )
        for file in raw_fastq_inputs
    ]
    params = bowtie_step["wdl_files"][0]["derived_from_files"][0]
    ancestors = mirna_accessioner.get_derived_from(
        bam,
        params.get("derived_from_task"),
        params.get("derived_from_filekey"),
        params.get("derived_from_output_type"),
        params.get("derived_from_inputs"),
    )
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
    task = analysis.get_tasks(bowtie_step["wdl_task_name"])[0]
    bam = [file for file in task.output_files if "bam" in file.filekeys][0]
    raw_fastq_inputs = list(set(mirna_accessioner.raw_fastq_inputs(bam)))
    accession_ids = [
        mirna_accessioner.get_encode_file_matching_md5_of_blob(file.filename).get(
            "accession"
        )
        for file in raw_fastq_inputs
    ]
    derived_from_files = bowtie_step["wdl_files"][0]["derived_from_files"]
    ancestors = mirna_accessioner.get_derived_from_all(bam, derived_from_files)
    ancestor_accessions = [ancestor.split("/")[-2] for ancestor in ancestors]
    assert len(ancestor_accessions) == 3
    assert len(accession_ids) == len(ancestor_accessions)
    assert set(accession_ids) == set(ancestor_accessions)


def mock_post_step_run(payload):
    payload.update({"@type": ["AnalysisStepRun"]})
    return payload


@pytest.mark.docker
@pytest.mark.filesystem
def test_get_or_make_step_run(mocker, mirna_accessioner):
    mocker.patch.object(mirna_accessioner.conn, "post", mock_post_step_run)
    mocker.patch.object(mirna_accessioner, "log_if_exists", autospec=True)
    bowtie_step = mirna_accessioner.steps.content[0]
    step_run = mirna_accessioner.get_or_make_step_run(
        mirna_accessioner.lab_pi,
        bowtie_step["dcc_step_run"],
        bowtie_step["dcc_step_version"],
        bowtie_step["wdl_task_name"],
    )
    assert "AnalysisStepRun" in step_run.get("@type")
    step_version = step_run.get("analysis_step_version")
    assert bowtie_step["dcc_step_version"] == step_version


@pytest.mark.docker
@pytest.mark.filesystem
def test_accession_file(mirna_accessioner):
    bowtie_step = mirna_accessioner.steps.content[0]
    analysis = mirna_accessioner.analysis
    task = analysis.get_tasks(bowtie_step["wdl_task_name"])[0]
    bam = [file for file in task.output_files if "bam" in file.filekeys][0]
    step_run = mirna_accessioner.get_or_make_step_run(
        mirna_accessioner.lab_pi,
        bowtie_step["dcc_step_run"],
        bowtie_step["dcc_step_version"],
        bowtie_step["wdl_task_name"],
    )
    file_params = bowtie_step["wdl_files"][0]
    obj = mirna_accessioner.make_file_obj(
        bam,
        file_params["file_format"],
        file_params["output_type"],
        step_run,
        file_params["derived_from_files"],
        file_format_type=file_params.get("file_format_type"),
    )
    encode_file = mirna_accessioner.accession_file(obj, bam)
    assert encode_file.get("accession")
    assert encode_file.get("status") == "uploading"
    assert encode_file.get("submitted_file_name") == bam.filename


@pytest.mark.docker
@pytest.mark.filesystem
def test_make_file_obj(mirna_accessioner):
    bowtie_step = mirna_accessioner.steps.content[0]
    analysis = mirna_accessioner.analysis
    task = analysis.get_tasks(bowtie_step["wdl_task_name"])[0]
    bam = [file for file in task.output_files if "bam" in file.filekeys][0]
    step_run = mirna_accessioner.get_or_make_step_run(
        mirna_accessioner.lab_pi,
        bowtie_step["dcc_step_run"],
        bowtie_step["dcc_step_version"],
        bowtie_step["wdl_task_name"],
    )
    file_params = bowtie_step["wdl_files"][0]
    obj = mirna_accessioner.make_file_obj(
        bam,
        file_params["file_format"],
        file_params["output_type"],
        step_run,
        file_params["derived_from_files"],
        file_format_type=file_params.get("file_format_type"),
    )
    assert obj.get("md5sum") and obj.get("file_size")
    assert len(obj.get("derived_from")) == 3


def test_accession_init(mock_accession: Accession, lab: str, award: str) -> None:
    assert mock_accession.COMMON_METADATA["lab"] == lab
    assert mock_accession.COMMON_METADATA["award"] == award
    assert all(
        (
            mock_accession.analysis,
            mock_accession.backend,
            mock_accession.conn,
            mock_accession.steps,
        )
    )


def test_get_step_run_id_string(mock_accession: Accession) -> None:
    expected = "/analysis-step-runs/123foobar"
    encode_file = {"step_run": expected}
    result = mock_accession.get_step_run_id(encode_file)
    assert result == expected


def test_get_step_run_id_dict(mock_accession: Accession) -> None:
    expected = "/analysis-step-runs/123foobar"
    encode_file = {"step_run": {"@id": expected}}
    result = mock_accession.get_step_run_id(encode_file)
    assert result == expected


def test_lab_pi(mock_accession: Accession, lab: str, award: str) -> None:
    assert mock_accession.lab_pi == "encode-processing-pipeline"


@pytest.mark.parametrize("file_format_type", [None, "bedMethyl"])
def test_file_from_template(
    mocker: MockFixture,
    mock_accession: Accession,
    lab: str,
    award: str,
    mock_file: MockFile,
    file_format_type: str,
) -> None:
    kwargs = {
        "file": mock_file,
        "file_format": "tsv",
        "output_type": "gene quantifications",
        "step_run": {"@id": "my-step-run"},
        "derived_from": "baz",
        "dataset": "qux",
        "file_format_type": file_format_type,
    }
    file = mock_accession.file_from_template(**kwargs)
    expected = {
        "status": "uploading",
        "aliases": ["encode-processing-pipeline:foo-bar"],
        "file_size": mock_file.size,
        "md5sum": mock_file.md5sum,
        "assembly": "hg19",
        "step_run": "my-step-run",
    }
    for k in ["output_type", "file_format", "dataset", "derived_from"]:
        expected[k] = kwargs[k]
    for k, v in expected.items():
        assert file[k] == v
    if file_format_type:
        assert file["file_format_type"] == file_format_type
    else:
        assert "file_format_type" not in file
    assert file["genome_annotation"] == "V19"
    assert "lab" in file
    assert "award" in file


def test_flatten(mock_accession: Accession) -> None:
    result = mock_accession.flatten([["a", "b"], ["c", "d"]])
    assert isinstance(result, GeneratorType)
    assert list(result) == ["a", "b", "c", "d"]


def test_get_bio_replicate_str(
    mock_accession: Accession, mock_encode_file: Dict[str, List[int]]
) -> None:
    result = mock_accession.get_bio_replicate(mock_encode_file)
    assert result == "1"


def test_get_bio_replicate_int(
    mock_accession: Accession, mock_encode_file: Dict[str, List[int]]
) -> None:
    result = mock_accession.get_bio_replicate(mock_encode_file, string=False)
    assert result == 1


def mock_queue_qc(qc, *args, **kwargs):
    return qc


@pytest.mark.filesystem
def test_make_microrna_quantification_qc(mock_replicated_mirna_accession):
    gs_file = [
        i
        for i in mock_replicated_mirna_accession.analysis.get_files(filekey="bam")
        if "rep1" in i.filename
    ][0]
    qc = mock_replicated_mirna_accession.make_microrna_quantification_qc("foo", gs_file)
    assert qc == {"expressed_mirnas": 393}


@pytest.mark.filesystem
def test_make_microrna_mapping_qc(mock_replicated_mirna_accession):
    gs_file = [
        i
        for i in mock_replicated_mirna_accession.analysis.get_files(filekey="bam")
        if "rep1" in i.filename
    ][0]
    qc = mock_replicated_mirna_accession.make_microrna_mapping_qc("foo", gs_file)
    assert qc == {"aligned_reads": 5873570}


@pytest.mark.filesystem
def test_make_microrna_correlation_qc_replicated(mock_replicated_mirna_accession):
    gs_file = [
        i for i in mock_replicated_mirna_accession.analysis.get_files(filekey="tsv")
    ][0]
    qc = mock_replicated_mirna_accession.make_microrna_correlation_qc("foo", gs_file)
    assert qc == {"Spearman correlation": 0.8885044458946942}


@pytest.mark.filesystem
def test_make_microrna_correlation_qc_unreplicated_returns_none(
    mocker, mock_accession_unreplicated, mirna_replicated_analysis
):
    mocker.patch.object(
        mock_accession_unreplicated, "analysis", mirna_replicated_analysis
    )
    mocker.patch.object(
        mock_accession_unreplicated, "backend", mirna_replicated_analysis.backend
    )
    mocker.patch.object(mock_accession_unreplicated, "file_has_qc", return_value=False)
    mocker.patch.object(mock_accession_unreplicated, "queue_qc", mock_queue_qc)
    gs_file = [
        i for i in mock_accession_unreplicated.analysis.get_files(filekey="tsv")
    ][0]
    qc = mock_accession_unreplicated.make_microrna_correlation_qc("foo", gs_file)
    assert qc is None


@pytest.mark.filesystem
def test_make_star_qc_metric(mock_replicated_mirna_accession):
    gs_file = [
        i
        for i in mock_replicated_mirna_accession.analysis.get_files(filekey="bam")
        if "rep1" in i.filename
    ][0]
    current_dir = Path(__file__).resolve()
    validation = current_dir.parent / "data" / "validation" / "mirna" / "files.json"
    with open(validation) as f:
        data = json.load(f)
    expected = [i for i in data if i["accession"] == "ENCFF590YAX"][0][
        "quality_metrics"
    ][0]
    qc = mock_replicated_mirna_accession.make_star_qc_metric("foo", gs_file)
    for k, v in qc.items():
        assert v == expected[k]


@pytest.fixture
def mock_replicated_mirna_accession(mocker, mirna_replicated_analysis, mock_accession):
    """
    Contains a legitimate replicated mirna analysis for purposes of testing mirna qm
    generation without creating any connections to servers.
    """
    mocker.patch.object(mock_accession, "analysis", mirna_replicated_analysis)
    mocker.patch.object(mock_accession, "backend", mirna_replicated_analysis.backend)
    mocker.patch.object(mock_accession, "file_has_qc", return_value=False)
    mocker.patch.object(mock_accession, "queue_qc", mock_queue_qc)
    return mock_accession


@pytest.fixture
def mirna_replicated_analysis(
    mock_accession_gc_backend: MockFixture
) -> Analysis:  # noqa: F811
    current_dir = Path(__file__).resolve()
    metadata_json_path = current_dir.parent / "data" / "mirna_replicated_metadata.json"
    analysis = Analysis(MetaData(metadata_json_path), backend=mock_accession_gc_backend)
    return analysis


@pytest.fixture
def mock_encode_file() -> Dict[str, List[int]]:
    return {"biological_replicates": [1, 2]}


class MockMetaData:
    content = {"workflowRoot": "gs://foo/bar", "calls": {}}


@pytest.fixture
def mock_metadata():
    return MockMetaData()


class MockAccessionSteps:
    path_to_json = "/dev/null"
    content = {"accession.steps": [{"a": "b"}]}


@pytest.fixture
def mock_accession_steps():
    return MockAccessionSteps()


@pytest.fixture
def mock_accession(
    mocker: MockFixture,
    mock_accession_gc_backend: MockGCBackend,
    mock_metadata: MockMetaData,
    mock_accession_steps: MockAccessionSteps,
    lab: str,
    award: str,
) -> Accession:
    """
    Mocked accession instance with dummy __init__ that doesn't do anything and pre-baked
    assembly property. @properties must be patched before instantiation
    """
    mocker.patch.object(
        Accession, "assembly", new_callable=PropertyMock(return_value="hg19")
    )
    mocker.patch.object(
        Accession, "genome_annotation", new_callable=PropertyMock(return_value="V19")
    )
    mocker.patch.object(
        Accession, "is_replicated", new_callable=PropertyMock(return_value=True)
    )
    mocked_accession = Accession(
        mock_accession_steps,
        Analysis(mock_metadata, backend=mock_accession_gc_backend),
        "mock_server.biz",
        lab,
        award,
    )
    return mocked_accession


@pytest.fixture
def mock_accession_unreplicated(
    mocker: MockFixture,
    mock_accession_gc_backend: MockGCBackend,
    mock_metadata: MockMetaData,
    lab: str,
    award: str,
) -> Accession:
    """
    Mocked accession instance with dummy __init__ that doesn't do anything and pre-baked
    assembly property. @properties must be patched before instantiation
    """
    mocker.patch.object(
        Accession, "is_replicated", new_callable=PropertyMock(return_value=False)
    )
    mocked_accession = Accession(
        "imaginary_steps.json",
        Analysis(mock_metadata, backend=mock_accession_gc_backend),
        "mock_server.biz",
        lab,
        award,
    )
    return mocked_accession


@pytest.fixture
def mock_file() -> MockFile:
    return MockFile("gs://foo/bar", 123, "abc")


def test_filter_encode_files_by_status_one_hit():
    files = [{"status": "foo"}, {"status": "bar"}, {"status": "deleted"}]
    assert len(Accession.filter_encode_files_by_status(files)) == 2


def test_filter_encode_files_by_status_no_hits():
    files = [{"status": "foo"}]
    assert len(Accession.filter_encode_files_by_status(files)) == 1
