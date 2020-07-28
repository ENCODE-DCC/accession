import json
from pathlib import Path
from unittest.mock import PropertyMock

import pytest
from pytest_mock.plugin import MockFixture

from accession.analysis import Analysis
from accession.encode_models import EncodeExperiment
from accession.metadata import FileMetadata


def mock_queue_qc(qc, *args, **kwargs):
    return qc


@pytest.fixture
def mirna_replicated_analysis(
    mock_accession_gc_backend: MockFixture, mirna_replicated_metadata_path: str
) -> Analysis:  # noqa: F811
    analysis = Analysis(
        FileMetadata(mirna_replicated_metadata_path), backend=mock_accession_gc_backend
    )
    return analysis


@pytest.fixture
def mock_replicated_mirna_accession(mocker, mirna_replicated_analysis, mock_accession):
    """
    Contains a legitimate replicated mirna analysis for purposes of testing mirna qm
    generation without creating any connections to servers.
    """
    mocker.patch.object(mock_accession, "analysis", mirna_replicated_analysis)
    mocker.patch.object(mock_accession, "backend", mirna_replicated_analysis.backend)
    mocker.patch.object(mock_accession, "queue_qc", mock_queue_qc)
    mocker.patch.object(
        mock_accession,
        "experiment",
        new_callable=PropertyMock(
            return_value=EncodeExperiment(
                {
                    "@id": "foo",
                    "assay_term_name": "microRNA",
                    "replicates": [
                        {"biological_replicate_number": 1},
                        {"biological_replicate_number": 2},
                    ],
                }
            )
        ),
    )
    return mock_accession


@pytest.mark.docker
@pytest.mark.filesystem
def test_accession_mirna_replicated(
    accessioner_factory, mirna_replicated_metadata_path
):
    factory = accessioner_factory(
        metadata_file=mirna_replicated_metadata_path, assay_name="mirna"
    )
    accessioner, expected_files = next(factory)
    accessioner.accession_steps(force=True)
    validate_accessioning(
        accessioner, expected_files, expected_num_files=12, dataset="ENCSR715NEZ"
    )


@pytest.mark.docker
@pytest.mark.filesystem
def test_accession_mirna_unreplicated(accessioner_factory):
    current_dir = Path(__file__).resolve()
    metadata_json_path = (
        current_dir.parent / "data" / "mirna_unreplicated_metadata.json"
    )
    factory = accessioner_factory(metadata_file=metadata_json_path, assay_name="mirna")
    accessioner, expected_files = next(factory)
    accessioner.accession_steps(force=True)
    validate_accessioning(
        accessioner, expected_files, expected_num_files=6, dataset="ENCSR543MWW"
    )


def validate_accessioning(accessioner, expected_files, expected_num_files, dataset):
    all_files = accessioner.conn.get("/files/", database=True)["@graph"]
    accessioner.conn.get(f"/files/?dataset=/experiments/{dataset}/", database=True)[
        "@graph"
    ]
    all_quality_metrics = [
        accessioner.conn.get(qm["@id"], database=True, frame="object")
        for qm in accessioner.conn.get("/quality-metrics/", database=True)["@graph"]
    ]
    excluded_types = ("reads", "genome index", "genome reference")
    files = [
        f
        for f in all_files
        if f["output_type"] not in excluded_types
        and f["dataset"] == f"/experiments/{dataset}/"
    ]
    assert len(files) == expected_num_files
    shared_keys_to_skip = ["submitted_by", "date_created", "@id", "uuid"]
    file_keys_to_skip = [
        "title",
        "accession",
        "file_size",
        "cloud_metadata",
        "href",
        "s3_uri",
        "no_file_available",
        "analysis_step_version",
        "content_md5sum",
        "matching_md5sum",
        "audit",
        "schema_version",
    ]
    qm_keys_to_skip = ["step_run"]
    for keys_to_skip in (file_keys_to_skip, qm_keys_to_skip):
        keys_to_skip.extend(shared_keys_to_skip)
    for partial_file in files:
        file = accessioner.conn.get(
            partial_file["@id"], frame="embedded", database=True
        )
        quality_metrics = [
            qm for qm in all_quality_metrics if file["@id"] in qm["quality_metric_of"]
        ]
        aliases = file["aliases"]
        expected = [f for f in expected_files if f["aliases"] == aliases][0]
        for key, expected_value in expected.items():
            if key in file_keys_to_skip:
                continue
            elif key == "step_run":
                for step_run_key in ("analysis_step_version", "aliases"):
                    assert file[key][step_run_key] == expected_value[step_run_key]
                assert file[key]["status"] == "in progress"
            elif key == "status":
                assert file[key] == "uploading"
            elif key in ("award", "lab"):
                assert file[key]["@id"] == expected_value["@id"]
            elif key == "file_size":
                assert file[key] == 3
            elif key == "derived_from":
                derived_from_aliases = []
                for i in all_files:
                    if i["@id"] in file[key]:
                        db_file = accessioner.conn.get(i["@id"], database=True)
                        derived_from_aliases.append(
                            (db_file["aliases"], db_file["md5sum"])
                        )
                expected_aliases = [
                    (f["aliases"], f["md5sum"])
                    for f in expected_files
                    if f["@id"] in expected_value
                ]
                assert sorted(derived_from_aliases) == sorted(expected_aliases)
            elif key == "quality_metrics":
                if not expected_value:
                    assert not quality_metrics
                else:
                    for expected_qm in expected_value:
                        posted_qms = [
                            qm
                            for qm in quality_metrics
                            if qm["@type"] == expected_qm["@type"]
                        ]
                        assert len(posted_qms) == 1
                        posted_qm = posted_qms[0]
                        for qm_key, qm_value in expected_qm.items():
                            if qm_key == "quality_metric_of":
                                assert len(qm_value) == len(posted_qm[qm_key])
                            elif qm_key in qm_keys_to_skip:
                                continue
                            elif qm_key == "status":
                                assert posted_qm[qm_key] == "in progress"
                            else:
                                assert qm_value == posted_qm[qm_key]
            else:
                assert file[key] == expected_value


@pytest.mark.filesystem
def test_make_microrna_mapping_qc(mock_replicated_mirna_accession, encode_file_no_qc):
    gs_file = [
        i
        for i in mock_replicated_mirna_accession.analysis.get_files(filekey="bam")
        if "rep1" in i.filename
    ][0]
    qc = mock_replicated_mirna_accession.make_microrna_mapping_qc(
        encode_file_no_qc, gs_file
    )
    assert qc == {"aligned_reads": 5873570}


@pytest.mark.filesystem
def test_make_microrna_correlation_qc_replicated(
    mock_replicated_mirna_accession, encode_file_no_qc
):
    gs_file = [
        i for i in mock_replicated_mirna_accession.analysis.get_files(filekey="tsv")
    ][0]
    qc = mock_replicated_mirna_accession.make_microrna_correlation_qc(
        encode_file_no_qc, gs_file
    )
    assert qc == {"Spearman correlation": 0.8885044458946942}


@pytest.mark.filesystem
def test_make_microrna_correlation_qc_unreplicated_returns_none(
    mocker, mock_accession_unreplicated, mirna_replicated_analysis, encode_file_no_qc
):
    mocker.patch.object(
        mock_accession_unreplicated, "analysis", mirna_replicated_analysis
    )
    mocker.patch.object(
        mock_accession_unreplicated, "backend", mirna_replicated_analysis.backend
    )
    mocker.patch.object(mock_accession_unreplicated, "queue_qc", mock_queue_qc)
    gs_file = [
        i for i in mock_accession_unreplicated.analysis.get_files(filekey="tsv")
    ][0]
    qc = mock_accession_unreplicated.make_microrna_correlation_qc(
        encode_file_no_qc, gs_file
    )
    assert qc is None


@pytest.mark.filesystem
def test_make_star_qc_metric(mock_replicated_mirna_accession, encode_file_no_qc):
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
    qc = mock_replicated_mirna_accession.make_star_qc_metric(encode_file_no_qc, gs_file)
    for k, v in qc.items():
        assert v == expected[k]


@pytest.mark.filesystem
def test_make_microrna_quantification_qc(
    mock_replicated_mirna_accession, encode_file_no_qc
):
    gs_file = [
        i
        for i in mock_replicated_mirna_accession.analysis.get_files(filekey="bam")
        if "rep1" in i.filename
    ][0]
    qc = mock_replicated_mirna_accession.make_microrna_quantification_qc(
        encode_file_no_qc, gs_file
    )
    assert qc == {"expressed_mirnas": 393}
